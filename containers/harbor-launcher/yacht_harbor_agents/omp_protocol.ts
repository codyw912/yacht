export const MAX_FRAME_BYTES = 16 * 1024 * 1024;

export type AdvisorSpec = {
	model: string;
	tools?: string[];
	instructions?: string;
};

export type DriverCommand =
	| {
			id: string;
			type: "init";
			model: string;
			deadline_ms: number;
			advisor?: AdvisorSpec;
	  }
	| {
			id: string;
			type: "prompt";
			turn_id: string;
			message: string;
			max_turns: number;
			timeout_seconds: number;
	  }
	| { id: string; type: "abort" }
	| { id: string; type: "state" }
	| { id: string; type: "shutdown" };

export type DriverFrame =
	| { type: "event"; event: unknown }
	| { type: "context"; turn_id: string; loop: number; context: unknown }
	| { type: "response"; id: string; success: boolean; data: unknown };

function requireString(value: unknown, field: string): string {
	if (typeof value !== "string" || value.length === 0) {
		throw new Error(`invalid ${field}`);
	}
	return value;
}

function requireNumber(value: unknown, field: string): number {
	if (typeof value !== "number" || !Number.isFinite(value)) {
		throw new Error(`invalid ${field}`);
	}
	return value;
}

function parseAdvisorSpec(value: unknown): AdvisorSpec | undefined {
	if (value === undefined || value === null) return undefined;
	if (typeof value !== "object" || Array.isArray(value)) {
		throw new Error("invalid advisor");
	}
	const spec = value as Record<string, unknown>;
	const model = requireString(spec.model, "advisor.model");
	const advisor: AdvisorSpec = { model };
	if (spec.tools !== undefined) {
		if (
			!Array.isArray(spec.tools) ||
			!spec.tools.every((item) => typeof item === "string" && item.length > 0)
		) {
			throw new Error("invalid advisor.tools");
		}
		advisor.tools = spec.tools as string[];
	}
	if (spec.instructions !== undefined) {
		if (typeof spec.instructions !== "string") {
			throw new Error("invalid advisor.instructions");
		}
		advisor.instructions = spec.instructions;
	}
	return advisor;
}


export function parseCommand(line: string): DriverCommand {
	let parsed: unknown;
	try {
		parsed = JSON.parse(line);
	} catch {
		throw new Error("invalid command json");
	}
	if (!parsed || typeof parsed !== "object") {
		throw new Error("invalid command");
	}
	const obj = parsed as Record<string, unknown>;
	const id = requireString(obj.id, "id");
	const type = requireString(obj.type, "type");
	switch (type) {
		case "init": {
			if ("turns" in obj || "captures" in obj || "instruction" in obj) {
				throw new Error("init must not include future turns");
			}
			return {
				id,
				type: "init",
				model: requireString(obj.model, "model"),
				deadline_ms: requireNumber(obj.deadline_ms, "deadline_ms"),
				// Spread conditionally so the no-advisor init stays byte-identical
				// (advisor key absent, not present-as-undefined) for strict
				// equality and JSON round-trips downstream.
				...(obj.advisor !== undefined ? { advisor: parseAdvisorSpec(obj.advisor) } : {}),
			};
		}
		case "prompt":
			return {
				id,
				type: "prompt",
				turn_id: requireString(obj.turn_id, "turn_id"),
				message: requireString(obj.message, "message"),
				max_turns: requireNumber(obj.max_turns, "max_turns"),
				timeout_seconds: requireNumber(obj.timeout_seconds, "timeout_seconds"),
			};
		case "abort":
		case "state":
		case "shutdown":
			return { id, type };
		default:
			throw new Error(`unknown command ${type}`);
	}
}

export function encodeFrame(frame: DriverFrame): string {
	const line = JSON.stringify(frame);
	const bytes = Buffer.byteLength(line, "utf8");
	if (bytes > MAX_FRAME_BYTES) {
		throw new Error(`frame size ${bytes} exceeds ${MAX_FRAME_BYTES}`);
	}
	return line;
}
