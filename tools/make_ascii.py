"""Rebuild the profile portraits in assets/ from assets/portrait.png.

The portrait is a low-angle shot against open sky. Sky pixels become spaces
so the card shows the head and shoulders only. Contrast-limited adaptive
histogram equalization runs on the foreground before the character ramp, so
facial detail is not flattened by the shirt and jacket. Output is deterministic.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTRAIT = ROOT / "assets" / "portrait.png"
DARK_ART = ROOT / "assets" / "ascii-art.txt"
LIGHT_ART = ROOT / "assets" / "ascii-art-light.txt"

COLUMNS = 90
CELL_ASPECT = 0.54
RAMP = " .:-=+*#%@"
LANCZOS_A = 3
CONTRAST_CUTOFF = 2.0
SKY_BLUE_MARGIN = 25
# OpenCV-style CLAHE: 8x8 tiles, clip at 4x the average bin count.
CLAHE_TILES = 8
CLAHE_CLIP = 4.0
CLAHE_BINS = 256
CLAHE_MIN_PIXELS = 32


def _paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    distance_left = abs(estimate - left)
    distance_up = abs(estimate - up)
    distance_up_left = abs(estimate - up_left)
    if distance_left <= distance_up and distance_left <= distance_up_left:
        return left
    if distance_up <= distance_up_left:
        return up
    return up_left


def _unfilter(filter_type: int, row: bytearray, previous: bytearray) -> bytearray:
    width = len(row)
    out = bytearray(width)
    for index, value in enumerate(row):
        left = out[index - 3] if index >= 3 else 0
        up = previous[index]
        up_left = previous[index - 3] if index >= 3 else 0
        if filter_type == 0:
            predictor = 0
        elif filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = up
        elif filter_type == 3:
            predictor = (left + up) // 2
        elif filter_type == 4:
            predictor = _paeth(left, up, up_left)
        else:
            raise ValueError(f"unsupported PNG filter {filter_type}")
        out[index] = (value + predictor) & 0xFF
    return out


def read_rgb_png(path: Path) -> list[list[tuple[int, int, int]]]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    offset = 8
    width = height = 0
    idat = bytearray()
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
            if bit_depth != 8 or color_type != 2 or interlace != 0:
                raise ValueError("portrait PNG must be 8-bit non-interlaced RGB")
        elif chunk_type == b"IDAT":
            idat.extend(chunk)
        elif chunk_type == b"IEND":
            break
    raw = zlib.decompress(bytes(idat))
    stride = width * 3
    cursor = 0
    previous = bytearray(stride)
    image: list[list[tuple[int, int, int]]] = []
    for _y in range(height):
        filter_type = raw[cursor]
        cursor += 1
        scanline = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        previous = _unfilter(filter_type, scanline, previous)
        image.append(
            [(previous[x * 3], previous[x * 3 + 1], previous[x * 3 + 2]) for x in range(width)]
        )
    return image


def _lanczos(distance: float) -> float:
    if distance <= -LANCZOS_A or distance >= LANCZOS_A:
        return 0.0
    if distance == 0.0:
        return 1.0
    pix = math.pi * distance
    return LANCZOS_A * math.sin(pix) * math.sin(pix / LANCZOS_A) / (pix * pix)


def _sample_weights(src_size: int, dst_size: int) -> list[list[tuple[int, float]]]:
    scale = src_size / dst_size
    taps: list[list[tuple[int, float]]] = []
    for dest in range(dst_size):
        center = (dest + 0.5) * scale - 0.5
        start = max(0, math.floor(center - LANCZOS_A + 1))
        end = min(src_size - 1, math.ceil(center + LANCZOS_A - 1))
        weighted: list[tuple[int, float]] = []
        total = 0.0
        for src in range(start, end + 1):
            weight = _lanczos(center - src)
            if weight != 0.0:
                weighted.append((src, weight))
                total += weight
        if total == 0.0:
            taps.append([(min(src_size - 1, max(0, round(center))), 1.0)])
        else:
            taps.append([(src, weight / total) for src, weight in weighted])
    return taps


def resize_lanczos(
    image: list[list[tuple[int, int, int]]], width: int, height: int
) -> list[list[tuple[int, int, int]]]:
    src_h = len(image)
    src_w = len(image[0])
    x_taps = _sample_weights(src_w, width)
    horizontal: list[list[tuple[float, float, float]]] = []
    for row in image:
        band: list[tuple[float, float, float]] = []
        for taps in x_taps:
            red = green = blue = 0.0
            for src, weight in taps:
                pixel = row[src]
                red += pixel[0] * weight
                green += pixel[1] * weight
                blue += pixel[2] * weight
            band.append((red, green, blue))
        horizontal.append(band)
    y_taps = _sample_weights(src_h, height)
    output: list[list[tuple[int, int, int]]] = []
    for taps in y_taps:
        row: list[tuple[int, int, int]] = []
        for x in range(width):
            red = green = blue = 0.0
            for src, weight in taps:
                pixel = horizontal[src][x]
                red += pixel[0] * weight
                green += pixel[1] * weight
                blue += pixel[2] * weight
            row.append(
                (
                    max(0, min(255, round(red))),
                    max(0, min(255, round(green))),
                    max(0, min(255, round(blue))),
                )
            )
        output.append(row)
    return output


def _luma(pixel: tuple[int, int, int]) -> int:
    red, green, blue = pixel
    return max(0, min(255, round(0.299 * red + 0.587 * green + 0.114 * blue)))


def _is_sky(pixel: tuple[int, int, int]) -> bool:
    red, green, blue = pixel
    return blue > red + SKY_BLUE_MARGIN and blue > green


def _clip_histogram(hist: list[int], limit: int) -> None:
    excess = 0
    for index, count in enumerate(hist):
        if count > limit:
            excess += count - limit
            hist[index] = limit
    if excess == 0:
        return
    bins = len(hist)
    batch = excess // bins
    if batch:
        for index in range(bins):
            hist[index] += batch
        excess -= batch * bins
    if excess == 0:
        return
    step = max(bins // excess, 1)
    index = 0
    while excess > 0 and index < bins:
        hist[index] += 1
        excess -= 1
        index += step


def _equalize_lut(hist: list[int]) -> list[int] | None:
    total = sum(hist)
    if total < CLAHE_MIN_PIXELS:
        return None
    cdf = 0
    cdf_min = 0
    found = False
    cumulative = [0] * len(hist)
    for index, count in enumerate(hist):
        cdf += count
        cumulative[index] = cdf
        if not found and count:
            cdf_min = cdf
            found = True
    span = total - cdf_min
    if span <= 0:
        return None
    return [max(0, min(255, round((value - cdf_min) * 255 / span))) for value in cumulative]


def _clahe(luma: list[list[int]], sky: list[list[bool]]) -> list[list[int]]:
    """Stretch foreground contrast inside each tile, then blend the tile maps."""
    height = len(luma)
    width = len(luma[0])
    tiles = CLAHE_TILES
    luts: list[list[list[int] | None]] = []
    for tile_y in range(tiles):
        y0 = tile_y * height // tiles
        y1 = (tile_y + 1) * height // tiles
        row_luts: list[list[int] | None] = []
        for tile_x in range(tiles):
            x0 = tile_x * width // tiles
            x1 = (tile_x + 1) * width // tiles
            hist = [0] * CLAHE_BINS
            for y in range(y0, y1):
                sky_row = sky[y]
                luma_row = luma[y]
                for x in range(x0, x1):
                    if not sky_row[x]:
                        hist[luma_row[x]] += 1
            count = sum(hist)
            if count >= CLAHE_MIN_PIXELS:
                _clip_histogram(hist, max(1, int(CLAHE_CLIP * count / CLAHE_BINS)))
            row_luts.append(_equalize_lut(hist))
        luts.append(row_luts)

    output: list[list[int]] = []
    for y in range(height):
        ny = (y + 0.5) * tiles / height - 0.5
        y1 = math.floor(ny)
        y2 = y1 + 1
        fy = 0.0 if y1 < 0 else (1.0 if y2 >= tiles else ny - y1)
        ya = min(max(y1, 0), tiles - 1)
        yb = min(max(y2, 0), tiles - 1)
        row_out: list[int] = []
        luma_row = luma[y]
        for x in range(width):
            nx = (x + 0.5) * tiles / width - 0.5
            x1 = math.floor(nx)
            x2 = x1 + 1
            fx = 0.0 if x1 < 0 else (1.0 if x2 >= tiles else nx - x1)
            xa = min(max(x1, 0), tiles - 1)
            xb = min(max(x2, 0), tiles - 1)
            mixed = 0.0
            total_w = 0.0
            value = luma_row[x]
            for lut, weight in (
                (luts[ya][xa], (1.0 - fx) * (1.0 - fy)),
                (luts[ya][xb], fx * (1.0 - fy)),
                (luts[yb][xa], (1.0 - fx) * fy),
                (luts[yb][xb], fx * fy),
            ):
                if lut is None or weight == 0.0:
                    continue
                mixed += lut[value] * weight
                total_w += weight
            if total_w == 0.0:
                row_out.append(value)
            else:
                row_out.append(max(0, min(255, round(mixed / total_w))))
        output.append(row_out)
    return output


def resize_plane(plane: list[list[int]], width: int, height: int) -> list[list[int]]:
    src_h = len(plane)
    src_w = len(plane[0])
    x_taps = _sample_weights(src_w, width)
    horizontal: list[list[float]] = []
    for row in plane:
        band: list[float] = []
        for taps in x_taps:
            value = 0.0
            for src, weight in taps:
                value += row[src] * weight
            band.append(value)
        horizontal.append(band)
    y_taps = _sample_weights(src_h, height)
    output: list[list[int]] = []
    for taps in y_taps:
        row_out: list[int] = []
        for x in range(width):
            value = 0.0
            for src, weight in taps:
                value += horizontal[src][x] * weight
            row_out.append(max(0, min(255, round(value))))
        output.append(row_out)
    return output


def _autocontrast_bounds(values: list[int], cutoff: float) -> tuple[int, int]:
    histogram = [0] * 256
    for value in values:
        histogram[value] += 1
    if not values:
        return 0, 255
    allowance = len(values) * cutoff / 100.0
    low = 0
    seen = 0
    for index, count in enumerate(histogram):
        seen += count
        if seen > allowance:
            low = index
            break
    high = 255
    seen = 0
    for index in range(255, -1, -1):
        seen += histogram[index]
        if seen > allowance:
            high = index
            break
    if high <= low:
        return 0, 255
    return low, high


def render_lines(image: list[list[tuple[int, int, int]]]) -> tuple[list[str], list[str]]:
    height = len(image)
    width = len(image[0])
    rows = max(1, round(height / width * COLUMNS * CELL_ASPECT))
    sampled = resize_lanczos(image, COLUMNS, rows)
    sky = [[_is_sky(pixel) for pixel in row] for row in sampled]
    source_luma = [[_luma(pixel) for pixel in row] for row in image]
    source_sky = [[_is_sky(pixel) for pixel in row] for row in image]
    contrasted = resize_plane(_clahe(source_luma, source_sky), COLUMNS, rows)
    foreground = [
        value
        for row, mask in zip(contrasted, sky)
        for value, hidden in zip(row, mask)
        if not hidden
    ]
    low, high = _autocontrast_bounds(foreground, CONTRAST_CUTOFF)
    span = max(1, high - low)
    dark_lines: list[str] = []
    light_lines: list[str] = []
    ramp_last = len(RAMP) - 1
    for row, mask in zip(contrasted, sky):
        dark_chars: list[str] = []
        light_chars: list[str] = []
        for value, hidden in zip(row, mask):
            if hidden:
                dark_chars.append(" ")
                light_chars.append(" ")
                continue
            stretched = (value - low) / span
            # Keep a floor so facial shadows stay ink instead of punching holes.
            level = max(1, min(ramp_last, round(max(0.0, min(1.0, stretched)) * ramp_last)))
            dark_chars.append(RAMP[level])
            light_chars.append(RAMP[ramp_last - level])
        dark_lines.append("".join(dark_chars).rstrip())
        light_lines.append("".join(light_chars).rstrip())
    while dark_lines and not dark_lines[0]:
        dark_lines.pop(0)
        light_lines.pop(0)
    return dark_lines, light_lines


def write_art(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    image = read_rgb_png(PORTRAIT)
    dark_lines, light_lines = render_lines(image)
    write_art(DARK_ART, dark_lines)
    write_art(LIGHT_ART, light_lines)
    print(f"wrote {DARK_ART.name} and {LIGHT_ART.name} ({len(dark_lines)} rows)")


if __name__ == "__main__":
    main()
