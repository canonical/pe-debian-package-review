#!/usr/bin/env bash
# Fetch a PPA package's source robustly for review.
#
# Usage:
#   ./fetch-source.sh                       # use the latest pick in .ppa-request
#   ./fetch-source.sh OWNER/ARCHIVE PKG [SERIES]
#
# Why not `pull-lp-source --ppa ...`? pull-lp-source pulls from the main Ubuntu
# archive; it has no real PPA support. Use pull-ppa-source, give it the PPA as
# OWNER/ARCHIVE (no "ppa:" prefix needed) and ALWAYS pass the series, otherwise
# it may look in the wrong release. We also clean the target dir first, because
# pull-ppa-source aborts with "Source unpack failed" if it already exists.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="/tmp/opencode/ppa-review"
REQ="$DIR/.ppa-request"

owner_archive="" pkg="" series=""
if [ "$#" -ge 2 ]; then
    owner_archive="${1#ppa:}"; pkg="$2"; series="${3:-}"
elif [ -f "$REQ" ]; then
    # .ppa-request line: <ts>\tppa:owner/archive\t<url>\t<package>\t<series>
    IFS=$'\t' read -r _ts ppa _url pkg series < <(tail -n1 "$REQ")
    owner_archive="${ppa#ppa:}"
else
    echo "no package given and no $REQ to read from" >&2
    exit 2
fi

if [ -z "$owner_archive" ] || [ -z "$pkg" ]; then
    echo "could not determine PPA/package (owner_archive='$owner_archive' pkg='$pkg')" >&2
    echo "pick a package on the PPA page, or pass: OWNER/ARCHIVE PKG [SERIES]" >&2
    exit 2
fi

echo "PPA:     ppa:$owner_archive"
echo "Package: $pkg"
echo "Series:  ${series:-<auto>}"

mkdir -p "$WORK"
cd "$WORK"

# Clean any previous attempt so extraction can't collide.
rm -rf "$WORK/$pkg"*/ "$WORK/${pkg}_"* 2>/dev/null || true

echo "+ pull-ppa-source --ppa $owner_archive $pkg ${series}"
# --no-verify-signature: PPA signing keys aren't imported here; that's expected
# for a read-only review and must not abort the fetch.
pull-ppa-source --no-verify-signature --ppa "$owner_archive" "$pkg" ${series:+$series}

# Locate the extracted tree.
tree="$(find "$WORK" -maxdepth 1 -type d -name "${pkg}-*" | sort | tail -n1)"
if [ -z "$tree" ] || [ ! -f "$tree/debian/changelog" ]; then
    echo "fetch completed but no extracted source tree with debian/ was found" >&2
    exit 1
fi

echo "OK: source extracted to $tree"
echo "$tree" > "$WORK/.last-source"
ls -1 "$tree/debian" | head -20
