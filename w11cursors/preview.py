"""Render a contact sheet of a built theme, straight from its XCursor files."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from . import mapping, xcursor


def _to_image(im: xcursor.XImage) -> Image.Image:
    b, g, r, a = Image.frombytes("RGBA", (im.width, im.height), im.pixels).split()
    # premultiplied -> straight alpha for display
    pre = Image.merge("RGBa", (r, g, b, a))
    return pre.convert("RGBA")


def sheet(theme: Path, size: int = 96, background=(138, 138, 138), cols: int = 6) -> Image.Image:
    names = [e.file for e in mapping.ENTRIES]
    cell_w, cell_h = size + 24, size + 34
    rows = (len(names) + cols - 1) // cols
    out = Image.new("RGBA", (cols * cell_w, rows * cell_h), background + (255,))
    draw = ImageDraw.Draw(out)
    for i, name in enumerate(names):
        images = xcursor.read(str(Path(theme) / "cursors" / name))
        pick = min({im.nominal for im in images}, key=lambda s: abs(s - size))
        frame = next(im for im in images if im.nominal == pick)
        sprite = _to_image(frame)
        x = (i % cols) * cell_w + (cell_w - sprite.width) // 2
        y = (i // cols) * cell_h + 6
        out.alpha_composite(sprite, (x, y))
        # mark the hotspot
        hx, hy = x + frame.xhot, y + frame.yhot
        draw.rectangle((hx - 1, hy - 1, hx + 1, hy + 1), outline=(255, 0, 0, 255))
        draw.text((i % cols * cell_w + 4, y + size + 6), name, fill=(255, 255, 255, 255))
    return out
