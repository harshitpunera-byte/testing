import json
import os
import time
from typing import Any, Dict
from urllib import error, request

from dotenv import load_dotenv


load_dotenv()


def _normalize_ollama_url(raw_url: str) -> str:
    url = raw_url.rstrip("/")

    if url.endswith("/api/chat"):
        return url
    if url.endswith("/api"):
        return f"{url}/chat"
    return f"{url}/api/chat"


LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower().strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o").strip()

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b").strip()
OLLAMA_EXTRACTION_MODEL = os.getenv("OLLAMA_EXTRACTION_MODEL", OLLAMA_MODEL).strip()
OLLAMA_REASONING_MODEL = os.getenv("OLLAMA_REASONING_MODEL", OLLAMA_MODEL).strip()
OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_FALLBACK_MODEL", "").strip()
OLLAMA_BASE_URL = _normalize_ollama_url(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip())
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))

_ollama_backoff_until = 0.0
_ollama_backoff_reason = ""


def _unique_non_empty(values: list[str]) -> list[str]:
    seen = set()
    result = []

    for value in values:
        normalized = (value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)

    return result


def _ollama_models_for_task(task: str) -> list[str]:
    if task == "extraction":
        return _unique_non_empty([OLLAMA_EXTRACTION_MODEL, OLLAMA_FALLBACK_MODEL, OLLAMA_MODEL])
    if task == "reasoning":
        return _unique_non_empty([OLLAMA_REASONING_MODEL, OLLAMA_FALLBACK_MODEL, OLLAMA_MODEL])
    return _unique_non_empty([OLLAMA_MODEL, OLLAMA_FALLBACK_MODEL])


def _default_value_for_field(field_schema: Dict[str, Any]):
    field_type = field_schema.get("type")

    if field_type == "array":
        return []

    if field_type == "object":
        return {}

    if field_type in {"string", "integer", "number", "boolean"}:
        return None

    any_of = field_schema.get("anyOf")
    if isinstance(any_of, list):
        for option in any_of:
            if option.get("type") == "array":
                return []
        return None

    return None


def _fallback_from_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return {}

    return {
        key: _default_value_for_field(field_schema if isinstance(field_schema, dict) else {})
        for key, field_schema in properties.items()
    }


def _coerce_to_json_object(raw: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")

    if start != -1 and end != -1 and end > start:
        maybe_json = raw[start : end + 1]
        try:
            parsed = json.loads(maybe_json)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    raise ValueError(f"Failed to extract valid JSON from LLM: {raw[:100]}...")
def _set_ollama_backoff(seconds: int, reason: str, log_message: str) -> None:
    global _ollama_backoff_until, _ollama_backoff_reason

    now = time.time()
    if now >= _ollama_backoff_until or reason != _ollama_backoff_reason:
        print(log_message)

    _ollama_backoff_until = now + seconds
    _ollama_backoff_reason = reason


def _backoff_ollama_after_failure(exc: Exception) -> None:
    message = str(exc).lower()

    if "http error" in message:
        _set_ollama_backoff(30, "http error", "Ollama HTTP error, backing off briefly.")
        return

    if "unavailable" in message or "temporarily skipped" in message:
        _set_ollama_backoff(60, "service unavailable", f"Ollama unavailable at {OLLAMA_BASE_URL}, backing off briefly.")
        return

    _set_ollama_backoff(30, "request failed", "Ollama call failed, backing off briefly.")


def _ollama_request(payload: dict, *, model_name: str) -> dict:
    if time.time() < _ollama_backoff_until:
        raise RuntimeError(f"Ollama temporarily skipped: {_ollama_backoff_reason}")

    payload = dict(payload)
    payload["model"] = model_name
    req = request.Request(
        OLLAMA_BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        if exc.code == 404:
            raise RuntimeError(
                error_body
                or f"Ollama model '{model_name}' missing or endpoint unavailable"
            ) from exc
        raise RuntimeError(error_body or f"Ollama HTTP error {exc.code}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Ollama unavailable: {exc.reason}") from exc
    except Exception as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc


def _openai_request(payload: dict) -> dict:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured")

    # Using ensure_ascii=True to avoid latin-1 encoding issues in headers/body
    try:
        body_str = json.dumps(payload, ensure_ascii=True)
        data_bytes = body_str.encode("ascii")
    except Exception as exc:
        # Fallback to UTF-8 if something goes wrong, though ASCII should cover everything due to escaping
        data_bytes = json.dumps(payload).encode("utf-8")

    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=data_bytes,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )

    try:
        # OpenAI usually takes less time than 90s, but we'll use 60s for safety
        with request.urlopen(req, timeout=60) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(error_body or f"OpenAI HTTP error {exc.code}") from exc
    except Exception as exc:
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc


def _extract_ollama_content(parsed_response: dict) -> str:
    raw_content = (
        parsed_response.get("message", {}).get("content")
        or parsed_response.get("response")
        or ""
    )

    if not raw_content:
        raise RuntimeError("Ollama returned an empty response")

    return raw_content


def _call_ollama_json(prompt: str, schema: dict, task: str = "default", max_retries: int = 3) -> str:
    payload = {
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON matching the supplied schema. Do not include markdown or commentary.",
            },
            {
                "role": "user",
                "content": f"{prompt}\n\nJSON schema:\n{json.dumps(schema, ensure_ascii=True)}",
            },
        ],
        "stream": False,
        "format": schema,
        "options": {
            "temperature": 0,
        },
    }

    last_error = None

    for attempt in range(max_retries):
        for model_name in _ollama_models_for_task(task):
            try:
                parsed_response = _ollama_request(payload, model_name=model_name)
                raw_content = _extract_ollama_content(parsed_response)
                return json.dumps(_coerce_to_json_object(raw_content, schema))
            except Exception as exc:
                last_error = exc
                print(f"Ollama model '{model_name}' failed/hallucinated for {task} on attempt {attempt+1}: {exc}")
                
        if attempt < max_retries - 1:
            print(f"Retrying JSON extraction (attempt {attempt+2}/{max_retries})...")
            time.sleep(1)

    if last_error:
        _backoff_ollama_after_failure(last_error)
        raise last_error

    raise RuntimeError("No Ollama model configured")


def _call_ollama_text(prompt: str, task: str = "default") -> str:
    payload = {
        "messages": [
            {
                "role": "system",
                "content": "Answer only from the provided context. If the context is insufficient, say that clearly.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "stream": False,
        "options": {
            "temperature": 0,
        },
    }

    last_error = None

    for model_name in _ollama_models_for_task(task):
        try:
            parsed_response = _ollama_request(payload, model_name=model_name)
            raw_content = _extract_ollama_content(parsed_response)
            return raw_content.strip()
        except Exception as exc:
            last_error = exc
            print(f"Ollama model '{model_name}' failed for {task}, trying next option.")

    if last_error:
        _backoff_ollama_after_failure(last_error)
        raise last_error

    raise RuntimeError("No Ollama model configured")


def _call_openai_json(prompt: str, schema: dict) -> str:
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON matching the supplied schema. Do not include markdown or commentary.",
            },
            {
                "role": "user",
                "content": f"{prompt}\n\nJSON schema:\n{json.dumps(schema, ensure_ascii=True)}",
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    
    parsed = _openai_request(payload)
    content = parsed.get("choices", [{}])[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError("OpenAI returned an empty JSON response")
        
    return json.dumps(_coerce_to_json_object(content, schema))


def _call_openai_text(prompt: str) -> str:
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Recruitment and Tender Analysis Expert. "
                    "Provide a helpful, direct, and concise answer based on the provided context. "
                    "If a list is requested, provide it in Markdown format. "
                    "Trust the structured analysis provided in the context."
                )
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0,
    }


    parsed = _openai_request(payload)
    content = parsed.get("choices", [{}])[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError("OpenAI returned an empty text response")
        
    return content.strip()


def llm_json_extract(prompt: str, schema: dict, task: str = "extraction") -> str:
    """
    Call the configured LLM provider (OpenAI or Ollama) and return a raw JSON string.
    """
    if LLM_PROVIDER == "openai":
        try:
            return _call_openai_json(prompt, schema)
        except Exception as exc:
            import traceback
            print(f"OpenAI JSON extraction failed for task '{task}': {exc}")
            traceback.print_exc()
            return json.dumps(_fallback_from_schema(schema))

    # Default to Ollama
    try:
        return _call_ollama_json(prompt, schema, task=task)
    except Exception as exc:
        import traceback
        print(f"Ollama JSON extraction failed for task '{task}': {exc}")
        traceback.print_exc()
        return json.dumps(_fallback_from_schema(schema))


def llm_text_answer(prompt: str, task: str = "reasoning") -> str:
    if LLM_PROVIDER == "openai":
        try:
            return _call_openai_text(prompt)
        except Exception as exc:
            print(f"OpenAI text-answer failed: {exc}")
            return ""

    # Default to Ollama
    try:
        return _call_ollama_text(prompt, task=task)
    except Exception as exc:
        print(f"Ollama text-answer unavailable: {exc}")
        return ""
