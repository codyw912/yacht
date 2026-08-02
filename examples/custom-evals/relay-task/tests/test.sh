#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier

if [ "$(cat /app/greeting.txt 2>/dev/null)" = "Hello again from YACHT!" ] \
    && [ -s /app/NOTES.md ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
