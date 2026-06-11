# Review: secvarctl 1.1.0-0ubuntu2 (ppa:fheimes/test)

- **Package:** secvarctl
- **Version:** 1.1.0-0ubuntu2
- **Target:** plucky (Ubuntu)
- **PPA:** https://launchpad.net/~fheimes/+archive/ubuntu/test
- **Source:** `/tmp/opencode/ppa-review/secvarctl-1.1.0`
- **Reviewed against:** `Package-Review-Guidelines.md`

## Verdict

**Changes requested.** No build or lintian errors and both architectures build,
and there are **no hard blockers**. However, several should-fix items need
attention before sponsoring — most importantly **debian/copyright completeness**
for the bundled third-party code.

| # | Step | Result |
|---|------|--------|
| 1 | Classify (PATCH/SRU/new) | pass |
| 2 | debian/watch | should-fix |
| 3 | debian/changelog | should-fix |
| 4 | debian/control | should-fix |
| 5 | debian/copyright | should-fix (priority) |
| 6 | debian/patches (quilt/DEP-3) | pass |
| 7 | Symbols & ABI | n/a |
| 8 | Lintian (source package) | 0 E, 1 W |
| 9 | Binary builds (PPA) | pass (2/2 arches) |
| 10 | Lintian (binary packages) | 0 E (container noise only) |

## Classification

Ubuntu-only package (`-0ubuntu2`, no Debian revision) targeting **plucky**. The
`-0ubuntu2` upload keeps upstream **1.1.0** and only changes packaging
("python3"). Not an SRU, not needs-packaging.

## Must fix (blocking)

None — there are no build, license-breaking, or lintian errors.

## Should fix (non-blocking)

1. **`debian/copyright` — priority.**
   - **Bundled third-party code is not attributed.** `Files: *` lumps everything
     under `Apache-2.0`, but the source bundles `external/skiboot/ccan/*` and
     other `external/` trees whose ccan/skiboot modules carry their own licences
     (commonly CC0 / MIT / LGPL / GPL). `licensecheck -r` cannot attribute ~353
     files. Audit `external/` and add explicit `Files:` paragraphs. *(For an
     actual archive/MIR upload this would be a must-fix.)* The already-declared
     `libstb-secvar-main/*` (BSD-2-Clause), `external/linux/.clang-format`
     (GPL-2.0) and `debian/*` (GPL-3) are fine.
   - **Stale years:** `Files: *` says `2013-2019 IBM Corp.` but upstream sources
     are dated to **2023**. Update the span.

2. **`debian/watch` matches pre-release tags.** It is functional (`version=4`,
   GitHub tags) and `uscan` parses it, but it reports **`1.1.0-rc1` as newer**
   than the released `1.1.0`. Add a `uversionmangle`/filter to drop `-rc`/`-pre`
   tags (and consider bumping to `version=5`), e.g.:
   ```
   version=4
   opts="uversionmangle=s/-?rc\d+//" \
     https://github.com/open-power/secvarctl/tags \
     .*/v?(\d[\d.]*)\.(?:tgz|tbz2|tar\.(?:gz|bz2|xz))
   ```

3. **`debian/changelog`.** The `-0ubuntu2` entry `* new version, python3` is
   vague and misleading — it is **not** a new upstream version (still 1.1.0); it
   is a packaging change. Describe what actually changed, in active voice.

4. **`debian/control`.**
   - `Standards-Version: 4.7.0` → bump to **4.7.2** (current).
   - Trailing whitespace on the `Build-Depends:`, `Architecture:` and `Depends:`
     lines — run `wrap-and-sort`.
   - Weak `Description`: the synopsis starts with "To manipulate…" (use a noun
     phrase) and the long-description first line "x86 works for file generation
     and validation." is unclear/ungrammatical. Reword.
   - `Maintainer: Ubuntu Developers …` is correct.

## Passing / not applicable

- **debian/patches (DEP-3):** the single `adjust_paths_for_libstb-secvar.patch`
  applies cleanly (no fuzz) with complete DEP-3 headers (`Forwarded: not-needed`,
  Ubuntu-specific). Nit: use `Bug-Ubuntu:` rather than generic `Bug:` for the LP
  URL.
- **Symbols & ABI: n/a.** The binary ships only `/usr/bin/secvarctl` (CLI); no
  shared library/SONAME (libstb-secvar is linked in), so no ABI tracking.

## Tool output

### Lintian — source package (0 errors, 1 warning)

```
W: secvarctl source: newer-standards-version 4.7.0 (current is 4.6.2)
```

- **False positive**: this lintian's database predates Policy 4.7.0. (Separately,
  bumping to 4.7.2 is recommended — see should-fix #4.)

### Binary builds (PPA) — 2/2 architectures

`amd64` and `ppc64el` both **Successfully built**. (The package restricts
`Architecture` to these two.)

### Lintian — binary packages (0 errors)

The only tags are `groff-message … troff: Segmentation fault` on
`secvarctl.1.gz` — **review container artifacts** (troff/groff crash in this
environment), not package defects. The package does ship a man page.

## Summary for the uploader

No blockers, but please complete `debian/copyright` for the bundled `external/`
code (and refresh the year span), tighten `debian/watch` against pre-release
tags, rewrite the thin `-0ubuntu2` changelog entry, and clean up
`debian/control` (Standards-Version, whitespace, Description).
