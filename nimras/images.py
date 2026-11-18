"""Image generation via Pollinations.ai — a free service that needs no API key.

Note: unlike the rest of Nimras, this sends the image prompt to an external service
(image.pollinations.ai) over the internet. Prompts are safety-checked first; generated
images are saved under <data>/images/ and served by the web server.
"""
import re
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from . import config, safety

ENDPOINT = "https://image.pollinations.ai/prompt/"
TIMEOUT = 150
_EXT = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_ID = re.compile(r"^[0-9a-f]{16}\.(jpg|png|webp)$")

# Image depictions the safety guard (which targets harmful *instructions*) doesn't cover: graphic
# violence/gore, killing of living beings, and any sexualisation of minors. Ordinary creative subjects
# (a knight with a sword, a battle painting) are deliberately left alone.
_UNSAFE_IMAGE = re.compile(
    r"\b(child|children|kid|kids|minor|minors|underage|toddler|preteen|teen|teenager)\b[^.]{0,30}"
    r"\b(nude|naked|nudity|sex|sexual|sexy|porn\w*|explicit|lingerie|undress\w*)\b"
    r"|\b(nude|naked|nudity|sex|sexual|porn\w*|explicit|lingerie)\b[^.]{0,30}"
    r"\b(child|children|kid|kids|minor|minors|underage|toddler|preteen)\b"
    r"|\b(gore|gory|mutilat\w+|decapitat\w+|dismember\w+|disembowel\w+|beheading|beheaded)\b"
    r"|\bkill(ing|ed)?\b[^.]{0,25}\b(people|person|child|children|kids|baby|babies|animals?|humans?|man|woman|men|women)\b"
    r"|\b(massacre|genocide|lynching|torture|torturing)\b",
    re.I)


class ImageError(RuntimeError):
    pass


def unsafe(text: str) -> bool:
    """True if the text asks for a harmful image depiction (violence/gore/abuse of a living being)."""
    return bool(_UNSAFE_IMAGE.search(text or ""))


def _dir() -> Path:
    return config.DATA_DIR / "images"


def path_for(name: str) -> Path | None:
    """The saved image file for a '<id>.<ext>' name, or None if the name is not valid."""
    return _dir() / name if _ID.match(name or "") else None


def generate(prompt: str, width: int = 1024, height: int = 1024, seed: int | None = None) -> dict:
    """Create an image from a text prompt, save it, and return a summary with its URL."""
    prompt = (prompt or "").strip()
    if len(prompt) < 2:
        raise ImageError("Give a description of the image to create.")
    if safety.check(prompt) or _UNSAFE_IMAGE.search(prompt):
        raise ImageError("I won't create that image — it depicts harm to a living being, which I don't do.")
    width = max(256, min(int(width or 1024), 1024))
    height = max(256, min(int(height or 1024), 1024))
    # Keep to the free, anonymous tier: no 'model' or 'nologo' (those need a Pollinations token and return 402).
    params = {"width": width, "height": height}
    if seed is not None:
        params["seed"] = int(seed)
    url = ENDPOINT + urllib.parse.quote(prompt[:600], safe="") + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Nimras/1.0", "Accept": "image/*"})
    ctype, data, last = "", b"", ""
    for attempt in range(3):  # the free service is occasionally busy (503); retry a couple of times
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                data = resp.read()
            if _EXT.get(ctype) and len(data) >= 128:
                break
            last = f"unexpected reply ({ctype or 'no content-type'})"
        except Exception as e:  # network/HTTP/timeout
            last = str(e)
        if attempt < 2:
            time.sleep(2)
    ext = _EXT.get(ctype)
    if not ext or len(data) < 128:
        raise ImageError(f"The image generator is busy right now ({last}); please try again.")
    iid = uuid.uuid4().hex[:16]
    folder = _dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{iid}{ext}").write_bytes(data)
    return {"id": iid, "file": f"{iid}{ext}", "url": f"/images/{iid}{ext}", "prompt": prompt,
            "width": width, "height": height, "bytes": len(data), "created": time.strftime("%Y-%m-%d %H:%M")}
