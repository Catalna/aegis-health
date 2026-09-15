import pytest

from backend.app.api import main
from backend.app.services.claim_queue import ClaimQueueWorker


@pytest.mark.asyncio
async def test_health_exposes_claim_queue_worker_status(monkeypatch):
    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def execute(self, _statement):
            return None

    class _ModelClient:
        async def list_models(self):
            return ["test-model"]

    class _Table:
        def count_rows(self):
            return 1

    worker = ClaimQueueWorker()
    worker._task = __import__("asyncio").current_task()
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr("backend.app.core.llm_client._ollama_client", _ModelClient())
    monkeypatch.setattr("backend.app.agents.financial_engine.get_financial_model", lambda: object())
    monkeypatch.setattr("backend.app.agents.fraud_agent.load_isolation_forest", lambda: object())
    monkeypatch.setattr("backend.app.ml.similarity.get_embedding_model", lambda: object())
    monkeypatch.setattr("backend.app.ml.similarity.get_table", lambda: _Table())
    monkeypatch.setattr("backend.app.ml.graph_metrics.graph_stats", lambda: {"providers_cached": 1})
    main.app.state.claim_queue_worker = worker

    payload = await main.health()

    assert payload["components"]["queue_worker"]["status"] == "ok"
    assert payload["components"]["queue_worker"]["running"] is True
    assert "active_claim_id" not in payload["components"]["queue_worker"]
    assert "models" not in payload["components"]["llm_ollama"]
    assert "test-model" not in str(payload)

    worker._stopping.set()
    degraded_payload = await main.health()
    assert degraded_payload["components"]["queue_worker"]["status"] == "warn"
    assert degraded_payload["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_does_not_expose_dependency_exception_details(monkeypatch):
    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def execute(self, _statement):
            raise RuntimeError("secret database hostname")

    class _ModelClient:
        async def list_models(self):
            raise RuntimeError("secret ollama token")

    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr("backend.app.core.llm_client._ollama_client", _ModelClient())
    monkeypatch.setattr("backend.app.agents.financial_engine.get_financial_model", lambda: (_ for _ in ()).throw(RuntimeError("secret model path")))
    monkeypatch.setattr("backend.app.agents.fraud_agent.load_isolation_forest", lambda: (_ for _ in ()).throw(RuntimeError("secret forest path")))
    monkeypatch.setattr("backend.app.ml.similarity.get_embedding_model", lambda: (_ for _ in ()).throw(RuntimeError("secret vector path")))
    monkeypatch.setattr("backend.app.ml.graph_metrics.graph_stats", lambda: (_ for _ in ()).throw(RuntimeError("secret graph path")))
    main.app.state.claim_queue_worker = None

    payload = await main.health()

    body = str(payload)
    assert "secret" not in body
    for component in payload["components"].values():
        if component["status"] == "error":
            assert component["error_code"] == "dependency_unavailable"


def test_health_overall_status_degrades_for_queue_worker_warning():
    assert main.overall_health_status({"queue_worker": {"status": "warn"}}) == "degraded"
    assert main.overall_health_status({"queue_worker": {"status": "error"}}) == "degraded"
