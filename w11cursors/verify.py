"""Verify a built theme: structure, name coverage and real libXcursor loading."""

from __future__ import annotations

import ctypes
import ctypes.util
import multiprocessing
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import mapping, xcursor
from .imaging import SIZES

REQUEST_SIZES = (16, 24, 32, 36, 48, 64, 72, 96, 128, 192, 256)


class _XcursorImage(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("size", ctypes.c_uint32),
                ("width", ctypes.c_uint32), ("height", ctypes.c_uint32),
                ("xhot", ctypes.c_uint32), ("yhot", ctypes.c_uint32),
                ("delay", ctypes.c_uint32), ("pixels", ctypes.POINTER(ctypes.c_uint32))]


class _XcursorImages(ctypes.Structure):
    _fields_ = [("nimage", ctypes.c_int),
                ("images", ctypes.POINTER(ctypes.POINTER(_XcursorImage))),
                ("name", ctypes.c_char_p)]


def run_isolated(func, *args):
    """Run ``func(*args)`` in a forked child and return its result.

    libXcursor caches XCURSOR_PATH in a static variable on the first call, so
    every theme location needs a fresh process.  A crash in the native library
    (it parses untrusted-ish files) is reported instead of killing the caller.
    """
    ctx = multiprocessing.get_context("fork")
    receiver, sender = ctx.Pipe(duplex=False)

    def child():
        try:
            sender.send(("ok", func(*args)))
        except BaseException as exc:  # noqa: BLE001
            sender.send(("error", f"{type(exc).__name__}: {exc}"))

    proc = ctx.Process(target=child)
    proc.start()
    sender.close()
    try:
        status, value = receiver.recv()
    except EOFError:
        proc.join()
        raise RuntimeError(f"child process died (exit code {proc.exitcode})") from None
    proc.join()
    if status == "error":
        raise RuntimeError(value)
    return value


def required_names() -> list[str]:
    seen: dict[str, None] = {}
    for group in (mapping.WAYLAND_SHAPES, mapping.X11_CORE, mapping.TOOLKIT_EXTRAS,
                  mapping.all_names()):
        for name in group:
            seen.setdefault(name)
    return list(seen)


def _nearest(size: int) -> int:
    return min(SIZES, key=lambda s: (abs(s - size), s))


def check_structure(theme: Path) -> tuple[list[str], dict[str, list[xcursor.XImage]]]:
    problems: list[str] = []
    loaded: dict[str, list[xcursor.XImage]] = {}
    index = theme / "index.theme"
    if not index.is_file():
        problems.append("index.theme is missing")
    else:
        text = index.read_text(encoding="utf-8")
        if "[Icon Theme]" not in text:
            problems.append("index.theme has no [Icon Theme] section")
        if f"Name={theme.name}" not in text.splitlines():
            problems.append(f"index.theme Name must equal the directory name {theme.name!r}")
    cursors = theme / "cursors"
    if not cursors.is_dir():
        return problems + ["cursors/ directory is missing"], loaded

    for name in required_names():
        path = cursors / name
        if not path.exists():
            problems.append(f"missing cursor name: {name}")
    for link in cursors.iterdir():
        if link.is_symlink():
            target = os.readlink(link)
            if os.path.isabs(target) or "/" in target:
                problems.append(f"{link.name}: symlink must be a plain relative name, got {target}")
            elif not (cursors / target).is_file() or (cursors / target).is_symlink():
                problems.append(f"{link.name}: dangling or chained symlink -> {target}")

    for entry in mapping.ENTRIES:
        path = cursors / entry.file
        try:
            images = xcursor.read(str(path))
        except Exception as exc:  # noqa: BLE001 - report, keep checking
            problems.append(f"{entry.file}: unreadable ({exc})")
            continue
        loaded[entry.file] = images
        by_size: dict[int, list[xcursor.XImage]] = {}
        for im in images:
            by_size.setdefault(im.nominal, []).append(im)
            if im.width != im.nominal or im.height != im.nominal:
                problems.append(f"{entry.file}: {im.nominal}px image is {im.width}x{im.height}")
            px = im.pixels
            if any(px[i] > px[i + 3] or px[i + 1] > px[i + 3] or px[i + 2] > px[i + 3]
                   for i in range(0, len(px), 4)):
                problems.append(f"{entry.file}: {im.nominal}px pixels are not premultiplied")
                break
        if set(by_size) != set(SIZES):
            problems.append(f"{entry.file}: sizes {sorted(by_size)} != {list(SIZES)}")
        counts = {len(v) for v in by_size.values()}
        if len(counts) != 1:
            problems.append(f"{entry.file}: frame count differs between sizes")
        if entry.kind == "ani" and (counts.pop() if counts else 0) < 2:
            problems.append(f"{entry.file}: animation has fewer than 2 frames")
        if entry.kind == "ani" and any(im.delay <= 0 for im in images):
            problems.append(f"{entry.file}: animation frame with zero delay")
    return problems, loaded


def check_libxcursor(theme: Path, loaded: dict[str, list[xcursor.XImage]]) -> tuple[list[str], int]:
    """Load every name at several sizes through the system libXcursor (in a child process)."""
    try:
        return run_isolated(_check_libxcursor, theme, loaded)
    except RuntimeError as exc:
        return [f"libXcursor check crashed: {exc}"], 0


def _check_libxcursor(theme: Path, loaded: dict[str, list[xcursor.XImage]]) -> tuple[list[str], int]:
    libname = ctypes.util.find_library("Xcursor")
    if not libname:
        return ["libXcursor check skipped: library not found"], -1
    lib = ctypes.CDLL(libname)
    lib.XcursorLibraryLoadImages.restype = ctypes.POINTER(_XcursorImages)
    lib.XcursorLibraryLoadImages.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    lib.XcursorImagesDestroy.argtypes = [ctypes.POINTER(_XcursorImages)]

    old = os.environ.get("XCURSOR_PATH")
    os.environ["XCURSOR_PATH"] = str(theme.parent)
    problems: list[str] = []
    checks = 0
    try:
        files = {n: (theme / "cursors" / n).resolve().name for n in required_names()
                 if (theme / "cursors" / n).exists()}
        for name, real in files.items():
            expected = loaded.get(real)
            if expected is None:
                continue
            for request in REQUEST_SIZES:
                ptr = lib.XcursorLibraryLoadImages(name.encode(), theme.name.encode(), request)
                checks += 1
                if not ptr:
                    problems.append(f"libXcursor: {name}@{request} did not load")
                    continue
                try:
                    imgs = ptr.contents
                    want = _nearest(request)
                    want_imgs = [e for e in expected if e.nominal == want]
                    if imgs.nimage != len(want_imgs):
                        problems.append(f"libXcursor: {name}@{request} gave {imgs.nimage} frames, "
                                        f"expected {len(want_imgs)}")
                        continue
                    first = imgs.images[0].contents
                    got = ctypes.string_at(first.pixels, first.width * first.height * 4)
                    ref = want_imgs[0]
                    if (first.size != want or got != ref.pixels
                            or (first.xhot, first.yhot) != (ref.xhot, ref.yhot)):
                        problems.append(f"libXcursor: {name}@{request} returned different data "
                                        f"(size {first.size}, expected {want})")
                finally:
                    lib.XcursorImagesDestroy(ptr)
    finally:
        if old is None:
            os.environ.pop("XCURSOR_PATH", None)
        else:
            os.environ["XCURSOR_PATH"] = old
    return problems, checks


WAYLAND_SIZES = (24, 32, 48, 64, 96, 128, 20, 40)


def check_wayland(theme: Path, loaded: dict[str, list[xcursor.XImage]]) -> tuple[list[str], int]:
    """Load every name through libwayland-cursor against the running compositor.

    Skipped (not failed) when there is no compositor, compiler or headers.
    """
    if not os.environ.get("WAYLAND_DISPLAY"):
        return ["libwayland-cursor check skipped: no WAYLAND_DISPLAY"], -1
    cc = shutil.which("cc") or shutil.which("gcc")
    pkgconf = shutil.which("pkg-config")
    if not cc or not pkgconf:
        return ["libwayland-cursor check skipped: no C compiler or pkg-config"], -1
    flags = subprocess.run([pkgconf, "--cflags", "--libs", "wayland-client", "wayland-cursor"],
                           capture_output=True, text=True)
    if flags.returncode != 0:
        return ["libwayland-cursor check skipped: wayland development files missing"], -1

    with tempfile.TemporaryDirectory(prefix="w11cursors-wl-") as tmp:
        exe = Path(tmp) / "wayland_check"
        build = subprocess.run([cc, "-O1", "-o", str(exe), str(Path(__file__).with_name("wayland_check.c")),
                                *flags.stdout.split()], capture_output=True, text=True)
        if build.returncode != 0:
            return [f"libwayland-cursor check skipped: compile failed: {build.stderr.strip()[:200]}"], -1
        names = [n for n in required_names() if (theme / "cursors" / n).exists()]
        env = dict(os.environ, XCURSOR_PATH=str(theme.parent))
        res = subprocess.run([str(exe), theme.name, *map(str, WAYLAND_SIZES)], input="\n".join(names),
                             capture_output=True, text=True, env=env, timeout=120)
    if res.stdout.startswith("SKIP"):
        return [f"libwayland-cursor check skipped: {res.stdout.strip()}"], -1

    problems: list[str] = []
    checks = 0
    for line in res.stdout.splitlines():
        parts = line.split()
        checks += 1
        if len(parts) < 3 or parts[1] == "THEME-LOAD-FAILED" or parts[2] == "MISSING":
            problems.append(f"libwayland-cursor: {line.strip()}")
            continue
        size, name = int(parts[0]), parts[1]
        frames, w, h, xhot, yhot = map(int, parts[2:7])
        real = (theme / "cursors" / name).resolve().name
        want = _nearest(size)
        ref = [e for e in loaded.get(real, []) if e.nominal == want]
        if not ref:
            continue
        if (frames, w, h, xhot, yhot) != (len(ref), want, want, ref[0].xhot, ref[0].yhot):
            problems.append(f"libwayland-cursor: {name}@{size} -> {frames} frames {w}x{h} hot {xhot},{yhot}; "
                            f"expected {len(ref)} frames {want}x{want} hot {ref[0].xhot},{ref[0].yhot}")
    if res.returncode not in (0, 1) and not problems:
        problems.append(f"libwayland-cursor check exited {res.returncode}: {res.stderr.strip()[:200]}")
    return problems, checks


def verify_theme(theme: Path, runtime: bool = True) -> tuple[list[str], int, list[str]]:
    """Return (problems, number of checks, notes about checks that were skipped)."""
    problems, loaded = check_structure(theme)
    notes: list[str] = []
    checks = len(loaded)
    if runtime and not problems:
        for check in (check_libxcursor, check_wayland):
            found, done = check(theme, loaded)
            if done < 0:  # skipped: the message is informational, not a failure
                notes += found
            else:
                problems += found
            checks += max(done, 0)
    return problems, checks, notes
