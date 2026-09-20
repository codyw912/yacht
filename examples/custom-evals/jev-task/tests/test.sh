#!/bin/bash
# test.sh — verifier for the jev-task example. Calls the advisory judge on the
# agent's output and writes reward + judge.json.
set -uo pipefail

mkdir -p /logs/verifier

# The agent's output under test.
JUDGE_STATE_FILE=/app/output.txt
export JUDGE_STATE_FILE

# The question the judge answers about the state. Noul = clean yes/no verdict.
cat > /tmp/judge-question.json <<'EOF'
{
  "output_ok": {
    "type": "noul",
    "instructions": "Does the output file contain a substantive, non-empty result that addresses the task?",
    "criteria": {
      "true": "The output is present, non-empty, and on-topic",
      "false": "The output is missing, empty, or off-topic"
    }
  }
}
EOF
export JUDGE_QUESTION_FILE=/tmp/judge-question.json

# Config — the API key arrives via [verifier] env (required_secrets does NOT
# reach the verifier; see the jev-probe-task result).
export JUDGE_BACKEND="${JUDGE_BACKEND:-typesafe}"
export JUDGE_MODEL="${JUDGE_MODEL:-jev-latest}"
export JUDGE_API_KEY_ENV="${JUDGE_API_KEY_ENV:-TYPESAFE_API_KEY}"
export JUDGE_ON_LOW_CONFIDENCE="${JUDGE_ON_LOW_CONFIDENCE:-human-review}"
export JUDGE_ON_ERROR="${JUDGE_ON_ERROR:-unresolved}"

/tests/judge.sh
