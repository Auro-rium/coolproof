from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.interventions import InterventionSpec, is_eligible, validated_cost


@dataclass(frozen=True)
class ZoneDemand:
    zone_id: str
    land_use: str
    equity_priority: bool = False
    is_school: bool = False


@dataclass(frozen=True)
class Allocation:
    zone_id: str
    intervention_id: str
    units: int
    cost: float
    benefit: float


@dataclass(frozen=True)
class PortfolioResult:
    allocations: tuple[Allocation, ...]
    total_cost: float
    total_benefit: float


def optimize_portfolio(
    zones: list[ZoneDemand],
    interventions: list[InterventionSpec],
    budget: float,
    *,
    min_equity_units: int = 0,
    min_school_units: int = 0,
) -> PortfolioResult:
    if budget < 0 or min_equity_units < 0 or min_school_units < 0:
        raise ValueError("budget and minimums cannot be negative")
    try:
        from ortools.linear_solver import pywraplp  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("OR-Tools must be installed for portfolio optimization") from exc
    # OR-Tools does not publish PEP 561 typing metadata. Keep the untyped SDK
    # boundary local; all input/output values remain concrete domain types.
    solver: Any = pywraplp.Solver.CreateSolver("SCIP")
    if solver is None:  # pragma: no cover
        raise RuntimeError("SCIP solver unavailable")
    variables: dict[tuple[str, str], Any] = {}
    costs = {item.intervention_id: item.unit_cost for item in interventions}
    benefits = {item.intervention_id: item.cooling_score for item in interventions}
    zone_by_id = {zone.zone_id: zone for zone in zones}
    for zone in zones:
        for intervention in interventions:
            if is_eligible(intervention, zone.land_use):
                variables[zone.zone_id, intervention.intervention_id] = solver.IntVar(
                    0, solver.infinity(), f"x_{zone.zone_id}_{intervention.intervention_id}"
                )
    solver.Add(
        solver.Sum(variable * costs[key[1]] for key, variable in variables.items()) <= budget
    )
    equity = [v for (zone_id, _), v in variables.items() if zone_by_id[zone_id].equity_priority]
    school = [v for (zone_id, _), v in variables.items() if zone_by_id[zone_id].is_school]
    solver.Add(solver.Sum(equity) >= min_equity_units)
    solver.Add(solver.Sum(school) >= min_school_units)
    solver.Maximize(solver.Sum(v * benefits[key[1]] for key, v in variables.items()))
    if solver.Solve() not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        raise ValueError("constraints are infeasible")
    allocations = []
    for (zone_id, intervention_id), variable in variables.items():
        units = int(variable.solution_value())
        if units:
            spec = next(i for i in interventions if i.intervention_id == intervention_id)
            allocations.append(
                Allocation(
                    zone_id,
                    intervention_id,
                    units,
                    validated_cost(spec, units),
                    spec.cooling_score * units,
                )
            )
    return PortfolioResult(
        tuple(allocations),
        round(sum(a.cost for a in allocations), 2),
        round(sum(a.benefit for a in allocations), 4),
    )
