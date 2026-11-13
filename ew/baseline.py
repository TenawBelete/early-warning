"""Behaviour baselines: is someone acting differently from their own normal?

Used by investigation mode for series such as posts per day, media
appearances per week, or share of posts on one topic. A robust z-score
(median and MAD) is used so that a few past spikes do not hide a new one.

This module is unit-tested on synthetic data. It is not exercised by the
Iran backtest, which has no per-person activity series.
"""
from __future__ import annotations

import statistics


def robust_z(history: list[float], current: float) -> float:
    """How unusual `current` is against `history` (about 0 = normal, above 3 = rare)."""
    if len(history) < 8:
        raise ValueError("need at least 8 baseline points")
    med = statistics.median(history)
    mad = statistics.median(abs(x - med) for x in history)
    # MAD is coarse on short, whole-number series, so never let the scale fall
    # far below the ordinary standard deviation.
    scale = max(1.4826 * mad, 0.75 * statistics.pstdev(history)) or 1.0
    return (current - med) / scale


def flag_changes(series: list[float], window: int = 28, threshold: float = 3.0) -> list[tuple[int, float]]:
    """Return (index, z) for every point that departs from its own trailing window."""
    out = []
    for i in range(window, len(series)):
        z = robust_z(series[i - window:i], series[i])
        if abs(z) >= threshold:
            out.append((i, round(z, 2)))
    return out
