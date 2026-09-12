import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "bun:test";
import { createMockModel, registerMockApi } from "@oh-my-pi/pi-ai/providers/mock";
import { createAgentSession, SessionManager, Settings } from "@oh-my-pi/pi-coding-agent";
import {
	CONTROLLED_SETTINGS,
	assertRequiredNativeTools,
	controlledToolRoster,
} from "../../containers/harbor-launcher/yacht_harbor_agents/omp_policy.ts";

registerMockApi();

describe("createAgentSession controlled roster", () => {
	it("keeps discoverable grep enabled after filtering spawning tools", async () => {
		const cwd = await mkdtemp(join(tmpdir(), "yacht-omp-"));
		const mock = createMockModel({ responses: [{ content: ["ok"] }] });
		const settings = await Settings.loadIsolated({ cwd, agentDir: cwd });
		for (const [path, value] of Object.entries(CONTROLLED_SETTINGS)) {
			settings.override(path as never, value as never);
		}
		const created = await createAgentSession({
			cwd,
			agentDir: cwd,
			sessionManager: SessionManager.inMemory(),
			model: mock,
			settings,
			disableExtensionDiscovery: true,
			enableMCP: false,
			restrictToolNames: false,
		});
		try {
			if (created.modelFallbackMessage) throw new Error(created.modelFallbackMessage);
			const roster = controlledToolRoster(
				created.session.getEnabledToolNames(),
				created.session.getMountedXdevToolNames(),
			);
			expect(roster).toContain("grep");
			assertRequiredNativeTools(roster);
			await created.session.setActiveToolsByName(roster);
			expect(created.session.getEnabledToolNames()).toContain("grep");
		} finally {
			await created.session.dispose();
		}
	});
});
