#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
manifest="$root/tests/omp-control/package.json"
lock="$root/tests/omp-control/package-lock.json"
runtime="$root/.runtime/omp-control"

if [[ ! -f "$lock" ]]; then
  echo "missing deterministic SDK lock: $lock" >&2
  echo "generate it with: npm install --package-lock-only --ignore-scripts --prefix tests/omp-control" >&2
  exit 1
fi

mkdir -p "$runtime"
cp "$manifest" "$runtime/package.json"
cp "$lock" "$runtime/package-lock.json"
npm ci --prefix "$runtime" --no-audit --no-fund

stage_tmp="$(mktemp -d "$runtime/source.tmp.XXXXXX")"
stage="$runtime/source.$$.${RANDOM}"
cleanup() {
  rm -rf "$stage_tmp" "$stage"
}
trap cleanup EXIT
mkdir -p "$stage_tmp/tests/omp-control" "$stage_tmp/containers/harbor-launcher/yacht_harbor_agents"
ln -s "$runtime/node_modules" "$stage_tmp/node_modules"
cp "$root"/tests/omp-control/*.ts "$stage_tmp/tests/omp-control/"
cp "$root"/containers/harbor-launcher/yacht_harbor_agents/*.ts \
  "$stage_tmp/containers/harbor-launcher/yacht_harbor_agents/"
mv "$stage_tmp" "$stage"

bun="$runtime/node_modules/.bin/bun"
"$bun" test --no-install "$stage/tests/omp-control"
YACHT_OMP_BUN="$bun" YACHT_OMP_STAGE_ROOT="$stage" \
  uv run --locked "$root/tests/omp-control/cross_language_test.py"
