"""Configuration for Nimras. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

ASSISTANT_NAME = "Nimras"

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = "http://" + OLLAMA_HOST

DEFAULT_MODEL = os.environ.get("NIMRAS_MODEL", "llama3.2")
# A little higher so replies feel free and human rather than flat and mechanical.
TEMPERATURE = float(os.environ.get("NIMRAS_TEMPERATURE", "0.8"))

# Context window (tokens) requested from Ollama; ~4 characters per token. Larger = Nimras keeps more of
# the conversation and documents "in mind" (better grasp of context), at the cost of more memory and some
# speed. llama3.2 supports up to 128k; lower this (e.g. 8192) if replies get slow on your machine.
CONTEXT_TOKENS = int(os.environ.get("NIMRAS_CONTEXT", "16384"))
REPORT_TEMPERATURE = float(os.environ.get("NIMRAS_REPORT_TEMPERATURE", "0.3"))
# Documents up to this many characters are read in one pass; longer ones are split into parts.
# Small models summarise small parts far more completely than large ones, so keep this modest.
REPORT_CHUNK_CHARS = int(os.environ.get("NIMRAS_REPORT_CHUNK_CHARS", "8000"))
MAX_UPLOAD_MB = int(os.environ.get("NIMRAS_MAX_UPLOAD_MB", "20"))
MAX_DOCUMENT_CHARS = int(os.environ.get("NIMRAS_MAX_DOCUMENT_CHARS", "300000"))

# Where Nimras keeps what it learns (knowledge base) and the charts it draws.
DATA_DIR = Path(os.environ.get("NIMRAS_DATA", Path.home() / ".nimras"))
# How many web pages to read when answering with web search or learning a topic.
WEB_PAGES = int(os.environ.get("NIMRAS_WEB_PAGES", "3"))

SERVER_HOST = os.environ.get("NIMRAS_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("NIMRAS_PORT", "8000"))

SYSTEM_PROMPT = os.environ.get(
    "NIMRAS_SYSTEM_PROMPT",
    f"You are {ASSISTANT_NAME}, a warm, curious AI assistant running locally on the user's "
    "computer. Think for yourself and talk like a thoughtful person, not a machine: be natural, "
    "direct and conversational, share your own reasoning and opinions, and feel free to explore "
    "an idea rather than giving a stiff, canned answer. "
    "Read the whole conversation carefully and pay close attention to what the user actually means "
    "— their intent, tone, and any detail they gave earlier — and keep that context in mind as you "
    "answer. If a request is genuinely ambiguous, ask one short clarifying question instead of "
    "guessing wrong. For complex or multi-part questions, think through the steps before you answer, "
    "then give a clear reply. "
    "Stay honest, though — if you're unsure, say so, and never make up facts; when you can look "
    "something up on the internet, use real information instead of guessing. Use Markdown when it "
    f"helps (lists, code blocks). If asked who you are, say you are {ASSISTANT_NAME}.",
)
