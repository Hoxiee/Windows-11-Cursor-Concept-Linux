"""Build XCursor themes from the upstream Windows assets."""

from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

from . import imaging, mapping, synth, xcursor
from .mapping import Entry, Variant
from .wincur import Animation, Frame, parse_ani, parse_cur

CREDITS = """\
{name}

Cursor artwork: "Windows 11 Cursors Concept HD v2.2" by Jepri Creations
https://www.deviantart.com/jepricreations

Converted to the XCursor format for Linux (X11, XWayland and Wayland).
Copy/alias drag badges, zoom lenses and the blank cursor are generated, the
rest is the author's artwork.  Use is personal-only; see Agreement.txt in the
source repository.  Credit the author when you show or share your setup.
"""


class AssetPack:
    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, mode: str, scale: str, *parts: str) -> Path:
        return self.root / mode / scale / Path(*parts)

    def has_variant(self, mode: str, scale: str, variant: Variant) -> bool:
        return self.path(mode, scale, variant.directory, "busy.ani").is_file()

    @lru_cache(maxsize=None)
    def cur(self, mode: str, scale: str, stem: str, alt: bool = False) -> list[Frame]:
        folder = "alternatives" if alt else "base"
        return parse_cur(self.path(mode, scale, folder, f"{stem}.cur").read_bytes())

    @lru_cache(maxsize=None)
    def ani(self, mode: str, scale: str, variant_dir: str, stem: str) -> Animation:
        return parse_ani(self.path(mode, scale, variant_dir, f"{stem}.ani").read_bytes())


def _static(frames: list[Frame]) -> list[xcursor.XImage]:
    return imaging.ladder(frames)


def _animated(anim: Animation) -> list[xcursor.XImage]:
    images: list[xcursor.XImage] = []
    for frames, delay in zip(anim.steps, anim.delays_ms):
        images.extend(imaging.with_delay(imaging.ladder(frames), delay))
    return images


def render_entry(pack: AssetPack, entry: Entry, mode: str, scale: str,
                 variant: Variant) -> list[xcursor.XImage]:
    if entry.kind == "cur":
        return _static(pack.cur(mode, scale, entry.source))
    if entry.kind == "alt":
        return _static(pack.cur(mode, scale, entry.source, True))
    if entry.kind == "ani":
        return _animated(pack.ani(mode, scale, variant.directory, entry.source))
    if entry.kind == "mirror":
        return _static(imaging.mirror(pack.cur(mode, scale, entry.source)))
    if entry.kind == "rotate":
        return _static(imaging.rotate_ccw(pack.cur(mode, scale, entry.source)))
    if entry.kind == "synth":
        pointer = pack.cur(mode, scale, "pointer")
        return _static(synth.render(entry.source, mode, pointer))
    raise ValueError(f"unknown entry kind {entry.kind!r}")


def index_theme(name: str, mode: str, scale: str, variant: Variant) -> str:
    desc = f"Windows 11 Cursor Concept ({mode}"
    desc += f", {variant.label.lower()} spinners" if variant.suffix else ""
    desc += ", small" if scale == "small" else ""
    desc += ") by Jepri Creations, for Linux"
    return f"[Icon Theme]\nName={name}\nComment={desc}\n"


def build_theme(pack: AssetPack, mode: str, scale: str, variant: Variant,
                out_dir: Path, static_cache: dict | None = None) -> Path:
    """Write one theme into ``out_dir/<name>`` and return its path."""
    name = mapping.theme_name(mode, scale, variant)
    root = Path(out_dir) / name
    if root.exists():
        shutil.rmtree(root)
    cursors = root / "cursors"
    cursors.mkdir(parents=True)
    cache = static_cache if static_cache is not None else {}
    for entry in mapping.ENTRIES:
        key = (mode, scale, entry.file)
        if entry.kind == "ani" or key not in cache:
            images = render_entry(pack, entry, mode, scale, variant)
            if entry.kind != "ani":
                cache[key] = images
        else:
            images = cache[key]
        xcursor.write(str(cursors / entry.file), images)
        for alias in entry.aliases:
            os.symlink(entry.file, cursors / alias)
    (root / "index.theme").write_text(index_theme(name, mode, scale, variant), encoding="utf-8")
    (root / "CREDITS.txt").write_text(CREDITS.format(name=name), encoding="utf-8")
    return root


def selection(modes, scales, variants) -> list[tuple[str, str, Variant]]:
    return [(m, s, v) for m in modes for s in scales for v in variants]
