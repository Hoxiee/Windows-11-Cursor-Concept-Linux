#!/usr/bin/env bash
# Thin wrapper: ./install.sh [options]  ==  ./w11cursor install [options]
# Example: ./install.sh --apply --flatpak        (dark+light, configure everything)
#          ./install.sh --scales regular,small --variants all
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
python3 -c 'import PIL' 2>/dev/null || { echo "Pillow is required (pacman -S python-pillow / apt install python3-pil)" >&2; exit 1; }
exec python3 "$here/w11cursor" install "$@"
