#!/usr/bin/env python3
"""Stage the Harbor launcher image build context.

Copies this directory into --output and writes
yacht_harbor_agents/execution_contract.py from the canonical
src/yacht/_execution_contract.py. Never reuses a stale in-tree copy.

Invocation (from the yacht repository root):

  python containers/harbor-launcher/prepare_context.py \\
      --output /tmp/harbor-launcher-context
  docker build -f /tmp/harbor-launcher-context/Dockerfile \\
      /tmp/harbor-launcher-context
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

LAUNCHER_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAUNCHER_DIR.parent.parent
CANONICAL_CONTRACT = REPO_ROOT / "src" / "yacht" / "_execution_contract.py"
STAGED_CONTRACT = Path("yacht_harbor_agents") / "execution_contract.py"
STAGING_MARKER = ".yacht-launcher-staging"


def stage(output: Path) -> None:
    if not CANONICAL_CONTRACT.is_file():
        raise SystemExit(f"canonical validator missing: {CANONICAL_CONTRACT}")
    if output == LAUNCHER_DIR or output == REPO_ROOT:
        raise SystemExit(f"refusing to stage into a source path: {output}")
    for parent in (LAUNCHER_DIR, REPO_ROOT):
        if parent == output or parent in output.parents or output in parent.parents:
            raise SystemExit(f"refusing to stage into a source path: {output}")
    if output.exists():
        if not (output / STAGING_MARKER).is_file():
            raise SystemExit(
                f"{output} exists and is not a yacht staging directory; "
                f"remove it or pass a fresh --output"
            )
        shutil.rmtree(output)
    shutil.copytree(
        LAUNCHER_DIR,
        output,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".*.swp"),
    )
    (output / STAGING_MARKER).write_text("yacht launcher staging\n", encoding="utf-8")
    destination = output / STAGED_CONTRACT
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CANONICAL_CONTRACT, destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    stage(args.output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
