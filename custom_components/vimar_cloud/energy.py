"""Helpers for integrating Vimar instantaneous power into energy."""
from __future__ import annotations

import math


def integrate_power_delta_kwh(
    previous_power_w: float | None,
    current_power_w: float,
    dt_seconds: float,
    max_gap_seconds: float,
) -> float:
    """Return trapezoidal energy for one valid sample interval.

    A gap larger than max_gap_seconds is deliberately not integrated because
    Vimar exposes instantaneous power, not a cumulative energy counter.
    """
    if previous_power_w is None:
        return 0.0
    if not math.isfinite(previous_power_w) or previous_power_w < 0:
        return 0.0
    if not math.isfinite(current_power_w) or current_power_w < 0:
        return 0.0
    if not math.isfinite(dt_seconds) or dt_seconds <= 0 or dt_seconds > max_gap_seconds:
        return 0.0
    return ((previous_power_w + current_power_w) / 2.0) * dt_seconds / 3_600_000.0
