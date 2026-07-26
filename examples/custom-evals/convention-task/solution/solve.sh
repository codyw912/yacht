#!/bin/bash
set -euo pipefail

cat > /app/tools/greet.py <<'EOF'
TOOL_NAME = "greet"


def run(args):
    print("Hello!")
    return 0
EOF

printf 'greet\n' >> /app/tools/registry.txt
