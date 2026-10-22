"""Windows cursor roles -> Linux cursor names.

Every theme gets one real file per ``Entry`` and a symlink for each alias.
Coverage matters more than elegance here: when a toolkit asks for a name the
theme lacks, libXcursor falls back to the ugly X11 core font cursor and
wlroots/Mutter/KWin show a default arrow (or nothing), so we list every name
used by the Wayland ``cursor-shape-v1`` protocol, CSS, GTK, Qt/KDE, the 77 X11
core cursors, and the legacy 32-hex-digit names Firefox/Chromium/GTK2/Wine use.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Entry:
    file: str                 # name of the real file inside cursors/
    kind: str                 # "cur" | "ani" | "alt" | "synth" | "mirror" | "rotate"
    source: str               # asset stem, or a synth recipe name
    aliases: tuple[str, ...] = field(default_factory=tuple)


ENTRIES: tuple[Entry, ...] = (
    Entry("default", "cur", "pointer", (
        "left_ptr", "arrow", "top_left_arrow", "X_cursor", "x-cursor", "wayland-cursor",
        "context-menu",
        # X11 core glyphs that have no sensible Windows counterpart
        "dot", "dotbox", "bogosity", "gumby", "draped_box", "heart", "icon", "iron_cross",
        "man", "mouse", "rtl_logo", "sailboat", "shuttle", "spider", "star", "trek",
        "umbrella", "boat", "coffee_mug", "gobbler", "leftbutton", "middlebutton",
        "rightbutton", "box_spiral", "top_tee", "bottom_tee", "left_tee", "right_tee",
        "sb_left_arrow", "sb_right_arrow", "sb_up_arrow", "sb_down_arrow",
    )),
    Entry("help", "cur", "help", (
        "question_arrow", "whats_this", "left_ptr_help", "dnd-ask",
        "5c6cd98b3f3ebcb1f9c7f1c204630408", "d9ce0ab605698f320427677b458ad60b",
    )),
    Entry("progress", "ani", "working", (
        "left_ptr_watch", "half-busy",
        "00000000000000020006000e7e9ffc3f", "08e8e1c95fe2fc01f976f1e063a24ccd",
        "3ecb610c1bf2410f44200f48c40d3599",
    )),
    Entry("wait", "ani", "busy", ("watch", "clock")),
    Entry("pointer", "cur", "link", (
        "hand", "hand1", "hand2", "pointing_hand", "grab", "openhand",
        "9d800788f1b08800ae810202380a0822", "e29285e634086352946a0e7090d73106",
    )),
    Entry("text", "cur", "beam", ("xterm", "ibeam")),
    Entry("vertical-text", "rotate", "beam"),
    Entry("crosshair", "cur", "precision", (
        "cross", "tcross", "cross_reverse", "diamond_cross", "target", "color-picker",
    )),
    Entry("cell", "alt", "precision", ("plus",)),
    Entry("pencil", "cur", "handwriting", ("draft", "draft_large", "draft_small", "spraycan")),
    Entry("not-allowed", "cur", "unavailable", (
        "no-drop", "dnd-no-drop", "forbidden", "crossed_circle", "circle", "pirate",
        "03b6e0fcb3499374a867c041f52298f0",
    )),
    Entry("ns-resize", "cur", "vert", (
        "n-resize", "s-resize", "row-resize", "size_ver", "size-ver", "v_double_arrow",
        "double_arrow", "sb_v_double_arrow", "top_side", "bottom_side", "split_v",
        "based_arrow_down", "down-arrow",
        "00008160000006810000408080010102", "2870a09082c103050810ffdffffe0204",
    )),
    Entry("ew-resize", "cur", "horz", (
        "e-resize", "w-resize", "col-resize", "size_hor", "size-hor", "h_double_arrow",
        "sb_h_double_arrow", "left_side", "right_side", "split_h", "left-arrow",
        "right-arrow",
        "028006030e0e7ebffc7f7070c0600140", "14fef782d02440884392942c11205230",
    )),
    # dgn1 is "\" (top-left <-> bottom-right), dgn2 is "/" (top-right <-> bottom-left).
    # bd_double_arrow is the backward diagonal "\"; fd_double_arrow the forward "/".
    Entry("nwse-resize", "cur", "dgn1", (
        "nw-resize", "se-resize", "size_fdiag", "size-fdiag", "bd_double_arrow",
        "top_left_corner", "bottom_right_corner", "ul_angle", "lr_angle",
        "c7088f0f3e6c8088236ef8e1e3e70000",
    )),
    Entry("nesw-resize", "cur", "dgn2", (
        "ne-resize", "sw-resize", "size_bdiag", "size-bdiag", "fd_double_arrow",
        "top_right_corner", "bottom_left_corner", "ur_angle", "ll_angle",
        "fcf1c3c7cd4491d801f1e1c78f100000",
    )),
    Entry("move", "cur", "move", (
        "all-scroll", "all-resize", "size_all", "size-all", "fleur", "sizing", "exchange",
        "grabbing", "closedhand", "dnd-move", "dnd-none",
        "4498f0e0c1937ffe01fd06f973665830", "9081237383d90e509aa00f00170e968f",
        "fcf21c00b30f7e3f83fe0dfd12e71cff",
    )),
    Entry("up-arrow", "cur", "alternate", ("up_arrow", "center_ptr", "based_arrow_up")),
    # Windows 10/11 specials: kept under their own names, nothing asks for them.
    Entry("person", "cur", "person"),
    Entry("pin", "cur", "pin"),
    # No upstream artwork exists for these: they are generated in the pack's style.
    Entry("copy", "synth", "copy", (
        "dnd-copy",
        "1081e37283d90000800003c07f3ef6bf", "6407b0e94181790501fd1e167b474872",
        "b66166c04f8c3109214a4fbd64a50fc8",
    )),
    Entry("alias", "synth", "alias", (
        "dnd-link", "link",
        "3085a0e285430894940527032f8b26df", "640fb0e74195791501fd1ed57b41487f",
        "a2a266d0498c3104214a47bd64ab0fc8",
    )),
    Entry("zoom-in", "synth", "zoom-in"),
    Entry("zoom-out", "synth", "zoom-out"),
    Entry("right_ptr", "mirror", "pointer"),
    Entry("blank", "synth", "blank"),  # Qt::BlankCursor
)

# cursor-shape-v1 (Wayland) as CSS names, including the v2 additions.
WAYLAND_SHAPES = (
    "default", "context-menu", "help", "pointer", "progress", "wait", "cell", "crosshair",
    "text", "vertical-text", "alias", "copy", "move", "no-drop", "not-allowed", "grab",
    "grabbing", "e-resize", "n-resize", "ne-resize", "nw-resize", "s-resize", "se-resize",
    "sw-resize", "w-resize", "ew-resize", "ns-resize", "nesw-resize", "nwse-resize",
    "col-resize", "row-resize", "all-scroll", "zoom-in", "zoom-out", "dnd-ask", "all-resize",
)

# cursorfont.h, i.e. everything libXcursor can map an XC_* glyph to.
X11_CORE = (
    "X_cursor", "arrow", "based_arrow_down", "based_arrow_up", "boat", "bogosity",
    "bottom_left_corner", "bottom_right_corner", "bottom_side", "bottom_tee", "box_spiral",
    "center_ptr", "circle", "clock", "coffee_mug", "cross", "cross_reverse", "crosshair",
    "diamond_cross", "dot", "dotbox", "double_arrow", "draft_large", "draft_small",
    "draped_box", "exchange", "fleur", "gobbler", "gumby", "hand1", "hand2", "heart", "icon",
    "iron_cross", "left_ptr", "left_side", "left_tee", "leftbutton", "ll_angle", "lr_angle",
    "man", "middlebutton", "mouse", "pencil", "pirate", "plus", "question_arrow", "right_ptr",
    "right_side", "right_tee", "rightbutton", "rtl_logo", "sailboat", "sb_down_arrow",
    "sb_h_double_arrow", "sb_left_arrow", "sb_right_arrow", "sb_up_arrow",
    "sb_v_double_arrow", "shuttle", "sizing", "spider", "spraycan", "star", "target", "tcross",
    "top_left_arrow", "top_left_corner", "top_right_corner", "top_side", "top_tee", "trek",
    "ul_angle", "umbrella", "ur_angle", "watch", "xterm",
)

# Names GTK, Qt/KDE and Chromium/Firefox request that are not in the lists above.
TOOLKIT_EXTRAS = (
    "left_ptr_watch", "left_ptr_help", "half-busy", "whats_this", "forbidden", "openhand",
    "closedhand", "pointing_hand", "up_arrow", "size_all", "size_hor", "size_ver",
    "size_bdiag", "size_fdiag", "split_h", "split_v", "dnd-copy", "dnd-move", "dnd-link",
    "dnd-none", "dnd-no-drop", "ibeam", "blank", "bd_double_arrow", "fd_double_arrow",
    "h_double_arrow", "v_double_arrow", "color-picker", "wayland-cursor",
)


def all_names() -> list[str]:
    names = []
    for e in ENTRIES:
        names.append(e.file)
        names.extend(e.aliases)
    return names


# ---------------------------------------------------------------------------
# Variants: the pack ships one pair of spinner animations per colour.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Variant:
    directory: str   # directory name under assets/<mode>/<size>/
    suffix: str      # appended to the theme name ("" = default)
    label: str       # human readable


VARIANTS: tuple[Variant, ...] = (
    Variant("01_default", "", "Default"),
    Variant("02_classic", "Classic", "Classic"),
    Variant("03_amber", "Amber", "Amber"),
    Variant("04_green", "Green", "Green"),
    Variant("05_indigo", "Indigo", "Indigo"),
    Variant("06_red", "Red", "Red"),
    Variant("07_squid", "Squid", "Squid"),
    Variant("08_purple", "Purple", "Purple"),
    Variant("09_candy", "Candy", "Candy"),
    Variant("10_sunset", "Sunset", "Sunset"),
    Variant("dark-purple", "DarkPurple", "Dark Purple"),
)

MODES = ("dark", "light")
SCALES = ("regular", "small")
THEME_PREFIX = "Win11Concept"


def theme_name(mode: str, scale: str, variant: Variant) -> str:
    parts = [THEME_PREFIX, mode.capitalize()]
    if variant.suffix:
        parts.append(variant.suffix)
    if scale == "small":
        parts.append("Small")
    return "-".join(parts)
