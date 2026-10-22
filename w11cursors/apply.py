"""Make every toolkit, X11 client and Wayland compositor on the machine use a theme.

Installing a cursor theme is only half of the job.  Which theme an application
shows is decided independently by

  * the compositor (it draws the cursor for native Wayland clients that use
    cursor-shape-v1, and for the root/WM cursors),
  * XWayland/X11 clients (libXcursor: ``Xcursor.theme`` X resource,
    ``XCURSOR_THEME``/``XCURSOR_SIZE``, ``~/.icons/default``),
  * GTK 3/4 (settings.ini, GSettings, the xdg-desktop-portal),
  * Qt/KDE (kcminputrc, XCURSOR_* on non-KDE desktops),
  * sandboxed apps (Flatpak cannot see ``~/.icons`` unless told).

If any of them disagrees you get the classic "right cursor on the desktop, wrong
one in Firefox/Steam/Electron/Wine" mix.  ``apply`` sets all of them to the same
theme and size.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

HOME = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
DATA = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share"))

MARK = "# managed by w11cursors"


class Applier:
    def __init__(self, theme: str, size: int, dry_run: bool = False):
        self.theme = theme
        self.size = size
        self.dry_run = dry_run
        self.log: list[str] = []

    # -- plumbing ---------------------------------------------------------
    def say(self, msg: str) -> None:
        self.log.append(msg)
        print(msg)

    def write(self, path: Path, text: str) -> None:
        self.say(f"{'would write' if self.dry_run else 'write'} {path}")
        if self.dry_run:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not path.with_name(path.name + ".w11bak").exists():
            shutil.copy2(path, path.with_name(path.name + ".w11bak"))
        path.write_text(text, encoding="utf-8")

    def run(self, *cmd: str, stdin: str | None = None) -> bool:
        self.say(f"{'would run' if self.dry_run else 'run'}: {' '.join(cmd)}")
        if self.dry_run:
            return True
        try:
            res = subprocess.run(cmd, input=stdin, text=True, capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError) as exc:
            self.say(f"  failed: {exc}")
            return False
        if res.returncode != 0:
            self.say(f"  exit {res.returncode}: {res.stderr.strip()[:200]}")
        return res.returncode == 0

    # -- steps ------------------------------------------------------------
    def default_theme(self) -> None:
        """The fallback every libXcursor client reads when nothing else is set."""
        body = ("[Icon Theme]\nName=Default\nComment=Default Cursor Theme\n"
                f"Inherits={self.theme}\n")
        for base in (HOME / ".icons", DATA / "icons"):
            self.write(base / "default" / "index.theme", body)

    def gtk(self) -> None:
        for ver in ("gtk-3.0", "gtk-4.0"):
            path = CONFIG / ver / "settings.ini"
            text = path.read_text(encoding="utf-8") if path.exists() else ""
            new = set_ini_keys(text, "Settings", {
                "gtk-cursor-theme-name": self.theme,
                "gtk-cursor-theme-size": str(self.size),
            })
            if new != text:
                self.write(path, new)

    def gsettings(self) -> None:
        if not shutil.which("gsettings"):
            return
        probe = subprocess.run(["gsettings", "list-keys", "org.gnome.desktop.interface"],
                               capture_output=True, text=True)
        if probe.returncode != 0 or "cursor-theme" not in probe.stdout:
            return
        # Also what GTK apps in Flatpak and xdg-desktop-portal consumers read.
        self.run("gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", self.theme)
        self.run("gsettings", "set", "org.gnome.desktop.interface", "cursor-size", str(self.size))

    def kde(self) -> None:
        if "KDE" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
            return
        tool = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
        if tool:
            for key, val in (("cursorTheme", self.theme), ("cursorSize", str(self.size))):
                self.run(tool, "--file", "kcminputrc", "--group", "Mouse", "--key", key, val)
        if shutil.which("plasma-apply-cursortheme"):
            self.run("plasma-apply-cursortheme", self.theme)

    def xresources(self) -> None:
        """XWayland and plain X11 clients read Xcursor.* from the resource database."""
        candidates = [HOME / ".Xresources", CONFIG / "X11" / "Xresources", HOME / ".Xdefaults"]
        path = next((p for p in candidates if p.exists()), candidates[0])
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        lines = [ln for ln in text.splitlines() if not re.match(r"\s*Xcursor\.(theme|size)\s*:", ln)]
        lines += [f"Xcursor.theme: {self.theme}", f"Xcursor.size: {self.size}"]
        new = "\n".join(lines).rstrip("\n") + "\n"
        if new != text:
            self.write(path, new)
        if os.environ.get("DISPLAY") and shutil.which("xrdb"):
            self.run("xrdb", "-merge", "-",
                     stdin=f"Xcursor.theme: {self.theme}\nXcursor.size: {self.size}\n")

    def environment(self) -> None:
        """systemd user session environment, inherited by compositors started by it."""
        body = (f"{MARK}\nXCURSOR_THEME={self.theme}\nXCURSOR_SIZE={self.size}\n")
        self.write(CONFIG / "environment.d" / "90-w11cursors.conf", body)
        if shutil.which("dbus-update-activation-environment"):
            self.run("dbus-update-activation-environment", "--systemd",
                     f"XCURSOR_THEME={self.theme}", f"XCURSOR_SIZE={self.size}")

    def compositor(self) -> None:
        if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
            self.run("hyprctl", "setcursor", self.theme, str(self.size))
        if os.environ.get("SWAYSOCK") and shutil.which("swaymsg"):
            self.run("swaymsg", "seat", "*", "xcursor_theme", self.theme, str(self.size))
        if shutil.which("riverctl") and os.environ.get("XDG_CURRENT_DESKTOP", "").lower() == "river":
            self.run("riverctl", "xcursor-theme", self.theme, str(self.size))

    def flatpak(self) -> None:
        """Sandboxed apps only see icons when the host directories are exposed."""
        if not shutil.which("flatpak"):
            self.say("flatpak not installed, skipping sandbox overrides")
            return
        path = ":".join([str(DATA / "icons"), str(HOME / ".icons"), "/usr/share/icons",
                         "/run/host/share/icons", "/run/host/user-share/icons"])
        self.run("flatpak", "override", "--user",
                 f"--filesystem={DATA / 'icons'}:ro", f"--filesystem={HOME / '.icons'}:ro",
                 "--filesystem=/usr/share/icons:ro",
                 f"--env=XCURSOR_PATH={path}", f"--env=XCURSOR_THEME={self.theme}",
                 f"--env=XCURSOR_SIZE={self.size}")

    def existing_configs(self) -> None:
        """Update XCURSOR/cursor lines that already exist in compositor configs and
        shell profiles.  Nothing is added: a stale value in any of them defeats the
        rest, but creating new settings in someone's dotfiles is not our call."""
        for path, patterns in self._rewrite_targets():
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            new = text
            for regex, repl in patterns:
                new = re.sub(regex, repl, new, flags=re.M)
            if new != text:
                self.write(path, new)

    def _rewrite_targets(self):
        t, sz = self.theme, str(self.size)
        niri = [
            (r'^(\s*xcursor-theme\s+)"[^"]*"', rf'\g<1>"{t}"'),
            (r'^(\s*xcursor-size\s+)\d+', rf'\g<1>{sz}'),
            (r'^(\s*XCURSOR_THEME\s+)"[^"]*"', rf'\g<1>"{t}"'),
            (r'^(\s*XCURSOR_SIZE\s+)"[^"]*"', rf'\g<1>"{sz}"'),
        ]
        hypr = [
            (r'^(\s*env\s*=\s*XCURSOR_THEME\s*,\s*)[^\s#]+', rf'\g<1>{t}'),
            (r'^(\s*env\s*=\s*XCURSOR_SIZE\s*,\s*)[^\s#]+', rf'\g<1>{sz}'),
            (r'(hyprctl\s+setcursor\s+)\S+\s+\d+', rf'\g<1>{t} {sz}'),
        ]
        sway = [(r'^(\s*seat\s+\S+\s+xcursor_theme\s+)\S+(\s+\d+)?', rf'\g<1>{t} {sz}')]
        labwc = [(r'^(\s*XCURSOR_THEME=).*$', rf'\g<1>{t}'), (r'^(\s*XCURSOR_SIZE=).*$', rf'\g<1>{sz}')]
        shell = [
            (r'^(\s*(?:export\s+)?XCURSOR_THEME=)["\']?[^"\'\s;]+["\']?', rf'\g<1>"{t}"'),
            (r'^(\s*(?:export\s+)?XCURSOR_SIZE=)["\']?[^"\'\s;]+["\']?', rf'\g<1>"{sz}"'),
            (r'^(\s*set\s+-gx\s+XCURSOR_THEME\s+)\S+', rf'\g<1>{t}'),
            (r'^(\s*set\s+-gx\s+XCURSOR_SIZE\s+)\S+', rf'\g<1>{sz}'),
        ]
        for f in sorted((CONFIG / "niri").rglob("*.kdl")):
            if "backups" not in f.parts:
                yield f, niri
        for f in sorted((CONFIG / "hypr").rglob("*.conf")):
            yield f, hypr
        for f in [CONFIG / "sway" / "config", *sorted((CONFIG / "sway" / "config.d").glob("*"))]:
            if f.is_file():
                yield f, sway
        yield CONFIG / "labwc" / "environment", labwc
        for name in (".profile", ".bash_profile", ".bashrc", ".zprofile", ".zshenv", ".zshrc",
                     ".xprofile", ".xinitrc"):
            yield HOME / name, shell
        yield CONFIG / "fish" / "config.fish", shell

    # -- diagnostics ------------------------------------------------------
    def conflicts(self) -> list[str]:
        """Places that would override the theme: the live environment (XCURSOR_* beats
        Xcursor.* resources and ~/.icons/default) and shell startup files."""
        found = []
        for key, want in (("XCURSOR_THEME", self.theme), ("XCURSOR_SIZE", str(self.size))):
            have = os.environ.get(key)
            if have is not None and have != want:
                found.append(f"current environment: {key}={have} (takes effect until you re-login)")
        path = os.environ.get("XCURSOR_PATH")
        if path and not any(Path(p).expanduser() == DATA / "icons" for p in path.split(":") if p):
            found.append(f"current environment: XCURSOR_PATH={path} does not include {DATA / 'icons'}")
        files = [HOME / n for n in (".profile", ".bash_profile", ".bashrc", ".zprofile", ".zshenv",
                                    ".zshrc", ".xprofile", ".xinitrc", ".pam_environment")]
        files += [CONFIG / "fish" / "config.fish"]
        for f in files:
            if not f.is_file():
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                m = re.match(r"\s*(?:export\s+|set\s+-gx\s+)?XCURSOR_(THEME|SIZE)[=\s]+[\"']?([^\"'\s]+)",
                             line)
                if m and not line.lstrip().startswith("#"):
                    want = self.theme if m.group(1) == "THEME" else str(self.size)
                    if m.group(2) != want:
                        found.append(f"{f}:{n}: {line.strip()}")
        return found

    def snippets(self) -> str:
        t, s = self.theme, self.size
        return f"""
Existing cursor settings in niri/Hyprland/sway/labwc configs and shell profiles were
updated in place.  If your compositor has none yet, add the matching lines:

  niri       ~/.config/niri/config.kdl
             cursor {{ xcursor-theme "{t}"; xcursor-size {s} }}
             (niri also exports XCURSOR_* to the apps it spawns, and
              xwayland-satellite inherits them)

  Hyprland   hyprland.conf
             env = XCURSOR_THEME,{t}
             env = XCURSOR_SIZE,{s}
             exec-once = hyprctl setcursor {t} {s}

  sway       ~/.config/sway/config
             seat seat0 xcursor_theme {t} {s}

  labwc      ~/.config/labwc/environment
             XCURSOR_THEME={t}
             XCURSOR_SIZE={s}

  river      riverctl xcursor-theme {t} {s}
  Wayfire    [input] cursor_theme = {t}, cursor_size = {s}
  i3/bspwm/openbox (X11)  nothing extra: Xresources + ~/.icons/default are set;
             make sure your session runs `xrdb -merge ~/.Xresources`.
"""


def set_ini_keys(text: str, section: str, values: dict[str, str]) -> str:
    """Set keys in an INI file, preserving everything else (comments, order)."""
    lines = text.splitlines()
    out: list[str] = []
    pending = dict(values)
    in_section = False
    seen_section = False
    for line in lines:
        header = re.match(r"\s*\[(.+)\]\s*$", line)
        if header:
            if in_section and pending:
                out.extend(f"{k}={v}" for k, v in pending.items())
                pending = {}
            in_section = header.group(1) == section
            seen_section = seen_section or in_section
        elif in_section:
            m = re.match(r"\s*([^=#;\s]+)\s*=", line)
            if m and m.group(1) in pending:
                out.append(f"{m.group(1)}={pending.pop(m.group(1))}")
                continue
        out.append(line)
    if pending:
        if not seen_section:
            out.append(f"[{section}]")
        out.extend(f"{k}={v}" for k, v in pending.items())
    return "\n".join(out).rstrip("\n") + "\n"


def apply(theme: str, size: int, dry_run: bool = False, flatpak: bool = False) -> Applier:
    a = Applier(theme, size, dry_run)
    for step in (a.default_theme, a.gtk, a.gsettings, a.kde, a.xresources, a.environment,
                 a.existing_configs, a.compositor):
        step()
    if flatpak:
        a.flatpak()
    bad = a.conflicts()
    if bad:
        print("\nWARNING: these override the theme (XCURSOR_* wins over every other setting):")
        for item in bad:
            print(f"  {item}")
    print(a.snippets())
    return a
