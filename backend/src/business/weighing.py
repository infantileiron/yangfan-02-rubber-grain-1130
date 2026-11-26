"""Convert closed proportions to a reproducible whole-gram bench recipe."""

from math import floor, isfinite

from .composition import COMPONENTS


def trial_weight(row: dict) -> int:
    value = row.get("trial_g")
    if value is None or not isfinite(value) or not 100 <= value <= 5000 or value != int(value):
        raise ValueError(f"{row['sample_id']} 的试样总量须为 100 到 5000 的整数克。")
    return int(value)


def weighing(parts: tuple[float, ...], total: int) -> str:
    quotas = [part * total for part in parts]
    grams = [floor(quota) for quota in quotas]
    by_remainder = sorted(range(len(grams)), key=lambda i: (grams[i] - quotas[i], i))
    for i in by_remainder[: total - sum(grams)]:
        grams[i] += 1
    return " / ".join(str(value) for value in grams)


def largest_adjustment(target: tuple[float, ...], reference: tuple[float, ...]) -> str:
    differences = [(actual - current) * 100 for actual, current in zip(target, reference)]
    index = max(range(len(differences)), key=lambda i: abs(differences[i]))
    return f"{COMPONENTS[index][1]} {differences[index]:+.2f} 个百分点"
