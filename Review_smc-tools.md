# Review: smc-tools 1.8.7-0ubuntu1 (ppa:fheimes/test)

- **Package:** smc-tools
- **Version:** 1.8.7-0ubuntu1
- **Target:** resolute (Ubuntu devel), universe
- **PPA:** https://launchpad.net/~fheimes/+archive/ubuntu/test
- **Source:** `/tmp/opencode/ppa-review/smc-tools-1.8.7`
- **Reviewed against:** `Package-Review-Guide_README.md`

## Verdict

**Changes requested.** No blocking build/license errors, but there are several
correctness issues that should be fixed before sponsoring — most importantly a
**non-functional `debian/watch`** and a **placeholder `LP: #` bug number** in
the changelog.

| # | Section | Result |
|---|---------|--------|
| 1 | Classify | warn |
| 2 | debian/watch | **fail** |
| 3 | debian/changelog | warn |
| 4 | debian/control | warn |
| 5 | debian/copyright | warn |
| 6 | Patches (quilt)/DEP-3 | pass |
| 7 | Symbols & ABI | n/a |
| 8 | Lintian (source package) | warn (0 E, 2 W) |
| 9 | Binary builds (PPA) | pass (5/5 arches) |
| 10 | Lintian (binary packages) | warn (0 E) |

## Must fix (blocking)

1. **`debian/watch` is malformed and non-functional.**
   The file uses a `Version: 5` / `Template: Github` / `Owner:` / `Project:`
   syntax that is **not** valid uscan format. `uscan` parses it as an obsolete
   *version 1* watch file and skips every line, so upstream version tracking
   does not work at all. Lintian also flags
   `missing-debian-watch-file-standard`.
   - A valid v5 file must start with lowercase `version=5` and contain a real
     URL/match line, e.g. for GitHub tags:
     ```
     version=5
     opts="mode=git,pgpmode=none" \
       https://github.com/ibm-s390-linux/smc-tools.git \
       refs/tags/v?(\d[\d.]*)
     ```
   - Note also the **wrong upstream org**: `Owner: ibm-s390-tools`, while the
     real repo (and `Homepage:`) is `github.com/ibm-s390-linux/smc-tools`.

2. **Placeholder bug reference in `debian/changelog`.**
   The top entry reads `New upstream release. (LP: #1234567)`. `#1234567` is a
   placeholder, not a real Launchpad bug. Replace it with the actual bug number
   or drop the `LP:` tag. The entry is also unusually terse compared to the
   detailed history below it.

## Should fix (non-blocking)

3. **Stale copyright years (`debian/copyright`).**
   `Files: *` declares `Copyright: 2016-2018 IBM Corp`, but source files carry
   IBM Corp copyright through **2021**. Lintian: `update-debian-copyright 2018
   vs 2026`. Extend the year ranges (and the `debian/*` 2018 Canonical stanza).

4. **Maintainer field (`debian/control`).**
   `Maintainer: Dimitri John Ledkov <xnox@ubuntu.com>` (personal). Ubuntu
   convention for archive uploads is
   `Maintainer: Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>`
   (with `XSBC-Original-Maintainer` if applicable).

5. **Forward the portability/typo patches.**
   `fix_folder_31_32_bit_systems.patch` and `fix_typo_in_manual_page.patch` are
   `Forwarded: no`. These are generally useful upstream — submit them and set
   `Forwarded:` to the URL. (`fix_library_path.patch` `not-needed` is fine.)

## Nice to have

- Add `debian/upstream/metadata` (lintian `upstream-metadata-file-is-missing`).
- Set `Rules-Requires-Root: no` in `debian/control` (lintian pedantic
  `silent-on-rules-requiring-root`).

## What passed

- **Classification:** new-upstream-version update to the devel release
  (resolute); not an SRU. Archive has 1.8.3 (noble) / 1.8.5 (questing); 1.8.7
  is already in resolute/stonking.
- **Patches:** all 3 apply cleanly via `quilt push -a` (no fuzz/offset) and
  carry complete DEP-3 headers.
- **control:** `wrap-and-sort -n` clean; `debhelper-compat (= 13)`;
  `Standards-Version: 4.7.2` (current — the lintian `newer-standards-version`
  warning is a false positive from an older lintian DB); source format
  `3.0 (quilt)`.
- **copyright:** valid DEP-5; EPL-1.0 with full license text; no conflicting
  licenses detected (`licensecheck`).
- **Symbols/ABI:** n/a — `libsmc-preload.so` is an `LD_PRELOAD` shim with no
  SONAME/public ABI, so no symbols file is required.
- **Binary builds (PPA):** **all 5 architectures built successfully** —
  amd64, arm64, armhf, ppc64el, s390x. No failed builds; no build log to chase.

## Lintian — full results

Two runs: `lintian -EvIL +pedantic` on the source `.dsc`, and the same on the
published binary `.deb`. Severities map to the review as: **E (error) = must
fix**, **W (warning) = should fix**; I/P/X are informational.

### Lintian errors (must fix)

**None.** Both the source package and the binary package produced **0 errors**.

### Lintian warnings (should fix)

Source package (`smc-tools_1.8.7-0ubuntu1.dsc`) — 2 warnings:

| Tag | Location | Meaning / action |
|-----|----------|------------------|
| `missing-debian-watch-file-standard` | `debian/watch` | The watch file doesn't start with a `version=` line, so lintian can't read its standard — corroborates the broken watch (Must-fix #1). Fix `debian/watch` to a real `version=5` file. |
| `newer-standards-version 4.7.2 (current is 4.6.2)` | `debian/control` | **False positive here** — the package's `Standards-Version: 4.7.2` is *newer* than this (older) lintian's database knows about. No action; nothing to downgrade. |

Binary package (`smc-tools_1.8.7-0ubuntu1_amd64.deb`) — 1 real warning
(+ 24 environment-noise warnings, see below):

| Tag | Location | Meaning / action |
|-----|----------|------------------|
| `no-manual-page` | `usr/bin/smc_dbg` | The `smc_dbg` binary installed in `/usr/bin` ships no man page. Every program in `/usr/bin` should have one (a symlink to a shared page is acceptable). Add a man page or a symlink. |

Environment-noise warnings (NOT package defects — do not action):

- 24 × `groff-message` of two kinds — 11 × `command exited with status 2` and
  13 × `troff: Segmentation fault (core dumped)` — across
  `af_smc.7`, `smc_pnet.8`, `smc_run.8`, `smcd-device.8`, `smcd-info.8`,
  `smcd-linkgroup.8`, `smcd-seid.8`, `smcd-stats.8`, `smcd-ueid.8`, `smcd.8`,
  `smcr.8`, `smcss.8`. These come from a **broken groff/troff in this review
  container** (troff is literally segfaulting), not from the man pages
  themselves. Re-check on a normal builder before trusting them.

### Lintian info / pedantic (nice to have)

| Tag | Where | Note |
|-----|-------|------|
| `hardening-no-bindnow` (I) | binary `usr/lib/libsmc-preload.so` | Build with now-binding hardening flags. |
| `patch-not-forwarded-upstream` (I, ×2) | `fix_folder_31_32_bit_systems.patch`, `fix_typo_in_manual_page.patch` | See Should-fix #5. |
| `renamed-tag` (P) | binary `usr/share/lintian/overrides/smc-tools:4` | Update the override `ldconfig-symlink-missing-for-shlib` → `lacks-versioned-link-to-shared-library`. |
| `silent-on-rules-requiring-root` (P) | `debian/control` | Set `Rules-Requires-Root: no`. |
| `update-debian-copyright 2018 vs 2026` (X) | `debian/copyright:232` | See Should-fix #3. |
| `upstream-metadata-file-is-missing` (X) | source | Add `debian/upstream/metadata`. |

## What else passed

- **Classification:** new-upstream-version update to the devel release
  (resolute); not an SRU. Archive has 1.8.3 (noble) / 1.8.5 (questing); 1.8.7
  is already in resolute/stonking.
- **Patches:** all 3 apply cleanly via `quilt push -a` (no fuzz/offset) and
  carry complete DEP-3 headers.
- **control:** `wrap-and-sort -n` clean; `debhelper-compat (= 13)`;
  `Standards-Version: 4.7.2` (current); source format `3.0 (quilt)`.
- **copyright:** valid DEP-5; EPL-1.0 with full license text; no conflicting
  licenses detected (`licensecheck`).

## Commands used

```sh
./fetch-source.sh                                  # pull-ppa-source + extract
rmadison smc-tools                                 # archive versions
uscan --watchfile debian/watch --no-download ...   # watch check (rejected)
wrap-and-sort -n -a                                # control tidiness (clean)
licensecheck -r .                                  # copyright cross-check
QUILT_PATCHES=debian/patches quilt push -a         # patch apply (clean)
lintian -EvIL +pedantic smc-tools_1.8.7-0ubuntu1.dsc
./check-binaries.sh                                # build status + download debs
lintian -EvIL +pedantic *.deb                      # binary lintian
```

> No signed build and no upload were performed (read-only review). No local
> binary build (`sbuild` unavailable); instead the PPA's own binary builds were
> checked via Launchpad and the published `.deb`s were lint-checked.
