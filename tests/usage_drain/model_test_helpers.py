from __future__ import annotations


def component_credits(
    *,
    uncached: int,
    cached: int,
    reasoning: int,
    nonreasoning: int,
) -> float:
    return (
        (uncached * 125.0) + (cached * 12.5) + ((reasoning + nonreasoning) * 750.0)
    ) / 1_000_000.0


def coefficients_by_feature(rows: list[dict[str, object]]) -> dict[str, float | None]:
    coefficients: dict[str, float | None] = {}
    for row in rows:
        coefficient = row["coefficient"]
        assert coefficient is None or isinstance(coefficient, (int, float))
        coefficients[str(row["feature"])] = None if coefficient is None else float(coefficient)
    return coefficients
