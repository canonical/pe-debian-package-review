# PPA Review: s390-tools 2.41.0-0ubuntu3

- **PPA:** ppa:fheimes/test
- **Source package:** s390-tools
- **Version:** 2.41.0-0ubuntu3
- **Series:** resolute
- **Binary packages:** s390-tools, s390-tools-data, s390-tools-cpuplugd,
  s390-tools-statd, s390-tools-osasnmpd, s390-tools-zkey,
  s390-tools-chreipl-fcp-mpath, libekmfweb1, libekmfweb-dev, libkmipclient1,
  libkmipclient-dev
- **Reviewer:** OpenCode (Claude Opus 4.8)
- **Date:** 2026-06-03

## Verdict: Changes requested

No hard blockers: the package builds on all four architectures and lintian
reports **zero errors**. However `debian/watch` is **non-functional** (must-fix),
and `debian/copyright` is **incomplete** for bundled zlib and LGPL-2.1+ files
(should-fix). Patch metadata and a couple of binary-lintian overrides also need
attention.

---

## Summary of findings

| Area | Verdict | Severity |
|------|---------|----------|
| Classification | Ubuntu delta to devel | — |
| debian/watch | **Broken** | must-fix |
| debian/changelog | Pass | — |
| debian/control | Pass | — |
| debian/copyright | Incomplete (zlib, LGPL) | should-fix |
| debian/patches | DEP-3 gaps | should-fix |
| Symbols & ABI | Pass | — |
| Lintian (source) | 0 E, 2 W | — |
| Binary builds | 4/4 OK | — |
| Lintian (binary) | 0 E, minor W | should-fix |

---

## Classification

An Ubuntu-delta upload (`2.41.0-0ubuntu3`) to the development series **resolute**.
The version under review matches what is already published in resolute
(`rmadison`: `2.41.0-0ubuntu3 | resolute`). The `-0ubuntu3` change is a packaging
bugfix: correcting the path for `.so` files in the `s390-tools-zkey` initramfs
hook to `/usr/libexec` (LP: #2147107). Not a new upstream release, not an SRU to a
stable pocket — a normal devel-series delta. The LP reference is present and
specific.

## Must-fix

### debian/watch is non-functional
Same defect class as the earlier smc-tools and valgrind reviews. The file uses a
key/value style that is **not valid uscan syntax**:

```
Version: 5

Template: Github
Owner: ibm-s390-linux
Project: s390-tools
Update-Script: uupdate
```

`uscan --no-download --verbose` parses it as an **obsolete version-1 watch file**
and **skips every line** ("Skipping the line: Version: 5", etc.), so upstream
version tracking is dead. Lintian independently corroborates this with
`W: missing-debian-watch-file-standard`. The `-0ubuntu2` changelog even claims
*"Update d/watch file to v5"*, but the file as shipped does nothing.

It needs a real uscan watch file, e.g. GitHub tag tracking:

```
version=4
opts="mode=git,pgpmode=none,uversionmangle=s/(\d)[-.]?(rc|RC)/$1~$2/" \
  https://github.com/ibm-s390-linux/s390-tools.git \
  refs/tags/v?@ANY_VERSION@ debian uupdate
```

(verify the exact tag regex against the upstream tag naming).

## Should-fix

### debian/copyright — incomplete coverage
DEP-5 machine-readable. The `Files: *` stanza attributes everything to
`1999-2024 IBM Corp.` under Expat, but `licensecheck -r` reveals files that are
**not** Expat and **not** represented anywhere in the copyright file:

- **Bundled zlib** under `zipl/boot/zlib/*` and `zipl/include/zlib/*`
  (`zlib.h`, `dfltcc*.c/h`, …): genuine zlib library source,
  `Copyright (C) 1995-2005 Jean-loup Gailly and Mark Adler`, carrying
  `SPDX-License-Identifier: Zlib`. The Zlib license is never mentioned in
  `debian/copyright`. This needs its own `Files:` stanza with the Zlib license
  text and the Gailly/Adler copyright.
- **LGPL-2.1+** systemd-derived unit files
  (`hsavmcore/initramfs/.../hsavmcore.service`,
  `zipl/dracut/99ngdump/ngdump.service`) carry the systemd
  "GNU Lesser General Public License … version 2.1 or later" header. LGPL-2.1 is
  not listed in `debian/copyright`.

The vendored Rust crates under `rust-vendor/*` are grouped by license
(Expat/Apache-2.0/BSD-2-Clause/BSL-1.0/Unicode/Unlicense) with license texts
present, but use blanket `Copyright: 2018`/`2018, 2021` placeholders rather than
the real per-crate holders — worth tightening, though secondary to the zlib/LGPL
gap above.

### debian/patches — DEP-3 metadata
All 6 patches apply cleanly with **0 fuzz** (good). DEP-3 gaps:

- `install-iucvterm.patch` has **no DEP-3 header at all** (no Description/Author/
  Forwarded).
- `fix-64bit-lib-path-handling.patch` — the patch **modified in this very upload**
  — lacks a `Forwarded:` field, its `Last-Update:` is still `2025-07-02` (not
  bumped for the `-0ubuntu3` change), its `Bug:` points to LP #2115416 rather than
  the upload's LP #2147107, and the Description has a typo ("path andling").

Minor: 6 offsets across `rust_paths`, `vendor-remove-unused-deps`, and
`conformance-to-dep17-usr-merge` — acceptable, but could be refreshed away.

### Lintian (binary) — minor warnings
No errors. Beyond review-container noise (≈42 `groff-message … troff:
Segmentation fault` warnings from a broken troff in the build container — ignore
per the guide):

- `W: mismatched-override embedded-library libyaml [usr/bin/pvapconfig]` and
  `[usr/bin/pvinfo]` — the `s390-tools` lintian overrides for an embedded libyaml
  no longer match what lintian detects; refresh/realign the overrides.
- `W: no-manual-page [usr/bin/pvextract-hdr]` — ship a man page for that binary.

## Passing / not applicable

- **debian/control:** `wrap-and-sort -ast` clean; `Standards-Version: 4.7.2`
  (latest); `Maintainer` = Ubuntu Developers with `XSBC-Original-Maintainer`
  (Debian S/390 Team) and Uploaders preserved; `Homepage` set; sensible
  per-binary `Architecture`/`Section`/`Priority`; appropriate Breaks/Replaces for
  the data/statd splits. (Lintian's `newer-standards-version 4.7.2 (current is
  4.6.2)` is an artifact of the older lintian in the container — 4.7.2 is in fact
  the current Policy; no action.)
- **debian/changelog:** well-formed; correct version `2.41.0-0ubuntu3`, target
  `resolute`, valid signature/date, active-voice entry, real LP reference
  (#2147107).
- **Symbols & ABI:** both shared libraries ship up-to-date symbols files
  (`libekmfweb1.symbols`, `libkmipclient1.symbols`) with `#MINVER#` and
  `Build-Depends-Package`. Symbol versioning is used; the new `LIBEKMFWEB_1.1` node
  and new entries are correctly tagged at minimum version `2.41.0`. SONAMEs
  (`libekmfweb.so.1`, `libkmipclient.so.1`) are consistent with the `*.install`
  files. The s390x build (where these libs build) succeeded, so dpkg-gensymbols
  accepted the files. Minor nice-to-have: set
  `export DPKG_GENSYMBOLS_CHECK_LEVEL = 4` in `debian/rules` for strict checking.
- **Lintian (source):** 0 errors; 2 warnings —
  `missing-debian-watch-file-standard` (the broken watch file, already a must-fix
  above) and the benign `newer-standards-version`.
- **Binary builds:** `amd64`, `arm64`, `ppc64el`, `s390x` all **Successfully
  built** on the PPA.

## Recommendation

Request changes. Fix `debian/watch` so uscan actually tracks upstream (must-fix);
add `debian/copyright` stanzas for the bundled zlib (Zlib license, Gailly & Adler)
and the LGPL-2.1+ systemd unit files (should-fix); add/refresh the patch DEP-3
headers — especially for `install-iucvterm.patch` and the just-modified
`fix-64bit-lib-path-handling.patch` — and realign the stale libyaml lintian
overrides. With those addressed the upload is otherwise in good shape for the
devel series: it builds on all architectures, the symbols files are current, and
lintian is error-free.
