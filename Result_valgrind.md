# PPA Review: valgrind 1:3.26.0-0ubuntu2

- **PPA:** ppa:fheimes/test
- **Source package:** valgrind
- **Version:** 1:3.26.0-0ubuntu2
- **Series:** resolute
- **Binary packages:** valgrind, valgrind-mpi
- **Reviewer:** OpenCode (Claude Opus 4.8)
- **Date:** 2026-06-03

## Verdict: Changes requested

No hard blockers to building/installing, but `debian/watch` is **non-functional**
(must-fix) and copyright year ranges are stale (should-fix). Everything else is in
good shape: the package builds, lintian is clean, and the Ubuntu deltas are
well-documented.

---

## Summary of findings

| Area | Verdict | Severity |
|------|---------|----------|
| Classification | New upstream + merge | — |
| debian/watch | **Broken** | must-fix |
| debian/changelog | Pass | — |
| debian/control | Pass | — |
| debian/copyright | Stale years | should-fix |
| debian/patches | Pass (minor) | nice-to-have |
| Symbols & ABI | N/A | — |
| Lintian (source) | Clean | — |
| Binary builds | OK | — |
| Lintian (binary) | Clean | — |

---

## Classification

New upstream release (3.26.0) of a long-standing package, uploaded to the devel
series **resolute** with epoch `1:`. Ubuntu is ahead of Debian (`-0ubuntuX`). The
top entry `-0ubuntu2` only "squashed lintian overrides"; `-0ubuntu1` is the real
new-upstream work, preceded by a merge with Debian unstable. Changelog cites real
Launchpad bugs (#2139096, #2130072).

## Must-fix

### debian/watch is non-functional
Same defect class as the earlier smc-tools review. The file uses a key/value style
(`Version: 5`, `Source:`, `Matching-Pattern:`, `Pgpsigurlmangle:`, `Uversionmangle:`)
that is **not valid uscan syntax**. `uscan` parses it as an obsolete version-1 watch
file and **skips every line**, so upstream version tracking is dead.

The `-0ubuntu1` changelog even claims *"d/watch: update to version 5"*, but the file
as shipped does nothing. It needs a real watch file, e.g.:

```
version=4
opts="pgpsigurlmangle=s/$/.asc/,uversionmangle=s/\.RC/~RC/" \
  https://sourceware.org/pub/valgrind/ valgrind-(.+)\.tar\.bz2
```

(verify the actual download URL/regex against the upstream release location).

## Should-fix

### debian/copyright — stale year ranges
DEP-5 machine-readable; predominantly GPL-2.0+ (70 stanzas) plus BSD-3-Clause,
LGPL-2.0+, LGPL-2.1+. The `Files: *` stanza Copyright stops at **2000-2012**
(Julian Seward), but upstream 3.26.0 is a 2024/2025 release — the year ranges need
refreshing. The large `licensecheck` UNKNOWN count is dominated by test fixtures and
generated inputs under the test tree, not a real licensing gap.

## Nice-to-have

- **debian/patches:** all 9 patches carry DEP-3 headers. A couple
  (`armv7-illegal-opcode.patch`, `13_fix-path-to-vgdb.patch`) lack an explicit
  `Forwarded:` field — worth adding for completeness.
- **debian/changelog:** the `-0ubuntu2` entry ("squashed lintian overrides") is terse.

## Passing / not applicable

- **debian/control:** Maintainer set to Ubuntu Developers with
  `XSBC-Original-Maintainer` (Ghedini) and Uploaders preserved; Standards-Version
  4.7.2 (current); Vcs-Git/Vcs-Browser present; clear binary descriptions;
  Breaks/Replaces valgrind-dev. No issues.
- **debian/changelog:** well-formed, correct epoch, valid signoffs, real LP bugs,
  itemized merge deltas and dropped (now-upstream) patches.
- **Symbols & ABI:** N/A — valgrind ships no public shared library and no `-dev`
  package; no `debian/*.symbols`. valgrind-mpi's libmpiwrap is an LD_PRELOAD helper
  with no tracked SONAME/ABI.
- **Lintian (source + binary):** clean (no errors; no actionable warnings beyond
  review-container artifacts).
- **Binary builds:** built successfully on the PPA.

## Recommendation

Request changes: fix `debian/watch` so uscan works (must-fix) and refresh
`debian/copyright` year ranges (should-fix). The remaining items are minor. Once the
watch file is corrected the upload is otherwise in good shape for the devel series.
