"""Nimras' knowledge base: what it has learned from skills, files and web pages.

Sources are split into short passages and stored as JSON in the data folder. When you chat,
the passages most relevant to your question are found with BM25 keyword search (no extra
model needed) and given to the model as reference notes, with citations.
"""
import json
import math
import re
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

from . import config
from .report import split_text

PASSAGE_CHARS = 1000
MAX_PASSAGES_PER_SOURCE = 80
_LOCK = threading.RLock()
_STOP = set("""a an and are as at be been but by can could did do does for from had has have he her his how i
if in into is it its me my no not of on or our she should so than that the their them then there these they
this to was we were what when where which who why will with would you your about also any just more most
other some such only very tell explain please""".split())

BUILTIN_SKILLS = [
    {"id": "skill-report-charts", "title": "Skill: report charts (choosing and styling report charts)",
     "path": Path(__file__).parent / "skills" / "report_charts" / "SKILL.md"},
]


def _db_path() -> Path:
    return config.DATA_DIR / "knowledge.json"


def _load() -> dict:
    try:
        return json.loads(_db_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sources": [], "dismissed": []}


def _save(db: dict) -> None:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _stem(w: str) -> str:
    """Very light stemming so 'charts' matches 'chart' and 'colours' matches 'colour'."""
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def keywords(text: str) -> str:
    """A question boiled down to search keywords: 'What is Sigiriya?' -> 'Sigiriya'."""
    words = [w for w in re.findall(r"[\w'-]+", text) if w.lower() not in _STOP]
    return " ".join(words) or text


def tokens(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1 and w not in _STOP]


def add_source(title: str, text: str, url: str = "", kind: str = "document",
               source_id: str | None = None) -> dict | None:
    """Store a source (replacing an earlier copy of the same URL/id). Returns its summary."""
    text = (text or "").strip()
    if not text:
        return None
    # Split at Markdown headings first so every passage starts with its own section title.
    sections = [s.strip() for s in re.split(r"\n(?=#{1,4} )", text) if s.strip()]
    passages = [p for s in sections for p in split_text(s, PASSAGE_CHARS)][:MAX_PASSAGES_PER_SOURCE]
    with _LOCK:
        db = _load()
        db["sources"] = [s for s in db["sources"]
                         if not ((url and s.get("url") == url) or (source_id and s["id"] == source_id))]
        src = {"id": source_id or uuid.uuid4().hex[:12], "title": (title or url or "Untitled")[:200],
               "url": url, "kind": kind, "added": time.strftime("%Y-%m-%d %H:%M"),
               "chars": len(text), "passages": passages}
        db["sources"].append(src)
        if source_id in db.get("dismissed", []):
            db["dismissed"].remove(source_id)
        _save(db)
    return _summary(src)


def _summary(s: dict) -> dict:
    return {k: v for k, v in s.items() if k != "passages"} | {"passages": len(s["passages"])}


def list_sources() -> list[dict]:
    return [_summary(s) for s in reversed(_load()["sources"])]


def delete(source_id: str) -> bool:
    with _LOCK:
        db = _load()
        before = len(db["sources"])
        db["sources"] = [s for s in db["sources"] if s["id"] != source_id]
        if source_id.startswith("skill-"):  # don't re-add a built-in skill the user removed
            db.setdefault("dismissed", []).append(source_id)
        _save(db)
        return len(db["sources"]) < before


def ensure_builtin() -> None:
    """Load the skills Nimras was taught into the knowledge base (once)."""
    with _LOCK:
        db = _load()
        have = {s["id"] for s in db["sources"]} | set(db.get("dismissed", []))
    for skill in BUILTIN_SKILLS:
        if skill["id"] not in have and skill["path"].exists():
            add_source(skill["title"], skill["path"].read_text(encoding="utf-8"),
                       kind="skill", source_id=skill["id"])


def search(query: str, k: int = 4, source_ids: list[str] | None = None,
           min_coverage: float = 0.5) -> list[dict]:
    """Best-matching passages for a query (BM25). Requires a share of query words to match."""
    q = set(tokens(query))
    if not q:
        return []
    docs = []
    for s in _load()["sources"]:
        if source_ids is not None and s["id"] not in source_ids:
            continue
        for p in s["passages"]:
            docs.append((s, p, Counter(tokens(s["title"] + " " + p))))
    if not docs:
        return []
    n = len(docs)
    avg_len = sum(sum(tf.values()) for *_, tf in docs) / n or 1
    df = Counter()
    for *_, tf in docs:
        df.update(set(tf) & q)
    need = max(1, math.ceil(len(q) * min_coverage))
    scored = []
    for s, p, tf in docs:
        matched = [w for w in q if tf[w]]
        if len(matched) < need:
            continue
        length = sum(tf.values())
        score = sum(math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                    * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * length / avg_len)) for w in matched)
        scored.append((score, s, p))
    scored.sort(key=lambda x: -x[0])
    return [{"source_id": s["id"], "title": s["title"], "url": s.get("url", ""), "kind": s["kind"],
             "text": p, "score": round(sc, 2)} for sc, s, p in scored[:k]]


def memories(limit: int = 25) -> list[str]:
    """What the user asked Nimras to remember, newest last (always given to the model)."""
    mems = [s for s in _load()["sources"] if s["kind"] == "memory"]
    return [" ".join(s["passages"]) for s in mems[-limit:]]


def forget_learned(question: str) -> int:
    """Remove learned answers saved for a question (used when the user marks a reply unhelpful)."""
    q = set(tokens(question))
    if not q:
        return 0
    with _LOCK:
        db = _load()
        keep, removed = [], 0
        for s in db["sources"]:
            if s["kind"] == "insight" and s["title"].lower().startswith("learned answer:"):
                overlap = q & set(tokens(" ".join(s["passages"])))
                if len(overlap) >= max(1, round(len(q) * 0.6)):
                    removed += 1
                    continue
            keep.append(s)
        if removed:
            db["sources"] = keep
            _save(db)
    return removed


def record_blocked(kind: str, where: str) -> None:
    """Count something the safety guard refused to search, answer or learn (the harmful text itself is not kept)."""
    with _LOCK:
        db = _load()
        log = db.setdefault("blocked", [])
        log.append({"kind": kind, "where": where, "at": time.strftime("%Y-%m-%d %H:%M")})
        db["blocked"] = log[-200:]
        db["blocked_total"] = db.get("blocked_total", 0) + 1
        _save(db)


def stats() -> dict:
    """How much Nimras has learned, by kind, and how much it refused to learn."""
    db = _load()
    counts = Counter(s["kind"] for s in db["sources"])
    return {"by_kind": dict(counts), "total": len(db["sources"]),
            "passages": sum(len(s["passages"]) for s in db["sources"]),
            "blocked": db.get("blocked_total", 0)}


def first_passages(source_ids: list[str], per_source: int = 1) -> list[dict]:
    """Fallback when nothing matches well: the opening passages of the given sources."""
    out = []
    for s in _load()["sources"]:
        if s["id"] in source_ids:
            out += [{"source_id": s["id"], "title": s["title"], "url": s.get("url", ""), "kind": s["kind"],
                     "text": p, "score": 0} for p in s["passages"][:per_source]]
    return out
