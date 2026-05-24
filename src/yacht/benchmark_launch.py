from yacht.workflows import benchmark_launch as _benchmark_launch
from yacht.workflows.benchmark_launch import *

_run_command = _benchmark_launch._run_command


def write_benchmark_launch_result(*, logbook_dir, command_runner=None):
    return _benchmark_launch.write_benchmark_launch_result(
        logbook_dir=logbook_dir,
        command_runner=command_runner or _run_command,
    )
