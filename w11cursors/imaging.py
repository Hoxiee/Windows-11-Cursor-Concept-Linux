"""Image helpers: size ladder, premultiplied resampling, hotspot maths."""

from __future__ import annotations

from PIL import Image, ImageChops

from .wincur import Frame
from .xcursor import XImage

# The pack ships 32/48/64/96.  24 is the de-facto XCURSOR_SIZE default on
# Linux, 40/56 give finer steps and 128 covers 4x HiDPI; all derived from the 96px artwork;
# libXcursor/libwayland-cursor pick the nominal size closest to the request.
SIZES = (24, 32, 40, 48, 56, 64, 96, 128)


def _premultiplied_resize(img: Image.Image, size: int) -> Image.Image:
    out = img.convert("RGBa").resize((size, size), Image.LANCZOS)
    # Lanczos overshoots; a premultiplied colour channel must never exceed alpha.
    r, g, b, a = out.split()
    r, g, b = (ImageChops.darker(c, a) for c in (r, g, b))
    return Image.merge("RGBa", (r, g, b, a))


def _bgra_bytes(premultiplied: Image.Image) -> bytes:
    r, g, b, a = premultiplied.split()
    return Image.merge("RGBA", (b, g, r, a)).tobytes()


def _scale_hotspot(hotspot: tuple[int, int], src: int, dst: int) -> tuple[int, int]:
    # The hotspot is the top-left corner of its pixel, so scale the coordinate
    # itself (not the pixel centre) and snap to the nearest pixel.
    return tuple(min(dst - 1, max(0, int(v * dst / src + 0.5))) for v in hotspot)  # type: ignore[return-value]


def ladder(frames: list[Frame], sizes=SIZES) -> list[XImage]:
    """Return one XImage per nominal size for a single cursor frame.

    Native sizes are used verbatim; the rest are resampled from the largest
    source image.
    """
    native = {f.size: f for f in frames if f.image.width == f.image.height}
    if not native:
        raise ValueError("cursor has no square image")
    largest = native[max(native)]
    out = []
    for size in sizes:
        if size in native:
            frame = native[size]
            pre = frame.image.convert("RGBa")
            hot = frame.hotspot
        else:
            pre = _premultiplied_resize(largest.image, size)
            hot = _scale_hotspot(largest.hotspot, largest.size, size)
        out.append(XImage(size, size, size, hot[0], hot[1], 0, _bgra_bytes(pre)))
    return out


def with_delay(images: list[XImage], delay_ms: int) -> list[XImage]:
    for im in images:
        im.delay = delay_ms
    return images


def mirror(frames: list[Frame]) -> list[Frame]:
    """Horizontal flip (used for the legacy X11 right_ptr arrow)."""
    return [Frame(f.image.transpose(Image.FLIP_LEFT_RIGHT),
                  (f.image.width - 1 - f.hotspot[0], f.hotspot[1])) for f in frames]


def rotate_ccw(frames: list[Frame]) -> list[Frame]:
    """Quarter turn counter-clockwise (I-beam -> vertical-text)."""
    return [Frame(f.image.transpose(Image.ROTATE_90),
                  (f.hotspot[1], f.image.width - 1 - f.hotspot[0])) for f in frames]
