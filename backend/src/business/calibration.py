"""Per-substrate calibration with master-batch-grouped holdout and blind review.

同一母批（同桶分装）的多个批次号组成一个留出组：
- 交叉验证按母批整体留出，避免同桶记录互相作为近邻而高估准度；
- 每个基材再留一个母批做盲评，盲评母批整体退出选参与近邻候选；
- 以四色配比误差（四个组分百分点绝对误差的均值）选择近邻数；
- 首次选出的近邻数与默认近邻数在同一批盲评样本上比较误差。
"""

from collections import defaultdict
from math import fsum

from .composition import center, clr, distance, proportions
from .weighing import DEFAULT_NEIGHBORS

BLIND_TOLERANCE = 1e-9


def composition_error(target: tuple[float, ...], reference: tuple[float, ...]) -> float:
    """四色配比误差：四个组分百分点绝对误差的均值。"""
    return fsum(abs(actual - current) for actual, current in zip(target, reference)) / len(target) * 100


def qualified_archive(rows: list[dict]) -> dict[str, dict[str, list[tuple[str, tuple[float, ...], tuple[float, ...]]]]]:
    """按基材、母批归集合格历史记录：sample_id、配比、CLR 坐标。"""
    archive: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["scope"] != "历史归档":
            continue
        inspection = row.get("inspection")
        if inspection not in {"合格", "未通过"}:
            raise ValueError(f"{row['sample_id']} 的历史归档缺少磨耗验收结论。")
        if inspection != "合格":
            continue
        master = row.get("master_batch")
        if not master:
            raise ValueError(f"历史归档批次 {row['sample_id']} 缺少母批号，无法按母批留出。")
        archive[row["substrate"]][master].append((row["sample_id"], proportions(row), clr(proportions(row))))
    return {substrate: dict(groups) for substrate, groups in archive.items()}


def _blind_master(groups: dict[str, list]) -> str:
    """盲评母批：合格子批最多，并列时取母批号排序靠前者，保证可复现。"""
    return sorted(groups, key=lambda master: (-len(groups[master]), master))[0]


def _fold_error(pool: list[tuple], held: list[tuple], neighbor_count: int) -> float:
    """在固定留出样本上评估某个近邻数的平均四色配比误差。"""
    if len(pool) < neighbor_count:
        raise ValueError("合格历史不足以覆盖指定近邻数。")
    total = 0.0
    for _, target, coordinates in held:
        nearest = sorted(
            (distance(coordinates, vector), vector) for _, _, vector in pool
        )[:neighbor_count]
        recipe = center([vector for _, vector in nearest])
        total += composition_error(target, recipe)
    return total / len(held)


def calibrate_substrate(
    substrate: str,
    groups: dict[str, list[tuple[str, tuple[float, ...], tuple[float, ...]]]],
    k_min: int,
    k_max: int,
) -> dict:
    masters = sorted(groups)
    if len(masters) < 3:
        raise ValueError(f"{substrate} 只有 {len(masters)} 个合格母批，至少需要 3 个（交叉验证与盲评各需独立母批）。")
    blind_master = _blind_master(groups)
    cv_masters = [master for master in masters if master != blind_master]
    blind_rows = groups[blind_master]
    if len(blind_rows) < 1:
        raise ValueError(f"{substrate} 的盲评母批 {blind_master} 没有合格子批。")
    qualified_total = sum(len(rows) for rows in groups.values())
    if qualified_total < 4:
        raise ValueError(f"{substrate} 只有 {qualified_total} 条合格历史，至少需要 4 条才能留出盲评母批并支持近邻评估。")

    # 候选近邻数不能超过任一交叉验证折的训练池规模，保证每个 k 都能完整留出评估。
    fold_pool_sizes = [qualified_total - len(groups[master]) for master in cv_masters]
    feasible_k_max = min(k_max, min(fold_pool_sizes))
    if feasible_k_max < k_min:
        raise ValueError(f"{substrate} 合格历史规模不足以支持近邻数 {k_min} 的母批留出评估。")

    cv_errors = []
    for neighbor_count in range(k_min, feasible_k_max + 1):
        fold_errors = []
        for held_master in cv_masters:
            pool = [item for master in cv_masters if master != held_master for item in groups[master]]
            fold_errors.append(_fold_error(pool, groups[held_master], neighbor_count))
        cv_errors.append({"neighbors": neighbor_count, "cv_error": round(fsum(fold_errors) / len(fold_errors), 6)})

    # 选交叉验证误差最小的近邻数；并列取较小的近邻数（模型更简单、结果更稳定）。
    chosen = min(cv_errors, key=lambda item: (item["cv_error"], item["neighbors"]))["neighbors"]

    # 盲评：盲评母批整体退出选参与近邻候选，新旧近邻数用同一批样本比误差。
    blind_pool = [item for master in cv_masters for item in groups[master]]
    blind_error = _fold_error(blind_pool, blind_rows, chosen)
    default_error = _fold_error(blind_pool, blind_rows, DEFAULT_NEIGHBORS)
    blind_passed = blind_error <= default_error + BLIND_TOLERANCE

    return {
        "substrate": substrate,
        "blind_master": blind_master,
        "blind_samples": [sample_id for sample_id, _, _ in blind_rows],
        "master_count": len(masters),
        "qualified_count": qualified_total,
        "chosen_neighbors": chosen,
        "default_neighbors": DEFAULT_NEIGHBORS,
        "cv_errors": cv_errors,
        "blind_error": round(blind_error, 6),
        "default_blind_error": round(default_error, 6),
        "blind_passed": blind_passed,
    }


def calibrate(rows: list[dict], k_min: int = 1, k_max: int = 8) -> tuple[list[dict], list[str]]:
    """返回 (各基材校准报告, 数据不足被跳过的基材告警)。"""
    archive = qualified_archive(rows)
    if not archive:
        raise ValueError("没有合格历史归档可用于校准。")
    reports = []
    warnings = []
    for substrate in sorted(archive):
        try:
            reports.append(calibrate_substrate(substrate, archive[substrate], k_min, k_max))
        except ValueError as exc:
            warnings.append(str(exc))
    if not reports:
        raise ValueError("；".join(warnings))
    return reports, warnings
