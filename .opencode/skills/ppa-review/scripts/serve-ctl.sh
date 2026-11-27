#!/usr/bin/env bash
# serve-ctl.sh — control the Markdown server (backs the "/serve ..." commands).
#
#   ./serve-ctl.sh start            # start with the last-used (or default) file
#   ./serve-ctl.sh stop             # stop the server
#   ./serve-ctl.sh restart          # restart with the current file
#   ./serve-ctl.sh status           # show whether it is running
#   ./serve-ctl.sh <path/to/file.md> # switch to that file (repo-root-relative
#                                     # or absolute) and (re)start
#
# This script lives at <repo-root>/.opencode/skills/ppa-review/scripts/ -- it
# walks up to the repo root so it works regardless of where it's invoked from,
# and so the whole ppa-review/ skill folder stays relocatable as a unit.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
VAR_DIR="$REPO_ROOT/var"
PIDFILE="$VAR_DIR/.serve.pid"
FILEPTR="$VAR_DIR/.serve.file"
LOG="/tmp/debpr-serve.log"
DEFAULT="docs/Package-Review-Guidelines.md"  # relative to REPO_ROOT

current_file() { [ -f "$FILEPTR" ] && cat "$FILEPTR" || echo "$DEFAULT"; }

is_running() { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }

start() {
  if is_running; then echo "already running (pid $(cat "$PIDFILE"))"; return; fi
  local f; f="$(current_file)"
  [ -f "$REPO_ROOT/$f" ] || { echo "file not found: $f"; exit 1; }
  mkdir -p "$VAR_DIR"
  rm -f "$PIDFILE"
  # serve.py writes its own PID to $PIDFILE on startup, so we never have to guess
  # which process is the server (pgrep would also match this launcher).
  setsid bash -c "exec python3 '$SCRIPT_DIR/serve.py' '$REPO_ROOT/$f' >'$LOG' 2>&1 </dev/null" &
  for _ in $(seq 1 25); do is_running && break; sleep 0.2; done
  is_running && echo "started (pid $(cat "$PIDFILE")) serving $f" \
    || { echo "failed to start; see $LOG"; exit 1; }
}

stop() {
  if is_running; then kill "$(cat "$PIDFILE")" && echo "stopped"; else echo "not running"; fi
  rm -f "$PIDFILE"
}

status() {
  if is_running; then echo "running (pid $(cat "$PIDFILE")) serving $(current_file)";
  else echo "stopped"; fi
}

case "${1:-status}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop || true; start ;;
  status)  status ;;
  *.md)    echo "$1" > "$FILEPTR"; stop || true; start ;;
  *)       echo "usage: $0 {start|stop|restart|status|<path/to/file.md>}"; exit 2 ;;
esac
