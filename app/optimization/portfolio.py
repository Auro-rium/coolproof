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
    exposure_score: float = 0.0
    implementation_capacity: int = 1


@dataclass(frozen=True)
class Allocation:
    zone_id: str
    intervention_id: str
    units: int
    cost: float
    benefit: float
    uncertainty: float = 0.0


@dataclass(frozen=True)
class PortfolioResult:
    allocations: tuple[Allocation, ...]
    total_cost: float
    total_benefit: float
    total_uncertainty: float = 0.0
    remaining_budget: float = 0.0
    rejected: tuple[dict[str, object], ...] = ()
    binding_constraints: tuple[str, ...] = ()


def optimize_portfolio(
    zones: list[ZoneDemand],
    interventions: list[InterventionSpec],
    budget: float,
    *,
    min_equity_units: int = 0,
    min_school_units: int = 0,
    uncertainty_penalty: float = 0.0,
    required: set[tuple[str, str]] | None = None,
    incompatible: set[tuple[str, str]] | None = None,
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
    if uncertainty_penalty < 0:
        raise ValueError("uncertainty_penalty cannot be negative")
    variables: dict[tuple[str, str], Any] = {}
    costs = {item.intervention_id: item.unit_cost for item in interventions}
    benefits = {item.intervention_id: item.cooling_score for item in interventions}
    zone_by_id = {zone.zone_id: zone for zone in zones}
    for zone in zones:
        for intervention in interventions:
            if is_eligible(intervention, zone.land_use):
                variables[zone.zone_id, intervention.intervention_id] = solver.BoolVar(
                    f"x_{zone.zone_id}_{intervention.intervention_id}"
                )
    solver.Add(
        solver.Sum(variable * costs[key[1]] for key, variable in variables.items()) <= budget
    )
    equity = [v for (zone_id, _), v in variables.items() if zone_by_id[zone_id].equity_priority]
    school = [v for (zone_id, _), v in variables.items() if zone_by_id[zone_id].is_school]
    solver.Add(solver.Sum(equity) >= min_equity_units)
    solver.Add(solver.Sum(school) >= min_school_units)
    # At most one unit per zone/intervention is deliberate: catalogue entries
    # represent a project option, not an unconstrained commodity.
    for zone in zones:
        options = [v for (zone_id, _), v in variables.items() if zone_id == zone.zone_id]
        solver.Add(solver.Sum(options) <= max(0, zone.implementation_capacity))
    required = required or set()
    incompatible = incompatible or set()
    for key, variable in variables.items():
        if key in required:
            solver.Add(variable == 1)
        if key in incompatible:
            solver.Add(variable == 0)
    uncertainties = {item.intervention_id: max(0.0, float(getattr(item, "uncertainty", 0.0))) for item in interventions}
    objective = solver.Sum(v * (benefits[key[1]] - uncertainty_penalty * uncertainties[key[1]])
                           for key, v in variables.items())
    solver.Maximize(objective)
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
                    uncertainties[intervention_id] * units,
                )
            )
    return PortfolioResult(
        tuple(allocations),
        round(sum(a.cost for a in allocations), 2),
        round(sum(a.benefit for a in allocations), 4),
        round(sum(a.uncertainty for a in allocations), 4),
        round(budget - sum(a.cost for a in allocations), 2),
        tuple({"zone_id": z.zone_id, "reason": "not_selected"} for z in zones for i in interventions
              if is_eligible(i, z.land_use) and (z.zone_id, i.intervention_id) not in {(a.zone_id, a.intervention_id) for a in allocations}),
        tuple((["budget"] if abs(sum(a.cost for a in allocations) - budget) < 0.01 else []) +
              (["equity_minimum"] if min_equity_units else []) + (["school_minimum"] if min_school_units else [])),
    )
