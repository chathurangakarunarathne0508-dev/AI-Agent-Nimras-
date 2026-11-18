"""Generate a structured report from a document's text.

Short documents are sent to the model in one pass. Longer ones are split into parts,
each part is condensed into notes, and the report is written from the combined notes.
"""
from typing import Iterator

from . import config
from .ollama_client import complete, stream_messages

REPORT_SYSTEM = (
    "You are a careful analyst who writes clear, well-organised reports from documents. "
    "Use only information found in the provided material. Never invent facts, numbers, "
    "names or dates. Copy figures exactly as written; do not calculate totals, differences "
    "or percentage changes yourself. If something is unclear or missing, say so. "
    "A short document deserves a short report: never pad it, and never write placeholders "
    "such as [insert ...]. "
    "End your answer after the last section."
)

REPORT_TEMPLATE = """Write a report about the document "{name}" in Markdown, using exactly these sections:

## Overview
One short paragraph: what the document is and its purpose.

## Key Points
Up to 8 bullet points with the most important information. A short document needs only a few.

## Details
The main topics, findings or arguments, each under its own ### sub-heading.

## Numbers and Dates
Bullet list of important figures, amounts, dates and deadlines. Write "None found." if there are none.

## Conclusions and Recommendations
What the document concludes, and any actions, risks or next steps it mentions.
{focus}
Here is the {kind}:

<<<
{text}
>>>"""

NOTES_PROMPT = """Below is part {i} of {n} of the document "{name}".
Write concise bullet-point notes covering every important fact, figure, name, date,
finding and conclusion in this part. Keep exact numbers. Do not add anything that is not in the text.

<<<
{text}
>>>"""


NOTES_MAX_TOKENS = 700
REPORT_MAX_TOKENS = 2000


DATA_PROMPT = """The file "{name}" is a data table. These facts were computed exactly from it by code:

{facts}

Verified chart findings:
{findings}

Data quality notes:
{warnings}

Write a short report in Markdown with exactly these sections:

## Overview
Two or three sentences on what the data covers.

## Key Findings
3 to 6 bullet points. Use only numbers given above, copied exactly. Do not calculate anything new.

## Things to Check
One bullet per data quality note above, or "No issues found." if there are none.
{focus}
Stop after the Things to Check section."""


def generate_data_report(name: str, df, instructions: str = "",
                         model: str | None = None) -> Iterator[dict]:
    """Report on a data table: code computes figures and draws charts (report-charts skill),
    the model writes only the narrative, and exact tables and charts are appended by code."""
    from . import charts

    yield {"status": "Checking the data…"}
    p = charts.plan(df, name)
    drawn, chart_error = [], ""
    yield {"status": f"Drawing {len(p['charts'])} chart(s)…"}
    try:
        drawn = charts.render(p)
    except charts.DataError as e:
        chart_error = str(e)

    findings = "\n".join(f"- {c['takeaway']}" for c in p["charts"] if c["type"] != "dashboard")
    warnings = "\n".join(f"- {w}" for w in p["warnings"]) or "- None."
    focus = f"\nThe reader asked you to focus on: {instructions.strip()}\n" if instructions.strip() else ""
    yield {"status": "Writing the report…"}
    msgs = [
        {"role": "system", "content": REPORT_SYSTEM},
        {"role": "user", "content": DATA_PROMPT.format(
            name=name, facts="\n\n".join(p["facts"]), findings=findings, warnings=warnings, focus=focus)},
    ]
    for piece in stream_messages(msgs, model, _options(800)):
        yield {"content": piece}

    tail = ["\n\n## Charts\n"]
    if chart_error:
        tail.append(f"Charts couldn't be drawn: {chart_error}\n")
    for c in drawn:
        tail.append(f"![{c['title']}]({c['url']})\n\n{c['takeaway']}\n")
    tail.append("\n## Data Tables\n\n*Computed directly from the file.*\n\n" + "\n\n".join(p["facts"]) + "\n")
    yield {"content": "\n".join(tail)}


def _options(max_tokens: int) -> dict:
    # num_predict caps the output: small models can otherwise loop on repetitive input forever.
    return {"temperature": config.REPORT_TEMPERATURE, "num_ctx": config.CONTEXT_TOKENS,
            "num_predict": max_tokens, "repeat_penalty": 1.15}


def split_text(text: str, size: int) -> list[str]:
    """Split text into pieces of at most `size` characters, preferring paragraph breaks."""
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        while len(para) > size:  # a single very long paragraph
            cut = para.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:cut])
            para = para[cut:].lstrip()
        if current and len(current) + len(para) + 2 > size:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current.strip():
        chunks.append(current)
    return chunks


def generate_report(name: str, text: str, instructions: str = "",
                    model: str | None = None) -> Iterator[dict]:
    """Yield progress events: {"status": str} while working, then {"content": str} chunks."""
    if len(text) > config.MAX_DOCUMENT_CHARS:
        yield {"status": f"Document is very long; using the first {config.MAX_DOCUMENT_CHARS:,} characters."}
        text = text[: config.MAX_DOCUMENT_CHARS]

    size = config.REPORT_CHUNK_CHARS
    kind = "document"
    round_no = 0
    while len(text) > size:
        round_no += 1
        parts = split_text(text, size)
        notes = []
        for i, part in enumerate(parts, 1):
            label = "Reading" if round_no == 1 else "Condensing notes"
            yield {"status": f"{label}: part {i} of {len(parts)}…"}
            msgs = [
                {"role": "system", "content": REPORT_SYSTEM},
                {"role": "user", "content": NOTES_PROMPT.format(i=i, n=len(parts), name=name, text=part)},
            ]
            notes.append(f"### Part {i}\n{complete(msgs, model, _options(NOTES_MAX_TOKENS)).strip()}")
        text = "\n\n".join(notes)
        kind = "set of notes taken from the document, part by part"
        if round_no >= 4:  # notes refuse to shrink; trim rather than loop forever
            text = text[:size]
            break

    focus = f"\nThe reader asked you to focus on: {instructions.strip()}\n" if instructions.strip() else ""
    yield {"status": "Writing the report…"}
    msgs = [
        {"role": "system", "content": REPORT_SYSTEM},
        {"role": "user", "content": REPORT_TEMPLATE.format(name=name, focus=focus, kind=kind, text=text)},
    ]
    for piece in stream_messages(msgs, model, _options(REPORT_MAX_TOKENS)):
        yield {"content": piece}
