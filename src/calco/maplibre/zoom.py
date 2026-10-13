from __future__ import annotations

import math

SCALE_AT_ZOOM_0 = 559082264.0287178
MAX_ZOOM = 24


def scale_to_zoom(scale: float, tile_size: int = 512) -> float:
    if scale <= 0:
        raise ValueError("scale must be positive")
    return math.log2(SCALE_AT_ZOOM_0 / scale) - math.log2(tile_size / 256)


def zoom_to_scale(zoom: float, tile_size: int = 512) -> float:
    return SCALE_AT_ZOOM_0 / 2 ** (zoom + math.log2(tile_size / 256))


def zoom_range(
    min_scale: float | None, max_scale: float | None, tile_size: int = 512
) -> dict[str, float]:
    found: dict[str, float] = {}
    if max_scale is not None:
        found["minzoom"] = round(max(0.0, scale_to_zoom(max_scale, tile_size)), 6)
    if min_scale is not None and min_scale > 0:
        found["maxzoom"] = round(min(float(MAX_ZOOM), scale_to_zoom(min_scale, tile_size)), 6)
    return found
