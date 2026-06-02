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

For each chosen package, pull the source for its series (no signing, no upload):

```sh
pull-ppa-source --ppa OWNER/ARCHIVE <package> <series>
# fallback: dget the .dsc from the PPA's +sourcepub listing
dpkg-source -x <package>_<version>.dsc      # extract into a tree
```

Work inside `/tmp/opencode/ppa-review/<package>` to keep the repo clean.

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
- **Lintian**: `lintian -EviL -pedantic <package>_<version>.dsc` on the source
  (and on `*.deb` if binaries are available); zero E, ideally zero W.
- Optional **source build**: `dpkg-buildpackage -S -us -uc` (no `sbuild` here, so
  no full binary build).

## Step 4 — Report

Write a per-package report `review-<package>.md` summarizing each guide section
as pass / warn / fail with evidence (command output snippets). Serve it on the
same server:

```sh
./serve-ctl.sh review-<package>.md
```
then share `http://10.72.172.152:8000/debpr/review-<package>.md`.

## Guardrails (from the guide, Appendix A)

- Never make **signed** builds; never **upload** to an archive or PPA.
- Keep build output quiet but logged; re-run checks after any change.
- If a tool or piece of info is missing, stop and report rather than guess.
- Only modify files under a scratch tree; never the served repo's guide.
