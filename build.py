#!/usr/bin/env python3
"""Generate colors/42vibes.vim from the vendored 42vibes palette.

The palette (vendor/palette.json) provides semantic colours, eight hue anchors
and the ANSI set. Each hue anchor is expanded into a nine-step HSL ramp, so
syntax colours share hue and saturation across the whole theme. The dark ramp
runs from light (100) to dark (900); the light ramp runs the other way.

Every GUI colour gets a 256-colour fallback: the nearest neighbour among the
xterm indices 16..255 (6x6x6 cube plus the 24 greys), measured in OKLab.
Indices 0..15 are intentionally skipped because terminals disagree about them.

Run:
    python3 build.py            # write colors/42vibes.vim
    python3 build.py --check    # exit 1 if the checked-in file is stale
    python3 build.py --report   # print the cterm mapping table
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parent
PALETTE_PATH = ROOT / "vendor" / "palette.json"
OUTPUT = ROOT / "colors" / "42vibes.vim"
README_EN = ROOT / "README.md"
README_DE = ROOT / "README.de.md"
READMES = {"en": README_EN, "de": README_DE}

SLOT_NAMES = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
BRIGHT_NAMES = [f"bright_{name}" for name in SLOT_NAMES]
ANSI_NAMES = SLOT_NAMES + BRIGHT_NAMES

SEMANTIC_ORDER = [
    "bg",
    "bg_deep",
    "surface",
    "surface_high",
    "surface_max",
    "text",
    "text_muted",
    "text_faint",
    "accent",
    "interactive",
    "warm",
    "border",
    "success",
    "warning",
    "error",
    "info",
]

README_START = "<!-- palette:start -->"
README_END = "<!-- palette:end -->"

PALETTE = json.loads(PALETTE_PATH.read_text(encoding="utf-8"))

STEPS = ["100", "200", "300", "400", "500", "600", "700", "800", "900"]
DARK_OFFSETS = dict(
    zip(STEPS, [0.28, 0.16, 0.09, 0.04, 0.00, -0.10, -0.20, -0.30, -0.38])
)
LIGHT_OFFSETS = dict(
    zip(STEPS, [-0.30, -0.20, -0.12, -0.05, 0.00, 0.08, 0.15, 0.22, 0.28])
)
SATURATION_SCALE = 0.55  # only the extreme steps 100 and 900


# --- colour math ---------------------------------------------------------


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def rgb_to_hsl(value: str) -> tuple[float, float, float]:
    r, g, b = (c / 255 for c in hex_to_rgb(value))
    high, low = max(r, g, b), min(r, g, b)
    light = (high + low) / 2
    if high == low:
        return 0.0, 0.0, light
    delta = high - low
    saturation = delta / (1 - abs(2 * light - 1))
    if high == r:
        hue = ((g - b) / delta) % 6
    elif high == g:
        hue = (b - r) / delta + 2
    else:
        hue = (r - g) / delta + 4
    return hue * 60, saturation, light


def hsl_to_hex(hue: float, saturation: float, light: float) -> str:
    light = max(0.0, min(1.0, light))
    saturation = max(0.0, min(1.0, saturation))
    chroma = (1 - abs(2 * light - 1)) * saturation
    x = chroma * (1 - abs((hue / 60) % 2 - 1))
    m = light - chroma / 2
    if hue < 60:
        r, g, b = chroma, x, 0.0
    elif hue < 120:
        r, g, b = x, chroma, 0.0
    elif hue < 180:
        r, g, b = 0.0, chroma, x
    elif hue < 240:
        r, g, b = 0.0, x, chroma
    elif hue < 300:
        r, g, b = x, 0.0, chroma
    else:
        r, g, b = chroma, 0.0, x
    return rgb_to_hex(((r + m) * 255, (g + m) * 255, (b + m) * 255))


def ramp(anchor: str, offsets: dict[str, float]) -> dict[str, str]:
    """Nine steps that keep hue and saturation and only move lightness."""
    hue, saturation, light = rgb_to_hsl(anchor)
    return {
        step: hsl_to_hex(
            hue,
            saturation * (SATURATION_SCALE if step in ("100", "900") else 1.0),
            light + offset,
        )
        for step, offset in offsets.items()
    }


# --- xterm 256 fallback --------------------------------------------------

XTERM_LEVELS = [0, 95, 135, 175, 215, 255]


def xterm_rgb(index: int) -> tuple[int, int, int]:
    """RGB value of an xterm palette index; only 16..255 are ever used."""
    if index < 232:
        n = index - 16
        return (
            XTERM_LEVELS[n // 36],
            XTERM_LEVELS[(n % 36) // 6],
            XTERM_LEVELS[n % 6],
        )
    grey = 8 + 10 * (index - 232)
    return (grey, grey, grey)


def _linear(channel: int) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def oklab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (_linear(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (x ** (1 / 3) for x in (l, m, s))
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


XTERM_LAB = [(index, oklab(xterm_rgb(index))) for index in range(16, 256)]


def nearest_cterm(value: str) -> tuple[int, float]:
    """Nearest xterm index in OKLab, plus its distance."""
    target = oklab(hex_to_rgb(value))
    return min(
        ((index, math.dist(target, lab)) for index, lab in XTERM_LAB),
        key=lambda item: (item[1], item[0]),
    )


# Fixed fallbacks. The nearest neighbour is correct everywhere except for the
# cases listed here; every deviation is caused by a collision or a cterm pair
# that would be too low-contrast. The README documents the same table.
CTERM_OVERRIDES: dict[tuple[str, str], int] = {
    # DiffAdd: xterm 233 is also Normal's background, so the diff background
    # would vanish. 22 (#005f5f) keeps a dark petrol wash (4.1:1 with the text).
    ("dark", "hue.green.900"): 22,
    # DiffAdd on light: nearest is 73 (#5fafaf) which leaves only 2.9:1 for
    # the green text; 79 (#5fd7af) reaches 4.2:1.
    ("light", "hue.green.900"): 79,
    # DiffChange on light: 109 (#87afaf) is 2.9:1 with the blue text; 110
    # (#87afd7) keeps the blue hue and reaches 3.1:1.
    ("light", "hue.blue.900"): 110,
    # DiffDelete on light: 181 (#d7afaf) is 2.3:1 with the red text; the paler
    # 224 (#ffd7d7) reaches 3.5:1.
    ("light", "hue.red.900"): 224,
    # VertSplit/PmenuThumb: light 250 (#bcbcbc) is only 1.9:1 on the
    # background; 109 (#87afaf) is a visible blue-grey border at 2.4:1.
    ("light", "semantic.border"): 109,
}

CTERM_OVERRIDE_REASONS = {
    ("dark", "hue.green.900"): "DiffAdd bg would equal Normal bg (233)",
    ("light", "hue.green.900"): "DiffAdd text would have only 2.9:1",
    ("light", "hue.blue.900"): "DiffChange text would have only 2.9:1",
    ("light", "hue.red.900"): "DiffDelete text would have only 2.3:1",
    ("light", "semantic.border"): "border would have only 1.9:1",
}


def cterm(mode: str, token: str, value: str) -> int:
    override = CTERM_OVERRIDES.get((mode, token))
    if override is not None:
        return override
    return nearest_cterm(value)[0]


# --- tokens --------------------------------------------------------------

MODES = ("dark", "light")


def build_tokens(mode: str) -> dict[str, str]:
    offsets = DARK_OFFSETS if mode == "dark" else LIGHT_OFFSETS
    tokens = {f"semantic.{key}": value for key, value in PALETTE[mode]["semantic"].items()}
    for name, anchor in PALETTE[mode]["hues"].items():
        for step, value in ramp(anchor, offsets).items():
            tokens[f"hue.{name}.{step}"] = value
    return tokens


TOKENS = {mode: build_tokens(mode) for mode in MODES}


# --- palette preview -----------------------------------------------------


def _svg_text(
    x: int | float,
    y: int | float,
    content: str,
    fill: str,
    size: int = 11,
    weight: str = "normal",
) -> str:
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}">{xml_escape(content)}</text>'
    )


def palette_svg(mode: str) -> str:
    """Pure SVG swatch sheet with semantic tokens and ANSI slots 0..15."""
    sem = PALETTE[mode]["semantic"]
    ansi = PALETTE[mode]["ansi"]
    width, height = 820, 660
    margin = 24
    content_width = width - 2 * margin

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" '
            f'font-family="ui-monospace, monospace" role="img" '
            f'aria-labelledby="palette-title">'
        ),
        f'<title id="palette-title">42vibes palette preview ({mode})</title>',
        f'<rect width="{width}" height="{height}" fill="{sem["bg"]}"/>',
        _svg_text(margin, 38, f"42vibes — {mode} palette", sem["text"], 18, "bold"),
        _svg_text(
            margin,
            60,
            "Generated by build.py from vendor/palette.json. Not a screenshot.",
            sem["text_muted"],
            11,
        ),
        _svg_text(margin, 90, "Semantic tokens", sem["text"], 12, "bold"),
    ]

    columns = 4
    gap = 12
    card_width = (content_width - gap * (columns - 1)) // columns
    card_height = 46
    row_pitch = 84
    start_y = 104
    for index, token in enumerate(SEMANTIC_ORDER):
        row, column = divmod(index, columns)
        x = margin + column * (card_width + gap)
        top = start_y + row * row_pitch
        value = sem[token]
        lines.append(
            f'<rect x="{x}" y="{top}" width="{card_width}" height="{card_height}" '
            f'rx="4" fill="{value}" stroke="{sem["border"]}" stroke-width="1"/>'
        )
        lines.append(_svg_text(x, top + 62, token, sem["text"], 11, "bold"))
        lines.append(_svg_text(x, top + 76, value, sem["text_muted"], 10))

    ansi_y = start_y + 4 * row_pitch + 40
    lines.append(_svg_text(margin, ansi_y - 14, "ANSI slots 0–15", sem["text"], 12, "bold"))

    columns = 8
    slot_width = (content_width - gap * (columns - 1)) // columns
    slot_height = 40
    slot_pitch = 78
    for index, name in enumerate(ANSI_NAMES):
        row, column = divmod(index, columns)
        x = margin + column * (slot_width + gap)
        top = ansi_y + row * slot_pitch
        value = ansi[name]
        lines.append(
            f'<rect x="{x}" y="{top}" width="{slot_width}" height="{slot_height}" '
            f'rx="4" fill="{value}" stroke="{sem["border"]}" stroke-width="1"/>'
        )
        lines.append(_svg_text(x, top + 56, f"{index} {name}", sem["text"], 10))
        lines.append(_svg_text(x, top + 70, value, sem["text_muted"], 9))

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def palette_block(lang: str) -> str:
    dark = PALETTE["dark"]["semantic"]
    light = PALETTE["light"]["semantic"]
    if lang == "de":
        heading = "### Palettenvorschau"
        intro = [
            "Die folgenden Grafiken sind **generierte Vorschauen** aus",
            "`vendor/palette.json` und keine Screenshots. `build.py` erzeugt sie als",
            "reines SVG nach `preview/`.",
        ]
        semantic_caption = "Semantische Tokens (Dark/Light):"
        ansi_caption = "ANSI 0–15 (Dark/Light):"
    else:
        heading = "### Palette preview"
        intro = [
            "The following graphics are **generated previews** from",
            "`vendor/palette.json`, not screenshots. `build.py` writes them as pure",
            "SVG to `preview/`.",
        ]
        semantic_caption = "Semantic tokens (Dark/Light):"
        ansi_caption = "ANSI 0–15 (Dark/Light):"
    lines = [
        README_START,
        "",
        heading,
        "",
        *intro,
        "",
        "![Palette Dark](preview/palette-dark.svg)",
        "",
        "![Palette Light](preview/palette-light.svg)",
        "",
        semantic_caption,
        "",
        "| Token | Dark | Light |",
        "| --- | --- | --- |",
    ]
    for token in SEMANTIC_ORDER:
        lines.append(f"| `{token}` | `{dark[token]}` | `{light[token]}` |")
    lines += [
        "",
        ansi_caption,
        "",
        "| Slot | Name | Dark | Light |",
        "| ---: | --- | --- | --- |",
    ]
    for index, name in enumerate(ANSI_NAMES):
        lines.append(
            f"| {index} | {name} | "
            f"`{PALETTE['dark']['ansi'][name]}` | "
            f"`{PALETTE['light']['ansi'][name]}` |"
        )
    lines.append("")
    lines.append(README_END)
    return "\n".join(lines)


def render_readme(path: Path, lang: str) -> str:
    text = path.read_text(encoding="utf-8")
    name = path.name
    if README_START not in text or README_END not in text:
        raise SystemExit(f"{name}: palette:start/palette:end markers missing")
    before, _, rest = text.partition(README_START)
    _, _, after = rest.partition(README_END)
    return before + palette_block(lang) + after


def outputs() -> dict[Path, str]:
    result = {OUTPUT: render()}
    for mode in MODES:
        result[ROOT / f"preview/palette-{mode}.svg"] = palette_svg(mode)
    for lang, path in READMES.items():
        result[path] = render_readme(path, lang)
    return result


# Named roles keep the group table readable and mode differences in one place.
ROLES = {
    "text": "semantic.text",
    "text_muted": "semantic.text_muted",
    "text_faint": "semantic.text_faint",
    "bg": "semantic.bg",
    "bg_deep": "semantic.bg_deep",
    "surface": "semantic.surface",
    "surface_high": "semantic.surface_high",
    "surface_max": "semantic.surface_max",
    "border": "semantic.border",
    "accent": "semantic.accent",
    "interactive": "semantic.interactive",
    "warm": "semantic.warm",
    "success": "semantic.success",
    "warning": "semantic.warning",
    "error": "semantic.error",
    "info": "semantic.info",
    "string": "hue.green.400",
    "number": "hue.orange.400",
    "keyword": "hue.purple.400",
    "function": "hue.blue.400",
    "preproc": "hue.red.400",
    "special": "hue.yellow.400",
    "punctuation": "hue.gray.400",
    "diff_add_bg": "hue.green.900",
    "diff_change_bg": "hue.blue.900",
    "diff_delete_bg": "hue.red.900",
    "diff_text_bg": "hue.blue.800",
}

# Roles whose ramp step differs between the modes.
MODE_ROLES = {
    "dark": {
        "comment": "hue.gray.600",
        "linenr": "hue.gray.600",
        "ignore": "hue.gray.700",
        "nontext": "hue.gray.700",
        "type": "hue.cyan.400",
    },
    "light": {
        "comment": "hue.gray.500",
        "linenr": "hue.gray.500",
        "ignore": "hue.gray.600",
        "nontext": "hue.gray.600",
        # cyan.400 sits too close to green.400 in the 256-colour cube; the
        # 500 anchor stays a full step away and keeps 4.7:1 on the light bg.
        "type": "hue.cyan.500",
    },
}


def token_for(mode: str, role: str) -> str:
    if role in ROLES:
        return ROLES[role]
    return MODE_ROLES[mode][role]


def resolve(mode: str, role: str | None) -> tuple[str, str] | None:
    if role is None:
        return None
    token = token_for(mode, role)
    return token, TOKENS[mode][token]


# (group, foreground role, background role, attributes, underline colour role)
GROUPS: list[tuple[str, str | None, str | None, str, str | None]] = [
    # base UI
    ("Normal", "text", "bg", "", None),
    ("Comment", "comment", None, "italic", None),
    ("Constant", "string", None, "", None),
    ("String", "string", None, "", None),
    ("Character", "string", None, "", None),
    ("Number", "number", None, "", None),
    ("Boolean", "number", None, "", None),
    ("Float", "number", None, "", None),
    ("Identifier", "text", None, "", None),
    ("Function", "function", None, "", None),
    ("Statement", "keyword", None, "", None),
    ("Conditional", "keyword", None, "", None),
    ("Repeat", "keyword", None, "", None),
    ("Label", "keyword", None, "", None),
    ("Operator", "punctuation", None, "", None),
    ("Keyword", "keyword", None, "", None),
    ("Exception", "preproc", None, "", None),
    ("PreProc", "preproc", None, "", None),
    ("Include", "preproc", None, "", None),
    ("Define", "preproc", None, "", None),
    ("Macro", "preproc", None, "", None),
    ("PreCondit", "preproc", None, "", None),
    ("Type", "type", None, "", None),
    ("StorageClass", "type", None, "", None),
    ("Structure", "type", None, "", None),
    ("Typedef", "type", None, "", None),
    ("Special", "special", None, "", None),
    ("SpecialChar", "special", None, "", None),
    ("Tag", "special", None, "", None),
    ("Delimiter", "punctuation", None, "", None),
    ("SpecialComment", "comment", None, "italic", None),
    ("Debug", "special", None, "", None),
    ("Underlined", "interactive", None, "underline", None),
    ("Ignore", "ignore", None, "", None),
    ("Error", "error", "bg_deep", "", None),
    ("Todo", "warm", "bg", "bold", None),
    ("ErrorMsg", "error", "bg", "bold", None),
    ("WarningMsg", "warning", None, "bold", None),
    ("ModeMsg", "text", None, "", None),
    ("MoreMsg", "success", None, "", None),
    ("Question", "success", None, "", None),
    ("Title", "accent", None, "bold", None),
    ("Directory", "interactive", None, "", None),
    ("MatchParen", "text", "surface_high", "", None),
    ("Cursor", "bg", "text", "", None),
    ("CursorLine", None, "surface", "", None),
    ("CursorLineNr", "accent", None, "", None),
    ("LineNr", "linenr", None, "", None),
    ("SignColumn", "linenr", "bg", "", None),
    ("Visual", "text", "surface_max", "", None),
    ("Search", "bg", "warm", "", None),
    ("IncSearch", "bg_deep", "accent", "", None),
    ("StatusLine", "text", "surface_high", "bold", None),
    ("StatusLineNC", "text_muted", "surface", "", None),
    ("VertSplit", "border", "bg", "", None),
    ("Pmenu", "text", "surface", "", None),
    ("PmenuSel", "bg_deep", "accent", "", None),
    ("PmenuSbar", None, "surface_high", "", None),
    ("PmenuThumb", None, "border", "", None),
    ("TabLine", "text_muted", "surface", "", None),
    ("TabLineSel", "text", "surface_high", "", None),
    ("TabLineFill", "text_muted", "bg_deep", "", None),
    ("DiffAdd", "string", "diff_add_bg", "", None),
    ("DiffChange", "function", "diff_change_bg", "", None),
    ("DiffDelete", "error", "diff_delete_bg", "", None),
    ("DiffText", "text", "diff_text_bg", "", None),
    ("Folded", "text_muted", "surface", "", None),
    ("NonText", "nontext", None, "", None),
    ("EndOfBuffer", "bg", None, "", None),
    ("SpellBad", "error", "bg", "undercurl", "error"),
    ("SpellCap", "warning", "bg", "undercurl", "warning"),
    ("SpellRare", "info", "bg", "undercurl", "info"),
    ("SpellLocal", "accent", "bg", "undercurl", "accent"),
    ("QuickFixLine", "text", "surface_high", "", None),
    ("ColorColumn", None, "surface", "", None),
    ("WildMenu", "bg_deep", "accent", "", None),
    # markdown
    ("markdownH1", "string", None, "bold", None),
    ("markdownH2", "function", None, "bold", None),
    ("markdownH3", "type", None, "bold", None),
    ("markdownBold", "text", None, "bold", None),
    ("markdownItalic", "text", None, "italic", None),
    ("markdownCode", "string", None, "", None),
    ("markdownLinkText", "interactive", None, "underline", None),
]

# Neovim only: treesitter captures and diagnostics.
NVIM_GROUPS: list[tuple[str, str | None, str | None, str, str | None]] = [
    ("@comment", "comment", None, "italic", None),
    ("@keyword", "keyword", None, "", None),
    ("@function", "function", None, "", None),
    ("@variable", "text", None, "", None),
    ("@string", "string", None, "", None),
    ("@number", "number", None, "", None),
    ("@type", "type", None, "", None),
    ("@operator", "punctuation", None, "", None),
    ("@punctuation.delimiter", "punctuation", None, "", None),
    ("@markup.heading.1", "string", None, "bold", None),
    ("@markup.heading.2", "function", None, "bold", None),
    ("@markup.heading.3", "type", None, "bold", None),
    ("@markup.strong", "text", None, "", None),
    ("DiagnosticError", "error", None, "", None),
    ("DiagnosticWarn", "warning", None, "", None),
    ("DiagnosticInfo", "info", None, "", None),
    ("DiagnosticHint", "text_muted", None, "", None),
    ("DiagnosticOk", "success", None, "", None),
]

CTERM_ATTRS = {"undercurl": "underline"}
TERM_ATTRS = {"undercurl": "underline"}


def highlight_line(
    mode: str,
    group: str,
    fg_role: str | None,
    bg_role: str | None,
    attrs: str,
    sp_role: str | None,
) -> str:
    parts = [f"hi {group:<22}"]

    def add(key: str, cterm_key: str, role: str) -> None:
        token, value = resolve(mode, role)  # type: ignore[misc]
        parts.append(f"{key}={value}")
        parts.append(f"{cterm_key}={cterm(mode, token, value)}")

    if fg_role is not None:
        add("guifg", "ctermfg", fg_role)
    if bg_role is not None:
        add("guibg", "ctermbg", bg_role)
    if sp_role is not None:
        token, value = resolve(mode, sp_role)  # type: ignore[misc]
        parts.append(f"guisp={value}")
    # Always write all three attribute slots. Without an explicit gui=NONE /
    # cterm=NONE Vim keeps the attributes that `hi clear` + `syntax reset`
    # installed, so e.g. ModeMsg would stay bold and IncSearch reversed.
    parts.append(f"term={TERM_ATTRS.get(attrs, attrs) or 'NONE'}")
    parts.append(f"gui={attrs or 'NONE'}")
    parts.append(f"cterm={CTERM_ATTRS.get(attrs, attrs) or 'NONE'}")
    return " ".join(parts)


def render_mode(mode: str, indent: str = "  ") -> list[str]:
    lines = [indent + highlight_line(mode, *group) for group in GROUPS]
    lines += [
        indent + "if has('nvim')",
        indent + '  " treesitter captures and diagnostics',
    ]
    lines += [
        indent + "  " + highlight_line(mode, *group) for group in NVIM_GROUPS
    ]
    lines += [indent + "endif"]
    return lines


def render() -> str:
    lines = [
        '" Vim color scheme: 42vibes',
        '"',
        '" Generated by build.py from vendor/palette.json -- do not edit by hand.',
        f'" Palette version: {PALETTE.get("version", 0)}',
        '"',
        '" Dark and light are selected automatically from \'background\'.',
        '" True color: guifg/guibg. 256-color terminals: ctermfg/ctermbg use the',
        '" nearest xterm color in OKLab (indices 16..255; 0..15 are ignored).',
        "",
        "hi clear",
        "if exists('syntax_on')",
        "  syntax reset",
        "endif",
        "",
        "let g:colors_name = '42vibes'",
        "",
        "if &background ==# 'light'",
        '  " --- light -------------------------------------------------------',
    ]
    lines += render_mode("light")
    lines += [
        "else",
        '  " --- dark --------------------------------------------------------',
    ]
    lines += render_mode("dark")
    lines += [
        "endif",
        "",
    ]
    return "\n".join(lines)


# --- reporting -----------------------------------------------------------

KEY_COLORS = [
    ("dark", "hue.green.500", "#2fb59d", 36, "Petrol / accent"),
    ("dark", "hue.blue.500", "#55a7c8", 74, "Blau / interactive"),
]


def report() -> None:
    print("cterm fallback: nearest xterm index in OKLab (16..255)")
    for mode, token, expected_hex, expected_index, label in KEY_COLORS:
        value = TOKENS[mode][token]
        index, distance = nearest_cterm(value)
        assert value == expected_hex, (token, value)
        print(
            f"  {mode:5} {label:22} {value} -> {index:3} "
            f"(expected ~{expected_index}, dE={distance:.4f})"
        )
    for mode in MODES:
        print(f"\n{mode}:")
        for group, fg_role, bg_role, _, _ in GROUPS + NVIM_GROUPS:
            if fg_role is None:
                continue
            token, value = resolve(mode, fg_role)  # type: ignore[misc]
            index = cterm(mode, token, value)
            mark = " *" if (mode, token) in CTERM_OVERRIDES else ""
            print(f"  {value} -> {index:3}{mark}  {group}")
    print("\nfixed cterm overrides (nearest -> override):")
    for (mode, token), index in sorted(CTERM_OVERRIDES.items()):
        value = TOKENS[mode][token]
        native = nearest_cterm(value)[0]
        reason = CTERM_OVERRIDE_REASONS[(mode, token)]
        print(f"  {mode:5} {token:22} {value} {native:3} -> {index:3}  {reason}")


def main(argv: list[str]) -> int:
    if "--report" in argv:
        report()
        return 0

    generated = outputs()
    if "--check" in argv:
        stale = [
            path.relative_to(ROOT)
            for path, content in generated.items()
            if (path.read_text(encoding="utf-8") if path.exists() else "") != content
        ]
        if stale:
            print(
                "veraltet: "
                + ", ".join(str(path) for path in stale)
                + "; bitte 'make build' ausführen."
            )
            return 1
        print("generierte Dateien: aktuell")
        return 0

    for path, content in generated.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"geschrieben: {path.relative_to(ROOT)}")
    print(f"({len(GROUPS)} + {len(NVIM_GROUPS)} Gruppen)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
