#!/usr/bin/env python3
"""Track, drive, and render the status of a PPA package review.

The review process (the agent) updates a small JSON state file as it works;
serve.py renders it as a panel at the bottom of the PPA page. A separate
append-only log file carries timestamped, line-by-line activity so long steps
(e.g. fetching source) show continuous progress instead of looking hung.

The same JSON state file is the single source of truth for *which package is
under review* (owner/archive/package/series) -- there is no separate request
file. `ppa.py` reads the target from here.

State file: <repo-root>/var/.review-status.json
Log file:   <repo-root>/var/.review-log
(both gitignored; this script's own directory can live anywhere -- e.g.
inside an OpenCode skill -- the repo root is found by walking up from here)

CLI:
  init <OWNER/ARCHIVE> <pkg> [series]   start/reset a review (records the target)
  run-all [<OWNER/ARCHIVE> <pkg> [series]]
                                        run the mechanical pipeline end to end:
                                          fetch -> source lintian ->
                                          binary builds -> binary lintian
                                        (target defaults to the recorded review)
  step <id> <status> [note...]          set one step's status; an optional note
                                        is appended to the activity log
  run <id> <cmd...>                     mark step <id> active, stream the
                                        command's output to the log, then mark
                                        done/fail by its exit code
  note <text...>                        set the free-text panel note
  report <url>                          link the finished report
  log <text...>                         append one activity line
  remaining                             list steps not yet reviewed
  severity                              list findings bucketed must-fix/should-fix
  steps                                 list the canonical step ids
  show                                  print the current state JSON
  clear                                 remove state + log

Step <status> is one of: pending active done warn fail skip
Step <id> is matched against the canonical ids below (case-insensitive, with a
unique-substring fallback). Unknown ids are rejected -- they are never silently
added -- so a typo can't create a phantom step.
"""
import glob
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import ppa  # for normalize() and resolve_target(); ppa does NOT import this

# This file lives at <repo-root>/.opencode/skills/ppa-review/scripts/ -- walk
# up to the repo root so the tool works regardless of where it's invoked from,
# and so the whole ppa-review/ skill folder stays relocatable as a unit.
DIR = Path(__file__).resolve().parent
REPO_ROOT = DIR.parents[3]
VAR = REPO_ROOT / "var"
STATE_FILE = VAR / ".review-status.json"
LOG_FILE = VAR / ".review-log"
REPORTS_DIR = VAR / "reports"
LOG_TAIL = 14  # number of recent activity lines to show in the panel
WORK = "/tmp/opencode/ppa-review"

# var/ (and var/reports/) ship as empty, tracked directories (.gitkeep) so this
# mkdir is normally a no-op; it's a safety net for anyone who deleted them.
VAR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# The default pipeline, mirroring AGENT-ppa-review.md: (canonical id, display).
# The id is stable and typo-resistant; the display name is what the panel shows.
STEPS = [
    ("list",           "List packages"),
    ("fetch",          "Fetch source"),
    ("classify",       "Classify (PATCH/SRU/new)"),
    ("watch",          "debian/watch"),
    ("changelog",      "debian/changelog"),
    ("control",        "debian/control"),
    ("copyright",      "debian/copyright"),
    ("patches",        "debian/patches (quilt/DEP-3)"),
    ("symbols",        "Symbols & ABI"),
    ("lintian-source", "Lintian (source package)"),
    ("builds",         "Binary builds (PPA)"),
    ("lintian-binary", "Lintian (binary packages)"),
    ("install-test",   "Install/upgrade test"),
    ("autopkgtest",    "Tests (upstream/autopkgtest)"),
    ("report",         "Report"),
]
STEP_IDS = [i for i, _ in STEPS]

LABELS = {
    "pending": ("&#9675;", "#57606a"),   # ○ grey
    "active":  ("&#9679;", "#0969da"),   # ● blue
    "done":    ("&#10003;", "#1a7f37"),  # ✓ green
    "warn":    ("&#9888;", "#9a6700"),   # ⚠ amber
    "fail":    ("&#10007;", "#cf222e"),  # ✗ red
    "skip":    ("&#8722;", "#57606a"),   # − grey
}

# Step verdict -> report severity bucket (#7). Terminal "done"/"skip" carry no
# finding; only warn/fail map to something the report must enumerate.
SEVERITY = {"fail": "must-fix", "warn": "should-fix"}


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


def init(owner, archive, package, series=""):
    """Start/reset a review and record its target in the state file."""
    LOG_FILE.write_text("", encoding="utf-8")
    save({
        "ppa": f"ppa:{owner}/{archive}",
        "owner": owner,
        "archive": archive,
        "package": package,
        "series": series,
        "url": ppa.ppa_web_url(owner, archive),
        "note": "Review started.",
        "steps": [{"id": i, "name": n, "status": "pending",
                   "started": None, "ended": None} for i, n in STEPS],
    })
    log(f"Review started for {package} from ppa:{owner}/{archive}"
        + (f" ({series})" if series else "") + ".")


def _find_step(steps, key):
    """Resolve a step by id or display name.

    Returns (step, None) on a unique match, (None, [ids]) when several steps
    match a substring (ambiguous), or (None, []) when nothing matches. Crucially
    it never *creates* a step -- callers turn a miss into an error.
    """
    k = key.strip().lower()
    for s in steps:
        if s.get("id", "").lower() == k or s.get("name", "").lower() == k:
            return s, None
    hits = [s for s in steps
            if k in s.get("id", "").lower() or k in s.get("name", "").lower()]
    if len(hits) == 1:
        return hits[0], None
    if len(hits) > 1:
        return None, [s.get("id") or s.get("name") for s in hits]
    return None, []


def set_step(key, status, note=None):
    if status not in LABELS:
        sys.exit(f"unknown status {status!r}; use one of {' '.join(LABELS)}")
    state = load()
    if state is None:
        sys.exit("no review in progress; run `init` first")
    s, ambiguous = _find_step(state["steps"], key)
    if s is None:
        if ambiguous:
            sys.exit(f"ambiguous step {key!r}; matches: {', '.join(ambiguous)}")
        sys.exit(f"unknown step {key!r}; valid ids: {', '.join(STEP_IDS)}")
    if status == "active" and not s.get("started"):
        s["started"] = _iso()
    if status in ("done", "warn", "fail", "skip"):
        s["ended"] = _iso()
    s["status"] = status
    save(state)
    log(f"-- {s['name']}: {status}")
    if note:
        log(f"   {note}")


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


def run(key, cmd):
    """Mark a step active, stream the command output to the log, set result."""
    set_step(key, "active")
    log(f"$ {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
    except OSError as exc:
        log(f"[could not start: {exc}]")
        set_step(key, "fail")
        return 127
    for line in proc.stdout:
        log(line.rstrip("\n"))
    rc = proc.wait()
    log(f"[exit {rc}]")
    set_step(key, "done" if rc == 0 else "fail")
    return rc


def run_all(args):
    """Run the mechanical pipeline end to end, each step streamed to the panel.

    fetch -> Lintian (source) -> binary builds -> Lintian (binary). The judgment
    steps (Classify, debian/*, Symbols & ABI, Report) are left to the agent.
    lintian uses `--fail-on none` so a *finding* (E:/W:) doesn't fail the step --
    the step means "analysis ran" and every tag lands in the log to triage.

    This replaces the old review-run.sh + fetch-source.sh + check-binaries.sh:
    one process, one activity log, calling ppa.py directly.
    """
    owner, archive, package, series = ppa.resolve_target(args)
    log(f"Running mechanical review steps for {package} "
        f"(ppa:{owner}/{archive}, series {series or '<auto>'}).")
    ppa_py = str(DIR / "ppa.py")
    target = [f"{owner}/{archive}", package] + ([series] if series else [])

    # 1) Fetch source -- abort the run if this fails (nothing to review without it).
    if run("fetch", ["python3", ppa_py, "fetch", *target]) != 0:
        set_note("Fetch failed; cannot continue. See the activity log.")
        return 1

    # 2) Lintian (source package) -- against the freshly unpacked .dsc.
    dscs = sorted(glob.glob(f"{WORK}/{package}_*.dsc"))
    if dscs:
        run("lintian-source", ["lintian", "--fail-on", "none", dscs[-1]])
    else:
        set_step("lintian-source", "warn",
                 f"no .dsc found for {package}; skipped source lintian")

    # 3) Binary builds (PPA) -- status + download debs; non-zero if an arch failed.
    run("builds", ["python3", ppa_py, "binaries", *target])

    # 4) Lintian (binary packages) -- against whatever .debs downloaded.
    debs = sorted(glob.glob(f"{WORK}/*.deb"))
    if debs:
        run("lintian-binary", ["lintian", "--fail-on", "none", *debs])
    else:
        set_step("lintian-binary", "skip",
                 "no .deb packages downloaded; skipped binary lintian")

    set_note("Mechanical checks complete (fetch, source/binary lintian, "
             "builds). Awaiting agent review of: Classify, debian/watch, "
             "changelog, control, copyright, patches, Symbols & ABI, then "
             "Report.")
    return 0


def remaining():
    state = load()
    if state is None:
        sys.exit("no review in progress")
    pend = [s for s in state["steps"] if s["status"] in ("pending", "active")]
    if not pend:
        print("(none -- all steps reviewed)")
        return
    for s in pend:
        print(f"{s.get('id',''):<16} {s['name']:<32} {s['status']}")


def severity():
    """Print findings bucketed by report severity (derived from step status)."""
    state = load()
    if state is None:
        sys.exit("no review in progress")
    buckets = {"must-fix": [], "should-fix": []}
    for s in state["steps"]:
        sev = SEVERITY.get(s["status"])
        if sev:
            buckets[sev].append(s["name"])
    for sev in ("must-fix", "should-fix"):
        print(f"{sev}:")
        for name in buckets[sev]:
            print(f"  - {name}")
        if not buckets[sev]:
            print("  (none)")


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
    mustfix = sum(1 for s in steps if s["status"] == "fail")
    shouldfix = sum(1 for s in steps if s["status"] == "warn")
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
    ppa_ref = state.get("ppa") or "?"
    note = state.get("note", "")
    updated = state.get("updated", "")
    report = state.get("report", "")
    head = (f"Reviewing <code>{pkg}</code> from <code>{ppa_ref}</code>"
            if pkg != "?" else "Review")
    findings = ""
    if mustfix or shouldfix:
        findings = (f"<p class='muted'>Findings: {mustfix} must-fix, "
                    f"{shouldfix} should-fix</p>")
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
    report_link = (f"<p><b>&#128196; <a href='{report}'>See {pkg} report</a></b></p>"
                   if report else "")
    return (
        "<div class='panel'><h2>Review status</h2>"
        f"<p>{head} &mdash; {done}/{len(steps)} steps reviewed</p>"
        f"{findings}"
        + f"<ul class='steps'>{''.join(rows)}</ul>"
        # Current/Next-step and "Review complete." status, plus the report link,
        # go *below* the step list so a human reading top-down lands on them
        # right where the steps end -- no scrolling back up.
        + cur_line
        + report_link
        + note_html
        + log_html
        + (f"<p class='muted'>updated {updated}</p>" if updated else "")
        + "</div>")


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    if cmd == "init" and len(rest) >= 2:
        owner, archive = ppa.normalize(rest[0])
        init(owner, archive, rest[1], rest[2] if len(rest) > 2 else "")
    elif cmd == "run-all":
        sys.exit(run_all(rest))
    elif cmd == "step" and len(rest) >= 2:
        set_step(rest[0], rest[1], " ".join(rest[2:]) or None)
    elif cmd == "note" and rest:
        set_note(" ".join(rest))
    elif cmd == "report" and len(rest) == 1:
        set_report(rest[0])
    elif cmd == "log" and rest:
        log(" ".join(rest))
    elif cmd == "run" and len(rest) >= 2:
        sys.exit(run(rest[0], rest[1:]))
    elif cmd == "remaining":
        remaining()
    elif cmd == "severity":
        severity()
    elif cmd == "steps":
        for i, n in STEPS:
            print(f"{i:<16} {n}")
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
