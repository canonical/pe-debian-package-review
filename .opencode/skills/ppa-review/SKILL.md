---
name: PPA Package Review
description: Review a Debian/Ubuntu source package published in a Launchpad PPA against the PE package-review checklist -- fetch its source, run Lintian and PPA binary builds, work the judgment steps (classification, debian/watch, changelog, control, copyright, patches, symbols & ABI, install/upgrade test, autopkgtest), and write a Result_<package>.md report. Use this whenever asked to review a PPA, a Launchpad package, or "ppa:owner/archive".
---

# PPA Package Review

How to take a Launchpad PPA reference and review its package(s) per
`references/Package-Review-Guidelines.md` (bundled with this skill).

All relative paths below (`scripts/...`, `references/...`) are relative to
**this skill's own directory** (the one containing this file). When this
skill is loaded, start by `cd`-ing to that directory — every command below
assumes that as the working directory, so this skill keeps working whether
it lives inside the full `debpr` repo or has been copied standalone
somewhere else (its scripts find their own repo root automatically, as long
as the repo root's `var/` directory exists — see "Where things are written"
below).

## Input: how a PPA gets specified

A PPA can be given in two equivalent forms:

- Launchpad URL: `https://launchpad.net/~OWNER/+archive/ubuntu/ARCHIVE`
- add-apt-repository spec: `ppa:OWNER/ARCHIVE`

Two ways to receive one:

1. **Web form** — the user visits `http://<addr>:8000/debpr/Package-Review-Frontend`, submits the
   PPA, and picks a package. `scripts/serve.py` then calls `review_status.init`
   to create the review state file (`<repo-root>/var/.review-status.json`) —
   the **single source of truth** for the target
   (owner/archive/package/series). The agent (and `ppa.py`) read the target
   from there.
2. **In chat** — the user pastes either form directly.

Normalize either form with `ppa.py`:

```sh
python3 scripts/ppa.py <ppa-ref>        # prints the PPA and lists published sources
```
or in code: `import ppa; owner, archive = ppa.normalize(ref)`.

## Where things are written

This skill writes all runtime state under `<repo-root>/var/` (the repo root
is found automatically by walking up from `scripts/`): the review state file
and activity log (`var/.review-status.json`, `var/.review-log`), and
finished reports (`var/reports/Result_<package>.md`). If this skill folder
was copied somewhere *without* the rest of the `debpr` repo, create an empty
`var/` and `var/reports/` directory four levels above this skill's own
directory (i.e. at the root of wherever you placed it) before first use.

## Step 1 — List the packages

Query the Launchpad API (no auth needed for public PPAs) and list published
sources with name, version, and series:

```sh
python3 scripts/ppa.py ppa:OWNER/ARCHIVE
```

If there are several packages, confirm with the user which one(s) to review
(reviewing all can be large). Record the chosen targets.

## Scriptable steps in one shot (optional)

Picking a package on the web page now **auto-starts** the mechanical steps: the
server launches `review_status.py run-all` in the background (detached, guarded
so only one review runs at a time) and the status panel begins updating on its
own. You can also run it by hand — to re-run, or when driving a review without
the web UI:

```sh
python3 scripts/review_status.py run-all                          # uses var/.review-status.json
python3 scripts/review_status.py run-all OWNER/ARCHIVE PKG SERIES # or specify explicitly
```

It runs: Fetch source -> Lintian (source package) -> Binary builds (PPA) ->
Lintian (binary packages), stopping if the fetch fails. lintian uses
`--fail-on none`, so a finding (E:/W:) doesn't fail the step — every tag lands in
the panel log for you to triage. The **judgment** steps below (Classify,
debian/watch, changelog, control, copyright, patches, Symbols & ABI,
**Install/upgrade test, Tests (autopkgtest)**, Report) are still done by the
agent — the install/upgrade test and autopkgtest run are *not* part of the
automated `run-all` pipeline (they need a disposable environment to install
into) and must be driven by hand each time; see Step 3c. The individual steps
can also be run on their own, as described next.

### Driving the status panel

The panel reads `var/.review-status.json`. Update one step at a time as you
reach a verdict; `<id>` is a canonical step id (`python3
scripts/review_status.py steps` lists them) and matching tolerates a unique
substring:

```sh
python3 scripts/review_status.py step <id> <status> [note...]   # one step
python3 scripts/review_status.py run  <id> <cmd...>             # stream a cmd as a step
python3 scripts/review_status.py remaining                      # steps not yet reviewed
python3 scripts/review_status.py severity                        # findings: must-fix/should-fix
```

`<status>` is `pending|active|done|warn|fail|skip`. `warn` = should-fix,
`fail` = must-fix (these feed the `severity` buckets and the report). An
unknown/ambiguous `<id>` is **rejected** (never silently appended), so a typo
can't create a phantom step.

## Step 2 — Fetch the source

For each chosen package, pull the source for its series (no signing, no upload).
Use `ppa.py fetch`, which reads the target from `var/.review-status.json`,
cleans the scratch dir, and runs the correct command:

```sh
python3 scripts/ppa.py fetch                       # uses the target in var/.review-status.json
python3 scripts/ppa.py fetch OWNER/ARCHIVE PKG SERIES   # or specify explicitly
```

Under the hood that is:

```sh
pull-ppa-source --no-verify-signature --ppa OWNER/ARCHIVE <package> <series>
```

Notes / common mistakes:

- Use `pull-ppa-source`, **not** `pull-lp-source` — the latter pulls from the
  main Ubuntu archive and has no working PPA support.
- Pass the PPA as `OWNER/ARCHIVE` (no `ppa:` prefix) and **always** pass the
  `<series>`; otherwise it may look in the wrong release.
- Remove any existing extraction dir first — `pull-ppa-source` aborts with
  "Source unpack failed" if the target directory already exists.
- `--no-verify-signature` is expected here (PPA signing keys aren't imported);
  it must not abort a read-only review fetch.

Work inside `/tmp/opencode/ppa-review/<package>` to keep the repo clean. The
helper writes the extracted tree path to `/tmp/opencode/ppa-review/.last-source`.
If the helper isn't used, extract manually:

```sh
dpkg-source -x <package>_<version>.dsc      # extract into a tree
```

## Step 3 — Review against the guide

Apply `references/Package-Review-Guidelines.md`. The high-value, tool-backed
checks that run without a full binary build:

- **Classify** the upload (needs-packaging / PATCH / SRU) and confirm the target
  series/pocket; compare with existing versions: `rmadison <package>`. An
  **empty `rmadison` result confirms needs-packaging**. Check
  `debian/source/format` early — `3.0 (native)` means `debian/watch` and
  `debian/patches/` are **not applicable**, not defects.
- **debian/watch**: present, `version=5` for new packages;
  `uscan --watchfile debian/watch --verbose` (or `--safe`). N/A for native
  packages.
- **debian/changelog**: version string correct for the case (see the guide's
  versioning sub-bullets), target release, signature line, `LP: #` reference,
  active-voice entries. A single "Initial release" entry is normal for
  needs-packaging even at a high `ubuntuN`.
- **debian/control**: `wrap-and-sort` clean, `Architecture`, `Section`,
  latest `Standards-Version` (especially for new packages),
  `XSBC-Original-Maintainer`. Watch for empty metapackages
  (`empty-binary-package`) and a stale-lintian-database
  `newer-standards-version` false positive.
- **debian/copyright**: `licensecheck -r .` and cross-check; all `debian/*`
  copyright holders listed; no stale `Files:` patterns. Cross-check
  `Source:`/`Upstream-Name:` against `debian/control`'s
  `Vcs-Browser`/`Vcs-Git` — catches a copy-paste from a sibling package.
- **Patches/quilt**: DEP-3 headers; `QUILT_PATCHES=debian/patches quilt push -a`
  applies with no fuzz; `quilt pop -a`; `series` consistent; `3.0 (quilt)` not
  editing upstream directly. N/A for native packages.
- **Symbols/ABI**: libraries ship up-to-date symbols; SONAMEs consistent. N/A
  when no shared libraries are shipped (metapackages, config-only packages).
- **Lintian (source package)**: `lintian -EvIL +pedantic <package>_<version>.dsc`
  on the source; zero E, ideally zero W.

## Step 3b — Binary builds & binary lintian

Check the PPA's own binary builds and lint the resulting `.deb`s:

```sh
python3 scripts/ppa.py binaries                 # uses the target in var/.review-status.json
python3 scripts/ppa.py binaries OWNER/ARCHIVE PKG SERIES
```

- **Binary builds (PPA)**: `python3 scripts/ppa.py builds ppa:OWNER/ARCHIVE PKG SERIES`
  prints the per-architecture state from Launchpad. **Every architecture the
  package targets must show "Successfully built"** — this is a required
  pass/fail check, not optional. If any arch is not "Successfully built",
  that is a **must-fix** (blocker): report it and **reference the build-log
  URL** that the command prints. `ppa.py binaries` also downloads the
  published binaries (`pull-ppa-source -p debs`) into
  `/tmp/opencode/ppa-review`.
- **Lintian (binary packages)**: run explicitly on every downloaded `.deb`:
  ```sh
  cd /tmp/opencode/ppa-review && lintian -EvIL +pedantic *.deb
  ```
  Note: binary lintian catches issues source lintian can't (man pages,
  hardening, shlib symlinks, stale overrides). Ignore environment-induced
  noise (e.g. a broken groff/troff producing `groff-message … Segmentation
  fault`, or an `unknown-field Modaliases` false positive on packages using
  `dh-modaliases`).
- Optional **source build**: `dpkg-buildpackage -S -us -uc` (no `sbuild` here, so
  no local binary build — rely on the PPA's builds above).

## Step 3c — Install/upgrade test and package tests (required, not optional)

These two checks are **required for every review**, not "nice to have" —
mark them `done`/`fail` on the panel (`install-test`, `autopkgtest`) like any
other judgment step; don't silently skip them.

- **Install/upgrade test**: actually install the downloaded `.deb`(s) in a
  disposable environment (container/chroot/VM — never the review host
  directly) and confirm `postinst`/`preinst`/`prerm`/`postrm` all run
  cleanly:
  ```sh
  sudo apt-get install -y ./*.deb        # fresh install
  ```
  If an older version of the package is already published in the archive
  (check with `rmadison`), also test the **upgrade path** from that version
  to the one under review — install the old version first, then upgrade to
  the new `.deb`(s), and confirm the transition is clean (no leftover
  files/config from removed pieces, maintainer scripts idempotent). Record
  the exact commands and their outcome in the report. A failure here (crash,
  unhandled maintainer-script error, broken dependency) is a **must-fix**.
- **Tests (upstream test suite / autopkgtest)**: check for
  `debian/tests/control` and run it:
  ```sh
  sbuild --run-autopkgtest ...           # full build + autopkgtest
  # or, against already-built binaries:
  autopkgtest <package>_<version>.dsc -- <backend>
  ```
  All defined tests must **pass**. If the package has **no autopkgtest at
  all**, that absence is itself a finding to report — **must-fix for new
  packages** (the guide's §8/§11 require autopkgtests for needs-packaging),
  should-fix otherwise unless justified (e.g. genuinely nothing testable,
  such as a pure metapackage — say so explicitly in the report rather than
  leaving it unaddressed).

## Step 4 — Report

Write a per-package report `var/reports/Result_<package>.md` (three levels up
from this skill's own directory: `../../../var/reports/`) summarizing each
guide section as pass / warn / fail with evidence (command output snippets).
Serve it on the same server (`scripts/serve.py` renders any `.md` file found
by basename under `docs/` or `var/reports/`) and link it from the status
panel:

```sh
python3 scripts/review_status.py report /debpr/Result_<package>.md
```
then share `http://10.72.172.152:8000/debpr/Result_<package>.md` (or your
host's own address/port — see `scripts/serve.py`'s `ADDRS`/`PORT`).

The `_` separator (not `-`) makes the package-name boundary unambiguous when
the package name itself contains hyphens (e.g. `Result_smc-tools.md`).

## Guardrails (from the guide's Appendix A)

- Never make **signed** builds; never **upload** to an archive or PPA.
- Keep build output quiet but logged; re-run checks after any change.
- If a tool or piece of info is missing, stop and report rather than guess.
- Only modify files under a scratch tree; never this skill's own
  `references/Package-Review-Guidelines.md`.
