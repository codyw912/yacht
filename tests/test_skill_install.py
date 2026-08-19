import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from yacht.domain.model import (
    ConfigError,
    RiggingInstallStep,
    RiggingRecipe,
    RuntimeRecipe,
    load_regatta,
)
from yacht.runtimes.capabilities import unsupported_rigging_capability_reasons
from yacht.runtimes.rigging_setup import plan_rigging_setup
from yacht.courses.terminal_bench.attempts_from_trials import (
    _agent_to_json,
    _tool_expectations,
)
from yacht.courses.terminal_bench.job import render_terminal_bench_job
from yacht.contracts.schemas import validate_task_attempt_document
from yacht.reports.task_attempt_scorecard import write_task_attempt_scorecard
from yacht.reports.benchmark_report import _delivery_decision
from yacht.reports.html_report import _delivery_table

from yacht.harnesses.skill_config import (
    SkillConfigError,
    render_skill_installs,
    supports_skill_installs,
)


SKILL_BODY = """\
---
name: team-conventions
description: Team conventions for tool modules.
---

# Tool module conventions
"""


def _skill_step(
    target: str = "team-conventions",
    content: str | None = SKILL_BODY,
) -> RiggingInstallStep:
    return RiggingInstallStep(method="skill", target=target, content=content)


class SkillInstallSupportTests(unittest.TestCase):
    def test_supported_harnesses_include_omp_and_codex(self) -> None:
        self.assertTrue(supports_skill_installs("claude-code"))
        self.assertTrue(supports_skill_installs("codex"))
        self.assertTrue(supports_skill_installs("omp"))

    def test_pi_does_not_support_skill_installs(self) -> None:
        self.assertFalse(supports_skill_installs("pi"))
        self.assertFalse(supports_skill_installs(None))


class ClaudeCodeSkillRenderTests(unittest.TestCase):
    def test_renders_skill_into_claude_project_layout(self) -> None:
        renders = render_skill_installs(
            "claude-code", (("team-conventions-skill", _skill_step()),)
        )

        self.assertEqual(len(renders), 1)
        self.assertEqual(
            renders[0].target,
            ".claude/skills/team-conventions/SKILL.md",
        )
        self.assertEqual(renders[0].content, SKILL_BODY)
        self.assertEqual(renders[0].skill_name, "team-conventions")
        self.assertEqual(renders[0].origin_name, "team-conventions-skill")

    def test_renders_omp_and_codex_skills_into_agent_skills_layout(self) -> None:
        for harness in ("omp", "codex"):
            with self.subTest(harness=harness):
                renders = render_skill_installs(
                    harness, (("team-conventions-skill", _skill_step()),)
                )

                self.assertEqual(
                    renders[0].target, ".agents/skills/team-conventions/SKILL.md"
                )

    def test_unsupported_harness_fails_before_tokens(self) -> None:
        with self.assertRaisesRegex(SkillConfigError, "does not support"):
            render_skill_installs("pi", (("team-conventions-skill", _skill_step()),))
        with self.assertRaisesRegex(SkillConfigError, "does not support"):
            render_skill_installs(None, (("team-conventions-skill", _skill_step()),))

    def test_missing_content_fails_on_supported_harness(self) -> None:
        with self.assertRaisesRegex(SkillConfigError, "missing content"):
            render_skill_installs(
                "claude-code",
                (("team-conventions-skill", _skill_step(content=None)),),
            )


def _skill_rigging() -> RiggingRecipe:
    return RiggingRecipe(name="team-conventions-skill", install=(_skill_step(),))


def _runtime(*, backend: str, harness: str) -> RuntimeRecipe:
    return RuntimeRecipe(
        name=f"{harness}-{backend}",
        backend=backend,
        harness=harness,
        image="yacht/test-image:1",
        command=(harness,),
    )


class SkillCapabilityGateTests(unittest.TestCase):
    def test_claude_code_accepts_skill_installs(self) -> None:
        reasons = unsupported_rigging_capability_reasons(
            _runtime(backend="harbor", harness="claude-code"),
            (_skill_rigging(),),
        )

        self.assertEqual(reasons, ())

    def test_pi_refuses_skill_installs_before_tokens(self) -> None:
        reasons = unsupported_rigging_capability_reasons(
            _runtime(backend="harbor", harness="pi"),
            (_skill_rigging(),),
        )

        self.assertEqual(len(reasons), 1)
        self.assertIn("does not support rigging install method skill", reasons[0])


def _skill_config(
    install_body: str,
    *,
    backend: str = "container",
    harness: str = "claude-code",
) -> str:
    runtime = f"""
[runtimes.box]
backend = "{backend}"
image = "yacht/test-image:1"
harness = "{harness}"
"""
    if backend == "harbor":
        runtime += 'harness_version = "1.0.0"\n'
    else:
        runtime += f'command = ["{harness}"]\n'
    adapter = ""
    if backend == "harbor":
        adapter = """
[course.adapter]
kind = "terminal-bench"
dataset = "terminal-bench/terminal-bench-2"
split = "2.0"
harness = "harbor"
"""
    return f"""
[regatta]
name = "skill-install"

[course]
name = "tiny-course"
tasks = [
  {{ id = "task-1", title = "Fix a failing test", difficulty = 1 }},
]
{adapter}
{runtime}
[tools.team-conventions]
kind = "agent-skill"
install_methods = ["skill"]

[riggings.team-conventions-skill]
tools = ["team-conventions"]

[[riggings.team-conventions-skill.install]]
{install_body}

[[vessels]]
name = "with-skill"
model = "mock"
runtime = "box"
rigging = ["team-conventions-skill"]
"""


class SkillInstallConfigTests(unittest.TestCase):
    def test_inline_skill_content_parses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(
                _skill_config(
                    'method = "skill"\n'
                    'target = "team-conventions"\n'
                    f'content = """{SKILL_BODY}"""'
                ),
                encoding="utf-8",
            )

            regatta = load_regatta(config_path)

        step = regatta.rigging_recipes["team-conventions-skill"].install[0]
        self.assertEqual(step.method, "skill")
        self.assertEqual(step.target, "team-conventions")
        self.assertEqual(step.content, SKILL_BODY)

    def test_skill_install_requires_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(
                _skill_config('method = "skill"\ntarget = "team-conventions"'),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "requires content"):
                load_regatta(config_path)


class SkillSetupPlanTests(unittest.TestCase):
    def test_plans_claude_code_skill_as_native_file(self) -> None:
        plan = plan_rigging_setup(
            runtime=_runtime(backend="container", harness="claude-code"),
            riggings=(_skill_rigging(),),
            command_prefix=(),
        )

        self.assertEqual(plan.commands, ())
        self.assertEqual(len(plan.files), 1)
        self.assertEqual(
            plan.files[0].target,
            ".claude/skills/team-conventions/SKILL.md",
        )
        self.assertEqual(plan.files[0].content, SKILL_BODY)
        self.assertEqual(plan.files[0].origin_name, "team-conventions-skill")


def _skill_payload_digest(*payload: str) -> str:
    """The digest a skill payload of SKILL.md plus resources should carry.

    Computed here independently of the renderer so the test pins the
    definition (logical relative path, NUL, content, NUL; sorted) rather
    than echoing whatever the renderer produced.
    """
    entries = [("SKILL.md", payload[0])]
    digest = hashlib.sha256()
    for relative_path, content in sorted(entries):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(content.encode("utf-8"))
        digest.update(b"\x00")
    return f"sha256:{digest.hexdigest()}"


class SkillHarborJobTests(unittest.TestCase):
    def test_job_renders_skill_as_native_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(
                _skill_config(
                    'method = "skill"\n'
                    'target = "team-conventions"\n'
                    f'content = """{SKILL_BODY}"""',
                    backend="harbor",
                ),
                encoding="utf-8",
            )
            regatta = load_regatta(config_path)

            job = render_terminal_bench_job(
                regatta=regatta,
                vessel_name="with-skill",
            )

        # The payload digest pins what Yacht rendered and shipped. It is
        # recorded for every skill, resources or not, so a missing digest
        # never has to be interpreted.
        self.assertEqual(
            job["agent"]["rigging_steps"],
            [
                {
                    "method": "config-file",
                    "target": ".claude/skills/team-conventions/SKILL.md",
                    "content": SKILL_BODY,
                    "content_digest": _skill_payload_digest(SKILL_BODY),
                }
            ],
        )

    def test_job_renders_omp_and_codex_skills_and_harbor_agents(self) -> None:
        for harness, import_path, skill_target in (
            (
                "omp",
                "yacht_harbor_agents.agents:YachtOmp",
                ".agents/skills/team-conventions/SKILL.md",
            ),
            (
                "codex",
                "yacht_harbor_agents.agents:YachtCodex",
                ".agents/skills/team-conventions/SKILL.md",
            ),
        ):
            with self.subTest(harness=harness):
                with tempfile.TemporaryDirectory() as temp_dir:
                    config_path = Path(temp_dir) / "regatta.toml"
                    config_path.write_text(
                        _skill_config(
                            'method = "skill"\n'
                            'target = "team-conventions"\n'
                            f'content = """{SKILL_BODY}"""',
                            backend="harbor",
                            harness=harness,
                        ),
                        encoding="utf-8",
                    )
                    job = render_terminal_bench_job(
                        regatta=load_regatta(config_path),
                        vessel_name="with-skill",
                    )

                self.assertEqual(job["agent"]["import_path"], import_path)
                self.assertEqual(
                    job["agent"]["rigging_steps"],
                    [
                        {
                            "method": "config-file",
                            "target": skill_target,
                            "content": SKILL_BODY,
                            "content_digest": _skill_payload_digest(SKILL_BODY),
                        }
                    ],
                )

    def test_job_rejects_skill_on_unsupported_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(
                _skill_config(
                    'method = "skill"\n'
                    'target = "team-conventions"\n'
                    f'content = """{SKILL_BODY}"""',
                    backend="harbor",
                    harness="pi",
                ),
                encoding="utf-8",
            )
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(ConfigError, "does not support"):
                render_terminal_bench_job(regatta=regatta, vessel_name="with-skill")


class SkillExpectationTests(unittest.TestCase):
    def test_logical_skill_install_uses_skill_target_not_claude_path(self) -> None:
        body = """\
---
name: conventions
description: Team conventions.
---

# Conventions
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(
                _skill_config(
                    f'method = "skill"\ntarget = "conventions"\ncontent = """{body}"""'
                ),
                encoding="utf-8",
            )
            regatta = load_regatta(config_path)

        vessel = next(v for v in regatta.vessels if v.name == "with-skill")
        runtime = regatta.runtime_recipes[vessel.runtime]
        expectations = _tool_expectations(regatta, vessel, runtime)

        self.assertEqual(
            expectations,
            [
                {
                    "tool": "team-conventions",
                    "kind": "agent-skill",
                    "expected_calls": ["Skill:conventions"],
                }
            ],
        )


class SkillStageEvidenceTests(unittest.TestCase):
    def test_claude_skill_tool_use_is_selected_not_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir)
            sessions = trial_dir / "agent" / "sessions" / "projects" / "-app"
            sessions.mkdir(parents=True)
            (sessions / "session.jsonl").write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Skill",
                                    "input": {"skill": "team-conventions"},
                                }
                            ]
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            agent = _agent_to_json(None, str(trial_dir), True)

        self.assertEqual(agent["tool_calls"], ["Skill:team-conventions"])
        self.assertEqual(
            agent["skill_stages"],
            [
                {
                    "skill": "team-conventions",
                    "available": "unmeasured",
                    "selected": "observed",
                    "loaded": "unmeasured",
                    "evidence_source": "claude-code-session-transcript",
                }
            ],
        )

    def test_omp_and_codex_native_streams_emit_skill_stages(self) -> None:
        fixtures = Path("tests/fixtures")
        cases = (
            ("omp.jsonl", "omp-skill-read.jsonl", "yacht-fixture", "omp-jsonl"),
            ("codex.jsonl", "codex-exec-skill.jsonl", "yacht-fixture", "codex-jsonl"),
        )
        for filename, fixture, skill, source in cases:
            with self.subTest(filename=filename):
                with tempfile.TemporaryDirectory() as temp_dir:
                    trial_dir = Path(temp_dir)
                    agent_dir = trial_dir / "agent"
                    agent_dir.mkdir(parents=True)
                    (agent_dir / filename).write_text(
                        fixtures.joinpath(fixture).read_text(encoding="utf-8"),
                        encoding="utf-8",
                    )
                    agent = _agent_to_json(None, str(trial_dir), True)

                self.assertEqual(
                    agent["skill_stages"],
                    [
                        {
                            "skill": skill,
                            "available": "unmeasured",
                            "selected": "observed",
                            "loaded": "observed",
                            "evidence_source": source,
                        }
                    ],
                )

    def test_episode_native_streams_emit_skill_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir)
            episode = trial_dir / "agent" / "episodes" / "002"
            episode.mkdir(parents=True)
            episode.joinpath("codex.jsonl").write_text(
                Path("tests/fixtures/codex-exec-skill.jsonl").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            agent = _agent_to_json(None, str(trial_dir), True)

        self.assertEqual(
            agent["skill_stages"][0]["evidence_source"],
            "codex-jsonl",
        )
        self.assertEqual(agent["skill_stages"][0]["skill"], "yacht-fixture")

    def test_mixed_malformed_and_valid_episode_streams_omit_skill_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir)
            first = trial_dir / "agent" / "episodes" / "001"
            second = trial_dir / "agent" / "episodes" / "002"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            first.joinpath("codex.jsonl").write_text(
                Path("tests/fixtures/codex-exec-skill.jsonl").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            second.joinpath("codex.jsonl").write_text("{not json\n", encoding="utf-8")
            agent = _agent_to_json(None, str(trial_dir), True)

        self.assertNotIn("skill_stages", agent)
        self.assertEqual(agent["tool_calls"], [])

    def test_harness_evidence_skill_name_is_not_claude_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir)
            agent_dir = trial_dir / "agent"
            agent_dir.mkdir(parents=True)
            (agent_dir / "harness-evidence.json").write_text(
                json.dumps(
                    {
                        "schema": "yacht.harness-evidence.v1",
                        "response": "done",
                        "usage": {"input_tokens": 10, "output_tokens": 5},
                        "tool_calls": [{"name": "Skill:team-conventions", "count": 1}],
                    }
                ),
                encoding="utf-8",
            )

            agent = _agent_to_json(None, str(trial_dir), True)

        self.assertEqual(agent["tool_calls"], ["Skill:team-conventions"])
        self.assertEqual(agent["tool_call_evidence"], "harness-evidence")
        self.assertNotIn("skill_stages", agent)

    def test_emitted_skill_stages_validate_on_task_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir)
            sessions = trial_dir / "agent" / "sessions" / "projects" / "-app"
            sessions.mkdir(parents=True)
            (sessions / "session.jsonl").write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Skill",
                                    "input": {"skill": "team-conventions"},
                                }
                            ]
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            agent = _agent_to_json(None, str(trial_dir), True)

        attempt = {
            "schema": "yacht.task-attempt.v1",
            "regatta": "skill-install",
            "course": "tiny-course",
            "comparison": "skill-vs-baseline",
            "vessel": "with-skill",
            "model": "mock",
            "rigging": ["team-conventions-skill"],
            "runtime": "box",
            "status": "completed",
            "task": {"id": "task-1", "title": "Task", "difficulty": 1},
            "runtime_context": {
                "backend": "harbor",
                "harness": "claude-code",
                "temp_home": str(trial_dir),
                "workspace_path": str(trial_dir),
                "command_prefix": [],
                "command": ["harbor", "run"],
                "cleanup_paths": [],
            },
            "prompt": "native",
            "agent": agent,
            "metrics": {"tokens": 1, "duration_seconds": 1.0},
            "secret_refs": [],
        }
        validate_task_attempt_document(attempt)
        self.assertEqual(
            attempt["agent"]["skill_stages"][0]["evidence_source"],
            "claude-code-session-transcript",
        )

    def test_scorecard_counts_selected_as_invoked_when_load_unmeasured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir)
            _write_staged_attempt(
                logbook_dir,
                tool_calls=[],
                skill_stages=[
                    {
                        "skill": "team-conventions",
                        "available": "unmeasured",
                        "selected": "observed",
                        "loaded": "unmeasured",
                        "evidence_source": "claude-code-session-transcript",
                    }
                ],
            )

            scorecard = write_task_attempt_scorecard(logbook_dir)

        invocation = scorecard["comparisons"][0]["vessels"][0]["tool_invocations"][0]
        self.assertEqual(invocation["invoked_attempts"], 1)
        self.assertEqual(
            invocation["skill_stages"],
            {
                "available": {"observed_attempts": 0, "measured_attempts": 0},
                "selected": {"observed_attempts": 1, "measured_attempts": 1},
                "loaded": {"observed_attempts": 0, "measured_attempts": 0},
            },
        )

    def test_reports_render_skill_stage_counts(self) -> None:
        delivery = {
            "vessel": "candidate",
            "status": "delivered",
            "tools": [
                {
                    "tool": "team-conventions",
                    "kind": "agent-skill",
                    "status": "measured",
                    "invoked_attempts": 1,
                    "measured_attempts": 1,
                    "skill_stages": {
                        "available": {
                            "observed_attempts": 0,
                            "measured_attempts": 0,
                        },
                        "selected": {
                            "observed_attempts": 1,
                            "measured_attempts": 1,
                        },
                        "loaded": {
                            "observed_attempts": 0,
                            "measured_attempts": 0,
                        },
                    },
                }
            ],
        }

        # A stage nothing could measure reads as unmeasured, not 0/0:
        # silence and a measured zero are different findings.
        self.assertIn(
            "selected 1/1; loaded unmeasured",
            _delivery_decision(delivery),
        )
        table = _delivery_table(
            {
                "vessels": [
                    {
                        "name": "candidate",
                        "tool_invocations": delivery["tools"],
                    }
                ]
            }
        )
        self.assertIn("selected 1/1", table)
        self.assertIn("loaded unmeasured", table)
        self.assertNotIn("loaded 0/0", table)
        self.assertIn("available unmeasured", table)


def _write_staged_attempt(
    logbook_dir: Path,
    *,
    tool_calls: list[str],
    skill_stages: list[dict[str, str]],
) -> None:
    agent: dict[str, object] = {
        "exit_code": 0,
        "response": "",
        "tool_calls": tool_calls,
        "transcript_path": "/tmp/trial",
        "tool_call_evidence": "claude-code-session-transcript",
        "skill_stages": skill_stages,
    }
    attempt = {
        "schema": "yacht.task-attempt.v1",
        "regatta": "skill-ab",
        "course": "team-conventions-ab",
        "comparison": "skill-vs-baseline",
        "vessel": "candidate",
        "model": "anthropic/claude-haiku-4-5",
        "rigging": ["team-conventions-skill"],
        "runtime": "harbor-claude",
        "status": "completed",
        "task": {"id": "task-1", "title": "Task", "difficulty": 1},
        "runtime_context": {
            "backend": "harbor",
            "harness": "claude-code",
            "temp_home": "/tmp/trial",
            "workspace_path": "/tmp/trial",
            "command_prefix": [],
            "command": ["harbor", "run"],
            "cleanup_paths": [],
        },
        "prompt": "native",
        "agent": agent,
        "metrics": {"tokens": 100, "duration_seconds": 1.0},
        "secret_refs": [],
        "tool_expectations": [
            {
                "tool": "team-conventions",
                "kind": "agent-skill",
                "expected_calls": ["Skill:team-conventions"],
            }
        ],
    }
    validate_task_attempt_document(attempt)
    path = logbook_dir / "task-attempts" / "skill-vs-baseline" / "candidate"
    path.mkdir(parents=True, exist_ok=True)
    (path / "task-1.json").write_text(
        json.dumps(attempt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
