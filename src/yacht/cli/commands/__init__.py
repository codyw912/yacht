from __future__ import annotations

from yacht.cli.commands import artifacts
from yacht.cli.commands import attempts
from yacht.cli.commands import benchmark
from yacht.cli.commands import doctor
from yacht.cli.commands import preflight
from yacht.cli.commands import real_benchmark
from yacht.cli.commands import regatta
from yacht.cli.commands import runtimes
from yacht.cli.commands import smoke

COMMAND_MODULES = (
    doctor,
    regatta,
    runtimes,
    artifacts,
    benchmark,
    preflight,
    attempts,
    smoke,
    real_benchmark,
)
