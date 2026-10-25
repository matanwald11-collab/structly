"""
utils/coords.py
===============
Coordinate conversion utilities for the Structly canvas.

World coordinate system: X → right, Y → up  (metres)
Scene coordinate system: X → right, Y → down (Qt default)
"""
from __future__ import annotations

SCALE_DEFAULT = 80.0   # pixels per metre (matches canvas.py SCALE)


def world_to_scene(wx: float, wy: float, scale: float = SCALE_DEFAULT) -> tuple[float, float]:
    """World (m) → scene (px)."""
    return wx * scale, -wy * scale


def scene_to_world(sx: float, sy: float, scale: float = SCALE_DEFAULT) -> tuple[float, float]:
    """Scene (px) → world (m)."""
    return sx / scale, -sy / scale


def snap_to_grid(v: float, step: float = 0.5) -> float:
    """Round a world value to the nearest grid step."""
    return round(v / step) * step
