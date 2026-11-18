"""Nimras' skills: reusable expertise packs applied automatically when relevant to a question.

Each skill is a folder with a SKILL.md: a title (# Name), a hidden triggers comment
(<!-- triggers: ... -->) used to match questions, a "**Use when:**" line, and guidance the
model follows. Built-in skills live in nimras/skills/; the user's own skills live in
<data>/skills/ and can be added or removed from the UI.

When a question matches a skill, its guidance is added to the model's instructions, so Nimras
"knows" that skill for that answer. The safety guard still applies to everything.
"""
import re
import threading
import uuid
from pathlib import Path

from . import config, knowledge, settings

BUILTIN_DIR = Path(__file__).parent / "skills"
_LOCK = threading.Lock()
MAX_BODY_CHARS = 1400


def _user_dir() -> Path:
    return config.DATA_DIR / "skills"


def _parse(path: Path, builtin: bool) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    title = next((ln[1:].strip() for ln in text.splitlines() if ln.startswith("# ")), path.parent.name)
    trig = ""
    if m := re.search(r"<!--\s*triggers:\s*(.*?)\s*-->", text, re.S | re.I):
        trig = m.group(1)
    desc = ""
    if m := re.search(r"\*\*Use when:\*\*\s*(.+)", text):
        desc = m.group(1).strip()
    elif m := re.search(r"^---\s*\n.*?^description:\s*(.+?)\s*\n", text, re.S | re.M):
        desc = m.group(1).strip()  # YAML frontmatter (report-charts style)
    # Body given to the model: drop the triggers comment and any YAML frontmatter, keep the rest.
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    body = re.sub(r"^---\s*\n.*?\n---\s*\n", "", body, flags=re.S).strip()
    return {"id": path.parent.name, "name": title, "description": desc,
            "triggers": [t.strip() for t in trig.split(",") if t.strip()],
            "body": body[:MAX_BODY_CHARS], "builtin": builtin}


def all_skills() -> list[dict]:
    """Every skill pack, built-in first, then the user's own."""
    out, seen = [], set()
    for base, builtin in ((BUILTIN_DIR, True), (_user_dir(), False)):
        if not base.is_dir():
            continue
        for folder in sorted(base.iterdir()):
            md = folder / "SKILL.md"
            if folder.is_dir() and md.is_file() and folder.name not in seen:
                if s := _parse(md, builtin):
                    seen.add(folder.name)
                    out.append(s)
    return out


def _summary(s: dict, disabled: set) -> dict:
    return {"id": s["id"], "name": s["name"], "description": s["description"],
            "triggers": s["triggers"], "builtin": s["builtin"], "enabled": s["id"] not in disabled}


def list_skills() -> list[dict]:
    disabled = set(settings.load()["disabled_skills"])
    return [_summary(s, disabled) for s in all_skills()]


def enabled_skills() -> list[dict]:
    disabled = set(settings.load()["disabled_skills"])
    return [s for s in all_skills() if s["id"] not in disabled]


# A few signals that keyword matching misses (arithmetic symbols, code symbols).
_BOOST = [("math", re.compile(r"\d\s*%|\d\s*[+\-*/×÷=]\s*\d|\b\d+\s*(plus|minus|times|divided)\b", re.I)),
          ("coding", re.compile(r"```|\b(def |function |console\.|import |#include|print\()", re.I))]


def select(question: str, limit: int = 2, min_score: int = 3) -> list[dict]:
    """The skills most relevant to a question (by trigger and name/description overlap)."""
    q = set(knowledge.tokens(question))
    if not q:
        return []
    boosted = {sid for sid, rx in _BOOST if rx.search(question)}
    scored = []
    for s in enabled_skills():
        trig = set(knowledge.tokens(" ".join(s["triggers"])))
        desc = set(knowledge.tokens(s["name"] + " " + s["description"]))
        score = 3 * len(q & trig) + len(q & desc) + (min_score if s["id"] in boosted else 0)
        if score >= min_score:
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:limit]]


SKILL_HEADER = ("\n\nYou have the following expertise. When it fits the user's message, apply it; "
                "otherwise ignore it. Follow your core safety rule above all of it.\n")


def guidance(skills: list[dict]) -> str:
    """The text added to the model's instructions for the selected skills."""
    if not skills:
        return ""
    return SKILL_HEADER + "\n\n".join(f"### Skill — {s['name']}\n{s['body']}" for s in skills)


def toggle(skill_id: str, enabled: bool) -> bool:
    if skill_id not in {s["id"] for s in all_skills()}:
        return False
    with _LOCK:
        disabled = set(settings.load()["disabled_skills"])
        disabled.discard(skill_id) if enabled else disabled.add(skill_id)
        settings.save({"disabled_skills": sorted(disabled)})
    return True


_SAFE_NAME = re.compile(r"[^a-z0-9]+")


def create_user_skill(name: str, instructions: str, triggers: str = "") -> dict:
    """Save a skill the user teaches Nimras. Returns its summary."""
    name = (name or "").strip()
    instructions = (instructions or "").strip()
    if len(name) < 2 or len(instructions) < 10:
        raise ValueError("Give the skill a name and some instructions for how to use it.")
    slug = "user-" + _SAFE_NAME.sub("-", name.lower()).strip("-")[:40] or "user-skill"
    with _LOCK:
        folder = _user_dir() / slug
        if folder.exists():
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"
            folder = _user_dir() / slug
        folder.mkdir(parents=True, exist_ok=True)
        trig = triggers.strip() or name
        body = (f"# {name}\n\n<!-- triggers: {trig} -->\n\n**Use when:** {trig}.\n\n"
                f"{instructions}\n")
        (folder / "SKILL.md").write_text(body, encoding="utf-8")
        # A newly added skill should be on, even if an old one with the same id was disabled.
        disabled = set(settings.load()["disabled_skills"])
        if slug in disabled:
            disabled.discard(slug)
            settings.save({"disabled_skills": sorted(disabled)})
    return _summary(_parse(folder / "SKILL.md", False), set())


def delete_user_skill(skill_id: str) -> bool:
    """Remove a user-created skill (built-in skills can only be turned off, not deleted)."""
    folder = _user_dir() / skill_id
    md = folder / "SKILL.md"
    if not (folder.is_dir() and md.is_file()):
        return False
    with _LOCK:
        md.unlink()
        try:
            folder.rmdir()
        except OSError:
            pass
    return True
