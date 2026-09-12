import { describe, expect, it } from "bun:test";
import { AdmissionController } from "../../containers/harbor-launcher/yacht_harbor_agents/omp_admission.ts";
import {
	abortAndQuiesce,
	attachAdmissionGate,
	runControlledPrompt,
} from "../../containers/harbor-launcher/yacht_harbor_agents/omp_session.ts";
import { createInjectedAgent, hangTool } from "./helpers.ts";

describe("cooperative abort and quiescence", () => {
	it("aborts a hanging cooperative tool, waits for idle, and allows continuation", async () => {
		const started = Promise.withResolvers<void>();
		const { mock, host } = createInjectedAgent({
			tools: [hangTool(() => started.resolve())],
			responses: [
				{ content: [{ type: "toolCall", id: "hang-1", name: "hang", arguments: { label: "wait" } }] },
				{ content: ["after abort"] },
			],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);

		const running = runControlledPrompt(host, admission, {
			turnId: "hang",
			message: "block",
			maxTurns: 4,
			sessionId: "sess-1",
		});
		await started.promise;

		const quiesce = await abortAndQuiesce(host, { timeoutMs: 1_000, protectedPids: [42] });
		expect(quiesce.ready).toBe(true);
		expect(quiesce.protected_pids).toEqual([42]);
		expect(quiesce.continuation_possible).toBe(true);

		const settle = await running;
		expect(settle.ended).toBe("timeout");
		expect(settle.continuation_possible).toBe(true);
		expect(settle.quiescence.ready).toBe(true);
		expect(mock.calls).toHaveLength(1);

		const next = await runControlledPrompt(host, admission, {
			turnId: "after",
			message: "continue",
			maxTurns: 1,
			sessionId: "sess-1",
		});
		expect(next.ended).toBe("natural");
		expect(mock.calls).toHaveLength(2);
	});

	it("times out a hanging tool from the message wall without an external abort", async () => {
		const started = Promise.withResolvers<void>();
		const { mock, host } = createInjectedAgent({
			tools: [hangTool(() => started.resolve())],
			responses: [{ content: [{ type: "toolCall", id: "hang-1", name: "hang", arguments: { label: "wait" } }] }],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);
		const settle = await runControlledPrompt(host, admission, {
			turnId: "wall",
			message: "block",
			maxTurns: 4,
			timeoutSeconds: 0.05,
			sessionId: "sess-1",
		});
		expect(settle.ended).toBe("timeout");
		expect(mock.calls).toHaveLength(1);
		expect(settle.continuation_possible).toBe(true);
	});

	it("failed quiescence kills the logical session and reports continuation_possible false", async () => {
		const started = Promise.withResolvers<void>();
		const { host } = createInjectedAgent({
			tools: [
				{
					name: "hang",
					label: "Hang",
					description: "Ignores abort",
					parameters: hangTool(() => undefined).parameters,
					concurrency: "exclusive",
					intent: "omit",
					async execute() {
						started.resolve();
						await Promise.withResolvers<void>().promise;
						return { content: [{ type: "text", text: "never" }], details: {} };
					},
				},
			],
			responses: [{ content: [{ type: "toolCall", id: "hang-1", name: "hang", arguments: { label: "ignore" } }] }],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);
		const running = runControlledPrompt(host, admission, {
			turnId: "stuck",
			message: "block",
			maxTurns: 2,
			sessionId: "sess-1",
		});
		await started.promise;

		const quiesce = await abortAndQuiesce(host, { timeoutMs: 20, protectedPids: [] });
		expect(quiesce.ready).toBe(false);
		expect(quiesce.continuation_possible).toBe(false);

		const settle = await running;
		expect(settle.continuation_possible).toBe(false);
		expect(settle.ended).toBe("error");
		expect(settle.invalid?.reason).toBe("quiescence");
		expect(settle.loops_completed).toBe(0);
		expect(admission.closed).toBe(true);
	});

	it("does not claim abort kills arbitrary non-cooperative descendants", async () => {
		const { host } = createInjectedAgent({
			responses: [{ content: ["idle"] }],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);
		await runControlledPrompt(host, admission, {
			turnId: "idle",
			message: "hi",
			maxTurns: 1,
			sessionId: "sess-1",
		});
		const quiesce = await abortAndQuiesce(host, { timeoutMs: 200, protectedPids: [7, 9] });
		expect(quiesce.ready).toBe(true);
		expect(quiesce.protected_pids).toEqual([7, 9]);
		expect(quiesce.reaped_descendants).toBeUndefined();
	});

	it("reports failed quiescence when waitForIdle rejects", async () => {
		const { host } = createInjectedAgent({ responses: [{ content: ["ok"] }] });
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);
		host.waitForIdle = () => Promise.reject(new Error("idle bookkeeping failed"));
		const quiesce = await abortAndQuiesce(host, { timeoutMs: 1_000, protectedPids: [3] });
		expect(quiesce.ready).toBe(false);
		expect(quiesce.continuation_possible).toBe(false);
	});

	it("reports failed quiescence when abort rejects", async () => {
		const { host } = createInjectedAgent({ responses: [{ content: ["ok"] }] });
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);
		host.abort = () => Promise.reject(new Error("abort refused"));
		const quiesce = await abortAndQuiesce(host, { timeoutMs: 1_000, protectedPids: [] });
		expect(quiesce.ready).toBe(false);
		expect(quiesce.continuation_possible).toBe(false);
	});

	it("does not label a rejected in-flight prompt as a timeout", async () => {
		const { host } = createInjectedAgent({ responses: [{ content: ["never"] }] });
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);
		host.prompt = () => Promise.reject(new Error("No API key found for mock"));
		const settle = await runControlledPrompt(host, admission, {
			turnId: "noauth",
			message: "go",
			maxTurns: 2,
			timeoutSeconds: 600,
			sessionId: "sess-1",
		});
		expect(settle.ended).toBe("error");
		expect(settle.error).toContain("No API key");
		expect(settle.loops_started).toBe(0);
	});
});
