"""The committed SecretSpec manifest: shape, and scopes under a dummy provider.

These tests never contact a real provider. The scope assertions run
SecretSpec against its `env` provider with dummy sentinels and an
isolated HOME, so no global operator configuration (1Password or
otherwise) can be reached.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "secretspec.toml"

ANTHROPIC_SENTINEL = "yacht-dummy-anthropic-DO-NOT-USE-6b21df"
OPENAI_SENTINEL = "yacht-dummy-openai-DO-NOT-USE-71e4ac"

SECRETSPEC = shutil.which("secretspec")


class SecretSpecManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = tomllib.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_declares_the_documented_project_and_secrets(self) -> None:
        self.assertEqual(self.manifest["project"]["name"], "yacht")
        self.assertEqual(self.manifest["project"]["revision"], "1.0")
        self.assertEqual(
            sorted(self.manifest["profiles"]["default"]),
            ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
        )
        self.assertEqual(
            self.manifest["scopes"],
            {
                "anthropic": {"secrets": ["ANTHROPIC_API_KEY"]},
                "openai": {"secrets": ["OPENAI_API_KEY"]},
            },
        )

    def test_manifest_commits_no_provider_or_vault_coordinates(self) -> None:
        text = MANIFEST_PATH.read_text(encoding="utf-8").lower()
        # No provider URI of any scheme, in a declaration or a comment.
        self.assertNotIn("://", text)
        # Coordinates: check declarations only — the header comment names
        # these very words to say where they belong instead.
        declarations = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        for forbidden in ("vault", "item =", "field =", "ref =", "refs"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, declarations)
        # No provider selection is committed anywhere in the manifest.
        self.assertNotIn("provider", self.manifest)
        self.assertNotIn("providers", self.manifest)

    def test_local_provider_overlay_is_gitignored(self) -> None:
        # Provider coordinates belong in secretspec.local.toml, which must
        # never become committable by accident.
        ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

        self.assertIn("/secretspec.local.toml", ignored)


# The scoped child never prints a value, not even a dummy one: it reports
# a SHA-256 digest per declared variable, and the parent compares digests.
# That keeps the sentinels out of captured command output, which is the
# habit docs/reference/secrets.md asks of humans and agents alike.
PROBE = """
import hashlib, json, os


def probe(name):
    value = os.environ.get(name)
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


print(json.dumps({name: probe(name) for name in
                  ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}))
"""


@unittest.skipUnless(SECRETSPEC, "secretspec is not installed")
class SecretSpecScopeTests(unittest.TestCase):
    def test_each_scope_exposes_only_its_own_secret(self) -> None:
        for scope, expected, hidden in (
            ("anthropic", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"),
            ("openai", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"),
        ):
            with self.subTest(scope=scope):
                stdout, stderr = _run_scope(scope)
                digests = json.loads(stdout)

                self.assertEqual(digests[expected], _digest(_sentinel(expected)))
                # An out-of-scope secret is gone, not merely empty: the
                # parent exported it and the scope removed it.
                self.assertIsNone(digests[hidden])
                for sentinel in (ANTHROPIC_SENTINEL, OPENAI_SENTINEL):
                    self.assertNotIn(sentinel, stdout)
                    self.assertNotIn(sentinel, stderr)


def _sentinel(variable: str) -> str:
    return ANTHROPIC_SENTINEL if variable == "ANTHROPIC_API_KEY" else OPENAI_SENTINEL


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _run_scope(scope: str) -> tuple[str, str]:
    assert SECRETSPEC is not None
    with tempfile.TemporaryDirectory() as home:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            # An isolated HOME keeps any operator-global provider
            # configuration (1Password included) out of reach.
            "HOME": home,
            "ANTHROPIC_API_KEY": ANTHROPIC_SENTINEL,
            "OPENAI_API_KEY": OPENAI_SENTINEL,
        }
        completed = subprocess.run(
            [
                SECRETSPEC,
                "--file",
                str(MANIFEST_PATH),
                "run",
                "--provider",
                "env",
                "--profile",
                "default",
                "--scope",
                scope,
                "--reason",
                "yacht automated test (dummy env provider)",
                "--",
                sys.executable,
                "-c",
                PROBE,
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    if completed.returncode != 0:
        raise AssertionError(
            f"secretspec run --scope {scope} failed ({completed.returncode}): "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout, completed.stderr


if __name__ == "__main__":
    unittest.main()
