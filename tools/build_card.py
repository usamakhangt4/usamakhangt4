"""Build the dark and light neofetch-style profile cards.

The palette lives here. The link buttons and the Pac-Man board import it so
one colour change repaints every SVG.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART_DARK = ROOT / "assets" / "ascii-art.txt"
ART_LIGHT = ROOT / "assets" / "ascii-art-light.txt"
CACHE_STATS = ROOT / "cache" / "stats.json"

# Keep this identical to make_ascii.RAMP. Index 0 is empty, index 9 is solid.
ART_RAMP = " .:-=+*#%@"

# Consolas advance measured at 100px: 54.98px per glyph.
# Courier New at the same size: 60.01px. size-adjust brings the wider faces
# onto Consolas' advance. textLength is a second lock so a generic monospace
# cannot drift the dot leaders.
CHAR_ADVANCE = 0.5498
MONO_SIZE_ADJUST = "91.62%"
MONO_FAMILY = 'Consolas, "Menlo Adjusted", "Mono Adjusted", monospace'

PANEL_COLS = 70
ART_WIDTH = 600.0
CELL_ASPECT = 0.54
OUTER_PAD = 22.0
COLUMN_GAP = 22.0
PANEL_PAD_X = 16.0
PANEL_FONT = 15.0
PANEL_LINE = 20.0

TITLE = "usama@khan"

INFO: list[tuple[str, str] | None] = [
    ("OS", "Windows, Ubuntu"),
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
        "bg": "#0d1117",
        "panel": "#161b22",
        "border": "#30363d",
        "text": "#e6edf3",
        "muted": "#6e7681",
        "accent": "#338bfd",
        "green": "#3fb950",
        "red": "#f85149",
        "cursor": "#338bfd",
        "ink_low": "#2c231e",
        "ink_high": "#fff1e4",
        "pac": "#ffe14a",
        "ghost_eye": "#f0f6fc",
        "ghost_pupil": "#0d1117",
        "ghosts": ["#338bfd", "#f85149", "#b07cff", "#3fb950"],
        "levels": ["#161b22", "#0e3a6b", "#1d6fd4", "#58a6ff", "#d2e7ff"],
    },
    "light": {
        "bg": "#ffffff",
        "panel": "#f6f8fa",
        "border": "#d0d7de",
        "text": "#1f2328",
        "muted": "#818b98",
        "accent": "#0969da",
        "green": "#1a7f37",
        "red": "#cf222e",
        "cursor": "#0969da",
        "ink_low": "#f7f4f1",
        "ink_high": "#2c241f",
        "pac": "#e2a400",
        "ghost_eye": "#ffffff",
        "ghost_pupil": "#1f2328",
        "ghosts": ["#0969da", "#cf222e", "#8250df", "#1a7f37"],
        "levels": ["#ebedf0", "#d5e5ff", "#8cbcff", "#338bfd", "#0550ae"],
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


@dataclass(frozen=True)
class ArtLayout:
    char_w: float
    line_h: float
    font_size: float
    height: float
    top: float


@dataclass(frozen=True)
class Canvas:
    width: float
    height: float
    art_width: float
    panel_x: float
    panel_y: float
    panel_w: float
    panel_h: float
    text_x: float
    text_top: float
    char_w: float


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


def _mix(start: str, end: str, amount: float) -> str:
    def channels(hex_color: str) -> tuple[int, int, int]:
        value = hex_color.removeprefix("#")
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

    left = channels(start)
    right = channels(end)
    mixed = tuple(round(left[index] + (right[index] - left[index]) * amount) for index in range(3))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def ink(character: str, theme_name: str) -> str:
    index = ART_RAMP.find(character)
    if index < 0:
        raise SystemExit(f"art contains {character!r}, which is outside the ramp")
    colors = theme(theme_name)
    low = colors["ink_low"]
    high = colors["ink_high"]
    if not isinstance(low, str) or not isinstance(high, str):
        raise SystemExit("ink colours must be strings")
    amount = index / (len(ART_RAMP) - 1)
    if theme_name == "dark":
        amount = amount**0.8
    elif theme_name == "light":
        amount = amount**1.15
    else:
        raise SystemExit(f"unknown theme {theme_name}")
    return _mix(low, high, amount)


def fit_pieces(prefix: str, prefix_role: str, tail: list[Seg], cols: int = PANEL_COLS) -> list[Seg]:
    tail_width = sum(len(piece.text) for piece in tail)
    dots = cols - len(prefix) - tail_width
    if dots < 2:
        raise SystemExit(f"panel row is wider than {cols} columns: {prefix!r} leaves {dots} dots")
    pieces = [Seg(prefix, prefix_role), Seg("." * dots, "muted"), *tail]
    width = sum(len(piece.text) for piece in pieces)
    if width != cols:
        raise SystemExit(f"row {prefix!r} is {width} columns, expected {cols}")
    return pieces


def fit_row(key: str, value: str, cols: int = PANEL_COLS) -> list[Seg]:
    return fit_pieces(f"{key}: ", "accent", [Seg(f" {value}", "text")], cols)


def section_line(title: str, cols: int = PANEL_COLS) -> list[Seg]:
    core = f"- {title} -"
    extra = cols - len(core)
    if extra < 1:
        raise SystemExit(f"section {title!r} does not fit in {cols} columns")
    text = core + ("—" * extra)
    if len(text) != cols:
        raise SystemExit(f"section {title!r} rendered at {len(text)} columns")
    return [Seg(text, "accent")]


def blank_line(cols: int = PANEL_COLS) -> list[Seg]:
    return [Seg(" " * cols, "text")]


def _placeholder(value: object) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}"


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


def stats_lines(stats: dict[str, int] | None) -> list[Line]:
    owned = _placeholder(None if stats is None else stats["repos_owned"])
    contributed = _placeholder(None if stats is None else stats["repos_contributed"])
    stars = _placeholder(None if stats is None else stats["stars"])
    commits = _placeholder(None if stats is None else stats["commits"])
    followers = _placeholder(None if stats is None else stats["followers"])
    added = _placeholder(None if stats is None else stats["loc_added"])
    deleted = _placeholder(None if stats is None else stats["loc_deleted"])
    loc_tail = [
        Seg(" ", "text"),
        Seg(f"++{added}", "green"),
        Seg(" ", "text"),
        Seg(f"--{deleted}", "red"),
    ]
    return [
        Line(fit_row("Repos", f"{owned} {{{contributed}}} | Stars: {stars}"), "row"),
        Line(fit_row("Commits", f"{commits} | Followers: {followers}"), "row"),
        Line(fit_pieces("Lines of Code: ", "accent", loc_tail), "row"),
    ]


def build_lines(stats: dict[str, int] | None) -> list[Line]:
    user, host = TITLE.split("@", 1)
    lines = [
        Line([Seg(user, "accent"), Seg("@", "muted"), Seg(host, "accent")], "title"),
        Line([Seg("-" * len(TITLE), "accent")], "rule"),
        Line(blank_line(), "row"),
    ]
    for item in INFO:
        if item is None:
            lines.append(Line(blank_line(), "row"))
            continue
        key, value = item
        lines.append(Line(fit_row(key, value), "row"))
    lines.append(Line(blank_line(), "row"))
    lines.append(Line(section_line("Contact"), "row"))
    for key, value in CONTACT:
        lines.append(Line(fit_row(key, value), "row"))
    lines.append(Line(blank_line(), "row"))
    lines.append(Line(section_line("GitHub Stats"), "row"))
    lines.extend(stats_lines(stats))
    lines.append(Line(blank_line(), "row"))
    lines.append(Line([Seg(">", "cursor")], "cursor"))
    for line in lines:
        if line.kind == "row":
            width = sum(len(piece.text) for piece in line.pieces)
            if width != PANEL_COLS:
                raise SystemExit(f"a panel row is {width} columns")
        if line.kind == "title":
            width = sum(len(piece.text) for piece in line.pieces)
            if width != len(TITLE):
                raise SystemExit("title width drifted")
    return lines


def load_art(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not any(line.strip() for line in lines):
        raise SystemExit(f"{path} has no portrait")
    return lines


def layout(dark_art: list[str], light_art: list[str], row_count: int) -> tuple[Canvas, dict[str, ArtLayout]]:
    char_w = PANEL_FONT * CHAR_ADVANCE
    panel_w = PANEL_PAD_X * 2 + PANEL_COLS * char_w
    panel_text_h = row_count * PANEL_LINE
    # The panel fixes the card. A denser portrait gets a smaller font so it
    # still fills ART_WIDTH without changing the card's pixel size.
    content_h = panel_text_h
    width = OUTER_PAD * 2 + ART_WIDTH + COLUMN_GAP + panel_w
    height = OUTER_PAD * 2 + content_h
    canvas = Canvas(
        width=width,
        height=height,
        art_width=ART_WIDTH,
        panel_x=OUTER_PAD + ART_WIDTH + COLUMN_GAP,
        panel_y=OUTER_PAD,
        panel_w=panel_w,
        panel_h=content_h,
        text_x=OUTER_PAD + ART_WIDTH + COLUMN_GAP + PANEL_PAD_X,
        text_top=OUTER_PAD + (content_h - panel_text_h) / 2,
        char_w=char_w,
    )
    arts: dict[str, ArtLayout] = {}
    for name, lines in ("dark", dark_art), ("light", light_art):
        columns = max(len(line) for line in lines)
        rows = len(lines)
        art_char = ART_WIDTH / columns
        natural_line = art_char / CELL_ASPECT
        natural_h = rows * natural_line
        scale = min(1.0, content_h / natural_h) if natural_h else 1.0
        line_h = natural_line * scale
        block = rows * line_h
        arts[name] = ArtLayout(
            char_w=art_char,
            line_h=line_h,
            font_size=art_char / CHAR_ADVANCE * scale,
            height=block,
            top=OUTER_PAD + (content_h - block) / 2,
        )
    return canvas, arts


def _runs(pieces: list[Seg]) -> list[Seg]:
    merged: list[Seg] = []
    for piece in pieces:
        if merged and merged[-1].role == piece.role:
            merged[-1] = Seg(merged[-1].text + piece.text, piece.role)
        else:
            merged.append(piece)
    return merged


def _text(x: float, y: float, pieces: list[Seg], theme_name: str, kind: str, char_w: float) -> str:
    merged = _runs(pieces)
    content = "".join(piece.text for piece in merged)
    spans = "".join(
        f'<tspan fill="{color(theme_name, piece.role)}">{esc(piece.text)}</tspan>' for piece in merged
    )
    cursor = ""
    if kind == "cursor":
        cursor = (
            '<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.45;0.5;1" '
            'dur="1.2s" begin="0s" repeatCount="indefinite" calcMode="discrete"/>'
        )
    return (
        f'<text class="mono" x="{fmt(x)}" y="{fmt(y)}" font-size="{fmt(PANEL_FONT)}" '
        f'textLength="{fmt(len(content) * char_w)}" lengthAdjust="spacingAndGlyphs" '
        f'xml:space="preserve" dominant-baseline="text-before-edge" data-kind="{kind}">'
        f"{spans}{cursor}</text>"
    )


def _art_text(lines: list[str], theme_name: str, art: ArtLayout) -> list[str]:
    rendered: list[str] = []
    for index, line in enumerate(lines):
        if not line:
            continue
        runs: list[tuple[str, str]] = []
        for character in line:
            paint = ink(character, theme_name)
            if runs and runs[-1][0] == paint:
                runs[-1] = (paint, runs[-1][1] + character)
            else:
                runs.append((paint, character))
        spans = "".join(f'<tspan fill="{paint}">{esc(text)}</tspan>' for paint, text in runs)
        y = art.top + index * art.line_h
        rendered.append(
            f'<text class="mono" x="{fmt(OUTER_PAD)}" y="{fmt(y)}" font-size="{fmt(art.font_size)}" '
            f'textLength="{fmt(len(line) * art.char_w)}" lengthAdjust="spacingAndGlyphs" '
            f'xml:space="preserve" dominant-baseline="text-before-edge" data-kind="art">{spans}</text>'
        )
    return rendered


def render(theme_name: str, lines: list[Line], art_lines: list[str], canvas: Canvas, art: ArtLayout) -> str:
    label = (
        "Profile card for Usama Khan, usama@khan, Applied AI Engineer in Pakistan "
        "and senior software engineer at FOCUS."
    )
    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(canvas.width)}" height="{fmt(canvas.height)}" '
            f'viewBox="0 0 {fmt(canvas.width)} {fmt(canvas.height)}" role="img" aria-label="{esc(label)}" '
            f'data-panel-cols="{PANEL_COLS}">'
        ),
        f"<style><![CDATA[{FONT_CSS}]]></style>",
        f'<rect width="{fmt(canvas.width)}" height="{fmt(canvas.height)}" rx="16" fill="{color(theme_name, "bg")}"/>',
        (
            f'<rect x="{fmt(canvas.panel_x)}" y="{fmt(canvas.panel_y)}" width="{fmt(canvas.panel_w)}" '
            f'height="{fmt(canvas.panel_h)}" rx="12" fill="{color(theme_name, "panel")}" '
            f'stroke="{color(theme_name, "border")}"/>'
        ),
        *_art_text(art_lines, theme_name, art),
    ]
    for index, line in enumerate(lines):
        body.append(
            _text(
                canvas.text_x,
                canvas.text_top + index * PANEL_LINE,
                line.pieces,
                theme_name,
                line.kind,
                canvas.char_w,
            )
        )
    body.append(
        f'<rect x="1.5" y="1.5" width="{fmt(canvas.width - 3)}" height="{fmt(canvas.height - 3)}" '
        f'rx="16" fill="none" stroke="{color(theme_name, "border")}"/>'
    )
    body.append("</svg>")
    return "\n".join(body) + "\n"


def main() -> None:
    stats = load_stats()
    lines = build_lines(stats)
    dark_art = load_art(ART_DARK)
    light_art = load_art(ART_LIGHT)
    canvas, arts = layout(dark_art, light_art, len(lines))
    cards = {
        "dark": ROOT / "dark_mode.svg",
        "light": ROOT / "light_mode.svg",
    }
    portraits = {"dark": dark_art, "light": light_art}
    for name, path in cards.items():
        path.write_text(render(name, lines, portraits[name], canvas, arts[name]), encoding="utf-8")
        print(f"wrote {path.name} ({fmt(canvas.width)}x{fmt(canvas.height)})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
