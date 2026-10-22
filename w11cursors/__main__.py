"""Command line interface: ``w11cursor build|install|uninstall|verify|preview|apply|doctor|list``."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

from . import apply as apply_mod
from . import doctor, mapping, preview, theme, verify

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
CREDIT_MARK = "Jepri Creations"


def _csv(value: str, allowed: list[str], what: str) -> list[str]:
    if value == "all":
        return allowed
    items = [v.strip() for v in value.split(",") if v.strip()]
    bad = [v for v in items if v not in allowed]
    if bad:
        raise SystemExit(f"unknown {what}: {', '.join(bad)} (choose from: {', '.join(allowed)}, all)")
    return items


def _selection(args) -> list[tuple[str, str, mapping.Variant]]:
    modes = _csv(args.modes, list(mapping.MODES), "mode")
    scales = _csv(args.scales, list(mapping.SCALES), "scale")
    by_key = {v.suffix.lower() or "default": v for v in mapping.VARIANTS}
    keys = _csv(args.variants.lower() if args.variants != "all" else "all",
                list(by_key), "variant")
    variants = [by_key[k] for k in keys]
    pack = theme.AssetPack(ASSETS)
    return [(m, s, v) for m, s, v in theme.selection(modes, scales, variants)
            if pack.has_variant(m, s, v)]


def _add_selection(p: argparse.ArgumentParser) -> None:
    p.add_argument("--modes", default="dark,light", help="dark, light (default: both)")
    p.add_argument("--scales", default="regular",
                   help="regular, small, or both as 'regular,small' (default: regular)")
    p.add_argument("--variants", default="default",
                   help="spinner colour variants: default, classic, amber, green, indigo, red, "
                        "squid, purple, candy, sunset, darkpurple, or 'all' (default: default)")


def _build(args, out: Path) -> list[Path]:
    pack = theme.AssetPack(ASSETS)
    out.mkdir(parents=True, exist_ok=True)
    cache: dict = {}
    built = []
    for mode, scale, variant in _selection(args):
        path = theme.build_theme(pack, mode, scale, variant, out, cache)
        print(f"built {path.name}")
        built.append(path)
    return built


def cmd_build(args) -> int:
    built = _build(args, Path(args.out))
    if args.verify:
        return _verify(built)
    return 0


def _verify(paths: list[Path], runtime: bool = True) -> int:
    failed = 0
    for path in paths:
        problems, checks, notes = verify.verify_theme(path, runtime)
        status = "ok" if not problems else f"{len(problems)} problem(s)"
        print(f"verify {path.name}: {checks} checks, {status}")
        for p in problems[:40]:
            print(f"  - {p}")
        for n in notes:
            print(f"  note: {n}")
        failed += bool(problems)
    return 1 if failed else 0


def cmd_verify(args) -> int:
    return _verify([Path(p).resolve() for p in args.themes], not args.no_runtime)


def _target(args) -> Path:
    if args.system:
        return Path(args.prefix or "/usr/share/icons")
    if args.prefix:
        return Path(args.prefix)
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "icons"


def _legacy_link(theme_dir: Path) -> None:
    """Symlink a theme into ~/.icons.

    Pre-2022 libXcursor builds (the one bundled with the Steam runtime, old
    Wine/Java/Electron apps) search ~/.icons but not ~/.local/share/icons; without
    the link they silently fall back to the X11 core font cursor.
    """
    legacy = Path.home() / ".icons"
    link = legacy / theme_dir.name
    if link.resolve() == theme_dir.resolve():
        return
    legacy.mkdir(exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink() if link.is_symlink() else shutil.rmtree(link)
    link.symlink_to(theme_dir)
    print(f"linked    {link} -> {theme_dir}")


def cmd_install(args) -> int:
    target = _target(args)
    with tempfile.TemporaryDirectory(prefix="w11cursors-") as tmp:
        built = _build(args, Path(tmp))
        if not built:
            raise SystemExit("nothing selected to build")
        if _verify(built, runtime=not args.skip_verify):
            raise SystemExit("verification failed, nothing installed")
        target.mkdir(parents=True, exist_ok=True)
        for path in built:
            dest = target / path.name
            staging = target / f".{path.name}.new"
            shutil.rmtree(staging, ignore_errors=True)
            shutil.copytree(path, staging, symlinks=True)
            shutil.rmtree(dest, ignore_errors=True)
            staging.rename(dest)
            print(f"installed {dest}")
            if args.legacy_link and not args.system:
                _legacy_link(dest)
    if args.apply:
        chosen = args.apply if args.apply != "auto" else built[0].name
        size = args.size
        if chosen not in {b.name for b in built}:
            print(f"note: {chosen} was not part of this install; applying anyway", file=sys.stderr)
        apply_mod.apply(chosen, size, dry_run=args.dry_run, flatpak=args.flatpak)
    else:
        print(f"\nNext: ./w11cursor apply {built[0].name} --size {args.size}")
    return 0


def cmd_uninstall(args) -> int:
    target = _target(args)
    removed = 0
    for path in sorted(target.glob(f"{mapping.THEME_PREFIX}-*")):
        credits = path / "CREDITS.txt"
        # Only remove directories we created.
        if path.is_dir() and credits.is_file() and CREDIT_MARK in credits.read_text(errors="ignore"):
            shutil.rmtree(path)
            print(f"removed {path}")
            removed += 1
    legacy = Path.home() / ".icons"
    if legacy.is_dir() and not args.system:
        for link in legacy.glob(f"{mapping.THEME_PREFIX}-*"):
            if link.is_symlink():
                link.unlink()
                print(f"removed {link}")
    if not removed:
        print(f"no {mapping.THEME_PREFIX} themes found in {target}")
    print("Note: settings written by `apply` (gtk, Xresources, environment.d, ~/.icons/default) "
          "are not reverted; restore the *.w11bak backups or point them at another theme.")
    return 0


def cmd_preview(args) -> int:
    img = preview.sheet(Path(args.theme), args.size)
    img.save(args.output)
    print(f"wrote {args.output}")
    return 0


def cmd_apply(args) -> int:
    name = args.theme
    found = [d for d in (_target(args), Path.home() / ".icons", Path("/usr/share/icons"))
             if (d / name / "cursors").is_dir()]
    if not found:
        raise SystemExit(f"theme {name!r} is not installed; run ./w11cursor install first")
    if not args.dry_run and not (Path.home() / ".icons" / name / "cursors").is_dir():
        src = next((d / name for d in (_target(args), Path("/usr/share/icons")) if (d / name / "cursors").is_dir()), None)
        if src and not str(src).startswith("/usr/"):
            _legacy_link(src)
    apply_mod.apply(name, args.size, dry_run=args.dry_run, flatpak=args.flatpak)
    return 0


def cmd_doctor(_args) -> int:
    return doctor.report()


def cmd_list(_args) -> int:
    pack = theme.AssetPack(ASSETS)
    for mode in mapping.MODES:
        for scale in mapping.SCALES:
            for v in mapping.VARIANTS:
                if pack.has_variant(mode, scale, v):
                    print(mapping.theme_name(mode, scale, v))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="w11cursor", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("build", help="build XCursor themes into a directory")
    _add_selection(p)
    p.add_argument("-o", "--out", default=str(ROOT / "build"))
    p.add_argument("--verify", action="store_true", help="verify the result")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("install", help="build, verify and install themes")
    _add_selection(p)
    p.add_argument("--system", action="store_true", help="install into /usr/share/icons (needs root)")
    p.add_argument("--prefix", help="install into this icons directory instead")
    p.add_argument("--legacy-link", action=argparse.BooleanOptionalAction, default=True,
                   help="symlink into ~/.icons for pre-2022 libXcursor builds such as the "
                        "Steam runtime's (default: on, --no-legacy-link to skip)")
    p.add_argument("--skip-verify", action="store_true", help="skip the libXcursor load test")
    p.add_argument("--apply", nargs="?", const="auto", metavar="THEME",
                   help="also configure GTK/Qt/X11/Wayland to use THEME (default: first built)")
    p.add_argument("--size", type=int, default=int(os.environ.get("XCURSOR_SIZE", 24)),
                   help="cursor size for --apply (default: $XCURSOR_SIZE or 24)")
    p.add_argument("--flatpak", action="store_true", help="with --apply: add Flatpak overrides")
    p.add_argument("--dry-run", action="store_true", help="with --apply: only print the changes")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("uninstall", help="remove installed Win11Concept-* themes")
    p.add_argument("--system", action="store_true")
    p.add_argument("--prefix")
    p.set_defaults(func=cmd_uninstall)

    p = sub.add_parser("verify", help="verify built/installed themes (structure + libXcursor)")
    p.add_argument("themes", nargs="+")
    p.add_argument("--no-runtime", action="store_true", help="skip the libXcursor load test")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("preview", help="render a contact sheet PNG of a theme")
    p.add_argument("theme")
    p.add_argument("-o", "--output", default="preview.png")
    p.add_argument("--size", type=int, default=96)
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("apply", help="point GTK/Qt/XWayland/Wayland/Flatpak at an installed theme")
    p.add_argument("theme")
    p.add_argument("--size", type=int, default=int(os.environ.get("XCURSOR_SIZE", 24)))
    p.add_argument("--system", action="store_true")
    p.add_argument("--prefix")
    p.add_argument("--flatpak", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("doctor", help="show which theme/size each layer uses and what disagrees")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("list", help="list every theme that can be built")
    p.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
