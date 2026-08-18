#!/bin/sh
# Same ruff gates as .github/workflows/ci.yml.
set -eu
cd "$(dirname "$0")/.."
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
