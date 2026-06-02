#!/usr/bin/env python3
"""Track and render the status of a PPA package review.

The review process (the agent) updates a small JSON state file as it works;
serve.py renders it as a panel at the bottom of the PPA page.

State file: .review-status.json (gitignored)

CLI:
  python3 review_status.py init <ppa> <package>     start/reset a review
  python3 review_status.py step <name> <status>     set one step's status
  python3 review_status.py note <text>              set the free-text note
  python3 review_status.py show                      print the current state
  python3 review_status.py clear                     remove the state file

Step <status> is one of: pending active done warn fail skip
Step <name> is matched case-insensitively against the default steps, or added.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent / ".review-status.json"

# The default pipeline, mirroring AGENT-ppa-review.md.
DEFAULT_STEPS = [
    "List packages",
    "Fetch source",
    "Classify (PATCH/SRU/new)",
    "debian/watch",
    "debian/changelog",
    "debian/control",
    "debian/copyright",
    "Patches (quilt) / DEP-3",
    "Symbols & ABI",
    "Lintian",
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
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load():
    if STATE_FILE.is_file():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return None


def save(state):
    state["updated"] = _now()
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def init(ppa, package):
    save({
        "ppa": ppa,
        "package": package,
        "note": "Review started.",
        "steps": [{"name": n, "status": "pending"} for n in DEFAULT_STEPS],
    })


def set_step(name, status):
    if status not in LABELS:
        sys.exit(f"unknown status {status!r}; use one of {' '.join(LABELS)}")
    state = load() or {"ppa": "", "package": "",
                       "steps": [{"name": n, "status": "pending"}
                                 for n in DEFAULT_STEPS]}
    for s in state["steps"]:
        if s["name"].lower() == name.lower():
            s["status"] = status
            break
    else:
        state["steps"].append({"name": name, "status": status})
    save(state)


def set_note(text):
    state = load()
    if state is None:
        sys.exit("no review in progress; run `init` first")
    state["note"] = text
    save(state)


def current(state):
    """The name of the active step, else the first pending one, else None."""
    for s in state["steps"]:
        if s["status"] == "active":
            return s["name"]
    for s in state["steps"]:
        if s["status"] == "pending":
            return s["name"]
    return None


def render_html():
    state = load()
    if state is None:
        return ("<div class='panel'><h2>Review status</h2>"
                "<p class='muted'>No review in progress. Submit a PPA and pick a "
                "package to begin.</p></div>")
    steps = state.get("steps", [])
    done = sum(1 for s in steps if s["status"] in ("done", "skip"))
    cur = current(state)
    rows = []
    for s in steps:
        glyph, color = LABELS.get(s["status"], LABELS["pending"])
        weight = "font-weight:600;" if s["name"] == cur else ""
        rows.append(
            f"<li style='{weight}'><span style='color:{color}'>{glyph}</span> "
            f"{s['name']} "
            f"<span class='muted'>&mdash; {s['status']}</span></li>")
    pkg = state.get("package") or "?"
    ppa = state.get("ppa") or "?"
    note = state.get("note", "")
    updated = state.get("updated", "")
    head = (f"Reviewing <code>{pkg}</code> from <code>{ppa}</code>"
            if pkg != "?" else "Review")
    cur_line = (f"<p><b>Current step:</b> {cur}</p>" if cur
                else "<p class='ok'><b>Review complete.</b></p>")
    return (
        "<div class='panel'><h2>Review status</h2>"
        f"<p>{head} &mdash; {done}/{len(steps)} steps</p>"
        f"{cur_line}"
        f"<ul class='steps'>{''.join(rows)}</ul>"
        + (f"<p class='muted'>{note}</p>" if note else "")
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
    elif cmd == "show":
        state = load()
        print(json.dumps(state, indent=2) if state else "(no review)")
    elif cmd == "clear":
        STATE_FILE.unlink(missing_ok=True)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
