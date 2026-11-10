"""Rebuild the profile portrait from assets/portrait.png.

The crop drops the shirt and jacket, then the foreground is denoised, masked,
and locally contrasted before it becomes characters. Dark and light use the
same glyphs. Colour lives in assets/ascii-color.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import binary_fill_holes, binary_opening, label

ROOT = Path(__file__).resolve().parent.parent
PORTRAIT = ROOT / "assets" / "portrait.png"
DARK_ART = ROOT / "assets" / "ascii-art.txt"
LIGHT_ART = ROOT / "assets" / "ascii-art-light.txt"
COLOR_JSON = ROOT / "assets" / "ascii-color.json"

COLUMNS = 72
RAMP = " .:-=+*#%@"


def _load_bgr(path: Path) -> np.ndarray:
    encoded = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"could not read {path}")
    return image


def _largest(mask: np.ndarray) -> np.ndarray:
    labeled, count = label(mask)
    if count < 1:
        raise SystemExit("portrait mask is empty")
    counts = np.bincount(labeled.ravel())
    counts[0] = 0
    return labeled == int(np.argmax(counts))


def _crop(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    x0 = int(width * 0.05)
    x1 = int(width * 0.80)
    y0 = int(height * 0.03)
    y1 = int(height * 0.74)
    return image[y0:y1, x0:x1]


def _foreground(bgr: np.ndarray) -> np.ndarray:
    blue = bgr[:, :, 0].astype(np.int16)
    green = bgr[:, :, 1].astype(np.int16)
    red = bgr[:, :, 2].astype(np.int16)
    sky = (blue > red + 25) & (blue > 90)
    opened = binary_opening(~sky, iterations=4)
    filled = binary_fill_holes(opened)
    return _largest(np.asarray(filled, dtype=bool))


def _luma(bgr: np.ndarray) -> np.ndarray:
    lightness = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[:, :, 0]
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    stretched = clahe.apply(lightness).astype(np.float32)
    blurred = cv2.GaussianBlur(stretched, (0, 0), 2)
    return np.clip(stretched + 2.5 * (stretched - blurred), 0, 255)


def _resize(image: np.ndarray, width: int, height: int) -> np.ndarray:
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)


def _masked_mean(rgb: np.ndarray, mask: np.ndarray, width: int, height: int) -> np.ndarray:
    weight = mask.astype(np.float32)
    weighted = rgb.astype(np.float32) * weight[:, :, None]
    small = _resize(weighted, width, height)
    small_weight = _resize(weight, width, height)
    mean = np.zeros_like(small)
    np.divide(small, small_weight[:, :, None], out=mean, where=small_weight[:, :, None] > 1e-4)
    return mean


def _fade(values: np.ndarray) -> np.ndarray:
    faded = values.copy()
    last = values.shape[0] - 1
    start = 0.7 * last
    if last <= start:
        return faded
    for index in range(values.shape[0]):
        if index < start:
            continue
        faded[index] *= 1 - 0.55 * ((index - start) / (last - start))
    return np.clip(faded, 0, 1)


def render(image: np.ndarray) -> tuple[list[str], list[list[list[float] | None]]]:
    cropped = _crop(image)
    denoised = cv2.fastNlMeansDenoisingColored(cropped, None, 9, 9, 7, 21)
    mask = _foreground(denoised)
    luma = _luma(denoised)
    height, width = denoised.shape[:2]
    rows = max(1, round(height / width * COLUMNS * 0.5))
    small_luma = _resize(luma, COLUMNS, rows)
    small_mask = _resize(mask.astype(np.float32), COLUMNS, rows)
    rgb = cv2.cvtColor(denoised, cv2.COLOR_BGR2RGB)
    mean = _masked_mean(rgb, mask, COLUMNS, rows)
    foreground = small_mask >= 0.5
    if not np.any(foreground):
        raise SystemExit("portrait resize lost the foreground")
    low, high = np.percentile(small_luma[foreground], [2, 99])
    span = float(high - low)
    if span <= 0:
        span = 1.0
    normal = np.clip((small_luma - float(low)) / span, 0, 1) ** 1.2
    normal = _fade(normal)
    lines: list[str] = []
    cells: list[list[list[float] | None]] = []
    for y in range(rows):
        chars: list[str] = []
        row_cells: list[list[float] | None] = []
        for x in range(COLUMNS):
            if not foreground[y, x]:
                chars.append(" ")
                row_cells.append(None)
                continue
            value = float(normal[y, x])
            level = max(1, min(9, round(value * 9)))
            chars.append(RAMP[level])
            pixel = mean[y, x]
            row_cells.append(
                [
                    int(np.clip(round(float(pixel[0])), 0, 255)),
                    int(np.clip(round(float(pixel[1])), 0, 255)),
                    int(np.clip(round(float(pixel[2])), 0, 255)),
                    round(value, 4),
                ]
            )
        line = "".join(chars).rstrip()
        lines.append(line)
        cells.append(row_cells[: len(line)])
    while lines and not lines[0]:
        lines.pop(0)
        cells.pop(0)
    while lines and not lines[-1]:
        lines.pop()
        cells.pop()
    return lines, cells


def main() -> None:
    lines, cells = render(_load_bgr(PORTRAIT))
    text = "\n".join(lines) + "\n"
    DARK_ART.write_text(text, encoding="utf-8")
    LIGHT_ART.write_text(text, encoding="utf-8")
    COLOR_JSON.write_text(json.dumps({"rows": cells}, separators=(",", ":")), encoding="utf-8")
    width = max(len(line) for line in lines)
    print(f"wrote ascii art ({len(lines)} rows, {width} columns)")


if __name__ == "__main__":
    main()
