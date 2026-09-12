import { describe, expect, it } from "bun:test";
import type { Context } from "@oh-my-pi/pi-ai";
import {
	AdmissionController,
	auditVisibleHistory,
	visiblePrefixFromContext,
} from "../../containers/harbor-launcher/yacht_harbor_agents/omp_admission.ts";
import {
	attachAdmissionGate,
	runControlledPrompt,
} from "../../containers/harbor-launcher/yacht_harbor_agents/omp_session.ts";
import { assistantTexts, createInjectedAgent, echoTool, userTexts } from "./helpers.ts";

function userMessage(text: string) {
	return { role: "user" as const, content: text, timestamp: 1 };
}

function assistantMessage(text: string, model = "mock-model") {
	return {
		role: "assistant" as const,
		content: [{ type: "text" as const, text }],
		api: "mock",
		provider: "mock",
		model,
		usage: {
			input: 0,
			output: 0,
			cacheRead: 0,
			cacheWrite: 0,
			totalTokens: 0,
			cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
		},
		stopReason: "stop" as const,
		timestamp: 1,
	};
}

function thinkingAssistant(thinking: string, text: string, model = "mock-model") {
	return {
		...assistantMessage(text, model),
		content: [
			{ type: "thinking" as const, thinking },
			{ type: "text" as const, text },
		],
	};
}

describe("visible history retention", () => {
	it("keeps the same in-memory session after a recoverable cap", async () => {
		const { agent, mock, host } = createInjectedAgent({
			responses: [{ content: ["remember alpha"] }, { content: ["still here"] }],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);

		const first = await runControlledPrompt(host, admission, {
			turnId: "m1",
			message: "secret token ORANGE-42",
			maxTurns: 1,
			sessionId: "sess-retain",
		});
		expect(first.ended).toBe("natural");
		expect(first.continuation_possible).toBe(true);
		expect(assistantTexts(agent).join("\n")).toContain("remember alpha");

		const second = await runControlledPrompt(host, admission, {
			turnId: "m2",
			message: "what was the token?",
			maxTurns: 1,
			sessionId: "sess-retain",
		});

		expect(second.ended).toBe("natural");
		expect(mock.calls).toHaveLength(2);
		expect(userTexts(agent)).toEqual(["secret token ORANGE-42", "what was the token?"]);
		const gated = admission.contexts.at(-1)?.context;
		expect(gated).toBeDefined();
		const prefix = visiblePrefixFromContext(gated as Context);
		expect(prefix.userTexts).toContain("secret token ORANGE-42");
		expect(prefix.assistantTexts.some((text) => text.includes("remember alpha"))).toBe(true);
	});

	it("emits the effective provider-visible context on each admitted call", async () => {
		const { agent, host } = createInjectedAgent({
			responses: [{ content: ["ok"] }],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);
		await runControlledPrompt(host, admission, {
			turnId: "ctx",
			message: "visible user",
			maxTurns: 1,
			sessionId: "sess-1",
		});
		expect(admission.contexts).toHaveLength(1);
		expect(admission.contexts[0]?.turnId).toBe("ctx");
		expect(admission.contexts[0]?.loop).toBe(1);
		expect(visiblePrefixFromContext(admission.contexts[0]!.context).userTexts).toContain("visible user");
		const frozen = JSON.stringify(admission.contexts[0]!.context.messages);
		agent.state.messages.push({ role: "user", content: "later mutation", timestamp: Date.now() });
		expect(JSON.stringify(admission.contexts[0]!.context.messages)).toBe(frozen);
	});

	it("records the provider-visible tool schemas in the admitted context", async () => {
		const executed: string[] = [];
		const { host } = createInjectedAgent({
			tools: [echoTool(executed)],
			responses: [{ content: ["ok"] }],
		});
		const admission = new AdmissionController();
		attachAdmissionGate(host, admission);
		await runControlledPrompt(host, admission, {
			turnId: "tools",
			message: "look",
			maxTurns: 1,
			sessionId: "sess-1",
		});
		const tools = admission.contexts[0]?.context.tools;
		expect(tools?.map((tool) => tool.name)).toEqual(["echo"]);
		expect(tools?.[0]?.description).toBe("Echo tool");
		const parameters = tools?.[0]?.parameters as { properties?: Record<string, unknown> } | undefined;
		expect(parameters?.properties).toHaveProperty("value");
		expect(JSON.parse(JSON.stringify(tools))).toEqual(tools);
	});

	it("invalidates when earlier visible user text is no longer a prefix", () => {
		const previous = visiblePrefixFromContext({
			systemPrompt: ["sys"],
			messages: [userMessage("early fact"), assistantMessage("ack")],
		});
		const truncated: Context = {
			systemPrompt: ["sys"],
			messages: [assistantMessage("ack")],
		};
		expect(auditVisibleHistory(previous, truncated, { modelId: "mock-model" })).toEqual({
			ok: false,
			reason: "truncation",
		});
	});

	it("invalidates compaction that replaces history with a summary", () => {
		const previous = visiblePrefixFromContext({
			systemPrompt: ["sys"],
			messages: [userMessage("early fact"), assistantMessage("long reply with fences\n```json\n{}\n```")],
		});
		const compacted: Context = {
			systemPrompt: ["sys"],
			messages: [userMessage("summary of earlier turns"), assistantMessage("ok")],
		};
		expect(auditVisibleHistory(previous, compacted, { modelId: "mock-model" })).toEqual({
			ok: false,
			reason: "compaction",
		});
	});

	it("invalidates a model switch across admitted calls", () => {
		const previous = visiblePrefixFromContext({
			systemPrompt: ["sys"],
			messages: [userMessage("hi"), assistantMessage("hello", "mock-model")],
		});
		const switched: Context = {
			systemPrompt: ["sys"],
			messages: [userMessage("hi"), assistantMessage("hello", "other-model")],
		};
		expect(auditVisibleHistory(previous, switched, { modelId: "other-model" })).toEqual({
			ok: false,
			reason: "model_switch",
		});
	});

	it("does not require hidden thinking text to be retained", () => {
		const previous = visiblePrefixFromContext({
			systemPrompt: ["sys"],
			messages: [userMessage("q"), thinkingAssistant("secret chain of thought", "public answer")],
		});
		const withoutThinking: Context = {
			systemPrompt: ["sys"],
			messages: [userMessage("q"), assistantMessage("public answer")],
		};
		expect(auditVisibleHistory(previous, withoutThinking, { modelId: "mock-model" })).toEqual({ ok: true });
	});
});
