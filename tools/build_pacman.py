"""Contribution calendar with a Pac-Man run and four ghosts.

Every long animation shares one duration and starts at 0 so the loop stays in
step. The mouth chomp is the only short cycle.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

from build_card import FONT_CSS, ROOT, color, esc, fmt, theme

CALENDAR_PATH = ROOT / "cache" / "calendar.json"
WEEKS = 53
DAYS = 7
BOARD_DURATION = 48.0
INTRO = 1.6
OUTRO = 2.0
RESET = 1.8
EAT = BOARD_DURATION - INTRO - OUTRO - RESET
DUR = "48s"
CELL = 12.0
GAP = 3.0
STEP = CELL + GAP
PAD = 20.0
LABEL_W = 40.0
MONTH_H = 22.0
LEGEND_GAP = 18.0
LEGEND_H = 18.0
GHOST_LAGS = (5, 9, 13, 17)
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKDAY_LABELS = ((0, "Mon"), (2, "Wed"), (4, "Fri"))


def _placeholder() -> list[list[dict[str, object]]]:
    start = date(2024, 1, 7)
    weeks: list[list[dict[str, object]]] = []
    for week in range(WEEKS):
        days = []
        for offset in range(DAYS):
            current = start + timedelta(days=week * DAYS + offset)
            days.append({"count": 0, "date": current.isoformat()})
        weeks.append(days)
    return weeks


def _complete_week(days: list[dict[str, object]]) -> list[dict[str, object]]:
    if len(days) > DAYS:
        days = days[:DAYS]
    completed = list(days)
    while len(completed) < DAYS:
        last = date.fromisoformat(str(completed[-1]["date"])) + timedelta(days=1)
        completed.append({"count": 0, "date": last.isoformat()})
    return completed


def _pad_week(before: date) -> list[dict[str, object]]:
    sunday = before - timedelta(days=7)
    return [
        {"count": 0, "date": (sunday + timedelta(days=offset)).isoformat()} for offset in range(DAYS)
    ]


def load_weeks() -> list[list[dict[str, object]]]:
    if not CALENDAR_PATH.exists():
        return _placeholder()
    loaded = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    raw = loaded.get("weeks") if isinstance(loaded, dict) else None
    if not isinstance(raw, list) or not raw:
        return _placeholder()
    weeks: list[list[dict[str, object]]] = []
    for week in raw:
        if not isinstance(week, list):
            return _placeholder()
        days = []
        for day in week:
            if not isinstance(day, dict) or "date" not in day or "count" not in day:
                return _placeholder()
            days.append({"count": int(day["count"]), "date": str(day["date"])})
        weeks.append(_complete_week(days))
    if len(weeks) > WEEKS:
        weeks = weeks[-WEEKS:]
    while len(weeks) < WEEKS:
        first = date.fromisoformat(str(weeks[0][0]["date"]))
        weeks.insert(0, _pad_week(first))
    return weeks


def _cuts(counts: list[int]) -> tuple[int, int, int]:
    positive = sorted(count for count in counts if count > 0)
    if not positive:
        return (1, 1, 1)

    def pick(fraction: float) -> int:
        index = min(len(positive) - 1, max(0, math.ceil(fraction * len(positive)) - 1))
        return positive[index]

    return pick(0.25), pick(0.5), pick(0.75)


def _level(count: int, cuts: tuple[int, int, int]) -> int:
    if count <= 0:
        return 0
    if count <= cuts[0]:
        return 1
    if count <= cuts[1]:
        return 2
    if count <= cuts[2]:
        return 3
    return 4


def _month_labels(weeks: list[list[dict[str, object]]]) -> list[tuple[int, str]]:
    labels: list[tuple[int, str]] = []
    last = -4
    for index, week in enumerate(weeks):
        marker: int | None = None
        for day in week:
            if str(day["date"]).endswith("-01"):
                marker = int(str(day["date"])[5:7])
                break
        if marker is None or index - last < 3:
            continue
        labels.append((index, MONTHS[marker - 1]))
        last = index
    return labels


def _geometry() -> tuple[float, float]:
    grid_w = WEEKS * STEP - GAP
    grid_h = DAYS * STEP - GAP
    width = PAD + LABEL_W + grid_w + PAD
    height = PAD + MONTH_H + grid_h + LEGEND_GAP + LEGEND_H + PAD
    return width, height


def _origin(week: int, day: int) -> tuple[float, float]:
    return PAD + LABEL_W + week * STEP, PAD + MONTH_H + day * STEP


def _center(week: int, day: int) -> tuple[float, float]:
    x, y = _origin(week, day)
    return x + CELL / 2, y + CELL / 2


def _cell_index(index: int) -> tuple[int, int]:
    return index % WEEKS, index // WEEKS


def _normalize_times(times: list[float]) -> list[float]:
    if len(times) < 2:
        raise SystemExit("SMIL animation needs two key times")
    gap = 0.000002
    fixed = [0.0]
    room = gap * (len(times) - 2)
    for offset, value in enumerate(times[1:-1], start=1):
        latest = 1.0 - gap * (len(times) - offset)
        earliest = fixed[-1] + gap
        if earliest >= latest:
            raise SystemExit("SMIL key times ran out of room")
        fixed.append(min(max(value, earliest), latest - room))
        room = max(0.0, room - gap)
    if fixed[-1] >= 1.0:
        raise SystemExit("SMIL key times collide with the end")
    fixed.append(1.0)
    return fixed


def _format_times(times: list[float]) -> str:
    rendered = [f"{value:.6f}" for value in _normalize_times(times)]
    for index in range(1, len(rendered)):
        if float(rendered[index]) <= float(rendered[index - 1]):
            raise SystemExit(f"SMIL key times are not increasing: {rendered[index - 1]} then {rendered[index]}")
    return ";".join(rendered)


def board_animate(tag: str, attribute: str, values: list[str], times: list[float], calc: str, transform: str = "") -> str:
    if len(values) != len(times):
        raise SystemExit(f"{attribute} has {len(values)} values for {len(times)} times")
    kind = f' type="{transform}"' if transform else ""
    return (
        f'<{tag} attributeName="{attribute}" begin="0s" dur="{DUR}" repeatCount="indefinite" '
        f'calcMode="{calc}" data-sync="board"{kind} values="{";".join(values)}" '
        f'keyTimes="{_format_times(times)}"/>'
    )


def _track(lag: int, total: int) -> tuple[list[str], list[float]]:
    frames: list[tuple[float, int]] = [(0.0, -lag)]
    for step in range(1, total):
        frames.append((INTRO + EAT * (step / total), step - lag))
    frames.append((INTRO + EAT, total - lag))
    frames.append((INTRO + EAT + OUTRO, total + 4 - lag))
    frames.append((BOARD_DURATION, -lag))
    values: list[str] = []
    times: list[float] = []
    for seconds, step in frames:
        if step < 0:
            anchor = _center(0, 0)
            point = (anchor[0] - 28 + step * 16, anchor[1])
        elif step >= total:
            last = _center(*_cell_index(total - 1))
            point = (last[0] + 30 + (step - total) * 14, last[1])
        else:
            point = _center(*_cell_index(step))
        values.append(f"{fmt(point[0])} {fmt(point[1])}")
        times.append(seconds / BOARD_DURATION)
    return values, times


def _wedge(radius: float, mouth_deg: float) -> str:
    half = math.radians(mouth_deg / 2)
    upper = (radius * math.cos(half), -radius * math.sin(half))
    lower = (radius * math.cos(half), radius * math.sin(half))
    return (
        f"M0 0 L{fmt(upper[0])} {fmt(upper[1])} "
        f"A{fmt(radius)} {fmt(radius)} 0 1 1 {fmt(lower[0])} {fmt(lower[1])} Z"
    )


def _circle(radius: float) -> str:
    return (
        f"M{fmt(radius)} 0 A{fmt(radius)} {fmt(radius)} 0 1 1 {fmt(-radius)} 0 "
        f"A{fmt(radius)} {fmt(radius)} 0 1 1 {fmt(radius)} 0"
    )


def _span_opacity(start: float, end: float) -> str:
    t0 = start / BOARD_DURATION
    t1 = min(end / BOARD_DURATION, 1.0)
    if t0 <= 0.0 and t1 >= 0.999:
        return ""
    if t0 <= 0.0:
        return board_animate("animate", "opacity", ["1", "1", "0", "0"], [0.0, t1, t1 + 0.0004, 1.0], "linear")
    if t1 >= 0.999:
        return board_animate("animate", "opacity", ["0", "0", "1", "1"], [0.0, t0, t0 + 0.0004, 1.0], "linear")
    return board_animate(
        "animate",
        "opacity",
        ["0", "0", "1", "1", "0", "0"],
        [0.0, t0, t0 + 0.0004, t1, t1 + 0.0004, 1.0],
        "linear",
    )


def _scores(counts: list[int]) -> list[str]:
    changes: list[tuple[float, int]] = [(0.0, 0)]
    running = 0
    total = len(counts)
    for index, count in enumerate(counts):
        running += count
        if running != changes[-1][1]:
            changes.append((INTRO + EAT * ((index + 1) / total), running))
    reset_at = INTRO + EAT + OUTRO
    if changes[-1][1] != 0:
        changes.append((reset_at, 0))
    parts: list[str] = []
    for index, (start, score) in enumerate(changes):
        end = changes[index + 1][0] if index + 1 < len(changes) else BOARD_DURATION
        animation = _span_opacity(start, end)
        base = "1" if not animation else "0"
        parts.append(
            f'<text class="mono" x="{fmt(PAD)}" y="{fmt(_legend_y() + 13)}" fill="__SCORE__" '
            f'font-size="13" opacity="{base}" data-kind="score">SCORE {score:,}{animation}</text>'
        )
    return parts


def _legend_y() -> float:
    return PAD + MONTH_H + (DAYS * STEP - GAP) + LEGEND_GAP


def _ghost(fill: str, eye: str, pupil: str) -> str:
    body = (
        "M-6,-1 C-6,-6.2 -3.2,-8 0,-8 C3.2,-8 6,-6.2 6,-1 "
        "L6,5 L4.4,3.5 L2.8,5 L1.2,3.5 L0,5 L-1.2,3.5 L-2.8,5 L-4.4,3.5 L-6,5 Z"
    )
    return (
        f'<g><path d="{body}" fill="{fill}"/>'
        f'<circle cx="-2.3" cy="-2.1" r="1.65" fill="{eye}"/>'
        f'<circle cx="2.3" cy="-2.1" r="1.65" fill="{eye}"/>'
        f'<circle cx="-1.7" cy="-1.8" r="0.72" fill="{pupil}"/>'
        f'<circle cx="2.9" cy="-1.8" r="0.72" fill="{pupil}"/></g>'
    )


def render(theme_name: str, weeks: list[list[dict[str, object]]]) -> str:
    colors = theme(theme_name)
    levels = colors["levels"]
    ghosts = colors["ghosts"]
    if not isinstance(levels, list) or len(levels) != 5 or not isinstance(ghosts, list) or len(ghosts) != 4:
        raise SystemExit(f"{theme_name} palette is missing levels or ghosts")
    width, height = _geometry()
    counts = [int(day["count"]) for week in weeks for day in week]
    if len(counts) != WEEKS * DAYS:
        raise SystemExit(f"calendar has {len(counts)} days")
    cuts = _cuts(counts)
    total = len(counts)
    hide = (INTRO + EAT + OUTRO) / BOARD_DURATION
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(width)}" height="{fmt(height)}" '
            f'viewBox="0 0 {fmt(width)} {fmt(height)}" role="img" '
            f'aria-label="{esc("GitHub contribution calendar. Pac-Man eats the days while the score counts up.")}">'
        ),
        f"<style><![CDATA[{FONT_CSS}]]></style>",
        f'<rect width="{fmt(width)}" height="{fmt(height)}" rx="16" fill="{color(theme_name, "bg")}"/>',
    ]
    for index, count in enumerate(counts):
        week, day = _cell_index(index)
        x, y = _origin(week, day)
        hit = (INTRO + EAT * (index / total)) / BOARD_DURATION
        parts.append(
            f'<rect data-cell="1" x="{fmt(x)}" y="{fmt(y)}" width="{fmt(CELL)}" height="{fmt(CELL)}" rx="2" '
            f'fill="{levels[_level(count, cuts)]}">'
            + board_animate(
                "animate",
                "opacity",
                ["1", "1", "0", "0", "1"],
                [0.0, hit, hit + 0.0004, (INTRO + EAT + OUTRO) / BOARD_DURATION, 1.0],
                "linear",
            )
            + "</rect>"
        )
    first = date.fromisoformat(str(weeks[0][0]["date"]))
    for weekday, label in WEEKDAY_LABELS:
        row = (weekday - first.weekday()) % 7
        _x, y = _center(0, row)
        parts.append(
            f'<text class="mono" x="{fmt(PAD)}" y="{fmt(y)}" fill="{color(theme_name, "muted")}" '
            f'font-size="11" dominant-baseline="central">{label}</text>'
        )
    for week, label in _month_labels(weeks):
        x, _y = _origin(week, 0)
        parts.append(
            f'<text class="mono" x="{fmt(x)}" y="{fmt(PAD + 4)}" fill="{color(theme_name, "muted")}" '
            f'font-size="12" dominant-baseline="text-before-edge">{label}</text>'
        )
    actor_opacity = board_animate(
        "animate",
        "opacity",
        ["1", "1", "0", "1"],
        [0.0, hide, hide + 0.0004, 1.0],
        "discrete",
    )
    for lag, ghost_fill in zip(GHOST_LAGS, ghosts, strict=True):
        values, times = _track(lag, total)
        parts.append(
            '<g>'
            + actor_opacity
            + "<g>"
            + board_animate("animateTransform", "transform", values, times, "discrete", "translate")
            + _ghost(ghost_fill, str(colors["ghost_eye"]), str(colors["ghost_pupil"]))
            + "</g></g>"
        )
    radius = CELL * 0.72
    values, times = _track(0, total)
    parts.append(
        "<g>"
        + actor_opacity
        + "<g>"
        + board_animate("animateTransform", "transform", values, times, "discrete", "translate")
        + f'<path fill="{color(theme_name, "pac")}" d="{_wedge(radius, 48)}">'
        + f'<animate attributeName="d" begin="0s" dur="0.24s" repeatCount="indefinite" '
        + f'values="{_wedge(radius, 48)};{_circle(radius)};{_wedge(radius, 48)}"/></path></g></g>'
    )
    box = 12.0
    boxes = 5 * box + 4 * GAP
    more_x = width - PAD - 36
    boxes_x = more_x - 8 - boxes
    less_x = boxes_x - 8 - 34
    legend_y = _legend_y()
    parts.append(
        f'<text class="mono" x="{fmt(less_x)}" y="{fmt(legend_y + 12)}" fill="{color(theme_name, "muted")}" '
        f'font-size="12" dominant-baseline="central">Less</text>'
    )
    for level, paint in enumerate(levels):
        parts.append(
            f'<rect x="{fmt(boxes_x + level * (box + GAP))}" y="{fmt(legend_y + 3)}" width="{fmt(box)}" '
            f'height="{fmt(box)}" rx="2" fill="{paint}"/>'
        )
    parts.append(
        f'<text class="mono" x="{fmt(more_x)}" y="{fmt(legend_y + 12)}" fill="{color(theme_name, "muted")}" '
        f'font-size="12" dominant-baseline="central">More</text>'
    )
    score_fill = color(theme_name, "accent")
    for score in _scores(counts):
        parts.append(score.replace("__SCORE__", score_fill))
    parts.append(
        f'<rect x="1.5" y="1.5" width="{fmt(width - 3)}" height="{fmt(height - 3)}" rx="16" fill="none" '
        f'stroke="{color(theme_name, "border")}"/>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    weeks = load_weeks()
    for theme_name in ("dark", "light"):
        path = ROOT / f"pacman_{theme_name}.svg"
        path.write_text(render(theme_name, weeks), encoding="utf-8")
        print(f"wrote {path.name}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
