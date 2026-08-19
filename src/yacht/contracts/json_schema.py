from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError, best_match
from jsonschema.protocols import Validator

_SCHEMA_PACKAGE = "yacht.schemas"
_SCHEMA_SUFFIX = ".schema.json"


@cache
def schema_text(schema_name: str) -> str:
    """Return the canonical packaged JSON Schema text."""
    return (
        files(_SCHEMA_PACKAGE)
        .joinpath(f"{schema_name}{_SCHEMA_SUFFIX}")
        .read_text(encoding="utf-8")
    )


@cache
def _validator(schema_name: str) -> Validator:
    try:
        schema = json.loads(schema_text(schema_name))
        Draft202012Validator.check_schema(schema)
    except (json.JSONDecodeError, SchemaError) as error:
        raise RuntimeError(
            f"packaged JSON Schema {schema_name} is invalid: {error}"
        ) from error
    if not isinstance(schema, dict):
        raise RuntimeError(f"packaged JSON Schema {schema_name} must be an object")
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validation_error(document: Any, schema_name: str) -> ValidationError | None:
    """Return the most relevant structural contract error, if any."""
    return best_match(_validator(schema_name).iter_errors(document))
