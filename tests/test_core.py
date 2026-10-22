import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from w11cursors import apply, imaging, mapping, theme, verify, wincur, xcursor  # noqa: E402


def make_cur(size=2, hotspot=(1, 0), alpha=255, mask_byte=0x00):
    """Hand-built single-image CUR with a 32bpp DIB (bottom-up BGRA) and AND mask."""
    px = b"".join(bytes([10 * i, 20, 30, alpha]) for i in range(size * size))  # B,G,R,A
    hdr = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    blob = hdr + px + bytes([mask_byte, 0, 0, 0]) * size
    entry = struct.pack("<BBBBHHII", size, size, 0, 0, hotspot[0], hotspot[1], len(blob), 22)
    return struct.pack("<HHH", 0, 2, 1) + entry + blob


class WinCurTests(unittest.TestCase):
    def test_cur_pixels_and_hotspot(self):
        (frame,) = wincur.parse_cur(make_cur())
        self.assertEqual(frame.hotspot, (1, 0))
        self.assertEqual(frame.image.size, (2, 2))
        # rows are stored bottom-up; first stored pixel (B=0) is bottom-left
        self.assertEqual(frame.image.getpixel((0, 1)), (30, 20, 0, 255))
        self.assertEqual(frame.image.getpixel((1, 0)), (30, 20, 30, 255))

    def test_zero_alpha_falls_back_to_and_mask(self):
        # AND mask bit 1 = transparent.  0xC0: both columns, 0x80: only the left one.
        (all_clear,) = wincur.parse_cur(make_cur(alpha=0, mask_byte=0xC0))
        self.assertEqual(all_clear.image.getchannel("A").getextrema(), (0, 0))
        (half,) = wincur.parse_cur(make_cur(alpha=0, mask_byte=0x80))
        self.assertEqual(half.image.getpixel((0, 0))[3], 0)
        self.assertEqual(half.image.getpixel((1, 0))[3], 255)
        # real alpha wins over the mask
        (kept,) = wincur.parse_cur(make_cur(alpha=200, mask_byte=0xC0))
        self.assertEqual(kept.image.getchannel("A").getextrema(), (200, 200))

    def test_rejects_garbage(self):
        with self.assertRaises(wincur.CursorFormatError):
            wincur.parse_cur(b"not a cursor")
        with self.assertRaises(wincur.CursorFormatError):
            wincur.parse_ani(b"RIFF\x00\x00\x00\x00WAVE")

    def _ani(self, rates=None, seq=None, frames=2, jif=2):
        cur = make_cur()
        icons = b"".join(b"icon" + struct.pack("<I", len(cur)) + cur + (b"\0" * (len(cur) & 1))
                         for _ in range(frames))
        steps = len(seq) if seq else frames
        chunks = b"anih" + struct.pack("<I", 36) + struct.pack("<9I", 36, frames, steps, 0, 0, 0, 0, jif, 1)
        if rates:
            chunks += b"rate" + struct.pack("<I", 4 * len(rates)) + struct.pack(f"<{len(rates)}I", *rates)
        if seq:
            chunks += b"seq " + struct.pack("<I", 4 * len(seq)) + struct.pack(f"<{len(seq)}I", *seq)
        chunks += b"LIST" + struct.pack("<I", 4 + len(icons)) + b"fram" + icons
        return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"ACON" + chunks

    def test_ani_default_rate(self):
        anim = wincur.parse_ani(self._ani())
        self.assertEqual(len(anim.steps), 2)
        self.assertEqual(anim.delays_ms, [33, 33])  # 2 jiffies = 33 ms

    def test_ani_rate_and_seq(self):
        anim = wincur.parse_ani(self._ani(rates=[6, 12, 3], seq=[0, 1, 0]))
        self.assertEqual(anim.delays_ms, [100, 200, 50])
        self.assertEqual(len(anim.steps), 3)


class XCursorTests(unittest.TestCase):
    def test_roundtrip(self):
        img = xcursor.XImage(32, 2, 2, 1, 1, 33, bytes(range(16)))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c")
            xcursor.write(path, [img])
            (back,) = xcursor.read(path)
        self.assertEqual(back, img)

    def test_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = xcursor.XImage(32, 2, 2, 5, 0, 0, bytes(16))  # hotspot outside
            with self.assertRaises(ValueError):
                xcursor.write(os.path.join(tmp, "c"), [bad])
            with self.assertRaises(ValueError):
                xcursor.write(os.path.join(tmp, "c"), [])


class ImagingTests(unittest.TestCase):
    def _frames(self):
        out = []
        for size in (32, 96):
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            img.paste((200, 100, 50, 255), (size // 4, size // 4, size // 2, size // 2))
            out.append(wincur.Frame(img, (size * 3 // 32, size * 9 // 32)))
        return out

    def test_ladder_has_every_size_and_scaled_hotspots(self):
        images = imaging.ladder(self._frames())
        self.assertEqual([i.nominal for i in images], list(imaging.SIZES))
        by = {i.nominal: i for i in images}
        self.assertEqual((by[96].xhot, by[96].yhot), (9, 27))
        self.assertEqual((by[24].xhot, by[24].yhot), (2, 7))   # 9/4, 27/4 rounded
        self.assertEqual((by[128].xhot, by[128].yhot), (12, 36))
        for im in images:
            self.assertTrue(0 <= im.xhot < im.width and 0 <= im.yhot < im.height)

    def test_pixels_are_premultiplied(self):
        for im in imaging.ladder(self._frames()):
            px = im.pixels
            for i in range(0, len(px), 4):
                self.assertLessEqual(max(px[i:i + 3]), px[i + 3])

    def test_mirror_and_rotate_move_hotspot_with_the_pixels(self):
        (f,) = [wincur.Frame(Image.new("RGBA", (8, 8)), (1, 2))]
        self.assertEqual(imaging.mirror([f])[0].hotspot, (6, 2))
        self.assertEqual(imaging.rotate_ccw([f])[0].hotspot, (2, 6))


class MappingTests(unittest.TestCase):
    def test_names_unique(self):
        names = mapping.all_names()
        dupes = {n for n in names if names.count(n) > 1}
        self.assertFalse(dupes, f"duplicate cursor names: {dupes}")

    def test_x11_core_list_is_complete(self):
        self.assertEqual(len(mapping.X11_CORE), 77)
        missing = set(mapping.X11_CORE) - set(mapping.all_names())
        self.assertFalse(missing)

    def test_wayland_and_toolkit_names_covered(self):
        names = set(mapping.all_names())
        self.assertFalse(set(mapping.WAYLAND_SHAPES) - names)
        self.assertFalse(set(mapping.TOOLKIT_EXTRAS) - names)

    def test_hash_names_are_32_hex(self):
        import re
        hashes = [n for n in mapping.all_names() if re.fullmatch(r"[0-9a-f]{32}", n)]
        self.assertGreaterEqual(len(hashes), 20)

    def test_every_source_exists_in_assets(self):
        pack = theme.AssetPack(ROOT / "assets")
        for mode in mapping.MODES:
            for scale in mapping.SCALES:
                for e in mapping.ENTRIES:
                    if e.kind in ("cur", "mirror", "rotate"):
                        self.assertTrue(pack.path(mode, scale, "base", f"{e.source}.cur").is_file(), e)
                    elif e.kind == "alt":
                        self.assertTrue(pack.path(mode, scale, "alternatives", f"{e.source}.cur").is_file(), e)


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="w11cursors-test-")
        pack = theme.AssetPack(ROOT / "assets")
        cls.path = theme.build_theme(pack, "dark", "small", mapping.VARIANTS[2], Path(cls.tmp))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def fresh_copy(self):
        dest = Path(self.tmp) / "copy" / self.path.name
        shutil.rmtree(dest.parent, ignore_errors=True)
        dest.parent.mkdir()
        shutil.copytree(self.path, dest, symlinks=True)
        return dest

    def test_naming(self):
        self.assertEqual(self.path.name, "Win11Concept-Dark-Amber-Small")

    def test_clean_theme_passes_structure_and_runtime(self):
        problems, checks, _notes = verify.verify_theme(self.path)
        self.assertEqual(problems, [])
        self.assertGreater(checks, 150)

    def test_animation_timing_and_frame_counts(self):
        pack = theme.AssetPack(ROOT / "assets")
        for cursor, stem in (("wait", "busy"), ("progress", "working")):
            source = pack.ani("dark", "small", "03_amber", stem)
            images = xcursor.read(str(self.path / "cursors" / cursor))
            self.assertEqual({i.delay for i in images}, {33})  # 2 jiffies
            self.assertEqual(len(images), len(source.steps) * len(imaging.SIZES))
            self.assertGreater(len(source.steps), 30)

    def test_aliases_are_relative_symlinks(self):
        link = self.path / "cursors" / "left_ptr"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "default")

    def test_detects_missing_alias(self):
        theme_dir = self.fresh_copy()
        (theme_dir / "cursors" / "col-resize").unlink()
        problems, _ = verify.check_structure(theme_dir)
        self.assertTrue(any("col-resize" in p for p in problems))

    def test_detects_dangling_symlink(self):
        theme_dir = self.fresh_copy()
        (theme_dir / "cursors" / "xterm").unlink()
        os.symlink("nope", theme_dir / "cursors" / "xterm")
        problems, _ = verify.check_structure(theme_dir)
        self.assertTrue(any("xterm" in p and "dangling" in p for p in problems))

    def test_detects_name_mismatch(self):
        theme_dir = self.fresh_copy()
        (theme_dir / "index.theme").write_text("[Icon Theme]\nName=Other\n")
        problems, _ = verify.check_structure(theme_dir)
        self.assertTrue(any("Name must equal" in p for p in problems))

    def test_detects_truncated_file_and_missing_sizes(self):
        theme_dir = self.fresh_copy()
        images = [i for i in xcursor.read(str(theme_dir / "cursors" / "default")) if i.nominal != 128]
        xcursor.write(str(theme_dir / "cursors" / "default"), images)
        problems, _ = verify.check_structure(theme_dir)
        self.assertTrue(any("default: sizes" in p for p in problems))
        data = (theme_dir / "cursors" / "text").read_bytes()
        (theme_dir / "cursors" / "text").write_bytes(data[:-100])
        problems, _ = verify.check_structure(theme_dir)
        self.assertTrue(any(p.startswith("text: unreadable") for p in problems))

    def test_detects_straight_alpha(self):
        theme_dir = self.fresh_copy()
        images = xcursor.read(str(theme_dir / "cursors" / "default"))
        px = bytearray(images[0].pixels)
        px[0:4] = bytes([255, 255, 255, 10])  # colour > alpha: not premultiplied
        images[0].pixels = bytes(px)
        xcursor.write(str(theme_dir / "cursors" / "default"), images)
        problems, _ = verify.check_structure(theme_dir)
        self.assertTrue(any("not premultiplied" in p for p in problems))


class ApplyTests(unittest.TestCase):
    def test_set_ini_keys_preserves_content(self):
        src = "# comment\n[Settings]\ngtk-theme-name=Foo\ngtk-cursor-theme-size = 16\n[Other]\nx=1\n"
        out = apply.set_ini_keys(src, "Settings", {"gtk-cursor-theme-name": "T", "gtk-cursor-theme-size": "24"})
        self.assertIn("# comment", out)
        self.assertIn("gtk-theme-name=Foo", out)
        self.assertIn("gtk-cursor-theme-size=24", out)
        self.assertIn("[Other]\nx=1", out)
        self.assertEqual(out.count("gtk-cursor-theme-name=T"), 1)
        # new key lands inside [Settings], not after [Other]
        self.assertLess(out.index("gtk-cursor-theme-name=T"), out.index("[Other]"))

    def test_set_ini_keys_creates_section(self):
        self.assertEqual(apply.set_ini_keys("", "Settings", {"a": "b"}), "[Settings]\na=b\n")

    def test_set_ini_keys_is_idempotent(self):
        once = apply.set_ini_keys("[Settings]\n", "Settings", {"a": "b"})
        self.assertEqual(apply.set_ini_keys(once, "Settings", {"a": "b"}), once)

    def _patched(self, home):
        return mock.patch.multiple(apply, HOME=home, CONFIG=home / ".config", DATA=home / ".local/share")

    def test_apply_writes_everything_and_backs_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".Xresources").write_text("Xft.dpi: 96\nXcursor.theme: Old\nXcursor.size: 99\n")
            (home / ".profile").write_text('export XCURSOR_THEME="Old"\nexport XCURSOR_SIZE=24\n')
            env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "SWAYSOCK",
                                                                    "HYPRLAND_INSTANCE_SIGNATURE")}
            env["PATH"] = "/nonexistent"  # no gsettings/xrdb/hyprctl/flatpak: pure file steps
            env["XDG_CURRENT_DESKTOP"] = "niri"
            with self._patched(home), mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch("builtins.print"):
                a = apply.apply("Win11Concept-Dark", 32)
            res = (home / ".Xresources").read_text()
            self.assertIn("Xft.dpi: 96", res)
            self.assertIn("Xcursor.theme: Win11Concept-Dark", res)
            self.assertIn("Xcursor.size: 32", res)
            self.assertNotIn("Old", res)
            self.assertTrue((home / ".Xresources.w11bak").exists())
            for ver in ("gtk-3.0", "gtk-4.0"):
                ini = (home / ".config" / ver / "settings.ini").read_text()
                self.assertIn("gtk-cursor-theme-name=Win11Concept-Dark", ini)
                self.assertIn("gtk-cursor-theme-size=32", ini)
            env_file = (home / ".config/environment.d/90-w11cursors.conf").read_text()
            self.assertIn("XCURSOR_THEME=Win11Concept-Dark", env_file)
            for base in (home / ".icons", home / ".local/share/icons"):
                self.assertIn("Inherits=Win11Concept-Dark", (base / "default/index.theme").read_text())
            # the stale ~/.profile exports were rewritten, so nothing overrides the theme now
            self.assertIn('XCURSOR_THEME="Win11Concept-Dark"', (home / ".profile").read_text())
            with self._patched(home), mock.patch.dict(os.environ, {"PATH": "/nonexistent"}, clear=True):
                self.assertEqual(a.conflicts(), [])

    def test_existing_configs_rewritten_in_place_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cfg = home / ".config"
            (cfg / "niri/config.d").mkdir(parents=True)
            (cfg / "niri/backups").mkdir()
            (cfg / "niri/config.d/10.kdl").write_text(
                'cursor {\n    xcursor-theme "Old"\n    xcursor-size 24\n    hide-when-typing\n}\n')
            (cfg / "niri/config.d/40.kdl").write_text(
                'environment {\n    XCURSOR_THEME "Old"\n    XCURSOR_SIZE "24"\n    OTHER "x"\n}\n')
            (cfg / "niri/backups/old.kdl").write_text('xcursor-theme "Keep"\n')
            (cfg / "niri/config.d/00-none.kdl").write_text("// nothing about cursors\n")
            (cfg / "hypr").mkdir()
            (cfg / "hypr/hyprland.conf").write_text(
                "env = XCURSOR_THEME,Old\nenv = XCURSOR_SIZE, 24\nexec-once = hyprctl setcursor Old 24\n"
                "# env = XCURSOR_THEME,Commented\n")
            (cfg / "sway").mkdir()
            (cfg / "sway/config").write_text("seat seat0 xcursor_theme Old 24\n")
            (home / ".profile").write_text('export XCURSOR_THEME="Old"\nexport XCURSOR_SIZE=24\nPATH=x\n')
            (home / ".zshrc").write_text("# no cursor settings here\n")
            env = {"PATH": "/nonexistent"}
            with self._patched(home), mock.patch.dict(os.environ, env, clear=True), mock.patch("builtins.print"):
                apply.Applier("New", 32).existing_configs()
            kdl = (cfg / "niri/config.d/10.kdl").read_text()
            self.assertIn('xcursor-theme "New"', kdl)
            self.assertIn("xcursor-size 32", kdl)
            self.assertIn("hide-when-typing", kdl)
            env_kdl = (cfg / "niri/config.d/40.kdl").read_text()
            self.assertIn('XCURSOR_THEME "New"', env_kdl)
            self.assertIn('XCURSOR_SIZE "32"', env_kdl)
            self.assertIn('OTHER "x"', env_kdl)
            self.assertEqual((cfg / "niri/backups/old.kdl").read_text(), 'xcursor-theme "Keep"\n')
            self.assertFalse((cfg / "niri/config.d/00-none.kdl.w11bak").exists())
            hypr = (cfg / "hypr/hyprland.conf").read_text()
            self.assertIn("env = XCURSOR_THEME,New", hypr)
            self.assertIn("env = XCURSOR_SIZE, 32", hypr)
            self.assertIn("hyprctl setcursor New 32", hypr)
            self.assertIn("# env = XCURSOR_THEME,Commented", hypr)
            self.assertEqual((cfg / "sway/config").read_text(), "seat seat0 xcursor_theme New 32\n")
            self.assertEqual((home / ".profile").read_text(),
                             'export XCURSOR_THEME="New"\nexport XCURSOR_SIZE="32"\nPATH=x\n')
            self.assertTrue((home / ".profile.w11bak").exists())
            self.assertFalse((home / ".bashrc").exists())  # never creates files

    def test_conflicts_report_live_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = {"PATH": "/nonexistent", "XCURSOR_THEME": "Stale", "XCURSOR_SIZE": "32",
                   "XCURSOR_PATH": "/opt/icons"}
            with self._patched(home), mock.patch.dict(os.environ, env, clear=True):
                found = apply.Applier("Win11Concept-Dark", 32).conflicts()
            self.assertEqual(len(found), 2)  # stale theme + XCURSOR_PATH; matching size is fine
            self.assertTrue(any("XCURSOR_THEME=Stale" in f for f in found))
            self.assertTrue(any("XCURSOR_PATH" in f for f in found))

    def test_dry_run_touches_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with self._patched(home), mock.patch.dict(os.environ, {"PATH": "/nonexistent"}), \
                    mock.patch("builtins.print"):
                apply.apply("T", 24, dry_run=True)
            self.assertEqual(list(home.rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
