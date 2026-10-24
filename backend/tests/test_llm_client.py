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


# ---------------------------------------------------------------------------
# Cascade lintas-provider: utama (gemini) → backup (ollama) → template di agent
# ---------------------------------------------------------------------------

class _StubLLM:
    """Stub client untuk menguji cascade tanpa jaringan."""

    def __init__(self, name: str, result=None, error: str | None = None):
        self.name = name
        self._result = result
        self._error = error
        self.calls = 0

    async def structured_call(self, prompt, system_prompt, output_schema, model="m", temperature=0.0):
        self.calls += 1
        if self._error is not None:
            from backend.app.core.llm_client import LLMError
            raise LLMError(self._error)
        return self._result

    async def is_available(self) -> bool:
        return self._error is None


from pydantic import BaseModel as _BM


class _S(_BM):
    x: str


@pytest.mark.asyncio
async def test_get_provider_chain_default_gemini_first(monkeypatch):
    monkeypatch.setattr("backend.app.core.llm_client.DEFAULT_PROVIDER", "gemini")
    from backend.app.core.llm_client import get_provider_chain
    assert get_provider_chain() == ["gemini", "ollama"]
    assert get_provider_chain("ollama") == ["ollama", "gemini"]
    # nilai aneh → fallback konservatif ke gemini utama
    assert get_provider_chain("habus") == ["gemini", "ollama"]


@pytest.mark.asyncio
async def test_cascade_uses_primary_when_healthy(monkeypatch):
    import backend.app.core.llm_client as llm_client

    gem = _StubLLM("gemini", _S(x="ok"))
    oll = _StubLLM("ollama", _S(x="jangan_dipakai"))

    def fake_factory(provider: str = "gemini"):
        return gem if provider == "gemini" else oll

    monkeypatch.setattr(llm_client, "get_llm_client", fake_factory)
    monkeypatch.setattr(llm_client, "DEFAULT_PROVIDER", "gemini")

    result = await llm_client._run_llm_with_fallback("p", "s", _S, "m", 0.0)
    assert result.x == "ok"
    assert gem.calls == 1 and oll.calls == 0
    assert llm_client.get_last_provider() == "gemini"
    assert llm_client.resolve_model_name("qwen2.5:3b") == llm_client.GEMINI_MODEL


@pytest.mark.asyncio
async def test_cascade_falls_back_to_ollama(monkeypatch):
    import backend.app.core.llm_client as llm_client

    gem = _StubLLM("gemini", error="GEMINI_API_KEY tidak dikonfigurasi")
    oll = _StubLLM("ollama", _S(x="dari_ollama"))

    def fake_factory(provider: str = "gemini"):
        return gem if provider == "gemini" else oll

    monkeypatch.setattr(llm_client, "get_llm_client", fake_factory)
    monkeypatch.setattr(llm_client, "DEFAULT_PROVIDER", "gemini")

    result = await llm_client._run_llm_with_fallback("p", "s", _S, "m", 0.0)
    assert result.x == "dari_ollama"
    assert gem.calls == 1 and oll.calls == 1
    assert llm_client.get_last_provider() == "ollama"
    # provenance: nama model Ollama yang diminta dipertahankan
    assert llm_client.resolve_model_name("qwen2.5:3b") == "qwen2.5:3b"


@pytest.mark.asyncio
async def test_cascade_all_fail_raises_llm_error(monkeypatch):
    import backend.app.core.llm_client as llm_client

    gem = _StubLLM("gemini", error="quota habis")
    oll = _StubLLM("ollama", error="Ollama down")

    def fake_factory(provider: str = "gemini"):
        return gem if provider == "gemini" else oll

    monkeypatch.setattr(llm_client, "get_llm_client", fake_factory)
    monkeypatch.setattr(llm_client, "DEFAULT_PROVIDER", "gemini")

    with pytest.raises(llm_client.LLMError) as excinfo:
        await llm_client._run_llm_with_fallback("p", "s", _S, "m", 0.0)
    message = str(excinfo.value)
    assert "gemini" in message and "ollama" in message
    assert gem.calls == 1 and oll.calls == 1


@pytest.mark.asyncio
async def test_explicit_provider_skips_cascade(monkeypatch):
    import backend.app.core.llm_client as llm_client

    gem = _StubLLM("gemini", error="JANGAN dipanggil")
    oll = _StubLLM("ollama", _S(x="dari_ollama"))

    def fake_factory(provider: str = "gemini"):
        return gem if provider == "gemini" else oll

    monkeypatch.setattr(llm_client, "get_llm_client", fake_factory)
    monkeypatch.setattr(llm_client, "DEFAULT_PROVIDER", "gemini")

    result = await llm_client._run_llm_with_fallback("p", "s", _S, "m", 0.0, forced_provider="ollama")
    assert result.x == "dari_ollama"
    assert gem.calls == 0 and oll.calls == 1


# ---------------------------------------------------------------------------
# Koersi skema (fix E2E: Gemini mengirim field list sebagai string) + console
# ---------------------------------------------------------------------------

class _ListSchema(_BM):
    signals: list[str]
    ids: list[str]


def test_validate_or_raise_comma_string_becomes_list():
    """GeminiClient menerima field list sebagai STRING — diparse ulang di sini."""
    from backend.app.core.llm_client import _validate_or_raise

    raw = json.dumps({"signals": "duplikat_len, tindakan_tanpa_diagnosis", "ids": "C1, C2"})
    parsed = _validate_or_raise(raw, _ListSchema)
    assert parsed.signals == ["duplikat_len", "tindakan_tanpa_diagnosis"]
    assert parsed.ids == ["C1", "C2"]


def test_validate_or_raise_json_string_and_newline_become_list():
    from backend.app.core.llm_client import _validate_or_raise

    raw = json.dumps({"signals": ["tuntas_lewat_json"], "ids": "e1\ne2"})
    parsed = _validate_or_raise(raw, _ListSchema)
    assert parsed.signals == ["tuntas_lewat_json"]  # list asli tidak diubah
    assert parsed.ids == ["e1", "e2"]


def test_console_safe_survives_unencodable_console(monkeypatch):
    """Windows console cp850 menolak '→' — fallback ASCII, alur cascade tetap jalan."""
    import builtins

    from backend.app.core.llm_client import _console_safe

    real_print = builtins.print
    calls = []

    def broken_console(*args, **kwargs):
        text = args[0] if args else ""
        if any(ord(ch) > 255 for ch in text):
            raise UnicodeEncodeError("charmap", text, 0, 1, "tidak terwakili")
        calls.append(text)
        return real_print(*args, **kwargs)

    monkeypatch.setattr(builtins, "print", broken_console)
    _console_safe("[LLM] gemini gagal → lanjut ollama")  # tidak boleh raise
    assert calls and "→" not in calls[0]
