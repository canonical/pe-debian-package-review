#!/usr/bin/env bash
# Fetch a PPA package's source robustly for review.
#
# Usage:
#   ./fetch-source.sh                       # use the latest pick in .ppa-request
#   ./fetch-source.sh OWNER/ARCHIVE PKG [SERIES]
#
# Thin wrapper: all logic lives in `ppa.py fetch` (request parsing, cleaning the
# scratch dir, pull-ppa-source, locating the unpacked tree). See ppa.py.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$DIR/ppa.py" fetch "$@"
