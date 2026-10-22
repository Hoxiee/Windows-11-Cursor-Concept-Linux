#!/usr/bin/env bash
# Thin wrapper: ./uninstall.sh [--system] [--prefix DIR]
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
exec python3 "$here/w11cursor" uninstall "$@"
