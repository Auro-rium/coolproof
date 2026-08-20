from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InterventionSpec:
    intervention_id: str
    name: str
    unit_cost: float
    cooling_score: float
    eligible_land_uses: frozenset[str]


def is_eligible(spec: InterventionSpec, land_use: str) -> bool:
    return land_use.casefold() in {value.casefold() for value in spec.eligible_land_uses}


def validated_cost(spec: InterventionSpec, units: int) -> float:
    if units < 0:
        raise ValueError("units cannot be negative")
    if spec.unit_cost <= 0 or spec.cooling_score < 0:
        raise ValueError("intervention costs and scores must be valid")
    return round(spec.unit_cost * units, 2)
