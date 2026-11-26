"""Find reproducible and quality-eligible rubber color blend references."""

from collections import defaultdict
from math import ceil, isfinite
from statistics import median

from .composition import center, clr, distance, proportions
from .weighing import largest_adjustment, trial_weight, weighing


def _split(rows: list[dict]):
    reference = defaultdict(list)
    candidates = []
    identifiers = set()
    for row in rows:
        identifier = row["sample_id"]
        if identifier in identifiers:
            raise ValueError(f"批次号 {identifier} 重复。")
        identifiers.add(identifier)
        parts = proportions(row)
        coordinates = clr(parts)
        if row["scope"] == "待试配":
            candidates.append((row, parts, coordinates, trial_weight(row)))
            continue
        inspection = row.get("inspection")
        if inspection not in {"合格", "未通过"}:
            raise ValueError(f"{identifier} 的历史归档缺少磨耗验收结论。")
        if inspection == "合格":
            reference[row["substrate"]].append((identifier, coordinates))
    if not candidates:
        raise ValueError("至少需要一条待试配记录。")
    return dict(reference), candidates


def _coverage(archive: list[tuple[str, tuple[float, ...]]]) -> float:
    distances = sorted(
        min(distance(vector, other) for j, (_, other) in enumerate(archive) if j != i)
        for i, (_, vector) in enumerate(archive)
    )
    return distances[ceil(len(distances) * 0.9) - 1]


def analyze(rows: list[dict], parameter: float) -> dict:
    if not isfinite(parameter) or not 1 <= parameter <= 8 or parameter != int(parameter):
        raise ValueError("纳入参考的近邻数须为 1 到 8 的整数。")
    neighbor_count = int(parameter)
    reference, candidates = _split(rows)
    thresholds = {}
    for substrate in sorted({row["substrate"] for row, _, _, _ in candidates}):
        archive = reference.get(substrate, [])
        required = max(2, neighbor_count)
        if len(archive) < required:
            raise ValueError(f"{substrate} 只有 {len(archive)} 个合格历史批次，至少需要 {required} 个。")
        thresholds[substrate] = _coverage(archive)

    matches = []
    for candidate, target, coordinates, grams in candidates:
        substrate = candidate["substrate"]
        archive = reference[substrate]
        nearest = sorted(
            (distance(coordinates, vector), key, vector) for key, vector in archive
        )[:neighbor_count]
        score, closest, _ = nearest[0]
        recipe = center([vector for _, _, vector in nearest])
        within_coverage = score <= thresholds[substrate] + 1e-12
        matches.append((
            not within_coverage,
            score,
            candidate["sample_id"],
            {
                "sample_id": candidate["sample_id"],
                "substrate": substrate,
                "nearest": closest,
                "distance": round(score, 6),
                "decision": "可先打样" if within_coverage else "单独复测",
                "deviation": largest_adjustment(target, recipe),
                "target_weighing": weighing(target, grams),
                "reference_weighing": weighing(recipe, grams),
            },
        ))

    matches.sort(key=lambda match: match[:3])
    priority_count = sum(not outside for outside, _, _, _ in matches)
    return {
        "summary": f"{len(matches)} 条待试配记录中，{priority_count} 条落入同基材历史配方覆盖范围。",
        "metrics": [
            {"label": "合格历史批次", "value": sum(len(values) for values in reference.values())},
            {"label": "可先打样", "value": priority_count},
            {"label": "待单独复测", "value": len(matches) - priority_count},
            {"label": "最近距离中位数", "value": round(median(match[1] for match in matches), 4)},
        ],
        "rows": [result for _, _, _, result in matches],
        "notes": [
            "四色投料的克数顺序为炭黑 / 陶红 / 沙黄 / 米白。",
            "记录按打样优先级和最近距离排序，距离相同时按批次号排列。",
            "参考中心来自同基材的合格历史配方。首试样仍需走色差与磨耗人工复测。",
            "同基材历史覆盖线分别为 " + "、".join(
                f"{substrate} {threshold:.4f}" for substrate, threshold in thresholds.items()
            ) + "。",
        ],
    }
