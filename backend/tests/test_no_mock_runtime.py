from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_does_not_expose_demo_generation_or_frontend_samples():
    backend_main = (ROOT / "backend/app/api/main.py").read_text(encoding="utf-8")
    frontend_app = (ROOT / "frontend/src/App.jsx").read_text(encoding="utf-8")
    frontend_api = (ROOT / "frontend/src/api.js").read_text(encoding="utf-8")
    claim_intake = (ROOT / "frontend/src/pages/ClaimIntake.jsx").read_text(encoding="utf-8")

    assert "synthetic_generator" not in backend_main
    assert "/api/demo/" not in backend_main
    assert not (ROOT / "seed_db.py").exists()
    assert not (ROOT / "frontend/vite-mock-plugin.js").exists()
    assert not (ROOT / "frontend/src/pages/DemoLoader.jsx").exists()
    assert "DemoLoader" not in frontend_app
    assert "demoApi" not in frontend_api
    assert "createDemoStream" not in frontend_api
    assert "SAMPLE_CLAIMS" not in claim_intake
    assert "CLM-TEST-0001" not in claim_intake
