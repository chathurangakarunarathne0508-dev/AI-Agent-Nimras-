"""Entry point: `python -m nimras` (web UI) or `python -m nimras chat` (terminal)."""
import sys

if len(sys.argv) > 1 and sys.argv[1] == "chat":
    from .cli import main
else:
    from .server import main

main()
