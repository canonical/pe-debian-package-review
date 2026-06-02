# What a DEB Package Review (Ubuntu) Needs

A consolidated, explained checklist for reviewing and sponsoring Ubuntu/Debian
source packages. It merges and restructures two sources — the PE team review
notes (with the `mediatek-vpud` example and agent guardrails) and the general
package review checklist — into a single bullet list you can work top to bottom.

A reviewer should insist on **every** item below being satisfied, or on an
explicit, recorded justification for any exception.

---

## 1. Classify the review first

- **Identify which of the three review types applies** — the rules for
  versioning and target releases differ for each:
  - **needs-packaging** — a brand-new package entering the archive (strictest
    scrutiny; see §11).
  - **PATCH** — an update for the Ubuntu release currently in development.
  - **SRU** — a Stable Release Update for an already-published release.
- **Check for existing/older versions** with `rmadison <package>` so you know
  what you are superseding and on which releases it already exists.
- **Confirm the archive pocket is correct** (`main`, `universe`, `multiverse`,
  or `restricted`) — it determines support commitments and licensing rules.
- **Confirm the target release is correct** (`plucky`, `oracular`, `noble`,
  `jammy`, …) and matches the changelog.

## 2. debian/watch (upstream tracking)

- **A correct watch file must be present** — it lets tooling discover and verify
  new upstream releases; a reviewer should always insist on one.
- **Use the latest watch file format** — `version=5` as of today. New packages
  in particular should ship a `version=5` watch file rather than an older
  format.
- **Validate it actually works**: `uscan --watchfile debian/watch --verbose`.
- **Use `uversionmangle`/`dversionmangle` where needed** to normalize odd
  upstream version strings into a sane Debian version.

## 3. debian/changelog

- **Entries must be clear, crisp, and grep-able** — use keywords, file names,
  and patch names so the history is easy to search later.
- **The package version must be correct** and follow Ubuntu version-string
  rules (e.g. `-0ubuntuN` for Ubuntu-only packages, `~` for pre-releases). The
  canonical reference is
  <https://documentation.ubuntu.com/project/how-ubuntu-is-made/concepts/version-strings/>.
  Key cases to check during review:
  - **Anatomy**: an Ubuntu version reads
    `[upstream_version]-[debian_revision]ubuntu[ubuntu_revision]`. The `-` splits
    upstream from the Debian revision; the `ubuntu` marker separates Ubuntu's
    changes so upstream, Debian, and Ubuntu can each iterate without colliding.
  - **Change in the devel release**: append/increment the number after `ubuntu`
    — `2.0-2` → `2.0-2ubuntu1` → `2.0-2ubuntu2`.
  - **Brand-new, Ubuntu-only package**: there is no Debian revision yet, so use
    `-0ubuntu1` (e.g. upstream `0.24.1` → `0.24.1-0ubuntu1`); the `ubuntu` suffix
    is mandatory to prevent auto-sync from overwriting it.
  - **Sync / re-sync from Debian**: keep the **exact** Debian version (no
    `ubuntu` suffix) — adding one would block future auto-syncs.
  - **No-change rebuild** (e.g. a library transition): add/increment a `buildN`
    suffix, not `ubuntuN` — `2.0-3` → `2.0-3build1` — so the package stays
    sync-eligible.
  - **Stable Release Update (SRU)**: never reuse or go backwards from the
    published version. If there was no prior Ubuntu delta, start at `ubuntu0.1`
    (`2.0-2` → `2.0-2ubuntu0.1`); if a delta exists, extend its trailing
    component (`2.0-2ubuntu2.4` → `2.0-2ubuntu2.5`).
  - **Native packages** (Debian/Ubuntu is upstream — no `-debian_revision`): the
    native marker suffix is plain `ubuntu` (migrate legacy `ubuntu0`); a Debian
    native `2.0` getting an Ubuntu delta becomes `2.0ubuntu1`.
  - **Backports across releases**: use a `~` suffix so the version sorts
    *before* the target release's own (e.g. `3.1-0ubuntu0.22.10.1` or
    `…~22.10.1`); `~` always orders lower than no suffix.
  - **PPA / test builds**: use a `~ppaN` suffix (e.g.
    `0.24.1-0ubuntu1~ppa1`) so the test build sorts below the eventual archive
    upload and never blocks it.
  - **Verify ordering** with `dpkg --compare-versions A lt B && echo ok` before
    settling on a version.
- **The target release must be correct** and consistent with §1.
- **A valid signature line must close the block** with the right name and email.
- **A Launchpad bug should be referenced** in the form `LP: #1234567` or
  `(LP: #1234567)` to tie the upload to its tracking bug.
- **Entries must be in active, imperative form**, e.g. "Remove
  d/p/oldpatch.patch…", "Update Standards-Version…", "No-change rebuild."
- **Every change under `debian/*` should be reflected** in the changelog, and
  ideally each line maps to a git commit to ease later maintenance. Folder
  abbreviations are fine (`d/control`, `d/rules`, `d/p/name.patch`).
- **Omit redundant `d/changelog` lines** — a changelog describing itself is
  implied and just noise.
- **Consider a NEWS.Debian entry** for changes important enough that users
  should be told at upgrade time.

## 4. debian/control

- **Run `wrap-and-sort`** for consistent, diff-friendly formatting.
- **Use `Architecture: any`** where the software is portable, rather than
  hard-coding architectures.
- **Libraries belong in `Section: libs`**, and binary stanzas should not
  redundantly repeat fields already inherited from the source stanza.
- **Standards-Version should be current** — bump it (and make the matching
  policy changes) when targeting the Ubuntu devel series or Debian
  unstable/experimental. **New packages especially must use the latest available
  Standards-Version** rather than an older one.
- **Fields must be sane** — accurate Sections, meaningful Descriptions, correct
  dependencies, and upstream metadata (`debian/upstream/metadata`).
- **Decide whether `update-maintainer` is needed** so Ubuntu uploads carry
  `XSBC-Original-Maintainer` correctly.
- **Only files inside `debian/` may be modified** — packaging changes must never
  touch upstream source directly.

## 5. debian/copyright

- **Licenses must match reality** — verify with `licensecheck -r .` and
  cross-check with `lrc` (licenserecon); treat `lrc` as a guide, not gospel.
- **It must accurately reflect upstream licensing**, file by file where they
  differ.
- **All copyright holders of `debian/*` files must be listed** — extract Debian
  contributors from `debian/changelog` and acknowledge each one.
- **Remove stale `Files:` patterns** that point at paths no longer present in
  the new upstream (watch for dropped vendored trees like `rust-vendor/*`).
- **Apply the strictest scrutiny for needs-packaging**, where copyright is a
  primary gate for entering the archive.

## 6. Patches (quilt) and DEP-3

For the full authoring walkthrough see
<https://documentation.ubuntu.com/project/contributors/patching/make-changes-to-a-package/>.

- **Understand the separation of concerns** — in a `3.0 (quilt)` package, Git
  tracks only the *packaging* (`debian/`), while changes to upstream source are
  carried as quilt patches under `debian/patches/`. A correct commit adds a new
  `debian/patches/<name>.patch` file (and the `series` entry), **never** a diff
  that edits upstream files directly.
- **The source format must be correct** (`debian/source/format`, typically
  `3.0 (quilt)`).
- **Patches should be created the `quilt` way** so they are well-formed:
  - `QUILT_PATCHES=debian/patches quilt new <name>.patch` — register a new patch
    and add it to `series`.
  - `quilt add <file>` **before** editing each source file, so quilt records it.
  - `quilt refresh -p ab --no-timestamps --no-index` — produce clean, stable,
    review-friendly diffs (no machine-specific timestamps/index lines).
- **Every patch needs a DEP-3 header** (Description, Origin/Author, Forwarded,
  Bug if any, Last-Update) so its purpose and provenance are documented; add it
  with `quilt header -e --dep3`. For Ubuntu-only patches, record
  `Forwarded: no, Ubuntu only`.
- **Each patch should be its own Git commit**, committing just
  `debian/patches/` (the patch file plus the updated `series`) with a clear
  message.
- **All patches must apply cleanly** — `quilt push -a` then `quilt pop -a`,
  leaving the tree clean before building.
- **Patches must not report fuzz** — fuzz breaks builds; refresh the patch with
  `quilt push -a --refresh`.
- **Offsets** may be left during SRUs but should be refreshed away for new
  packages and new patches.
- **Dropped patches must be removed from both** the `debian/patches/` directory
  **and** the `series` file.
- **Never edit upstream files directly** in `3.0 (quilt)` packages — all changes
  go through quilt; clean `.pc/` between operations.
- **Reviewer tooling note**: the source is typically obtained with
  `git-ubuntu clone <package>`, and the matching orig tarball with
  `git-ubuntu export-orig` (which lands `../<pkg>_<ver>.orig.tar.gz` one
  directory up, where the build tools expect it — leave it there).

## 7. Symbols & ABI

- **C/C++ libraries must ship an up-to-date symbols file** so dependency
  versioning is precise (check the build log for `MINVER` hints).
- **Use the `(c++)` symbol format** for C++ libraries.
- **Make symbol checks strict** via `export DPKG_GENSYMBOLS_CHECK_LEVEL = 4` in
  `debian/rules`, and drop manual `shlibs` overrides.
- **Verify SONAMEs are consistent** between the real `.so.X.Y.Z` and its
  `.so.X` symlink.
- **Handle ABI/API breaks deliberately** — bump the SONAME, confirm the break is
  intentional with upstream, keep the `.so` dev symlink in `-dev`, and trigger a
  rebuild of all reverse-dependencies (a library transition).

## 8. Build & test

- **Build with `sbuild`** for full binary builds and **`dpkg-buildpackage -S`**
  for source-only builds, in a clean chroot.
- **Run autopkgtests** (`sbuild --run-autopkgtest`) — they are **required** for
  new packages.
- **Build hardening flags must be enabled.**
- **Do a PPA test build** and reference it in the LP bug; the build counts as
  successful only if its in-build tests also pass.
- **Consider real-world tests** such as install/upgrade of the resulting binary.
- **Keep `debian/rules` clean** — no excessive workarounds; use `dh-python` for
  Python packages.

## 9. Lintian

- **Run lintian on both source and binary packages** with
  `lintian -EviL -pedantic` (binaries at minimum).
- **There must be zero `E:` errors.**
- **There should be zero `W:` warnings** unless there is a convincing,
  documented justification; fix as much as possible.
- **Use `lintian-explain-tags <tag>`** to understand any tag before acting.
- **Use a documented `lintian-overrides`** only for genuine false positives.

## 10. Sponsoring & upload

- **Attach a debdiff to the LP bug** so reviewers/sponsors can see exactly what
  changed.
- **Request sponsoring when needed** — tag the bug `pe-sponsoring-request` and
  consider subscribing `ubuntu-sponsors`.
- **Follow up after upload** — confirm the upstream build succeeded, all
  autopkgtests pass (`update_excuses`), and any SRU validation is completed.
- **Note:** signing and uploading are human responsibilities (see Appendix A).

## 11. New packages (needs-packaging) — extra care

- **File a `needs-packaging` LP bug** using the official New Packages template.
- **Use the latest standards/formats** — ship a `version=5` watch file (§2) and
  set `Standards-Version` to the latest available release (§4); new packages
  have no legacy excuse for trailing versions.
- **Give copyright the strictest review** (see §5) — it gates archive entry.
- **Follow the target-release rule**: land in the current devel release first,
  then add to in-service releases newest→oldest. If a partner has only specific
  releases enabled, a package may land directly there — but record the reason in
  the bug's Notes (e.g. "only jammy was enabled for Elektrobit").
- **Example takeaways from `mediatek-vpud`**: recommend upstream adopt semantic
  versioning, derive a proper Debian version (`0.24.1-0ubuntu1` — the `ubuntu`
  suffix is required for Ubuntu-only packages), flag the missing `LP: #` in the
  changelog, and confirm `jammy` was the right target under the partner rule.

---

## Appendix A — Agent guardrails

When an automated agent performs these reviews:

- **Run builds with silent options but keep build logs in separate files** so
  failures can still be inspected; lintian may run with full verbosity.
- **Never make signed builds** — always `-us -uc`.
- **Never upload to an archive or PPA** — that is human-only.
- **Stay offline by default** — if a tool or fact is unavailable, prefer to stop
  and ask rather than guess.
- **Skip a fix that cannot be done cleanly** and leave a note for the human.
- **After a failed fix, restore the tree** to the last good commit
  (`git checkout -- . && git clean -fd`).
- **Rebuild and re-run lintian after every fix.**
- **Keep changes as separate commits**, and only use branches created by the
  agent or by `gbp` — never modify pre-existing branches.
- **Log every action to `AGENT_LOG.md`** (one-line summary plus the exact
  command) so another agent can resume from the log and repo state.

## Appendix B — Quick command reference

```sh
rmadison <package>                         # existing versions across releases
uscan --watchfile debian/watch --verbose   # validate watch file
uscan --safe                               # check for a new upstream release
licensecheck -r .                          # license scan
lrc                                        # licenserecon cross-check
quilt push -a / quilt pop -a               # apply / unapply all patches
quilt push -a --refresh                    # refresh patches (remove fuzz)
quilt header -e --dep3 <patch>             # edit/verify a DEP-3 header
dpkg-buildpackage -S -us -uc               # source-only build (unsigned)
sbuild --run-autopkgtest                   # full binary build + tests
lintian -EviL -pedantic [../*.deb]         # lint source / binaries
lintian-explain-tags <tag>                 # explain a lintian tag
```
