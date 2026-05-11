from pathlib import Path

from tests.preflight_artifacts import write_preflight_artifact
from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.runtime_instances import write_runtime_instances_plan
from yacht.swebench_predictions import write_swe_bench_predictions


PI_FFF_CONFIG_PATH = Path("examples/pi-fff-provisioning.toml")
PI_BASELINE_PREDICTIONS_PATH = Path("examples/pi-baseline-predictions.json")
PI_FFF_PREDICTIONS_PATH = Path("examples/pi-fff-predictions.json")


def write_pi_fff_config(path: Path) -> None:
    path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")


def write_vessel_candidate(
    *,
    config_path: Path,
    logbook_dir: Path,
    vessel_name: str,
) -> None:
    write_swe_bench_predictions(
        config_path=config_path,
        predictions_path=_predictions_path(vessel_name),
        logbook_dir=logbook_dir,
        vessel_name=vessel_name,
    )


def write_vessel_preflight(
    *,
    logbook_dir: Path,
    vessel_name: str,
    status: str = "passed",
) -> None:
    write_preflight_artifact(
        logbook_dir=logbook_dir,
        comparison_name="pi-vs-pi-fff",
        vessel_name=vessel_name,
        status=status,
    )


def write_runtime_snapshot(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
) -> None:
    write_runtime_instances_plan(
        config_path=config_path,
        logbook_dir=logbook_dir,
        workspace_path=workspace_path,
    )


def write_vessel_ready_inputs(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    vessel_name: str,
) -> None:
    write_vessel_candidate(
        config_path=config_path,
        logbook_dir=logbook_dir,
        vessel_name=vessel_name,
    )
    write_runtime_snapshot(
        config_path=config_path,
        logbook_dir=logbook_dir,
        workspace_path=workspace_path,
    )
    write_vessel_preflight(logbook_dir=logbook_dir, vessel_name=vessel_name)


def _predictions_path(vessel_name: str) -> Path:
    if vessel_name == "pi-baseline":
        return PI_BASELINE_PREDICTIONS_PATH
    if vessel_name == "pi-plus-fff":
        return PI_FFF_PREDICTIONS_PATH
    raise ValueError(f"unsupported fixture vessel {vessel_name}")
