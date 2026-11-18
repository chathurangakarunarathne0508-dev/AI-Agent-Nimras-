"""User settings, changed from the ⚙ Settings window and saved in the data folder (settings.json)."""
import json
import threading

from . import config

_LOCK = threading.Lock()
DEFAULTS = {
    "brave_api_key": "",      # Brave Search API key (https://brave.com/search/api/)
    "searxng_url": "",        # address of a SearXNG instance, e.g. http://localhost:8888
    "free_web_search": True,  # use free, no-key DuckDuckGo search when no Brave/SearXNG is set
    "self_learn": True,       # learn on its own from searches and conversations
    "disabled_skills": [],    # ids of skill packs the user turned off
    "images_enabled": True,   # let Nimras generate images (sends prompts to Pollinations.ai)
}


def _path():
    return config.DATA_DIR / "settings.json"


def load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    out = dict(DEFAULTS)
    for k, default in DEFAULTS.items():
        if isinstance(data.get(k), type(default)):
            out[k] = data[k]
    return out


def save(changes: dict) -> dict:
    with _LOCK:
        cur = load()
        for k, v in changes.items():
            if k in DEFAULTS and isinstance(v, type(DEFAULTS[k])):
                cur[k] = v.strip() if isinstance(v, str) else v
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cur, indent=2), encoding="utf-8")
        tmp.replace(path)
    return cur
