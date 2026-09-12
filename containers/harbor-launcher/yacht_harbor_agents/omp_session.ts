import { AdmissionController, type Ended, type InvalidReason } from "./omp_admission.ts";
import { isQuestionRead, QUESTION_READ_BLOCK } from "./omp_policy.ts";

export type QuiescenceReport = {
	ready: boolean;
	protected_pids: number[];
	continuation_possible: boolean;
	reaped_descendants?: undefined;
};

export type PromptSettle = {
	ended: Ended;
	loops_started: number;
	loops_completed: number;
	continuation_possible: boolean;
	session_id: string;
	started_at: string;
	ended_at: string;
	usage: {
		input?: number;
		output?: number;
		cacheRead?: number;
		cacheWrite?: number;
		totalTokens?: number;
	} | null;
	cost: number | null;
	quiescence: { ready: boolean; protected_pids: number[] };
	invalid?: { reason: InvalidReason };
	/** Present when the prompt call itself threw; never a silent swallow. */
	error?: string;
};

export type HostMessage = {
	role?: string;
	content?: unknown;
	stopReason?: string;
	errorMessage?: string;
	usage?: {
		input?: number;
		output?: number;
		cacheRead?: number;
		cacheWrite?: number;
		totalTokens?: number;
		cost?: { total?: number };
	};
	model?: string;
};

export type ControlledHost = {
	prompt(message: string): Promise<unknown>;
	abort(): unknown;
	waitForIdle(): Promise<void>;
	addBeforeModelCall(
		fn: (context: { messages?: unknown[]; systemPrompt?: string[] }, signal?: AbortSignal) => unknown,
	): () => void;
	busy(): boolean;
	messages(): readonly HostMessage[];
	beforeToolCall?: (ctx: { toolCall: { name: string }; args: Record<string, unknown> }, signal?: AbortSignal) => unknown;
	subscribe?: (fn: (event: { type: string; message?: HostMessage }) => void) => () => void;
};

export type RunPromptInput = {
	turnId: string;
	message: string;
	maxTurns: number;
	timeoutSeconds?: number;
	sessionId: string;
	protectedPids?: number[];
	overallDeadlineMs?: number;
};

type InFlight = {
	admission: AdmissionController;
	sessionId: string;
	protectedPids: number[];
	startedAt: string;
	resolve: (settle: PromptSettle) => void;
	settled: boolean;
};

const inFlightByHost = new WeakMap<object, InFlight>();

export function attachAdmissionGate(
	host: ControlledHost,
	admission: AdmissionController,
	onAdmit?: (gated: { turnId: string; loop: number; context: unknown }) => void,
): () => void {
	const previous = host.beforeToolCall;
	host.beforeToolCall = (ctx, signal) => {
		if (isQuestionRead(ctx.toolCall.name, ctx.args)) {
			return { block: true, reason: QUESTION_READ_BLOCK };
		}
		return previous?.(ctx, signal);
	};
	return host.addBeforeModelCall((context, signal) => {
		const before = admission.contexts.length;
		const result = admission.beforeModelCall(context, signal);
		if (admission.contexts.length > before) onAdmit?.(admission.contexts[admission.contexts.length - 1]!);
		return result;
	});
}

function isFailedAssistant(message: HostMessage): boolean {
	return (
		message.role === "assistant" &&
		(message.stopReason === "error" || message.stopReason === "aborted" || Boolean(message.errorMessage))
	);
}

/**
 * Per-message provider usage. A failed or aborted provider result whose own
 * usage is unknown makes the message total unknown rather than a partial sum
 * presented as complete.
 */
function usageFromSlice(messages: readonly HostMessage[]): PromptSettle["usage"] {
	let any = false;
	const usage = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0 };
	const keys = ["input", "output", "cacheRead", "cacheWrite", "totalTokens"] as const;
	const present: Record<(typeof keys)[number], boolean> = {
		input: false,
		output: false,
		cacheRead: false,
		cacheWrite: false,
		totalTokens: false,
	};
	for (const message of messages) {
		if (message.role !== "assistant") continue;
		if (isFailedAssistant(message)) return null;
		if (!message.usage) return null;
		any = true;
		for (const key of keys) {
			const value = message.usage[key];
			if (typeof value === "number") {
				present[key] = true;
				usage[key] += value;
			}
		}
	}
	if (!any) return null;
	const out: NonNullable<PromptSettle["usage"]> = {};
	for (const key of keys) {
		if (present[key]) out[key] = usage[key];
	}
	return out;
}

function costFromSlice(messages: readonly HostMessage[]): number | null {
	let total = 0;
	let any = false;
	for (const message of messages) {
		if (message.role !== "assistant") continue;
		if (isFailedAssistant(message)) return null;
		if (!message.usage?.cost || typeof message.usage.cost.total !== "number") return null;
		any = true;
		total += message.usage.cost.total;
	}
	return any ? total : null;
}

function classifyEnded(admission: AdmissionController, slice: readonly HostMessage[]): Ended {
	if (admission.invalid) return "error";
	if (admission.ended === "cap") return "cap";
	// Only a deadline or an explicit abort is a timeout. A generic prompt
	// rejection (auth preflight, provider construction, dropped prompt) is an
	// error and must not borrow the timeout label.
	if (admission.ended === "timeout") return "timeout";
	for (let i = slice.length - 1; i >= 0; i--) {
		const message = slice[i]!;
		if (message.role !== "assistant") continue;
		if (message.stopReason === "error" || message.errorMessage) return "error";
		break;
	}
	if (admission.ended === "error") return "error";
	return admission.ended ?? "natural";
}

function buildSettle(
	host: ControlledHost,
	admission: AdmissionController,
	input: {
		sessionId: string;
		protectedPids: number[];
		startedAt: string;
		ready?: boolean;
		error?: string;
	},
): PromptSettle {
	const slice = host.messages().slice(admission.messageStartIndex);
	const ended = classifyEnded(admission, slice);
	return {
		ended,
		loops_started: admission.loopsStarted,
		loops_completed: admission.loopsCompleted,
		continuation_possible: !admission.halted,
		session_id: input.sessionId,
		started_at: input.startedAt,
		ended_at: new Date().toISOString(),
		usage: usageFromSlice(slice),
		cost: costFromSlice(slice),
		quiescence: {
			ready: input.ready ?? !admission.halted,
			protected_pids: input.protectedPids,
		},
		invalid: admission.invalid,
		error: input.error,
	};
}

function finishInFlight(host: object, settle: PromptSettle): void {
	const inflight = inFlightByHost.get(host);
	if (!inflight || inflight.settled) return;
	inflight.settled = true;
	inflight.resolve(settle);
	inFlightByHost.delete(host);
}

export async function runControlledPrompt(
	host: ControlledHost,
	admission: AdmissionController,
	input: RunPromptInput,
): Promise<PromptSettle> {
	if (host.busy() || inFlightByHost.has(host)) {
		throw new Error("overlapping prompt");
	}
	const protectedPids = input.protectedPids ?? [];
	if (admission.halted || (admission.invalid && admission.invalid.reason !== "quiescence")) {
		admission.close();
		return buildSettle(host, admission, {
			sessionId: input.sessionId,
			protectedPids,
			startedAt: new Date().toISOString(),
			ready: false,
		});
	}
	if (admission.explicitlyClosed && admission.cumulativeLoopsStarted === 0) {
		admission.ended = "error";
		const settle = buildSettle(host, admission, {
			sessionId: input.sessionId,
			protectedPids,
			startedAt: new Date().toISOString(),
			ready: true,
		});
		settle.continuation_possible = true;
		admission.ended = undefined;
		return settle;
	}

	const startedAt = new Date().toISOString();
	admission.beginPrompt({
		turnId: input.turnId,
		maxTurns: input.maxTurns,
		timeoutSeconds: input.timeoutSeconds,
		messageStartIndex: host.messages().length,
	});
	if (admission.closed) {
		return buildSettle(host, admission, {
			sessionId: input.sessionId,
			protectedPids,
			startedAt,
			ready: true,
		});
	}

	const pending = Promise.withResolvers<PromptSettle>();
	inFlightByHost.set(host, {
		admission,
		sessionId: input.sessionId,
		protectedPids,
		startedAt,
		resolve: pending.resolve,
		settled: false,
	});

	const now = admission.now();
	const messageDeadline =
		input.timeoutSeconds !== undefined ? now + input.timeoutSeconds * 1000 : undefined;
	const overall = input.overallDeadlineMs;
	const wallMs = [messageDeadline, overall]
		.filter((value): value is number => value !== undefined)
		.reduce((min, value) => Math.min(min, value - now), Number.POSITIVE_INFINITY);

	let timedOut = false;
	let timer: ReturnType<typeof setTimeout> | undefined;
	if (Number.isFinite(wallMs) && wallMs <= 0) {
		timedOut = true;
		admission.ended = "timeout";
		await abortAndQuiesce(host, { timeoutMs: 1_000, protectedPids });
	} else if (Number.isFinite(wallMs)) {
		timer = setTimeout(() => {
			timedOut = true;
			admission.ended = "timeout";
			void abortAndQuiesce(host, { timeoutMs: 5_000, protectedPids });
		}, wallMs);
	}

	const unsub = host.subscribe?.((event) => {
		if (event.type !== "turn_end") return;
		const message = event.message;
		if (message?.role !== "assistant") return;
		if (message.errorMessage || message.stopReason === "error" || message.stopReason === "aborted") return;
		admission.markLoopCompleted();
	});
	let promptError: string | undefined;
	try {
		const promptWork = host.prompt(input.message).then(
			(accepted) => {
				if (accepted === false) {
					promptError = "prompt was dropped before dispatch";
					if (!admission.ended && !timedOut) admission.ended = "error";
				}
			},
			(error: unknown) => {
				promptError = error instanceof Error ? error.message : String(error);
				if (!admission.ended && !timedOut) admission.ended = "error";
			},
		);
		await Promise.race([promptWork, pending.promise.then(() => undefined)]);
	} finally {
		unsub?.();
		if (timer) clearTimeout(timer);
		const inflight = inFlightByHost.get(host);
		if (inflight && !inflight.settled) {
			const bound = Promise.withResolvers<"timeout">();
			const idleTimer = setTimeout(() => bound.resolve("timeout"), 5_000);
			// A rejected waitForIdle is a failure to settle, not a clean idle.
			const idle = host
				.waitForIdle()
				.then(() => "idle" as const)
				.catch((error: unknown) => {
					promptError ??= error instanceof Error ? error.message : String(error);
					return "failed" as const;
				});
			const settled = await Promise.race([idle, bound.promise]);
			clearTimeout(idleTimer);
			if (settled !== "idle") admission.halt("quiescence");
			admission.close();
			admission.recordSettledMessages(host.messages());
			finishInFlight(
				host,
				buildSettle(host, admission, {
					sessionId: input.sessionId,
					protectedPids,
					startedAt,
					ready: settled === "idle" && !admission.halted,
					error: promptError,
				}),
			);
		} else {
			admission.close();
			admission.recordSettledMessages(host.messages());
		}
	}
	return pending.promise;
}

export async function abortAndQuiesce(
	host: ControlledHost,
	options: { timeoutMs: number; protectedPids: number[] },
): Promise<QuiescenceReport> {
	const deadline = Promise.withResolvers<"timeout">();
	const timer = setTimeout(() => deadline.resolve("timeout"), options.timeoutMs);
	// A rejected abort or waitForIdle means the session did not settle; it must
	// not be reported as a clean quiescence.
	const settle = (async () => {
		await host.abort();
		await host.waitForIdle();
		return "idle" as const;
	})().catch(() => "failed" as const);
	const winner = await Promise.race([settle, deadline.promise]);
	clearTimeout(timer);
	const inflight = inFlightByHost.get(host);
	const admission = inflight?.admission;
	if (winner !== "idle") {
		admission?.halt("quiescence");
		if (inflight && admission && !inflight.settled) {
			finishInFlight(
				host,
				buildSettle(host, admission, {
					sessionId: inflight.sessionId,
					protectedPids: options.protectedPids,
					startedAt: inflight.startedAt,
					ready: false,
				}),
			);
		}
		return {
			ready: false,
			protected_pids: options.protectedPids,
			continuation_possible: false,
		};
	}
	if (admission && !admission.ended) admission.ended = "timeout";
	admission?.close();
	admission?.recordSettledMessages(host.messages());
	return {
		ready: true,
		protected_pids: options.protectedPids,
		continuation_possible: !admission?.halted,
	};
}
