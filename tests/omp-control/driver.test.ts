import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { describe, expect, it } from "bun:test";
import { createMockModel, registerMockApi } from "@oh-my-pi/pi-ai/providers/mock";
import { AuthStorage, createAgentSession, ModelRegistry, SessionManager, Settings } from "@oh-my-pi/pi-coding-agent";
import { AdmissionController } from "../../containers/harbor-launcher/yacht_harbor_agents/omp_admission.ts";
import { sessionHost } from "../../containers/harbor-launcher/yacht_harbor_agents/omp_control.ts";
import { CONTROLLED_SETTINGS } from "../../containers/harbor-launcher/yacht_harbor_agents/omp_policy.ts";
import {
	attachAdmissionGate,
	runControlledPrompt,
} from "../../containers/harbor-launcher/yacht_harbor_agents/omp_session.ts";

registerMockApi();

const DRIVER = join(
	dirname(dirname(import.meta.dir)),
	"containers",
	"harbor-launcher",
	"yacht_harbor_agents",
	"omp_control.ts",
);

async function controlledSession(
	responses: Parameters<typeof createMockModel>[0]["responses"],
	options?: { withCredential?: boolean; registerAdvisorModel?: boolean },
) {
	const cwd = await mkdtemp(join(tmpdir(), "yacht-driver-"));
	const mock = createMockModel({ responses });
	const settings = await Settings.loadIsolated({ cwd, agentDir: cwd });
	for (const [path, value] of Object.entries(CONTROLLED_SETTINGS)) {
		settings.override(path as never, value as never);
	}
	// AgentSession.prompt preflights the registry for a provider key, so the
	// mock provider needs a real (in-memory) credential like any other.
	const authStorage = await AuthStorage.create(join(cwd, "auth.db"));
	if (options?.withCredential !== false) {
		authStorage.setRuntimeApiKey(mock.provider, "mock-key");
	}
	const modelRegistry = new ModelRegistry(authStorage, join(cwd, "models.yml"), { settings });
	if (options?.registerAdvisorModel) {
		// The advisor resolves config.model through resolveModelOverride against
		// the registry's available set — the injected mock model never enters it,
		// so register the mock provider explicitly or the advisor lands no_model.
		modelRegistry.registerProvider("mock", {
			api: "mock",
			baseUrl: "mock://",
			apiKey: "mock-key",
			models: [
				{
					id: "mock-model",
					name: "mock-model",
					reasoning: false,
					input: ["text"],
					cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
					contextWindow: 200000,
					maxTokens: 32768,
				},
			],
		} as never);
	}
	const created = await createAgentSession({
		cwd,
		agentDir: cwd,
		sessionManager: SessionManager.inMemory(),
		model: mock,
		modelRegistry,
		settings,
		disableExtensionDiscovery: true,
		enableMCP: false,
		restrictToolNames: false,
	});
	return { created, mock };
}

describe("production driver seams", () => {
	it("caps a real AgentSession prompt through the production host", async () => {
		const { created, mock } = await controlledSession([
			{ content: ["first answer"], usage: { input: 5, output: 2, totalTokens: 7 } },
			{ content: ["should not be reached"] },
		]);
		try {
			const admission = new AdmissionController();
			const host = sessionHost(created.session);
			attachAdmissionGate(host, admission);
			const settle = await runControlledPrompt(host, admission, {
				turnId: "initial",
				message: "say hello",
				maxTurns: 1,
				sessionId: created.session.sessionManager.getSessionId(),
			});
			const diagnostic = JSON.stringify({
				settleError: settle.error,
				ended: settle.ended,
				stateError: created.session.agent.state.error,
				model: created.session.agent.state.model?.api,
				assistant: created.session.agent.state.messages
					.filter((message) => message.role === "assistant")
					.map((message) => ({
						stopReason: "stopReason" in message ? message.stopReason : undefined,
						errorMessage: "errorMessage" in message ? message.errorMessage : undefined,
					})),
			});
			expect(`${mock.calls.length} ${diagnostic}`).toStartWith("1 ");
			expect(settle.loops_started).toBe(1);
			expect(settle.loops_completed).toBe(1);
			expect(settle.ended).toBe("natural");
			expect(settle.usage).toEqual(expect.objectContaining({ input: 5, output: 2 }));
			expect(admission.contexts[0]?.context.tools?.some((tool) => tool.name === "read")).toBe(true);
		} finally {
			await created.session.dispose();
		}
	});

	it("arms a controller-supplied advisor and reports its stats", async () => {
		const { created } = await controlledSession([{ content: ["answer"] }], {
			registerAdvisorModel: true,
		});
		try {
			const session = created.session;
			// Mirror handleInit's advisor arm: install the restricted roster while
			// advisor.enabled is still off (so no legacy default advisor builds),
			// then enable. config.model wins outright via resolveModelOverride —
			// modelRoles.advisor is only the fallback when config.model is unset.
			session.applyAdvisorConfigs(
				[{ name: "controlled", model: "mock/mock-model", tools: ["read", "grep", "glob"] }],
				undefined,
			);
			session.setAdvisorEnabled(true);
			session.settings.override("advisor.enabled" as never, true as never);

			// The controller roster is installed verbatim — one advisor named
			// "controlled", not a filesystem-discovered or legacy "default" entry.
			expect(session.isAdvisorEnabled()).toBe(true);
			expect(session.isAdvisorActive()).toBe(true);
			const host = sessionHost(session);
			const stats = host.advisorStats?.();
			expect(stats?.enabled).toBe(true);
			expect(stats?.advisors.map((a) => a.name)).toEqual(["controlled"]);
			expect(stats?.advisors[0]?.status).toBe("running");
			expect(stats?.advisors[0]?.model).toBe("mock/mock-model");
		} finally {
			await created.session.dispose();
		}
	});

	it("reports no advisor block when the arm is not opted in", async () => {
		const { created } = await controlledSession([{ content: ["answer"] }]);
		try {
			const host = sessionHost(created.session);
			expect(host.advisorStats?.()).toBeUndefined();
		} finally {
			await created.session.dispose();
		}
	});

	it("marks the advisor error when the pre-settle drain fails", async () => {
		// A drain that times out or fails means the advisor's final review was
		// still in flight when the settle was captured — the reported spend is
		// partial, so the settle must surface "error", not a clean "running".
		const host = {
			prompt: () => Promise.resolve(true),
			abort: () => {},
			waitForIdle: () => Promise.resolve(),
			addBeforeModelCall: () => () => {},
			busy: () => false,
			messages: () => [{ role: "assistant", content: "done" }],
			advisorStats: () => ({
				enabled: true,
				cost_usd: 0.5,
				advisors: [
					{
						name: "controlled",
						status: "running",
						model: "mock/mock-model",
						tokens: { input: 10, output: 2 },
						cost: 0.5,
						messages: { user: 1, assistant: 1, total: 2 },
					},
				],
			}),
			drainAdvisors: () => Promise.resolve(false),
		};
		const admission = new AdmissionController();
		const settle = await runControlledPrompt(host as never, admission, {
			turnId: "t1",
			message: "go",
			maxTurns: 1,
			sessionId: "s1",
		});
		expect(settle.advisor?.advisors[0]?.status).toBe("error");
	});

	it("keeps the second scripted message in the same session history", async () => {
		const { created, mock } = await controlledSession([
			{ content: ["stored ORANGE-42"] },
			{ content: ["still remembered"] },
		]);
		try {
			const admission = new AdmissionController();
			const host = sessionHost(created.session);
			attachAdmissionGate(host, admission);
			const sessionId = created.session.sessionManager.getSessionId();
			await runControlledPrompt(host, admission, {
				turnId: "m1",
				message: "remember ORANGE-42",
				maxTurns: 1,
				sessionId,
			});
			const second = await runControlledPrompt(host, admission, {
				turnId: "m2",
				message: "what did I say?",
				maxTurns: 1,
				sessionId,
			});
			const secondDiagnostic = JSON.stringify({
				error: second.error,
				invalid: second.invalid,
				loops: [second.loops_started, second.loops_completed],
				baselineUsers: admission.lastPrefix?.userTexts,
				baselineAssistants: admission.lastPrefix?.assistantTexts,
				contexts: admission.contexts.map((entry) => ({
					turn: entry.turnId,
					loop: entry.loop,
					roles: (entry.context.messages ?? []).map((message) =>
						message && typeof message === "object" && "role" in message ? message.role : "?",
					),
				})),
				assistant: created.session.agent.state.messages
					.filter((message) => message.role === "assistant")
					.map((message) => ({
						stopReason: "stopReason" in message ? message.stopReason : undefined,
						errorMessage: "errorMessage" in message ? message.errorMessage : undefined,
					})),
			});
			expect(`${second.ended} ${secondDiagnostic}`).toStartWith("natural ");
			expect(mock.calls).toHaveLength(2);
			const lastContext = admission.contexts.at(-1)?.context;
			const serialized = JSON.stringify(lastContext?.messages);
			expect(serialized).toContain("remember ORANGE-42");
			expect(serialized).toContain("stored ORANGE-42");
		} finally {
			await created.session.dispose();
		}
	});

	it("reports a missing provider credential as error, not timeout", async () => {
		const { created } = await controlledSession([{ content: ["unreachable"] }], { withCredential: false });
		try {
			const admission = new AdmissionController();
			const host = sessionHost(created.session);
			attachAdmissionGate(host, admission);
			const settle = await runControlledPrompt(host, admission, {
				turnId: "noauth",
				message: "go",
				maxTurns: 2,
				timeoutSeconds: 600,
				sessionId: created.session.sessionManager.getSessionId(),
			});
			expect(settle.ended).toBe("error");
			expect(settle.error).toContain("API key");
			expect(settle.loops_started).toBe(0);
		} finally {
			await created.session.dispose();
		}
	});

	it("answers state and rejects a prompt before init over real stdin", async () => {
		const child = Bun.spawn([process.execPath, DRIVER], {
			stdin: "pipe",
			stdout: "pipe",
			stderr: "pipe",
			env: { ...process.env, PATH: "" },
		});
		const responses: Array<Record<string, unknown>> = [];
		const reader = (async () => {
			const decoder = new TextDecoder();
			let buffer = "";
			for await (const chunk of child.stdout) {
				buffer += decoder.decode(chunk);
				let index = buffer.indexOf("\n");
				while (index >= 0) {
					const line = buffer.slice(0, index).trim();
					buffer = buffer.slice(index + 1);
					if (line) responses.push(JSON.parse(line));
					index = buffer.indexOf("\n");
				}
			}
		})();
		child.stdin.write(`${JSON.stringify({ id: "s1", type: "state" })}\n`);
		child.stdin.write(
			`${JSON.stringify({ id: "p1", type: "prompt", turn_id: "Q", message: "hi", max_turns: 1, timeout_seconds: 5 })}\n`,
		);
		child.stdin.write("{not json}\n");
		child.stdin.write(`${JSON.stringify({ id: "x1", type: "shutdown" })}\n`);
		await reader;
		// No kill here: the driver must exit on its own after the shutdown ack.
		expect(await child.exited).toBe(0);
		const byId = new Map(responses.map((frame) => [frame.id as string, frame]));
		expect(byId.get("s1")).toEqual({
			type: "response",
			id: "s1",
			success: false,
			data: { error: "not initialized", code: "error" },
		});
		expect(byId.get("p1")).toEqual({
			type: "response",
			id: "p1",
			success: false,
			data: { error: "not initialized", code: "error" },
		});
		const protocolFrame = byId.get("unknown");
		expect(protocolFrame?.success).toBe(false);
		expect((protocolFrame?.data as { code?: string }).code).toBe("protocol");
	});

	it("acks shutdown and exits on its own without being killed", async () => {
		const child = Bun.spawn([process.execPath, DRIVER], {
			stdin: "pipe",
			stdout: "pipe",
			stderr: "pipe",
			env: { ...process.env, PATH: "" },
		});
		child.stdin.write(`${JSON.stringify({ id: "x1", type: "shutdown" })}\n`);
		// Real timer by necessity: this asserts a real subprocess terminates, and
		// fake timers cannot drive another process's exit. The bound is a failure
		// deadline, not a guessed settle delay - a healthy driver exits at once.
		const timeout = Promise.withResolvers<"hung">();
		const timer = setTimeout(() => timeout.resolve("hung"), 5_000);
		const outcome = await Promise.race([child.exited.then(() => "exited" as const), timeout.promise]);
		clearTimeout(timer);
		if (outcome === "hung") child.kill();
		// The shutdown ack must still be readable: exiting may not truncate stdout.
		const text = await new Response(child.stdout).text();
		const frames = text
			.split("\n")
			.filter((line) => line.trim())
			.map((line) => JSON.parse(line));
		expect(frames.at(-1)).toEqual({
			type: "response",
			id: "x1",
			success: true,
			data: { ready: false },
		});
		expect(outcome).toBe("exited");
	});
});
