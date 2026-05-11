import json
from pathlib import Path


def write_preflight_artifact(
    *,
    logbook_dir: Path,
    comparison_name: str,
    vessel_name: str,
    status: str,
) -> None:
    artifact_path = logbook_dir / "preflight" / comparison_name / f"{vessel_name}.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
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
                    "github:example/yacht-runtimes#pi",
                    "--command",
                ],
                "cleanup_paths": [f"/tmp/{vessel_name}"],
                "status": status,
                "failure_policy": "abort-group",
                "secret_refs": [],
                "checks": [
                    {
                        "name": "runtime-home-isolated",
                        "kind": "path-isolation",
                        "origin": "runtime",
                        "origin_name": "pi",
                        "required": True,
                        "status": status,
                        "evidence": {"paths": {"HOME": f"/tmp/{vessel_name}/home"}},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
