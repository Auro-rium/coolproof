from __future__ import annotations

import pytest

from app.core.telemetry import redact_telemetry
from app.services.verification import VerificationInput, calculate_verification


def test_weather_adjusted_matched_control_calculation() -> None:
    result = calculate_verification(
        VerificationInput(
            treated_baseline=35,
            treated_observed=31,
            control_baseline=34,
            control_observed=34,
            treated_weather_delta=1,
            control_weather_delta=1,
            expected_cooling=3,
        )
    )
    assert result["cooling_effect"] == 4
    assert result["expected_minus_observed"] == -1
    assert result["met_expectation"] is True


def test_verifier_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        calculate_verification(
            VerificationInput(35, 31, 34, 34, expected_cooling=float("nan"))
        )


def test_telemetry_redacts_secret_and_source_text() -> None:
    safe = redact_telemetry({"api_key": "secret", "source_text": "private", "count": 3})
    assert safe == {
        "api_key": {"redacted": True, "length": 6},
        "source_text": {"redacted": True, "length": 7},
        "count": 3,
    }
