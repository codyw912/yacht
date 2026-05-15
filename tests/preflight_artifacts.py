import json
from pathlib import Path


def write_preflight_artifact(
    *,
    logbook_dir: Path,
    comparison_name: str,
    vessel_name: str,
    status: str,
    include_agent_prompt: bool = False,
) -> None:
    artifact_path = logbook_dir / "preflight" / comparison_name / f"{vessel_name}.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    checks = [
        {
            "name": "runtime-home-isolated",
            "kind": "path-isolation",
            "origin": "runtime",
            "origin_name": "pi",
            "required": True,
            "status": status,
            "evidence": {"paths": {"HOME": f"/tmp/{vessel_name}/home"}},
        }
    ]
    if include_agent_prompt:
        checks.append(
            {
                "name": "fff-headless-smoke",
                "kind": "agent-prompt",
                "origin": "rigging",
                "origin_name": "pi-fff",
                "required": True,
                "status": status,
                "evidence": {
                    "response": {"available": True, "configured": True},
                    "expected_tool_calls": ["fffind"],
                    "tool_calls": ["fffind"],
                    "transcript_path": f"/tmp/{vessel_name}/fff-smoke.json",
                },
            }
        )
    artifact_path.write_text(
        json.dumps(
            {
                "schema": "yacht.preflight.v1",
                "regatta": "pi-fff-comparison",
                "comparison": comparison_name,
                "vessel": vessel_name,
                "runtime": "pi",
                "workspace_path": "/tmp/workspace",
                "temp_home": f"/tmp/{vessel_name}/home",
                "command_prefix": [
                    "nix",
                    "develop",
                    "path:.#pi",
                    "--command",
                ],
                "cleanup_paths": [f"/tmp/{vessel_name}"],
                "status": status,
                "failure_policy": "abort-group",
                "secret_refs": [],
                "checks": checks,
            }
        ),
        encoding="utf-8",
    )
