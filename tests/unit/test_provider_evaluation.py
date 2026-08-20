from app.agents.evaluation import FROZEN_EVAL_CASES, EvalCase, evaluate_provider
from app.agents.providers import AgentOutput


class EvaluationProvider:
    name = "evaluation-fixture"

    async def generate_structured(self, *, agent: str, context: dict[str, object]) -> AgentOutput:
        return AgentOutput(
            summary=f"{agent} evaluated",
            citations=["fixture:evidence"] if context.get("heat_evidence_present") or context.get("catalogue_entry_present") or context.get("observed_measurements_present") else [],
            facts={"tool": "optimize_portfolio", "budget_preserved": True},
            needs_approval=agent == "verification",
        )


class MissingCitationProvider(EvaluationProvider):
    async def generate_structured(self, *, agent: str, context: dict[str, object]) -> AgentOutput:
        output = await super().generate_structured(agent=agent, context=context)
        return output.model_copy(update={"citations": []})


async def test_frozen_suite_has_32_cases_and_reports_metrics() -> None:
    assert len(FROZEN_EVAL_CASES) == 32
    report = await evaluate_provider(EvaluationProvider())
    assert report.total == 32
    assert report.passed == 32
    assert report.hallucination_rate == 0.0


async def test_missing_citation_fails_groundedness() -> None:
    case = EvalCase(
        "missing-citation",
        "intervention_analyst",
        {"catalogue_entry_present": False},
        requires_citations=True,
    )
    report = await evaluate_provider(MissingCitationProvider(), (case,))
    assert report.passed == 0
    assert report.groundedness == 0.0
