import { describe, expect, it } from "bun:test";
import type { StreamFn } from "@oh-my-pi/pi-agent-core";
import { AdmissionController } from "../../containers/harbor-launcher/yacht_harbor_agents/omp_admission.ts";
import {
	attachAdmissionGate,
	runControlledPrompt,
} from "../../containers/harbor-launcher/yacht_harbor_agents/omp_session.ts";
import { createInjectedAgent, echoTool } from "./helpers.ts";

describe("OMP admission gate against real agent-core", () => {
	it("cap 1 natural text admits one model call and does not start loop 2", async () => {
		const { mock, host } = createInjectedAgent({
			responses: [{ content: ["final answer"], usage: { input: 11, output: 7, totalTokens: 18 } }],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);

		const settle = await runControlledPrompt(host, admission, {
			turnId: "initial",
			message: "hello",
			maxTurns: 1,
			sessionId: "sess-1",
		});

		expect(mock.calls).toHaveLength(1);
		expect(settle.ended).toBe("natural");
		expect(settle.loops_started).toBe(1);
		expect(settle.loops_completed).toBe(1);
		expect(settle.continuation_possible).toBe(true);
		expect(settle.usage).toEqual(expect.objectContaining({ input: 11, output: 7, totalTokens: 18 }));
	});

	it("cap 1 tool response runs the tool batch as one loop and stops before N+1", async () => {
		const executed: string[] = [];
		const { mock, host } = createInjectedAgent({
			tools: [echoTool(executed)],
			responses: [
				{ content: [{ type: "toolCall", id: "tool-1", name: "echo", arguments: { value: "first" } }] },
				{ content: ["should not be reached"] },
			],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);

		const settle = await runControlledPrompt(host, admission, {
			turnId: "Q",
			message: "use the tool",
			maxTurns: 1,
			sessionId: "sess-1",
		});

		expect(executed).toEqual(["first"]);
		expect(mock.calls).toHaveLength(1);
		expect(settle.ended).toBe("cap");
		expect(settle.loops_started).toBe(1);
		expect(settle.continuation_possible).toBe(true);
	});

	it("multiple tools in one response consume a single loop", async () => {
		const executed: string[] = [];
		const { mock, host } = createInjectedAgent({
			tools: [echoTool(executed)],
			responses: [
				{
					content: [
						{ type: "toolCall", id: "tool-1", name: "echo", arguments: { value: "a" } },
						{ type: "toolCall", id: "tool-2", name: "echo", arguments: { value: "b" } },
					],
				},
				{ content: ["should not be reached"] },
			],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);

		const settle = await runControlledPrompt(host, admission, {
			turnId: "Q",
			message: "parallel tools",
			maxTurns: 1,
			sessionId: "sess-1",
		});

		expect(executed).toEqual(["a", "b"]);
		expect(mock.calls).toHaveLength(1);
		expect(settle.loops_started).toBe(1);
		expect(settle.ended).toBe("cap");
	});

	it("cap 2 looping tools admits two model calls and refuses the third", async () => {
		const executed: string[] = [];
		const { mock, host } = createInjectedAgent({
			tools: [echoTool(executed)],
			responses: [
				{ content: [{ type: "toolCall", id: "t1", name: "echo", arguments: { value: "one" } }] },
				{ content: [{ type: "toolCall", id: "t2", name: "echo", arguments: { value: "two" } }] },
				{ content: ["should not be reached"] },
			],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);

		const settle = await runControlledPrompt(host, admission, {
			turnId: "loop",
			message: "keep going",
			maxTurns: 2,
			sessionId: "sess-1",
		});

		expect(executed).toEqual(["one", "two"]);
		expect(mock.calls).toHaveLength(2);
		expect(settle.ended).toBe("cap");
		expect(settle.loops_started).toBe(2);
		expect(settle.loops_completed).toBe(2);
	});

	it("natural last text on the last permitted call stays natural", async () => {
		const executed: string[] = [];
		const { mock, host } = createInjectedAgent({
			tools: [echoTool(executed)],
			responses: [
				{ content: [{ type: "toolCall", id: "t1", name: "echo", arguments: { value: "prep" } }] },
				{ content: ["done after tools"] },
			],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);

		const settle = await runControlledPrompt(host, admission, {
			turnId: "final",
			message: "finish",
			maxTurns: 2,
			sessionId: "sess-1",
		});

		expect(executed).toEqual(["prep"]);
		expect(mock.calls).toHaveLength(2);
		expect(settle.ended).toBe("natural");
		expect(settle.loops_started).toBe(2);
	});

	it("provider-internal HTTP retries inside one streamFn are not extra admissions", async () => {
		const inner = createInjectedAgent({ responses: [{ content: ["ok"] }] });
		let httpAttempts = 0;
		const retrying: StreamFn = (model, context, options) => {
			httpAttempts += 2;
			return inner.mock.stream(model, context, options);
		};
		const { agent, host } = createInjectedAgent({
			responses: [{ content: ["unused"] }],
			streamFn: retrying,
		});
		agent.state.model = inner.mock.model;
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);

		const settle = await runControlledPrompt(host, admission, {
			turnId: "retry",
			message: "once",
			maxTurns: 3,
			sessionId: "sess-1",
		});

		expect(inner.mock.calls).toHaveLength(1);
		expect(httpAttempts).toBe(2);
		expect(settle.loops_started).toBe(1);
		expect(settle.ended).toBe("natural");
	});

	it("a closed gate admits no model work", async () => {
		const { mock, host } = createInjectedAgent({
			responses: [{ content: ["should not run"] }],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);
		admission.close();

		const settle = await runControlledPrompt(host, admission, {
			turnId: "closed",
			message: "nope",
			maxTurns: 4,
			sessionId: "sess-1",
		});

		expect(mock.calls).toHaveLength(0);
		expect(settle.loops_started).toBe(0);
		expect(settle.ended).toBe("error");
		expect(settle.continuation_possible).toBe(true);
	});

	it("deadline refuses the next admission without starting that provider call", async () => {
		let nowMs = 1_000;
		const executed: string[] = [];
		const { mock, host } = createInjectedAgent({
			tools: [echoTool(executed)],
			responses: [
				{ content: [{ type: "toolCall", id: "t1", name: "echo", arguments: { value: "slow" } }] },
				{ content: ["too late"] },
			],
		});
		const original = executed.push.bind(executed);
		executed.push = (value: string) => {
			nowMs = 3_000;
			return original(value);
		};
		const admission = new AdmissionController({ now: () => nowMs });
		attachAdmissionGate(host, admission);

		const settle = await runControlledPrompt(host, admission, {
			turnId: "deadline",
			message: "hurry",
			maxTurns: 5,
			timeoutSeconds: 1,
			sessionId: "sess-1",
		});

		expect(executed).toEqual(["slow"]);
		expect(mock.calls).toHaveLength(1);
		expect(settle.ended).toBe("timeout");
		expect(settle.loops_started).toBe(1);
		expect(settle.continuation_possible).toBe(true);
	});

	it("resets only the per-message counter and keeps cumulative admissions", async () => {
		const { mock, host } = createInjectedAgent({
			responses: [
				{ content: ["first"], usage: { input: 10, output: 1, totalTokens: 11 } },
				{ content: ["second"], usage: { input: 20, output: 2, totalTokens: 22 } },
			],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);

		const first = await runControlledPrompt(host, admission, {
			turnId: "m1",
			message: "one",
			maxTurns: 1,
			sessionId: "sess-1",
		});
		expect(admission.closed).toBe(true);
		const second = await runControlledPrompt(host, admission, {
			turnId: "m2",
			message: "two",
			maxTurns: 1,
			sessionId: "sess-1",
		});
		expect(admission.closed).toBe(true);

		expect(first.loops_started).toBe(1);
		expect(second.loops_started).toBe(1);
		expect(admission.cumulativeLoopsStarted).toBe(2);
		expect(mock.calls).toHaveLength(2);
		expect(first.ended).toBe("natural");
		expect(second.ended).toBe("natural");
		expect(first.usage).toEqual(expect.objectContaining({ input: 10, totalTokens: 11 }));
		expect(second.usage).toEqual(expect.objectContaining({ input: 20, totalTokens: 22 }));
	});

	it("classifies a provider stream failure as error not natural", async () => {
		const { host } = createInjectedAgent({
			responses: [{ throw: "provider returned 500" }],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);
		const settle = await runControlledPrompt(host, admission, {
			turnId: "fail",
			message: "go",
			maxTurns: 2,
			sessionId: "sess-1",
		});
		expect(settle.ended).toBe("error");
		expect(settle.usage).toBeNull();
	});
});
