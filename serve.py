#!/usr/bin/env python3
"""Render and serve a Markdown file as HTML, plus a PPA-review request form.

Usage: python3 serve.py [file.md]
  Defaults to Package-Review-Guidelines.md.

Routes:
  GET  /debpr/<basename>   render the served Markdown file
  GET  /debpr/Package-Review-Frontend
                           a form to submit a Launchpad PPA for review
  POST /debpr/Package-Review-Frontend
                           normalize the PPA, then list its packages so the
                           user can pick one (warns if there are many)
  GET  /debpr/Package-Review-Frontend?owner=&archive=&pick=NAME&series=S
                           start a review of the chosen package: init the status
                           file (the single source of truth for the target) and
                           launch the mechanical pipeline
  GET  /debpr/ppa/status   the review-status panel as an HTML fragment (polled)
"""
import atexit
import http.server
import os
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

import markdown

import ppa as ppalib
import review_status

PORT = 8000
ADDRS = ["10.72.172.152", "127.0.0.1"]
DIR = Path(__file__).resolve().parent
DOC = (DIR / (sys.argv[1] if len(sys.argv) > 1 else "Package-Review-Guidelines.md")).resolve()
URL_PATH = "/debpr/" + DOC.name
PPA_PATH = "/debpr/Package-Review-Frontend"
STATUS_PATH = "/debpr/ppa/status"
PIDFILE = DIR / ".serve.pid"
RUN_LOG = "/tmp/debpr-review-run.log"
MANY = 5  # warn when a PPA has more than this many packages

STYLE = ("body{max-width:900px;margin:auto;padding:2rem;"
         "font-family:sans-serif;line-height:1.6}"
         "pre{background:#f6f8fa;padding:1rem;overflow:auto}"
         "code{background:#eff1f3;padding:.1em .3em}"
         "input[type=text]{flex:1;padding:.6em;font-size:1em;box-sizing:border-box}"
         "button{padding:.6em 1.2em;font-size:1em;white-space:nowrap}"
         ".ppa-row{display:flex;gap:.6em;align-items:stretch}"
         "table{border-collapse:collapse;width:100%}"
         "th,td{border:1px solid #d0d7de;padding:6px 10px;text-align:left}"
         ".warn{background:#fff8c5;border:1px solid #d4a72c;padding:.8em 1em;border-radius:6px}"
         ".ok{color:#070}.err{color:#b00}.muted{color:#57606a;font-size:.9em}"
         ".panel{margin-top:2.5rem;border-top:2px solid #d0d7de;padding-top:1rem}"
         ".steps{list-style:none;padding-left:0}"
         ".steps li{padding:.15em 0}"
         ".log{background:#0d1117;color:#c9d1d9;font-size:.82em;line-height:1.45;"
         "max-height:16em;overflow:auto;padding:.7em .9em;border-radius:6px}")


def esc(s):
    return urllib.parse.quote(str(s))


def html(title, body):
    return (f"<!doctype html><meta charset='utf-8'><title>{title}</title>"
            f"<style>{STYLE}</style>{body}").encode("utf-8")


_md_cache = {}  # str(path) -> (mtime, payload); markdown render is the slow bit


def render_markdown(path):
    key = str(path)
    mtime = path.stat().st_mtime
    hit = _md_cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    body = markdown.markdown(
        path.read_text(encoding="utf-8"),
        extensions=["fenced_code", "tables", "toc", "sane_lists"],
    )
    payload = html(path.stem, body)
    _md_cache[key] = (mtime, payload)
    return payload


_status_cache = {"sig": None, "payload": b""}


def status_fragment():
    """Render the status panel, cached on the state+log file mtimes."""
    sig = tuple(p.stat().st_mtime if p.is_file() else 0
                for p in (review_status.STATE_FILE, review_status.LOG_FILE))
    if _status_cache["sig"] != sig:
        _status_cache["sig"] = sig
        _status_cache["payload"] = review_status.render_html().encode("utf-8")
    return _status_cache["payload"]


def status_panel():
    """A self-refreshing container that polls the status fragment route."""
    return (f"<div id='review-status'>{review_status.render_html()}</div>"
            "<script>setInterval(function(){"
            f"fetch('{STATUS_PATH}').then(function(r){{return r.text();}})"
            ".then(function(t){document.getElementById('review-status')"
            ".innerHTML=t;var l=document.querySelector('#review-status .log');"
            "if(l){l.scrollTop=l.scrollHeight;}});},3000);</script>")


def ppa_form(msg=""):
    return html("Submit a PPA for review", f"""
      <h1>Review a Launchpad PPA</h1>
      <p>Enter a PPA as a URL
      (<code>https://launchpad.net/~owner/+archive/ubuntu/name</code>)
      or as an add-apt-repository spec (<code>ppa:owner/name</code>).</p>
      <form method="post" action="{PPA_PATH}">
        <div class="ppa-row">
          <input type="text" name="ppa" placeholder="ppa:fheimes/test" required>
          <button type="submit">List packages</button>
        </div>
      </form>
      {msg}
      <p><a href="{URL_PATH}">&larr; Review guide</a></p>
      {status_panel()}""")


def package_list_page(owner, archive, rows):
    web = ppalib.ppa_web_url(owner, archive)
    warn = ""
    if len(rows) > MANY:
        warn = (f"<p class='warn'><b>Heads up:</b> this PPA has "
                f"<b>{len(rows)}</b> packages. Reviewing many packages can be a "
                f"large effort &mdash; pick one below to review at a time.</p>")
    trs = "".join(
        f"<tr><td>{r['name']}</td><td><code>{r['version']}</code></td>"
        f"<td>{r['series']}</td>"
        f"<td><a href='{PPA_PATH}?owner={esc(owner)}&archive={esc(archive)}"
        f"&pick={esc(r['name'])}&series={esc(r['series'])}'>Review this</a></td></tr>"
        for r in rows)
    return html(f"{owner}/{archive} packages", f"""
      <h1>Packages in <code>ppa:{owner}/{archive}</code></h1>
      <p><a href="{web}">{web}</a> &mdash; {len(rows)} published source(s)</p>
      {warn}
      <table><tr><th>Package</th><th>Version</th><th>Series</th><th></th></tr>
      {trs}</table>
      <p><a href="{PPA_PATH}">&larr; Submit a different PPA</a></p>
      {status_panel()}""")


_run_lock = threading.Lock()
_run_proc = None  # the in-flight review pipeline, if any


def start_review_run(setup=None):
    """Run `setup` and launch the mechanical pipeline detached, unless one runs.

    `setup` (init the status file for the new pick) runs *inside* the lock and
    only when we actually start, so a fresh pick can't reset the state of a
    review that's already in flight. Returns True if started, False if one was
    running. The child gets its own session (start_new_session) so it survives
    the request thread, with stdin closed and output captured to RUN_LOG.
    """
    global _run_proc
    with _run_lock:
        if _run_proc is not None and _run_proc.poll() is None:
            return False
        if setup:
            setup()
        log = open(RUN_LOG, "w", encoding="utf-8")
        _run_proc = subprocess.Popen(
            ["python3", str(DIR / "review_status.py"), "run-all"], cwd=str(DIR),
            stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True)
        return True


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, payload, code=200, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parts = urllib.parse.urlsplit(self.path)
        if parts.path == URL_PATH:
            self._send(render_markdown(DOC))
        elif parts.path == STATUS_PATH:
            self._send(status_fragment())
        elif parts.path.startswith("/debpr/") and parts.path.endswith(".md"):
            # Serve any Markdown file living in the repo dir (e.g. review-*.md).
            name = parts.path[len("/debpr/"):]
            target = (DIR / name).resolve()
            if target.parent == DIR and target.is_file():
                self._send(render_markdown(target))
            else:
                self.send_error(404)
        elif parts.path == PPA_PATH:
            q = urllib.parse.parse_qs(parts.query)
            if "pick" in q:  # user chose a specific package
                owner = q.get("owner", [""])[0]
                archive = q.get("archive", [""])[0]
                pkg = q.get("pick", [""])[0]
                series = q.get("series", [""])[0]
                def setup():
                    review_status.init(owner, archive, pkg, series)
                    review_status.set_step("list", "done")

                if start_review_run(setup):
                    msg = (f"<p class='ok'>Recorded <code>{pkg}</code> "
                           f"({series}) from <code>ppa:{owner}/{archive}</code> "
                           f"and <b>started the review</b>. The mechanical steps "
                           f"are running now &mdash; watch the panel below; the "
                           f"agent completes the judgment steps.</p>")
                else:
                    msg = ("<p class='warn'>A review is already running. Let it "
                           "finish, then pick again to start a new one.</p>")
                self._send(ppa_form(msg))
            else:
                self._send(ppa_form())
        else:
            self.send_error(404)

    def do_POST(self):
        if urllib.parse.urlsplit(self.path).path != PPA_PATH:
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        ref = (form.get("ppa", [""])[0]).strip()
        try:
            owner, archive = ppalib.normalize(ref)
        except ValueError:
            self._send(ppa_form(f"<p class='err'>Not a valid PPA reference: "
                                f"<code>{ref}</code></p>"), code=400)
            return
        try:
            rows = ppalib.list_sources(owner, archive)
        except Exception as exc:  # noqa: BLE001
            self._send(ppa_form(f"<p class='err'>Could not query PPA: "
                                f"{exc}</p>"), code=502)
            return
        if not rows:
            self._send(ppa_form(f"<p class='warn'>No published sources found in "
                                f"<code>ppa:{owner}/{archive}</code>.</p>"))
            return
        self._send(package_list_page(owner, archive, rows))

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def serve(addr):
    httpd = http.server.ThreadingHTTPServer((addr, PORT), Handler)
    print(f"Serving http://{addr}:{PORT}{URL_PATH}  (PPA form: {PPA_PATH})")
    httpd.serve_forever()


def _write_pidfile():
    PIDFILE.write_text(f"{os.getpid()}\n", encoding="utf-8")
    atexit.register(lambda: PIDFILE.unlink(missing_ok=True))


if __name__ == "__main__":
    if not DOC.is_file():
        sys.exit(f"file not found: {DOC}")
    _write_pidfile()
    for addr in ADDRS[1:]:
        threading.Thread(target=serve, args=(addr,), daemon=True).start()
    serve(ADDRS[0])
