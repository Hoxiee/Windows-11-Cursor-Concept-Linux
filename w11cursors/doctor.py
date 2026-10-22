"""Read-only diagnosis of the cursor setup of the current session.

Prints which theme/size every layer (environment, GTK, GSettings, X resources,
~/.icons/default, KDE) asks for, whether that theme exists on disk, and what
disagrees.  Nothing is modified.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .apply import CONFIG, DATA, HOME
from .mapping import THEME_PREFIX


def search_dirs() -> list[Path]:
    """Directories libXcursor/libwayland-cursor look in (XCURSOR_PATH, else defaults)."""
    env = os.environ.get("XCURSOR_PATH")
    if env:
        return [Path(p).expanduser() for p in env.split(":") if p]
    dirs = [DATA / "icons", HOME / ".icons"]
    dirs += [Path(p) / "icons" for p in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") if p]
    dirs += [Path("/usr/share/pixmaps")]
    return list(dict.fromkeys(dirs))


def find_theme(name: str) -> Path | None:
    for d in search_dirs():
        if (d / name / "cursors").is_dir():
            return d / name
    return None


def _ini(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(rf"\s*{re.escape(key)}\s*=\s*(.*?)\s*$", line)
        if m:
            return m.group(1)
    return None


def _gsettings(key: str) -> str | None:
    if not shutil.which("gsettings"):
        return None
    res = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", key],
                         capture_output=True, text=True)
    return res.stdout.strip().strip("'") if res.returncode == 0 else None


def _xresource(key: str) -> str | None:
    if not (os.environ.get("DISPLAY") and shutil.which("xrdb")):
        return None
    res = subprocess.run(["xrdb", "-query"], capture_output=True, text=True)
    for line in res.stdout.splitlines():
        m = re.match(rf"Xcursor\.{key}:\s*(.*)", line)
        if m:
            return m.group(1).strip()
    return None


def collect() -> list[tuple[str, str | None, str | None]]:
    """(source, theme, size) for every layer that can set the cursor."""
    rows: list[tuple[str, str | None, str | None]] = []
    rows.append(("environment XCURSOR_*", os.environ.get("XCURSOR_THEME"), os.environ.get("XCURSOR_SIZE")))
    for ver in ("gtk-3.0", "gtk-4.0"):
        p = CONFIG / ver / "settings.ini"
        rows.append((f"{ver}/settings.ini", _ini(p, "gtk-cursor-theme-name"), _ini(p, "gtk-cursor-theme-size")))
    rows.append(("GSettings (GTK, portal, Flatpak)", _gsettings("cursor-theme"), _gsettings("cursor-size")))
    rows.append(("X resources (XWayland/X11)", _xresource("theme"), _xresource("size")))
    for base in (HOME / ".icons", DATA / "icons"):
        inherits = _ini(base / "default" / "index.theme", "Inherits")
        rows.append((f"{base}/default (Inherits)", inherits, None))
    kde = CONFIG / "kcminputrc"
    if kde.is_file():
        rows.append(("KDE kcminputrc", _ini(kde, "cursorTheme"), _ini(kde, "cursorSize")))
    env_d = CONFIG / "environment.d"
    if env_d.is_dir():
        for f in sorted(env_d.glob("*.conf")):
            t, s = _ini(f, "XCURSOR_THEME"), _ini(f, "XCURSOR_SIZE")
            if t or s:
                rows.append((f"environment.d/{f.name}", t, s))
    return rows


def report() -> int:
    print(f"session   : {os.environ.get('XDG_SESSION_TYPE', '?')}  desktop={os.environ.get('XDG_CURRENT_DESKTOP', '?')}"
          f"  WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY', '-')}  DISPLAY={os.environ.get('DISPLAY', '-')}")
    print(f"search    : {' : '.join(str(d) for d in search_dirs())}")
    installed = sorted({p.name for d in search_dirs() if d.is_dir() for p in d.glob("Win11Concept-*")
                        if (p / "cursors").is_dir()})
    print(f"installed : {', '.join(installed) if installed else 'no Win11Concept-* theme found'}")
    print()
    rows = collect()
    width = max(len(r[0]) for r in rows)
    problems = 0
    themes = set()
    for source, name, size in rows:
        if name is None and size is None:
            print(f"  {source:<{width}}  -")
            continue
        status = ""
        if name:
            themes.add(name)
            found = find_theme(name)
            if not found:
                status = "  <-- theme NOT FOUND in the search path"
                problems += 1
        print(f"  {source:<{width}}  theme={name or '-'}  size={size or '-'}{status}")
    sizes = {r[2] for r in rows if r[2]}
    for name in sorted(t for t in themes if t.startswith(THEME_PREFIX)):
        found = find_theme(name)
        if found and not str(found).startswith(("/usr/", str(HOME / ".icons"))) \
                and not (HOME / ".icons" / name / "cursors").is_dir():
            print(f"WARNING: {name} is not visible from ~/.icons; the Steam runtime and other old "
                  f"libXcursor builds will show the X11 core cursor. Run ./w11cursor apply {name}")
            problems += 1
    print()
    if len(themes) > 1:
        print(f"MISMATCH: layers disagree on the theme: {', '.join(sorted(themes))}")
        problems += 1
    if len(sizes) > 1:
        print(f"MISMATCH: layers disagree on the size: {', '.join(sorted(sizes))}")
        problems += 1
    if os.environ.get("XCURSOR_THEME"):
        print("note: XCURSOR_THEME/XCURSOR_SIZE override X resources and ~/.icons/default for X11 clients.")
    if not problems:
        print("OK: every layer agrees." if themes else "nothing configured yet; run ./w11cursor apply THEME")
    return 1 if problems else 0
