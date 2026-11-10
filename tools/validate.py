"""Parse every generated SVG and check the panel grid and SMIL timing."""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET

from build_card import ART_RAMP, CANVAS_W, PANEL_COLS, ROOT, build_lines, fmt, load_art, load_stats
from build_pacman import DAYS, DUR, WEEKS, load_weeks
from make_ascii import RAMP

SVG = "http://www.w3.org/2000/svg"
CARD = ("dark_mode.svg", "light_mode.svg")
PACMAN = ("pacman_dark.svg", "pacman_light.svg")
LINKS = tuple(f"link_{name}_{theme}.svg" for name in ("portfolio", "linkedin", "email") for theme in ("dark", "light"))
LOC_ROW = re.compile(r"^\. Lines of Code: \.+ [\d,]+ \( [\d,]+\+\+, [\d,]+-- \)$")
BUTTON_W = "339.333"


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _parse(path: Path) -> ET.Element:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise SystemExit(f"{path.name} is not valid XML: {exc}") from exc
    if _tag(root) != "svg":
        raise SystemExit(f"{path.name} root is not svg")
    if any(_tag(element) == "script" for element in root.iter()):
        raise SystemExit(f"{path.name} contains a script")
    return root


def _text(element: ET.Element) -> str:
    return "".join(element.itertext())


def _check_rows(cards: dict[str, ET.Element]) -> None:
    expected = ["".join(piece.text for piece in line.pieces) for line in build_lines(load_stats()) if line.kind == "row"]
    if not expected:
        raise SystemExit("the card has no panel rows")
    for name, root in cards.items():
        rows = [_text(element) for element in root.iter(f"{{{SVG}}}text") if element.get("data-kind") == "row"]
        if rows != expected:
            raise SystemExit(f"{name} panel rows do not match the builder")
        for row in rows:
            if len(row) != PANEL_COLS:
                raise SystemExit(f"{name} has a row of {len(row)} columns, expected {PANEL_COLS}")
        loc = [row for row in rows if row.startswith(". Lines of Code:")]
        if len(loc) != 1 or LOC_ROW.fullmatch(loc[0]) is None:
            raise SystemExit(f"{name} lines-of-code row does not match the expected form")
        if root.get("data-panel-cols") != str(PANEL_COLS):
            raise SystemExit(f"{name} is missing the panel column count")
        if root.get("width") != fmt(CANVAS_W):
            raise SystemExit(f"{name} is {root.get('width')} wide, expected {fmt(CANVAS_W)}")


def _check_art(cards: dict[str, ET.Element]) -> None:
    files = {"dark_mode.svg": ROOT / "assets" / "ascii-art.txt", "light_mode.svg": ROOT / "assets" / "ascii-art-light.txt"}
    for name, root in cards.items():
        rendered = [_text(element) for element in root.iter(f"{{{SVG}}}text") if element.get("data-kind") == "art"]
        source = [line for line in load_art(files[name]) if line]
        if rendered != source:
            raise SystemExit(f"{name} art does not match {files[name].name}")


def _check_score(root: ET.Element, name: str) -> None:
    total = sum(int(day["count"]) for week in load_weeks() for day in week)
    if total <= 0:
        return
    blob = "".join(root.itertext())
    if f"{total:,}" not in blob:
        raise SystemExit(f"{name} score never reaches the contribution total {total:,}")


def _check_board(root: ET.Element, name: str) -> None:
    animations = [
        element
        for element in root.iter()
        if _tag(element) in {"animate", "animateTransform"} and element.get("data-sync") == "board"
    ]
    if len(animations) < WEEKS * DAYS:
        raise SystemExit(f"{name} is missing board animations")
    cells = [element for element in root.iter(f"{{{SVG}}}rect") if element.get("data-cell") == "1"]
    if len(cells) != WEEKS * DAYS:
        raise SystemExit(f"{name} has {len(cells)} days, expected {WEEKS * DAYS}")
    durations = {element.get("dur") for element in animations}
    begins = {element.get("begin") for element in animations}
    if durations != {DUR} or begins != {"0s"}:
        raise SystemExit(f"{name} board animations do not share begin 0 and dur {DUR}")
    for element in animations:
        values = (element.get("values") or "").split(";")
        raw_times = (element.get("keyTimes") or "").split(";")
        if len(values) != len(raw_times) or len(values) < 2:
            raise SystemExit(f"{name} has a SMIL value/keyTimes mismatch")
        try:
            times = [float(item) for item in raw_times]
        except ValueError as exc:
            raise SystemExit(f"{name} has a non-numeric keyTime") from exc
        if times[0] != 0.0 or abs(times[-1] - 1.0) > 1e-6:
            raise SystemExit(f"{name} keyTimes must run from 0 to 1")
        if any(times[index] >= times[index + 1] for index in range(len(times) - 1)):
            raise SystemExit(f"{name} keyTimes are not strictly increasing")
        if any(item < 0.0 or item > 1.0 for item in times):
            raise SystemExit(f"{name} keyTimes leave the 0..1 range")
        if element.get("repeatCount") != "indefinite":
            raise SystemExit(f"{name} board animation does not loop")


def _same_box(paths: tuple[str, ...], label: str) -> None:
    boxes = []
    for name in paths:
        root = _parse(ROOT / name)
        boxes.append((root.get("viewBox"), root.get("width"), root.get("height")))
    if len(set(boxes)) != 1:
        raise SystemExit(f"{label} themes differ in size: {boxes}")


def main() -> None:
    if ART_RAMP != RAMP:
        raise SystemExit("the card ramp and the ASCII ramp have drifted apart")
    missing = [name for name in (*CARD, *PACMAN, *LINKS) if not (ROOT / name).exists()]
    if missing:
        raise SystemExit(f"missing SVG: {', '.join(missing)}")
    cards = {name: _parse(ROOT / name) for name in CARD}
    _same_box(CARD, "card")
    _check_rows(cards)
    _check_art(cards)
    _same_box(PACMAN, "pacman")
    for name in PACMAN:
        root = _parse(ROOT / name)
        _check_board(root, name)
        _check_score(root, name)
    _same_box(LINKS, "link")
    for name in LINKS:
        root = _parse(ROOT / name)
        if root.get("aria-label") in {None, ""}:
            raise SystemExit(f"{name} needs alt text")
        if root.get("width") != BUTTON_W:
            raise SystemExit(f"{name} is {root.get('width')} wide, expected {BUTTON_W}")
    for name in PACMAN:
        root = _parse(ROOT / name)
        if root.get("width") != fmt(CANVAS_W):
            raise SystemExit(f"{name} is {root.get('width')} wide, expected {fmt(CANVAS_W)}")
    print(f"validated {len(CARD) + len(PACMAN) + len(LINKS)} SVGs")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
