from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_assessment_uses_deterministic_evidence_support_label():
    assessment = (ROOT / "frontend/src/pages/Assessment.jsx").read_text(encoding="utf-8")
    assert "evidence_support" in assessment
    assert "Kekuatan Evidence Deterministik" in assessment


def test_dashboard_uses_financial_exposure_language():
    dashboard = (ROOT / "frontend/src/pages/Dashboard.jsx").read_text(encoding="utf-8")
    assert "Potential Financial Exposure" in dashboard
    assert "Potential Savings" not in dashboard


def test_dashboard_api_exposes_additive_financial_exposure_key():
    api = (ROOT / "backend/app/api/main.py").read_text(encoding="utf-8")
    assert '"potential_financial_exposure"' in api
