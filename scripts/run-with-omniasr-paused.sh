#!/usr/bin/env bash
# Pause the omniasr :8000 server for one HawEdit command, then always bring it back. D-331.
#
# The server holds ~14.6 GB of GPU 1, and HawEdit's Stage 1 now runs on GPU 1 only, so the two
# cannot share the card. The server's watchdog leaves it down while app/MAINTENANCE holds a live
# PID; this wrapper's own PID is that PID for exactly the lifetime of the command. HawEdit itself
# never stops anything: without this wrapper its worker halts honestly on a busy GPU (D-260).
#
# Run it where the omniasr scripts run (inside WSL), e.g.
#   OMNIASR_ROOT=/mnt/c/Users/<you>/Desktop/omniasr-v11-audit \
#     bash scripts/run-with-omniasr-paused.sh <hawedit command...>
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "usage: OMNIASR_ROOT=<omniasr-v11-audit> bash $0 <command> [args...]" >&2
  exit 2
fi
root="${OMNIASR_ROOT:?set OMNIASR_ROOT to the omniasr-v11-audit checkout}"
lock="$root/app/MAINTENANCE"

# noclobber: never take over (or later delete) a lock someone else holds.
if ! (set -o noclobber; printf '%s\n' "$$" > "$lock") 2>/dev/null; then
  echo "REFUSED: $lock already exists ($(cat "$lock" 2>/dev/null || echo unreadable))." >&2
  echo "Another maintenance window is open; not pausing the server twice." >&2
  exit 3
fi

restore() {
  local status=$?
  trap - EXIT
  if [[ "$(cat "$lock" 2>/dev/null)" == "$$" ]]; then
    rm -f "$lock"
  fi
  if ! bash "$root/scripts/restart_server.sh"; then
    echo "WARNING: restart_server.sh failed; the :8000 server may still be down." >&2
    [[ $status -ne 0 ]] || status=4
  fi
  exit "$status"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

bash "$root/scripts/stop_server.sh"
"$@"
