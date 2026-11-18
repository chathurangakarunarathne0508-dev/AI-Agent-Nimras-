"""Saved conversations, kept on disk so they survive browser changes and cleared browser data."""
import json
import threading

from . import config

_LOCK = threading.Lock()
ROLES = {"user", "assistant"}


class ChatError(ValueError):
    pass


def _path():
    return config.DATA_DIR / "chats.json"


def load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("convos"), list):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"convos": [], "active": None}


def _clean(c) -> dict:
    if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not isinstance(c.get("messages"), list):
        raise ChatError("Each conversation needs an id and a list of messages.")
    msgs = []
    for m in c["messages"]:
        if not isinstance(m, dict) or m.get("role") not in ROLES or not isinstance(m.get("content"), str):
            raise ChatError("Invalid message in conversation.")
        msg = {"role": m["role"], "content": m["content"]}
        if isinstance(m.get("report"), str):
            msg["report"] = m["report"]
        img = m.get("image")
        if isinstance(img, dict) and isinstance(img.get("url"), str) and img["url"].startswith("/images/"):
            msg["image"] = {"url": img["url"], "prompt": str(img.get("prompt") or "")[:600]}
        msgs.append(msg)
    return {"id": c["id"][:64], "title": str(c.get("title") or "New chat")[:200],
            "updated": c.get("updated") if isinstance(c.get("updated"), (int, float)) else 0,
            "messages": msgs}


def save(data) -> None:
    """Replace the saved conversations with the browser's current list."""
    if not isinstance(data, dict) or not isinstance(data.get("convos"), list):
        raise ChatError("Expected {\"convos\": [...]}.")
    clean = {"convos": [_clean(c) for c in data["convos"]],
             "active": data.get("active") if isinstance(data.get("active"), str) else None}
    path = _path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(clean, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
