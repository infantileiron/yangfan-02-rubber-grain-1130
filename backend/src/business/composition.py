"""Closure, zero replacement, and centered log ratios for dry granule weights."""

from math import exp, fsum, isfinite, log, sqrt

COMPONENTS = (
    ("carbon_g", "炭黑"),
    ("terra_g", "陶红"),
    ("ochre_g", "沙黄"),
    ("ivory_g", "米白"),
)


def proportions(row: dict) -> tuple[float, ...]:
    values = tuple(float(row[key]) for key, _ in COMPONENTS)
    if any(not isfinite(value) or (value != 0 and not 0.01 <= value <= 10000) for value in values):
        raise ValueError(f"{row['sample_id']} 的色粒克数须为 0（未检出）或 0.01 到 10000。")
    total = fsum(values)
    if total <= 0:
        raise ValueError(f"{row['sample_id']} 的四色粒总克数必须大于 0。")
    return tuple(value / total for value in values)


def clr(parts: tuple[float, ...]) -> tuple[float, ...]:
    zeros = parts.count(0.0)
    if zeros:
        replacement = min(0.0005, min(part for part in parts if part > 0) / 2)
        factor = 1 - replacement * zeros
        parts = tuple(part * factor if part > 0 else replacement for part in parts)
    logs = tuple(log(part) for part in parts)
    log_center = fsum(logs) / len(logs)
    return tuple(value - log_center for value in logs)


def distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sqrt(fsum((x - y) ** 2 for x, y in zip(left, right)))


def center(vectors: list[tuple[float, ...]]) -> tuple[float, ...]:
    shifted = [fsum(axis) / len(vectors) for axis in zip(*vectors)]
    offset = max(shifted)
    weights = [exp(value - offset) for value in shifted]
    total = fsum(weights)
    return tuple(value / total for value in weights)
