"""Data fetch tool: HTTP GET a URL and return its readable text content.

Gives subagents access to full page content beyond search snippets. Best-effort
by design: any failure yields a notice string so the task keeps running.
Fetched content is untrusted external data — it is injection-scanned and
delimited before reaching the LLM (CLAUDE.md §9.3).

SSRF defense: only http(s) URLs without credentials, and every address the
hostname resolves to must be globally routable. Known residual risk: a
DNS-rebinding window between the resolve check and the fetch is not closed in
this tier.
"""

from __future__ import annotations

import asyncio
import logging
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.core.constants import (
    DATA_FETCH_MAX_BYTES,
    DATA_FETCH_MAX_CHARS,
    DATA_FETCH_RESULT_CLOSE,
    DATA_FETCH_RESULT_OPEN,
    UNTRUSTED_CONTENT_NOTICE,
)
from app.utils.prompt_guard import is_suspicious
from app.utils.url_guard import resolve_is_public as _resolve_is_public
from app.utils.url_guard import validate_url_shape as _validate_url

logger = logging.getLogger(__name__)

_WITHHELD_NOTICE = "(content withheld: it looked like a prompt-injection attempt)"
_SKIPPED_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "head"})
# Tags whose end implies a paragraph/line break in the extracted text.
_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "li",
        "tr",
        "br",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "table",
        "ul",
        "ol",
        "blockquote",
        "pre",
    }
)


class _TextExtractor(HTMLParser):
    """Dependency-free HTML → plain text (stdlib html.parser)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        lines = (" ".join(line.split()) for line in raw.splitlines())
        return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> str:
    """Extract readable text from HTML, skipping scripts/styles/boilerplate."""
    extractor = _TextExtractor()
    try:
        extractor.feed(html)
        extractor.close()
    except Exception:  # noqa: BLE001 - malformed HTML must not kill the task
        logger.warning("HTML parsing failed; falling back to raw text")
        return html
    return extractor.text()


async def fetch(url: str) -> str:
    """Fetch a URL and return a delimited text block. Never raises."""
    if not settings.data_fetch_enabled:
        return _failure(url, "the data_fetch tool is disabled")
    reason = _validate_url(url)
    if reason is not None:
        return _failure(url, reason)
    hostname = urlsplit(url).hostname or ""
    if not await asyncio.to_thread(_resolve_is_public, hostname):
        return _failure(url, "host is not publicly routable")

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.data_fetch_timeout_seconds,
            headers={"User-Agent": "MaestroAgent/1.0 (+data_fetch tool)"},
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) >= DATA_FETCH_MAX_BYTES:
                        break
    except httpx.HTTPError as exc:
        logger.warning("data_fetch failed for %s", url, exc_info=True)
        return _failure(url, str(exc) or exc.__class__.__name__)

    text = body.decode("utf-8", errors="replace")
    if "html" in content_type:
        text = html_to_text(text)
    text = text.strip()[:DATA_FETCH_MAX_CHARS]
    if not text:
        return _failure(url, "the page contained no readable text")
    # Drop content that looks like a prompt-injection payload (CLAUDE.md §9.3).
    if is_suspicious(text):
        text = _WITHHELD_NOTICE
    return "\n".join(
        [
            DATA_FETCH_RESULT_OPEN,
            f"URL: {url}",
            text,
            DATA_FETCH_RESULT_CLOSE,
            UNTRUSTED_CONTENT_NOTICE,
        ]
    )


def _failure(url: str, reason: str) -> str:
    return (
        f'Could not fetch "{url}": {reason}. '
        "Continue without it and note the limitation."
    )
