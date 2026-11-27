---
name: Serve a Markdown file as a web page
description: Render a .md file to HTML and serve it over plain-Python HTTP (no framework), reachable from a browser. Use this whenever asked to "serve", "preview", or "publish" a Markdown document locally, or when handling a "/serve ..." command.
---

# Serve a Markdown file as a web page

Reusable knowledge for an agent: render a `.md` file to HTML and serve it over
HTTP with plain Python (no framework), reachable from a browser. This skill is
pure, generic knowledge with no bundled scripts of its own — the recipe below
is a complete, working pattern you can implement directly. For a concrete,
already-working implementation of this same pattern (plus a PPA-review web
form and live status panel built on top of it), see the `ppa-review` skill's
`scripts/serve.py` and `scripts/serve-ctl.sh`.

## `/serve` commands

When the user types a `/serve …` command and the `ppa-review` skill's
`serve-ctl.sh` is available (e.g. both skills are installed together, as in
the `debpr` repo), run it with the matching argument:

| User command         | Action                                              | Run                                  |
| --------------------- | ---------------------------------------------------- | ------------------------------------ |
| `/serve start`       | Start the server with the last-used (or default) file | `./serve-ctl.sh start`               |
| `/serve stop`        | Stop the server                                     | `./serve-ctl.sh stop`                |
| `/serve restart`     | Restart with the current file                       | `./serve-ctl.sh restart`             |
| `/serve <file.md>`   | Switch to `<file.md>` and (re)start                 | `./serve-ctl.sh <path/to/file.md>`   |

Notes (when using that concrete implementation):
- `<file.md>` is a path relative to the repo root (e.g.
  `docs/Package-Review-Guidelines.md` or `var/reports/Result_<pkg>.md`). The
  chosen file is remembered in `var/.serve.file`, so a later `/serve restart`
  keeps serving it.
- The default file (when none was ever chosen) is
  `docs/Package-Review-Guidelines.md`.
- `serve-ctl.sh` tracks the process in `var/.serve.pid`, logs to
  `/tmp/debpr-serve.log`, and uses `serve.py` under the hood. After starting,
  report the URL `http://<addr>:8000/debpr/<basename>`.

If there's no such existing script available, implement the recipe below
from scratch instead.

## Goal

Given a Markdown file, expose it at a URL like
`http://<addr>:<port>/<path>` so it renders as a styled web page.

## Prerequisites

- Python 3 (standard library: `http.server`, `socketserver`, `threading`).
- The `markdown` package for server-side rendering (renders fully offline; no
  CDN/JS needed on the client). Optionally `pygments` for code highlighting.

Install (this host needs the override flag because of PEP 668):

```sh
python3 -m pip install --break-system-packages markdown
```

If `pip` is missing, install it first (e.g. `python3 -m ensurepip` or the
distro's `python3-pip` package).

## Minimal recipe

1. Read the `.md` file and convert with
   `markdown.markdown(text, extensions=["fenced_code", "tables", "toc", "sane_lists"])`.
2. Wrap the HTML body in a tiny document with a little inline CSS for
   readability (`max-width`, padded `pre`/`code`).
3. Subclass `http.server.BaseHTTPRequestHandler`; in `do_GET`, match the exact
   URL path, render on each request (so edits show up on refresh), and return
   `200` with `Content-Type: text/html; charset=utf-8`. Return `404` otherwise.
4. Serve with `socketserver.TCPServer((addr, port), Handler)`.

## Choosing the bind address

- `127.0.0.1` — reachable only from this host (loopback).
- The host's LAN IP (find with `hostname -I` or `ss -ltn`) — reachable from the
  local network.
- `0.0.0.0` — all interfaces at once (simplest, but binds everywhere).

To serve on **specific** addresses (e.g. loopback **and** the LAN IP) rather
than all interfaces, bind one `TCPServer` per address, each in its own thread:

```python
for addr in ADDRS[1:]:
    threading.Thread(target=serve, args=(addr,), daemon=True).start()
serve(ADDRS[0])
```

External reachability beyond the LAN also depends on NAT / firewall / security
groups — opening the port in code is not enough.

## Running it detached

Background it so it survives the launching shell. Use `setsid` and redirect I/O:

```sh
setsid python3 serve.py > /tmp/serve.log 2>&1 < /dev/null &
```

Verify and manage:

```sh
pgrep -af '[s]erve.py'          # find the PID
ss -ltn | grep ':8000'          # confirm it is listening
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/<path>
kill <PID>                       # stop it
```

## Gotchas

- **Don't kill yourself**: `pkill -f serve.py` also matches the very shell
  command that contains "serve.py". Prefer `kill <PID>` from `pgrep -af '[s]erve.py'`
  (the bracket trick excludes the matcher itself).
- **PEP 668 / externally-managed env**: `pip install` may need
  `--break-system-packages` (or use a virtualenv).
- **Rendering happens per request**, so editing the `.md` file is reflected on
  the next browser refresh — no restart needed.
- Keep the path match exact; redirect `/` to the document only if you want a
  convenience entry point.
- **If serving more than one directory of `.md` files** (e.g. a docs folder
  and a reports folder), validate the requested basename against a safe
  pattern (e.g. `^[A-Za-z0-9][A-Za-z0-9._-]*\.md$`, rejecting any `/`) *before*
  touching the filesystem, then look it up in each allowed directory by plain
  join (no `..`-traversal possible since no separator is accepted). Avoid
  resolving symlinks for this containment check — resolving a symlinked file
  returns its target's real parent directory, not the symlink's own directory,
  which can defeat a naive `resolved_path.parent == allowed_dir` check.
