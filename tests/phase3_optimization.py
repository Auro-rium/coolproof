import pytest

pytest.importorskip("ortools")

from app.optimization.portfolio import ZoneDemand, optimize_portfolio
from app.services.interventions import InterventionSpec


def test_optimizer_obeys_budget_eligibility_and_minimums() -> None:
    result = optimize_portfolio(
        [
            ZoneDemand("school", "school", is_school=True),
            ZoneDemand("park", "park", equity_priority=True),
        ],
        [
            InterventionSpec("trees", "Trees", 10, 5, frozenset({"school", "park"})),
            InterventionSpec("cool-roof", "Cool roof", 30, 20, frozenset({"school"})),
        ],
        50,
        min_equity_units=1,
        min_school_units=1,
    )
    assert result.total_cost <= 50
    assert {a.zone_id for a in result.allocations} == {"school", "park"}


def test_optimizer_rejects_infeasible_equity_requirement() -> None:
    with pytest.raises(ValueError, match="infeasible"):
        optimize_portfolio(
            [ZoneDemand("z", "park")],
            [InterventionSpec("roof", "Roof", 5, 2, frozenset({"school"}))],
            20,
            min_equity_units=1,
        )
