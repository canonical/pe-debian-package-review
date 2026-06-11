# Review: smc-tools 1.8.7-0ubuntu1 (ppa:fheimes/test)

- **Package:** smc-tools
- **Version:** 1.8.7-0ubuntu1
- **Target:** resolute (Ubuntu devel)
- **PPA:** https://launchpad.net/~fheimes/+archive/ubuntu/test
- **Source:** `/tmp/opencode/ppa-review/smc-tools-1.8.7`
- **Reviewed against:** `Package-Review-Guidelines.md`

## Verdict

**Changes requested.** There are **no blocking build or license errors** and all
5 architectures build, but two **must-fix** correctness issues (a non-functional
`debian/watch` and a placeholder `LP: #` bug number) and three should-fix items
need addressing before sponsoring.

| # | Step | Result |
|---|------|--------|
| 1 | Classify (PATCH/SRU/new) | pass |
| 2 | debian/watch | **must-fix** |
| 3 | debian/changelog | **must-fix** |
| 4 | debian/control | should-fix |
| 5 | debian/copyright | should-fix |
| 6 | debian/patches (quilt/DEP-3) | should-fix |
| 7 | Symbols & ABI | n/a |
| 8 | Lintian (source package) | 0 E, 2 W |
| 9 | Binary builds (PPA) | pass (5/5 arches) |
| 10 | Lintian (binary packages) | 0 E, 1 W (+ container noise) |

## Classification

New **upstream release** (1.8.6 → 1.8.7) uploaded to the **development series
`resolute`**. Version `-0ubuntu1` (Ubuntu-only package, no Debian revision).
This is a normal devel-series upload — **not** an SRU and **not**
needs-packaging. `Standards-Version: 4.7.2` is current.

## Must fix (blocking)

1. **`debian/watch` is malformed and non-functional.**
   The file uses a `Version: 5` / `Template: Github` / `Owner: ...` /
   `Project: ...` syntax that is **not** valid uscan format. `uscan` parses it
   as an obsolete *version 1* watch file and **skips every line**
   (`Skipping the line: Version: 5`, etc.), so upstream version tracking does
   not work at all. Lintian corroborates this with
   `W: missing-debian-watch-file-standard [debian/watch]`.
   - Additionally, `Owner: ibm-s390-tools` does not match the actual upstream
     GitHub org `ibm-s390-linux` (per `Homepage`).
   - A valid v5 file must start with lowercase `version=5` and a real URL/match
     line, e.g. for GitHub tags:
     ```
     version=5
     opts="mode=git,pgpmode=none" \
       https://github.com/ibm-s390-linux/smc-tools.git \
       refs/tags/v?(\d[\d.]*)
     ```
   - Verify with `uscan --watchfile debian/watch --no-download`.

2. **Placeholder bug reference in `debian/changelog`.**
   The top entry reads `* New upstream release. (LP: #1234567)`. `LP: #1234567`
   is a placeholder, not a real bug. Replace it with the actual Launchpad bug
   for the 1.8.7 update, or remove the `LP: #` reference if none applies.

## Should fix (non-blocking)

3. **`debian/control` Maintainer.** `Maintainer` is an individual
   (`Dimitri John Ledkov <xnox@ubuntu.com>`). For an Ubuntu-maintained package
   this should be `Ubuntu Developers
   <ubuntu-devel-discuss@lists.ubuntu.com>` with the original preserved in
   `XSBC-Original-Maintainer` (use `update-maintainer`). `wrap-and-sort` is
   clean and `Homepage` points at the correct upstream org.

4. **Stale copyright years in `debian/copyright`.** `Files: *` declares
   `2016-2018 IBM Corp`, but upstream source files carry copyright years up to
   **2021**. Update the span (e.g. `2016-2021`). The `debian/*` GPL-3 and
   upstream EPL-1.0 declarations are otherwise fine.

5. **Patch forwarding (DEP-3).** All three patches apply cleanly with no fuzz
   (`quilt push -a` / `pop -a` OK), but:
   - `fix_folder_31_32_bit_systems.patch` has **no `Forwarded` field** — add one
     (and forward upstream, or `Forwarded: not-needed` with a reason).
   - `fix_typo_in_manual_page.patch` has `Forwarded: no` — a manual-page typo
     fix should be **forwarded upstream**; update the field once submitted.
   - `fix_library_path.patch` is fine (`Forwarded: not-needed`, Ubuntu-specific,
     with Bug-Ubuntu/Bug-IBM references).

## Tool output

### Lintian — source package (0 errors, 2 warnings)

```
W: smc-tools source: missing-debian-watch-file-standard [debian/watch]
W: smc-tools source: newer-standards-version 4.7.2 (current is 4.6.2)
```

- `missing-debian-watch-file-standard` — a direct symptom of must-fix #1.
- `newer-standards-version 4.7.2` — **false positive**: this lintian's database
  predates Policy 4.7.2; 4.7.2 is the current Standards-Version. No action.

### Binary builds (PPA) — 5/5 architectures

`amd64`, `arm64`, `armhf`, `ppc64el`, `s390x` all **Successfully built**.

### Lintian — binary packages (0 errors, 1 real warning)

```
W: smc-tools: no-manual-page [usr/bin/smc_dbg]
```

- `no-manual-page [usr/bin/smc_dbg]` — `smc_dbg` ships without a man page;
  worth adding one upstream/in packaging, but non-blocking.
- The ~24 `groff-message ... troff: Segmentation fault` warnings are **review
  container artifacts** (troff/groff crashes in this environment when rendering
  the shipped man pages); they are **not** package defects and should be
  disregarded.

## Symbols & ABI — not applicable

The package ships `libsmc-preload.so` purely as an **`LD_PRELOAD` shim** with no
SONAME and no public library ABI, so symbols/shlibs tracking does not apply.

## Summary for the uploader

Fix the two blockers (`debian/watch`, placeholder `LP: #`) and ideally the three
should-fix items (Maintainer, copyright years, patch forwarding), then re-upload.
Builds and licensing are otherwise in good shape.
