"""Find reproducible and quality-eligible rubber color blend references."""

from collections import defaultdict
from math import ceil, isfinite
from statistics import median

from .calibration import qualified_archive
from .composition import center, clr, distance, proportions
from .weighing import DEFAULT_NEIGHBORS, largest_adjustment, trial_weight, weighing


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
        if not row.get("master_batch"):
            raise ValueError(f"历史归档批次 {identifier} 缺少母批号，无法按母批组织近邻。")
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


def _validated_neighbors(value: float) -> int:
    if not isfinite(value) or not 1 <= value <= 8 or value != int(value):
        raise ValueError("纳入参考的近邻数须为 1 到 8 的整数。")
    return int(value)


def analyze(rows: list[dict], parameter: float, neighbor_map: dict | None = None,
            calibration_meta: dict | None = None) -> dict:
    """计算配方参考。

    parameter 为补录期/无已发布校准版本时的兜底近邻数；
    neighbor_map 给出每个基材已发布校准版本选定的近邻数，优先于 parameter。
    calibration_meta 记录每个基材所用档案与盲评口径，随结果返回供配方参考页追溯。
    """
    fallback = _validated_neighbors(parameter)
    neighbor_map = neighbor_map or {}
    reference, candidates = _split(rows)
    thresholds = {}
    substrate_neighbors = {}
    for substrate in sorted({row["substrate"] for row, _, _, _ in candidates}):
        archive = reference.get(substrate, [])
        neighbor_count = int(neighbor_map.get(substrate, fallback))
        required = max(2, neighbor_count)
        if len(archive) < required:
            raise ValueError(f"{substrate} 只有 {len(archive)} 个合格历史批次，至少需要 {required} 个。")
        thresholds[substrate] = _coverage(archive)
        substrate_neighbors[substrate] = neighbor_count

    matches = []
    for candidate, target, coordinates, grams in candidates:
        substrate = candidate["substrate"]
        archive = reference[substrate]
        neighbor_count = substrate_neighbors[substrate]
        nearest = sorted(
            (distance(coordinates, vector), key, vector) for key, vector in archive
        )[:neighbor_count]
        score, closest, _ = nearest[0]
        recipe = center([vector for _, _, vector in nearest])
        within_coverage = score <= thresholds[substrate] + 1e-12
        meta = (calibration_meta or {}).get(substrate)
        matches.append((
            not within_coverage,
            score,
            candidate["sample_id"],
            {
                "sample_id": candidate["sample_id"],
                "substrate": substrate,
                "nearest": closest,
                "neighbor_count": neighbor_count,
                "neighbor_source": "published_calibration" if meta else "fallback",
                "calibration_id": meta["calibration_id"] if meta else None,
                "archive_dataset_id": meta["dataset_id"] if meta else None,
                "blind_master": meta["blind_master"] if meta else None,
                "blind_error": meta["blind_error"] if meta else None,
                "default_blind_error": meta["default_blind_error"] if meta else None,
                "distance": round(score, 6),
                "decision": "可先打样" if within_coverage else "单独复测",
                "deviation": largest_adjustment(target, recipe),
                "target_weighing": weighing(target, grams),
                "reference_weighing": weighing(recipe, grams),
            },
        ))

    matches.sort(key=lambda match: match[:3])
    priority_count = sum(not outside for outside, _, _, _ in matches)
    calibrated = sorted(substrate for substrate, meta in (calibration_meta or {}).items() if meta)
    notes = [
        "四色投料的克数顺序为炭黑 / 陶红 / 沙黄 / 米白。",
        "记录按打样优先级和最近距离排序，距离相同时按批次号排列。",
        "参考中心来自同基材的合格历史配方。首试样仍需走色差与磨耗人工复测。",
        "同基材历史覆盖线分别为 " + "、".join(
            f"{substrate} {threshold:.4f}" for substrate, threshold in thresholds.items()
        ) + "。",
    ]
    if calibrated:
        notes.append("近邻数口径：" + "、".join(
            f"{substrate} {substrate_neighbors[substrate]} 个（已发布母批盲评校准，盲评母批 {calibration_meta[substrate]['blind_master']}，"
            f"盲评误差 {calibration_meta[substrate]['blind_error']:.4f} 对默认 {DEFAULT_NEIGHBORS} 近邻 {calibration_meta[substrate]['default_blind_error']:.4f} 个百分点）"
            for substrate in calibrated
        ) + "。")
    fallback_substrates = sorted(set(substrate_neighbors) - set(calibrated))
    if fallback_substrates:
        notes.append("、".join(fallback_substrates) +
                     f" 暂无通过盲评的已发布校准，补录称重档案期间沿用旧版口径，按默认 {fallback} 个近邻推荐。")
    return {
        "summary": f"{len(matches)} 条待试配记录中，{priority_count} 条落入同基材历史配方覆盖范围。",
        "metrics": [
            {"label": "合格历史批次", "value": sum(len(values) for values in reference.values())},
            {"label": "可先打样", "value": priority_count},
            {"label": "待单独复测", "value": len(matches) - priority_count},
            {"label": "最近距离中位数", "value": round(median(match[1] for match in matches), 4)},
        ],
        "rows": [result for _, _, _, result in matches],
        "notes": notes,
    }


def validate_archive(rows: list[dict]) -> None:
    """复用校准归集逻辑，提前暴露母批与验收口径问题。"""
    qualified_archive(rows)
