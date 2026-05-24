from yacht.preflight import execution as _execution
from yacht.preflight.execution import *

_run_command = _execution._run_command


def execute_machine_preflight(
    *,
    regatta,
    vessel,
    instance,
    artifact_path,
    comparison=None,
    command_runner=None,
):
    return _execution.execute_machine_preflight(
        regatta=regatta,
        vessel=vessel,
        instance=instance,
        artifact_path=artifact_path,
        comparison=comparison,
        command_runner=command_runner or _run_command,
    )


def execute_preflight(
    *,
    regatta,
    vessel,
    instance,
    artifact_path,
    comparison=None,
    command_runner=None,
    agent_prompt_runner=None,
):
    return _execution.execute_preflight(
        regatta=regatta,
        vessel=vessel,
        instance=instance,
        artifact_path=artifact_path,
        comparison=comparison,
        command_runner=command_runner or _run_command,
        agent_prompt_runner=agent_prompt_runner,
    )
