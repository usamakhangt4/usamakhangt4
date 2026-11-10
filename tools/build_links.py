"""Pixel-art Portfolio, LinkedIn, and Email buttons, dark and light."""

from __future__ import annotations

import sys

from build_card import CHAR_ADVANCE, FONT_CSS, ROOT, color, esc, fmt

BUTTONS = (
    ("portfolio", "PORTFOLIO", 3.0),
    ("linkedin", "LINKEDIN", 7.667),
    ("email", "EMAIL", 12.333),
)

# 16x16 masks. "#" is ink, "*" is the accent pixel that blinks, "." is empty.
ICONS = {
    "portfolio": (
        "################",
        "#..............#",
        "#..............#",
        "#..##.....*....#",
        "#..##..........#",
        "#..............#",
        "#....######....#",
        "#..............#",
        "################",
        "................",
        ".......##.......",
        ".......##.......",
        ".....######.....",
        "....########....",
        "................",
        "................",
    ),
    "linkedin": (
        "..############..",
        ".##############.",
        "################",
        "###.##....##.###",
        "###.##...#.#.###",
        "###.##...#.#.###",
        "###.##...#.#.###",
        "###.##...#.#.###",
        "###.###...##.###",
        "###..........###",
        "###..######..###",
        "###..######..###",
        "###..######..*##",
        "################",
        ".##############.",
        "..############..",
    ),
    "email": (
        "................",
        ".##############.",
        ".#............#.",
        ".#.#........#.#.",
        ".#..#......#..#.",
        ".#...#....#...#.",
        ".#....#..#....#.",
        ".#.....##.....#.",
        ".#............#.",
        ".#............#.",
        ".#.....*......#.",
        ".#............#.",
        ".##############.",
        "................",
        "................",
        "................",
    ),
}

VIEW_W = "339.333"
VIEW_H = 60.0
PIXEL = 2.0
LABEL_FONT = 18.0
LABEL_ADVANCE = LABEL_FONT * CHAR_ADVANCE


def _num(number: float) -> str:
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _notch(x: float, y: float, width: float, height: float, notch: int = 3) -> str:
    right = x + width
    bottom = y + height
    commands = [f"M{_num(x + notch)} {_num(y)}", f"H{_num(right - notch)}"]
    for step in range(1, notch + 1):
        commands.append(f"L{_num(right - notch + step)} {_num(y + step)}")
    commands.append(f"V{_num(bottom - notch)}")
    for step in range(1, notch + 1):
        commands.append(f"L{_num(right - step)} {_num(bottom - notch + step)}")
    commands.append(f"H{_num(x + notch)}")
    for step in range(1, notch + 1):
        commands.append(f"L{_num(x + notch - step)} {_num(bottom - step)}")
    commands.append(f"V{_num(y + notch)}")
    for step in range(1, notch + 1):
        commands.append(f"L{_num(x + step)} {_num(y + notch - step)}")
    commands.append("Z")
    return " ".join(commands)


def _box(x: float, y: float, width: float, height: float) -> str:
    return f"M{_num(x)} {_num(y)}H{_num(x + width)}V{_num(y + height)}H{_num(x)}Z"


def _icon(name: str, theme_name: str) -> str:
    rows = ICONS[name]
    rects: list[str] = []
    for y, row in enumerate(rows):
        if len(row) != 16:
            raise SystemExit(f"{name} icon row {y} is {len(row)} pixels")
        for x, cell in enumerate(row):
            if cell == ".":
                continue
            fill = color(theme_name, "text" if cell == "*" else name)
            blink = ""
            if cell == "*":
                blink = (
                    '<animate attributeName="opacity" values="1;0;0" keyTimes="0;0.5;1" '
                    'dur="1.06s" begin="0s" calcMode="discrete" repeatCount="indefinite"/>'
                )
            rects.append(
                f'<rect x="{fmt(x * PIXEL)}" y="{fmt(y * PIXEL)}" width="{fmt(PIXEL)}" '
                f'height="{fmt(PIXEL)}" fill="{fill}">{blink}</rect>'
            )
    if not any("animate" in rect for rect in rects):
        raise SystemExit(f"{name} icon needs a blinking pixel")
    body = "".join(rects)
    motion = ""
    if name == "linkedin":
        motion = (
            '<animateTransform attributeName="transform" type="translate" additive="sum" '
            'values="0 0;0 -3;0 0;0 0" keyTimes="0;0.8;0.9;1" dur="2s" begin="0s" '
            'calcMode="discrete" repeatCount="indefinite"/>'
        )
    elif name == "email":
        motion = (
            '<animateTransform attributeName="transform" type="translate" additive="sum" '
            'values="0 0;-2 0;2 0;-2 0;2 0;0 0;0 0" keyTimes="0;0.7;0.74;0.78;0.82;0.86;1" '
            'dur="2.4s" begin="0s" calcMode="discrete" repeatCount="indefinite"/>'
        )
    elif name != "portfolio":
        raise SystemExit(f"unknown button {name}")
    return f'<g shape-rendering="crispEdges">{motion}{body}</g>'


def render(theme_name: str, name: str, label: str, x0: float) -> str:
    alt = {"portfolio": "Portfolio", "linkedin": "LinkedIn", "email": "Email"}[name]
    label_w = len(label) * LABEL_ADVANCE
    group_w = 32 + 12 + label_w
    group_x = x0 + (324 - group_w) / 2
    icon_y = (VIEW_H - 32) / 2
    outer = _notch(x0 - 3, 0, 330, 60)
    inner = _box(x0, 3, 324, 54)
    bevel = "#ffffff" if theme_name == "dark" else "#000000"
    bevel_opacity = "0.06" if theme_name == "dark" else "0.04"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{VIEW_W}" height="{fmt(VIEW_H)}" '
        f'viewBox="0 0 {VIEW_W} {fmt(VIEW_H)}" role="img" aria-label="{esc(alt)}">\n'
        f"<style><![CDATA[{FONT_CSS}]]></style>\n"
        f'<path d="{outer}" fill="{color(theme_name, "button_border")}"/>\n'
        f'<path d="{inner}" fill="{color(theme_name, "bg")}"/>\n'
        f'<rect x="{_num(x0)}" y="3" width="324" height="3" fill="{bevel}" opacity="{bevel_opacity}"/>\n'
        f'<rect x="{_num(x0)}" y="51" width="324" height="3" fill="{color(theme_name, name)}" opacity="0.18"/>\n'
        f'<rect x="{_num(x0)}" y="54" width="324" height="3" fill="{color(theme_name, name)}"/>\n'
        f'<g transform="translate({_num(group_x)} {fmt(icon_y)})">{_icon(name, theme_name)}</g>\n'
        f'<text class="mono" x="{_num(group_x + 44)}" y="35" fill="{color(theme_name, "text")}" '
        f'font-size="{fmt(LABEL_FONT)}" textLength="{fmt(label_w)}" lengthAdjust="spacing" '
        f'xml:space="preserve">{esc(label)}</text>\n'
        "</svg>\n"
    )


def main() -> None:
    for name, label, x0 in BUTTONS:
        for theme_name in ("dark", "light"):
            path = ROOT / f"link_{name}_{theme_name}.svg"
            path.write_text(render(theme_name, name, label, x0), encoding="utf-8")
            print(f"wrote {path.name}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
