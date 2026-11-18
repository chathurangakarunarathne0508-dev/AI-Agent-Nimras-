"""Extract plain text from uploaded documents.

Text formats and .docx use only the standard library. PDF support needs the optional
`pypdf` package (pip install pypdf).
"""
import io
import re
import zipfile
from html.parser import HTMLParser
from pathlib import PurePath
from xml.etree import ElementTree

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".log", ".xml", ".yaml", ".yml", ".rst"}
HTML_EXTENSIONS = {".html", ".htm"}
SHEET_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}
SUPPORTED = sorted(TEXT_EXTENSIONS | HTML_EXTENSIONS | SHEET_EXTENSIONS | {".docx", ".pdf"})

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MAX_XML_BYTES = 100 * 1024 * 1024  # guard against zip bombs


class DocumentError(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    """Return the readable text of a document, or raise DocumentError."""
    ext = PurePath(filename).suffix.lower()
    if ext == ".pdf":
        text = _pdf(data)
    elif ext == ".docx":
        text = _docx(data)
    elif ext in HTML_EXTENSIONS:
        text = html_to_text(_decode(data))
    elif ext in SHEET_EXTENSIONS:
        text = _spreadsheet(data)
    elif ext in TEXT_EXTENSIONS or _looks_like_text(data):
        text = _decode(data)
    else:
        raise DocumentError(
            f"Unsupported file type '{ext or filename}'. Supported: {', '.join(SUPPORTED)}"
        )
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        hint = " It may be a scanned PDF (images only); text recognition (OCR) isn't supported." \
            if ext == ".pdf" else ""
        raise DocumentError(f"No readable text found in {filename}.{hint}")
    return text


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _looks_like_text(data: bytes) -> bool:
    sample = data[:4096]
    return b"\x00" not in sample


def _pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise DocumentError("Reading PDFs needs the pypdf package. Install it with: pip install pypdf")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise DocumentError("This PDF is password-protected.")
        pages = []
        for i, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"[Page {i}]\n{text}")
        return "\n\n".join(pages)
    except DocumentError:
        raise
    except Exception as e:
        raise DocumentError(f"Could not read this PDF: {e}")


def _docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > _MAX_XML_BYTES:
                raise DocumentError("This Word document is too large to read.")
            root = ElementTree.fromstring(z.read(info))
    except DocumentError:
        raise
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        raise DocumentError("This doesn't look like a valid .docx file. (Old .doc files aren't supported; "
                            "save it as .docx or PDF first.)")

    body = root.find(f"{_W}body")
    lines: list[str] = []

    def para_text(p) -> str:
        parts = []
        for el in p.iter():
            if el.tag == f"{_W}t" and el.text:
                parts.append(el.text)
            elif el.tag == f"{_W}tab":
                parts.append("\t")
            elif el.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        return "".join(parts)

    for block in (body if body is not None else []):
        if block.tag == f"{_W}p":
            lines.append(para_text(block))
        elif block.tag == f"{_W}tbl":
            for row in block.iter(f"{_W}tr"):
                cells = [" ".join(para_text(p) for p in tc.iter(f"{_W}p")).strip()
                         for tc in row.iter(f"{_W}tc")]
                lines.append(" | ".join(cells))
            lines.append("")
    return "\n".join(lines)


def _spreadsheet(data: bytes) -> str:
    try:
        import pandas as pd
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    except ImportError:
        raise DocumentError("Reading Excel files needs pandas and openpyxl: pip install pandas openpyxl")
    except Exception as e:
        raise DocumentError(f"Could not read this spreadsheet: {e}")
    return "\n\n".join(f"[Sheet: {name}]\n{df.to_csv(index=False)}" for name, df in sheets.items())


class _TextHTML(HTMLParser):
    _SKIP = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "button"}
    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"}

    def __init__(self):
        super().__init__()
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def html_to_text(src: str) -> str:
    """Readable text of an HTML page, without scripts, menus, headers and footers."""
    p = _TextHTML()
    p.feed(src)
    text = "".join(p.out)
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines()]
    return "\n\n".join(l for l in lines if l)
