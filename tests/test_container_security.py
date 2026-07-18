from datetime import date

import pytest

from pyfixagent.container_security import evaluate_report


def allowlist(expires: str = "2026-08-31") -> dict:
    return {
        "exceptions": [
            {
                "id": "CVE-2026-12087",
                "expires": expires,
                "rationale": "reviewed base-image issue",
            }
        ]
    }


def test_security_report_accepts_an_active_reviewed_exception():
    result = evaluate_report(
        "x CRITICAL CVE-2026-12087",
        allowlist(),
        today=date(2026, 7, 18),
    )

    assert result["allowed"] == ["CVE-2026-12087"]
    assert result["unexpected"] == []
    assert result["expired"] == []


def test_security_report_rejects_new_and_expired_findings():
    result = evaluate_report(
        "x CRITICAL CVE-2026-12087\nx HIGH CVE-2026-99999",
        allowlist(expires="2026-07-01"),
        today=date(2026, 7, 18),
    )

    assert result["unexpected"] == ["CVE-2026-12087", "CVE-2026-99999"]
    assert result["expired"] == ["CVE-2026-12087"]


def test_security_report_validates_exception_metadata():
    with pytest.raises(ValueError, match="requires expires and rationale"):
        evaluate_report(
            "CVE-2026-12087",
            {"exceptions": [{"id": "CVE-2026-12087"}]},
            today=date(2026, 7, 18),
        )
