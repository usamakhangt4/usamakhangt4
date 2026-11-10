"""Build the dark and light profile cards.

The palette lives here. The link buttons and the Pac-Man board import it so
one colour change repaints every SVG.
"""

from __future__ import annotations

import colorsys
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART_DARK = ROOT / "assets" / "ascii-art.txt"
ART_LIGHT = ROOT / "assets" / "ascii-art-light.txt"
ART_COLOR = ROOT / "assets" / "ascii-color.json"
CACHE_STATS = ROOT / "cache" / "stats.json"

# Keep this identical to make_ascii.RAMP. Index 0 is empty, index 9 is solid.
ART_RAMP = " .:-=+*#%@"
CHAR_ADVANCE = 0.5498
MONO_SIZE_ADJUST = "91.62%"
MONO_FAMILY = 'Consolas, "Menlo Adjusted", "Mono Adjusted", monospace'

CANVAS_W = 1018.0
PANEL_COLS = 65
PANEL_FONT = 16.0
PANEL_ADVANCE = 8.8
PANEL_LINE = 20.0
TEXT_X = 431.0
FIRST_Y = 31.0
ART_FONT = 10.2
ART_ADVANCE = 5.608
ART_LINE = 11.2
ART_BAND = (15.0, 416.0)
SHIPPED = date(2018, 9, 1)
TITLE = "usama@khan"

INFO: list[tuple[str, str] | None] = [
    ("OS", "Windows, Ubuntu"),
    ("Uptime", ""),
    ("Host", "Pakistan"),
    ("Kernel", "Applied AI Engineer"),
    ("Work", "Senior Software Engineer @ FOCUS"),
    ("IDE", "VS Code"),
    None,
    ("Languages.Programming", "TypeScript, JavaScript, Python, Rust"),
    ("Languages.Computer", "HTML, CSS, SQL, GraphQL"),
    ("Languages.Real", "English, Urdu"),
    None,
    ("Focus.Web", "Next.js, React, TypeScript, Three.js"),
    ("Focus.AI", "Computer Vision, Local LLMs, PyTorch"),
    ("Focus.Backend", "Python, FastAPI, Laravel, WebSockets"),
    ("Hobbies", "Dota 2, Local LLMs"),
]

CONTACT = [
    ("Email", "usamakhangt4@gmail.com"),
    ("LinkedIn", "usamakhangt4"),
    ("Portfolio", "usamakhan.vercel.app"),
]

THEMES: dict[str, dict[str, str | list[str]]] = {
    "dark": {
        "bg": "#161b22",
        "text": "#c9d1d9",
        "key": "#58a6ff",
        "value": "#a5d6ff",
        "dots": "#616e7f",
        "green": "#3fb950",
        "red": "#f85149",
        "button_border": "#363c43",
        "portfolio": "#58a6ff",
        "linkedin": "#a5d6ff",
        "email": "#f0883e",
        "pac": "#ffe14a",
        "ghost_eye": "#f0f6fc",
        "ghost_pupil": "#161b22",
        "ghosts": ["#f85149", "#f778ba", "#39c5cf", "#f0883e"],
        "levels": ["#21262d", "#1f3654", "#2b5287", "#4a7fc4", "#a5d6ff"],
    },
    "light": {
        "bg": "#f6f8fa",
        "text": "#24292f",
        "key": "#0969da",
        "value": "#0a3069",
        "dots": "#8c959f",
        "green": "#1a7f37",
        "red": "#cf222e",
        "button_border": "#d8d8da",
        "portfolio": "#0969da",
        "linkedin": "#0550ae",
        "email": "#bc4c00",
        "pac": "#e2a400",
        "ghost_eye": "#ffffff",
        "ghost_pupil": "#24292f",
        "ghosts": ["#cf222e", "#bf3989", "#1b7c83", "#bc4c00"],
        "levels": ["#ebedf0", "#cfe0f5", "#94bbe9", "#4f8ad6", "#0a3069"],
    },
}

FONT_CSS = f"""
@font-face {{
  font-family: "Menlo Adjusted";
  src: local("Menlo");
  size-adjust: {MONO_SIZE_ADJUST};
  ascent-override: 100%;
  descent-override: 20%;
  line-gap-override: 0%;
}}
@font-face {{
  font-family: "Mono Adjusted";
  src: local("Courier New"), local("Liberation Mono"), local("DejaVu Sans Mono");
  size-adjust: {MONO_SIZE_ADJUST};
  ascent-override: 100%;
  descent-override: 20%;
  line-gap-override: 0%;
}}
.mono {{
  font-family: {MONO_FAMILY};
  white-space: pre;
}}
""".strip()


@dataclass(frozen=True)
class Seg:
    text: str
    role: str


@dataclass(frozen=True)
class Line:
    pieces: list[Seg]
    kind: str


def theme(name: str) -> dict[str, str | list[str]]:
    if name == "dark":
        return THEMES["dark"]
    if name == "light":
        return THEMES["light"]
    raise SystemExit(f"unknown theme {name}")


def color(name: str, role: str) -> str:
    value = theme(name)[role]
    if not isinstance(value, str):
        raise SystemExit(f"{role} is not a colour on {name}")
    return value


def fmt(number: float) -> str:
    rounded = round(number, 2)
    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _width(pieces: list[Seg]) -> int:
    return sum(len(piece.text) for piece in pieces)


def _join(pieces: list[Seg]) -> str:
    return "".join(piece.text for piece in pieces)


def uptime(today: date | None = None) -> str:
    current = date.today() if today is None else today
    years = current.year - SHIPPED.year
    months = current.month - SHIPPED.month
    if current.day < SHIPPED.day:
        months -= 1
    if months < 0:
        years -= 1
        months += 12
    return f"{years} years, {months} months (shipping since 2018)"


def _key(key: str) -> list[Seg]:
    pieces: list[Seg] = []
    for index, part in enumerate(key.split(".")):
        if index:
            pieces.append(Seg(".", "text"))
        pieces.append(Seg(part, "key"))
    return pieces


def _row(key: str, value: str) -> list[Seg]:
    prefix = [Seg(". ", "dots"), *_key(key), Seg(":", "text")]
    dots = PANEL_COLS - _width(prefix) - len(value) - 2
    if dots < 1:
        raise SystemExit(f"{key} does not fit in {PANEL_COLS} columns")
    pieces = [*prefix, Seg(" " + ("." * dots) + " ", "dots"), Seg(value, "value")]
    if _width(pieces) != PANEL_COLS:
        raise SystemExit(f"{key} rendered at {_width(pieces)} columns")
    return pieces


def _separator() -> list[Seg]:
    return [Seg("." + (" " * (PANEL_COLS - 1)), "dots")]


def _section(title: str) -> list[Seg]:
    core = f"- {title} -"
    dashes = PANEL_COLS - len(core) - 1
    if dashes < 1:
        raise SystemExit(f"section {title} does not fit")
    text = core + ("—" * dashes) + "-"
    if len(text) != PANEL_COLS:
        raise SystemExit(f"section {title} rendered at {len(text)} columns")
    return [Seg(text, "text")]


def _half(prefix: list[Seg], value: list[Seg], width: int) -> list[Seg]:
    dots = width - _width(prefix) - _width(value) - 2
    if dots < 1:
        raise SystemExit(f"split column does not fit in {width}: {_join(prefix)} {_join(value)}")
    pieces = [*prefix, Seg(" " + ("." * dots) + " ", "dots"), *value]
    if _width(pieces) != width:
        raise SystemExit(f"split column rendered at {_width(pieces)}, expected {width}")
    return pieces


def _split(left_key: str, left_value: list[Seg], right_key: str, right_value: list[Seg]) -> list[Seg]:
    left = _half([Seg(". ", "dots"), Seg(left_key, "key"), Seg(":", "text")], left_value, 37)
    right = _half([Seg(right_key, "key"), Seg(":", "text")], right_value, 25)
    pieces = [*left, Seg(" | ", "text"), *right]
    if _width(pieces) != PANEL_COLS:
        raise SystemExit(f"{left_key} split rendered at {_width(pieces)} columns")
    return pieces


def _num(value: int | None) -> str:
    if value is None:
        return "0"
    return f"{value:,}"


def load_stats() -> dict[str, int] | None:
    if not CACHE_STATS.exists():
        return None
    data = json.loads(CACHE_STATS.read_text(encoding="utf-8"))
    required = (
        "repos_owned",
        "repos_contributed",
        "stars",
        "commits",
        "followers",
        "loc_added",
        "loc_deleted",
    )
    if any(key not in data for key in required):
        return None
    return {key: int(data[key]) for key in required}


def _stats(stats: dict[str, int] | None) -> list[Line]:
    owned = 0 if stats is None else stats["repos_owned"]
    contributed = 0 if stats is None else stats["repos_contributed"]
    stars = 0 if stats is None else stats["stars"]
    commits = 0 if stats is None else stats["commits"]
    followers = 0 if stats is None else stats["followers"]
    added = 0 if stats is None else stats["loc_added"]
    deleted = 0 if stats is None else stats["loc_deleted"]
    repos_value = [
        Seg(_num(owned), "value"),
        Seg(" {", "text"),
        Seg("Contributed", "key"),
        Seg(": ", "text"),
        Seg(_num(contributed), "value"),
        Seg("}", "text"),
    ]
    loc_value = [
        Seg(_num(added - deleted), "value"),
        Seg(" ( ", "text"),
        Seg(f"{_num(added)}++", "green"),
        Seg(", ", "text"),
        Seg(f"{_num(deleted)}--", "red"),
        Seg(" )", "text"),
    ]
    return [
        Line(_split("Repos", repos_value, "Stars", [Seg(_num(stars), "value")]), "row"),
        Line(_split("Commits", [Seg(_num(commits), "value")], "Followers", [Seg(_num(followers), "value")]), "row"),
        Line(
            [
                Seg(". ", "dots"),
                *_key("Lines of Code"),
                Seg(":", "text"),
                Seg(
                    " "
                    + (
                        "."
                        * (
                            PANEL_COLS
                            - len(". Lines of Code:")
                            - _width(loc_value)
                            - 2
                        )
                    )
                    + " ",
                    "dots",
                ),
                *loc_value,
            ],
            "row",
        ),
    ]


def build_lines(stats: dict[str, int] | None, today: date | None = None) -> list[Line]:
    lines = [
        Line(
            [Seg(TITLE, "title"), Seg(" -" + ("—" * 52) + "-", "rule")],
            "row",
        )
    ]
    for item in INFO:
        if item is None:
            lines.append(Line(_separator(), "row"))
            continue
        key, value = item
        if key == "Uptime":
            value = uptime(today)
        lines.append(Line(_row(key, value), "row"))
    lines.append(Line(_separator(), "row"))
    lines.append(Line(_section("Contact"), "row"))
    for key, value in CONTACT:
        lines.append(Line(_row(key, value), "row"))
    lines.append(Line(_separator(), "row"))
    lines.append(Line(_section("GitHub Stats"), "row"))
    lines.extend(_stats(stats))
    lines.append(Line([Seg(" " * PANEL_COLS, "text")], "row"))
    lines.append(Line([Seg("> ", "key"), Seg("█", "value")], "cursor"))
    for line in lines:
        if line.kind != "row":
            continue
        if _width(line.pieces) != PANEL_COLS:
            raise SystemExit(f"a panel row is {_width(line.pieces)} columns: {_join(line.pieces)!r}")
    if _width(lines[0].pieces) != PANEL_COLS:
        raise SystemExit("title row is not 65 columns")
    return lines


def load_art(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not any(line.strip() for line in lines):
        raise SystemExit(f"{path} has no portrait")
    return lines


def load_colors() -> list[list[list[float] | None]]:
    if not ART_COLOR.exists():
        raise SystemExit(f"missing {ART_COLOR.name}")
    data = json.loads(ART_COLOR.read_text(encoding="utf-8"))
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise SystemExit(f"{ART_COLOR.name} has no rows")
    return rows


def _paint(cell: list[float], theme_name: str) -> str:
    red, green, blue, value = (float(cell[0]) / 255, float(cell[1]) / 255, float(cell[2]) / 255, float(cell[3]))
    hue, _lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    if theme_name == "dark":
        saturation = min(1.0, saturation * 1.25)
        lightness = 0.30 + 0.62 * value
    elif theme_name == "light":
        saturation = min(1.0, saturation * 1.25 * 1.35)
        lightness = 0.55 - 0.35 * value
    else:
        raise SystemExit(f"unknown theme {theme_name}")
    out_r, out_g, out_b = colorsys.hls_to_rgb(hue, lightness, saturation)
    return "#{:02x}{:02x}{:02x}".format(
        int(round(out_r * 255)),
        int(round(out_g * 255)),
        int(round(out_b * 255)),
    )


def _art_runs(line: str, cells: list[list[float] | None], theme_name: str) -> list[tuple[str, str]]:
    if len(cells) != len(line):
        raise SystemExit("portrait colour rows do not match the art")
    runs: list[tuple[str, str]] = []
    pending = ""
    for character, cell in zip(line, cells, strict=True):
        if character == " " or cell is None:
            pending += character
            continue
        paint = _paint(cell, theme_name)
        if runs and runs[-1][0] == paint:
            runs[-1] = (paint, runs[-1][1] + pending + character)
        elif not runs:
            runs.append((paint, pending + character))
        else:
            if pending:
                runs[-1] = (runs[-1][0], runs[-1][1] + pending)
            runs.append((paint, character))
        pending = ""
    if pending and runs:
        runs[-1] = (runs[-1][0], runs[-1][1] + pending)
    return runs


def _fill(theme_name: str, role: str) -> str:
    if role == "title":
        return color(theme_name, "key")
    if role == "rule":
        return "url(#title-rule)"
    return color(theme_name, role)


def _spans(pieces: list[Seg], theme_name: str, bold_title: bool) -> str:
    parts: list[str] = []
    for piece in pieces:
        weight = ' font-weight="bold"' if bold_title and piece.role == "title" else ""
        blink = ""
        if piece.text == "█":
            blink = (
                '<animate attributeName="opacity" values="1;0" dur="1.06s" begin="0s" '
                'calcMode="discrete" repeatCount="indefinite"/>'
            )
        parts.append(f'<tspan fill="{_fill(theme_name, piece.role)}"{weight}>{esc(piece.text)}{blink}</tspan>')
    return "".join(parts)


def _line(pieces: list[Seg], theme_name: str, kind: str, y: float) -> str:
    content = _join(pieces)
    length = ""
    if kind == "row":
        length = f' textLength="{fmt(len(content) * PANEL_ADVANCE)}" lengthAdjust="spacing"'
    blink_parent = kind == "cursor"
    return (
        f'<text class="mono" font-size="{fmt(PANEL_FONT)}" xml:space="preserve" data-kind="{kind}">'
        f'<tspan x="{fmt(TEXT_X)}" y="{fmt(y)}"{length}>{_spans(pieces, theme_name, bold_title=not blink_parent)}</tspan>'
        "</text>"
    )


def _portrait(lines: list[str], colors: list[list[list[float] | None]], theme_name: str, height: float) -> str:
    columns = max(len(line) for line in lines)
    block_w = columns * ART_ADVANCE
    band_w = ART_BAND[1] - ART_BAND[0]
    x = ART_BAND[0] + (band_w - block_w) / 2
    block_h = (len(lines) - 1) * ART_LINE
    first_y = (height - block_h) / 2
    parts: list[str] = []
    for index, line in enumerate(lines):
        if not line:
            continue
        runs = _art_runs(line, colors[index], theme_name)
        spans = "".join(f'<tspan fill="{paint}">{esc(text)}</tspan>' for paint, text in runs)
        y = first_y + index * ART_LINE
        parts.append(
            f'<text class="mono" font-size="{fmt(ART_FONT)}" xml:space="preserve" data-kind="art">'
            f'<tspan x="{fmt(x)}" y="{fmt(y)}" textLength="{fmt(len(line) * ART_ADVANCE)}" '
            f'lengthAdjust="spacing">{spans}</tspan></text>'
        )
    return "".join(parts)


def _defs(theme_name: str, height: float) -> str:
    return (
        "<defs>"
        f'<linearGradient id="title-rule" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{color(theme_name, "key")}"/>'
        f'<stop offset="1" stop-color="{color(theme_name, "dots")}" stop-opacity="0.35"/>'
        "</linearGradient>"
        f'<linearGradient id="scan" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{color(theme_name, "key")}" stop-opacity="0"/>'
        f'<stop offset="0.5" stop-color="{color(theme_name, "key")}" stop-opacity="0.10"/>'
        f'<stop offset="1" stop-color="{color(theme_name, "key")}" stop-opacity="0"/>'
        "</linearGradient>"
        '<clipPath id="reveal">'
        f'<rect x="0" y="0" width="{fmt(CANVAS_W)}" height="0">'
        f'<animate attributeName="height" from="0" to="{fmt(height)}" dur="1.2s" begin="0.2s" fill="freeze"/>'
        "</rect></clipPath>"
        "</defs>"
    )


def render(
    theme_name: str,
    lines: list[Line],
    art_lines: list[str],
    colors: list[list[list[float] | None]],
    today: date,
) -> str:
    height = FIRST_Y + PANEL_LINE * (len(lines) - 1) + 20
    label = (
        "Profile card for Usama Khan, usama@khan, Applied AI Engineer in Pakistan "
        "and senior software engineer at FOCUS."
    )
    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(CANVAS_W)}" height="{fmt(height)}" '
            f'viewBox="0 0 {fmt(CANVAS_W)} {fmt(height)}" role="img" aria-label="{esc(label)}" '
            f'data-panel-cols="{PANEL_COLS}">'
        ),
        f"<style><![CDATA[{FONT_CSS}]]></style>",
        _defs(theme_name, height),
        f'<rect width="{fmt(CANVAS_W)}" height="{fmt(height)}" rx="15" fill="{color(theme_name, "bg")}"/>',
        _portrait(art_lines, colors, theme_name, height),
        (
            f'<rect x="15" y="-40" width="386" height="40" fill="url(#scan)">'
            f'<animate attributeName="y" values="-40;{fmt(height)};{fmt(height)}" keyTimes="0;0.35;1" '
            f'dur="9s" begin="0s" repeatCount="indefinite"/></rect>'
        ),
        '<g clip-path="url(#reveal)">',
    ]
    for index, line in enumerate(lines):
        body.append(_line(line.pieces, theme_name, line.kind, FIRST_Y + index * PANEL_LINE))
    body.append("</g>")
    body.append(
        f'<text class="mono" x="1003" y="{fmt(height - 14)}" text-anchor="end" font-size="11" '
        f'fill="{color(theme_name, "dots")}">updated {today.isoformat()} · auto-built daily</text>'
    )
    body.append("</svg>")
    return "\n".join(body) + "\n"


def main() -> None:
    today = date.today()
    stats = load_stats()
    lines = build_lines(stats, today)
    colors = load_colors()
    dark_art = load_art(ART_DARK)
    light_art = load_art(ART_LIGHT)
    if len(colors) != len(dark_art):
        raise SystemExit("colour map does not match the portrait")
    cards = {"dark": ROOT / "dark_mode.svg", "light": ROOT / "light_mode.svg"}
    portraits = {"dark": dark_art, "light": light_art}
    height = FIRST_Y + PANEL_LINE * (len(lines) - 1) + 20
    for name, path in cards.items():
        path.write_text(render(name, lines, portraits[name], colors, today), encoding="utf-8")
        print(f"wrote {path.name} ({fmt(CANVAS_W)}x{fmt(height)})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
