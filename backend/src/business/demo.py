"""Stable sample archive for both supported rubber granule substrates."""

from random import Random

from .composition import COMPONENTS


def _build_row(
    identifier: str,
    scope: str,
    substrate: str,
    weights: tuple[float, ...],
    inspection: str | None = None,
    grams: int | None = None,
) -> dict:
    values = {key: weight for (key, _), weight in zip(COMPONENTS, weights)}
    return {
        "sample_id": identifier,
        "scope": scope,
        "substrate": substrate,
        **values,
        "inspection": inspection,
        "trial_g": grams,
    }


def demo_rows() -> list[dict]:
    rng = Random(2026112502)
    profiles = (
        ("再生 EPDM", (46, 20, 18, 16), (32, 36, 23, 9), (61, 19, 14, 6)),
        ("再生 SBR", (69, 6, 18, 7), (56, 14, 23, 7), (38, 12, 23, 27)),
    )
    rows = [_build_row("RG-H-001", "历史归档", "再生 EPDM", (460, 200, 180, 160), "合格")]
    for number in range(2, 73):
        substrate, *recipes = profiles[number % 2]
        recipe = recipes[(number // 2) % len(recipes)]
        batch_factor = rng.choice((5, 8, 12, 15, 20))
        weights = tuple(round(max(0, (fraction + rng.uniform(-4, 4))) * batch_factor, 1) for fraction in recipe)
        inspection = "未通过" if number % 9 == 0 or number == 70 else "合格"
        if number == 70:
            weights = (46, 20, 18, 16)
        rows.append(_build_row(f"RG-H-{number:03}", "历史归档", substrate, weights, inspection))

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
