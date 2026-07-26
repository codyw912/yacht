#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier
reward=0

# The conventions under test (documented in the team skill, not the
# instruction): a tool module defines TOOL_NAME and run(args) -> int,
# and registers its TOOL_NAME in /app/tools/registry.txt.
if python3 - <<'EOF'
import sys

sys.path.insert(0, "/app/tools")
import greet

assert greet.TOOL_NAME == "greet"
assert greet.run([]) == 0

with open("/app/tools/registry.txt", encoding="utf-8") as handle:
    names = [line.strip() for line in handle if line.strip()]
assert "greet" in names
EOF
then
  reward=1
fi

echo "$reward" > /logs/verifier/reward.txt
