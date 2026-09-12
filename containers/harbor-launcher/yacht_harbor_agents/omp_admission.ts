import { toolWireSchema } from "@oh-my-pi/pi-ai/utils/schema";

export type Ended = "natural" | "cap" | "timeout" | "error";
export type InvalidReason = "compaction" | "truncation" | "model_switch" | "quiescence" | "event_frame";

export type VisibleTurn = {
	role: "user" | "assistant";
	text: string;
};

export type VisiblePrefix = {
	turns: VisibleTurn[];
	modelId?: string;
	userTexts: string[];
	assistantTexts: string[];
};

export type SerializedTool = {
	name: string;
	description?: string;
	parameters?: unknown;
};

export type GatedContext = {
	turnId: string;
	loop: number;
	context: { systemPrompt?: string[]; messages?: unknown[]; tools?: SerializedTool[] };
};

/**
 * A JSON-safe view of the provider-bound context. Live tool objects carry
 * schema functions, so each tool is projected to the same wire JSON Schema the
 * providers send; messages are round-tripped so the snapshot cannot alias live
 * history.
 */
export function serializableContext(context: {
	systemPrompt?: string[];
	messages?: unknown[];
	tools?: unknown[];
}): GatedContext["context"] {
	const tools: SerializedTool[] = [];
	for (const raw of context.tools ?? []) {
		if (!raw || typeof raw !== "object" || !("name" in raw) || typeof raw.name !== "string") continue;
		const tool = raw as { name: string; description?: string };
		let parameters: unknown;
		try {
			parameters = toolWireSchema(raw as Parameters<typeof toolWireSchema>[0]);
		} catch {
			parameters = undefined;
		}
		tools.push({ name: tool.name, description: tool.description, parameters });
	}
	return {
		systemPrompt: context.systemPrompt ? [...context.systemPrompt] : undefined,
		messages: JSON.parse(JSON.stringify(context.messages ?? [])) as unknown[],
		tools,
	};
}

type ContentBlock = { type?: string; text?: string };

function textBlocks(content: unknown): string[] {
	if (typeof content === "string") return content ? [content] : [];
	if (!Array.isArray(content)) return [];
	const texts: string[] = [];
	for (const block of content as ContentBlock[]) {
		if (block && block.type === "text" && typeof block.text === "string") texts.push(block.text);
	}
	return texts;
}

function messageRole(message: { role?: string }): string | undefined {
	return message.role;
}

export function visiblePrefixFromContext(context: { messages?: unknown[] }): VisiblePrefix {
	return visiblePrefixFromMessages(context.messages ?? []);
}

export function visiblePrefixFromMessages(messages: readonly unknown[]): VisiblePrefix {
	const turns: VisibleTurn[] = [];
	let modelId: string | undefined;
	for (const raw of messages) {
		if (!raw || typeof raw !== "object") continue;
		const message = raw as { role?: string; content?: unknown; model?: string };
		if (message.role === "user") {
			for (const text of textBlocks(message.content)) turns.push({ role: "user", text });
		} else if (message.role === "assistant") {
			for (const text of textBlocks(message.content)) turns.push({ role: "assistant", text });
			if (typeof message.model === "string" && message.model) modelId = message.model;
		}
	}
	return {
		turns,
		modelId,
		userTexts: turns.filter((turn) => turn.role === "user").map((turn) => turn.text),
		assistantTexts: turns.filter((turn) => turn.role === "assistant").map((turn) => turn.text),
	};
}

/**
 * Every retained turn must still be present in the same relative order. The
 * SDK legitimately injects its own provider-context entries (date/cwd
 * reminders, wrappers), so extra turns are permitted; a dropped or reordered
 * retained turn is not.
 */
function retainsOrderedTurns(previous: VisibleTurn[], current: VisibleTurn[]): boolean {
	let cursor = 0;
	for (const turn of previous) {
		let found = -1;
		for (let i = cursor; i < current.length; i++) {
			if (current[i]!.role === turn.role && current[i]!.text === turn.text) {
				found = i;
				break;
			}
		}
		if (found === -1) return false;
		cursor = found + 1;
	}
	return true;
}

export function auditVisibleHistory(
	previous: VisiblePrefix,
	current: { messages?: unknown[] },
	options?: { modelId?: string },
): { ok: true } | { ok: false; reason: "compaction" | "truncation" | "model_switch" } {
	const now = visiblePrefixFromMessages(current.messages ?? []);
	const modelId = options?.modelId ?? now.modelId;
	if (previous.modelId && modelId && previous.modelId !== modelId) {
		return { ok: false, reason: "model_switch" };
	}
	if (retainsOrderedTurns(previous.turns, now.turns)) return { ok: true };
	// A retained turn is gone. Novel text alongside the loss means history was
	// rewritten (summary spliced in); a pure loss is truncation.
	const retained: Record<string, true> = {};
	for (const turn of previous.turns) retained[`${turn.role}:${turn.text}`] = true;
	const novel = now.turns.some((turn) => !retained[`${turn.role}:${turn.text}`]);
	return { ok: false, reason: novel ? "compaction" : "truncation" };
}

export class AdmissionController {
	now: () => number;
	closed = true;
	explicitlyClosed = false;
	halted = false;
	loopsStarted = 0;
	loopsCompleted = 0;
	cumulativeLoopsStarted = 0;
	contexts: GatedContext[] = [];
	ended?: Ended;
	invalid?: { reason: InvalidReason };
	turnId = "";
	maxTurns = 0;
	deadlineMs?: number;
	lastPrefix?: VisiblePrefix;
	messageStartIndex = 0;

	constructor(options?: { now?: () => number }) {
		this.now = options?.now ?? Date.now;
	}

	beginPrompt(options: { turnId: string; maxTurns: number; timeoutSeconds?: number; messageStartIndex?: number }): void {
		if (this.halted || (this.invalid && this.invalid.reason !== "quiescence")) {
			this.closed = true;
			this.halted = true;
			this.ended = "error";
			return;
		}
		this.closed = false;
		this.explicitlyClosed = false;
		this.turnId = options.turnId;
		this.maxTurns = options.maxTurns;
		this.loopsStarted = 0;
		this.loopsCompleted = 0;
		this.ended = undefined;
		this.messageStartIndex = options.messageStartIndex ?? 0;
		const started = this.now();
		this.deadlineMs =
			options.timeoutSeconds !== undefined ? started + options.timeoutSeconds * 1000 : undefined;
	}

	close(): void {
		this.closed = true;
		this.explicitlyClosed = true;
	}

	halt(reason: InvalidReason | Ended = "error"): void {
		this.halted = true;
		this.closed = true;
		this.explicitlyClosed = true;
		if (reason === "quiescence" || reason === "event_frame") {
			this.ended = "error";
			this.invalid = { reason };
		} else if (reason === "natural" || reason === "cap" || reason === "timeout" || reason === "error") {
			this.ended = reason;
		} else {
			this.ended = "error";
			this.invalid = { reason };
		}
	}

	/**
	 * Extend the audit baseline with the replies that settled after the last
	 * admitted call. The baseline must stay in the provider projection the gate
	 * actually compares: session state carries entries (reminders, custom
	 * messages, non-replay records) that never reach the provider context, so
	 * adopting raw state wholesale reports phantom compaction on the next call.
	 */
	recordSettledMessages(messages: readonly unknown[]): void {
		const admitted = this.lastPrefix;
		if (!admitted) {
			this.lastPrefix = visiblePrefixFromMessages(messages);
			return;
		}
		const settled = visiblePrefixFromMessages(messages);
		const known: Record<string, true> = {};
		for (const turn of admitted.turns) known[`${turn.role}:${turn.text}`] = true;
		const turns = [...admitted.turns];
		for (const turn of settled.turns) {
			if (turn.role !== "assistant") continue;
			if (known[`${turn.role}:${turn.text}`]) continue;
			turns.push(turn);
		}
		this.lastPrefix = {
			turns,
			modelId: settled.modelId ?? admitted.modelId,
			userTexts: turns.filter((turn) => turn.role === "user").map((turn) => turn.text),
			assistantTexts: turns.filter((turn) => turn.role === "assistant").map((turn) => turn.text),
		};
	}

	markLoopCompleted(): void {
		if (this.loopsCompleted < this.loopsStarted) this.loopsCompleted += 1;
	}

	beforeModelCall = (
		context: { messages?: unknown[]; systemPrompt?: string[] },
		signal?: AbortSignal,
	): { stop: true; reason?: string } | undefined => {
		if (this.halted || this.closed) {
			if (!this.ended) this.ended = "error";
			return { stop: true, reason: this.halted ? "halted" : "closed" };
		}
		if (signal?.aborted) {
			this.ended = this.ended ?? "timeout";
			this.close();
			return { stop: true, reason: "aborted" };
		}
		if (this.deadlineMs !== undefined && this.now() >= this.deadlineMs) {
			this.ended = "timeout";
			this.close();
			return { stop: true, reason: "timeout" };
		}
		if (this.lastPrefix) {
			const audit = auditVisibleHistory(this.lastPrefix, context, {
				modelId: visiblePrefixFromContext(context).modelId,
			});
			if (!audit.ok) {
				this.invalid = { reason: audit.reason };
				this.ended = "error";
				this.halted = true;
				this.close();
				return { stop: true, reason: audit.reason };
			}
		}
		if (this.loopsStarted >= this.maxTurns) {
			this.ended = "cap";
			this.close();
			return { stop: true, reason: "cap" };
		}
		this.loopsStarted += 1;
		this.cumulativeLoopsStarted += 1;
		const snapshot = serializableContext(context);
		this.contexts.push({ turnId: this.turnId, loop: this.loopsStarted, context: snapshot });
		this.lastPrefix = visiblePrefixFromMessages(snapshot.messages ?? []);
		return undefined;
	};
}
