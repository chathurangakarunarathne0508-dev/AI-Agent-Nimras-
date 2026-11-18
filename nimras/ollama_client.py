"""Minimal Ollama client using only the Python standard library."""
import json
import urllib.error
import urllib.request
from typing import Iterator

from . import config


class OllamaError(RuntimeError):
    pass


def _request(path: str, payload: dict | None = None, timeout: float = 600):
    url = f"{config.OLLAMA_HOST}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode()).get("error", str(e))
        except Exception:
            detail = str(e)
        raise OllamaError(detail) from e
    except urllib.error.URLError as e:
        raise OllamaError(
            f"Cannot reach Ollama at {config.OLLAMA_HOST}. Is it running? (try: ollama serve)"
        ) from e


def list_models() -> list[str]:
    with _request("/api/tags", timeout=10) as resp:
        data = json.loads(resp.read().decode())
    return sorted(m["name"] for m in data.get("models", []))


def build_messages(history: list[dict]) -> list[dict]:
    """Prepend Nimras' system prompt and keep only valid chat turns."""
    msgs = [{"role": "system", "content": config.SYSTEM_PROMPT}]
    for m in history:
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            msgs.append({"role": m["role"], "content": m["content"]})
    return msgs


def stream_chat(history: list[dict], model: str | None = None) -> Iterator[str]:
    """Yield response text chunks from Ollama as they are generated."""
    return stream_messages(build_messages(history), model, {"temperature": config.TEMPERATURE})


def complete(messages: list[dict], model: str | None = None, options: dict | None = None) -> str:
    """Return the full response for raw messages (no Nimras system prompt added)."""
    return "".join(stream_messages(messages, model, options))


def stream_messages(messages: list[dict], model: str | None = None,
                    options: dict | None = None) -> Iterator[str]:
    """Stream a response for raw messages, passed to Ollama as-is."""
    payload = {
        "model": model or config.DEFAULT_MODEL,
        "messages": messages,
        "stream": True,
        "options": options or {},
    }
    with _request("/api/chat", payload) as resp:
        for line in resp:
            if not line.strip():
                continue
            chunk = json.loads(line)
            if "error" in chunk:
                raise OllamaError(chunk["error"])
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content
            if chunk.get("done"):
                break
