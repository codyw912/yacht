# ADR 0024: MCP Installs Through Capability-Providing Riggings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a rigged tool (pi-mcp-adapter) provide the `mcp-server` install method for a harness that lacks it (pi), with yacht rendering the adapter's config so delivery stays measurable — per `docs/adr/0024-unlock-mcp-installs-through-capability-providing-riggings.md`.

**Architecture:** A `provides` declaration on `[tools.<name>]` entries names the install method and harness a rigged tool provides. A built-in provider registry in `yacht/harnesses/mcp_config.py` ships the per-provider rendering knowledge (config target, settings that pin the `mcp__<server>__` namespace). The capability gate, trial-home setup, harbor job rendering, and expectation derivation all consult the same resolution helper: native harness support first, then a rigged provider, else refuse/omit.

**Tech Stack:** Python 3.12, stdlib `unittest` (NOT pytest), `uv run --locked`, jj (colocated git repo).

## Global Constraints

- **Version control is jj, not git.** `git commit` fails on signing. Commit with `jj commit -m "<message>"` (the working copy is auto-tracked; no staging step). The feature bookmark is `adr-0024`.
- **Tests:** run a module with `uv run --locked -m unittest tests.test_<name> -v`; the full suite with `uv run --locked -m unittest discover -s tests`.
- **Provider facts (verified against pi-mcp-adapter 2.15.0 README and harbor 0.20.0 source; do not re-derive):**
  - pi has NO native MCP support; `pi-mcp-adapter` installs via `pi install npm:pi-mcp-adapter@<version>` and reads config from `~/.pi/agent/mcp.json`.
  - The rendered config document carries the servers and the adapter settings in one JSON file: `{"mcpServers": {...}, "settings": {"directTools": true, "toolPrefix": "mcp"}}`. `directTools: true` + `toolPrefix: "mcp"` yields the delimited `mcp__<server>__<tool>` names that ADR 0022's matching already expects.
  - Harbor 0.20.0's Pi agent tees pi's `--mode json` JSONL stream (minus `message_update` events) to `/logs/agent/pi.txt` in the trial dir, and runs pi commands with `. ~/.nvm/nvm.sh;` sourced first (node comes from nvm in the task container).
- **Honesty rules from the ADR:** no provider declaration → the gate refuses; no namespace guarantee → no expectation (unmeasured, never guessed). Refusal messages state what is missing.
- Follow existing code style: frozen dataclasses, `_private` module helpers, docstrings only where they carry a constraint the code can't show.

---

### Task 1: `provides` declarations on tool capabilities

**Files:**
- Modify: `src/yacht/runtimes/tool_capabilities.py`
- Modify: `src/yacht/config/loader.py` (function `_parse_tool_capabilities`, ~line 512)
- Test: `tests/test_mcp_providers.py` (create)

**Interfaces:**
- Consumes: existing `ToolCapability` dataclass.
- Produces: `ProvidedInstall(method: str, harness: str)` frozen dataclass in `yacht.runtimes.tool_capabilities`; `ToolCapability.provides: tuple[ProvidedInstall, ...] = ()`; `to_json()` emits `"provides": [{"method": ..., "harness": ...}]` when non-empty; loader parses `provides = [{ method = "...", harness = "..." }]` from `[tools.<name>]` tables.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mcp_providers.py`:

```python
import unittest

from yacht.config.loader import _parse_tool_capabilities
from yacht.runtimes.tool_capabilities import ProvidedInstall, ToolCapability


class ProvidesDeclarationTests(unittest.TestCase):
    def test_tool_capability_declares_provided_install_method(self) -> None:
        capability = ToolCapability(
            name="pi-mcp-adapter",
            kind="mcp-adapter",
            provides=(ProvidedInstall(method="mcp-server", harness="pi"),),
        )

        self.assertEqual(
            capability.to_json()["provides"],
            [{"method": "mcp-server", "harness": "pi"}],
        )

    def test_to_json_omits_empty_provides(self) -> None:
        capability = ToolCapability(name="fff", kind="code-navigation")

        self.assertNotIn("provides", capability.to_json())

    def test_loader_parses_provides_from_tools_table(self) -> None:
        capabilities = _parse_tool_capabilities(
            {
                "tools": {
                    "pi-mcp-adapter": {
                        "kind": "mcp-adapter",
                        "install_methods": ["agent-extension"],
                        "provides": [
                            {"method": "mcp-server", "harness": "pi"},
                        ],
                    }
                }
            }
        )

        self.assertEqual(
            capabilities["pi-mcp-adapter"].provides,
            (ProvidedInstall(method="mcp-server", harness="pi"),),
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --locked -m unittest tests.test_mcp_providers -v`
Expected: FAIL with `ImportError: cannot import name 'ProvidedInstall'`

- [ ] **Step 3: Implement**

In `src/yacht/runtimes/tool_capabilities.py`, add above `ToolCapability`:

```python
@dataclass(frozen=True)
class ProvidedInstall:
    method: str
    harness: str
```

Add to `ToolCapability` fields (after `expected_tool_calls`):

```python
    provides: tuple[ProvidedInstall, ...] = ()
```

Add to `ToolCapability.to_json()` (after the `expected_tool_calls` block):

```python
        if self.provides:
            payload["provides"] = [
                {"method": provided.method, "harness": provided.harness}
                for provided in self.provides
            ]
```

In `src/yacht/config/loader.py`, `_parse_tool_capabilities`, add to the `ToolCapability(...)` construction (after `expected_tool_calls=...`):

```python
                provides=tuple(
                    ProvidedInstall(
                        method=str(item["method"]),
                        harness=str(item["harness"]),
                    )
                    for item in tool.get("provides", ())
                ),
```

and add `ProvidedInstall` to the existing `from yacht.runtimes.tool_capabilities import ...` import in loader.py.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --locked -m unittest tests.test_mcp_providers -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
jj commit -m "Declare provided install methods on tool capabilities"
```

---

### Task 2: Provider registry, pi-mcp-adapter renderer, and schema validation

**Files:**
- Modify: `src/yacht/harnesses/mcp_config.py`
- Modify: `src/yacht/runtimes/tool_capabilities.py` (resolution helper)
- Modify: `src/yacht/contracts/schemas.py` (function `_validate_tool_capabilities`, ~line 4132)
- Test: `tests/test_mcp_providers.py`

**Interfaces:**
- Consumes: `ProvidedInstall`, `ToolCapability` from Task 1; existing `McpConfigRender`, `McpServerEntry`, `McpConfigError` in `mcp_config.py`; `RiggingRecipe` from `yacht.domain.model`.
- Produces (in `yacht.harnesses.mcp_config`):
  - `McpInstallProvider(tool_name: str, harness: str, config_target: str, pins_namespace: bool)` frozen dataclass
  - `PI_MCP_ADAPTER_CONFIG_TARGET = ".pi/agent/mcp.json"`
  - `MCP_INSTALL_PROVIDERS: dict[tuple[str, str], McpInstallProvider]` keyed by `(tool_name, harness)`
  - `supported_mcp_install_provider(tool_name: str, harness: str) -> bool`
  - `render_provider_mcp_config(provider: McpInstallProvider, steps: tuple[tuple[str, RiggingInstallStep], ...]) -> McpConfigRender`
- Produces (in `yacht.runtimes.tool_capabilities`):
  - `provided_mcp_install_provider(harness: str | None, riggings: tuple[RiggingRecipe, ...], capabilities: dict[str, ToolCapability] | None) -> McpInstallProvider | None`
- Import direction rule: `mcp_config.py` must keep zero imports from `yacht.runtimes` (its docstring says why); the capabilities-aware resolution helper therefore lives in `runtimes/tool_capabilities.py`, which MAY import from `yacht.harnesses.mcp_config` and `yacht.domain.model`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mcp_providers.py`:

```python
import json

from yacht.domain.model import RiggingInstallStep, RiggingRecipe
from yacht.contracts.schemas import SchemaValidationError, _validate_tool_capabilities
from yacht.harnesses.mcp_config import (
    MCP_INSTALL_PROVIDERS,
    McpConfigError,
    render_provider_mcp_config,
    supported_mcp_install_provider,
)
from yacht.runtimes.tool_capabilities import provided_mcp_install_provider


def _adapter_capability() -> ToolCapability:
    return ToolCapability(
        name="pi-mcp-adapter",
        kind="mcp-adapter",
        provides=(ProvidedInstall(method="mcp-server", harness="pi"),),
    )


class ProviderRegistryTests(unittest.TestCase):
    def test_pi_mcp_adapter_is_a_supported_provider_for_pi(self) -> None:
        self.assertTrue(supported_mcp_install_provider("pi-mcp-adapter", "pi"))
        self.assertFalse(supported_mcp_install_provider("pi-mcp-adapter", "claude-code"))
        self.assertFalse(supported_mcp_install_provider("other-adapter", "pi"))

    def test_renders_servers_and_observability_settings_in_one_document(self) -> None:
        provider = MCP_INSTALL_PROVIDERS[("pi-mcp-adapter", "pi")]
        step = RiggingInstallStep(
            method="mcp-server",
            target="files",
            command=("mcp-server-filesystem", "/app"),
        )

        render = render_provider_mcp_config(provider, (("pi-mcp-files", step),))

        self.assertEqual(render.target, ".pi/agent/mcp.json")
        self.assertEqual(
            json.loads(render.content),
            {
                "mcpServers": {
                    "files": {
                        "command": "mcp-server-filesystem",
                        "args": ["/app"],
                    }
                },
                "settings": {"directTools": True, "toolPrefix": "mcp"},
            },
        )
        self.assertEqual(
            [(entry.origin_name, entry.server_name) for entry in render.entries],
            [("pi-mcp-files", "files")],
        )

    def test_provider_render_requires_command_and_unique_server_names(self) -> None:
        provider = MCP_INSTALL_PROVIDERS[("pi-mcp-adapter", "pi")]
        no_command = RiggingInstallStep(method="mcp-server", target="files")

        with self.assertRaises(McpConfigError):
            render_provider_mcp_config(provider, (("rig", no_command),))


class ProviderResolutionTests(unittest.TestCase):
    def test_resolves_provider_rigged_on_the_vessel(self) -> None:
        rigging = RiggingRecipe(name="pi-mcp-files", tools=("pi-mcp-adapter",))
        capabilities = {"pi-mcp-adapter": _adapter_capability()}

        provider = provided_mcp_install_provider("pi", (rigging,), capabilities)

        self.assertIsNotNone(provider)
        self.assertEqual(provider.tool_name, "pi-mcp-adapter")
        self.assertTrue(provider.pins_namespace)

    def test_no_provider_without_declaration_or_for_other_harness(self) -> None:
        rigging = RiggingRecipe(name="pi-mcp-files", tools=("pi-mcp-adapter",))
        capabilities = {"pi-mcp-adapter": _adapter_capability()}

        self.assertIsNone(provided_mcp_install_provider("claude-code", (rigging,), capabilities))
        self.assertIsNone(provided_mcp_install_provider("pi", (rigging,), {}))
        self.assertIsNone(provided_mcp_install_provider("pi", (rigging,), None))
        self.assertIsNone(provided_mcp_install_provider(None, (rigging,), capabilities))


class ProvidesSchemaValidationTests(unittest.TestCase):
    def test_accepts_a_supported_provider_declaration(self) -> None:
        _validate_tool_capabilities(
            {
                "tools": {
                    "pi-mcp-adapter": {
                        "kind": "mcp-adapter",
                        "provides": [{"method": "mcp-server", "harness": "pi"}],
                    }
                }
            }
        )

    def test_rejects_a_provider_yacht_cannot_render_for(self) -> None:
        with self.assertRaises(SchemaValidationError):
            _validate_tool_capabilities(
                {
                    "tools": {
                        "mystery-adapter": {
                            "kind": "mcp-adapter",
                            "provides": [{"method": "mcp-server", "harness": "pi"}],
                        }
                    }
                }
            )

    def test_rejects_unknown_provided_methods(self) -> None:
        with self.assertRaises(SchemaValidationError):
            _validate_tool_capabilities(
                {
                    "tools": {
                        "pi-mcp-adapter": {
                            "kind": "mcp-adapter",
                            "provides": [{"method": "package", "harness": "pi"}],
                        }
                    }
                }
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --locked -m unittest tests.test_mcp_providers -v`
Expected: FAIL with `ImportError` on the new `mcp_config` names.

- [ ] **Step 3: Implement the registry and renderer in `src/yacht/harnesses/mcp_config.py`**

Extend the module docstring's first paragraph with one sentence: providers registered here can supply the renderer for a harness that lacks one (ADR 0024). Then add:

```python
PI_MCP_ADAPTER_CONFIG_TARGET = ".pi/agent/mcp.json"


@dataclass(frozen=True)
class McpInstallProvider:
    """A rigged tool yacht knows how to render MCP configuration for.

    pins_namespace records whether the rendered settings guarantee the
    delimited mcp__<server>__ tool names ADR 0022 matches; a provider
    without the guarantee yields no delivery expectation.
    """

    tool_name: str
    harness: str
    config_target: str
    pins_namespace: bool


MCP_INSTALL_PROVIDERS: dict[tuple[str, str], McpInstallProvider] = {
    ("pi-mcp-adapter", "pi"): McpInstallProvider(
        tool_name="pi-mcp-adapter",
        harness="pi",
        config_target=PI_MCP_ADAPTER_CONFIG_TARGET,
        pins_namespace=True,
    ),
}


def supported_mcp_install_provider(tool_name: str, harness: str) -> bool:
    return (tool_name, harness) in MCP_INSTALL_PROVIDERS


def render_provider_mcp_config(
    provider: McpInstallProvider,
    steps: tuple[tuple[str, RiggingInstallStep], ...],
) -> McpConfigRender:
    servers, entries = _mcp_servers_from_steps(steps)
    content = (
        json.dumps(
            {
                "mcpServers": servers,
                # directTools + the mcp toolPrefix pin the delimited
                # namespace; proxy mode would make delivery unobservable.
                "settings": {"directTools": True, "toolPrefix": "mcp"},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return McpConfigRender(
        target=provider.config_target,
        content=content,
        entries=entries,
    )
```

Refactor the duplicated server-dict loop: extract the body of `_render_claude_code_mcp_config` into

```python
def _mcp_servers_from_steps(
    steps: tuple[tuple[str, RiggingInstallStep], ...],
) -> tuple[dict[str, dict[str, object]], tuple[McpServerEntry, ...]]:
```

(the existing loop verbatim: command required, duplicate target refused, entries accumulated) and have both `_render_claude_code_mcp_config` and `render_provider_mcp_config` call it.

- [ ] **Step 4: Implement the resolution helper in `src/yacht/runtimes/tool_capabilities.py`**

```python
from yacht.domain.model import RiggingRecipe
from yacht.harnesses.mcp_config import MCP_INSTALL_PROVIDERS, McpInstallProvider


def provided_mcp_install_provider(
    harness: str | None,
    riggings: tuple[RiggingRecipe, ...],
    capabilities: dict[str, ToolCapability] | None,
) -> McpInstallProvider | None:
    """The supported provider a rigged tool declares for this harness,
    or None. Declaration and registry must agree: a tool that declares
    provision yacht cannot render for resolves to nothing."""
    if harness is None or not capabilities:
        return None
    for rigging in riggings:
        for tool_name in rigging.tools:
            capability = capabilities.get(tool_name)
            if capability is None:
                continue
            for provided in capability.provides:
                if provided.method != "mcp-server" or provided.harness != harness:
                    continue
                provider = MCP_INSTALL_PROVIDERS.get((tool_name, harness))
                if provider is not None:
                    return provider
    return None
```

- [ ] **Step 5: Implement schema validation in `src/yacht/contracts/schemas.py`**

Add near the top imports: `from yacht.harnesses.mcp_config import supported_mcp_install_provider`.

In `_validate_tool_capabilities`, after the `expected_tool_calls` block:

```python
        provides = tool.get("provides", [])
        provides_list = _require_list(provides, f"tools.{tool_name}.provides")
        for index, entry_value in enumerate(provides_list):
            entry_path = f"tools.{tool_name}.provides[{index}]"
            entry = _require_object(entry_value, entry_path)
            _require_allowed_value(
                entry.get("method"), {"mcp-server"}, f"{entry_path}.method"
            )
            _require_non_empty_string(entry.get("harness"), f"{entry_path}.harness")
            if not supported_mcp_install_provider(tool_name, str(entry["harness"])):
                raise SchemaValidationError(
                    f"{entry_path} declares an unsupported provider: yacht "
                    f"does not ship a {entry['method']} rendering for tool "
                    f"{tool_name} on harness {entry['harness']}"
                )
```

(Check the exact names of `_require_list`/`_require_object`/`_require_allowed_value` helpers in the file and match them.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run --locked -m unittest tests.test_mcp_providers -v`
Expected: all PASS. Also run `uv run --locked -m unittest tests.test_schemas -v` to catch regressions.

- [ ] **Step 7: Commit**

```bash
jj commit -m "Ship the MCP install provider registry with the pi-mcp-adapter rendering"
```

---

### Task 3: Capability gate accepts provider-provided mcp-server installs

**Files:**
- Modify: `src/yacht/runtimes/capabilities.py`
- Modify: `src/yacht/preflight/runner.py` (thread `tool_capabilities` from `_planned_vessel_preflight` ~line 293 → `_planned_preflight_checks` ~line 311 → `_planned_rigging_capability_checks` ~line 350)
- Modify: `src/yacht/workflows/real_benchmark_runbook.py` (`_rigging_capabilities`, ~line 192)
- Test: `tests/test_mcp_providers.py`

**Interfaces:**
- Consumes: `provided_mcp_install_provider` from Task 2.
- Produces: `rigging_capabilities_to_json(runtime, riggings, tool_capabilities=None)` and `unsupported_rigging_capability_reasons(runtime, riggings, tool_capabilities=None)` — same names, `tool_capabilities` now also feeds the gate (None keeps today's native-only behavior, which is refusal, the safe side). Supported provider-backed checks carry `"provided_by": "<tool name>"`. Also: `agent-extension` on the `harbor` backend is supported only for harnesses the launcher can install extensions for (`HARBOR_AGENT_EXTENSION_HARNESSES = {"pi"}` — needed by Task 8's install path).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mcp_providers.py`:

```python
from yacht.domain.model import RuntimeRecipe
from yacht.runtimes.capabilities import (
    rigging_capabilities_to_json,
    unsupported_rigging_capability_reasons,
)


def _pi_runtime(backend: str = "container") -> RuntimeRecipe:
    return RuntimeRecipe(
        name="pi-runtime",
        backend=backend,
        harness="pi",
        image="yacht/pi-agent-runtime:pi-0.74.0",
        command=("pi",),
    )


def _mcp_rigging() -> RiggingRecipe:
    return RiggingRecipe(
        name="pi-mcp-files",
        tools=("pi-mcp-adapter", "files"),
        install=(
            RiggingInstallStep(
                method="agent-extension",
                target="npm:pi-mcp-adapter@2.15.0",
                agent="pi",
            ),
            RiggingInstallStep(
                method="mcp-server",
                target="files",
                command=("mcp-server-filesystem", "/app"),
            ),
        ),
    )


class ProviderCapabilityGateTests(unittest.TestCase):
    def test_provider_unlocks_mcp_server_for_pi(self) -> None:
        capabilities = {"pi-mcp-adapter": _adapter_capability()}

        reasons = unsupported_rigging_capability_reasons(
            _pi_runtime(), (_mcp_rigging(),), capabilities
        )

        self.assertEqual(reasons, ())

    def test_gate_still_refuses_without_the_provider(self) -> None:
        reasons = unsupported_rigging_capability_reasons(
            _pi_runtime(), (_mcp_rigging(),), {}
        )

        self.assertEqual(len(reasons), 1)
        self.assertIn("mcp-server", reasons[0])

    def test_check_payload_names_the_provider(self) -> None:
        capabilities = {"pi-mcp-adapter": _adapter_capability()}

        payload = rigging_capabilities_to_json(
            _pi_runtime(), (_mcp_rigging(),), capabilities
        )

        mcp_checks = [
            check
            for check in payload["install_checks"]
            if check["method"] == "mcp-server"
        ]
        self.assertEqual(mcp_checks[0]["provided_by"], "pi-mcp-adapter")
        self.assertTrue(mcp_checks[0]["supported"])

    def test_claude_code_native_support_gains_no_provided_by(self) -> None:
        runtime = RuntimeRecipe(
            name="claude-runtime",
            backend="container",
            harness="claude-code",
            image="img",
            command=("claude",),
        )
        rigging = RiggingRecipe(
            name="files-mcp",
            install=(
                RiggingInstallStep(
                    method="mcp-server",
                    target="files",
                    command=("mcp-server-filesystem", "/app"),
                ),
            ),
        )

        payload = rigging_capabilities_to_json(runtime, (rigging,), {})

        check = payload["install_checks"][0]
        self.assertTrue(check["supported"])
        self.assertNotIn("provided_by", check)

    def test_harbor_agent_extension_supported_for_pi_only(self) -> None:
        step = RiggingInstallStep(
            method="agent-extension",
            target="npm:pi-mcp-adapter@2.15.0",
            agent="pi",
        )
        rigging = RiggingRecipe(name="adapter", install=(step,))
        pi_harbor = RuntimeRecipe(
            name="harbor-pi",
            backend="harbor",
            harness="pi",
            image="yacht/harbor-launcher:harbor-0.20.0",
            command=(),
        )
        claude_harbor = RuntimeRecipe(
            name="harbor-claude",
            backend="harbor",
            harness="claude-code",
            image="yacht/harbor-launcher:harbor-0.20.0",
            command=(),
        )
        claude_step = RiggingInstallStep(
            method="agent-extension", target="npm:x@1.0.0", agent="claude-code"
        )

        self.assertEqual(
            unsupported_rigging_capability_reasons(pi_harbor, (rigging,), {}), ()
        )
        self.assertEqual(
            len(
                unsupported_rigging_capability_reasons(
                    claude_harbor,
                    (RiggingRecipe(name="x", install=(claude_step,)),),
                    {},
                )
            ),
            1,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --locked -m unittest tests.test_mcp_providers -v`
Expected: the new gate tests FAIL (`unsupported_rigging_capability_reasons` takes 2 args; pi mcp-server refused; harbor agent-extension refused).

- [ ] **Step 3: Implement in `src/yacht/runtimes/capabilities.py`**

- Add `"agent-extension"` to `SUPPORTED_INSTALL_METHODS_BY_BACKEND["harbor"]` and define `HARBOR_AGENT_EXTENSION_HARNESSES = {"pi"}` (module constant — the launcher's in-container installer map in Task 8 mirrors it).
- Change signatures:

```python
def rigging_capabilities_to_json(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    tool_capabilities: dict[str, ToolCapability] | None = None,
) -> dict[str, Any]:
    checks = _install_checks(runtime, riggings, tool_capabilities)
    ...

def unsupported_rigging_capability_reasons(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    tool_capabilities: dict[str, ToolCapability] | None = None,
) -> tuple[str, ...]:
    checks = _install_checks(runtime, riggings, tool_capabilities)
    ...
```

- `_install_checks` resolves the provider once for the vessel (provision is vessel-wide — a provider in one rigging unlocks mcp-server steps in another rigging on the same vessel):

```python
def _install_checks(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    tool_capabilities: dict[str, ToolCapability] | None,
) -> list[dict[str, Any]]:
    provider = provided_mcp_install_provider(
        harness_for_runtime(runtime), riggings, tool_capabilities
    )
    return [
        _install_check(runtime, rigging, step, provider)
        for rigging in riggings
        for step in rigging.install
    ]
```

- `_install_check(runtime, rigging, step, provider)` passes `provider` to `_step_support` and, when the step is `mcp-server`, supported, and NOT natively supported (`not supports_mcp_server_installs(harness_for_runtime(runtime))`), adds `payload["provided_by"] = provider.tool_name`.
- `_step_support(runtime, step, provider)` changes:
  - `agent-extension` branch gains, after the existing agent-mismatch check:

    ```python
        if (
            runtime.backend == "harbor"
            and runtime_harness not in HARBOR_AGENT_EXTENSION_HARNESSES
        ):
            return (
                False,
                "agent-extension installs on the harbor backend are supported "
                f"for harnesses {sorted(HARBOR_AGENT_EXTENSION_HARNESSES)} only, "
                f"not {runtime_harness}",
            )
    ```
  - `mcp-server` branch becomes:

    ```python
    if step.method == "mcp-server":
        runtime_harness = harness_for_runtime(runtime)
        if not supports_mcp_server_installs(runtime_harness) and provider is None:
            return (
                False,
                f"runtime harness {runtime_harness} does not support rigging "
                "install method mcp-server and no rigged tool provides it",
            )
        if not step.command:
            return (
                False,
                f"mcp-server install {step.target} requires command",
            )
    ```
- Import `provided_mcp_install_provider` and `ToolCapability` from `yacht.runtimes.tool_capabilities`.

- [ ] **Step 4: Thread `tool_capabilities` through the two callers that lack it**

- `src/yacht/preflight/runner.py`: add `tool_capabilities: dict[str, ToolCapability]` keyword parameter to `_planned_preflight_checks` and `_planned_rigging_capability_checks`; pass `regatta.tool_capabilities` from `_planned_vessel_preflight` (line ~293) and hand it to `rigging_capabilities_to_json(runtime, riggings, tool_capabilities)` at line ~356. Import `ToolCapability` for the annotation.
- `src/yacht/workflows/real_benchmark_runbook.py` line ~199: `rigging_capabilities_to_json(runtime, riggings, regatta.tool_capabilities)`.

- [ ] **Step 5: Run tests**

Run: `uv run --locked -m unittest tests.test_mcp_providers tests.test_cli_preflight tests.test_real_benchmark_runbook -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
jj commit -m "Accept provider-provided mcp-server installs at the capability gate"
```

---

### Task 4: Render the provider's config into the trial home

**Files:**
- Modify: `src/yacht/runtimes/rigging_setup.py`
- Modify: `src/yacht/runtimes/backend.py` (`_apply_rigging_installs` ~line 197, both `prepare` call sites)
- Test: `tests/test_rigging_setup.py`

**Interfaces:**
- Consumes: `render_provider_mcp_config`, `provided_mcp_install_provider`, gate signatures from Tasks 2–3.
- Produces: `plan_rigging_setup(*, runtime, riggings, command_prefix, tool_capabilities=None)` — when the harness has no native renderer but a rigged provider exists, `plan.mcp_config` is the provider render (target `.pi/agent/mcp.json`). `apply_rigging_setup` is unchanged (it already writes `plan.mcp_config` into the trial home via `_write_into_trial_home`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rigging_setup.py` (reuse its `_runtime()` pi fixture and `_mcp_step` helper):

```python
from yacht.runtimes.tool_capabilities import ProvidedInstall, ToolCapability


def _adapter_capabilities() -> dict[str, ToolCapability]:
    return {
        "pi-mcp-adapter": ToolCapability(
            name="pi-mcp-adapter",
            kind="mcp-adapter",
            provides=(ProvidedInstall(method="mcp-server", harness="pi"),),
        )
    }


class ProviderMcpConfigPlanTests(unittest.TestCase):
    def test_plans_provider_config_for_pi_with_adapter_rigged(self) -> None:
        rigging = RiggingRecipe(
            name="pi-mcp-files",
            tools=("pi-mcp-adapter", "files"),
            install=(
                RiggingInstallStep(
                    method="agent-extension",
                    target="npm:pi-mcp-adapter@2.15.0",
                    agent="pi",
                ),
                _mcp_step("files", ("mcp-server-filesystem", "/app")),
            ),
        )

        plan = plan_rigging_setup(
            runtime=_runtime(),
            riggings=(rigging,),
            command_prefix=(),
            tool_capabilities=_adapter_capabilities(),
        )

        self.assertIsNotNone(plan.mcp_config)
        self.assertEqual(plan.mcp_config.target, ".pi/agent/mcp.json")
        content = json.loads(plan.mcp_config.content)
        self.assertEqual(
            content["settings"], {"directTools": True, "toolPrefix": "mcp"}
        )
        self.assertIn("files", content["mcpServers"])
        # The adapter itself still installs by its ordinary step.
        self.assertEqual(
            [command.target for command in plan.commands],
            ["npm:pi-mcp-adapter@2.15.0"],
        )

    def test_still_rejects_mcp_server_for_pi_without_the_provider(self) -> None:
        rigging = RiggingRecipe(
            name="pi-mcp-files",
            install=(_mcp_step("files", ("mcp-server-filesystem", "/app")),),
        )

        with self.assertRaises(RiggingSetupError):
            plan_rigging_setup(
                runtime=_runtime(),
                riggings=(rigging,),
                command_prefix=(),
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --locked -m unittest tests.test_rigging_setup -v`
Expected: new tests FAIL (`plan_rigging_setup` has no `tool_capabilities` parameter).

- [ ] **Step 3: Implement in `src/yacht/runtimes/rigging_setup.py`**

- `plan_rigging_setup` gains `tool_capabilities: dict[str, ToolCapability] | None = None`; pass it to `unsupported_rigging_capability_reasons(runtime, riggings, tool_capabilities)` and to `_mcp_config(runtime, riggings, tuple(mcp_steps), tool_capabilities)`.
- `_mcp_config` becomes:

```python
def _mcp_config(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    mcp_steps: tuple[tuple[str, RiggingInstallStep], ...],
    tool_capabilities: dict[str, ToolCapability] | None,
) -> McpConfigRender | None:
    if not mcp_steps:
        return None
    harness = harness_for_runtime(runtime)
    try:
        render = render_mcp_config(harness, mcp_steps)
        if render is None:
            provider = provided_mcp_install_provider(
                harness, riggings, tool_capabilities
            )
            if provider is not None:
                render = render_provider_mcp_config(provider, mcp_steps)
    except McpConfigError as error:
        raise RiggingSetupError(str(error)) from error
    if render is None:
        raise RiggingSetupError(
            f"runtime harness {harness} does not support rigging install "
            "method mcp-server and no rigged tool provides it"
        )
    return render
```

- Imports: `render_provider_mcp_config` from `yacht.harnesses.mcp_config`; `ToolCapability`, `provided_mcp_install_provider` from `yacht.runtimes.tool_capabilities`.

- [ ] **Step 4: Thread from the backends**

In `src/yacht/runtimes/backend.py`, `_apply_rigging_installs` gains a `tool_capabilities` parameter passed to `plan_rigging_setup`; both `HostNixRuntimeBackend.prepare` and `ContainerRuntimeBackend.prepare` pass `tool_capabilities=regatta.tool_capabilities`.

- [ ] **Step 5: Run tests**

Run: `uv run --locked -m unittest tests.test_rigging_setup tests.test_runtime_backend -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
jj commit -m "Render provider MCP configuration into the trial home"
```

---

### Task 5: Add the pi MCP examples

**Files:**
- Create: `examples/custom-eval-pi-mcp-ab-smoke.toml`
- Create: `examples/container-pi-mcp-real-task-smoke.toml`
- Create: `preflights/pi-mcp.md`

**Interfaces:**
- Consumes: schema `provides` support (Task 2), gate (Task 3). Reuses the existing `examples/custom-evals/mcp-task` task directory — do not author a new task.
- Produces: the two configs later tasks load as test fixtures (`CustomEvalPiMcp` fixtures in Tasks 6 and 8 reference these exact paths and vessel names).

- [ ] **Step 1: Write `examples/custom-eval-pi-mcp-ab-smoke.toml`**

Mirror `examples/custom-eval-mcp-ab-smoke.toml` (same course/adapter/secrets/preflight structure — copy those blocks, then adjust). Full content:

```toml
# Measure MCP delivery on a harness without MCP support (ADR 0024):
# stock pi cannot carry an MCP server; the treatment rigs
# pi-mcp-adapter — a declared install provider — plus the reference
# filesystem server. yacht renders the adapter's mcp.json with
# directTools on and the delimited mcp toolPrefix, so the treatment
# stays observable as mcp__files__ tools in the preserved transcript.
#
#   uv run yacht run examples/custom-eval-pi-mcp-ab-smoke.toml \
#     --logbook /private/tmp/yacht-pi-mcp-ab \
#     --workspace . \
#     --secret anthropic=@env:ANTHROPIC_API_KEY \
#     --repetitions 3
#
# Requirements: Docker running, uv, ANTHROPIC_API_KEY exported, and the
# pinned launcher image built (rebuild it after launcher changes):
#
#   docker build -t yacht/harbor-launcher:harbor-0.20.0 containers/harbor-launcher

[regatta]
name = "custom-eval-pi-mcp-ab-smoke"

[preflight]
failure_policy = "abort-group"

[course]
name = "pi-mcp-files-ab"

[[course.tasks]]
id = "mcp-task"
title = "Inventory the data files, via MCP filesystem tools when available"

[course.adapter]
kind = "custom-eval"
dataset = "custom-evals"
split = "v1"
harness = "harbor"

[secrets.anthropic]
source = "env"
name = "ANTHROPIC_API_KEY"

[runtimes.harbor-pi]
backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "pi"
harness_version = "0.74.0"
required_secrets = ["anthropic"]

[runtimes.harbor-pi.preflight]
required = true
checks = [
  { name = "docker-daemon", kind = "command", command = ["docker", "info"] },
  { name = "harbor-launcher-image", kind = "command", command = ["docker", "image", "inspect", "yacht/harbor-launcher:harbor-0.20.0"] },
  { name = "agent-install", kind = "install-only" },
]

# The provider: an extension that gives pi the mcp-server install
# method. Declaring provision is what unlocks the capability gate;
# yacht ships the rendering that keeps it observable (ADR 0024).
[tools.pi-mcp-adapter]
kind = "mcp-adapter"
description = "MCP adapter extension for pi: provides the mcp-server install method."
interfaces = ["agent-tool"]
install_methods = ["agent-extension"]
provides = [{ method = "mcp-server", harness = "pi" }]

[tools.files]
kind = "mcp-server"
description = "Reference filesystem MCP server: directory listing and file reads under /app."
interfaces = ["mcp"]
install_methods = ["package", "mcp-server"]

# The treatment is honestly a composition: the adapter plus the server.
[riggings.pi-mcp-files]
tools = ["pi-mcp-adapter", "files"]
instructions = "Prefer the mcp__files__ tools for filesystem inspection."

[[riggings.pi-mcp-files.install]]
method = "agent-extension"
target = "npm:pi-mcp-adapter@2.15.0"
agent = "pi"

[[riggings.pi-mcp-files.install]]
method = "package"
target = "npm:@modelcontextprotocol/server-filesystem@2026.7.10"

[[riggings.pi-mcp-files.install]]
method = "mcp-server"
target = "files"
command = ["mcp-server-filesystem", "/app"]

[[vessels]]
name = "pi-baseline"
model = "anthropic/claude-haiku-4-5"
runtime = "harbor-pi"

[[vessels]]
name = "pi-with-mcp"
model = "anthropic/claude-haiku-4-5"
runtime = "harbor-pi"
rigging = ["pi-mcp-files"]

[[comparisons]]
name = "pi-mcp-vs-baseline"
course = "pi-mcp-files-ab"
vessels = ["pi-baseline", "pi-with-mcp"]
```

- [ ] **Step 2: Write `examples/container-pi-mcp-real-task-smoke.toml`**

Mirror `examples/container-pi-fff-real-task-smoke.toml`'s runtime block and `examples/container-claude-code-mcp-real-task-smoke.toml`'s shape; this one exercises the container-backend render path and the agent-prompt liveness gate the ADR names:

```toml
# ADR 0024 on the container backend: the adapter's servers are lazy
# (they connect on first tool call), so a config-presence check proves
# rendering, not a working server. The agent-prompt preflight with
# expect_tool_calls is the liveness gate.

[regatta]
name = "container-pi-mcp-real-task-smoke"

[preflight]
failure_policy = "abort-group"

[course]
name = "container-pi-mcp-real-task-smoke"
tasks = [
  { id = "container-pi-mcp-smoke-1", title = "Inspect this repository using any configured MCP tooling available to you, then reply with a compact JSON object containing completed and tool_calls.", difficulty = 1 },
]

[secrets.anthropic]
source = "env"
name = "ANTHROPIC_API_KEY"

[runtimes.pi-container]
backend = "container"
harness = "pi"
image = "yacht/pi-agent-runtime:pi-0.74.0"
command = ["pi", "--provider", "anthropic", "--model", "haiku", "--print", "--mode", "json"]
container_home = "/home/yacht"
container_workspace = "/workspace"
required_secrets = ["anthropic"]

[runtimes.pi-container.preflight]
required = true
checks = [
  { name = "pi-present", kind = "command", command = ["pi", "--version"] },
  { name = "runtime-home-isolated", kind = "path-isolation", env = ["HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"] },
]

[tools.pi-mcp-adapter]
kind = "mcp-adapter"
description = "MCP adapter extension for pi: provides the mcp-server install method."
interfaces = ["agent-tool"]
install_methods = ["agent-extension"]
provides = [{ method = "mcp-server", harness = "pi" }]

[tools.files]
kind = "mcp-server"
description = "Reference filesystem MCP server scoped to the trial workspace."
interfaces = ["mcp"]
install_methods = ["package", "mcp-server"]

[riggings.pi-mcp-files]
tools = ["pi-mcp-adapter", "files"]
instructions = "Use the mcp__files__ tools for filesystem inspection. For this smoke task, make exactly one minimal mcp__files__list_allowed_directories tool call before answering."

[[riggings.pi-mcp-files.install]]
method = "agent-extension"
target = "npm:pi-mcp-adapter@2.15.0"
agent = "pi"

[[riggings.pi-mcp-files.install]]
method = "package"
target = "npm:@modelcontextprotocol/server-filesystem@2026.7.10"

[[riggings.pi-mcp-files.install]]
method = "mcp-server"
target = "files"
command = ["mcp-server-filesystem", "/workspace"]

[riggings.pi-mcp-files.preflight]
required = true
checks = [
  { name = "pi-mcp-headless-smoke", kind = "agent-prompt", prompt = "preflights/pi-mcp.md", expect_tool_calls = ["mcp__files__list_allowed_directories"] },
]

[[vessels]]
name = "pi-container-baseline"
model = "haiku"
runtime = "pi-container"

[[vessels]]
name = "pi-container-mcp"
model = "haiku"
runtime = "pi-container"
rigging = ["pi-mcp-files"]

[[comparisons]]
name = "container-pi-vs-pi-mcp-real-task"
course = "container-pi-mcp-real-task-smoke"
vessels = ["pi-container-baseline", "pi-container-mcp"]
```

- [ ] **Step 3: Write `preflights/pi-mcp.md`**

Mirror `preflights/claude-code-fff-mcp.md`:

```markdown
You are running a YACHT preflight smoke check for the MCP integration in
pi, provided by the pi-mcp-adapter extension.

Verify that the files MCP server is available in the current session and
that it is configured for the isolated runtime state prepared by YACHT.

Requirements:
- Make one minimal `mcp__files__list_allowed_directories` tool call that
  proves the MCP server is reachable.
- Do not modify the repository or benchmark workspace.

Return only one JSON object on stdout:

```json
{
  "available": true,
  "tool_calls": ["mcp__files__list_allowed_directories"],
  "notes": "short factual note"
}
```

Set `available` to `false` if the files MCP server cannot be reached.
```

- [ ] **Step 4: Validate both configs**

Run:
```bash
uv run --locked yacht validate examples/custom-eval-pi-mcp-ab-smoke.toml
uv run --locked yacht validate examples/container-pi-mcp-real-task-smoke.toml
```
Expected: both succeed. If validation rejects a field, fix the config (or, if the schema is wrong, the schema task) — do not delete the declaration to make validation pass.

- [ ] **Step 5: Commit**

```bash
jj commit -m "Add the pi MCP A/B examples riding the declared provider"
```

---

### Task 6: Key MCP expectations on the namespace guarantee

**Files:**
- Modify: `src/yacht/courses/terminal_bench/attempts_from_trials.py` (`_tool_expectations` ~line 204 and the `_MCP_NAMESPACED_HARNESSES` comment block ~line 198)
- Test: `tests/test_skill_invocation.py` (existing home of `_tool_expectations` tests)

**Interfaces:**
- Consumes: `provided_mcp_install_provider` (Task 2), `examples/custom-eval-pi-mcp-ab-smoke.toml` (Task 5). Existing test pattern in `tests/test_skill_invocation.py`: load an example config with `load_regatta`, pick a vessel by name, call `_tool_expectations(regatta, vessel, runtime)`.
- Produces: expectations emitted when the harness namespaces natively OR a rigged provider with `pins_namespace=True` covers the harness; otherwise the mcp-server steps yield nothing (unmeasured).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_skill_invocation.py` (match its existing imports/fixtures; it already defines `MCP_EXAMPLE_CONFIG` and helpers that load regattas from example files):

```python
PI_MCP_EXAMPLE_CONFIG = Path("examples/custom-eval-pi-mcp-ab-smoke.toml")


class PiProviderExpectationTests(unittest.TestCase):
    def test_provider_guarantee_emits_the_namespace_expectation(self) -> None:
        regatta = load_regatta(PI_MCP_EXAMPLE_CONFIG)
        vessel = next(v for v in regatta.vessels if v.name == "pi-with-mcp")
        runtime = regatta.runtime_recipes[vessel.runtime]

        expectations = _tool_expectations(regatta, vessel, runtime)

        mcp = [e for e in expectations if e["kind"] == "mcp-server"]
        self.assertEqual(
            mcp,
            [
                {
                    "tool": "files",
                    "kind": "mcp-server",
                    "expected_calls": ["mcp__files__"],
                }
            ],
        )

    def test_stock_pi_vessel_gets_no_mcp_expectation(self) -> None:
        regatta = load_regatta(PI_MCP_EXAMPLE_CONFIG)
        vessel = next(v for v in regatta.vessels if v.name == "pi-baseline")
        runtime = regatta.runtime_recipes[vessel.runtime]

        self.assertEqual(_tool_expectations(regatta, vessel, runtime), [])
```

(Adjust `load_regatta` import/spelling to whatever `tests/test_skill_invocation.py` already uses.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --locked -m unittest tests.test_skill_invocation -v`
Expected: the provider test FAILS (pi is not in `_MCP_NAMESPACED_HARNESSES`, so no expectation).

- [ ] **Step 3: Implement**

In `_tool_expectations`, compute the guarantee once before the rigging loop and use it in place of the per-iteration harness test:

```python
    riggings = tuple(
        rigging
        for name in vessel.rigging
        if (rigging := regatta.rigging_recipes.get(name)) is not None
    )
    provider = provided_mcp_install_provider(
        runtime.harness, riggings, regatta.tool_capabilities
    )
    mcp_namespaced = runtime.harness in _MCP_NAMESPACED_HARNESSES or (
        provider is not None and provider.pins_namespace
    )
```

and replace `if runtime.harness not in _MCP_NAMESPACED_HARNESSES: continue` with `if not mcp_namespaced: continue`.

Update the comment above `_MCP_NAMESPACED_HARNESSES` (~line 198): the namespace is guaranteed natively by Claude Code, or by a rigged provider whose rendered configuration pins the delimited convention (ADR 0024); a harness with neither yields no expectation rather than a marker its transcripts can never match.

Import `provided_mcp_install_provider` from `yacht.runtimes.tool_capabilities`.

- [ ] **Step 4: Run tests**

Run: `uv run --locked -m unittest tests.test_skill_invocation -v`
Expected: PASS (including the pre-existing claude-code expectation tests).

- [ ] **Step 5: Commit**

```bash
jj commit -m "Emit MCP expectations from the namespace guarantee, not the harness list"
```

---

### Task 7: Observe pi tool calls from preserved harbor trials

**Files:**
- Modify: `src/yacht/harnesses/pi.py`
- Modify: `src/yacht/courses/terminal_bench/attempts_from_trials.py` (`_observed_tool_calls` ~line 301)
- Test: `tests/test_mcp_providers.py`

**Interfaces:**
- Consumes: existing private pi JSONL parsers in `pi.py` (`_jsonl_events`, `_looks_like_pi_jsonl`, `_tool_calls_from_pi_events`). Harbor's Pi agent preserves the JSONL stream at `<trial_dir>/agent/pi.txt`.
- Produces (in `yacht.harnesses.pi`): `PI_JSONL_EVIDENCE = "pi-jsonl"` and

  ```python
  def tool_calls_from_pi_jsonl(output: str) -> tuple[str, ...] | None:
      """Tool calls from a preserved pi --mode json stream, or None when
      the output is not pi JSONL — unmeasured, which is different from a
      stream that shows no tool was called."""
  ```
- `attempts_from_trials._observed_tool_calls` gains a third source: after `harness-evidence` and Claude Code sessions, read `trial_dir / "agent" / "pi.txt"` when it exists; a parseable stream returns `(list(calls), PI_JSONL_EVIDENCE)` even when calls is empty (measured zero).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mcp_providers.py`:

```python
import tempfile
from pathlib import Path

from yacht.harnesses.pi import PI_JSONL_EVIDENCE, tool_calls_from_pi_jsonl
from yacht.courses.terminal_bench.attempts_from_trials import _observed_tool_calls

PI_JSONL = "\n".join(
    [
        '{"type": "agent_start"}',
        '{"type": "turn_end", "toolResults": [{"toolName": "mcp__files__list_directory"}]}',
        '{"type": "message_end", "message": {"role": "assistant", "api": "anthropic", "content": [{"type": "text", "text": "done"}]}}',
        '{"type": "agent_end"}',
    ]
)


class PiObservedToolCallTests(unittest.TestCase):
    def test_parses_tool_calls_from_pi_jsonl(self) -> None:
        self.assertEqual(
            tool_calls_from_pi_jsonl(PI_JSONL),
            ("mcp__files__list_directory",),
        )

    def test_non_pi_output_is_unmeasured(self) -> None:
        self.assertIsNone(tool_calls_from_pi_jsonl("plain text output"))

    def test_observed_tool_calls_reads_preserved_pi_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial_dir = Path(tmp)
            (trial_dir / "agent").mkdir()
            (trial_dir / "agent" / "pi.txt").write_text(
                PI_JSONL, encoding="utf-8"
            )

            calls, source = _observed_tool_calls(trial_dir)

        self.assertEqual(calls, ["mcp__files__list_directory"])
        self.assertEqual(source, PI_JSONL_EVIDENCE)

    def test_missing_pi_output_stays_unmeasured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls, source = _observed_tool_calls(Path(tmp))

        self.assertEqual(calls, [])
        self.assertIsNone(source)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --locked -m unittest tests.test_mcp_providers -v`
Expected: FAIL with `ImportError: cannot import name 'PI_JSONL_EVIDENCE'`.

- [ ] **Step 3: Implement**

In `src/yacht/harnesses/pi.py` (near the top-level constants):

```python
PI_JSONL_EVIDENCE = "pi-jsonl"


def tool_calls_from_pi_jsonl(output: str) -> tuple[str, ...] | None:
    """Tool calls from a preserved pi --mode json stream, or None when
    the output is not pi JSONL — unmeasured, which is different from a
    stream that shows no tool was called."""
    events = _jsonl_events(output)
    if not events or not _looks_like_pi_jsonl(events):
        return None
    return _tool_calls_from_pi_events(events)
```

In `attempts_from_trials.py`, extend `_observed_tool_calls`:

```python
    pi_calls = _pi_output_tool_calls(trial_dir / "agent" / "pi.txt")
    if pi_calls is not None:
        return list(pi_calls), PI_JSONL_EVIDENCE
    return [], None
```

with:

```python
def _pi_output_tool_calls(output_path: Path) -> tuple[str, ...] | None:
    if not output_path.is_file():
        return None
    return tool_calls_from_pi_jsonl(output_path.read_text(encoding="utf-8"))
```

Import `PI_JSONL_EVIDENCE, tool_calls_from_pi_jsonl` from `yacht.harnesses.pi`. If this import creates a cycle (pi.py imports `yacht.workflows.task_attempts` and `yacht.preflight`), verify with `uv run --locked -m compileall src` plus the test run; if a cycle appears, move the two parser entry points into a new leaf module `src/yacht/harnesses/pi_jsonl.py` and re-export from `pi.py`.

- [ ] **Step 4: Run tests**

Run: `uv run --locked -m unittest tests.test_mcp_providers tests.test_pi_adapter -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
jj commit -m "Mine observed tool calls from preserved pi trial output"
```

---

### Task 8: Carry the provider composition onto harbor courses

**Files:**
- Modify: `src/yacht/courses/terminal_bench/job.py`
- Modify: `containers/harbor-launcher/yacht_harbor_agents/rigging.py`
- Test: `tests/test_harbor_agent_rigging.py` (launcher), `tests/test_terminal_bench_course.py` (job rendering — it already imports `render_terminal_bench_job` and `load_regatta` and has existing `mcp_servers` job tests around lines 159–213)

**Interfaces:**
- Consumes: `provided_mcp_install_provider`, `render_provider_mcp_config`, `supports_mcp_server_installs`; the harbor pi example from Task 5.
- Produces:
  - `job.py`: `SUPPORTED_RIGGING_INSTALL_METHODS = ("agent-extension", "config-file", "mcp-server", "package")`. `render_terminal_bench_job` resolves the provider for the vessel. Native-MCP harness (claude-code): behavior unchanged (`mcp_servers` passthrough). Provider path (pi + adapter): `agent["mcp_servers"] == []`, and `rigging_steps` carries (a) the agent-extension steps verbatim via `step.to_json()` (pin required: reuse `_PACKAGE_PIN` against the target) and (b) one synthetic config-file step `{"method": "config-file", "target": "<provider config_target>", "content": "<rendered JSON>"}` replacing the mcp-server steps. mcp-server steps with neither native support nor a provider raise `ConfigError` with the same message as the gate.
  - `rigging.py` (launcher): `SUPPORTED_METHODS = ("agent-extension", "config-file", "package")`; agent-extension steps run the per-agent installer — `_AGENT_EXTENSION_INSTALLERS = {"pi": ". ~/.nvm/nvm.sh; pi install {target}"}` — with the npm-prefixed pinned target quoted via `shlex.quote`; unknown agents raise `ValueError`. (This mirrors `HARBOR_AGENT_EXTENSION_HARNESSES` from Task 3 — keep the two in sync.)

- [ ] **Step 1: Write the failing launcher tests**

Append to `tests/test_harbor_agent_rigging.py` (match its existing import of `rigging_commands`):

```python
    def test_agent_extension_step_installs_through_pi(self) -> None:
        commands = rigging_commands(
            [
                {
                    "method": "agent-extension",
                    "target": "npm:pi-mcp-adapter@2.15.0",
                    "agent": "pi",
                }
            ]
        )

        self.assertEqual(len(commands), 1)
        self.assertIn(". ~/.nvm/nvm.sh; pi install", commands[0])
        self.assertIn("npm:pi-mcp-adapter@2.15.0", commands[0])

    def test_agent_extension_step_rejects_unknown_agents(self) -> None:
        with self.assertRaises(ValueError):
            rigging_commands(
                [
                    {
                        "method": "agent-extension",
                        "target": "npm:x@1.0.0",
                        "agent": "claude-code",
                    }
                ]
            )
```

- [ ] **Step 2: Write the failing job-rendering tests**

Append to `tests/test_terminal_bench_course.py` (it already imports `json`, `Path`, `render_terminal_bench_job`, and `load_regatta`):

```python
PI_MCP_EXAMPLE_CONFIG = Path("examples/custom-eval-pi-mcp-ab-smoke.toml")


class ProviderJobRenderingTests(unittest.TestCase):
    def test_provider_vessel_ships_rendered_config_not_mcp_servers(self) -> None:
        regatta = load_regatta(PI_MCP_EXAMPLE_CONFIG)

        job = render_terminal_bench_job(regatta=regatta, vessel_name="pi-with-mcp")

        agent = job["agent"]
        self.assertEqual(agent["mcp_servers"], [])
        methods = [step["method"] for step in agent["rigging_steps"]]
        self.assertIn("agent-extension", methods)
        config_steps = [
            step
            for step in agent["rigging_steps"]
            if step["method"] == "config-file"
            and step["target"] == ".pi/agent/mcp.json"
        ]
        self.assertEqual(len(config_steps), 1)
        content = json.loads(config_steps[0]["content"])
        self.assertEqual(
            content["settings"], {"directTools": True, "toolPrefix": "mcp"}
        )
        self.assertIn("files", content["mcpServers"])

    def test_claude_code_native_path_is_unchanged(self) -> None:
        regatta = load_regatta(Path("examples/custom-eval-mcp-ab-smoke.toml"))

        job = render_terminal_bench_job(
            regatta=regatta, vessel_name="claude-with-mcp"
        )

        self.assertEqual(
            [server["name"] for server in job["agent"]["mcp_servers"]], ["files"]
        )
```

- [ ] **Step 3: Run both test modules to verify they fail**

Expected failures: launcher raises on `agent-extension` (unsupported method); job render passes mcp-server steps into `mcp_servers` for pi and rejects agent-extension via `_require_supported_method`.

- [ ] **Step 4: Implement the launcher side (`containers/harbor-launcher/yacht_harbor_agents/rigging.py`)**

```python
SUPPORTED_METHODS = ("agent-extension", "config-file", "package")

_AGENT_EXTENSION_INSTALLERS = {
    # pi's node comes from nvm inside harbor task containers.
    "pi": ". ~/.nvm/nvm.sh; pi install {target}",
}
```

`_step_command` dispatches `agent-extension` to:

```python
def _agent_extension_command(step: dict[str, Any]) -> str:
    agent = step.get("agent")
    template = _AGENT_EXTENSION_INSTALLERS.get(agent)
    if template is None:
        supported = ", ".join(sorted(_AGENT_EXTENSION_INSTALLERS))
        raise ValueError(
            f"agent-extension steps are supported for agents {supported} in "
            f"task containers, got {agent!r}"
        )
    target = step.get("target")
    if not isinstance(target, str) or not target.startswith("npm:"):
        raise ValueError(
            f"agent-extension step target must use the npm: prefix, got {target!r}"
        )
    return template.format(target=shlex.quote(target))
```

- [ ] **Step 5: Implement the job side (`src/yacht/courses/terminal_bench/job.py`)**

- Add `"agent-extension"` to `SUPPORTED_RIGGING_INSTALL_METHODS`.
- In `render_terminal_bench_job`, resolve once:

```python
    provider = provided_mcp_install_provider(
        _harness_name(runtime), tuple(riggings), regatta.tool_capabilities
    )
```

- Restructure `_mcp_servers` / `_rigging_steps` into provider-aware forms (suggested: keep both functions, give them the provider and harness):
  - `_mcp_servers(riggings, harness)` returns the current list when `supports_mcp_server_installs(harness)`; otherwise `[]` (steps are handled by `_rigging_steps`). Keep its validation (command required, duplicates refused) running in both cases.
  - `_rigging_steps(riggings, harness, provider)`:
    - mcp-server steps: skipped when native; rendered into ONE appended synthetic step when a provider exists —

      ```python
      render = render_provider_mcp_config(provider, tuple(mcp_steps))
      steps.append(
          {
              "method": "config-file",
              "target": render.target,
              "content": render.content,
          }
      )
      ```
    - mcp-server steps with neither native support nor provider: `raise ConfigError(f"runtime harness {harness} does not support rigging install method mcp-server and no rigged tool provides it")`.
    - agent-extension steps: require `step.agent == harness` and a version-pinned target (`_PACKAGE_PIN.search(step.target)`), then pass through `step.to_json()`.
- Imports: `provided_mcp_install_provider` from `yacht.runtimes.tool_capabilities`; `render_provider_mcp_config`, `supports_mcp_server_installs` from `yacht.harnesses.mcp_config`.

- [ ] **Step 6: Run tests**

Run: `uv run --locked -m unittest tests.test_harbor_agent_rigging tests.test_terminal_bench_course tests.test_course_handoff -v`
Expected: PASS (the job document must still satisfy `validate_terminal_bench_job_document` — the synthetic config-file step is an object in `rigging_steps`, which the schema allows).

- [ ] **Step 7: Commit**

```bash
jj commit -m "Carry the provider composition onto harbor courses"
```

---

### Task 9: Docs, changelog, ADR acceptance, full checks

**Files:**
- Modify: `docs/adr/0024-unlock-mcp-installs-through-capability-providing-riggings.md` (Status: Proposed → Accepted)
- Modify: `docs/reference/custom-evals.md` (MCP section: note that a harness without native MCP support can carry a server through a declared provider, referencing the pi example)
- Modify: `docs/tutorials/validating-a-tool-claim.md` (one sentence + link where MCP delivery is discussed: pi requires the pi-mcp-adapter provider, see `examples/custom-eval-pi-mcp-ab-smoke.toml`)
- Modify: `CHANGELOG.md` (new `## Unreleased` section at top)

**Interfaces:** none — documentation only, but the changelog entry must describe behavior implemented in Tasks 1–8, not aspirations.

- [ ] **Step 1: Flip the ADR status to Accepted**

- [ ] **Step 2: Update the two docs**

Keep each addition short (2–4 sentences) and in the file's existing voice. Key points: provision is declared on the tool (`provides = [{ method = "mcp-server", harness = "pi" }]`); yacht renders the adapter's config with observability pinned; no declaration → the gate still refuses; no guarantee → unmeasured, never guessed.

- [ ] **Step 3: Add the changelog entry**

```markdown
## Unreleased

### MCP installs through capability-providing riggings (ADR 0024)

- A `[tools.<name>]` entry can declare that it provides the `mcp-server`
  install method for a named harness, and the capability gate accepts an
  mcp-server step when the harness supports it natively or a rigged tool
  provides it. pi-mcp-adapter on pi is the first supported provider:
  yacht renders the adapter's `.pi/agent/mcp.json` with `directTools` on
  and the delimited `mcp` tool prefix, so delivery stays measurable.
- MCP delivery expectations now key on the namespace guarantee rather
  than the harness list, and harbor trials preserve pi's JSONL stream as
  tool-call evidence, so stock-versus-extended MCP comparisons extend to
  pi with delivery evidence on the treatment side.
```

- [ ] **Step 4: Run the full local checks**

```bash
uv run --locked -m unittest discover -s tests
uv run --locked -m compileall src tests
uv run --locked yacht validate examples/custom-eval-pi-mcp-ab-smoke.toml
uv run --locked yacht validate examples/container-pi-mcp-real-task-smoke.toml
uv run --locked yacht validate examples/custom-eval-mcp-ab-smoke.toml
uv run --locked yacht validate examples/container-pi-fff-real-benchmark-smoke.toml
```
Expected: all pass. Fix anything that fails before committing.

- [ ] **Step 5: Commit**

```bash
jj commit -m "Accept ADR 0024 and document provider-backed MCP installs"
```

---

## Post-plan notes (not tasks)

- **Live validation before release:** per the standing practice, this feature needs a token-spending integration run before the next release: rebuild the launcher image (`docker build -t yacht/harbor-launcher:harbor-0.20.0 containers/harbor-launcher` — the launcher's rigging module changed in Task 8), then run `examples/custom-eval-pi-mcp-ab-smoke.toml` with `--repetitions 3` and confirm the scorecard shows a measured `files` invocation rate with `observed_tools` on the treatment vessel. Two pins may need adjusting from live results: pi `harness_version = "0.74.0"` and `pi-mcp-adapter@2.15.0` (compatibility between the two is unverified offline; the adapter README's naming under `toolPrefix: "mcp"` matches the ADR but only the live run proves `mcp__files__<tool>` end to end).
- **Branch finish:** bookmark `adr-0024` already holds the ADR commits. After the last task: `jj bookmark set adr-0024 -r @-`, push, and open the PR (plain URL in output, lean description, no attribution footers).
