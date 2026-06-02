#!/usr/bin/env bash
# Report PPA build status for the picked package and download its binary debs.
#
# Usage:
#   ./check-binaries.sh                      # use the latest pick in .ppa-request
#   ./check-binaries.sh OWNER/ARCHIVE PKG [SERIES]
#
# - Prints the per-architecture build state from Launchpad; if any arch failed
#   to build it prints the build-log URL and exits non-zero (so the review step
#   is flagged), while still downloading whatever binaries did build.
# - Downloads the binary .deb packages into /tmp/opencode/ppa-review so the
#   "Lintian (binary packages)" step can run `lintian ... *.deb`.
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="/tmp/opencode/ppa-review"
REQ="$DIR/.ppa-request"

owner_archive="" pkg="" series=""
if [ "$#" -ge 2 ]; then
    owner_archive="${1#ppa:}"; pkg="$2"; series="${3:-}"
elif [ -f "$REQ" ]; then
    IFS=$'\t' read -r _ts ppa _url pkg series < <(tail -n1 "$REQ")
    owner_archive="${ppa#ppa:}"
else
    echo "no package given and no $REQ to read from" >&2
    exit 2
fi
[ -n "$owner_archive" ] && [ -n "$pkg" ] || { echo "missing PPA/package" >&2; exit 2; }

echo "PPA:     ppa:$owner_archive"
echo "Package: $pkg   Series: ${series:-<auto>}"
echo

echo "== Build status (Launchpad) =="
python3 "$DIR/ppa.py" builds "ppa:$owner_archive" "$pkg" ${series:+$series}
build_rc=$?
if [ "$build_rc" -ne 0 ]; then
    echo ">> One or more architectures FAILED to build (see log URL above)."
fi
echo

echo "== Downloading binary .deb packages =="
mkdir -p "$WORK"; cd "$WORK"
rm -f ./*.deb 2>/dev/null || true
# -p debs pulls the binary packages (host arch + arch-independent).
pull-ppa-source --no-verify-signature -p debs --ppa "$owner_archive" "$pkg" ${series:+$series} 2>&1 \
    | sed 's/^/   /'
echo
debs=( "$WORK"/*.deb )
if [ -e "${debs[0]}" ]; then
    echo "Downloaded $(ls -1 "$WORK"/*.deb | wc -l) .deb(s):"
    ls -1 "$WORK"/*.deb | sed 's/^/   /'
else
    echo "No .deb packages downloaded."
fi

# Non-zero overall if any build failed, so the step is flagged.
exit "$build_rc"
