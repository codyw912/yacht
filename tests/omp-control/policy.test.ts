import { describe, expect, it } from "bun:test";
import {
	CONTROLLED_ENV,
	CONTROLLED_SETTINGS,
	MODEL_SPAWNING_TOOLS,
	REQUIRED_NATIVE_TOOLS,
	assertNoModelSpawningTools,
	assertSideInferenceGuards,
	assertRequiredNativeTools,
	controlledToolRoster,
	isQuestionRead,
	parseExactModelSelector,
	RESTRICT_TOOL_NAMES,
} from "../../containers/harbor-launcher/yacht_harbor_agents/omp_policy.ts";

describe("controlled execution policy", () => {
	it("disables automatic side model work, retry/fallback, compaction, and background jobs", () => {
		expect(CONTROLLED_SETTINGS["compaction.enabled"]).toBe(false);
		expect(CONTROLLED_SETTINGS["compaction.autoContinue"]).toBe(false);
		expect(CONTROLLED_SETTINGS["compaction.midTurnEnabled"]).toBe(false);
		expect(CONTROLLED_SETTINGS["compaction.asyncEnabled"]).toBe(false);
		expect(CONTROLLED_SETTINGS["compaction.experimentalContextManagement"]).toBe(false);
		expect(CONTROLLED_SETTINGS["retry.enabled"]).toBe(false);
		expect(CONTROLLED_SETTINGS["retry.modelFallback"]).toBe(false);
		expect(CONTROLLED_SETTINGS["retry.usageAwareFallback"]).toBe(false);
		expect(CONTROLLED_SETTINGS["advisor.enabled"]).toBe(false);
		expect(CONTROLLED_SETTINGS["autolearn.enabled"]).toBe(false);
		expect(CONTROLLED_SETTINGS["autolearn.autoContinue"]).toBe(false);
		expect(CONTROLLED_SETTINGS["memory.backend"]).toBe("off");
		expect(CONTROLLED_SETTINGS["bash.autoBackground.enabled"]).toBe(false);
		expect(CONTROLLED_SETTINGS["eval.autoBackground.enabled"]).toBe(false);
		expect(CONTROLLED_SETTINGS["async.enabled"]).toBe(false);
		expect(CONTROLLED_SETTINGS["goal.enabled"]).toBe(false);
		expect(CONTROLLED_SETTINGS["title.refreshOnReplan"]).toBe(false);
		expect(CONTROLLED_ENV.PI_NO_TITLE).toBe("1");
	});

	it("preserves required native tools and does not use restrictToolNames", () => {
		expect(REQUIRED_NATIVE_TOOLS).toEqual(["bash", "read", "write", "edit", "grep"]);
		expect(RESTRICT_TOOL_NAMES).toBe(false);
	});

	it("rejects model-spawning surfaces instead of claiming budget parity", () => {
		expect(MODEL_SPAWNING_TOOLS).toEqual(expect.arrayContaining(["task", "eval", "browser"]));
		expect(() => assertNoModelSpawningTools(["bash", "read", "write", "edit", "grep", "mcp__plane_workitem"])).not.toThrow();
		expect(() => assertNoModelSpawningTools(["bash", "task"])).toThrow(/task|unsupported/i);
		expect(() => assertNoModelSpawningTools(["eval"])).toThrow(/eval|unsupported/i);
		expect(() => assertNoModelSpawningTools(["browser"])).toThrow(/browser|unsupported/i);
	});

	it("parses an exact model selector with reasoning suffix and does not invent a fallback", () => {
		expect(parseExactModelSelector("omp-subscriptions/xai-oauth/grok-4.6:medium")).toEqual({
			provider: "omp-subscriptions",
			id: "xai-oauth/grok-4.6",
			thinkingLevel: "medium",
		});
		expect(() => parseExactModelSelector("")).toThrow(/model/i);
		expect(() => parseExactModelSelector("grok-4.6")).toThrow(/model/i);
	});

	it("keeps discoverable grep and mounted MCP while dropping spawning tools", () => {
		const roster = controlledToolRoster(
			["bash", "read", "write", "edit", "task", "eval"],
			["grep", "mcp__plane_workitem"],
		);
		expect(roster).toEqual(["bash", "read", "write", "edit", "grep", "mcp__plane_workitem"]);
		expect(() => assertRequiredNativeTools(roster)).not.toThrow();
	});

	it("rejects native read image-question mode without disabling ordinary read", () => {
		expect(isQuestionRead("read", { path: "notes.md" })).toBe(false);
		expect(isQuestionRead("read", { path: "image.png", q: "what is this" })).toBe(true);
		expect(isQuestionRead("read", { path: "image.png?q=what" })).toBe(true);
		expect(isQuestionRead("read", { path: "image.png?%71=what" })).toBe(true);
		expect(isQuestionRead("read", { path: "image.png?q=" })).toBe(false);
		expect(isQuestionRead("read", { path: "https://example.com/search?q=ordinary" })).toBe(false);
		expect(isQuestionRead("bash", { q: "x" })).toBe(false);
	});

	it("refuses to run when a side-inference guard setting drifted", () => {
		const effective: Record<string, unknown> = { "memory.backend": "off", "autolearn.enabled": false, "launch.enabled": false };
		expect(() => assertSideInferenceGuards((path) => effective[path])).not.toThrow();
		effective["memory.backend"] = "mnemopi";
		expect(() => assertSideInferenceGuards((path) => effective[path])).toThrow(/memory\.backend/);
		effective["memory.backend"] = "off";
		effective["autolearn.enabled"] = true;
		expect(() => assertSideInferenceGuards((path) => effective[path])).toThrow(/autolearn\.enabled/);
		effective["autolearn.enabled"] = false;
		effective["launch.enabled"] = true;
		expect(() => assertSideInferenceGuards((path) => effective[path])).toThrow(/launch\.enabled/);
	});
});
