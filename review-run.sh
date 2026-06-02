#!/usr/bin/env bash
# review-run.sh — run the *scriptable* review steps in order, each streamed live
# to the status panel (via review_status.py run), stopping/flagging on failure.
#
# This closes the gap where picking a package on the web page records the request
# but nothing executes. The judgment steps (Classify, debian/watch, changelog,
# control, copyright, patches, Symbols & ABI, Report) are left to the agent; this
# only automates the mechanical ones:
#
#     Fetch source -> Lintian (source package)
#                  -> Binary builds (PPA) -> Lintian (binary packages)
#
# Usage:
#   ./review-run.sh                      # use the latest pick in .ppa-request
#   ./review-run.sh OWNER/ARCHIVE PKG [SERIES]
#
# lintian is invoked with `--fail-on none` so a *finding* (E:/W:) doesn't mark
# the step failed; the step means "analysis ran", and every tag is in the panel
# log for the agent to triage into the report.
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="/tmp/opencode/ppa-review"
RS=(python3 "$DIR/review_status.py")

# Resolve the picked package (for locating the .dsc/.deb files). The sub-scripts
# read .ppa-request themselves, but we need PKG to build file paths here.
if [ "$#" -ge 2 ]; then
    pkg="$2"
else
    cur="$("${RS[@]/review_status.py/ppa.py}" current 2>/dev/null)" || true
    pkg="$(printf '%s' "$cur" | cut -f2)"
fi
if [ -z "${pkg:-}" ]; then
    echo "no package given and none recorded in .ppa-request" >&2
    echo "pick one on the PPA page, or pass: OWNER/ARCHIVE PKG [SERIES]" >&2
    exit 2
fi
echo "Running scriptable review steps for: $pkg"

# 1) Fetch source — abort the run if this fails (nothing to review without it).
if ! "${RS[@]}" run "Fetch source" "$DIR/fetch-source.sh" "$@"; then
    "${RS[@]}" note "Fetch failed; cannot continue. See the activity log."
    echo "fetch failed — stopping" >&2
    exit 1
fi

# 2) Lintian (source package) — run against the freshly unpacked .dsc.
dsc="$(ls -1 "$WORK/${pkg}_"*.dsc 2>/dev/null | head -1)"
if [ -n "$dsc" ]; then
    "${RS[@]}" run "Lintian (source package)" lintian --fail-on none "$dsc"
else
    "${RS[@]}" step "Lintian (source package)" warn
    "${RS[@]}" log "no .dsc found for $pkg; skipped source lintian"
fi

# 3) Binary builds (PPA) — build status + download the .debs. check-binaries.sh
#    exits non-zero if any architecture failed, which flags this step as failed
#    (a real review concern) while still downloading whatever did build.
"${RS[@]}" run "Binary builds (PPA)" "$DIR/check-binaries.sh" "$@"

# 4) Lintian (binary packages) — run against whatever .debs downloaded.
mapfile -t debs < <(ls -1 "$WORK"/*.deb 2>/dev/null)
if [ "${#debs[@]}" -gt 0 ]; then
    "${RS[@]}" run "Lintian (binary packages)" lintian --fail-on none "${debs[@]}"
else
    "${RS[@]}" step "Lintian (binary packages)" skip
    "${RS[@]}" log "no .deb packages downloaded; skipped binary lintian"
fi

echo
echo "Scriptable steps done. Remaining judgment steps are for the agent:"
echo "  Classify, debian/watch, changelog, control, copyright, patches,"
echo "  Symbols & ABI, Report."

# Make the parked state explicit in the panel so it doesn't look hung: the
# mechanical phase is finished and the remaining steps await the agent.
"${RS[@]}" note "Mechanical checks complete (fetch, source/binary lintian, \
builds). Awaiting agent review of: Classify, debian/watch, changelog, control, \
copyright, patches, Symbols & ABI, then Report."
