#!/usr/bin/env python3
"""Validate colors/42vibes.vim against the vendored palette and the spec.

The checks are intentionally independent from build.py: ramps, OKLab
neighbours and contrast are recomputed here. Structural checks parse the
generated Vimscript, so a hand edit or a broken generator is caught.

Run: python3 validate.py
"""

from __future__ import annotations

import json
import hashlib
import math
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PALETTE = json.loads((ROOT / "vendor" / "palette.json").read_text(encoding="utf-8"))
THEME = ROOT / "colors" / "42vibes.vim"
README_FILES = {"en": "README.md", "de": "README.de.md"}
README_SWITCHES = {
    "en": "**English** · [Deutsch](README.de.md)",
    "de": "[English](README.md) · **Deutsch**",
}

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

STEPS = ["100", "200", "300", "400", "500", "600", "700", "800", "900"]
OFFSETS = {
    "dark": [0.28, 0.16, 0.09, 0.04, 0.00, -0.10, -0.20, -0.30, -0.38],
    "light": [-0.30, -0.20, -0.12, -0.05, 0.00, 0.08, 0.15, 0.22, 0.28],
}

REQUIRED_GROUPS = [
    "Normal", "Comment", "Constant", "String", "Character", "Number", "Boolean",
    "Float", "Identifier", "Function", "Statement", "Conditional", "Repeat",
    "Label", "Operator", "Keyword", "Exception", "PreProc", "Include", "Define",
    "Macro", "PreCondit", "Type", "StorageClass", "Structure", "Typedef",
    "Special", "SpecialChar", "Tag", "Delimiter", "SpecialComment", "Debug",
    "Underlined", "Ignore", "Error", "Todo", "ErrorMsg", "WarningMsg",
    "ModeMsg", "MoreMsg", "Question", "Title", "Directory", "MatchParen",
    "Cursor", "CursorLine", "CursorLineNr", "LineNr", "SignColumn", "Visual",
    "Search", "IncSearch", "StatusLine", "StatusLineNC", "VertSplit", "Pmenu",
    "PmenuSel", "PmenuSbar", "PmenuThumb", "TabLine", "TabLineSel",
    "TabLineFill", "DiffAdd", "DiffChange", "DiffDelete", "DiffText", "Folded",
    "NonText", "EndOfBuffer", "SpellBad", "SpellCap", "SpellRare", "SpellLocal",
    "QuickFixLine", "ColorColumn", "WildMenu",
    "markdownH1", "markdownH2", "markdownH3", "markdownBold", "markdownItalic",
    "markdownCode", "markdownLinkText",
]

REQUIRED_NVIM_GROUPS = [
    "@comment", "@keyword", "@function", "@variable", "@string", "@number",
    "@type", "@operator", "@punctuation.delimiter",
    "@markup.heading.1", "@markup.heading.2", "@markup.heading.3",
    "@markup.strong",
    "DiagnosticError", "DiagnosticWarn", "DiagnosticInfo", "DiagnosticHint",
    "DiagnosticOk",
]

BOLD_GROUPS = {
    "Title", "ErrorMsg", "WarningMsg", "Todo", "StatusLine",
    "markdownH1", "markdownH2", "markdownH3", "markdownBold",
    "@markup.heading.1", "@markup.heading.2", "@markup.heading.3",
}

# Fixed cterm fallbacks; each one has to be justified in the README.
EXPECTED_OVERRIDES = {
    ("dark", "#0c1715"): 22,
    ("light", "#66baab"): 79,
    ("light", "#8fb0c0"): 110,
    ("light", "#d2b7bb"): 224,
    ("light", "#a8bfd1"): 109,
}

STRUCTURAL = {"VertSplit"}
DIFF_GROUPS = {"DiffAdd", "DiffChange", "DiffDelete"}
TEXT_CONTRAST_MIN = 3.0
STRUCTURAL_CONTRAST_MIN = 1.8  # palette border is intentionally subtle
DIFF_CONTRAST_MIN = 2.8  # diff lines are tinted backgrounds, not body text

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


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


def ramps(mode: str) -> dict[str, dict[str, str]]:
    result = {}
    for name, anchor in PALETTE[mode]["hues"].items():
        hue, saturation, light = rgb_to_hsl(anchor)
        result[name] = {
            step: hsl_to_hex(
                hue,
                saturation * (0.55 if step in ("100", "900") else 1.0),
                light + offset,
            )
            for step, offset in zip(STEPS, OFFSETS[mode])
        }
    return result


XTERM_LEVELS = [0, 95, 135, 175, 215, 255]


def xterm_rgb(index: int) -> tuple[int, int, int]:
    if index < 232:
        n = index - 16
        return (XTERM_LEVELS[n // 36], XTERM_LEVELS[(n % 36) // 6], XTERM_LEVELS[n % 6])
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


def nearest_cterm(value: str) -> int:
    target = oklab(hex_to_rgb(value))
    return min(
        ((index, math.dist(target, lab)) for index, lab in XTERM_LAB),
        key=lambda item: (item[1], item[0]),
    )[0]


def luminance(value: str) -> float:
    r, g, b = (_linear(c) for c in hex_to_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def gui_contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def cterm_contrast(a: int, b: int) -> float:
    return gui_contrast(
        "#%02x%02x%02x" % xterm_rgb(a), "#%02x%02x%02x" % xterm_rgb(b)
    )


HI_RE = re.compile(r"^\s*hi\s+(\S+)\s+(.+)$")
ARG_RE = re.compile(r"(\w+)=([^\s]+)")


def parse_theme() -> dict[str, dict[str, dict[str, str]]]:
    """Return {mode: {group: {arg: value}}} plus structural checks."""
    text = THEME.read_text(encoding="utf-8")
    lines = text.splitlines()

    def index_of(pattern: str, start: int = 0) -> int:
        for i in range(start, len(lines)):
            if lines[i] == pattern:
                return i
        return -1

    light_if = index_of("if &background ==# 'light'")
    top_else = index_of("else", light_if + 1)
    top_endif = index_of("endif", top_else + 1)
    if min(light_if, top_else, top_endif) < 0 or not (light_if < top_else < top_endif):
        raise SystemExit("Struktur: if/else/endif für background nicht gefunden")

    blocks = {
        "light": lines[light_if + 1 : top_else],
        "dark": lines[top_else + 1 : top_endif],
    }

    parsed: dict[str, dict[str, dict[str, str]]] = {}
    for mode, block in blocks.items():
        groups: dict[str, dict[str, str]] = {}
        in_nvim = False
        for line in block:
            stripped = line.strip()
            if stripped.startswith("if has('nvim')"):
                in_nvim = True
                continue
            if stripped == "endif":
                in_nvim = False
                continue
            match = HI_RE.match(line)
            if not match:
                continue
            group, rest = match.groups()
            if group.startswith("@") and not in_nvim:
                fail(f"{mode}: {group} steht außerhalb des has('nvim')-Blocks")
            if group in groups:
                fail(f"{mode}: Gruppe {group} ist doppelt definiert")
            groups[group] = dict(ARG_RE.findall(rest))
        if not any("if has('nvim')" in line for line in block):
            fail(f"{mode}: kein has('nvim')-Block")
        parsed[mode] = groups

    # file-level requirements
    clear_at = text.find("\nhi clear\n")
    first_hi = next(
        (
            sum(len(line) + 1 for line in lines[:i])
            for i, line in enumerate(lines)
            if re.match(r"^\s+hi\s+\S+", line)
        ),
        -1,
    )
    if clear_at < 0 or first_hi < 0 or clear_at > first_hi:
        fail("hi clear muss vor der ersten Gruppen-Definition stehen")
    if "if exists('syntax_on')\n  syntax reset\nendif" not in text:
        fail("syntax reset fehlt oder ist nicht durch exists('syntax_on') geschützt")
    if "let g:colors_name = '42vibes'" not in text:
        fail("g:colors_name ist nicht auf '42vibes' gesetzt")
    for forbidden in ("set background", "set termguicolors", "set t_Co"):
        if forbidden in text:
            fail(f"colorscheme darf '{forbidden}' nicht setzen")
    if "hi link" in text:
        fail("hi link ist unerwartet; alle Gruppen sollen explizit sein")

    return parsed


def check_mode(mode: str, groups: dict[str, dict[str, str]]) -> None:
    expected = set(REQUIRED_GROUPS) | set(REQUIRED_NVIM_GROUPS)
    missing = expected - set(groups)
    extra = set(groups) - expected
    if missing:
        fail(f"{mode}: fehlende Gruppen {sorted(missing)}")
    if extra:
        fail(f"{mode}: unbekannte Gruppen {sorted(extra)}")

    ramp = ramps(mode)
    allowed = set(PALETTE[mode]["semantic"].values())
    for hue in ramp.values():
        allowed.update(hue.values())

    normal = groups.get("Normal", {})
    normal_bg_gui = normal.get("guibg")
    normal_bg_cterm = int(normal.get("ctermbg", "-1"))

    for group, args in groups.items():
        for key in ("guifg", "guibg", "guisp"):
            if key in args and args[key] not in allowed:
                fail(f"{mode}: {group}.{key}={args[key]} ist keine Paletten-/Rampenfarbe")
        for key in ("ctermfg", "ctermbg"):
            if key in args:
                index = int(args[key])
                if not 16 <= index <= 255:
                    fail(f"{mode}: {group}.{key}={index} liegt außerhalb 16..255")
        # every GUI colour needs a cterm fallback and vice versa
        if ("guifg" in args) != ("ctermfg" in args):
            fail(f"{mode}: {group} hat guifg/ctermfg nicht paarweise")
        if ("guibg" in args) != ("ctermbg" in args):
            fail(f"{mode}: {group} hat guibg/ctermbg nicht paarweise")

        # Every definition must be complete: an omitted attribute slot would
        # silently inherit the default set by `hi clear`/`syntax reset`.
        for key in ("term", "gui", "cterm"):
            if key not in args:
                fail(f"{mode}: {group} definiert {key} nicht explizit")

        attrs = args.get("gui", "")
        cterm_attrs = args.get("cterm", "")
        # The generator writes NONE explicitly so Vim does not inherit the
        # attributes installed by `hi clear` + `syntax reset`.
        if attrs == "NONE":
            attrs = ""
        if cterm_attrs == "NONE":
            cterm_attrs = ""
        if attrs not in ("", "bold", "italic", "underline", "undercurl"):
            fail(f"{mode}: {group} nutzt unerwartete gui-Attribute '{attrs}'")
        expected_cterm = "underline" if attrs == "undercurl" else attrs
        if attrs and cterm_attrs != expected_cterm:
            fail(f"{mode}: {group} cterm='{cterm_attrs}' passt nicht zu gui='{attrs}'")
        if not attrs and cterm_attrs:
            fail(f"{mode}: {group} hat cterm-Attribute ohne gui-Gegenstueck")
        if "bold" in attrs and group not in BOLD_GROUPS:
            fail(f"{mode}: {group} ist fett, gehört aber nicht zur Bold-Liste")
        if group in BOLD_GROUPS:
            if "bold" not in attrs or "bold" not in cterm_attrs:
                fail(f"{mode}: {group} muss gui=bold UND cterm=bold sein")

        # cterm mapping: nearest neighbour unless a documented override exists
        for gui_key, cterm_key in (("guifg", "ctermfg"), ("guibg", "ctermbg")):
            if gui_key not in args:
                continue
            value = args[gui_key]
            index = int(args[cterm_key])
            wanted = EXPECTED_OVERRIDES.get((mode, value), nearest_cterm(value))
            if index != wanted:
                fail(
                    f"{mode}: {group}.{cterm_key}={index}, erwartet {wanted} "
                    f"für {value}"
                )

        # contrast
        if "guifg" in args and group != "EndOfBuffer":
            if "guibg" in args:
                ratio = gui_contrast(args["guifg"], args["guibg"])
                c_ratio = cterm_contrast(int(args["ctermfg"]), int(args["ctermbg"]))
                if group in STRUCTURAL:
                    threshold = STRUCTURAL_CONTRAST_MIN
                elif group in DIFF_GROUPS:
                    threshold = DIFF_CONTRAST_MIN
                else:
                    threshold = TEXT_CONTRAST_MIN
                if ratio < threshold or c_ratio < threshold:
                    fail(
                        f"{mode}: {group} Kontrast gui={ratio:.2f} cterm={c_ratio:.2f} "
                        f"< {threshold}"
                    )
            elif normal_bg_gui:
                ratio = gui_contrast(args["guifg"], normal_bg_gui)
                c_ratio = cterm_contrast(int(args["ctermfg"]), normal_bg_cterm)
                if ratio < TEXT_CONTRAST_MIN or c_ratio < TEXT_CONTRAST_MIN:
                    fail(
                        f"{mode}: {group} Kontrast auf Normal gui={ratio:.2f} "
                        f"cterm={c_ratio:.2f} < {TEXT_CONTRAST_MIN}"
                    )

    # the two documented key mappings
    key_checks = {"Title": "#2fb59d", "Directory": "#55a7c8"} if mode == "dark" else {}
    for group, value in key_checks.items():
        wanted = nearest_cterm(value)
        got = groups[group].get("ctermfg")
        if str(wanted) != got:
            fail(f"{mode}: {group}.ctermfg={got} für {value}, erwartet {wanted}")

    # diff backgrounds must stay distinguishable from Normal and each other
    diff_bgs = [
        groups[g]["ctermbg"] for g in ("DiffAdd", "DiffChange", "DiffDelete")
        if "ctermbg" in groups.get(g, {})
    ]
    if len(set(diff_bgs)) != 3:
        fail(f"{mode}: Diff-Hintergründe sind nicht unterscheidbar: {diff_bgs}")
    if str(normal_bg_cterm) in diff_bgs:
        fail(f"{mode}: ein Diff-Hintergrund entspricht Normal")


def svg_hex_values(path: Path) -> set[str]:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    values: set[str] = set()
    for element in root.iter():
        for attribute in element.attrib.values():
            values.update(
                match.lower() for match in re.findall(r"#[0-9a-fA-F]{6}", attribute)
            )
        for text in (element.text, element.tail):
            if text:
                values.update(
                    match.lower() for match in re.findall(r"#[0-9a-fA-F]{6}", text)
                )
    return values


def validate_readmes() -> None:
    for lang, name in README_FILES.items():
        path = ROOT / name
        if not path.is_file():
            fail(f"{name}: fehlt")
            continue
        text = path.read_text(encoding="utf-8")
        if README_START not in text or README_END not in text:
            fail(f"{name}: palette:start/palette:end Marker fehlen")
            continue
        if text.index(README_START) > text.index(README_END):
            fail(f"{name}: palette:end steht vor palette:start")
            continue
        block = text.split(README_START, 1)[1].split(README_END, 1)[0]
        for image in ("preview/palette-dark.svg", "preview/palette-light.svg"):
            if image not in block:
                fail(f"{name}: Palettenblock nennt {image} nicht")
        for image in (
            "![Palette Dark](preview/palette-dark.svg)",
            "![Palette Light](preview/palette-light.svg)",
        ):
            if image not in text:
                fail(f"{name}: erwartete Bildmarke fehlt: {image}")
        switch = README_SWITCHES[lang]
        if switch not in text:
            fail(f"{name}: Sprachumschalter fehlt oder ist falsch -> {switch!r}")
        elif switch not in text.splitlines()[:5]:
            fail(f"{name}: Sprachumschalter steht nicht oben")
        if "](LICENSE)" not in text:
            fail(f"{name}: verweist nicht auf LICENSE")
        for term in ("MIT", "2026 42vibes"):
            if term not in text:
                fail(f"{name}: Lizenzabschnitt enthält {term!r} nicht")
        if not any(line in text for line in ("## License", "## Lizenz")):
            fail(f"{name}: Lizenzüberschrift fehlt")
        print(f"{name}: Marker, Bildpfade, Sprachumschalter und Lizenz vorhanden")


def validate_previews() -> None:
    texts = {
        name: (ROOT / name).read_text(encoding="utf-8")
        if (ROOT / name).is_file()
        else ""
        for name in README_FILES.values()
    }
    for mode in ("dark", "light"):
        relative = f"preview/palette-{mode}.svg"
        path = ROOT / relative
        if not path.is_file():
            fail(f"{relative}: fehlt")
            continue
        try:
            values = svg_hex_values(path)
        except (OSError, ET.ParseError) as exc:
            fail(f"{relative}: ungültiges SVG/XML: {exc}")
            continue
        if 'font-family="ui-monospace, monospace"' not in path.read_text(
            encoding="utf-8"
        ):
            fail(f"{relative}: font-family ui-monospace fehlt")
        required = set(PALETTE[mode]["semantic"].values()) | {
            PALETTE[mode]["ansi"][name] for name in ANSI_NAMES
        }
        missing = sorted(required - values)
        if missing:
            fail(f"{relative}: fehlende Hex-Werte -> {', '.join(missing)}")
        else:
            print(
                f"{relative}: valides XML, 16/16 ANSI + "
                f"{len(SEMANTIC_ORDER)} semantische Hex-Werte"
            )
        for name, text in texts.items():
            if f"]({relative})" not in text:
                fail(f"{name}: verweist nicht auf {relative}")


def hash_tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def validate_deterministic() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix=".determinism-", dir=ROOT))
    try:
        work = temp_dir / "repo"
        work.mkdir()
        shutil.copy2(ROOT / "build.py", work / "build.py")
        for name in README_FILES.values():
            shutil.copy2(ROOT / name, work / name)
        shutil.copytree(ROOT / "vendor", work / "vendor")
        first: dict[str, str] | None = None
        for run in (1, 2):
            result = subprocess.run(
                [sys.executable, str(work / "build.py")],
                cwd=work,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                fail(
                    f"Build-Determinismus: Lauf {run} fehlgeschlagen "
                    f"(Exit {result.returncode}): {result.stderr.strip()}"
                )
                return
            hashes = hash_tree(work)
            if run == 1:
                first = hashes
                continue
            if hashes != first:
                changed = sorted(
                    name
                    for name in set(hashes) | set(first or {})
                    if hashes.get(name) != (first or {}).get(name)
                )
                fail(
                    "Build-Determinismus: zweiter Lauf weicht ab -> "
                    + ", ".join(changed)
                )
                return
        print(
            f"Build-Determinismus: zwei Läufe byte-identisch "
            f"({len(first or {})} Dateien)"
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> int:
    if not THEME.exists():
        print(f"fehlt: {THEME}")
        return 1
    parsed = parse_theme()
    for mode in ("dark", "light"):
        check_mode(mode, parsed[mode])

    validate_previews()
    validate_readmes()
    validate_deterministic()

    dark_title = parsed["dark"]["Title"]
    petrol = nearest_cterm("#2fb59d")
    blue = nearest_cterm("#55a7c8")
    print(
        f"Dark Petrol #2fb59d -> ctermfg={dark_title.get('ctermfg')} "
        f"(OKLab-Nachbar {petrol}, erwartet ~36)"
    )
    print(
        f"Dark Blau   #55a7c8 -> ctermfg={parsed['dark']['Directory'].get('ctermfg')} "
        f"(OKLab-Nachbar {blue}, erwartet ~74)"
    )

    if failures:
        print(f"\n{len(failures)} Fehler:")
        for message in failures:
            print(f"  - {message}")
        return 1
    print(f"\ncolors/42vibes.vim: ok ({len(REQUIRED_GROUPS)} + {len(REQUIRED_NVIM_GROUPS)} Gruppen, dark und light)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
