"""Live release gate: spend a little, prove the whole path works.

Unit tests cover the pieces; this proves the end-to-end provider path
and the evidence surfaces a release is judged on. It runs the skill A/B
twice — once in full, then once as a candidate against the first run
recorded as a baseline — which is both the cheapest full exercise of
the pipeline and the flagship workflow itself.

    uv run python scripts/release_gate.py

Requires Docker, the pinned launcher image, and ANTHROPIC_API_KEY.
Spends roughly $0.05 at defaults. Re-check a finished gate without
spending again with --skip-live --root <previous root>.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AB_CONFIG = REPO_ROOT / "examples" / "custom-eval-skill-ab-smoke.toml"
LAUNCHER_IMAGE = "yacht/harbor-launcher:harbor-0.20.0"
COMPARISON = "skill-vs-baseline"
BASELINE_VESSEL = "claude-baseline"
CANDIDATE_VESSEL = "claude-with-skill"


class GateFailure(Exception):
    """A gate check failed; the release should not ship."""


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.root or Path(
        f"/private/tmp/yacht-release-gate-{datetime.now():%Y%m%d-%H%M%S}"
    )
    baseline_logbook = root / "baseline"
    candidate_logbook = root / "candidate"
    export_dir = root / "export"

    print(f"release gate root: {root}")
    try:
        if args.skip_live:
            print("skipping live runs (--skip-live)")
        else:
            _preflight_host(args)
            _run_full_ab(baseline_logbook, args)
            _run_against_recorded_baseline(
                baseline_logbook, candidate_logbook, root, args
            )
        _export(candidate_logbook, export_dir)
        _render_reports(candidate_logbook, root)
        checks = _checks(baseline_logbook, candidate_logbook, export_dir, root)
    except GateFailure as error:
        print(f"\nGATE FAILED: {error}")
        return 1
    except subprocess.CalledProcessError as error:
        print(f"\nGATE FAILED: command exited {error.returncode}")
        return 1

    print("\n--- gate checks ---")
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    spend = _total_spend(baseline_logbook, candidate_logbook)
    if spend is not None:
        print(f"\nprovider spend across both runs: ${spend:.4f}")
    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print(f"\nGATE FAILED: {len(failed)} check(s) failed")
        return 1
    print(f"\nGATE PASSED. Artifacts under {root}")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        help="Directory for gate logbooks. Defaults to a timestamped temp dir.",
    )
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="Re-run checks against an existing --root without spending tokens.",
    )
    parser.add_argument(
        "--secret",
        default="anthropic=@env:ANTHROPIC_API_KEY",
        help="Secret binding passed through to yacht run.",
    )
    return parser.parse_args(argv)


def _preflight_host(args: argparse.Namespace) -> None:
    """Fail before spending, not after."""
    env_name = args.secret.split("@env:")[-1] if "@env:" in args.secret else None
    if env_name and not os.environ.get(env_name):
        raise GateFailure(f"{env_name} is not set")
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        raise GateFailure("Docker is not running")
    if (
        subprocess.run(
            ["docker", "image", "inspect", LAUNCHER_IMAGE],
            capture_output=True,
        ).returncode
        != 0
    ):
        raise GateFailure(
            f"launcher image {LAUNCHER_IMAGE} is missing; build it from "
            "containers/harbor-launcher"
        )


def _run_full_ab(logbook: Path, args: argparse.Namespace) -> None:
    print("\n[1/4] full A/B run (both vessels) — this is the baseline")
    _yacht(
        "run",
        str(AB_CONFIG),
        "--logbook",
        str(logbook),
        "--workspace",
        str(REPO_ROOT),
        "--secret",
        args.secret,
    )


def _run_against_recorded_baseline(
    baseline_logbook: Path,
    candidate_logbook: Path,
    root: Path,
    args: argparse.Namespace,
) -> None:
    print("\n[2/4] candidate-only run against the recorded baseline")
    config = _recorded_baseline_config(baseline_logbook, root)
    _yacht(
        "run",
        str(config),
        "--logbook",
        str(candidate_logbook),
        "--workspace",
        str(REPO_ROOT),
        "--secret",
        args.secret,
    )


def _recorded_baseline_config(baseline_logbook: Path, root: Path) -> Path:
    """Derive the regression-check config: one live vessel, one recorded.

    Also absolutizes the dataset path (the derived file lives outside
    examples/) and declares export attribution so the gate can exercise
    the Every Eval Ever export.
    """
    text = AB_CONFIG.read_text(encoding="utf-8")
    dataset = (AB_CONFIG.parent / "custom-evals").resolve()
    text = text.replace('dataset = "custom-evals"', f'dataset = "{dataset}"')
    old_vessels = f'vessels = ["{BASELINE_VESSEL}", "{CANDIDATE_VESSEL}"]'
    if old_vessels not in text:
        raise GateFailure(
            f"{AB_CONFIG.name} no longer declares the expected comparison "
            "vessels; update scripts/release_gate.py"
        )
    text = text.replace(
        old_vessels,
        f'vessels = ["{CANDIDATE_VESSEL}"]\n'
        f'baseline = {{ logbook = "{baseline_logbook.resolve()}", '
        f'vessel = "{BASELINE_VESSEL}" }}',
    )
    text += (
        "\n[export]\n"
        'source_organization_name = "YACHT release gate"\n'
        'evaluator_relationship = "first_party"\n'
    )
    root.mkdir(parents=True, exist_ok=True)
    config = root / "regression-check.toml"
    config.write_text(text, encoding="utf-8")
    return config


def _export(candidate_logbook: Path, export_dir: Path) -> None:
    print("\n[3/4] Every Eval Ever export (no tokens)")
    _yacht(
        "report",
        "--logbook",
        str(candidate_logbook),
        "--format",
        "every-eval-ever",
        "--output",
        str(export_dir),
    )


def _render_reports(candidate_logbook: Path, root: Path) -> None:
    print("\n[4/4] reports (no tokens)")
    for fmt, suffix in (("text", "txt"), ("markdown", "md"), ("html", "html")):
        _yacht(
            "report",
            "--logbook",
            str(candidate_logbook),
            "--format",
            fmt,
            "--output",
            str(root / f"report.{suffix}"),
        )


def _checks(
    baseline_logbook: Path,
    candidate_logbook: Path,
    export_dir: Path,
    root: Path,
) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    baseline = _load(baseline_logbook / "benchmark-scorecard.json")
    candidate = _load(candidate_logbook / "benchmark-scorecard.json")

    comparison = _comparison(baseline)
    measured = [v for v in comparison["vessels"] if v["status"] == "measured"]
    checks.append(
        (
            "full A/B measured both vessels",
            len(measured) == 2,
            f"{len(measured)}/2 measured, status {baseline['status']}",
        )
    )

    attempts = _load(baseline_logbook / "task-attempt-scorecard.json")
    delivery = _delivery_entries(attempts)
    checks.append(
        (
            "skill delivery measured from transcripts (ADR 0019)",
            bool(delivery) and all(e.get("status") == "measured" for e in delivery),
            ", ".join(
                f"{e.get('tool')}={e.get('status')}"
                f"({e.get('invoked_attempts')}/{e.get('measured_attempts')})"
                for e in delivery
            )
            or "no tool_invocations recorded",
        )
    )

    candidate_comparison = _comparison(candidate)
    recorded = [v for v in candidate_comparison["vessels"] if v["status"] == "recorded"]
    run_date = (
        recorded[0].get("baseline_source", {}).get("run_date") if recorded else None
    )
    checks.append(
        (
            "recorded baseline reused without re-running (ADR 0018)",
            len(recorded) == 1 and bool(run_date),
            f"recorded vessels={len(recorded)}, baseline run_date={run_date}",
        )
    )
    live_attempts = candidate_logbook / "task-attempts" / COMPARISON
    ran = (
        sorted(p.name for p in live_attempts.iterdir())
        if live_attempts.is_dir()
        else []
    )
    checks.append(
        (
            "only the live vessel ran",
            ran == [CANDIDATE_VESSEL],
            f"attempt dirs: {ran or 'none'}",
        )
    )

    statistics = candidate_comparison.get("statistics", {})
    checks.append(
        (
            "paired statistics and evidence grade present (ADR 0013)",
            bool(statistics.get("paired", {}).get("grade")),
            str(statistics.get("paired", {}).get("grade")),
        )
    )
    guidance = statistics.get("repetition_guidance")
    checks.append(
        (
            "repetition budget offered (ADR 0021)",
            isinstance(guidance, dict) and bool(guidance.get("plans")),
            f"{len(guidance.get('plans', []))} plans"
            if isinstance(guidance, dict)
            else "absent (expected when evidence was found)",
        )
    )

    exports = sorted(export_dir.glob("*.json")) if export_dir.is_dir() else []
    versions = {_load(path).get("schema_version") for path in exports}
    checks.append(
        (
            "Every Eval Ever export written (ADR 0020)",
            len(exports) == 2 and versions == {"0.2.2"},
            f"{len(exports)} documents, schema {versions or 'none'}",
        )
    )

    html = (
        (root / "report.html").read_text(encoding="utf-8")
        if (root / "report.html").is_file()
        else ""
    )
    markers = {
        "recorded baseline": "recorded baseline from" in html,
        "delivery": "Skill delivery" in html or "treatment" in html,
        "efficiency": "Tokens/res" in html,
    }
    checks.append(
        (
            "HTML report renders the decision metrics",
            all(markers.values()),
            ", ".join(f"{k}={'y' if v else 'n'}" for k, v in markers.items()),
        )
    )
    return checks


def _comparison(scorecard: dict) -> dict:
    for comparison in scorecard["comparisons"]:
        if comparison["name"] == COMPARISON:
            return comparison
    raise GateFailure(f"comparison {COMPARISON} not found in scorecard")


def _delivery_entries(attempts: dict) -> list[dict]:
    return [
        entry
        for comparison in attempts.get("comparisons", [])
        for vessel in comparison.get("vessels", [])
        for entry in vessel.get("tool_invocations", [])
    ]


def _total_spend(*logbooks: Path) -> float | None:
    total = 0.0
    found = False
    for logbook in logbooks:
        path = logbook / "task-attempt-scorecard.json"
        if not path.is_file():
            continue
        cost = _load(path).get("summary", {}).get("total_cost")
        if isinstance(cost, (int, float)):
            total += float(cost)
            found = True
    return total if found else None


def _load(path: Path) -> dict:
    if not path.is_file():
        raise GateFailure(f"expected artifact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _yacht(*args: str) -> None:
    command = ["uv", "run", "yacht", *args]
    print(f"$ {' '.join(command)}")
    subprocess.run(command, cwd=REPO_ROOT, check=True)


if __name__ == "__main__":
    sys.exit(main())
