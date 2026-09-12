export const CONTROLLED_SETTINGS = {
	"compaction.enabled": false,
	"compaction.autoContinue": false,
	"compaction.midTurnEnabled": false,
	"compaction.asyncEnabled": false,
	"compaction.experimentalContextManagement": false,
	"retry.enabled": false,
	"retry.modelFallback": false,
	"retry.usageAwareFallback": false,
	"advisor.enabled": false,
	"autolearn.enabled": false,
	"autolearn.autoContinue": false,
	"memory.backend": "off",
	"bash.autoBackground.enabled": false,
	"eval.autoBackground.enabled": false,
	"async.enabled": false,
	"launch.enabled": false,
	"goal.enabled": false,
	"title.refreshOnReplan": false,
} as const;

export const CONTROLLED_ENV = {
	PI_NO_TITLE: "1",
} as const;

export const REQUIRED_NATIVE_TOOLS = ["bash", "read", "write", "edit", "grep"] as const;

/**
 * Tools whose execution can start model work outside the admission gate.
 * `task` spawns a subagent session, `eval` reaches
 * `instrumentedCompleteSimple` through its completion bridge, and `browser`
 * drives vision-capable side requests.
 */
export const MODEL_SPAWNING_TOOLS = ["task", "eval", "browser"] as const;

/**
 * Settings that must hold for the native roster to stay free of side
 * inference. `memory.backend` off keeps recall/retain/reflect/memory_edit out
 * of the roster (each reaches `completeSimple` in the memory backends), and
 * `autolearn.enabled` false keeps `learn`/`manage_skill` out. Asserted at init
 * so a future settings change cannot silently re-open these paths.
 */
export const SIDE_INFERENCE_GUARDS = {
	"memory.backend": "off",
	"autolearn.enabled": false,
	"launch.enabled": false,
} as const;

export const RESTRICT_TOOL_NAMES = false;

export const QUESTION_READ_BLOCK = "image-question inference is disabled for controlled execution";

const THINKING_LEVELS: Record<string, true> = {
	minimal: true,
	low: true,
	medium: true,
	high: true,
	xhigh: true,
	max: true,
};

export type ExactModelSelector = {
	provider: string;
	id: string;
	thinkingLevel?: string;
};

export function parseExactModelSelector(selector: string): ExactModelSelector {
	if (!selector || !selector.includes("/")) {
		throw new Error("invalid model selector");
	}
	const slash = selector.indexOf("/");
	const provider = selector.slice(0, slash);
	let id = selector.slice(slash + 1);
	if (!provider || !id) {
		throw new Error("invalid model selector");
	}
	let thinkingLevel: string | undefined;
	const colon = id.lastIndexOf(":");
	if (colon > 0) {
		const suffix = id.slice(colon + 1);
		if (THINKING_LEVELS[suffix]) {
			thinkingLevel = suffix;
			id = id.slice(0, colon);
		}
	}
	if (!id) {
		throw new Error("invalid model selector");
	}
	return thinkingLevel ? { provider, id, thinkingLevel } : { provider, id };
}

export function assertNoModelSpawningTools(names: readonly string[]): void {
	for (const name of names) {
		if ((MODEL_SPAWNING_TOOLS as readonly string[]).includes(name)) {
			throw new Error(`unsupported model-spawning tool: ${name}`);
		}
	}
}

export function controlledToolRoster(enabled: readonly string[], mounted: readonly string[]): string[] {
	const spawning: Record<string, true> = {};
	for (const name of MODEL_SPAWNING_TOOLS) spawning[name] = true;
	const roster: string[] = [];
	const seen: Record<string, true> = {};
	for (const name of [...enabled, ...mounted]) {
		if (spawning[name] || seen[name]) continue;
		seen[name] = true;
		roster.push(name);
	}
	return roster;
}

export function assertRequiredNativeTools(roster: readonly string[]): void {
	for (const required of REQUIRED_NATIVE_TOOLS) {
		if (!roster.includes(required)) {
			throw new Error(`required native tool missing: ${required}`);
		}
	}
}

/**
 * Refuse to run when a guard setting drifted, rather than measuring a session
 * whose roster can start unbudgeted model work.
 */
export function assertSideInferenceGuards(effective: (path: string) => unknown): void {
	for (const [path, expected] of Object.entries(SIDE_INFERENCE_GUARDS)) {
		const actual = effective(path);
		if (actual !== expected) {
			throw new Error(`side-inference guard ${path} must be ${String(expected)}, got ${String(actual)}`);
		}
	}
}

export function isQuestionRead(toolName: string, args: Record<string, unknown>): boolean {
	if (toolName !== "read") return false;
	if (args.q != null && args.q !== "") return true;
	const path = args.path;
	if (typeof path !== "string") return false;
	if (path.includes("://") && !path.startsWith("attachment://") && !path.startsWith("local://")) return false;
	const queryIndex = path.indexOf("?");
	return queryIndex !== -1 && Boolean(new URLSearchParams(path.slice(queryIndex + 1)).get("q"));
}
