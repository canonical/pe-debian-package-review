# DEB Package Review Guide

A consolidated checklist and reference for reviewing and sponsoring Debian/Ubuntu
source packages. This guide merges and restructures two sources:

- The **PE team DEB package review** working notes (with the `mediatek-vpud`
  worked example and agent guardrails).
- The general **Package Review Checklist** (lintian, copyright, symbols, DEP-3,
  control, build & test conventions).

Use it as a top-to-bottom checklist. A reviewer should insist on every item
below being satisfied (or an explicit, convincing justification being recorded).

---

## 1. Classify the Review

At least three cases must be distinguished, because each has different rules for
versioning and target releases:

| Case | Trigger | Notes |
|------|---------|-------|
| **needs-packaging** | A brand-new package | Requires extra care — see §11 |
| **PATCH** | Update for an Ubuntu release currently in development | Target the devel series |
| **SRU** | Update for an already-published Ubuntu release | Stable Release Update rules apply |

Then sanity-check the landing target:

- Check for existing/older versions of the package:
  ```sh
  rmadison <package>        # e.g. rmadison rocm-core
  ```
- Confirm the archive **pocket** is correct: `main`, `universe`, `multiverse`,
  or `restricted`.
- Confirm the **target release** is correct (`plucky`, `oracular`, `noble`,
  `jammy`, …).

---

## 2. debian/watch

- A watch file **must** be present and correct. A reviewer should always insist
  on a proper watch file.
- Verify it:
  ```sh
  uscan --watchfile debian/watch --verbose
  ```
- Use `uversionmangle` where upstream version strings need normalizing, e.g.:
  ```
  uversionmangle=s/(\d+\.\d+\.\d+)\.\d++(.*)/$1/
  ```
- Reference example:
  <https://git.launchpad.net/ubuntu/+source/xlnx-firmware/tree/debian/watch>

Example watch file:
```
version=4
opts="searchmode=plain" \
 https://gitlab.com/mediatek/aiot/rity/vpud/tags?sort=updated_desc \
 -/archive/v?\d[\d.a-f+]+/vpud-@ANY_VERSION@@ARCHIVE_EXT@
```

---

## 3. debian/changelog

- Keep entries **clear, crisp, and grep-able** — use key words, file names, etc.
- Verify the **package version** is correct. References:
  - <https://wiki.ubuntu.com/SecurityTeam/UpdatePreparation#Update_the_packaging>
  - <https://github.com/canonical/ubuntu-maintainers-handbook/blob/main/VersionStrings.md>
  - <https://documentation.ubuntu.com/project/how-ubuntu-is-made/concepts/version-strings/>
- Verify the **target release** is correct (see §1).
- Verify a proper **signature line** at the end of the block (correct name and
  email address).
- A **Launchpad bug** should be referenced, in the form `LP: #1234567` or
  `(LP: #1234567)`.
- Write entries in **active form**, e.g.:
  - `Remove d/p/oldpatch.patch since it's not included in the new version.`
  - `Update Standards-Version field in d/control to latest level.`
  - `No-change rebuild.`
- **Every** change under `debian/*` should be reflected in the changelog, and
  ideally each changelog line maps to a corresponding git commit (eases later
  maintenance). Abbreviations are allowed: `d/control`, `d/rules`,
  `d/p/patchname.patch`, etc.
- Style preference: avoid literal `d/changelog` / `debian/changelog` lines
  inside a changelog entry — they are implied and should be omitted.
- Consider a **NEWS.Debian** file for important changes:
  <https://www.debian.org/doc/manuals/developers-reference/best-pkging-practices.html#supplementing-changelogs-with-news-debian-files>

Inspect just the top block with:
```sh
sed '/^ --/q' debian/changelog
```

---

## 4. debian/control

- Run `wrap-and-sort` for consistent formatting.
- **Architecture**: use `any` where possible.
- **Section**: for libraries use `libs`; do not let a binary stanza redundantly
  mirror the source `Section` (lintian: `installable-field-mirrors-source`).
- Check `Standards-Version` is current:
  <https://www.debian.org/doc/debian-policy/upgrading-checklist.html>
  - For Ubuntu devel uploads, target the latest Standards-Version. Find the
    current devel release name via
    <https://api.launchpad.net/1.0/ubuntu/devel>.
  - For uploads to Debian unstable/experimental, also upgrade to the latest
    Standards-Version.
- Verify Sections, Descriptions, and other fields are sane.
- Include upstream metadata (`debian/upstream/metadata`).
- For autopkgtest control files, prefer `gcc` over `build-essential` (with the
  `superficial` restriction).
- Determine whether `update-maintainer` needs to be run (Ubuntu uploads should
  carry `XSBC-Original-Maintainer`).
- **Only files inside the `debian/` directory may be modified.**

---

## 5. debian/copyright

Checked carefully — especially for **needs-packaging**.

- Verify licenses match reality:
  ```sh
  lrc                                              # licenserecon; apt install licenserecon
  licensecheck --check '.*' --recursive --deb-machine --lines 0 -- *
  licensecheck -r .
  grep -i copyright *
  ```
  `licenserecon` is convenient but not always 100% accurate — cross-check.
- The file must accurately reflect **upstream** licenses.
- **Copyright holders for `debian/*` files** must all be listed. Extract Debian
  authors from `debian/changelog` and ensure every contributor is acknowledged.
- Rule of thumb: `lrc` output (upstream files) + changelog authors
  (`debian/*` files) = a complete `debian/copyright`.
- Remove stale `Files:` patterns that reference paths no longer present in the
  new upstream (lintian: `superfluous-file-pattern`); pay special attention to
  vendored trees like `rust-vendor/*` when upstream drops them.

Project: <https://tracker.debian.org/pkg/licenserecon>

---

## 6. Patches (quilt) and DEP-3

- All patches must follow the **DEP-3** header standard:
  - <http://dep.debian.net/deps/dep3/>
  - <https://documentation.ubuntu.com/project/how-ubuntu-is-made/concepts/deb-3-patch-file-headers/>
  - Required fields: Description, Origin/Author, Bug (if applicable),
    Last-Update. Generate/verify with:
    ```sh
    quilt header -e --dep3 mypatch.patch
    ```
- Confirm the source **format** is correct (`debian/source/format`).
- Apply and unapply patches cleanly:
  ```sh
  export QUILT_PATCHES=debian/patches
  quilt push -a     # apply all
  quilt pop  -a     # unapply all (leave tree clean before build)
  ```
- Patches **must not report `fuzz`** — fuzz breaks builds. Refresh the offending
  patch:
  ```sh
  quilt push -a --refresh
  ```
- **Offsets**: acceptable to leave during SRUs, but should be removed by a
  refresh for new packages and new patches.
- If a patch is dropped (already applied upstream), remove it from **both** the
  `debian/patches/` directory **and** `debian/patches/series`.
- Clean the `.pc/` directory between operations: `rm -rf .pc`.
- For `3.0 (quilt)` packages, **never** apply patches directly to upstream files
  in git commits — always maintain them as quilt patches.

---

## 7. Symbols & ABI

- C/C++ libraries **must** ship a symbols file, kept up to date (search the
  build log for `MINVER` and symbols hints).
- For C++ symbols, use the `(c++)` format (see the `convert-symbols` helper:
  <https://github.com/talhaHavadar/dotfiles/blob/main/dot/bin/packaging/convert-symbols>).
- Make symbol checks strict by adding to `debian/rules`:
  ```make
  export DPKG_GENSYMBOLS_CHECK_LEVEL = 4
  ```
- Drop any explicit `shlibs` override — it should appear naturally in build logs.
- Check **SONAMEs**. Matching `.so` version and symlink are fine, e.g.:
  ```
  librocm-core.so.1.0.70100
  librocm-core.so.1 -> librocm-core.so.1.0.70100
  ```
- If upstream breaks ABI/API:
  - Bump the SONAME.
  - Confirm with upstream that the break is intentional.
  - The `.so` dev symlink belongs in the `-dev` package.
  - Rebuild all reverse-dependencies (a library transition).

---

## 8. Build & Test

- Build with **`sbuild`**, and `--run-autopkgtest` whenever possible. Prefer
  `dpkg-buildpackage -S` for **source-only** builds and `sbuild` for full
  **binary** builds.
- **autopkgtest is required** for new packages.
- Ensure **build hardening flags** are enabled.
- A **PPA test build** should be done and ideally referenced in an LP bug
  comment. Confirm:
  - The build succeeded.
  - Any tests run as part of the build succeeded (otherwise the build is *not*
    successful).
  - Consider extra tests, e.g. install/upgrade the package.
- Keep `debian/rules` free of excessive workarounds.
- Use `dh_python` / `dh-python` for Python packages.

---

## 9. Lintian

Run lintian on **both** the source and the binary packages (binary at minimum):

```sh
lintian -EviL -pedantic                 # source (build with: debuild --no-conf -S -d)
lintian -EviL -pedantic ../*.deb        # binaries (from local or PPA build)
```

- There must be **no `E:` (errors)**.
- There should be **no `W:` (warnings)** unless a convincing justification is
  given; fix as many issues as possible.
- Use `lintian-explain-tags <tag>` to understand a tag.
- For genuine false positives, add a documented `lintian-overrides`.
- `sbuild` can run lintian post-build with:
  ```perl
  $lintian_opts = ['-EviL', '-pedantic'];
  ```

---

## 10. Sponsoring & Upload

- Attach a **debdiff** to the LP bug.
- Decide whether **sponsoring** is needed. If so:
  - Add the tag `pe-sponsoring-request` to the LP bug
    (<https://bugs.launchpad.net/ubuntu/+bugs?field.tag=pe-sponsoring-request>).
  - Consider subscribing `ubuntu-sponsors` to the bug.
- Even after a sponsor uploads, follow up on:
  - Upstream build success (help fix if it fails).
  - autopkgtests passing (check `update_excuses`, help fix).
  - Any required SRU validation steps.

General references:
- <https://www.debian.org/doc/manuals/developers-reference/best-pkging-practices.html>
- Upstream should sign their tags.

---

## 11. New Package ("needs-packaging") — Extra Care

New packages need everything above **plus**:

- File an LP bug per <https://wiki.ubuntu.com/UbuntuDevelopment/NewPackages>,
  tagged `needs-packaging`, filled out using the template at
  <https://wiki.ubuntu.com/UbuntuDevelopment/NewPackages/ExamplePackageRequest>.
- `debian/copyright` gets the strictest scrutiny (see §5).
- **Target release rule**: introduce into the current devel release first, then
  add to other in-service releases newest→oldest. In PE, a partner may only have
  specific releases enabled, in which case a new package can land directly on a
  specific release — record this in the LP bug **Notes**, e.g.:
  > Notes: Since only jammy was enabled for Elektrobit, this package cannot be
  > uploaded to any Ubuntu releases newer than jammy (as of today).

### Worked example: `mediatek-vpud`

Obtain the source (manual download example, since LP cmd-line login is TODO):
```sh
pull-ppa-source --ppa 'baoshan-ppa/baoshan-proposed' 'mediatek-vpud' 'jammy'
# fallback: download from the PPA +sourcepub +listing-archive-extra page
```

Build a local source package and run lintian:
```sh
dpkg-buildpackage -S -d --sign-key=<your key>
lintian -EvIL -pedantic
```
Sample lintian output (only `I:` infos — no E/W, so the source is good):
```
I: mediatek-vpud source: adopted-extended-field XSBC-Original-Maintainer [debian/control:5]
I: mediatek-vpud source: installable-field-mirrors-source Section [debian/control:12]
I: mediatek-vpud source: out-of-date-standards-version 4.1.2 (current is 4.7.0)
```

Version review for this example:
- Upstream tags: <https://gitlab.com/mediatek/aiot/rity/vpud/-/tags>
- Recommend upstream adopt semantic versioning (<https://semver.org/>); the
  semantic upstream version would be `0.24.1`.
- Proper Debian version: `0.24.1-0ubuntu1` (the `XubuntuY` suffix is required
  because an Ubuntu-only package is being introduced).
- Changelog message `* Bump to 0.24.1.0+eec4966` is **missing a Launchpad bug**.
- Target `jammy` is correct under the partner-enablement rule above.

Next steps after review:
1. Adjust the source package per the findings.
2. Recreate the source package.
3. Re-run lintian on the source.
4. Build the binaries in a PPA.
5. Run lintian on the `*.deb`.
6. Check the lintian output.
7. If clean, find a sponsor and add `pe-sponsoring-request`.

---

## Appendix A — Agent Guardrails

When an automated agent performs these reviews, it must obey:

- Run build commands with **silent options**, but keep build logs in separate
  log files so errors can be inspected. Lintian may run with full verbosity.
- **Do NOT** make signed builds (always use `-us -uc`).
- **Do NOT** upload to an archive or PPA — those steps are for humans only, even
  where docs describe them.
- Generally **no internet access is needed**; if a tool or piece of information
  is unavailable, **wait for human input** rather than guessing.
- If a fix is not cleanly doable, **skip it and leave a note** for the human.
- After a failed fix, **clean and restore** the tree to the last good commit
  (`git checkout -- . && git clean -fd`).
- After **each** fix, redo source and binary builds, then re-run lintian.
- Keep changes as **separate git commits**.
- **Do NOT** modify existing branches — only use branches created by the agent
  or by `gbp`.
- Log every action to `AGENT_LOG.md` (one-line summary plus the exact command),
  so a second agent can resume from the log and repo state.
- Prefer **`dpkg-buildpackage`** for source-only builds and **`sbuild`** for
  full binary builds.

## Appendix B — Quick Command Reference

```sh
rmadison <package>                         # existing versions across releases
uscan --watchfile debian/watch --verbose   # validate watch file
uscan --safe                               # check for new upstream
licensecheck -r .                          # license scan
lrc                                        # licenserecon cross-check
quilt push -a / quilt pop -a               # apply / unapply patches
quilt push -a --refresh                    # refresh patches (kill fuzz)
quilt header -e --dep3 <patch>             # DEP-3 header
dpkg-buildpackage -S -us -uc               # source-only build (unsigned)
sbuild --run-autopkgtest                   # full binary build + tests
lintian -EviL -pedantic [../*.deb]         # lint source / binaries
lintian-explain-tags <tag>                 # explain a lintian tag
```
