"""Test LLM client — retry logic, JSON cleaning, interface compliance."""
import json
import pytest


def test_clean_json_text_strips_markdown():
    from backend.app.core.llm_client import _clean_json_text
    raw = '```json\n{"a": 1}\n```'
    assert json.loads(_clean_json_text(raw)) == {"a": 1}


def test_clean_json_text_strips_think_tags():
    from backend.app.core.llm_client import _clean_json_text
    raw = '<think>reasoning...</think>\n{"a": 1}'
    assert json.loads(_clean_json_text(raw)) == {"a": 1}


def test_gemini_client_not_configured_raises():
    from backend.app.core.llm_client import GeminiClient, LLMError
    from pydantic import BaseModel

    class S(BaseModel):
        x: str

    client = GeminiClient(api_key="")
    with pytest.raises(LLMError):
        import asyncio
        asyncio.run(client.structured_call("p", "s", S))


def test_ollama_client_implements_protocol():
    from backend.app.core.llm_client import OllamaClient, LLMClient
    client = OllamaClient()
    assert callable(getattr(client, "structured_call", None))
    # Structural check terhadap Protocol
    assert isinstance(client, LLMClient)


def test_get_llm_client_factory():
    from backend.app.core.llm_client import get_llm_client, OllamaClient, GeminiClient
    assert isinstance(get_llm_client("ollama"), OllamaClient)
    assert isinstance(get_llm_client("gemini"), GeminiClient)


def test_json_instruction_contains_schema_keys():
    from backend.app.core.llm_client import _build_json_instruction
    from pydantic import BaseModel

    class S(BaseModel):
        plausibility: str
        evidence_text: str

    instr = _build_json_instruction("sys", S)
    assert "plausibility" in instr
    assert "evidence_text" in instr
    assert "JSON" in instr


@pytest.mark.asyncio
async def test_ollama_structured_call_retries_on_bad_output(monkeypatch):
    """Output JSON rusak → retry dengan feedback → sukses di percobaan ke-2."""
    from backend.app.core.llm_client import OllamaClient
    from pydantic import BaseModel

    class S(BaseModel):
        value: int

    client = OllamaClient()
    calls = []

    async def fake_model_available(model):
        return True

    async def fake_generate_raw(prompt, system_prompt, model, temperature):
        calls.append(prompt)
        if len(calls) == 1:
            return '{"value": "BUKAN_ANGKA"}'  # invalid
        return '{"value": 42}'

    monkeypatch.setattr(client, "model_available", fake_model_available)
    monkeypatch.setattr(client, "_generate_raw", fake_generate_raw)

    result = await client.structured_call("p", "s", S)
    assert result.value == 42
    assert len(calls) == 2
    assert "GAGAL" in calls[1] or "PERCOBAAN" in calls[1]
