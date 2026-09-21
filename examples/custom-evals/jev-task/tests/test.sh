#!/bin/bash
# test.sh — verifier for the jev-task example. Reads the judge config from
# JUDGE_* env vars (set in task.toml [verifier] env — the only channel that
# reaches tests/test.sh; task.toml itself is a sensitive file not mounted into
# the container), then calls the advisory judge on the agent's output.
set -uo pipefail

mkdir -p /logs/verifier

# The agent's output under test.
export JUDGE_STATE_FILE=/app/output.txt

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

# JUDGE_* vars arrive via [verifier] env in task.toml. Defaults apply for any
# the task didn't set.
export JUDGE_BACKEND="${JUDGE_BACKEND:-typesafe}"
export JUDGE_MODEL="${JUDGE_MODEL:-jev-latest}"
export JUDGE_API_KEY_ENV="${JUDGE_API_KEY_ENV:-TYPESAFE_API_KEY}"
export JUDGE_ON_LOW_CONFIDENCE="${JUDGE_ON_LOW_CONFIDENCE:-human-review}"
export JUDGE_ON_ERROR="${JUDGE_ON_ERROR:-unresolved}"

/tests/judge.sh
