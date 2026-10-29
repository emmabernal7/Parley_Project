"""Common utilities for pricing engines."""
from __future__ import annotations


def nearest_half(x: float) -> float:
    return float(round(x - 0.5) + 0.5)


def _hl(x: float) -> str:
    return f"{x:+g}"
