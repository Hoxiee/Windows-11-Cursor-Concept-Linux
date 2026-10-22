"""Readers for the Windows cursor formats used by the upstream pack.

``.cur``  - static cursor, several sizes in one file (DIB or PNG payloads).
``.ani``  - RIFF/ACON animated cursor, every frame is an embedded ``.cur``.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass

from PIL import Image

JIFFY_MS = 1000 / 60  # ANI timing unit is 1/60 s


class CursorFormatError(ValueError):
    pass


@dataclass
class Frame:
    """One size of one cursor image, straight (non-premultiplied) RGBA."""

    image: Image.Image
    hotspot: tuple[int, int]

    @property
    def size(self) -> int:
        return max(self.image.size)


@dataclass
class Animation:
    steps: list[list[Frame]]  # per step: every size of that frame
    delays_ms: list[int]


def _decode_dib(blob: bytes, width: int, height: int) -> Image.Image:
    (hdr_size, dib_w, dib_h2, _planes, bpp, compression, _img_size, _xppm, _yppm,
     colors_used, _important) = struct.unpack("<IiiHHIIiiII", blob[:40])
    if hdr_size < 40:
        raise CursorFormatError(f"unsupported DIB header size {hdr_size}")
    if compression not in (0, 3):
        raise CursorFormatError(f"unsupported DIB compression {compression}")
    w = dib_w or width
    h = abs(dib_h2) // 2  # DIB height covers the XOR bitmap and the AND mask
    pos = hdr_size
    palette: list[tuple[int, int, int]] = []
    if bpp <= 8:
        n = colors_used or (1 << bpp)
        raw = blob[pos:pos + 4 * n]
        palette = [(raw[i + 2], raw[i + 1], raw[i]) for i in range(0, 4 * n, 4)]
        pos += 4 * n
    elif compression == 3 and hdr_size == 40:
        pos += 12  # BITFIELDS masks; every writer we care about uses plain BGRA

    xor_stride = ((w * bpp + 31) // 32) * 4
    xor = blob[pos:pos + xor_stride * h]
    pos += xor_stride * h
    and_stride = ((w + 31) // 32) * 4
    mask = blob[pos:pos + and_stride * h]

    if bpp == 32:
        img = Image.frombuffer("RGBA", (w, h), xor, "raw", "BGRA", xor_stride, -1)
        # Legacy cursors carry 32bpp colour with an all-zero alpha channel and
        # rely on the AND mask for transparency.
        if img.getchannel("A").getextrema() == (0, 0) and len(mask) == and_stride * h:
            img.putalpha(_mask_to_alpha(mask, w, h, and_stride))
        return img
    if bpp == 24:
        img = Image.frombuffer("RGB", (w, h), xor, "raw", "BGR", xor_stride, -1).convert("RGBA")
    elif bpp in (1, 4, 8):
        img = Image.new("RGBA", (w, h))
        px = img.load()
        for row in range(h):
            line = xor[row * xor_stride:(row + 1) * xor_stride]
            y = h - 1 - row
            for x in range(w):
                bit = x * bpp
                idx = (line[bit // 8] >> (8 - bpp - bit % 8)) & ((1 << bpp) - 1)
                r, g, b = palette[idx]
                px[x, y] = (r, g, b, 255)
    else:
        raise CursorFormatError(f"unsupported bit depth {bpp}")
    img.putalpha(_mask_to_alpha(mask, w, h, and_stride))
    return img


def _mask_to_alpha(mask: bytes, w: int, h: int, stride: int) -> Image.Image:
    """AND mask: 1 = transparent, 0 = opaque; rows are stored bottom-up."""
    alpha = Image.new("L", (w, h), 255)
    px = alpha.load()
    for row in range(h):
        y = h - 1 - row
        line = mask[row * stride:(row + 1) * stride]
        for x in range(w):
            if (line[x // 8] >> (7 - x % 8)) & 1:
                px[x, y] = 0
    return alpha


def parse_cur(data: bytes) -> list[Frame]:
    if len(data) < 6:
        raise CursorFormatError("file too short")
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    if reserved != 0 or kind not in (1, 2):
        raise CursorFormatError("not an ICO/CUR file")
    frames: list[Frame] = []
    for i in range(count):
        w, h, _colors, _res, hx, hy, size, offset = struct.unpack(
            "<BBBBHHII", data[6 + 16 * i:22 + 16 * i])
        w, h = w or 256, h or 256
        blob = data[offset:offset + size]
        if blob[:8] == b"\x89PNG\r\n\x1a\n":
            img = Image.open(io.BytesIO(blob)).convert("RGBA")
        else:
            img = _decode_dib(blob, w, h)
        if kind == 1:  # plain icon: no hotspot, use the centre
            hx, hy = img.width // 2, img.height // 2
        frames.append(Frame(img, (hx, hy)))
    return frames


def parse_ani(data: bytes) -> Animation:
    if data[:4] != b"RIFF" or data[8:12] != b"ACON":
        raise CursorFormatError("not a RIFF/ACON file")
    pos, end = 12, min(len(data), 8 + struct.unpack("<I", data[4:8])[0])
    header = None
    rates: list[int] = []
    seq: list[int] = []
    icons: list[bytes] = []
    while pos + 8 <= end:
        cid = data[pos:pos + 4]
        size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"anih":
            header = struct.unpack("<9I", body[:36])
        elif cid == b"rate":
            rates = list(struct.unpack(f"<{size // 4}I", body))
        elif cid == b"seq ":
            seq = list(struct.unpack(f"<{size // 4}I", body))
        elif cid == b"LIST" and body[:4] == b"fram":
            q = 4
            while q + 8 <= len(body):
                sub = body[q:q + 4]
                sub_size = struct.unpack("<I", body[q + 4:q + 8])[0]
                if sub == b"icon":
                    icons.append(body[q + 8:q + 8 + sub_size])
                q += 8 + sub_size + (sub_size & 1)
        pos += 8 + size + (size & 1)
    if header is None:
        raise CursorFormatError("ANI without anih chunk")
    _cb, n_frames, n_steps, _cx, _cy, _bpp, _planes, jif_rate, flags = header
    if not flags & 1:
        raise CursorFormatError("raw (non-ICON) ANI frames are not supported")
    if len(icons) != n_frames:
        raise CursorFormatError(f"expected {n_frames} frames, found {len(icons)}")
    order = seq or list(range(n_steps))
    steps, delays = [], []
    parsed = [parse_cur(blob) for blob in icons]
    for i, idx in enumerate(order[:n_steps]):
        steps.append(parsed[idx])
        jif = rates[i] if i < len(rates) else jif_rate
        delays.append(max(1, round(jif * JIFFY_MS)))
    return Animation(steps, delays)
