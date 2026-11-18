"""World Wide Web access: search and reading pages as plain text.

Search uses services that allow programs: the Brave Search API (free key) or a SearXNG instance
(free, open source, can run on this computer), set in ⚙ Settings or via NIMRAS_BRAVE_API_KEY /
NIMRAS_SEARXNG_URL. Without one there is no web search and Nimras answers from its own model.
Wikipedia results are skipped. Any public web
address can still be read directly when the user asks. Only public http(s) addresses are fetched, and pages are
treated as text, never run as code.
"""
import ipaddress
import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html import unescape

from . import settings
from .documents import DocumentError, extract_text, html_to_text

USER_AGENT = "Nimras/1.0 (personal local AI assistant; python-urllib)"
# DuckDuckGo's HTML endpoint expects a browser-like client; this UA carries no personal data.
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
BRAVE_API_KEY = os.environ.get("NIMRAS_BRAVE_API_KEY", "").strip()
MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_PAGE_CHARS = 60_000


class WebError(RuntimeError):
    pass


def _check_public(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise WebError(f"Only http(s) web addresses can be opened: {url}")
    try:
        infos = socket.getaddrinfo(parts.hostname, None)
    except socket.gaierror:
        raise WebError(f"Couldn't find the website {parts.hostname}.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise WebError(f"{parts.hostname} is a private/local address; only public websites are allowed.")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirect)


def _get(url: str, timeout: float = 20, headers: dict | None = None, allow_private: bool = False):
    """Fetch a URL. Only public addresses, unless allow_private (used for the user's own SearXNG)."""
    if not allow_private:
        _check_public(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en;q=0.9",
                                               **(headers or {})})
    try:
        resp = (urllib.request.urlopen if allow_private else _opener.open)(req, timeout=timeout)
        body = resp.read(MAX_PAGE_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise WebError(f"{url} returned HTTP {e.code}.")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise WebError(f"Couldn't open {url}: {reason}")
    return resp, body[:MAX_PAGE_BYTES]


# Results from these sites are skipped: the user wants answers that don't come from Wikipedia.
SKIP_DOMAINS = ("wikipedia.org", "wikiwand.com")


def _providers() -> tuple[str, str]:
    """(Brave API key, SearXNG address) from the environment or the ⚙ Settings window."""
    s = settings.load()
    brave = BRAVE_API_KEY or s["brave_api_key"]
    searx = (os.environ.get("NIMRAS_SEARXNG_URL", "").strip() or s["searxng_url"]).rstrip("/")
    return brave, searx


def _free_search_on() -> bool:
    """Whether the free, no-key DuckDuckGo search is enabled (the default)."""
    return bool(settings.load().get("free_web_search", True))


def search_provider() -> str:
    """The web search service in use, or "" when none is set up (Nimras then answers on its own)."""
    brave, searx = _providers()
    return "Brave Search" if brave else "SearXNG" if searx else "DuckDuckGo" if _free_search_on() else ""


def _json(url: str, headers: dict | None = None, allow_private: bool = False) -> dict:
    _, body = _get(url, headers=headers, allow_private=allow_private)
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        raise WebError("The search service sent an unreadable reply.")


def _brave(query: str, n: int, key: str) -> list[dict]:
    try:
        data = _json("https://api.search.brave.com/res/v1/web/search?"
                     + urllib.parse.urlencode({"q": query, "count": min(20, n)}),
                     {"Accept": "application/json", "X-Subscription-Token": key})
    except WebError as e:
        if "HTTP 401" in str(e) or "HTTP 403" in str(e) or "HTTP 422" in str(e):
            raise WebError("Brave Search rejected the API key. Check it in ⚙ Settings.")
        if "HTTP 429" in str(e):
            raise WebError("Brave Search limit reached for now (too many searches). Try again later.")
        raise
    return [{"title": r.get("title", ""), "url": r["url"],
             "snippet": unescape(re.sub(r"<[^>]+>", "", r.get("description", "")))}
            for r in data.get("web", {}).get("results", []) if r.get("url")]


def _searxng(query: str, n: int, base: str) -> list[dict]:
    # The user's own SearXNG often runs on this computer or the local network, so private addresses are allowed.
    try:
        data = _json(f"{base}/search?" + urllib.parse.urlencode({"q": query, "format": "json", "language": "en"}),
                     {"Accept": "application/json"}, allow_private=True)
    except WebError as e:
        if "HTTP 403" in str(e):
            raise WebError("SearXNG refused JSON results. Add 'json' to search.formats in its settings.yml.")
        raise
    return [{"title": r.get("title", ""), "url": r["url"], "snippet": r.get("content", "") or ""}
            for r in data.get("results", []) if str(r.get("url", "")).startswith(("http://", "https://"))]


def _ddg_real(href: str) -> str:
    """DuckDuckGo wraps results as //duckduckgo.com/l/?uddg=<real url>; unwrap it."""
    if href.startswith("//"):
        href = "https:" + href
    parts = urllib.parse.urlsplit(href)
    if parts.netloc.endswith("duckduckgo.com") and parts.path.startswith("/l/"):
        return urllib.parse.parse_qs(parts.query).get("uddg", [""])[0]
    return href if parts.scheme in ("http", "https") else ""


def _duckduckgo(query: str, n: int) -> list[dict]:
    """Free, no-key search via DuckDuckGo's HTML endpoint. Queries are sent to DuckDuckGo."""
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query, "kl": "wt-wt"})
    try:
        _, body = _get(url, headers={"User-Agent": BROWSER_UA})
    except WebError as e:
        raise WebError(f"Free web search (DuckDuckGo) is unavailable right now ({e}).")
    html = body.decode("utf-8", "replace")
    links = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
    snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)
    strip = lambda t: unescape(" ".join(re.sub(r"<[^>]+>", "", t).split()))
    out = []
    for i, (href, title) in enumerate(links):
        real = _ddg_real(href)
        if real:
            out.append({"title": strip(title), "url": real, "snippet": strip(snips[i]) if i < len(snips) else ""})
        if len(out) >= n:
            break
    return out


def _skipped(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in SKIP_DOMAINS)


def search(query: str, max_results: int = 6) -> list[dict]:
    """Return [{title, url, snippet}] from the configured search service (Brave Search or SearXNG)."""
    brave, searx = _providers()
    if brave:
        results = _brave(query, max_results + 4, brave)
    elif searx:
        results = _searxng(query, max_results + 4, searx)
    elif _free_search_on():
        results = _duckduckgo(query, max_results + 4)
    else:
        raise WebError("Web search is turned off. Turn on free web search in ⚙ Settings, or add a "
                       "Brave Search API key or a SearXNG address.")
    seen, out = set(), []
    for r in results:
        if _skipped(r["url"]) or r["url"] in seen:
            continue
        seen.add(r["url"])
        out.append(r)
    return out[:max_results]


def test_search() -> dict:
    """Run a small search to check the settings work."""
    provider = search_provider()
    if not provider:
        return {"ok": False, "provider": "", "message": "No search service is set up."}
    try:
        n = len(search("weather forecast", 3))
        return {"ok": n > 0, "provider": provider,
                "message": f"{provider} works: {n} results for a test search." if n else f"{provider} returned no results."}
    except WebError as e:
        return {"ok": False, "provider": provider, "message": str(e)}


def _wikipedia(url: str) -> dict | None:
    """Clean article text from Wikipedia's API instead of scraping the page."""
    parts = urllib.parse.urlsplit(url)
    if not (parts.netloc.endswith(".wikipedia.org") and parts.path.startswith("/wiki/")):
        return None
    title = urllib.parse.unquote(parts.path[len("/wiki/"):])
    data = _json(f"https://{parts.netloc}/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1,
         "titles": title, "format": "json", "utf8": 1}))
    page = next(iter(data.get("query", {}).get("pages", {}).values()), {})
    text = page.get("extract", "")
    if not text:
        return None
    text = re.sub(r"\n*={2,} *(See also|References|External links|Further reading|Notes|Bibliography) *={2,}[\s\S]*$",
                  "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return {"title": f"{page.get('title', title)} - Wikipedia", "url": url, "text": text[:MAX_PAGE_CHARS]}


def fetch(url: str) -> dict:
    """Download a page and return {title, url, text}."""
    if wiki := _wikipedia(url):
        return wiki
    resp, body = _get(url)
    ctype = (resp.headers.get_content_type() or "").lower()
    final_url = resp.geturl() or url
    title = ""
    if "html" in ctype or ctype == "text/plain" or not ctype:
        src = body.decode(resp.headers.get_content_charset() or "utf-8", "replace")
        if "html" in ctype or "<html" in src[:2000].lower():
            m = re.search(r"<title[^>]*>(.*?)</title>", src, re.S | re.I)
            title = " ".join(unescape(m.group(1)).split()) if m else ""
            text = html_to_text(src)
        else:
            text = src
    elif ctype == "application/pdf":
        try:
            text = extract_text("page.pdf", body)
        except DocumentError as e:
            raise WebError(str(e))
    else:
        raise WebError(f"{url} is a {ctype} file, which Nimras can't read.")
    # Keep paragraphs that read like prose, dropping menu fragments and cookie banners.
    paras = [p for p in text.split("\n\n") if len(p) >= 60 or (len(p.split()) >= 6 and p.rstrip()[-1:] in ".:?!")]
    text = "\n\n".join(paras)[:MAX_PAGE_CHARS]
    if len(text) < 200:
        raise WebError(f"{url} didn't have enough readable text.")
    return {"title": title or urllib.parse.urlsplit(final_url).netloc, "url": final_url, "text": text}
