#!/bin/bash
# judge.sh — advisory judge for a custom-eval verifier.
#
# Calls a System One model (TypeSafe Jev, or any OpenAI-compatible substitute)
# with a `state` + typed `questions`, reads the verdict + confidence, applies a
# configurable escalation policy, and writes /logs/verifier/reward.txt plus an
# advisory /logs/verifier/judge.json.
#
# Dependency-free: needs only curl + python3 (or jq) in the task image.
# Config via JUDGE_* env vars (set in task.toml [verifier] env or exported by
# test.sh). See docs/reference/custom-evals.md "Advisory judging".
set -uo pipefail

VERIFIER_DIR="${VERIFIER_DIR:-/logs/verifier}"
mkdir -p "$VERIFIER_DIR"

# --- Config (env overridable) ------------------------------------------------
JUDGE_BACKEND="${JUDGE_BACKEND:-typesafe}"            # typesafe | openai-compat
JUDGE_BASE_URL="${JUDGE_BASE_URL:-https://api.typesafe.ai/v1/systemone}"
JUDGE_MODEL="${JUDGE_MODEL:-jev-latest}"
JUDGE_API_KEY_ENV="${JUDGE_API_KEY_ENV:-TYPESAFE_API_KEY}"
JUDGE_CONFIDENCE_THRESHOLD="${JUDGE_CONFIDENCE_THRESHOLD:-0.5}"
JUDGE_ON_LOW_CONFIDENCE="${JUDGE_ON_LOW_CONFIDENCE:-human-review}" # llm-judge|human-review|advisory-only
JUDGE_MODEL_ESCALATION="${JUDGE_MODEL_ESCALATION:-}"
JUDGE_BASE_URL_ESCALATION="${JUDGE_BASE_URL_ESALATION:-${JUDGE_BASE_URL_ESCALATION:-}}"
JUDGE_API_KEY_ENV_ESCALATION="${JUDGE_API_KEY_ENV_ESCALATION:-OPENAI_API_KEY}"
JUDGE_REQUEST_TIMEOUT_SEC="${JUDGE_REQUEST_TIMEOUT_SEC:-20}"
JUDGE_ON_ERROR="${JUDGE_ON_ERROR:-unresolved}"        # unresolved|zero|advisory-only
JUDGE_STATE_FILE="${JUDGE_STATE_FILE:-}"
JUDGE_QUESTION_FILE="${JUDGE_QUESTION_FILE:-}"

API_KEY="${!JUDGE_API_KEY_ENV:-}"

log() { echo "[judge] $*" >&2; }

write_reward() { # $1 = reward value
  echo "$1" > "$VERIFIER_DIR/reward.txt"
}

write_judge() { # $1 = json body
  echo "$1" > "$VERIFIER_DIR/judge.json"
}

# JSON-escape a file's contents into a string via python3.
json_string_of_file() { # $1 = path
  python3 - "$1" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        print(json.dumps(fh.read()))
except Exception:
    print('""')
PY
}

# --- Build + send the System One request -------------------------------------
# Returns the raw response body on stdout, or nothing on failure.
call_judge() { # $1 = base_url  $2 = api_key  $3 = model  $4 = state_json  $5 = questions_json
  local base_url="$1" key="$2" model="$3" state="$4" questions="$5"
  local body
  if [ "$JUDGE_BACKEND" = "openai-compat" ]; then
    # Map to an OpenAI-compatible /chat/completions call. The question is
    # flattened into a single user message; the verdict is read back from the
    # message content as JSON.
    body=$(python3 - "$model" "$state" "$questions" <<'PY'
import json, sys
model, state, questions = sys.argv[1], sys.argv[2], sys.argv[3]
print(json.dumps({
    "model": model,
    "messages": [
        {"role": "system", "content": "You are an eval judge. Answer the question about the state. Respond with only a JSON object: {\"verdict\": <0..1>, \"confidence\": <0..1>}."},
        {"role": "user", "content": "State:\n" + json.loads(state) + "\n\nQuestion:\n" + questions},
    ],
    "temperature": 0,
}))
PY
)
    curl -sS --max-time "$JUDGE_REQUEST_TIMEOUT_SEC" \
      -H "Authorization: Bearer $key" -H "Content-Type: application/json" \
      -d "$body" "$base_url" 2>/dev/null
    return
  fi
  # typesafe System One shape
  body=$(python3 - "$model" "$state" "$questions" <<'PY'
import json, sys
model, state, questions = sys.argv[1], sys.argv[2], sys.argv[3]
print(json.dumps({
    "model": model,
    "state": json.loads(state),
    "questions": json.loads(questions),
}))
PY
)
  curl -sS --max-time "$JUDGE_REQUEST_TIMEOUT_SEC" \
    -H "Authorization: Bearer $key" -H "Content-Type: application/json" \
    -d "$body" "$base_url" 2>/dev/null
}

# --- Parse the response -------------------------------------------------------
# Prints "<verdict> <confidence> <model>" on stdout, or nothing on parse failure.
parse_response() { # $1 = response body
  python3 - "$1" "$JUDGE_BACKEND" <<'PY'
import json, sys
body, backend = sys.argv[1], sys.argv[2]
try:
    data = json.loads(body)
except Exception:
    sys.exit(1)
model = data.get("model", "")
if backend == "openai-compat":
    try:
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        print(parsed.get("verdict", 0), parsed.get("confidence", 0), model)
        sys.exit(0)
    except Exception:
        sys.exit(1)
answers = data.get("answers", {})
if not answers:
    sys.exit(1)
ans = next(iter(answers.values()))
if ans.get("type") == "noul":
    noul = float(ans.get("noul", 0))
    # Noul carries no confidence field; derive it as distance from 0.5
    # (0.5 = maximally uncertain, 0.0/1.0 = fully confident). Verdict is noul>=0.5.
    confidence = 2 * abs(noul - 0.5)
    print(1 if noul >= 0.5 else 0, confidence, model)
elif ans.get("type") in ("choice", "score"):
    verdict = ans.get("choice") or ans.get("score", 0)
    # map choice/score to 0..1: choice "pass"->1 "fail"->0; score normalized by levels
    if isinstance(verdict, str):
        verdict = 1 if verdict.lower() in ("pass", "yes", "true") else 0
    print(verdict, ans.get("confidence", 0), model)
else:
    sys.exit(1)
PY
}

# --- Main ---------------------------------------------------------------------
if [ -z "$API_KEY" ]; then
  log "no API key in \$$JUDGE_API_KEY_ENV"
  case "$JUDGE_ON_ERROR" in
    zero) write_reward 0 ;;
    advisory-only) : ;;
    *) : ;;  # unresolved: no reward written
  esac
  write_judge '{"error":"no_api_key","backend":"'"$JUDGE_BACKEND"'"}'
  exit 0
fi

if [ -z "$JUDGE_STATE_FILE" ] || [ -z "$JUDGE_QUESTION_FILE" ]; then
  log "JUDGE_STATE_FILE and JUDGE_QUESTION_FILE are required"
  write_judge '{"error":"missing_state_or_question"}'
  [ "$JUDGE_ON_ERROR" = "zero" ] && write_reward 0
  exit 0
fi

STATE_JSON="$(json_string_of_file "$JUDGE_STATE_FILE")"
QUESTIONS_JSON="$(cat "$JUDGE_QUESTION_FILE")"

RESPONSE="$(call_judge "$JUDGE_BASE_URL" "$API_KEY" "$JUDGE_MODEL" "$STATE_JSON" "$QUESTIONS_JSON")"
PARSED="$(parse_response "$RESPONSE")"

if [ -z "$PARSED" ]; then
  log "judge call failed or unparseable"
  case "$JUDGE_ON_ERROR" in
    zero) write_reward 0 ;;
    advisory-only) : ;;
    *) : ;;
  esac
  write_judge '{"error":"call_failed","backend":"'"$JUDGE_BACKEND"'","model":"'"$JUDGE_MODEL"'"}'
  exit 0
fi

read -r VERDICT CONFIDENCE MODEL <<<"$PARSED"

ESCALATED="false"
ESC_VERDICT=""

# Escalation: low confidence -> configured path.
LOW=$(python3 -c "print(1 if float('$CONFIDENCE') < float('$JUDGE_CONFIDENCE_THRESHOLD') else 0)")
if [ "$LOW" = "1" ]; then
  case "$JUDGE_ON_LOW_CONFIDENCE" in
    llm-judge)
      ESCALATED="true"
      ESC_KEY="${!JUDGE_API_KEY_ENV_ESCALATION:-}"
      ESC_RESP="$(call_judge "${JUDGE_BASE_URL_ESCALATION:-$JUDGE_BASE_URL}" "$ESC_KEY" "${JUDGE_MODEL_ESCALATION:-$JUDGE_MODEL}" "$STATE_JSON" "$QUESTIONS_JSON")"
      ESC_PARSED="$(parse_response "$ESC_RESP")"
      if [ -n "$ESC_PARSED" ]; then
        read -r ESC_VERDICT _ _ESC_MODEL <<<"$ESC_PARSED"
        VERDICT="$ESC_VERDICT"  # escalation verdict decides
      fi
      ;;
    human-review)
      ESCALATED="true"
      VERDICT=""   # leave unresolved
      ;;
    advisory-only)
      : ;;  # record but don't decide
  esac
fi

# Write reward: verdict >= 0.5 -> 1 else 0; empty verdict -> unresolved.
if [ -n "$VERDICT" ] && [ "$JUDGE_ON_LOW_CONFIDENCE" != "advisory-only" ]; then
  R=$(python3 -c "print(1 if float('$VERDICT') >= 0.5 else 0)")
  write_reward "$R"
elif [ "$JUDGE_ON_ERROR" = "zero" ]; then
  write_reward 0
fi

write_judge "$(python3 - "$JUDGE_BACKEND" "$MODEL" "$VERDICT" "$CONFIDENCE" "$ESCALATED" "$ESC_VERDICT" <<'PY'
import json, sys
backend, model, verdict, confidence, escalated, esc = sys.argv[1:7]
print(json.dumps({
    "backend": backend,
    "model": model,
    "verdict": float(verdict) if verdict else None,
    "confidence": float(confidence) if confidence else None,
    "escalated": escalated == "true",
    "escalation_verdict": float(esc) if esc else None,
}))
PY
)"
exit 0
