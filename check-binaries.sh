#!/usr/bin/env bash
# Report PPA build status for the picked package and download its binary debs.
#
# Usage:
#   ./check-binaries.sh                      # use the latest pick in .ppa-request
#   ./check-binaries.sh OWNER/ARCHIVE PKG [SERIES]
#
# Thin wrapper: all logic lives in `ppa.py binaries` (Launchpad per-arch build
# status + downloading the binary .debs into /tmp/opencode/ppa-review). Exits
# non-zero if any architecture failed to build. See ppa.py.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$DIR/ppa.py" binaries "$@"
