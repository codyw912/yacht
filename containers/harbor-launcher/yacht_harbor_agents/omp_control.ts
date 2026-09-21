import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";
import {
	createAgentSession,
	SessionManager,
	Settings,
	type AgentSession,
} from "@oh-my-pi/pi-coding-agent";
import { initializeExtensions } from "@oh-my-pi/pi-coding-agent/modes/runtime-init";
import { discoverAdvisorConfigs } from "@oh-my-pi/pi-coding-agent/advisor/config";
import { AdmissionController } from "./omp_admission.ts";
import {
	CONTROLLED_ENV,
	CONTROLLED_SETTINGS,
	RESTRICT_TOOL_NAMES,
	assertNoModelSpawningTools,
	assertRequiredNativeTools,
	assertSideInferenceGuards,
	controlledToolRoster,
	parseExactModelSelector,
} from "./omp_policy.ts";
import { encodeFrame, parseCommand, type DriverCommand, type DriverFrame } from "./omp_protocol.ts";
import {
	abortAndQuiesce,
	attachAdmissionGate,
	runControlledPrompt,
	type ControlledHost,
	type PromptSettle,
} from "./omp_session.ts";

type DriverState = {
	session: AgentSession;
	host: ControlledHost;
	admission: AdmissionController;
	model: string;
	deadlineMs: number;
	protectedPids: number[];
	unsubscribeEvents: () => void;
	detachGate: () => void;
};

let driver: DriverState | undefined;
let promptTask: Promise<void> | undefined;
let stdoutFlushed = true;

function writeFrame(frame: DriverFrame): void {
	// `write` returning false means the payload is buffered; `drainStdout`
	// awaits that flush before the process is allowed to exit.
	stdoutFlushed = stdout.write(`${encodeFrame(frame)}\n`);
}

/** Resolve once every queued stdout frame has actually left the process. */
async function drainStdout(): Promise<void> {
	if (stdoutFlushed) return;
	const { promise, resolve } = Promise.withResolvers<void>();
	stdout.once("drain", resolve);
	await promise;
	stdoutFlushed = true;
}

function writeResponse(id: string, success: boolean, data: unknown): void {
	writeFrame({ type: "response", id, success, data });
}

function writeError(id: string, error: unknown, code = "error"): void {
	const message = error instanceof Error ? error.message : String(error);
	writeResponse(id, false, { error: message, code });
}

export function sessionHost(session: AgentSession): ControlledHost {
	const agent = session.agent;
	const host: ControlledHost = {
		prompt: (message) => session.prompt(message),
		abort: () => session.abort({ goalReason: "internal" }),
		waitForIdle: () => session.waitForIdle(),
		addBeforeModelCall: (fn) => agent.addBeforeModelCall(fn),
		busy: () => session.isStreaming,
		messages: () => agent.state.messages,
		subscribe: (fn) => agent.subscribe(fn as never),
		advisorStats: () => {
			if (!session.isAdvisorEnabled()) return undefined;
			const stats = session.getAdvisorStats();
			return {
				enabled: stats.configured,
				cost_usd: stats.cost,
				advisors: stats.advisors.map((a) => ({
					name: a.name,
					status: a.status,
					model: a.model ? `${a.model.provider}/${a.model.id}` : undefined,
					tokens: { ...a.tokens },
					cost: a.cost,
					messages: { ...a.messages },
				})),
			};
		},
		drainAdvisors: async (timeoutMs) => {
			if (!session.isAdvisorEnabled()) return true;
			// Preserve late advisor notes as cards rather than letting a blocker
			// triggerTurn the primary after its terminal answer, then wait for the
			// in-flight review to land so the settle's advisor block is complete.
			session.prepareForHeadlessAdvisorDrain();
			return session.waitForAdvisorCatchup(timeoutMs);
		},
	};
	Object.defineProperty(host, "beforeToolCall", {
		get: () => agent.beforeToolCall,
		set: (fn: ControlledHost["beforeToolCall"]) => {
			agent.beforeToolCall = fn;
		},
		enumerable: true,
		configurable: true,
	});
	return host;
}

function protectedPids(): number[] {
	return driver?.protectedPids ?? [process.pid];
}

async function disposeSession(session: AgentSession | undefined): Promise<void> {
	if (!session) return;
	try {
		session.agent.abort();
		await Promise.race([
			session.dispose?.() ?? session.waitForIdle(),
			new Promise((resolve) => setTimeout(resolve, 5_000)),
		]);
	} catch {
		// Best-effort bounded disposal after failed init or shutdown.
	}
}

async function handleInit(cmd: Extract<DriverCommand, { type: "init" }>): Promise<void> {
	if (driver) throw new Error("already initialized");
	Bun.env.PI_NO_TITLE = CONTROLLED_ENV.PI_NO_TITLE;
	const parsed = parseExactModelSelector(cmd.model);
	const advisorSpec = cmd.advisor;
	const advisorParsed = advisorSpec ? parseExactModelSelector(advisorSpec.model) : undefined;
	// Hoisted so the init policy response (below) can report the resolved roster;
	// populated only when the advisor arm runs.
	let advisorTools: string[] | undefined;
	const settings = await Settings.loadIsolated({ cwd: process.cwd() });
	for (const [path, value] of Object.entries(CONTROLLED_SETTINGS)) {
		settings.override(path as never, value as never);
	}

	const selector = `${parsed.provider}/${parsed.id}`;
	const created = await createAgentSession({
		sessionManager: SessionManager.inMemory(),
		settings,
		modelPattern: selector,
		thinkingLevel: parsed.thinkingLevel as "medium" | "low" | "high" | "minimal" | "xhigh" | "max" | undefined,
		restrictToolNames: RESTRICT_TOOL_NAMES,
		enableMCP: true,
		deadline: cmd.deadline_ms,
	});
	const session = created.session;
	try {
		if (created.modelFallbackMessage) {
			throw new Error(`model fallback refused: ${created.modelFallbackMessage}`);
		}
		const model = session.agent.state.model;
		if (!model) throw new Error("model not configured");
		const resolved = `${model.provider}/${model.id}`;
		if (resolved !== selector) {
			throw new Error(`model mismatch: wanted ${selector}, got ${resolved}`);
		}
		assertSideInferenceGuards((path) => session.settings.get(path as never));
		const roster = controlledToolRoster(session.getEnabledToolNames(), session.getMountedXdevToolNames());
		assertRequiredNativeTools(roster);
		assertNoModelSpawningTools(roster);
		await session.setActiveToolsByName(roster);
		if (advisorSpec && advisorParsed) {
			// The advisor roster must come from the controller, not the filesystem:
			// the evaluated agent shares the workspace and could plant a
			// WATCHDOG.yml to replace the advisor roster at the next runtime
			// rebuild.
			const discovered = await discoverAdvisorConfigs(process.cwd());
			if (discovered.advisors.length > 0) {
				throw new Error(
					"project WATCHDOG.yml discovered during controlled execution; " +
						"an agent-writable advisor roster is an infrastructure error",
				);
			}
			// The advisor's tool set is bounded like the primary's: it must not
			// reach the model-spawning tools the controlled primary is denied.
			advisorTools = advisorSpec.tools ?? ["read", "grep", "glob"];
			assertNoModelSpawningTools(advisorTools);
			const advisorSelector = `${advisorParsed.provider}/${advisorParsed.id}`;
			// advisor.enabled was held off through createAgentSession so no legacy
			// default advisor built. Install the controller's restricted roster
			// first (stored only while disabled), then enable — enabling first
			// would build a legacy {name:"default"} advisor before the swap.
			session.applyAdvisorConfigs(
				[
					{
						name: "controlled",
						// Full selector (with :level) so the advisor's thinking level
						// resolves; advisorSelector below is the bare provider/id used
						// only for the resolved-model comparison.
						model: advisorSpec.model,
						tools: advisorTools,
						instructions: advisorSpec.instructions,
					},
				],
				undefined,
			);
			session.setAdvisorEnabled(true);
			if (!session.isAdvisorEnabled() || !session.isAdvisorActive()) {
				throw new Error("advisor enabled but no advisor runtime resolved");
			}
			// setAdvisorEnabled flips the live runtime but not the recorded
			// setting; sync it so the reported policy and the runtime agree.
			session.settings.override("advisor.enabled" as never, true as never);
			const advisorModel = session.getAdvisorAgent()?.state.model;
			const advisorResolved = advisorModel
				? `${advisorModel.provider}/${advisorModel.id}`
				: undefined;
			if (advisorResolved !== advisorSelector) {
				throw new Error(
					`advisor model mismatch: wanted ${advisorSelector}, got ${advisorResolved ?? "none"}`,
				);
			}
		}
		// Emit session_start so extensions (e.g. the advisor-gate provider
		// plugin) capture their ExtensionContext. The controlled driver bypasses
		// the mode layer that normally emits this, so without it the plugin's
		// streamSimple sees an undefined ctx and fails the advisor arm.
		await initializeExtensions(session, {
			reportSendError: (action, error) =>
				console.error(`[extension ${action}]`, error),
			reportRuntimeError: (error) => console.error("[extension]", error),
			mode: "print",
		});
		const admission = new AdmissionController();
		const host = sessionHost(session);
		const detachGate = attachAdmissionGate(host, admission, (gated) => {
			try {
				writeFrame({
					type: "context",
					turn_id: gated.turnId,
					loop: gated.loop,
					context: gated.context,
				});
			} catch (error) {
				admission.halt("event_frame");
				writeError("context", error, "event_frame");
				throw error;
			}
		});
		const unsubscribeEvents = session.agent.subscribe((event) => {
			try {
				writeFrame({ type: "event", event });
			} catch (error) {
				admission.halt("event_frame");
				void abortAndQuiesce(host, { timeoutMs: 5_000, protectedPids: [process.pid] });
				writeError("event", error, "event_frame");
			}
		});
		driver = {
			session,
			host,
			admission,
			model: cmd.model,
			deadlineMs: cmd.deadline_ms,
			protectedPids: [process.pid],
			unsubscribeEvents,
			detachGate,
		};
		writeResponse(cmd.id, true, {
			ready: true,
			session_id: session.sessionManager.getSessionId(),
			model: cmd.model,
			policy: {
				...CONTROLLED_SETTINGS,
				"advisor.enabled": advisorSpec !== undefined,
				tools: roster,
				...(advisorSpec ? { advisor: { model: advisorSpec.model, tools: advisorTools } } : {}),
			},
			protected_pids: driver.protectedPids,
		});
	} catch (error) {
		await disposeSession(session);
		throw error;
	}
}

async function handlePrompt(cmd: Extract<DriverCommand, { type: "prompt" }>): Promise<void> {
	if (!driver) throw new Error("not initialized");
	const settle: PromptSettle = await runControlledPrompt(driver.host, driver.admission, {
		turnId: cmd.turn_id,
		message: cmd.message,
		maxTurns: cmd.max_turns,
		timeoutSeconds: cmd.timeout_seconds,
		sessionId: driver.session.sessionManager.getSessionId(),
		protectedPids: protectedPids(),
		overallDeadlineMs: driver.deadlineMs,
	});
	writeResponse(cmd.id, true, settle);
}

async function handleAbort(cmd: Extract<DriverCommand, { type: "abort" }>): Promise<void> {
	if (!driver) throw new Error("not initialized");
	const quiescence = await abortAndQuiesce(driver.host, {
		timeoutMs: 5_000,
		protectedPids: protectedPids(),
	});
	writeResponse(cmd.id, true, {
		ended: driver.admission.ended ?? "timeout",
		loops_started: driver.admission.loopsStarted,
		loops_completed: driver.admission.loopsCompleted,
		continuation_possible: quiescence.continuation_possible,
		session_id: driver.session.sessionManager.getSessionId(),
		quiescence: { ready: quiescence.ready, protected_pids: quiescence.protected_pids },
	});
}

function handleState(cmd: Extract<DriverCommand, { type: "state" }>): void {
	if (!driver) throw new Error("not initialized");
	writeResponse(cmd.id, true, {
		ready: !driver.admission.halted,
		model: driver.model,
		closed: driver.admission.closed,
		halted: driver.admission.halted,
		loops_started: driver.admission.loopsStarted,
		cumulative_loops_started: driver.admission.cumulativeLoopsStarted,
		quiescence: { ready: !driver.session.isStreaming, protected_pids: protectedPids() },
	});
}

async function handleShutdown(cmd: Extract<DriverCommand, { type: "shutdown" }>): Promise<void> {
	const current = driver;
	if (current) {
		current.admission.halt("error");
		await abortAndQuiesce(current.host, { timeoutMs: 5_000, protectedPids: protectedPids() });
		current.unsubscribeEvents();
		current.detachGate();
		await disposeSession(current.session);
		driver = undefined;
	}
	writeResponse(cmd.id, true, { ready: false });
}

export async function dispatchCommand(cmd: DriverCommand): Promise<void> {
	switch (cmd.type) {
		case "init":
			await handleInit(cmd);
			return;
		case "prompt":
			if (promptTask) throw new Error("overlapping prompt");
			promptTask = handlePrompt(cmd)
				.catch((error) => writeError(cmd.id, error))
				.finally(() => {
					promptTask = undefined;
				});
			return;
		case "abort":
			await handleAbort(cmd);
			return;
		case "state":
			handleState(cmd);
			return;
		case "shutdown":
			if (driver) {
				driver.admission.halt("error");
				await abortAndQuiesce(driver.host, { timeoutMs: 5_000, protectedPids: protectedPids() });
			}
			if (promptTask) await promptTask.catch(() => undefined);
			await handleShutdown(cmd);
			return;
	}
}

export async function main(): Promise<void> {
	const rl = createInterface({ input: stdin, crlfDelay: Infinity });
	try {
		for await (const line of rl) {
			if (!line.trim()) continue;
			let cmd: DriverCommand;
			try {
				cmd = parseCommand(line);
			} catch (error) {
				writeError("unknown", error, "protocol");
				continue;
			}
			try {
				await dispatchCommand(cmd);
				if (cmd.type === "shutdown") break;
			} catch (error) {
				writeError(cmd.id, error);
			}
		}
	} finally {
		// Release the stdin reader so it cannot hold the loop open, then let
		// every queued frame reach the controller before anything else.
		rl.close();
		stdin.pause();
		await drainStdout();
	}
}

if (import.meta.main) {
	await main();
	// The SDK leaves live handles (native watchers, pooled transports, pending
	// timers) that outlast shutdown, so awaiting a natural exit hangs the
	// controller's close. Exit explicitly — strictly after the stdout drain
	// above, never before it.
	process.exit(0);
}
