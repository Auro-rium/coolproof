"""Deterministic matched-control verification calculations.

The service accepts already-validated aggregate measurements.  It does not
fetch weather, infer observations, or ask an agent to calculate an outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from time import monotonic

from app.core.telemetry import verification_duration_seconds, verification_runs_total


@dataclass(frozen=True)
class VerificationInput:
    treated_baseline: float
    treated_observed: float
    control_baseline: float
    control_observed: float
    treated_weather_delta: float = 0.0
    control_weather_delta: float = 0.0
    expected_cooling: float = 0.0
    treated_threshold_hours_baseline: float = 0.0
    treated_threshold_hours_observed: float = 0.0
    control_threshold_hours_baseline: float = 0.0
    control_threshold_hours_observed: float = 0.0
    total_cost: float = 0.0
    sample_size: int = 1


@dataclass(frozen=True)
class VerificationObservation:
    zone_id: str
    observed_at: str
    temperature_c: float
    threshold_hours: float = 0.0
    weather_delta_c: float = 0.0
    treated: bool = True


def _finite(name: str, value: float) -> float:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def calculate_verification(data: VerificationInput) -> dict[str, object]:
    """Calculate weather-adjusted difference-in-differences.

    Positive ``cooling_effect`` means the treated zone cooled relative to its
    matched control.  Weather deltas are removed from each group before the
    comparison, making the output comparable across observation windows.
    """
    started = monotonic()
    try:
        values = {name: _finite(name, float(value)) for name, value in data.__dict__.items()}
        treated_delta = values["treated_observed"] - values["treated_baseline"]
        control_delta = values["control_observed"] - values["control_baseline"]
        treated_adjusted_delta = treated_delta - values["treated_weather_delta"]
        control_adjusted_delta = control_delta - values["control_weather_delta"]
        # Lower temperatures are better; invert the conventional delta.
        cooling_effect = control_adjusted_delta - treated_adjusted_delta
        expected = max(0.0, values["expected_cooling"])
        variance = cooling_effect - expected
        attainment = cooling_effect / expected if expected else 0.0
        result: dict[str, object] = {
            "method": "matched_control_weather_adjusted_difference_in_differences",
            "treated_delta": treated_delta,
            "control_delta": control_delta,
            "treated_weather_adjusted_delta": treated_adjusted_delta,
            "control_weather_adjusted_delta": control_adjusted_delta,
            "cooling_effect": cooling_effect,
            "expected_cooling": expected,
            "expected_minus_observed": -variance,
            "attainment_ratio": attainment,
            "met_expectation": cooling_effect >= expected,
        }
        threshold_treated = values["treated_threshold_hours_baseline"] - values["treated_threshold_hours_observed"]
        threshold_control = values["control_threshold_hours_baseline"] - values["control_threshold_hours_observed"]
        threshold_reduction = threshold_treated - threshold_control
        # Conservative normal approximation around the DiD effect. A caller
        # can provide a sample size; this remains deterministic and explicit.
        n = max(1, int(values["sample_size"]))
        standard_error = abs(cooling_effect) / sqrt(n) if n > 1 else 0.0
        result.update({"threshold_hours_reduction": threshold_reduction,
                       "treated_threshold_hours_reduction": threshold_treated,
                       "control_threshold_hours_reduction": threshold_control,
                       "observed_cooling": cooling_effect,
                       "weather_adjusted_cooling": cooling_effect,
                       "confidence_interval_95_low": cooling_effect - 1.96 * standard_error,
                       "confidence_interval_95_high": cooling_effect + 1.96 * standard_error,
                       "cost_per_degree": (values["total_cost"] / cooling_effect if cooling_effect > 0 else None),
                       "cost_per_exposure_hour_avoided": (values["total_cost"] / threshold_reduction if threshold_reduction > 0 else None),
                       "sample_size": n})
        verification_runs_total.labels(status="completed").inc()
        return result
    except (TypeError, ValueError, OverflowError):
        verification_runs_total.labels(status="failed").inc()
        raise
    finally:
        verification_duration_seconds.observe(monotonic() - started)
