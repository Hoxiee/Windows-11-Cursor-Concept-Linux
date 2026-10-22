"""Cursors the upstream pack has no artwork for, drawn in the pack's style.

Windows has no copy/link drag badges, zoom lenses or a blank cursor, but Linux
toolkits ask for them constantly (file-manager drag and drop, image viewers,
maps).  They are rendered at 96px with the same palette as the real artwork
(black fill + white outline for dark, the inverse for light) and a soft drop
shadow; the regular size ladder then derives the other sizes.
"""

from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .wincur import Frame

N = 96   # canvas size
SS = 4   # supersampling factor

# (fill, outline) measured from the upstream pointer.cur artwork
PALETTE = {
    "dark": ((0, 0, 0), (249, 249, 249)),
    "light": ((249, 249, 249), (0, 0, 0)),
}


def _mask() -> Image.Image:
    return Image.new("L", (N * SS, N * SS), 0)


def _px(*values: float) -> list[float]:
    return [v * SS for v in values]


def _line(draw: ImageDraw.ImageDraw, p0, p1, width: float) -> None:
    """Thick line with round caps."""
    (x0, y0), (x1, y1) = p0, p1
    draw.line(_px(x0, y0, x1, y1), fill=255, width=round(width * SS))
    r = width / 2
    for x, y in (p0, p1):
        draw.ellipse(_px(x - r, y - r, x + r, y + r), fill=255)


def _plus(draw, cx, cy, half, width):
    _line(draw, (cx - half, cy), (cx + half, cy), width)
    _line(draw, (cx, cy - half), (cx, cy + half), width)


def _minus(draw, cx, cy, half, width):
    _line(draw, (cx - half, cy), (cx + half, cy), width)


def _grow(mask: Image.Image, radius: float) -> Image.Image:
    """Round dilation: blur the mask, then threshold at the grown edge."""
    if radius <= 0:
        return mask
    blurred = mask.filter(ImageFilter.GaussianBlur(radius * SS * 0.55))
    # A hard disc of radius r blurred with sigma s drops below ~0.5 at the edge;
    # a low threshold re-inflates it into a smooth outline of roughly +r.
    return blurred.point(lambda v: 255 if v > 22 else 0).filter(ImageFilter.GaussianBlur(SS * 0.4))


def _layer(mask: Image.Image, colour: tuple[int, int, int]) -> Image.Image:
    alpha = mask.reduce(SS)
    layer = Image.new("RGBA", (N, N), colour + (0,))
    layer.putalpha(alpha)
    return layer


def _shadow(alpha: Image.Image) -> Image.Image:
    blurred = alpha.filter(ImageFilter.GaussianBlur(1.6))
    blurred = ImageChops.offset(blurred, 0, 2).point(lambda v: int(v * 0.35))
    layer = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    layer.putalpha(blurred)
    return layer


def _compose(base: Image.Image, glyph_masks: list[tuple[Image.Image, tuple[int, int, int]]],
             shadow_mask: Image.Image) -> Image.Image:
    out = Image.alpha_composite(base, _shadow(shadow_mask.reduce(SS)))
    for mask, colour in glyph_masks:
        out = Image.alpha_composite(out, _layer(mask, colour))
    return out


def _outlined(shape_mask, fill, line, grow=3.5):
    return [(_grow(shape_mask, grow), line), (shape_mask, fill)]


def _zoom(mode: str, sign: str) -> Frame:
    fill, line = PALETTE[mode]
    m = _mask()
    d = ImageDraw.Draw(m)
    cx, cy, radius, stroke = 38, 38, 19.5, 7
    d.ellipse(_px(cx - radius - stroke / 2, cy - radius - stroke / 2,
                  cx + radius + stroke / 2, cy + radius + stroke / 2), fill=255)
    d.ellipse(_px(cx - radius + stroke / 2, cy - radius + stroke / 2,
                  cx + radius - stroke / 2, cy + radius - stroke / 2), fill=0)
    _line(d, (cx + radius * 0.72, cy + radius * 0.72), (79, 79), 9.5)
    inner = _mask()
    di = ImageDraw.Draw(inner)
    (_plus if sign == "+" else _minus)(di, cx, cy, 5, 4.5)
    # The sign sits inside the lens glass, so it gets a thinner outline than the
    # ring or the two outlines would merge and blot out the lens.
    outline = ImageChops.lighter(_grow(m, 3.5), _grow(inner, 2.0))
    layers = [(outline, line), (m, fill), (inner, fill)]
    img = _compose(Image.new("RGBA", (N, N), (0, 0, 0, 0)), layers, outline)
    return Frame(img, (cx, cy))


def _badge(mode: str, kind: str, pointer: Frame) -> Frame:
    fill, line = PALETTE[mode]
    base = pointer.image.resize((N, N)) if pointer.image.size != (N, N) else pointer.image.copy()
    cx, cy, radius = 72, 72, 15
    disc = _mask()
    ImageDraw.Draw(disc).ellipse(_px(cx - radius, cy - radius, cx + radius, cy + radius), fill=255)
    glyph = _mask()
    dg = ImageDraw.Draw(glyph)
    if kind == "copy":
        _plus(dg, cx, cy, 8, 5)
    else:  # alias: arrow pointing up and to the right
        _line(dg, (cx - 7, cy + 7), (cx + 3, cy - 3), 5)
        dg.polygon(_px(cx - 3, cy - 9, cx + 9, cy - 9, cx + 9, cy + 3), fill=255)
    layers = _outlined(disc, fill, line, grow=3.2) + [(glyph, line)]
    img = _compose(base, layers, _grow(disc, 3.2))
    return Frame(img, pointer.hotspot)


def render(recipe: str, mode: str, pointer: list[Frame]) -> list[Frame]:
    """Return a single 96px frame for ``recipe``."""
    if recipe == "blank":
        return [Frame(Image.new("RGBA", (N, N), (0, 0, 0, 0)), (0, 0))]
    if recipe in ("zoom-in", "zoom-out"):
        return [_zoom(mode, "+" if recipe == "zoom-in" else "-")]
    if recipe in ("copy", "alias"):
        largest = max(pointer, key=lambda f: f.size)
        return [_badge(mode, recipe, largest)]
    raise KeyError(recipe)
