"""Auxiliary skill resources: layout, path checks, and payload digest.

A skill that references other files is only delivered if those files ship
with it. The payload digest pins what Yacht rendered, so a change in any
file of the bundle is visible in the artifact.
"""

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

from tests.test_skill_install import SKILL_BODY, _skill_config
from yacht.courses.terminal_bench.job import render_terminal_bench_job
from yacht.domain.model import ConfigError, load_regatta
from yacht.harnesses.skill_config import render_skill_installs
from yacht.runtimes.rigging_setup import plan_rigging_setup

CHECKLIST = "# Checklist\n- one\n"
TEMPLATE = "## Template\nbody\n"


def _load_harbor_rigging_module():
    module_path = (
        Path(__file__).resolve().parent.parent
        / "containers/harbor-launcher/yacht_harbor_agents/rigging.py"
    )
    spec = importlib.util.spec_from_file_location(
        "yacht_harbor_agents_rigging_resources", module_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_body(resources: str = "", *, content: str = SKILL_BODY) -> str:
    return (
        'method = "skill"\n'
        'target = "team-conventions"\n'
        f'content = """{content}"""\n' + resources
    )


def _two_resources() -> str:
    return (
        "resources = [\n"
        f'  {{ path = "reference/checklist.md", content = """{CHECKLIST}""" }},\n'
        f'  {{ path = "templates/pr.md", content = """{TEMPLATE}""" }},\n'
        "]\n"
    )


def _regatta(root: Path, install_body: str, **kwargs):
    config_path = root / "regatta.toml"
    config_path.write_text(_skill_config(install_body, **kwargs), encoding="utf-8")
    return load_regatta(config_path)


def _steps(regatta):
    rigging = regatta.rigging_recipes["team-conventions-skill"]
    return tuple(("team-conventions-skill", step) for step in rigging.install)


def _expected_digest(*entries: tuple[str, str]) -> str:
    digest = hashlib.sha256()
    for relative_path, content in sorted(entries):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(content.encode("utf-8"))
        digest.update(b"\x00")
    return f"sha256:{digest.hexdigest()}"


class SkillResourceRenderTests(unittest.TestCase):
    def test_renders_every_resource_under_each_harness_layout(self) -> None:
        for harness, base in (
            ("claude-code", ".claude/skills/team-conventions"),
            ("omp", ".agents/skills/team-conventions"),
            ("codex", ".agents/skills/team-conventions"),
        ):
            with self.subTest(harness=harness), tempfile.TemporaryDirectory() as tmp:
                regatta = _regatta(
                    Path(tmp), _install_body(_two_resources()), harness=harness
                )

                renders = render_skill_installs(harness, _steps(regatta))

                self.assertEqual(len(renders), 1)
                render = renders[0]
                self.assertEqual(render.target, f"{base}/SKILL.md")
                self.assertEqual(
                    [
                        (resource.target, resource.content)
                        for resource in render.resources
                    ],
                    [
                        (f"{base}/reference/checklist.md", CHECKLIST),
                        (f"{base}/templates/pr.md", TEMPLATE),
                    ],
                )

    def test_digest_is_the_logical_payload_not_the_rendered_paths(self) -> None:
        # The same skill must carry the same digest on every harness:
        # .claude/skills/... and .agents/skills/... are the same bundle.
        digests = set()
        for harness in ("claude-code", "omp", "codex"):
            with tempfile.TemporaryDirectory() as tmp:
                regatta = _regatta(
                    Path(tmp), _install_body(_two_resources()), harness=harness
                )
                renders = render_skill_installs(harness, _steps(regatta))
                digests.add(renders[0].content_digest)

        self.assertEqual(
            digests,
            {
                _expected_digest(
                    ("SKILL.md", SKILL_BODY),
                    ("reference/checklist.md", CHECKLIST),
                    ("templates/pr.md", TEMPLATE),
                )
            },
        )

    def test_digest_is_stable_across_renders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            regatta = _regatta(Path(tmp), _install_body(_two_resources()))
            steps = _steps(regatta)

            first = render_skill_installs("claude-code", steps)[0].content_digest
            second = render_skill_installs("claude-code", steps)[0].content_digest

        self.assertEqual(first, second)

    def test_digest_changes_when_a_resource_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before = render_skill_installs(
                "claude-code",
                _steps(_regatta(Path(tmp), _install_body(_two_resources()))),
            )[0].content_digest

        changed = _two_resources().replace("- one", "- one\n- two")
        with tempfile.TemporaryDirectory() as tmp:
            after = render_skill_installs(
                "claude-code",
                _steps(_regatta(Path(tmp), _install_body(changed))),
            )[0].content_digest

        self.assertNotEqual(before, after)

    def test_resource_free_skill_renders_one_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            regatta = _regatta(Path(tmp), _install_body())

            render = render_skill_installs("claude-code", _steps(regatta))[0]

            self.assertEqual(render.resources, ())
            self.assertEqual(
                render.content_digest, _expected_digest(("SKILL.md", SKILL_BODY))
            )


class SkillResourceLoaderTests(unittest.TestCase):
    def test_reads_a_resource_from_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "checklist.md").write_text(CHECKLIST, encoding="utf-8")
            resources = (
                "resources = [\n"
                '  { path = "reference/checklist.md", source = "checklist.md" },\n'
                "]\n"
            )

            regatta = _regatta(root, _install_body(resources))

            step = regatta.rigging_recipes["team-conventions-skill"].install[0]
            self.assertEqual(step.resources[0].path, "reference/checklist.md")
            self.assertEqual(step.resources[0].content, CHECKLIST)

    def test_rejects_an_absolute_resource_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resources = 'resources = [{ path = "/etc/passwd", content = "x" }]\n'

            # The document validator fires before the parser and names the
            # rigging and install index; that is the message users see.
            with self.assertRaisesRegex(
                ConfigError,
                r"install\[0\].resources\[0\].path must be relative",
            ):
                _regatta(Path(tmp), _install_body(resources))

    def test_rejects_a_traversing_resource_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resources = 'resources = [{ path = "../escape.md", content = "x" }]\n'

            with self.assertRaisesRegex(
                ConfigError,
                r"must not contain '\.\.'",
            ):
                _regatta(Path(tmp), _install_body(resources))

    def test_rejects_an_empty_resource_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resources = 'resources = [{ path = "", content = "x" }]\n'

            with self.assertRaisesRegex(
                ConfigError,
                r"install\[0\].resources\[0\].path must be a non-empty string",
            ):
                _regatta(Path(tmp), _install_body(resources))

    def test_rejects_a_resource_without_content_or_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resources = 'resources = [{ path = "reference/checklist.md" }]\n'

            with self.assertRaisesRegex(
                ConfigError,
                r"resources\[0\] must define exactly one of content or source",
            ):
                _regatta(Path(tmp), _install_body(resources))

    def test_rejects_a_resource_claiming_the_skill_body_filename(self) -> None:
        # The host writer emits SKILL.md first and the Harbor lowering emits
        # it last, so a collision would build two different trees from one
        # digest depending on which path ran.
        for path in ("SKILL.md", "./SKILL.md"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as tmp:
                resources = f'resources = [{{ path = "{path}", content = "x" }}]\n'

                with self.assertRaisesRegex(ConfigError, "reserved for the skill body"):
                    _regatta(Path(tmp), _install_body(resources))

    def test_rejects_two_resources_naming_one_file(self) -> None:
        for first, second in (
            ("reference/checklist.md", "reference/checklist.md"),
            ("reference/checklist.md", "./reference/checklist.md"),
            ("reference/checklist.md", "reference/./checklist.md"),
        ):
            with self.subTest(second=second), tempfile.TemporaryDirectory() as tmp:
                resources = (
                    "resources = [\n"
                    f'  {{ path = "{first}", content = "a" }},\n'
                    f'  {{ path = "{second}", content = "b" }},\n'
                    "]\n"
                )

                with self.assertRaisesRegex(ConfigError, "both name"):
                    _regatta(Path(tmp), _install_body(resources))

    def test_rejects_a_resource_path_naming_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resources = 'resources = [{ path = ".", content = "x" }]\n'

            with self.assertRaisesRegex(ConfigError, "names no file"):
                _regatta(Path(tmp), _install_body(resources))

    def test_normalizes_a_dot_slash_path_before_writing_and_hashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resources = (
                'resources = [{ path = "./reference/checklist.md", '
                f'content = """{CHECKLIST}""" }}]\n'
            )
            regatta = _regatta(Path(tmp), _install_body(resources))

            render = render_skill_installs("claude-code", _steps(regatta))[0]

            self.assertEqual(
                render.resources[0].target,
                ".claude/skills/team-conventions/reference/checklist.md",
            )
            self.assertEqual(
                render.content_digest,
                _expected_digest(
                    ("SKILL.md", SKILL_BODY),
                    ("reference/checklist.md", CHECKLIST),
                ),
            )

    def test_rejects_resources_on_a_non_skill_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            body = (
                'method = "config-file"\n'
                'target = ".config/thing.json"\n'
                'content = "{}"\n'
                'resources = [{ path = "extra.md", content = "x" }]\n'
            )

            with self.assertRaisesRegex(ConfigError, "only valid for skill installs"):
                _regatta(Path(tmp), body)


class SkillResourceDeliveryTests(unittest.TestCase):
    def test_host_setup_plans_every_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            regatta = _regatta(Path(tmp), _install_body(_two_resources()))

            plan = plan_rigging_setup(
                runtime=regatta.runtime_recipes["box"],
                riggings=(regatta.rigging_recipes["team-conventions-skill"],),
                command_prefix=(),
                tool_capabilities=regatta.tool_capabilities,
            )

            self.assertEqual(
                [(file.target, file.content) for file in plan.files],
                [
                    (".claude/skills/team-conventions/SKILL.md", SKILL_BODY),
                    (
                        ".claude/skills/team-conventions/reference/checklist.md",
                        CHECKLIST,
                    ),
                    (".claude/skills/team-conventions/templates/pr.md", TEMPLATE),
                ],
            )

    def test_harbor_job_lowers_every_file_and_pins_the_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            regatta = _regatta(
                Path(tmp),
                _install_body(_two_resources()),
                backend="harbor",
                harness="omp",
            )

            job = render_terminal_bench_job(regatta=regatta, vessel_name="with-skill")

            steps = job["agent"]["rigging_steps"]
            self.assertEqual(
                [step["target"] for step in steps],
                [
                    ".agents/skills/team-conventions/reference/checklist.md",
                    ".agents/skills/team-conventions/templates/pr.md",
                    ".agents/skills/team-conventions/SKILL.md",
                ],
            )
            self.assertTrue(all(step["method"] == "config-file" for step in steps))
            self.assertEqual(
                steps[-1]["content_digest"],
                _expected_digest(
                    ("SKILL.md", SKILL_BODY),
                    ("reference/checklist.md", CHECKLIST),
                    ("templates/pr.md", TEMPLATE),
                ),
            )

    def test_lowered_commands_assume_no_hashing_tool_in_the_task_image(self) -> None:
        # These commands run through environment.exec in the author's task
        # container. Verifying the digest there would need a tool the image
        # is not obliged to have, so the digest is a pin, not a check.
        rigging = _load_harbor_rigging_module()
        with tempfile.TemporaryDirectory() as tmp:
            regatta = _regatta(
                Path(tmp),
                _install_body(_two_resources()),
                backend="harbor",
                harness="omp",
            )
            job = render_terminal_bench_job(regatta=regatta, vessel_name="with-skill")

            commands = rigging.rigging_commands(job["agent"]["rigging_steps"])

            self.assertEqual(len(commands), 3)
            for command in commands:
                with self.subTest(command=command):
                    for tool in ("node ", "python3", "sha256sum", "shasum", "openssl"):
                        self.assertNotIn(tool, command)


if __name__ == "__main__":
    unittest.main()
