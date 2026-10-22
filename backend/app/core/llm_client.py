"""
LLM Client abstraction (PRD Section 7).

- LLMClient       : Protocol interface — semua agent memanggil LLM lewat interface ini.
- OllamaClient    : jalur utama demo (lokal, tanpa internet).
- GeminiClient    : baseline benchmark & fallback produksi (Gemini API free tier).

Retry logic (AGENTS.md prinsip #2): output yang gagal parse/divalidasi di-retry
maksimal 2x dengan pesan error sebagai feedback, baru LLMError dilempar.
"""
import os
import json
import httpx
from typing import Protocol, Optional, runtime_checkable
from pydantic import BaseModel
from dotenv import load_dotenv
from backend.app.core.errors import DEPENDENCY_UNAVAILABLE_CODE

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")  # "ollama" | "gemini"

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "mistral:7b")

# Per-agent model config (sesuai AGENTS.md)
CLINICAL_MODEL             = os.getenv("CLINICAL_MODEL", "mistral:7b")
REVIEW_MODEL               = os.getenv("REVIEW_MODEL", "deepseek-r1:7b")
REVIEW_MODEL_FALLBACK      = os.getenv("REVIEW_MODEL_FALLBACK", "mistral:7b")
EXPLANATION_MODEL          = os.getenv("EXPLANATION_MODEL", "qwen2.5:7b")
EXPLANATION_MODEL_FALLBACK = os.getenv("EXPLANATION_MODEL_FALLBACK", "mistral:7b")

MAX_RETRIES = 2  # 1 percobaan awal + 2 retry dengan feedback error


class LLMError(Exception):
    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code


# ---------------------------------------------------------------------------
# Helpers JSON
# ---------------------------------------------------------------------------

def _clean_json_text(raw: str) -> str:
    clean = raw.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    if clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    # Strip thinking tags dari deepseek-r1
    if "<think>" in clean:
        clean = clean[clean.rfind("</think>") + 8:].strip()
    return clean.strip()


def _build_json_instruction(system_prompt: str, output_schema: type[BaseModel]) -> str:
    """Instruksi JSON dengan template deskriptif.

    Template menampilkan nama field + tipe (bukan sekadar <str>) — model 7B
    terbukti jauh lebih patuh mengisi konten nyata ketika placeholder deskriptif.
    """
    fields = output_schema.model_fields
    json_template = {}
    for k, v in fields.items():
        ann = v.annotation
        ann_name = getattr(ann, "__name__", None) or str(ann)
        if "list" in ann_name.lower():
            placeholder = f"<list of string - field {k}>"
        elif "int" in ann_name.lower():
            placeholder = f"<integer - field {k}>"
        elif "float" in ann_name.lower() or "double" in ann_name.lower():
            placeholder = f"<number - field {k}>"
        else:
            placeholder = f"<string - field {k}>"
        json_template[k] = placeholder
    template_str = json.dumps(json_template, indent=2, ensure_ascii=False)
    return (
        f"{system_prompt}\n\n"
        f"Kamu HARUS merespons HANYA dalam format JSON yang valid. "
        f"JSON kamu harus persis mengikuti struktur dan keys berikut ini "
        f"(isi setiap field dengan konten NYATA sesuai instruksi, bukan placeholder):\n"
        f"{template_str}\n\n"
        f"JANGAN tambahkan teks, markdown, backticks, atau penjelasan apa pun di luar JSON."
    )


def _validate_or_raise(raw: str, output_schema: type[BaseModel]) -> BaseModel:
    data = json.loads(_clean_json_text(raw))
    return output_schema.model_validate(data)


# ---------------------------------------------------------------------------
# Client implementations
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMClient(Protocol):
    """Interface swappable — PRD Section 7. Semua agent hanya bergantung pada ini."""

    async def structured_call(
        self,
        prompt: str,
        system_prompt: str,
        output_schema: type[BaseModel],
        model: str = DEFAULT_MODEL,
        temperature: float = 0.0,
    ) -> BaseModel: ...


class OllamaClient:
    """Jalur utama development & demo live (lokal via Ollama)."""

    name = "ollama"

    def __init__(self, base_url: str = OLLAMA_BASE_URL, timeout: float = 120.0):
        self.base_url = base_url
        self.timeout = timeout

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            pass
        return []

    async def model_available(self, model: str) -> bool:
        models = await self.list_models()
        # exact match atau prefix match (mis. qwen2.5:7b vs qwen2.5:7b-instruct)
        return any(m.startswith(model.split(":")[0]) for m in models)

    async def get_available_model(self, preferred: str, fallback: str = DEFAULT_MODEL) -> str:
        if await self.model_available(preferred):
            return preferred
        print(f"[LLM] Model '{preferred}' tidak tersedia, fallback ke '{fallback}'")
        return fallback

    async def _generate_raw(self, prompt: str, system_prompt: str, model: str, temperature: float) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
                "num_predict": 1024,
                "top_p": 0.9,
                "seed": 42,
                "num_gpu": int(os.getenv("OLLAMA_NUM_GPU", "99")),
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                return response.json().get("response", "")
            except httpx.HTTPStatusError as e:
                raise LLMError(f"HTTP error dari Ollama: {e}", DEPENDENCY_UNAVAILABLE_CODE)
            except httpx.RequestError as e:
                raise LLMError(f"Koneksi ke Ollama gagal: {e}", DEPENDENCY_UNAVAILABLE_CODE)

    async def structured_call(
        self,
        prompt: str,
        system_prompt: str,
        output_schema: type[BaseModel],
        model: str = DEFAULT_MODEL,
        temperature: float = 0.0,
    ) -> BaseModel:
        if not await self.model_available(model):
            raise LLMError(
                f"Model '{model}' tidak tersedia di Ollama",
                DEPENDENCY_UNAVAILABLE_CODE,
            )

        augmented = _build_json_instruction(system_prompt, output_schema)
        last_error = ""
        raw = ""
        for attempt in range(1 + MAX_RETRIES):
            retry_note = ""
            if attempt > 0:
                retry_note = (
                    f"\n\nPERCOBAAN {attempt + 1}: Respons sebelumnya GAGAL divalidasi.\n"
                    f"Error: {last_error}\n"
                    f"Perbaiki dan kembalikan HANYA JSON valid sesuai struktur."
                )
            raw = await self._generate_raw(prompt + retry_note, augmented, model, temperature)
            try:
                return _validate_or_raise(raw, output_schema)
            except Exception as e:
                last_error = str(e)[:300]
        raise LLMError(f"Gagal parse output LLM setelah {1 + MAX_RETRIES} percobaan: {last_error}\nRaw: {raw[:400]}")


class GeminiClient:
    """Baseline benchmark & production-path narrative (Gemini API free tier)."""

    name = "gemini"

    def __init__(self, api_key: str = GEMINI_API_KEY, model: str = GEMINI_MODEL):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def structured_call(
        self,
        prompt: str,
        system_prompt: str,
        output_schema: type[BaseModel],
        model: str = DEFAULT_MODEL,  # diabaikan — Gemini punya model sendiri
        temperature: float = 0.0,
    ) -> BaseModel:
        if not self.is_configured():
            raise LLMError("GEMINI_API_KEY tidak dikonfigurasi di .env", DEPENDENCY_UNAVAILABLE_CODE)

        fields = output_schema.model_fields
        props = {}
        for k, v in fields.items():
            ann = v.annotation
            ann_name = getattr(ann, "__name__", None) or str(ann)
            t = "STRING"
            if "int" in ann_name.lower():
                t = "INTEGER"
            elif "float" in ann_name.lower() or "double" in ann_name.lower():
                t = "NUMBER"
            elif "bool" in ann_name.lower():
                t = "BOOLEAN"
            elif "list" in ann_name.lower():
                t = "STRING"  # disederhanakan: minta string dipisah koma lalu diparse
            props[k] = {"type": t}

        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\n{prompt}"}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": props,
                    "required": list(props.keys()),
                },
            },
        }
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"

        last_error = ""
        for attempt in range(1 + MAX_RETRIES):
            body = dict(payload)
            if attempt > 0:
                body["contents"].append({"parts": [{"text": f"Respons sebelumnya gagal divalidasi: {last_error}. Perbaiki dan kembalikan JSON valid saja."}]})
            async with httpx.AsyncClient(timeout=60.0) as client:
                try:
                    resp = await client.post(url, json=body)
                    resp.raise_for_status()
                    data = resp.json()
                    raw = data["candidates"][0]["content"]["parts"][0]["text"]
                    return _validate_or_raise(raw, output_schema)
                except LLMError:
                    raise
                except Exception as e:
                    last_error = str(e)[:300]
        raise LLMError(f"GeminiClient gagal setelah {1 + MAX_RETRIES} percobaan: {last_error}")


# ---------------------------------------------------------------------------
# Module-level default client + backward-compatible functions
# ---------------------------------------------------------------------------

_ollama_client = OllamaClient()
_gemini_client = GeminiClient()


def get_llm_client(provider: str = DEFAULT_PROVIDER) -> LLMClient:
    """Factory sesuai PRD Section 7 — demo=ollama, benchmark/production-path=gemini."""
    if provider == "gemini":
        return _gemini_client
    return _ollama_client


async def get_available_model(preferred: str, fallback: str = DEFAULT_MODEL) -> str:
    return await _ollama_client.get_available_model(preferred, fallback)


async def structured_completion(
    prompt: str,
    system_prompt: str,
    output_schema: type[BaseModel],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    provider: str = DEFAULT_PROVIDER,
) -> BaseModel:
    """Backward-compatible entry point — route ke client sesuai provider."""
    client = get_llm_client(provider)
    return await client.structured_call(prompt, system_prompt, output_schema, model, temperature)
