#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
# Presence check only — never echo the key value into trial evidence.
if [ -n "${TYPESAFE_API_KEY:-}" ]; then
  echo "TYPESAFE_API_KEY=SET" > /logs/verifier/probe.txt
else
  echo "TYPESAFE_API_KEY=UNSET" > /logs/verifier/probe.txt
fi
echo 1 > /logs/verifier/reward.txt
