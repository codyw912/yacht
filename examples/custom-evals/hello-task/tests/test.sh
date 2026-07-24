#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier

if [ "$(cat /app/greeting.txt 2>/dev/null)" = "Hello from YACHT!" ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
