"""Frozen, provider-neutral evaluation cases for agent inference.

The suite evaluates the contract around an agent response, not the quality of
an LLM's prose.  Cases contain only synthetic metadata and never source
documents, prompts, credentials, or customer data.  The same cases can be run
against NIM before deployment and Backboard after provider selection.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from app.agents.providers import AgentOutput, LLMProvider


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    agent: str
    context: dict[str, object]
    requires_citations: bool = False
    expected_tool: str | None = None
    requires_budget_preserved: bool = False
    requires_approval: bool = False


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    schema_valid: bool
    grounded: bool
    tool_correct: bool
    budget_preserved: bool
    approval_requested: bool
    latency_ms: float

    @property
    def passed(self) -> bool:
        return all((self.schema_valid, self.grounded, self.tool_correct,
                    self.budget_preserved, self.approval_requested))


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    provider: str
    cases: tuple[CaseResult, ...]

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(case.passed for case in self.cases)

    @property
    def schema_validity(self) -> float:
        return _rate(self.cases, lambda case: case.schema_valid)

    @property
    def groundedness(self) -> float:
        return _rate(self.cases, lambda case: case.grounded)

    @property
    def tool_selection_accuracy(self) -> float:
        return _rate(self.cases, lambda case: case.tool_correct)

    @property
    def hallucination_rate(self) -> float:
        return 1.0 - self.groundedness

    @property
    def average_latency_ms(self) -> float:
        return sum(case.latency_ms for case in self.cases) / self.total if self.total else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "total": self.total,
            "passed": self.passed,
            "schema_validity": self.schema_validity,
            "groundedness": self.groundedness,
            "tool_selection_accuracy": self.tool_selection_accuracy,
            "hallucination_rate": self.hallucination_rate,
            "average_latency_ms": self.average_latency_ms,
            "cases": [
                {"case_id": case.case_id, "passed": case.passed,
                 "latency_ms": case.latency_ms}
                for case in self.cases
            ],
        }


def _rate(cases: tuple[CaseResult, ...], predicate: Callable[[CaseResult], bool]) -> float:
    return sum(predicate(case) for case in cases) / len(cases) if cases else 0.0


def _make_cases() -> tuple[EvalCase, ...]:
    # Six cases per governed agent task. The repeated patterns are intentional:
    # they make the corpus easy to audit and keep the acceptance criteria frozen.
    cases: list[EvalCase] = []
    for index in range(1, 9):
        cases.append(EvalCase(f"heat-{index:02d}", "heat_intelligence",
                              {"heat_evidence_present": index % 2 == 0},
                              requires_citations=index % 2 == 0))
        cases.append(EvalCase(f"intervention-{index:02d}", "intervention_analyst",
                              {"catalogue_entry_present": index % 2 == 0},
                              requires_citations=index % 2 == 0))
        cases.append(EvalCase(f"portfolio-{index:02d}", "portfolio",
                              {"budget": 750000 + index, "schools_protected": True},
                              expected_tool="optimize_portfolio",
                              requires_budget_preserved=True))
        cases.append(EvalCase(f"verification-{index:02d}", "verification",
                              {"observed_measurements_present": index % 2 == 0},
                              requires_citations=index % 2 == 0,
                              requires_approval=True))
    return tuple(cases)


FROZEN_EVAL_CASES: tuple[EvalCase, ...] = _make_cases()


async def evaluate_provider(
    provider: LLMProvider, cases: tuple[EvalCase, ...] = FROZEN_EVAL_CASES,
) -> EvaluationReport:
    results: list[CaseResult] = []
    for case in cases:
        started = monotonic()
        schema_valid = grounded = tool_correct = budget_preserved = approval_requested = False
        try:
            output = await provider.generate_structured(agent=case.agent, context=case.context)
            # AgentOutput validation already happened at the provider boundary.
            schema_valid = isinstance(output, AgentOutput)
            grounded = not case.requires_citations or bool(output.citations)
            expected_tool = case.expected_tool
            tool_correct = expected_tool is None or output.facts.get("tool") == expected_tool
            budget_preserved = not case.requires_budget_preserved or output.facts.get("budget_preserved") is True
            approval_requested = not case.requires_approval or output.needs_approval
        except Exception:  # noqa: BLE001 - a failed case is an evaluation result
            schema_valid = False
            grounded = tool_correct = budget_preserved = approval_requested = False
        results.append(CaseResult(
            case.case_id, schema_valid, grounded, tool_correct, budget_preserved,
            approval_requested, (monotonic() - started) * 1000,
        ))
    return EvaluationReport(provider=provider.name, cases=tuple(results))
