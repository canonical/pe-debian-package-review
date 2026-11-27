# debpr — Debian/Ubuntu Package Review toolkit

An agent-driven toolkit for reviewing Ubuntu/Debian source packages published
in a Launchpad PPA, following a written review guide, with a live status
panel and a self-contained Markdown web server. Built to be operated by an
OpenCode agent from chat, with no separate frontend framework.

**Layout at a glance:** all the knowledge and tooling lives in one
self-contained unit, `.opencode/skills/ppa-review/` — a real, auto-discovered
OpenCode Skill, not just a convention. Copy that one folder into any other
project and it keeps working on its own (see
[Reusing just the skills](#reusing-just-the-skills)).

**Contents:** [Components](#components) ·
[Workflow](#workflow) ·
[Skills](#skills) ·
[Reusing just the skills](#reusing-just-the-skills) ·
[State & logs](#state--logs-gitignored-local-only) ·
[Setup](#setup-first-time-from-scratch) ·
[Quick start](#quick-start--using-it-day-to-day) ·
[Worked example](#worked-example-start-to-finish)

## Components

```
debpr/
├── README.md
├── docs/
│   └── Package-Review-Guidelines.md    (symlink -> the skill's own copy, below)
├── .opencode/
│   └── skills/
│       ├── ppa-review/                  <- the main Skill: self-contained
│       │   ├── SKILL.md                    knowledge + tooling for reviewing
│       │   ├── references/                 a PPA package end to end
│       │   │   └── Package-Review-Guidelines.md
│       │   └── scripts/
│       │       ├── ppa.py
│       │       ├── review_status.py
│       │       ├── serve.py
│       │       ├── serve-ctl.sh
│       │       └── review-notify.ts
│       └── serve-markdown/              <- a second, generic Skill: how to
│           └── SKILL.md                    serve any .md file as a web page
└── var/                                 (gitignored run state; see below)
    ├── .review-status.json
    ├── .review-log
    ├── .serve.pid / .serve.file
    └── reports/
        └── Result_<package>.md
```

| Path | Role |
|------|------|
| `.opencode/skills/ppa-review/SKILL.md` | The **Skill** OpenCode auto-discovers and advertises: how to take a PPA reference, fetch a package's source, drive the mechanical pipeline, work the judgment steps, and write the report. See [Skills](#skills). |
| `.opencode/skills/ppa-review/references/Package-Review-Guidelines.md` | The review guide itself — a checklist (classification, `debian/watch`, `changelog`, `control`, `copyright`, patches/quilt, symbols & ABI, build & test, lintian, sponsoring, new-package rules) the agent works through top to bottom. Bundled *inside* the skill folder so the skill is self-contained; also reachable at `docs/Package-Review-Guidelines.md` via a symlink for convenience/direct browsing. |
| `.opencode/skills/ppa-review/scripts/ppa.py` | Launchpad API helpers: normalize a PPA reference (`ppa:OWNER/ARCHIVE` or an LP URL), list its published sources, fetch a package's source (`pull-ppa-source`), check per-architecture build status, and download built binaries. |
| `.opencode/skills/ppa-review/scripts/review_status.py` | The review **state machine**: a JSON file (`var/.review-status.json`) is the single source of truth for which package is under review and the status of each canonical step; an append-only log (`var/.review-log`) carries live activity; `run-all` drives the mechanical half of the pipeline end to end. |
| `.opencode/skills/ppa-review/scripts/serve.py` | A dependency-light HTTP server (stdlib `http.server` + the `markdown` package) that renders Markdown files under `docs/` or `var/reports/` as styled pages, hosts the PPA-submission web form, and exposes the live status panel as a polled HTML fragment. |
| `.opencode/skills/ppa-review/scripts/serve-ctl.sh` | start/stop/restart/status wrapper around `serve.py`, backing the `/serve …` chat commands. |
| `.opencode/skills/ppa-review/scripts/review-notify.ts` | An OpenCode plugin: watches `var/.review-status.json` at the OS level (zero LLM tokens) and, the instant the mechanical steps finish, injects a continuation prompt into the active chat session so the agent picks up the judgment steps on its own — no manual "did it finish?" polling. |
| `.opencode/skills/serve-markdown/SKILL.md` | A second, fully generic **Skill**: how to render any `.md` file to HTML and serve it over plain-Python HTTP. No PPA knowledge, no bundled scripts — a pure, reusable recipe. |
| `var/reports/Result_<package>.md` | One per-package review report (gitignored — a working artifact, not versioned). |

## Workflow

```
 PPA reference                         references/Package-Review-Guidelines.md
 (ppa:OWNER/ARCHIVE or LP URL)                      │
        │                                           │ judgment steps
        ▼                                           ▼
 ┌───────────────┐   init    ┌──────────────────────────────┐
 │ web form /    │ ────────► │ var/.review-status.json      │
 │ chat message  │           │ (single source of truth:     │
 └───────────────┘           │  owner/archive/pkg/series +  │
                              │  per-step status)            │
                              └───────────┬──────────────────┘
                                          │ run-all (mechanical)
                                          ▼
                 fetch source ─► lintian (source) ─► binary builds (PPA)
                                          │                 ─► lintian (binary)
                                          ▼
                              review-notify plugin (fs.watch,
                              no polling) wakes the agent the
                              moment the mechanical steps finish
                                          │
                                          ▼
                 agent works the judgment steps by hand:
                 classify → watch → changelog → control → copyright
                 → patches → symbols/ABI → install/upgrade test →
                 tests (autopkgtest) → Report
                                          │
                                          ▼
                       var/reports/Result_<package>.md written,
                       linked into the panel, served at
                       http://<addr>:8000/debpr/Result_<package>.md
```

1. **Input.** A PPA is given either via the web form
   (`http://<addr>:8000/debpr/Package-Review-Frontend`) or pasted directly in
   chat, as `ppa:OWNER/ARCHIVE` or a Launchpad URL.
2. **Init.** Picking a package (web form) or starting a review in chat calls
   `review_status.py init`, which records the target
   (owner/archive/package/series) in `var/.review-status.json` — there is no
   separate "request" file; everything downstream reads the target from here.
3. **Mechanical pipeline (scriptable, auto-run).** `review_status.py run-all`
   chains: fetch source (`ppa.py fetch`, i.e.
   `pull-ppa-source --no-verify-signature`) → `lintian` on the source package
   → binary build status + download (`ppa.py binaries`) → `lintian` on every
   downloaded `.deb`. Each step's status/log lands in `var/.review-status.json`
   / `var/.review-log` as it runs. The web form auto-starts this in the
   background the moment a package is picked.
4. **Wake-up (push, not poll).** The `review-notify` OpenCode plugin watches
   `var/.review-status.json` with an OS-level `fs.watch`. The moment `run-all`
   writes its "Mechanical checks complete…" note, the plugin injects a new
   chat turn telling the agent to continue — no LLM tokens spent polling a
   file in a loop.
5. **Judgment steps (agent, by hand).** Following
   `references/Package-Review-Guidelines.md`, the agent works through
   classification, `debian/watch`, `changelog`, `control`, `copyright`,
   `patches`/quilt, symbols & ABI, an install/upgrade test, and an
   autopkgtest check — each recorded with
   `review_status.py step <id> <status> [note]` (`done` / `warn` =
   should-fix / `fail` = must-fix / `skip` = n/a).
6. **Report.** The agent writes `var/reports/Result_<package>.md`
   (pass/warn/fail per guide section, with tool-output evidence), links it
   with `review_status.py report <url>`, and marks the `report` step `done` —
   the panel reaches N/N.
7. **Serving.** `serve.py` (via `serve-ctl.sh` / `/serve` chat commands)
   renders the guide, the frontend form, the live panel, and any report under
   `var/reports/` at `http://<addr>:8000/debpr/<name>`, re-rendering on every
   request so edits show up on refresh with no restart.

## Skills

This project ships **two real OpenCode Skills** — not just conventionally
read `.md` files, but entries OpenCode auto-discovers at
`.opencode/skills/<id>/SKILL.md`, advertises to the model based on their
`description`, and loads on demand via the `skill` tool (or by mentioning
`@ppa-review` / `@serve-markdown` directly in a prompt):

- **`ppa-review`** (`.opencode/skills/ppa-review/SKILL.md`) — "how to review
  a PPA": input forms, the mechanical pipeline, driving
  `var/.review-status.json`, the judgment-step checklist (bundled alongside
  it at `references/Package-Review-Guidelines.md`), binary builds/lintian,
  the mandatory install/upgrade test and autopkgtest check, writing the
  report, and the guardrails (never sign/upload, keep build logs, log every
  action, only touch a scratch tree). Its `scripts/` subfolder carries the
  actual tooling (`ppa.py`, `review_status.py`, `serve.py`, `serve-ctl.sh`,
  the `review-notify.ts` plugin) — this entire skill folder is a
  **self-contained, relocatable unit** (see below).
- **`serve-markdown`** (`.opencode/skills/serve-markdown/SKILL.md`) — "how to
  serve a Markdown file as a web page": the `/serve …` chat-command
  convention, the generic render-and-serve recipe, choosing a bind address,
  running detached, and common gotchas (PEP 668, not killing your own shell
  with `pkill -f serve.py`, symlink-safe path containment checks). This one
  is **pure knowledge with no bundled scripts** — a complete recipe you can
  implement from scratch wherever it's needed, with a cross-reference to
  `ppa-review`'s `scripts/serve.py` as a concrete working example.

Lessons learned from real reviews get folded back into `ppa-review`'s
`SKILL.md` and the bundled guide over time (see the git history, e.g. the
needs-packaging / native-package / install-test-and-autopkgtest lessons from
reviewing `dgx-server-defaults`).

## Reusing just the skills

Because each skill is a self-contained folder under `.opencode/skills/`
(scripts and reference material bundled alongside `SKILL.md`, every internal
path relative to that folder), you can copy **just one skill folder** into a
different project's own `.opencode/skills/` directory and it keeps working
there with no further setup:

```sh
# From this repo, copy just the PPA-review skill elsewhere:
cp -r .opencode/skills/ppa-review  /path/to/other-project/.opencode/skills/

# Or just the generic "serve a markdown file" knowledge, with nothing else:
cp -r .opencode/skills/serve-markdown  /path/to/other-project/.opencode/skills/
```

The only thing `ppa-review`'s scripts assume is that a `var/` (and
`var/reports/`) directory exists at the root of wherever the containing
project lives, four levels above the skill's own directory — create those
(empty is fine) if they don't already exist:

```sh
mkdir -p /path/to/other-project/var/reports
```

If you also want the push-based auto-wake plugin to work in the new project,
register it the same way described in [Setup step
6](#6-optional-wire-up-the-opencode-auto-wake-plugin) below, pointing at the
copy's `review-notify.ts`.

## State & logs (gitignored, local only)

Everything mutable lives under `var/`, tracked in git only via two
placeholder `var/.gitkeep` / `var/reports/.gitkeep` files (so the directories
always exist right after a fresh clone, before any script has run):

- `var/.review-status.json` — current review target + per-step status (the
  "single source of truth").
- `var/.review-log` — append-only, timestamped activity log behind the
  panel.
- `var/.serve.pid` / `var/.serve.file` — which file `serve.py` is currently
  serving, and its PID, for `serve-ctl.sh`.
- `var/reports/Result_*.md` — per-package reports; working artifacts,
  intentionally not version-controlled.

## Setup (first time, from scratch)

Everything below assumes an Ubuntu (or close Debian derivative) machine —
this was built and tested on Ubuntu 24.04 LTS. You need: this repo, a handful
of Debian packaging tools, the `markdown` Python package, and (optionally,
for the auto-wake behavior) OpenCode itself with one plugin line in its
config.

### 1. Get the repo

If you don't already have it locally:

```sh
git clone <this-repo-url> ~/debpr   # or copy/unpack it however you received it
cd ~/debpr
```

(Everything in this guide assumes you're running commands from inside this
directory, unless a step says otherwise.)

### 2. Install the Debian packaging tools the review steps use

```sh
sudo apt-get update
sudo apt-get install -y \
  ubuntu-dev-tools \
  devscripts \
  lintian \
  quilt \
  dpkg-dev
```

This gives you: `pull-ppa-source`, `rmadison` (ubuntu-dev-tools); `licensecheck`,
`wrap-and-sort`, `uscan` (devscripts); `lintian`; `quilt`; and `dpkg-source`
(dpkg-dev). `sbuild` is **not** required — the toolkit relies on the PPA's own
Launchpad builds (`ppa.py builds`/`binaries`) instead of building locally.

### 3. Install the Python dependency for the web server

```sh
python3 -m pip install --break-system-packages markdown
```

`--break-system-packages` is needed on modern Ubuntu/Debian (PEP 668 marks
the system Python as externally managed); a virtualenv works too if you
prefer one. Verify it worked:

```sh
python3 -c "import markdown; print(markdown.__version__)"
```

### 4. Pick a bind address for the web server

`serve.py` has a hard-coded list of addresses it listens on
(`ADDRS = [...]` near the top of the file) — by default your machine's own
LAN IP (so it's reachable from other machines on your network) plus
`127.0.0.1` (loopback-only, always reachable from the same host). Find your
own LAN IP and edit that list if it doesn't already match:

```sh
hostname -I          # prints your IP(s), e.g. "192.168.1.42 ..."
```

If you only ever want to browse the panel from the same machine, you can
simplify `ADDRS` to just `["127.0.0.1"]`.

### 5. Start the web server

```sh
cd .opencode/skills/ppa-review/scripts
chmod +x serve-ctl.sh        # first time only, if not already executable
./serve-ctl.sh start
cd -   # back to the repo root
```

Expected output: `started (pid NNNNN) serving docs/Package-Review-Guidelines.md`.
Open `http://127.0.0.1:8000/debpr/Package-Review-Guidelines.md` (or your LAN
IP instead of `127.0.0.1`) in a browser — you should see the review guide
rendered as a styled page. Troubleshooting:

```sh
.opencode/skills/ppa-review/scripts/serve-ctl.sh status   # running or stopped?
tail -f /tmp/debpr-serve.log                               # see why it failed to start
```

### 6. (Optional) Wire up the OpenCode auto-wake plugin

Skip this step if you'll drive reviews entirely by hand (step 8 below still
works fine without it — you'll just need to re-check progress yourself
instead of being auto-notified). To enable it, add the plugin's absolute
path to OpenCode's own config file (create the file if it doesn't exist):

```sh
mkdir -p ~/.config/opencode
cat > ~/.config/opencode/opencode.jsonc <<EOF
{
  "\$schema": "https://opencode.ai/config.json",
  "plugin": ["file://$(pwd)/.opencode/skills/ppa-review/scripts/review-notify.ts"]
}
EOF
```

(If you already have an `opencode.jsonc` with other settings, just add this
repo's plugin path to its existing `"plugin"` array instead of overwriting
the file — and don't list the same plugin file under two different config
locations at once, or it may load twice and double up its wake-up prompts.)
OpenCode picks up config changes automatically (`/reload` to force it).

That's the whole setup. You now have a running web server and (optionally) a
plugin that watches for review progress — on to actually using it.

## Quick start — using it day to day

```sh
cd .opencode/skills/ppa-review/scripts

# Serve the guide at http://<addr>:8000/debpr/Package-Review-Guidelines.md
./serve-ctl.sh start                                   # defaults to the guide
# The PPA submission form and live panel are routes baked into serve.py itself,
# not separate .md files: http://<addr>:8000/debpr/Package-Review-Frontend
./serve-ctl.sh var/reports/Result_<pkg>.md             # switch to a report instead
# (the file argument is always relative to the REPO ROOT, not your current
# directory, regardless of where you run serve-ctl.sh from -- or pass an
# absolute path)
./serve-ctl.sh stop

# Drive a review by hand (normally the web form + plugin do this)
python3 review_status.py init OWNER/ARCHIVE pkg series
python3 review_status.py run-all
python3 review_status.py remaining
python3 review_status.py step control warn "wrap-and-sort clean; should-fix: ..."
python3 review_status.py severity
python3 review_status.py report /debpr/Result_pkg.md
```

See `references/Package-Review-Guidelines.md` Appendix B (reachable from the
repo root at `docs/Package-Review-Guidelines.md`) for the underlying
`rmadison`/`uscan`/`licensecheck`/`quilt`/`lintian` command reference used
while working the judgment steps.

## Worked example, start to finish

This walks through reviewing a real package, `smc-tools`, from
`ppa:fheimes/test` — the same one behind `var/reports/Result_smc-tools.md` in
this repo, so you can compare your own output against a finished report.

### Option A — via chat (recommended for a novice)

With the web server running (Setup step 5) and, ideally, the OpenCode plugin
loaded (Setup step 6), just tell your OpenCode agent:

> Review `ppa:fheimes/test`, package `smc-tools`.

The agent discovers and loads the `ppa-review` skill, normalizes the PPA,
lists its packages, confirms `smc-tools` with you if there's more than one
candidate, then runs `review_status.py init` + `run-all` for you. A few
seconds later either the plugin wakes the agent automatically, or the agent
simply continues in the same turn — either way it works through the
judgment steps from the bundled guide and writes
`var/reports/Result_smc-tools.md`. Watch it happen live at
`http://<addr>:8000/debpr/ppa/status`, or just wait for the agent's final
summary in chat.

### Option B — driving it by hand from a terminal

If you want to see every step explicitly (or you're not using an agent at
all), run everything from the skill's own `scripts/` directory:

```sh
cd .opencode/skills/ppa-review/scripts

# 1. List what's in the PPA, and normalize the reference
python3 ppa.py ppa:fheimes/test

# 2. Start a review of one specific package (owner/archive, package, series)
python3 review_status.py init fheimes/test smc-tools resolute

# 3. Run the mechanical pipeline: fetch source, source lintian,
#    binary builds, binary lintian. Watch it work:
python3 review_status.py run-all
tail -f ../../../../var/.review-log       # Ctrl-C once it says "Mechanical checks complete"

# 4. See what's left to review by hand
python3 review_status.py remaining
#   classify         Classify (PATCH/SRU/new)         pending
#   watch            debian/watch                     pending
#   changelog        debian/changelog                 pending
#   ...

# 5. Go through references/Package-Review-Guidelines.md section by section
#    against the fetched source (its path is printed by run-all, and
#    recorded in /tmp/opencode/ppa-review/.last-source):
cat /tmp/opencode/ppa-review/.last-source
cd "$(cat /tmp/opencode/ppa-review/.last-source)"
uscan --watchfile debian/watch --verbose     # §2
dpkg-parsechangelog                          # §3
wrap-and-sort -tvk -d . --dry-run            # §4 (drop --dry-run to apply)
licensecheck -r .                            # §5
quilt push -a && quilt pop -a                # §6, if debian/patches exists
cd -   # back to .opencode/skills/ppa-review/scripts

# 6. Record your verdict for each step as you reach it
python3 review_status.py step classify done "PATCH upload, resolute devel, version checks out"
python3 review_status.py step watch done "uscan finds new upstream releases fine"
python3 review_status.py step changelog fail "placeholder LP: #1234567 - must-fix"
python3 review_status.py step control warn "Maintainer should use update-maintainer - should-fix"
python3 review_status.py step copyright warn "stale copyright years - should-fix"
python3 review_status.py step patches warn "two patches missing Forwarded: field - should-fix"
python3 review_status.py step symbols skip "n/a: no shared library ABI"
python3 review_status.py step install-test done "installed smc-tools_*.deb cleanly in a throwaway container"
python3 review_status.py step autopkgtest skip "n/a: package has no debian/tests/control and none is expected here"

# 7. See the running tally of findings at any point
python3 review_status.py severity

# 8. Write var/reports/Result_smc-tools.md (by hand, or ask an agent to draft
#    it from the gathered evidence), then link and close out the review
python3 review_status.py report /debpr/Result_smc-tools.md
python3 review_status.py step report done "Changes requested: 2 must-fix, 3 should-fix"

# 9. Read the finished report in your browser
#    http://<addr>:8000/debpr/Result_smc-tools.md
```

At any point, `python3 review_status.py show` prints the full current state
as JSON, and `python3 review_status.py steps` lists every canonical step id
so you don't have to guess spellings.
