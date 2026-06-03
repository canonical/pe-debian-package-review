#!/usr/bin/env python3
"""Track and render the status of a PPA package review.

The review process (the agent) updates a small JSON state file as it works;
serve.py renders it as a panel at the bottom of the PPA page. A separate
append-only log file carries timestamped, line-by-line activity so long steps
(e.g. fetching source) show continuous progress instead of looking hung.

State file: .review-status.json   Log file: .review-log   (both gitignored)

CLI:
  python3 review_status.py init <ppa> <package>     start/reset a review
  python3 review_status.py step <name> <status>     set one step's status
  python3 review_status.py note <text>              set the free-text note
  python3 review_status.py report <url>             link the finished report
  python3 review_status.py log <text...>            append one activity line
  python3 review_status.py run <name> <cmd...>      mark step active, stream the
                                                    command's output to the log,
                                                    then mark done/fail by exit
  python3 review_status.py show                      print the current state
  python3 review_status.py clear                     remove state + log

Step <status> is one of: pending active done warn fail skip
Step <name> is matched case-insensitively against the default steps, or added.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DIR = Path(__file__).resolve().parent
STATE_FILE = DIR / ".review-status.json"
LOG_FILE = DIR / ".review-log"
LOG_TAIL = 14  # number of recent activity lines to show in the panel

# The default pipeline, mirroring AGENT-ppa-review.md.
DEFAULT_STEPS = [
    "List packages",
    "Fetch source",
    "Classify (PATCH/SRU/new)",
    "debian/watch",
    "debian/changelog",
    "debian/control",
    "debian/copyright",
    "debian/patches (quilt/DEP-3)",
    "Symbols & ABI",
    "Lintian (source package)",
    "Binary builds (PPA)",
    "Lintian (binary packages)",
    "Report",
]

LABELS = {
    "pending": ("&#9675;", "#57606a"),   # ○ grey
    "active":  ("&#9679;", "#0969da"),   # ● blue
    "done":    ("&#10003;", "#1a7f37"),  # ✓ green
    "warn":    ("&#9888;", "#9a6700"),   # ⚠ amber
    "fail":    ("&#10007;", "#cf222e"),  # ✗ red
    "skip":    ("&#8722;", "#57606a"),   # − grey
}


def _now():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _now()).isoformat(timespec="seconds")


def load():
    if STATE_FILE.is_file():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return None


def save(state):
    state["updated"] = _iso()
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def log(text):
    """Append one timestamped activity line; force a flush so polls see it."""
    stamp = _now().strftime("%H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        for line in str(text).splitlines() or [""]:
            fh.write(f"{stamp}  {line}\n")
        fh.flush()


def init(ppa, package):
    LOG_FILE.write_text("", encoding="utf-8")
    save({
        "ppa": ppa,
        "package": package,
        "note": "Review started.",
        "steps": [{"name": n, "status": "pending", "started": None,
                   "ended": None} for n in DEFAULT_STEPS],
    })
    log(f"Review started for {package} from {ppa}.")


def set_step(name, status):
    if status not in LABELS:
        sys.exit(f"unknown status {status!r}; use one of {' '.join(LABELS)}")
    state = load() or {"ppa": "", "package": "",
                       "steps": [{"name": n, "status": "pending",
                                  "started": None, "ended": None}
                                 for n in DEFAULT_STEPS]}
    for s in state["steps"]:
        if s["name"].lower() == name.lower():
            if status == "active" and not s.get("started"):
                s["started"] = _iso()
            if status in ("done", "warn", "fail", "skip"):
                s["ended"] = _iso()
            s["status"] = status
            name = s["name"]
            break
    else:
        state["steps"].append({"name": name, "status": status,
                               "started": _iso() if status == "active" else None,
                               "ended": None})
    save(state)
    log(f"-- {name}: {status}")


def set_note(text):
    state = load()
    if state is None:
        sys.exit("no review in progress; run `init` first")
    state["note"] = text
    save(state)
    log(text)


def set_report(url):
    state = load()
    if state is None:
        sys.exit("no review in progress; run `init` first")
    state["report"] = url
    save(state)
    log(f"Report available: {url}")


def run(name, cmd):
    """Mark a step active, stream the command output to the log, set result."""
    set_step(name, "active")
    log(f"$ {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
    except OSError as exc:
        log(f"[could not start: {exc}]")
        set_step(name, "fail")
        return 127
    for line in proc.stdout:
        log(line.rstrip("\n"))
    rc = proc.wait()
    log(f"[exit {rc}]")
    set_step(name, "done" if rc == 0 else "fail")
    return rc


def _elapsed(started, ended=None):
    try:
        a = datetime.fromisoformat(started)
    except (TypeError, ValueError):
        return ""
    b = datetime.fromisoformat(ended) if ended else _now()
    secs = int((b - a).total_seconds())
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m{secs % 60:02d}s"


def current(state):
    """The active step, else the first pending one, else None."""
    for s in state["steps"]:
        if s["status"] == "active":
            return s
    for s in state["steps"]:
        if s["status"] == "pending":
            return s
    return None


def _tail_log():
    if not LOG_FILE.is_file():
        return []
    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    return lines[-LOG_TAIL:]


def _html_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_html():
    state = load()
    if state is None:
        return ("<div class='panel'><h2>Review status</h2>"
                "<p class='muted'>No review in progress. Submit a PPA and pick a "
                "package to begin.</p></div>")
    steps = state.get("steps", [])
    # "reviewed" = reached a terminal verdict (incl. warn/fail findings & skip),
    # i.e. not still pending/active. So the count reaches N/N when the whole
    # review is done, even though some steps are warnings or failures.
    done = sum(1 for s in steps
               if s["status"] in ("done", "skip", "warn", "fail"))
    cur = current(state)
    cur_name = cur["name"] if cur else None
    rows = []
    for s in steps:
        glyph, color = LABELS.get(s["status"], LABELS["pending"])
        weight = "font-weight:600;" if s["name"] == cur_name else ""
        extra = ""
        if s["status"] == "active" and s.get("started"):
            extra = f" <span class='muted'>({_elapsed(s['started'])} elapsed)</span>"
        elif s.get("started") and s.get("ended"):
            extra = f" <span class='muted'>({_elapsed(s['started'], s['ended'])})</span>"
        rows.append(
            f"<li style='{weight}'><span style='color:{color}'>{glyph}</span> "
            f"{s['name']} <span class='muted'>&mdash; {s['status']}</span>{extra}</li>")
    pkg = state.get("package") or "?"
    ppa = state.get("ppa") or "?"
    note = state.get("note", "")
    updated = state.get("updated", "")
    report = state.get("report", "")
    head = (f"Reviewing <code>{pkg}</code> from <code>{ppa}</code>"
            if pkg != "?" else "Review")
    if cur and cur["status"] == "active":
        el = _elapsed(cur.get("started")) if cur.get("started") else ""
        cur_line = f"<p><b>Current step:</b> {cur['name']} &mdash; running {el}</p>"
    elif cur:
        cur_line = f"<p><b>Next step:</b> {cur['name']}</p>"
    else:
        cur_line = "<p class='ok'><b>Review complete.</b></p>"
    log_lines = _tail_log()
    log_html = ""
    if log_lines:
        body = _html_escape("\n".join(log_lines))
        log_html = (f"<p class='muted' style='margin-bottom:.2em'>Activity log "
                    f"(last {len(log_lines)} lines):</p>"
                    f"<pre class='log'>{body}</pre>")
    note_html = ""
    if note:
        text = _html_escape(note)
        link_html = ""
        if report:
            basename = report.rsplit("/", 1)[-1]
            # Split off a trailing "See report" mention onto its own line as a
            # clickable link to the report file.
            text, n = re.subn(r"\s*See report\.?\s*$", "", text,
                              flags=re.IGNORECASE)
            if n:
                link_html = (f"<p class='muted'>See "
                             f"<a href='{report}'>{basename}</a></p>")
        note_html = f"<p class='muted'>{text}</p>{link_html}"
    return (
        "<div class='panel'><h2>Review status</h2>"
        f"<p>{head} &mdash; {done}/{len(steps)} steps reviewed</p>"
        f"{cur_line}"
        + (f"<p><b>&#128196; <a href='{report}'>See {pkg} report</a></b></p>"
           if report else "")
        + f"<ul class='steps'>{''.join(rows)}</ul>"
        + note_html
        + log_html
        + (f"<p class='muted'>updated {updated}</p>" if updated else "")
        + "</div>")


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    if cmd == "init" and len(rest) == 2:
        init(rest[0], rest[1])
    elif cmd == "step" and len(rest) == 2:
        set_step(rest[0], rest[1])
    elif cmd == "note" and rest:
        set_note(" ".join(rest))
    elif cmd == "report" and len(rest) == 1:
        set_report(rest[0])
    elif cmd == "log" and rest:
        log(" ".join(rest))
    elif cmd == "run" and len(rest) >= 2:
        sys.exit(run(rest[0], rest[1:]))
    elif cmd == "show":
        state = load()
        print(json.dumps(state, indent=2) if state else "(no review)")
    elif cmd == "clear":
        STATE_FILE.unlink(missing_ok=True)
        LOG_FILE.unlink(missing_ok=True)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
