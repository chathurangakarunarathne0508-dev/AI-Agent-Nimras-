"""Terminal chat with Nimras."""
from . import assistant, config, knowledge, web
from .ollama_client import OllamaError, list_models

HELP = """Commands:
  /help              show this help
  /models            list installed Ollama models
  /model <name>      switch model
  /web auto|on|off   auto: search when a question needs facts or current details (default)
  /learn <url|topic> learn from a web page, or research a topic on the web
  /knowledge         list what Nimras has learned
  /forget <id>       remove something from the knowledge base
  /reset             start a new conversation
  /exit              quit"""


def _run_learn(arg: str) -> None:
    kwargs = {"url": arg} if arg.startswith(("http://", "https://")) else {"topic": arg}
    try:
        for evt in assistant.learn(**kwargs):
            if "status" in evt:
                print(f"  {evt['status']}")
            for s in evt.get("learned", []):
                print(f"  Learned: {s['title']}  (id {s['id']})")
    except web.WebError as e:
        print(f"Error: {e}")


def main():
    model = config.DEFAULT_MODEL
    web_mode = "auto"
    history: list[dict] = []
    knowledge.ensure_builtin()
    print(f"{config.ASSISTANT_NAME} (model: {model}) - type /help for commands.\n")

    while True:
        try:
            text = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return
        if not text:
            continue

        if text.startswith("/"):
            cmd, _, arg = text.partition(" ")
            arg = arg.strip()
            if cmd in ("/exit", "/quit"):
                print("Goodbye!")
                return
            elif cmd == "/help":
                print(HELP)
            elif cmd == "/reset":
                history.clear()
                print("Conversation cleared.")
            elif cmd == "/models":
                try:
                    print("\n".join(list_models()) or "No models installed. Try: ollama pull llama3.2:1b")
                except OllamaError as e:
                    print(f"Error: {e}")
            elif cmd == "/model" and arg:
                model = arg
                print(f"Switched to {model}.")
            elif cmd == "/web":
                if arg.lower() in ("auto", "on", "off"):
                    web_mode = arg.lower()
                if not web.search_provider():
                    print("Web search isn't set up: add a Brave Search key or SearXNG address in the web UI's "
                          "⚙ Settings (or set NIMRAS_BRAVE_API_KEY). I'll answer on my own.")
                print(f"Web search mode: {web_mode} ({web.search_provider() or 'no search service'}).")
            elif cmd == "/learn" and arg:
                _run_learn(arg)
            elif cmd == "/knowledge":
                for s in knowledge.list_sources():
                    print(f"  [{s['id']}] ({s['kind']}) {s['title']}  {s['url']}")
            elif cmd == "/forget" and arg:
                print("Forgotten." if knowledge.delete(arg) else "No source with that id.")
            else:
                print("Unknown command. Type /help.")
            continue

        history.append({"role": "user", "content": text})
        reply = ""
        started = False
        try:
            for evt in assistant.answer(history, model, web_mode=web_mode):
                if "status" in evt and not started:
                    print(f"  ({evt['status']})")
                for s in evt.get("learned", []):
                    print(f"  (learned: {s['title']})")
                if "content" in evt:
                    if not started:
                        print(f"{config.ASSISTANT_NAME} > ", end="", flush=True)
                        started = True
                    reply += evt["content"]
                    print(evt["content"], end="", flush=True)
            print("\n")
            history.append({"role": "assistant", "content": reply})
        except KeyboardInterrupt:
            print("\n[stopped]\n")
            if reply:
                history.append({"role": "assistant", "content": reply})
        except OllamaError as e:
            print(f"\nError: {e}\n")
            history.pop()


if __name__ == "__main__":
    main()
