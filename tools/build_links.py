"""Pixel-art Portfolio, LinkedIn, and Email buttons, dark and light."""

from __future__ import annotations

import sys

from build_card import FONT_CSS, ROOT, color, esc, fmt

BUTTONS = (
    ("portfolio", "PORTFOLIO"),
    ("linkedin", "LINKEDIN"),
    ("email", "EMAIL"),
)

# 16x16 masks. "#" is ink, "*" is the accent pixel that idles, "." is empty.
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

VIEW_W = 360.0
VIEW_H = 84.0
PIXEL = 3.0
IDLE_SECONDS = "2.6s"


def _icon(name: str, theme_name: str) -> str:
    rows = ICONS[name]
    origin_x = 16.0
    origin_y = (VIEW_H - len(rows) * PIXEL) / 2
    rects: list[str] = []
    blinks: list[str] = []
    for y, row in enumerate(rows):
        if len(row) != 16:
            raise SystemExit(f"{name} icon row {y} is {len(row)} pixels")
        for x, cell in enumerate(row):
            if cell == ".":
                continue
            fill = color(theme_name, "accent" if cell == "*" else "text")
            rect = (
                f'<rect x="{fmt(x * PIXEL)}" y="{fmt(y * PIXEL)}" width="{fmt(PIXEL)}" '
                f'height="{fmt(PIXEL)}" fill="{fill}"/>'
            )
            if cell == "*":
                blinks.append(
                    rect.replace(
                        "/>",
                        '><animate attributeName="opacity" values="1;0.25;1" dur="1.6s" '
                        'begin="0s" repeatCount="indefinite"/></rect>',
                    )
                )
            else:
                rects.append(rect)
    if not blinks:
        raise SystemExit(f"{name} icon needs an idle pixel")
    body = "".join(rects + blinks)
    return (
        f'<g transform="translate({fmt(origin_x)} {fmt(origin_y)})">'
        f'<animateTransform attributeName="transform" type="translate" additive="sum" '
        f'values="0 0; 0 -1.5; 0 0" keyTimes="0;0.5;1" dur="{IDLE_SECONDS}" begin="0s" '
        f'repeatCount="indefinite"/>'
        f"{body}</g>"
    )


def render(theme_name: str, name: str, label: str) -> str:
    alt = {"portfolio": "Portfolio", "linkedin": "LinkedIn", "email": "Email"}[name]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(VIEW_W)}" height="{fmt(VIEW_H)}" '
        f'viewBox="0 0 {fmt(VIEW_W)} {fmt(VIEW_H)}" role="img" aria-label="{esc(alt)}">\n'
        f"<style><![CDATA[{FONT_CSS}]]></style>\n"
        f'<rect width="{fmt(VIEW_W)}" height="{fmt(VIEW_H)}" rx="12" fill="{color(theme_name, "panel")}" '
        f'stroke="{color(theme_name, "border")}"/>\n'
        f"{_icon(name, theme_name)}\n"
        f'<text class="mono" x="78" y="{fmt(VIEW_H / 2)}" fill="{color(theme_name, "text")}" '
        f'font-size="18" dominant-baseline="central" xml:space="preserve">{esc(label)}</text>\n'
        "</svg>\n"
    )


def main() -> None:
    for name, label in BUTTONS:
        for theme_name in ("dark", "light"):
            path = ROOT / f"link_{name}_{theme_name}.svg"
            path.write_text(render(theme_name, name, label), encoding="utf-8")
            print(f"wrote {path.name}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
