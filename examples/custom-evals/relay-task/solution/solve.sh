#!/bin/bash
set -euo pipefail
mkdir -p /app
echo "decision: greeting lives in /app/greeting.txt" > /app/NOTES.md
echo "Hello again from YACHT!" > /app/greeting.txt
