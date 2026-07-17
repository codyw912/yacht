from __future__ import annotations

from yacht.cli.commands import doctor
from yacht.cli.commands import inspect
from yacht.cli.commands import internals
from yacht.cli.commands import regatta
from yacht.cli.commands import serve

COMMAND_MODULES = (
    doctor,
    regatta,
    inspect,
    serve,
    internals,
)
