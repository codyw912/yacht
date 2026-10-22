#!/usr/bin/env bash
# tmux TTY driver for CLI/TUI verification. Copied unchanged into
# .agents/skills/verify-<project>/scripts/lib/ by create-verification-skill.
#
# Each run gets its own tmux server (socket name) so it never touches the
# user's sessions. Evidence is captured with capture-pane into a directory
# the caller names. Nothing here knows the project; the drive script does.
#
# Usage (from a drive script that has `source`d this file):
#   tty_freeze  <evidence-dir> <rubric-file>            # copy rubric + its sha256 into evidence (run BEFORE driving)
#   tty_start   <session> <evidence-dir> <command...>   # start command in a fresh server+session
#   tty_send    <session> <keys...>                     # send keys (tmux send-keys syntax)
#   tty_wait    <session> <regex> [timeout-s]           # wait until pane matches regex (default 30s)
#   tty_capture <session> <label>                       # save pane to <evidence-dir>/<NN>-<label>.txt; safe inside $(...)
#   tty_stop    <session>                               # kill this run's server; evidence stays
#
# Socket name is derived from the session so tty_stop only ever kills ours.
set -euo pipefail

_tty_sock() { printf 'cstack-verify-%s' "$1"; }
# Capture numbering lives in a file under the evidence dir, not a shell
# variable, so tty_capture works inside $(...) and across subshells.
_tty_next_seq() {
  local evidence=$1 f="$1/.seq" n
  n=$(cat "$f" 2>/dev/null || echo 0); n=$((n+1)); printf '%s' "$n" > "$f"; printf '%02d' "$n"
}

tty_freeze() {
  local evidence=$1 rubric=$2
  mkdir -p "$evidence"
  cp "$rubric" "$evidence/rubric.md"
  if command -v sha256sum >/dev/null; then sha256sum "$rubric" | cut -d' ' -f1 > "$evidence/rubric.sha256"
  else shasum -a 256 "$rubric" | cut -d' ' -f1 > "$evidence/rubric.sha256"; fi
}

tty_start() {
  local session=$1 evidence=$2; shift 2
  mkdir -p "$evidence"
  printf '%s\n' "$evidence" > "/tmp/$(_tty_sock "$session").evidence"
  tmux -L "$(_tty_sock "$session")" new-session -d -s "$session" -x 160 -y 48 "$@"
}

tty_send() {
  local session=$1; shift
  tmux -L "$(_tty_sock "$session")" send-keys -t "$session" "$@"
}

tty_wait() {
  local session=$1 pattern=$2 timeout=${3:-30} i=0
  while (( i < timeout * 4 )); do
    if tmux -L "$(_tty_sock "$session")" capture-pane -p -t "$session" 2>/dev/null | grep -Eq -- "$pattern"; then return 0; fi
    sleep 0.25; i=$((i+1))
  done
  echo "tty_wait: pattern not seen within ${timeout}s: $pattern" >&2
  tty_capture "$session" "timeout" >/dev/null || true
  return 1
}

# Wait until a pattern is ABSENT from the pane: the liveness wait. Use it
# for busy indicators ("running", "sending", a spinner) so the drive waits
# for the turn to finish, not for a value the rubric will judge.
tty_wait_gone() {
  local session=$1 pattern=$2 timeout=${3:-30} i=0 pane
  while (( i < timeout * 4 )); do
    # Capture first, then test: a failed capture (dead session, no pane)
    # must not read as "pattern absent" — a crashed TUI is not a finished turn.
    if ! pane=$(tmux -L "$(_tty_sock "$session")" capture-pane -p -t "$session" 2>/dev/null); then
      echo "tty_wait_gone: session $session is not capturable (exited or never started)" >&2
      return 1
    fi
    if ! printf '%s\n' "$pane" | grep -Eq -- "$pattern"; then return 0; fi
    sleep 0.25; i=$((i+1))
  done
  echo "tty_wait_gone: pattern still present after ${timeout}s: $pattern" >&2
  tty_capture "$session" "timeout" >/dev/null || true
  return 1
}

# Wait until the pane has stopped changing for `settle` seconds: the
# liveness wait for states with no busy indicator (a startup frame, a
# stream held by a gate). Fails on a dead session like tty_wait_gone.
tty_wait_quiet() {
  local session=$1 settle=${2:-2} timeout=${3:-30} i=0 prev="" cur quiet=0
  local need=$(( settle * 4 ))
  while (( i < timeout * 4 )); do
    if ! cur=$(tmux -L "$(_tty_sock "$session")" capture-pane -p -t "$session" 2>/dev/null); then
      echo "tty_wait_quiet: session $session is not capturable (exited or never started)" >&2
      return 1
    fi
    if [ -n "$cur" ] && [ "$cur" = "$prev" ]; then quiet=$((quiet+1)); else quiet=0; fi
    if (( quiet >= need )); then return 0; fi
    prev=$cur; sleep 0.25; i=$((i+1))
  done
  echo "tty_wait_quiet: pane still changing after ${timeout}s" >&2
  tty_capture "$session" "timeout" >/dev/null || true
  return 1
}

tty_capture() {
  local session=$1 label=$2
  local evidence; evidence=$(cat "/tmp/$(_tty_sock "$session").evidence")
  local out; out="$evidence/$(_tty_next_seq "$evidence")-$label.txt"
  tmux -L "$(_tty_sock "$session")" capture-pane -p -S -200 -t "$session" > "$out"
  printf '%s\n' "$out"
}

tty_stop() {
  local session=$1 sock; sock=$(_tty_sock "$session")
  tmux -L "$sock" kill-server 2>/dev/null || true
  # tmux leaves the socket file behind; remove it so "is anything running"
  # checks can rely on the file's absence.
  rm -f "/tmp/tmux-$(id -u)/$sock" "/tmp/$sock.evidence"
}
