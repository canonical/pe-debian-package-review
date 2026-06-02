#!/usr/bin/env bash
# serve-ctl.sh — control the Markdown server (backs the "/serve ..." commands).
#
#   ./serve-ctl.sh start            # start with the last-used (or default) file
#   ./serve-ctl.sh stop             # stop the server
#   ./serve-ctl.sh restart          # restart with the current file
#   ./serve-ctl.sh status           # show whether it is running
#   ./serve-ctl.sh <file.md>        # switch to <file.md> and (re)start
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$DIR/.serve.pid"
FILEPTR="$DIR/.serve.file"
LOG="/tmp/debpr-serve.log"
DEFAULT="Package-Review-Guide_README.md"

current_file() { [ -f "$FILEPTR" ] && cat "$FILEPTR" || echo "$DEFAULT"; }

is_running() { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }

start() {
  if is_running; then echo "already running (pid $(cat "$PIDFILE"))"; return; fi
  local f; f="$(current_file)"
  [ -f "$DIR/$f" ] || { echo "file not found: $f"; exit 1; }
  setsid bash -c "exec python3 '$DIR/serve.py' '$f' >'$LOG' 2>&1 </dev/null" &
  sleep 1
  pgrep -f "[s]erve.py" | head -1 > "$PIDFILE"
  is_running && echo "started (pid $(cat "$PIDFILE")) serving $f" || { echo "failed to start; see $LOG"; exit 1; }
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
  *)       echo "usage: $0 {start|stop|restart|status|<file.md>}"; exit 2 ;;
esac
