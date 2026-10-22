"""End-to-end X11 check (also what XWayland clients go through).

Starts a private Xvfb, publishes ``Xcursor.theme``/``Xcursor.size`` in
RESOURCE_MANAGER exactly like ``xrdb -merge`` does, and verifies that libXcursor
resolves our theme, its size and its images.  Skipped without Xvfb/libX11.
"""

import ctypes
import ctypes.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from w11cursors import mapping, theme, verify, xcursor  # noqa: E402


@unittest.skipUnless(shutil.which("Xvfb"), "Xvfb not installed")
class X11ResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        x11, xcur = ctypes.util.find_library("X11"), ctypes.util.find_library("Xcursor")
        if not x11 or not xcur:
            raise unittest.SkipTest("libX11/libXcursor missing")
        cls.x11, cls.xcur = ctypes.CDLL(x11), ctypes.CDLL(xcur)
        cls.tmp = tempfile.mkdtemp(prefix="w11cursors-x11-")
        pack = theme.AssetPack(ROOT / "assets")
        cls.theme = theme.build_theme(pack, "light", "regular", mapping.VARIANTS[0], Path(cls.tmp))
        r, w = os.pipe()
        cls.xvfb = subprocess.Popen(["Xvfb", "-displayfd", str(w), "-screen", "0", "320x200x24",
                                     "-nolisten", "tcp", "-noreset"], pass_fds=(w,), stderr=subprocess.DEVNULL)
        os.close(w)
        cls.display = f":{os.read(r, 16).decode().strip()}"
        os.close(r)

        cls.x11.XOpenDisplay.restype = ctypes.c_void_p
        cls.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        cls.x11.XDefaultRootWindow.restype = ctypes.c_ulong
        cls.x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        cls.x11.XInternAtom.restype = ctypes.c_ulong
        cls.x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        cls.x11.XChangeProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                                            ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_char_p, ctypes.c_int]
        cls.x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        cls.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        cls.xcur.XcursorGetTheme.restype = ctypes.c_char_p
        cls.xcur.XcursorGetTheme.argtypes = [ctypes.c_void_p]
        cls.xcur.XcursorGetDefaultSize.argtypes = [ctypes.c_void_p]
        cls.xcur.XcursorLibraryLoadImages.restype = ctypes.POINTER(verify._XcursorImages)
        cls.xcur.XcursorLibraryLoadImages.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]

    @classmethod
    def tearDownClass(cls):
        cls.xvfb.terminate()
        cls.xvfb.wait(timeout=10)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def publish(self, text: str) -> None:
        dpy = self.x11.XOpenDisplay(self.display.encode())
        self.assertTrue(dpy, "cannot open Xvfb")
        root = self.x11.XDefaultRootWindow(dpy)
        atom = self.x11.XInternAtom(dpy, b"RESOURCE_MANAGER", 0)
        data = text.encode()
        self.x11.XChangeProperty(dpy, root, atom, 31, 8, 0, data, len(data))  # XA_STRING, replace
        self.x11.XSync(dpy, 0)
        self.x11.XCloseDisplay(dpy)

    def _clean_env(self, **extra):
        """Environment without the developer's own XCURSOR_* so results are deterministic."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("XCURSOR_")}
        env.update(extra)
        return mock.patch.dict(os.environ, env, clear=True)

    def test_environment_overrides_resources(self):
        """XCURSOR_THEME/SIZE beat Xcursor.* - a stale export defeats `xrdb`."""
        self.publish(f"Xcursor.theme: {self.theme.name}\nXcursor.size: 48\n")
        with self._clean_env(XCURSOR_THEME="SomethingElse", XCURSOR_SIZE="64"):
            dpy = self.x11.XOpenDisplay(self.display.encode())
            self.assertEqual(self.xcur.XcursorGetTheme(dpy).decode(), "SomethingElse")
            self.assertEqual(self.xcur.XcursorGetDefaultSize(dpy), 64)
            self.x11.XCloseDisplay(dpy)

    def _probe(self):
        """Runs in a forked child: libXcursor caches XCURSOR_PATH per process."""
        errors = []
        os.environ["XCURSOR_PATH"] = self.tmp
        for key in ("XCURSOR_THEME", "XCURSOR_SIZE"):
            os.environ.pop(key, None)
        dpy = self.x11.XOpenDisplay(self.display.encode())
        theme_name = self.xcur.XcursorGetTheme(dpy)
        size = self.xcur.XcursorGetDefaultSize(dpy)
        if theme_name is None or theme_name.decode() != self.theme.name:
            errors.append(f"theme from resources: {theme_name!r}")
        if size != 48:
            errors.append(f"size from resources: {size}")
        ref = {e.file: xcursor.read(str(self.theme / "cursors" / e.file)) for e in mapping.ENTRIES}
        # the names a WM, xterm, Java and Tk ask for, via libXcursor's core-glyph names
        for name, real in (("left_ptr", "default"), ("xterm", "text"), ("watch", "wait"),
                           ("fleur", "move"), ("sb_h_double_arrow", "ew-resize"),
                           ("top_left_corner", "nwse-resize"), ("hand2", "pointer"),
                           ("question_arrow", "help"), ("X_cursor", "default")):
            ptr = self.xcur.XcursorLibraryLoadImages(name.encode(), self.theme.name.encode(), size)
            if not ptr:
                errors.append(f"{name} fell back to the X core font cursor")
                continue
            first = ptr.contents.images[0].contents
            want = [i for i in ref[real] if i.nominal == 48]
            got = (first.size, ptr.contents.nimage, first.xhot, first.yhot)
            exp = (48, len(want), want[0].xhot, want[0].yhot)
            if got != exp:
                errors.append(f"{name}: got {got}, expected {exp}")
        self.x11.XCloseDisplay(dpy)
        return errors

    def test_resources_select_theme_and_size(self):
        self.publish(f"Xcursor.theme: {self.theme.name}\nXcursor.size: 48\n")
        self.assertEqual(verify.run_isolated(self._probe), [])


if __name__ == "__main__":
    unittest.main()
