# Windows 11 Cursor Concept for Linux

The **dark** and **light** packs of Jepri Creations' *Windows 11 Cursors Concept HD v2.2*,
converted to proper XCursor themes for X11, XWayland and Wayland. Personal use only, see
[NOTICE.md](NOTICE.md).

* 2 modes (dark, light) x 2 scales (regular, small) x 11 spinner colours = 42 themes
* sizes 24, 32, 40, 48, 56, 64, 96, 128 px, animated busy/progress cursors, correct hotspots
* every cursor name the Linux world asks for (see [Coverage](#coverage))
* a tool that makes GTK, Qt, XWayland, the compositor and your shell agree on the theme

## Quick start

```sh
./install.sh --apply            # dark + light into ~/.local/share/icons, dark becomes active
./w11cursor doctor              # which theme/size does every layer use?
```

Requirements: `python3`, Pillow (`pacman -S python-pillow` / `apt install python3-pil`).
Verification additionally uses `libXcursor`, and, when a compositor, `gcc` and the Wayland
headers are present, `libwayland-cursor`; both checks are skipped otherwise.

```sh
./install.sh --apply Win11Concept-Light --size 32       # pick another theme and size
./install.sh --scales regular,small --variants all      # everything (~12 MB per theme)
./install.sh --system                                   # /usr/share/icons, needs root
./install.sh --apply --dry-run                          # show what apply would change
./uninstall.sh                                          # remove Win11Concept-* themes
```

Theme names: `Win11Concept-<Dark|Light>[-<Colour>][-Small]`, e.g. `Win11Concept-Dark`,
`Win11Concept-Light-Amber`, `Win11Concept-Dark-Small`. Colours change only the busy/progress
spinners: `Classic Amber Green Indigo Red Squid Purple Candy Sunset DarkPurple` (the
latter exists for regular size only). `./w11cursor list` prints them all.

## Commands

| command | what it does |
| --- | --- |
| `install` | build, verify, install (`--prefix`, `--system`, `--no-legacy-link`, `--apply`) |
| `apply THEME [--size N] [--flatpak] [--dry-run]` | make every layer use THEME |
| `doctor` | show theme/size per layer, flag missing themes and disagreements |
| `verify DIR...` | structure + real `libXcursor` and `libwayland-cursor` loading |
| `build -o DIR` | build themes without installing |
| `preview THEME -o x.png` | contact sheet with hotspots marked |

## Why `apply` exists: Wayland, XWayland and who decides the cursor

A theme on disk is only half the job. Different components pick the theme independently,
and one stale setting is enough to get "right cursor on the desktop, wrong one in app X":

| layer | who uses it | set by `apply` |
| --- | --- | --- |
| compositor config (`cursor {}`, `seat xcursor_theme`, `hyprctl setcursor`) | cursor drawn by the compositor, native Wayland clients using `cursor-shape-v1` | existing lines in niri, Hyprland, sway, labwc configs are rewritten in place |
| `XCURSOR_THEME` / `XCURSOR_SIZE` | XWayland and X11 clients, GTK, Qt, Chromium, Firefox, children of the compositor | `environment.d`, D-Bus/systemd activation environment, existing exports in shell profiles |
| `Xcursor.theme` X resource | X11 / XWayland clients via libXcursor (**environment wins over it**) | `~/.Xresources` (+ `xrdb -merge` when available) |
| `~/.icons/default/index.theme` | any libXcursor client with nothing else configured | `Inherits=<theme>` |
| GTK `settings.ini`, GSettings | GTK 3/4, xdg-desktop-portal, Flatpak GTK apps | both |
| KDE `kcminputrc` | Plasma on Wayland and X11 | when running under KDE |
| Flatpak sandbox | cannot see `~/.icons` | `--flatpak` adds overrides *(not tested here, flatpak is not installed on the dev machine)* |

Facts worth knowing, all verified while building this:

* `XCURSOR_THEME`/`XCURSOR_SIZE` **override** `Xcursor.*` X resources and `~/.icons/default`.
  A forgotten `export XCURSOR_THEME=...` in `~/.profile` silently defeats everything else,
  so `apply` rewrites existing exports and `doctor` reports them.
* libXcursor caches `XCURSOR_PATH` at the first call per process; the verifier therefore runs
  its libXcursor test in a fresh process per theme.
* Missing names are not harmless: libXcursor falls back to the ugly X11 core *font* cursor
  and compositors show a default arrow or nothing. Hence the complete alias table.
* Running programs keep the cursor they loaded. Restart them (or re-login) after `apply`.
* Sizes: 24 is the Linux default, 32 matches Windows at 100 % (the artwork has generous padding, so 32-40 looks right on most screens). Request sizes are matched to
  the nearest of 24/32/40/48/56/64/96/128, so fractional scaling (1.25x, 1.5x ...) works.
* **Steam** (and other apps with a bundled pre-2022 libXcursor: Steam runtime, old Wine/Java)
  searches `~/.icons` but not `~/.local/share/icons`. Without the `~/.icons/<theme>` symlink they show
  the bare X11 core arrow. `install` and `apply` create that symlink; `doctor` warns when it is missing.
  Steam also inherits the environment of whatever launched it (launcher service, desktop session):
  restart the launcher, or re-login, after changing the theme or size.
* Hyprland also supports hyprcursor; it falls back to these XCursor themes, nothing extra
  is needed.

### Per-compositor snippets (when your config has no cursor lines yet)

```
niri      cursor { xcursor-theme "Win11Concept-Dark"; xcursor-size 24 }
Hyprland  env = XCURSOR_THEME,Win11Concept-Dark / env = XCURSOR_SIZE,24
          exec-once = hyprctl setcursor Win11Concept-Dark 24
sway      seat seat0 xcursor_theme Win11Concept-Dark 24
labwc     ~/.config/labwc/environment: XCURSOR_THEME=... XCURSOR_SIZE=...
```

## Coverage

Each theme has one real file per Windows role plus symlinks for the aliases (~190 names):

* Wayland `cursor-shape-v1` / CSS: `default pointer text wait progress help cell crosshair
  not-allowed no-drop copy alias move grab grabbing all-scroll *-resize zoom-in zoom-out
  dnd-ask all-resize ...`
* all 77 X11 core cursors (`left_ptr xterm watch fleur sb_h_double_arrow ...`), so legacy
  apps never fall back to the X font cursor
* GTK / Qt / KDE / Chromium / Firefox names (`size_ver openhand pointing_hand left_ptr_watch
  dnd-copy blank ...`) and the 32-hex legacy names used by GTK2, Firefox, Chromium and Wine

Mapping highlights: `link.cur` is `pointer`/`hand2`/`grab`, `move.cur` also serves
`grabbing`, `precision.cur` is `crosshair`, the alternative precision cursor is `cell`/`plus`,
`handwriting.cur` is `pencil`/`draft`, `alternate.cur` is `up-arrow`. Not in the pack and
therefore **generated** in the pack's style: `copy`, `alias`/`dnd-link`, `zoom-in`,
`zoom-out`, `blank`, plus mirrored `right_ptr` and rotated `vertical-text`.
`person` and `pin` are Windows-only and are installed under their own names.

## How it works

```
assets/<mode>/<scale>/{base,alternatives,<variant>}   original .cur/.ani
        |  w11cursors/wincur.py     parse CUR (32bpp DIB/PNG/legacy mask) and ANI (rate, seq)
        |  w11cursors/imaging.py    premultiplied Lanczos ladder 24..128, hotspot scaling
        |  w11cursors/synth.py      generated badges and lenses
        |  w11cursors/mapping.py    role -> names, variants
        |  w11cursors/xcursor.py    XCursor writer (premultiplied ARGB, ms delays)
        v
~/.local/share/icons/Win11Concept-*/{index.theme,CREDITS.txt,cursors/}
```

Native 32/48/64/96 px images are copied untouched; 24, 40, 56 and 128 px are resampled from the 96 px
artwork. Animations use the ANI frame timing (33 ms by default).

## Tests

```sh
python3 -m unittest discover -s tests     # parsers, mapping, build, verifier, apply, Xvfb end-to-end
```

The X11 test starts a private `Xvfb` (skipped when missing) and checks that libXcursor
resolves the theme, size and hotspots from `Xcursor.*` resources, and that the environment
takes precedence.

## Layout

```
assets/        dark/ and light/ trees of the upstream pack (Install.inf removed,
               "dark purple - pippouz request" renamed to dark-purple), Agreement.txt
w11cursors/    converter, verifier, apply, doctor (Python 3 + Pillow, one small C probe)
tests/         unittest suite
install.sh  uninstall.sh  w11cursor    entry points
```
