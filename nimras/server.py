"""Web server for Nimras: serves the chat UI, chat (with knowledge + web), reports, charts and learning."""
import base64
import binascii
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from urllib.parse import urlsplit

from . import assistant, charts, chats, config, images, knowledge, settings, skills_lib
from .documents import DocumentError, extract_text
from .ollama_client import OllamaError, list_models
from .report import generate_data_report, generate_report
from . import web
from .web import WebError

STATIC_DIR = Path(__file__).parent / "static"
MASCOT_PATH = re.compile(r"^/mascot/([a-z]+)\.png$")
IMAGE_PATH = re.compile(r"^/images/([0-9a-f]{16}\.(?:jpg|png|webp))$")
CHART_PATH = re.compile(r"^/charts/([0-9a-f]{32})/([A-Za-z0-9_.-]+\.png)$")
_IMG_CTYPE = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _settings_view() -> dict:
    """Settings for the UI. The API key itself is never sent back, only its last 4 characters."""
    s = settings.load()
    key = web.BRAVE_API_KEY or s["brave_api_key"]
    return {"provider": web.search_provider(), "brave_key_set": bool(key),
            "brave_key_hint": ("…" + key[-4:]) if key else "", "brave_from_env": bool(web.BRAVE_API_KEY),
            "searxng_url": s["searxng_url"], "self_learn": s["self_learn"],
            "free_web_search": s["free_web_search"], "images_enabled": s["images_enabled"],
            "stats": knowledge.stats()}


class Handler(BaseHTTPRequestHandler):
    server_version = "Nimras/1.0"

    def log_message(self, fmt, *args):  # quieter logs
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj) -> None:
        self._send(status, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (STATIC_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path in ("/talk", "/talk.html"):
            self._send(200, (STATIC_DIR / "talk.html").read_bytes(), "text/html; charset=utf-8")
        elif m := MASCOT_PATH.match(self.path):
            path = STATIC_DIR / "mascot" / f"{m.group(1)}.png"
            if path.is_file():
                self._send(200, path.read_bytes(), "image/png", {"Cache-Control": "max-age=86400"})
            else:
                self._json(404, {"error": "Not found"})
        elif self.path == "/api/models":
            info = {"default": config.DEFAULT_MODEL, "name": config.ASSISTANT_NAME,
                    "max_upload_mb": config.MAX_UPLOAD_MB, "web_search": web.search_provider()}
            try:
                self._json(200, {"models": list_models(), **info})
            except OllamaError as e:
                self._json(502, {"error": str(e), "models": [], **info})
        elif self.path == "/api/knowledge":
            self._json(200, {"sources": knowledge.list_sources(), "stats": knowledge.stats()})
        elif self.path == "/api/settings":
            self._json(200, _settings_view())
        elif self.path == "/api/skills":
            self._json(200, {"skills": skills_lib.list_skills()})
        elif self.path == "/api/chats":
            self._json(200, chats.load())
        elif m := IMAGE_PATH.match(self.path):
            path = images.path_for(m.group(1))
            if path and path.is_file():
                self._send(200, path.read_bytes(), _IMG_CTYPE[path.suffix], {"Cache-Control": "max-age=86400"})
            else:
                self._json(404, {"error": "Image not found."})
        elif m := CHART_PATH.match(self.path):
            path = config.DATA_DIR / "charts" / m.group(1) / m.group(2)
            if path.is_file():
                self._send(200, path.read_bytes(), "image/png", {"Cache-Control": "max-age=86400"})
            else:
                self._json(404, {"error": "Chart not found (it may have been deleted)."})
        else:
            self._json(404, {"error": "Not found"})

    def _same_origin(self) -> bool:
        """Block other websites open in the browser from changing Nimras (cross-site request forgery)."""
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host", ""):
            self._json(403, {"error": "Requests from other websites are not allowed."})
            return False
        return True

    def do_DELETE(self):
        if not self._same_origin():
            return
        if m := re.match(r"^/api/knowledge/([\w-]+)$", self.path):
            ok = knowledge.delete(m.group(1))
            return self._json(200 if ok else 404, {"deleted": ok})
        if m := re.match(r"^/api/skills/([\w-]+)$", self.path):
            ok = skills_lib.delete_user_skill(m.group(1))
            return self._json(200 if ok else 404, {"deleted": ok})
        self._json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path not in ("/api/chat", "/api/report", "/api/learn", "/api/chats", "/api/settings",
                              "/api/skills", "/api/feedback", "/api/image"):
            return self._json(404, {"error": "Not found"})
        if not self._same_origin():
            return
        if self.headers.get_content_type() != "application/json":
            return self._json(415, {"error": "Send JSON (Content-Type: application/json)."})
        length = int(self.headers.get("Content-Length") or 0)
        # base64 inflates uploads by ~4/3; allow some headroom for the JSON wrapper.
        if length > config.MAX_UPLOAD_MB * 1024 * 1024 * 4 // 3 + 64 * 1024:
            return self._json(413, {"error": f"File too large (limit {config.MAX_UPLOAD_MB} MB)."})
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "Invalid JSON"})

        if self.path == "/api/chats":
            try:
                chats.save(req)
            except chats.ChatError as e:
                return self._json(400, {"error": str(e)})
            return self._json(200, {"saved": True})

        if self.path == "/api/skills":
            if isinstance(req.get("id"), str) and isinstance(req.get("enabled"), bool):
                ok = skills_lib.toggle(req["id"], req["enabled"])
                return self._json(200 if ok else 404, {"skills": skills_lib.list_skills(), "ok": ok})
            try:  # create a user skill
                skills_lib.create_user_skill(str(req.get("name") or ""), str(req.get("instructions") or ""),
                                             str(req.get("triggers") or ""))
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            return self._json(200, {"skills": skills_lib.list_skills()})

        if self.path == "/api/image":
            if not settings.load().get("images_enabled", True):
                return self._json(403, {"error": "Image generation is turned off in Settings."})
            try:
                img = images.generate(str(req.get("prompt") or ""), req.get("width") or 1024,
                                      req.get("height") or 1024, req.get("seed"))
            except images.ImageError as e:
                return self._json(400, {"error": str(e)})
            return self._json(200, img)

        if self.path == "/api/feedback":
            out = assistant.feedback(str(req.get("question") or ""), str(req.get("answer") or ""),
                                     str(req.get("rating") or ""))
            return self._json(200 if out.get("ok") else 400, out)

        if self.path == "/api/settings":
            changes = {}
            if isinstance(req.get("brave_api_key"), str):
                changes["brave_api_key"] = req["brave_api_key"]
            if isinstance(req.get("searxng_url"), str):
                u = req["searxng_url"].strip()
                if u and not re.match(r"^https?://[^\s/]+", u):
                    return self._json(400, {"error": "The SearXNG address must start with http:// or https://"})
                changes["searxng_url"] = u
            if isinstance(req.get("self_learn"), bool):
                changes["self_learn"] = req["self_learn"]
            if isinstance(req.get("free_web_search"), bool):
                changes["free_web_search"] = req["free_web_search"]
            if isinstance(req.get("images_enabled"), bool):
                changes["images_enabled"] = req["images_enabled"]
            settings.save(changes)
            out = _settings_view()
            if req.get("test"):
                out["test"] = web.test_search()
            return self._json(200, out)

        if self.path == "/api/chat":
            mode = req.get("web")
            if isinstance(mode, bool):
                mode = "on" if mode else "off"
            if mode not in ("auto", "on", "off"):
                mode = "auto"
            return self._stream(assistant.answer(req.get("messages") or [], req.get("model"), web_mode=mode))

        filename = str(req.get("filename") or "")
        try:
            data = base64.b64decode(req.get("data") or "", validate=True)
        except (ValueError, binascii.Error):
            return self._json(400, {"error": "Upload was corrupted; please try again."})

        if self.path == "/api/learn":
            url, topic = str(req.get("url") or "").strip(), str(req.get("topic") or "").strip()
            if not (url or topic or filename):
                return self._json(400, {"error": "Give a web address, a topic or a file to learn from."})
            return self._stream(assistant.learn(url=url, topic=topic, filename=filename, data=data))

        # /api/report
        filename = filename or "document.txt"
        instructions, model = str(req.get("instructions") or ""), req.get("model")
        if charts.is_table(filename):
            try:
                df = charts.load_table(filename, data)
                charts.analyse(df)  # raises DataError if there's nothing numeric to chart
                print(f"Data report requested for {filename} ({len(df):,} rows)")
                return self._stream(generate_data_report(filename, df, instructions, model))
            except charts.DataError as e:
                print(f"{filename}: not chartable ({e}); writing a text report instead")
        try:
            text = extract_text(filename, data)
        except DocumentError as e:
            return self._json(400, {"error": str(e)})
        print(f"Report requested for {filename} ({len(text):,} characters of text)")
        self._stream(generate_report(filename, text, instructions, model))

    def _stream(self, events):
        """Send newline-delimited JSON events; connection closes when done (HTTP/1.0)."""
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(obj):
            self.wfile.write((json.dumps(obj) + "\n").encode())
            self.wfile.flush()

        try:
            try:
                for evt in events:
                    emit(evt)
                emit({"done": True})
            except (OllamaError, WebError, DocumentError, charts.DataError) as e:
                emit({"error": str(e)})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # client pressed Stop


def main():
    knowledge.ensure_builtin()
    httpd = ThreadingHTTPServer((config.SERVER_HOST, config.SERVER_PORT), Handler)
    print(f"{config.ASSISTANT_NAME} is running at http://{config.SERVER_HOST}:{config.SERVER_PORT}")
    print(f"Ollama: {config.OLLAMA_HOST}  |  default model: {config.DEFAULT_MODEL}")
    print(f"Knowledge and charts are kept in {config.DATA_DIR}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nGoodbye!")


if __name__ == "__main__":
    main()
