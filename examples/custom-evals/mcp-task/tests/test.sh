#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier
reward=0

expected=$'alpha.txt\nbeta.txt\ngamma.txt'
if [ -f /app/inventory.txt ] && [ "$(cat /app/inventory.txt)" = "$expected" ]; then
  reward=1
fi

echo "$reward" > /logs/verifier/reward.txt
