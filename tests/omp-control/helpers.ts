import { type } from "@oh-my-pi/omptype";
import { Agent, type AgentTool, type StreamFn } from "@oh-my-pi/pi-agent-core";
import { createMockModel, type MockResponseSource } from "@oh-my-pi/pi-ai/providers/mock";
import type { ControlledHost, HostMessage } from "../../containers/harbor-launcher/yacht_harbor_agents/omp_session.ts";
const echoSchema = type({ value: "string" });
const hangSchema = type({ label: "string" });

export function echoTool(executed: string[]): AgentTool<typeof echoSchema, { value: string }> {
	return {
		name: "echo",
		label: "Echo",
		description: "Echo tool",
		parameters: echoSchema,
		concurrency: "exclusive",
		intent: "omit",
		async execute(_toolCallId, params) {
			executed.push(params.value);
			return {
				content: [{ type: "text", text: `ok:${params.value}` }],
				details: { value: params.value },
			};
		},
	};
}

export function hangTool(onStart: () => void): AgentTool<typeof hangSchema, { label: string }> {
	return {
		name: "hang",
		label: "Hang",
		description: "Cooperative hanging tool",
		parameters: hangSchema,
		concurrency: "exclusive",
		intent: "omit",
		async execute(_toolCallId, params, signal) {
			onStart();
			const { promise, reject } = Promise.withResolvers<void>();
			if (signal?.aborted) {
				reject(new Error(`aborted:${params.label}`));
			} else {
				signal?.addEventListener("abort", () => reject(new Error(`aborted:${params.label}`)), { once: true });
			}
			await promise;
			return {
				content: [{ type: "text", text: "never" }],
				details: { label: params.label },
			};
		},
	};
}

export function asHost(agent: Agent): ControlledHost {
	const host: ControlledHost = {
		prompt: (message) => agent.prompt(message),
		abort: () => agent.abort(),
		waitForIdle: () => agent.waitForIdle(),
		addBeforeModelCall: (fn) => agent.addBeforeModelCall(fn as never),
		busy: () => agent.state.isStreaming,
		messages: () => agent.state.messages as HostMessage[],
		subscribe: (fn) => agent.subscribe(fn as never),
	};
	Object.defineProperty(host, "beforeToolCall", {
		get: () => (agent as { beforeToolCall?: ControlledHost["beforeToolCall"] }).beforeToolCall,
		set: (fn: ControlledHost["beforeToolCall"]) => {
			(agent as { beforeToolCall?: ControlledHost["beforeToolCall"] }).beforeToolCall = fn;
		},
		enumerable: true,
		configurable: true,
	});
	return host;
}

export function createInjectedAgent(options: {
	responses: MockResponseSource;
	tools?: AgentTool[];
	systemPrompt?: string;
	streamFn?: StreamFn;
}) {
	const mock = createMockModel({ responses: options.responses });
	const agent = new Agent({
		streamFn: options.streamFn ?? mock.stream,
		initialState: {
			model: mock.model,
			systemPrompt: [options.systemPrompt ?? "yacht-eval"],
			tools: options.tools ?? [],
			messages: [],
		},
	});
	return { agent, mock, host: asHost(agent) };
}

export function userTexts(agent: Agent): string[] {
	return agent.state.messages.flatMap((message) => {
		if (message.role !== "user") return [];
		if (typeof message.content === "string") return [message.content];
		if (!Array.isArray(message.content)) return [];
		return message.content
			.filter((block): block is { type: "text"; text: string } => block.type === "text")
			.map((block) => block.text);
	});
}

export function assistantTexts(agent: Agent): string[] {
	return agent.state.messages.flatMap((message) => {
		if (message.role !== "assistant") return [];
		if (!Array.isArray(message.content)) return [];
		return message.content
			.filter((block): block is { type: "text"; text: string } => block.type === "text")
			.map((block) => block.text);
	});
}
