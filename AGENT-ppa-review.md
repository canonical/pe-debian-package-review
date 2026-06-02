# AGENT-ppa-review.md — Reviewing a Launchpad PPA

How an agent takes a PPA reference and reviews its package(s) per
`Package-Review-Guide_README.md`.

## Input: how a PPA gets specified

A PPA can be given in two equivalent forms:

- Launchpad URL: `https://launchpad.net/~OWNER/+archive/ubuntu/ARCHIVE`
- add-apt-repository spec: `ppa:OWNER/ARCHIVE`

Two ways to receive one:

1. **Web form** — the user visits `http://<addr>:8000/debpr/ppa`, submits the
   PPA, and `serve.py` records it (normalized) to `.ppa-request` as a
   tab-separated line: `<timestamp>\tppa:owner/archive\t<url>`. The agent reads
   the latest line from `.ppa-request`.
2. **In chat** — the user pastes either form directly.

Normalize either form with `ppa.py`:

```sh
python3 ppa.py <ppa-ref>        # prints the PPA and lists published sources
```
or in code: `import ppa; owner, archive = ppa.normalize(ref)`.

## Step 1 — List the packages

Query the Launchpad API (no auth needed for public PPAs) and list published
sources with name, version, and series:

```sh
python3 ppa.py ppa:OWNER/ARCHIVE
```

If there are several packages, confirm with the user which one(s) to review
(reviewing all can be large). Record the chosen targets.

## Step 2 — Fetch the source

For each chosen package, pull the source for its series (no signing, no upload).
Use the helper, which reads the latest pick from `.ppa-request`, cleans the
scratch dir, and runs the correct command:

```sh
./fetch-source.sh                       # uses the picked package in .ppa-request
./fetch-source.sh OWNER/ARCHIVE PKG SERIES   # or specify explicitly
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

Apply `Package-Review-Guide_README.md`. The high-value, tool-backed checks that
run without a full binary build:

- **Classify** the upload (needs-packaging / PATCH / SRU) and confirm the target
  series/pocket; compare with existing versions: `rmadison <package>`.
- **debian/watch**: present, `version=5` for new packages;
  `uscan --watchfile debian/watch --verbose` (or `--safe`).
- **debian/changelog**: version string correct for the case (see the guide's
  versioning sub-bullets), target release, signature line, `LP: #` reference,
  active-voice entries.
- **debian/control**: `wrap-and-sort` clean, `Architecture`, `Section`,
  latest `Standards-Version` (especially for new packages),
  `XSBC-Original-Maintainer`.
- **debian/copyright**: `licensecheck -r .` and cross-check; all `debian/*`
  copyright holders listed; no stale `Files:` patterns.
- **Patches/quilt**: DEP-3 headers; `QUILT_PATCHES=debian/patches quilt push -a`
  applies with no fuzz; `quilt pop -a`; `series` consistent; `3.0 (quilt)` not
  editing upstream directly.
- **Symbols/ABI**: libraries ship up-to-date symbols; SONAMEs consistent.
- **Lintian (source package)**: `lintian -EvIL +pedantic <package>_<version>.dsc`
  on the source; zero E, ideally zero W.

## Step 3b — Binary builds & binary lintian

Check the PPA's own binary builds and lint the resulting `.deb`s:

```sh
./check-binaries.sh                 # uses the pick in .ppa-request
./check-binaries.sh OWNER/ARCHIVE PKG SERIES
```

- **Binary builds (PPA)**: `python3 ppa.py builds ppa:OWNER/ARCHIVE PKG SERIES`
  prints the per-architecture state from Launchpad. If any arch is not
  "Successfully built", report it and **reference the build-log URL** that the
  command prints (the helper exits non-zero so the step is flagged). The helper
  also downloads the published binaries (`pull-ppa-source -p debs`) into
  `/tmp/opencode/ppa-review`.
- **Lintian (binary packages)**: run explicitly on every downloaded `.deb`:
  ```sh
  cd /tmp/opencode/ppa-review && lintian -EvIL +pedantic *.deb
  ```
  Note: binary lintian catches issues source lintian can't (man pages,
  hardening, shlib symlinks, stale overrides). Ignore environment-induced noise
  (e.g. a broken groff/troff producing `groff-message … Segmentation fault`).
- Optional **source build**: `dpkg-buildpackage -S -us -uc` (no `sbuild` here, so
  no local binary build — rely on the PPA's builds above).

## Step 4 — Report

Write a per-package report `Review_<package>.md` summarizing each guide section
as pass / warn / fail with evidence (command output snippets). Serve it on the
same server (serve.py renders any repo-local `/debpr/<name>.md`) and link it
from the status panel:

```sh
python3 review_status.py report /debpr/Review_<package>.md
```
then share `http://10.72.172.152:8000/debpr/Review_<package>.md`.

The `_` separator (not `-`) makes the package-name boundary unambiguous when
the package name itself contains hyphens (e.g. `Review_smc-tools.md`).

## Guardrails (from the guide, Appendix A)

- Never make **signed** builds; never **upload** to an archive or PPA.
- Keep build output quiet but logged; re-run checks after any change.
- If a tool or piece of info is missing, stop and report rather than guess.
- Only modify files under a scratch tree; never the served repo's guide.
