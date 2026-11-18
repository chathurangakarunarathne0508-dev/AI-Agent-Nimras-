# Nimras

A local AI assistant powered by [Ollama](https://ollama.com). The AI runs entirely on your machine; the
only things that go online are web searches and pages you ask it to read.

- Modern web UI: searchable chat history grouped by date (rename, download, delete), quick-action cards,
  model picker with an Ollama status light, light/dark mode, streaming replies with a Stop button (or Esc),
  copy buttons, and a collapsible sidebar that works on phones too
- **Saved chats**: conversations are saved on disk (`~/.nimras/chats.json`), so they're still there after
  restarting, switching browsers or clearing browser data. Hover a chat in the sidebar and press ⬇ to
  download it as Markdown
- **Document reports**: attach a file (📎 or drag & drop) and Nimras writes a structured report
- **Data reports with charts**: attach a CSV or Excel file and get charts, a dashboard and exact data
  tables, following the *report-charts* skill
- **Knowledge base** (📚): Nimras remembers what it learns from skills, files and web pages, uses it in
  chat and cites its sources
- **Image generation**: ask Nimras to "draw/create an image of…" and it generates a picture with the free
  [Pollinations.ai](https://pollinations.ai) service and shows it in chat (this one feature sends the prompt
  to that service; turn it off in ⚙ Settings to stay fully local)
- **Answers on its own** from the AI model; optional **web search** (🌐) with a Brave Search API key
- **Skills** (✨): built-in expertise Nimras applies on its own — image-prompt crafting, coding, writing,
  tutoring, translation, math, research and defensive cybersecurity — plus any skill you teach it
- **Mascot**: a chibi mecha robot (`nimras/static/mascot/`, cut from the pose sheet) that acts out what
  Nimras is doing: waves on the welcome screen, thinks, types on a holo-keyboard while searching the web,
  runs with a data cube while reading pages and files, presents the answer, and gives a thumbs up when done
- Terminal chat mode

## Setup

1. Install Ollama and make sure it is running (`ollama serve`, or the Ollama desktop app).
2. Download a model (Nimras uses `llama3.2:1b` by default):
   ```
   ollama pull llama3.2:1b
   ```
3. Install the Python packages used for PDFs, spreadsheets and charts:
   ```
   pip install pypdf pandas openpyxl matplotlib
   ```
   Chat works without them; only the matching features need them.
4. Start Nimras:
   ```
   python -m nimras          # web UI at http://127.0.0.1:8000
   python -m nimras chat     # terminal chat
   ```
   On Windows you can also double-click `start-nimras.bat`.

## Document reports

Supported files: `.pdf`, `.docx`, `.xlsx`, `.csv`, `.txt`, `.md`, `.tsv`, `.json`, `.html`, `.log`, `.xml`,
`.yaml`, `.rst`. Optionally type what the report should focus on before pressing Enter. Finished reports
can be downloaded as a standalone `.html` (charts embedded) or as `.md`.

- Scanned PDFs (images only) can't be read, since there is no OCR. Old `.doc` files aren't supported.
- Long documents are split into parts (about 8,000 characters each), condensed into notes, and the report
  is written from the notes. On a laptop CPU, expect roughly 40 seconds per part.
- Small models like `llama3.2:1b` can miss or mix up details. For more reliable reports use a larger
  model such as `llama3.2` (3B). Always check important figures against the source.

## Data reports and the report-charts skill

CSV and Excel files with numeric columns get a data report. Nimras was taught the **report-charts** skill
(`nimras/skills/report_charts/`), and applies its rules **in code**, so numbers are never estimated by the
language model:

- picks the chart type from the data: line or column for change over time, a sorted bar for comparisons,
  and a donut for shares with 5 parts or fewer. Long category lists are grouped into "Other".
- writes titles that state a finding computed from the data ("North had the highest Sales, 37% of the total")
- draws them in the skill's house style with its own `make_charts.py`, plus a one-page dashboard
- flags missing values and duplicate rows, and appends exact data tables

The model only writes the overview and key findings around these computed facts. To match an earlier
chart's look, put a style file at `~/.nimras/chart_style.json` (same keys as
`skills/report_charts/example_style.json`).

## Skills

Nimras has **skills** — packs of expertise it applies automatically when a message fits. Open **✨ Skills**
in the sidebar to see them, turn any off, or teach it a new one.

Built in: **Image prompt studio** (writes ready-to-paste prompts for image generators — the local text model
can't render images itself), **Coding help**, **Writing & editing**, **Tutor & skill coach** (teaches you any
skill step by step), **Cybersecurity (defensive)**, **Translation & language**, **Math & calculation**,
**Research & fact-finding**, and **Report charts** (used by data reports).

- Nimras picks the fitting skill(s) per message by matching your words; the mascot shows which it's using.
- **Teach a new skill**: give it a name, trigger words and instructions, and it's saved to `<data>/skills/`
  and used from then on. You can delete your own skills; built-in ones can only be switched off.
- Every skill still obeys the safety guard below — no skill can be used to harm a living being. The
  cybersecurity skill is scoped to **defence, learning and authorised testing**; it won't help attack
  systems or accounts you don't own, and malicious hacking requests (malware, breaking into others'
  accounts, stealing data, DDoS) are refused.

## Internet search, self-learning and safety

**Internet search.** Nimras decides by itself when to search: it looks things up when you ask for facts, details
or anything current (news, prices, "latest"…), reads the top pages, and lists them as sources. It answers on its
own for chat, writing and coding. Wikipedia results are skipped. Your search queries are sent to the search service.
Works on both the main workspace and the **Talk 1-on-1** page (toggle with the 🌐 button there).

Search services, in order of preference (set in **⚙ Settings**):
- **DuckDuckGo** — free, no key, **on by default**. Nothing to set up; turn it off to keep Nimras fully local.
- a free [Brave Search API](https://brave.com/search/api/) key, or
- a [SearXNG](https://docs.searxng.org/admin/installation-docker.html) address (free and open source; it can run on
  this computer, e.g. `docker run -p 8888:8080 searxng/searxng`, with `json` added to `search.formats`).

**Self-learning** (on by default; switch in ⚙ Settings). Nimras keeps a local knowledge base
(`~/.nimras/knowledge.json`) and improves on its own. It doesn't retrain the model; it consults its notes.
- **Web pages** it reads for your questions are saved.
- **Learned answers**: an answer built from web pages is saved, so the next time it answers straight from
  memory, faster and without searching. Questions about current things are always searched again.
- **Memories**: "remember that…", "my name is…", "I live in…", and corrections ("actually…") are saved and
  used in every chat.
- **Learning from your feedback**: every reply has a 👍 / 👎. 👍 saves that question-and-answer so Nimras
  reuses it next time (faster, and cited); 👎 makes it forget a learned answer it had saved for that
  question. This is how you teach it which answers were good — the model itself isn't retrained.
- **📚 Knowledge** shows counts of everything learned and lets you remove anything or teach it directly
  (a web address, a topic, or a file).

**Safety guard (always on).** Nimras never helps harm people, animals or any other living being. Requests
about weapons, poisons, chemical/biological agents, violence, cruelty or self-harm are refused kindly, never
searched and never learned (self-harm gets a supportive reply pointing to helplines). Pages and files that
contain harmful instructions are not saved. Blocked items are counted (the harmful text isn't stored). The
guard uses intent patterns, so ordinary questions ("is chocolate poisonous to dogs?") still work; like any
filter it isn't perfect, and the model is also instructed with the same rule.

Other protections: only public websites are opened (except your own SearXNG), pages are read as text and
never treated as instructions, and other websites open in your browser can't send commands to Nimras.
## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `NIMRAS_MODEL` | `llama3.2:1b` | Default Ollama model |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server address |
| `NIMRAS_PORT` | `8000` | Web UI port |
| `NIMRAS_HOST` | `127.0.0.1` | Web UI bind address |
| `NIMRAS_TEMPERATURE` | `0.7` | Sampling temperature |
| `NIMRAS_SYSTEM_PROMPT` | (built in) | Override Nimras' personality |
| `NIMRAS_DATA` | `~/.nimras` | Where knowledge and charts are stored |
| `NIMRAS_BRAVE_API_KEY` | (none) | Brave Search API key (or set it in ⚙ Settings) |
| `NIMRAS_SEARXNG_URL` | (none) | SearXNG address (or set it in ⚙ Settings) |
| `NIMRAS_WEB_PAGES` | `3` | Pages read per web search |
| `NIMRAS_CONTEXT` | `8192` | Context window (tokens) for reports and knowledge-based answers |
| `NIMRAS_REPORT_CHUNK_CHARS` | `8000` | Part size for long documents |
| `NIMRAS_REPORT_TEMPERATURE` | `0.3` | Sampling temperature for reports |
| `NIMRAS_MAX_UPLOAD_MB` | `20` | Largest file you can upload |
| `NIMRAS_MAX_DOCUMENT_CHARS` | `300000` | Text beyond this is ignored |

Example (PowerShell): `$env:NIMRAS_MODEL = "llama3.2"; python -m nimras`

## Terminal commands

`/help`, `/models`, `/model <name>`, `/web auto|on|off`, `/learn <url|topic>`, `/knowledge`, `/forget <id>`,
`/reset`, `/exit`

## Project layout

```
nimras/
  config.py         settings + Nimras' system prompt
  ollama_client.py  streaming client for the Ollama API
  assistant.py      chat answers using the knowledge base and the web; learning
  knowledge.py      knowledge base (passages + BM25 search)
  chats.py          saved conversations (chats.json)
  web.py            internet search (Brave / SearXNG) and page reading
  safety.py         safety guard: never help or learn to harm a living being
  skills_lib.py     skill packs (expertise applied per message) + user-taught skills
  settings.py       settings saved from the ⚙ Settings window
  documents.py      text extraction from PDF, Word, Excel, HTML and text files
  charts.py         applies the report-charts skill: picks charts, computes figures
  report.py         document reports and data reports
  server.py         web server (UI, /api/chat, /api/report, /api/learn, /api/knowledge, /charts)
  cli.py            terminal chat
  skills/           skill packs, each a folder with a SKILL.md
    image_prompt/ coding/ writing/ tutor/ security/ translation/ math/ research/
    report_charts/  also used in code for data reports (make_charts.py, examples)
  static/index.html chat interface
```
