import { describe, expect, it } from "bun:test";
import {
	encodeFrame,
	MAX_FRAME_BYTES,
	parseCommand,
} from "../../containers/harbor-launcher/yacht_harbor_agents/omp_protocol.ts";
import { AdmissionController } from "../../containers/harbor-launcher/yacht_harbor_agents/omp_admission.ts";
import {
	attachAdmissionGate,
	runControlledPrompt,
} from "../../containers/harbor-launcher/yacht_harbor_agents/omp_session.ts";
import { createInjectedAgent } from "./helpers.ts";

describe("driver protocol framing", () => {
	it("parses init/prompt/abort/state/shutdown commands with ids", () => {
		expect(parseCommand(JSON.stringify({ id: "1", type: "init", model: "mock/mock-model:medium", deadline_ms: 9 }))).toEqual({
			id: "1",
			type: "init",
			model: "mock/mock-model:medium",
			deadline_ms: 9,
		});
		expect(
			parseCommand(
				JSON.stringify({
					id: "2",
					type: "prompt",
					turn_id: "Q",
					message: "hi",
					max_turns: 30,
					timeout_seconds: 600,
				}),
			),
		).toEqual({
			id: "2",
			type: "prompt",
			turn_id: "Q",
			message: "hi",
			max_turns: 30,
			timeout_seconds: 600,
		});
		expect(parseCommand(JSON.stringify({ id: "3", type: "abort" }))).toEqual({ id: "3", type: "abort" });
		expect(parseCommand(JSON.stringify({ id: "4", type: "state" }))).toEqual({ id: "4", type: "state" });
		expect(parseCommand(JSON.stringify({ id: "5", type: "shutdown" }))).toEqual({ id: "5", type: "shutdown" });
	});

	it("rejects init payloads that smuggle future turns", () => {
		expect(() =>
			parseCommand(
				JSON.stringify({
					id: "1",
					type: "init",
					model: "mock/mock-model",
					deadline_ms: 1,
					turns: [{ id: "future", instruction: "secret" }],
				}),
			),
		).toThrow(/future/i);
	});

	it("encodes event, context, and response frames without a separate ready type", () => {
		const eventLine = encodeFrame({ type: "event", event: { type: "agent_start" } });
		const contextLine = encodeFrame({
			type: "context",
			turn_id: "Q",
			loop: 1,
			context: { systemPrompt: ["sys"], messages: [] },
		});
		const responseLine = encodeFrame({
			type: "response",
			id: "1",
			success: true,
			data: {
				ready: true,
				session_id: "sess",
				model: "mock/mock-model:medium",
				protected_pids: [1],
				policy: { "compaction.enabled": false },
			},
		});
		expect(JSON.parse(eventLine).type).toBe("event");
		expect(JSON.parse(contextLine)).toEqual({
			type: "context",
			turn_id: "Q",
			loop: 1,
			context: { systemPrompt: ["sys"], messages: [] },
		});
		expect(JSON.parse(responseLine).type).toBe("response");
		expect(JSON.parse(responseLine).success).toBe(true);
		expect(eventLine.includes("\n")).toBe(false);
	});

	it("never silently truncates an oversized stdout frame", () => {
		const huge = "x".repeat(MAX_FRAME_BYTES + 1);
		expect(() => encodeFrame({ type: "event", event: { type: "message_end", blob: huge } })).toThrow(/size|frame/i);
	});

	it("prompt settle includes ending, counters, continuation, quiescence, and timestamps", async () => {
		const { host } = createInjectedAgent({ responses: [{ content: ["ok"] }] });
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);
		const settle = await runControlledPrompt(host, admission, {
			turnId: "Q",
			message: "hi",
			maxTurns: 1,
			sessionId: "sess-9",
			protectedPids: [11],
		});
		expect(settle.ended).toBe("natural");
		expect(settle.loops_started).toBe(1);
		expect(settle.loops_completed).toBe(1);
		expect(settle.continuation_possible).toBe(true);
		expect(settle.session_id).toBe("sess-9");
		expect(Date.parse(settle.started_at)).toBeGreaterThan(0);
		expect(Date.parse(settle.ended_at)).toBeGreaterThanOrEqual(Date.parse(settle.started_at));
		expect(settle.quiescence).toEqual({ ready: true, protected_pids: [11] });
		const line = encodeFrame({ type: "response", id: "2", success: true, data: settle });
		expect(JSON.parse(line).data.ended).toBe("natural");
	});

	it("rejects overlapping prompts on the same session", async () => {
		const started = Promise.withResolvers<void>();
		const { host } = createInjectedAgent({
			responses: [
				async () => {
					started.resolve();
					await Promise.withResolvers<void>().promise;
					return { content: ["late"] };
				},
			],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);
		const first = runControlledPrompt(host, admission, {
			turnId: "a",
			message: "one",
			maxTurns: 2,
			sessionId: "sess-1",
		});
		await started.promise;
		await expect(
			runControlledPrompt(host, admission, {
				turnId: "b",
				message: "two",
				maxTurns: 2,
				sessionId: "sess-1",
			}),
		).rejects.toThrow(/overlap|busy/i);
		host.abort();
		await first.catch(() => undefined);
	});
});
