"""Reader/writer for the XCursor file format (libXcursor, libwayland-cursor).

Layout: 16-byte header, a table of contents, then one 36-byte-headed chunk per
image.  Pixels are premultiplied ARGB32, little endian (so B,G,R,A in memory).
For an animation the nominal ``size`` groups the frames and the ``delay`` of
every chunk is in milliseconds.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = b"Xcur"
FILE_VERSION = 0x10000
IMAGE_TYPE = 0xFFFD0002
IMAGE_VERSION = 1
MAX_DIM = 0x7FFF  # libXcursor rejects anything larger


@dataclass
class XImage:
    nominal: int
    width: int
    height: int
    xhot: int
    yhot: int
    delay: int
    pixels: bytes  # premultiplied BGRA bytes, width*height*4


def write(path: str, images: list[XImage]) -> None:
    if not images:
        raise ValueError("a cursor needs at least one image")
    for im in images:
        if not (0 < im.width <= MAX_DIM and 0 < im.height <= MAX_DIM):
            raise ValueError(f"bad image size {im.width}x{im.height}")
        if not (0 <= im.xhot < im.width and 0 <= im.yhot < im.height):
            raise ValueError(f"hotspot {im.xhot},{im.yhot} outside {im.width}x{im.height}")
        if len(im.pixels) != im.width * im.height * 4:
            raise ValueError("pixel buffer does not match image size")
    header_len = 16
    toc_len = 12 * len(images)
    pos = header_len + toc_len
    toc, chunks = [], []
    for im in images:
        toc.append(struct.pack("<III", IMAGE_TYPE, im.nominal, pos))
        chunk = struct.pack("<IIIIIIIII", 36, IMAGE_TYPE, im.nominal, IMAGE_VERSION,
                            im.width, im.height, im.xhot, im.yhot, im.delay) + im.pixels
        chunks.append(chunk)
        pos += len(chunk)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<4sIII", MAGIC, header_len, FILE_VERSION, len(images)))
        fh.write(b"".join(toc))
        fh.write(b"".join(chunks))


def read(path: str) -> list[XImage]:
    with open(path, "rb") as fh:
        data = fh.read()
    magic, header_len, _version, ntoc = struct.unpack("<4sIII", data[:16])
    if magic != MAGIC:
        raise ValueError("not an XCursor file")
    images = []
    for i in range(ntoc):
        kind, _subtype, pos = struct.unpack("<III", data[header_len + 12 * i:header_len + 12 * i + 12])
        if kind != IMAGE_TYPE:
            continue
        (_hs, _ty, nominal, _ver, w, h, xh, yh, delay) = struct.unpack("<IIIIIIIII", data[pos:pos + 36])
        pixels = data[pos + 36:pos + 36 + w * h * 4]
        if len(pixels) != w * h * 4:
            raise ValueError("truncated image chunk")
        images.append(XImage(nominal, w, h, xh, yh, delay, pixels))
    return images
