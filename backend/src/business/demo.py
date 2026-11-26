"""Stable sample archive for both supported rubber granule substrates.

同桶胶粒分装出的多个批次号共享一个母批号（master_batch），
子批之间仅有称重总量与小幅配比波动，母批之间配方中心明显不同。
"""

from random import Random

from .composition import COMPONENTS


def _build_row(
    identifier: str,
    scope: str,
    substrate: str,
    weights: tuple[float, ...],
    master_batch: str | None = None,
    inspection: str | None = None,
    grams: int | None = None,
) -> dict:
    values = {key: weight for (key, _), weight in zip(COMPONENTS, weights)}
    return {
        "sample_id": identifier,
        "master_batch": master_batch,
        "scope": scope,
        "substrate": substrate,
        **values,
        "inspection": inspection,
        "trial_g": grams,
    }


def _sub_batches(rng: Random, recipe: tuple[int, ...], count: int) -> list[tuple[float, ...]]:
    """同一母批下的子批：配比几乎相同，总克数不同，并保留未检出零值。"""
    batches = []
    for index in range(count):
        factor = rng.choice((5, 8, 12, 15, 20))
        weights = tuple(
            round(max(0, fraction + rng.uniform(-1.2, 1.2)) * factor, 1) for fraction in recipe
        )
        if index == 3 and min(recipe) > 8:
            weights = weights[:3] + (0.0,)
        batches.append(weights)
    return batches


# 每个基材 8 个母批，每批 5 个分装子批；母批配方中心互不相同。
_MASTERS = {
    "再生 EPDM": (
        (46, 20, 18, 16), (32, 36, 23, 9), (61, 19, 14, 6), (55, 12, 20, 13),
        (28, 30, 26, 16), (40, 22, 18, 20), (48, 26, 16, 10), (35, 18, 30, 17),
    ),
    "再生 SBR": (
        (69, 6, 18, 7), (56, 14, 23, 7), (38, 12, 23, 27), (62, 9, 20, 9),
        (44, 22, 20, 14), (50, 10, 28, 12), (33, 18, 24, 25), (58, 8, 16, 18),
    ),
}
_SUB_BATCHES_PER_MASTER = 5
# 磨耗未通过的基材内子批序号（1..40）；EPDM 第 40 个（RG-H-041）配比撞金样 RG-H-001 但磨耗未通过。
_FAILURE_ORDINALS = frozenset({8, 17, 26, 35, 40})
# 与金样 RG-H-001（460/200/180/160 g）同配比但验收未通过的子批。
_GOLDEN_RECIPE = (46, 20, 18, 16)


def demo_rows() -> list[dict]:
    rng = Random(2026112502)
    rows = [_build_row(
        "RG-H-001", "历史归档", "再生 EPDM", (460, 200, 180, 160),
        master_batch="MB-EPDM-01", inspection="合格",
    )]
    history_number = 1
    for substrate, recipes in _MASTERS.items():
        prefix = "EPDM" if substrate == "再生 EPDM" else "SBR"
        for master_index, recipe in enumerate(recipes, start=1):
            master_id = f"MB-{prefix}-{master_index:02d}"
            for within_master, weights in enumerate(_sub_batches(rng, recipe, _SUB_BATCHES_PER_MASTER)):
                history_number += 1
                ordinal = (master_index - 1) * _SUB_BATCHES_PER_MASTER + within_master + 1
                failed = ordinal in _FAILURE_ORDINALS
                if substrate == "再生 EPDM" and ordinal == 40:
                    weights = _GOLDEN_RECIPE
                rows.append(_build_row(
                    f"RG-H-{history_number:03}", "历史归档", substrate, weights,
                    master_batch=master_id, inspection="未通过" if failed else "合格",
                ))

    candidates = (
        ("再生 EPDM", (92, 40, 36, 32), 750),
        ("再生 EPDM", (19, 24, 14, 43), 500),
        ("再生 EPDM", (29, 39, 23, 9), 800),
        ("再生 EPDM", (63, 20, 16, 0), 1250),
        ("再生 SBR", (69, 7, 17, 7), 750),
        ("再生 SBR", (39, 12, 22, 27), 950),
        ("再生 SBR", (19, 62, 12, 7), 600),
        ("再生 SBR", (57, 12, 25, 6), 850),
    )
    for number, (substrate, weights, grams) in enumerate(candidates, 1):
        rows.append(_build_row(f"RG-T-{number:02}", "待试配", substrate, weights, grams=grams))
    return rows
