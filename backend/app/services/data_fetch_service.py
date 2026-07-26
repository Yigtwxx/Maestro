"""Data fetch tool: retrieve a URL and return its readable text or selected data.

Gives subagents access to full page content beyond search snippets. Best-effort
by design: any failure yields a notice string so the task keeps running.
Fetched content is untrusted external data — it is injection-scanned and
delimited before reaching the LLM (CLAUDE.md §9.3).

Two engines, chosen by ``DATA_FETCH_ENGINE``:

``scrapling`` (default)
    Scrapling's ``AsyncFetcher`` over curl_cffi, which impersonates a real
    browser's TLS/JA3 fingerprint and header order. Anti-bot layers that reject
    a plain httpx request generally let this through. Responses are lxml-parsed,
    so a CSS ``selector`` can pull out just the elements the agent needs instead
    of dumping the whole page into the prompt. An optional browser tier
    (``DATA_FETCH_RENDER_ENABLED``) handles JavaScript-rendered pages; it is off
    by default and degrades silently when no browser binaries are installed.

``httpx``
    The original streaming-GET implementation, retained as a one-env-var
    rollback. Does not support ``selector`` or ``render``.

SSRF defense (static tier): only http(s) URLs without credentials; every address
the hostname resolves to must be globally routable; redirects use libcurl's SAFE
mode, which rejects hops to private/internal addresses; and the final URL is
re-validated after the fetch. Known residual risks: a DNS-rebinding window
between the resolve check and the request is not closed, and the *browser* tier
has neither SAFE-mode redirects nor subresource control — a rendered page issues
requests to arbitrary hosts. That is a second reason rendering is off by default.

Size cap — a known weakness of the scrapling engine, stated plainly. Scrapling
cannot stream: ``Response`` arrives fully read and eagerly lxml-parsed, so
``DATA_FETCH_MAX_BYTES`` can only be enforced *post hoc*, after the bytes are
already in memory. What bounds that path is ``huge_tree=False`` (restoring
libxml2's document-size guard, which Scrapling disables by default), an advisory
``Range`` header, and the request timeout. curl's ``max_recv_speed`` would give
a real ceiling but is unusable: throttling the receive rate desynchronises
nghttp2's flow-control window, so every HTTP/2 request fails with curl error 16
(verified live). Forcing HTTP/1.1 to regain it would break the browser
impersonation this engine exists for. Operators who need a hard mid-stream cap
more than they need anti-bot success should set ``DATA_FETCH_ENGINE=httpx``,
which still enforces the cap while streaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Mapping
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.core.constants import (
    DATA_FETCH_CHALLENGE_MARKERS,
    DATA_FETCH_CHALLENGE_STATUSES,
    DATA_FETCH_ENGINE_HTTPX,
    DATA_FETCH_IGNORED_TAGS,
    DATA_FETCH_IMPERSONATE,
    DATA_FETCH_MATCH_MAX_CHARS,
    DATA_FETCH_MAX_BYTES,
    DATA_FETCH_MAX_CHARS,
    DATA_FETCH_MAX_REDIRECTS,
    DATA_FETCH_RESULT_CLOSE,
    DATA_FETCH_RESULT_OPEN,
    DATA_FETCH_RETRIES,
    DATA_FETCH_SELECTOR_MAX_MATCHES,
    UNTRUSTED_CONTENT_NOTICE,
)
from app.utils.prompt_guard import is_suspicious
from app.utils.url_guard import resolve_is_public as _resolve_is_public
from app.utils.url_guard import validate_url_shape as _validate_url

logger = logging.getLogger(__name__)

_WITHHELD_NOTICE = "(content withheld: it looked like a prompt-injection attempt)"
_SKIPPED_TAGS = frozenset(DATA_FETCH_IGNORED_TAGS)
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
# Selector.__init__ knobs applied to every parsed response. Only the two that
# change Scrapling's defaults are set: huge_tree defaults to True, which
# *disables* libxml2's protection against pathological documents — exactly the
# wrong default for untrusted input — and adaptive would create an on-disk
# SQLite element store. keep_comments/keep_cdata are already False upstream;
# passing keep_cdata explicitly only triggers an lxml deprecation warning.
_SELECTOR_CONFIG = {
    "huge_tree": False,
    "adaptive": False,
}
# How much of a body to scan for a bot-wall marker.
_CHALLENGE_SCAN_CHARS = 2000


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


# --- Scrapling loading ----------------------------------------------------
# Imported lazily: Scrapling's static engine pulls in playwright at module level,
# which costs real time at boot, and a missing install must degrade rather than
# break startup. The module globals double as the monkeypatch seam for tests,
# mirroring how test_web_search_service replaces DDGS.

_static_fetcher: Any | None = None
_stealthy_fetcher: Any | None = None
_import_error: str | None = None
_render_availability: bool | None = None
_render_lock = asyncio.Lock()
_render_semaphore: asyncio.Semaphore | None = None


def _quiet_scrapling_logger() -> None:
    """Stop Scrapling from printing every fetched URL on its own handler.

    Scrapling installs a StreamHandler on the "scrapling" logger at INFO and
    logs one line per request. ``configure_logging`` only clears *root*
    handlers, so that one survives and would emit model-supplied URLs outside
    our configured format (breaking LOG_FORMAT=json).
    """
    scrapling_logger = logging.getLogger("scrapling")
    scrapling_logger.handlers.clear()
    scrapling_logger.propagate = True
    scrapling_logger.setLevel(logging.WARNING)


def _load_static_fetcher() -> Any | None:
    """Import ``AsyncFetcher`` once. Returns None when scrapling is absent."""
    global _static_fetcher, _import_error
    if _static_fetcher is not None or _import_error is not None:
        return _static_fetcher
    try:
        from scrapling.fetchers import AsyncFetcher
    except Exception as exc:  # noqa: BLE001 - any import failure must degrade
        _import_error = str(exc) or exc.__class__.__name__
        logger.warning(
            "scrapling unavailable (%s); data_fetch falls back to httpx",
            _import_error,
        )
        return None
    _quiet_scrapling_logger()
    _static_fetcher = AsyncFetcher
    return _static_fetcher


def _load_stealthy_fetcher() -> Any | None:
    """Import ``StealthyFetcher`` once. Returns None when it is unavailable."""
    global _stealthy_fetcher
    if _stealthy_fetcher is not None:
        return _stealthy_fetcher
    try:
        from scrapling.fetchers import StealthyFetcher
    except Exception:  # noqa: BLE001 - the static tier is still fully usable
        logger.warning("scrapling browser tier unavailable", exc_info=True)
        return None
    _stealthy_fetcher = StealthyFetcher
    return _stealthy_fetcher


def _browser_cache_dirs() -> tuple[Path, ...]:
    """Directories Playwright-family browsers are installed into."""
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if override:
        return (Path(override),)
    home = Path.home()
    return (
        home / ".cache" / "ms-playwright",  # Linux
        home / "AppData" / "Local" / "ms-playwright",  # Windows
        home / "Library" / "Caches" / "ms-playwright",  # macOS
    )


def _probe_browsers() -> bool:
    """Stat-level check for installed browser binaries. Never launches one."""
    from importlib.util import find_spec

    try:
        if find_spec("patchright") is None:
            return False
        scrapling_spec = find_spec("scrapling")
    except (ImportError, ValueError):  # pragma: no cover - defensive
        return False

    # `scrapling install` touches this sentinel next to the package after
    # downloading browsers, so it is the intended opt-in signal.
    if scrapling_spec is not None and scrapling_spec.origin:
        sentinel = (
            Path(scrapling_spec.origin).parent / ".scrapling_dependencies_installed"
        )
        if sentinel.exists():
            return True

    # Browsers installed by hand, without the sentinel.
    return any(
        any(directory.glob("chromium*"))
        for directory in _browser_cache_dirs()
        if directory.is_dir()
    )


async def is_render_available() -> bool:
    """Whether the browser tier can run. Probed once, then cached."""
    global _render_availability
    if not settings.data_fetch_render_enabled:
        return False
    if _render_availability is not None:
        return _render_availability
    async with _render_lock:
        if _render_availability is None:
            _render_availability = await asyncio.to_thread(_probe_browsers)
            if not _render_availability:
                logger.info(
                    "no browser binaries found; data_fetch render tier disabled "
                    "(run `scrapling install` to enable it)"
                )
    return _render_availability


def _disable_render(reason: str) -> None:
    """Turn the browser tier off for this process after a launch failure.

    The probe is a filesystem heuristic; patchright may resolve a different
    browser revision than `scrapling install` fetches. Flipping the cache here
    makes a wrong-positive cost one slow fetch per process, never a task.
    """
    global _render_availability
    _render_availability = False
    logger.warning("data_fetch render tier disabled after failure: %s", reason)


def _get_render_semaphore() -> asyncio.Semaphore:
    """One semaphore per process; a headless browser is 300-500MB of RSS."""
    global _render_semaphore
    if _render_semaphore is None:
        _render_semaphore = asyncio.Semaphore(
            settings.data_fetch_render_max_concurrency
        )
    return _render_semaphore


# --- Response helpers -----------------------------------------------------


def _content_type(headers: Mapping[str, str] | None) -> str:
    """Case-insensitive content-type lookup (header containers vary)."""
    if not headers:
        return ""
    for key, value in headers.items():
        if str(key).lower() == "content-type":
            return str(value).lower()
    return ""


def _looks_challenged(response: Any) -> bool:
    """Whether a response is a bot wall rather than the requested page."""
    if getattr(response, "status", 200) in DATA_FETCH_CHALLENGE_STATUSES:
        return True
    body = getattr(response, "body", b"") or b""
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    head = str(body)[:_CHALLENGE_SCAN_CHARS].lower()
    return any(marker in head for marker in DATA_FETCH_CHALLENGE_MARKERS)


def _extract_matches(response: Any, selector: str) -> list[dict[str, str]] | None:
    """Elements matching ``selector``. None means the selector was invalid."""
    try:
        elements = response.css(selector)
    except Exception:  # noqa: BLE001 - cssselect/lxml raise several types
        return None

    matches: list[dict[str, str]] = []
    for element in list(elements)[:DATA_FETCH_SELECTOR_MAX_MATCHES]:
        try:
            raw_text = element.get_all_text(separator=" ", strip=True)
        except Exception:  # noqa: BLE001 - text nodes lack the full API
            raw_text = str(element)
        entry = {"text": " ".join(str(raw_text).split())[:DATA_FETCH_MATCH_MAX_CHARS]}
        # .attrib returns an empty container on text nodes; element["href"]
        # would raise there instead.
        attributes = getattr(element, "attrib", None)
        href = attributes.get("href") if attributes else None
        if href:
            try:
                absolute = response.urljoin(str(href))
            except Exception:  # noqa: BLE001 - a malformed href is not fatal
                absolute = str(href)
            entry["href"] = str(absolute)[:DATA_FETCH_MATCH_MAX_CHARS]
        matches.append(entry)
    return matches


def _wrap(url: str, header: str | None, payload: str) -> str:
    """Delimited untrusted-content block, the one shape every engine returns."""
    lines = [DATA_FETCH_RESULT_OPEN, f"URL: {url}"]
    if header:
        lines.append(header)
    lines.extend([payload, DATA_FETCH_RESULT_CLOSE, UNTRUSTED_CONTENT_NOTICE])
    return "\n".join(lines)


def _text_block(url: str, text: str) -> str | None:
    """Wrap page text, or None when there was nothing readable."""
    text = text.strip()[:DATA_FETCH_MAX_CHARS]
    if not text:
        return None
    if is_suspicious(text):
        text = _WITHHELD_NOTICE
    return _wrap(url, None, text)


def _selector_block(url: str, selector: str, matches: list[dict[str, str]]) -> str:
    """Wrap selector matches as a JSON array."""
    if not matches:
        return (
            f'No elements matched the CSS selector "{selector}" on {url}. '
            "The page was fetched successfully — retry without a selector to "
            "see its text, then pick a selector from what you see."
        )
    combined = " ".join(entry["text"] for entry in matches)
    if is_suspicious(combined):
        payload = _WITHHELD_NOTICE
    else:
        payload = json.dumps(matches, ensure_ascii=False)[:DATA_FETCH_MAX_CHARS]
    shown = len(matches)
    header = f"Selector: {selector} ({shown} match{'' if shown == 1 else 'es'})"
    return _wrap(url, header, payload)


# --- Public entry point ---------------------------------------------------


async def fetch(url: str, *, selector: str | None = None, render: bool = False) -> str:
    """Fetch a URL and return a delimited block. Never raises.

    ``selector`` returns only the matching elements as a JSON array;
    ``render`` asks for a real browser and is ignored when none is installed.
    """
    if not settings.data_fetch_enabled:
        return _failure(url, "the data_fetch tool is disabled")
    reason = _validate_url(url)
    if reason is not None:
        return _failure(url, reason)
    hostname = urlsplit(url).hostname or ""
    if not await asyncio.to_thread(_resolve_is_public, hostname):
        return _failure(url, "host is not publicly routable")

    if settings.data_fetch_engine == DATA_FETCH_ENGINE_HTTPX:
        return await _fetch_httpx(url, selector)
    fetcher = _load_static_fetcher()
    if fetcher is None:
        return await _fetch_httpx(url, selector)
    return await _fetch_scrapling(url, fetcher, selector=selector, render=render)


async def _fetch_scrapling(
    url: str, fetcher: Any, *, selector: str | None, render: bool
) -> str:
    """Browser tier when asked for and available; otherwise the static tier.

    ``render`` is a hint, never a requirement: with no browser installed — the
    default for this image — the request still goes out over the static tier
    rather than failing, because that tier is the baseline capability, not a
    fallback.
    """
    response: Any = None
    if render and await is_render_available():
        response = await _fetch_rendered(url)

    if response is None:
        try:
            response = await fetcher.get(
                url,
                impersonate=DATA_FETCH_IMPERSONATE,
                stealthy_headers=True,
                timeout=settings.data_fetch_timeout_seconds,
                retries=DATA_FETCH_RETRIES,
                follow_redirects="safe",
                max_redirects=DATA_FETCH_MAX_REDIRECTS,
                # Advisory size cap. Static-file servers honour it and truncate
                # to a 206; HTML servers generally ignore it, which is harmless.
                # Deliberately NOT curl's max_recv_speed: throttling the receive
                # rate desynchronises nghttp2's flow-control window and every
                # HTTP/2 request fails with curl error 16. Verified against a
                # live host — see the module docstring.
                headers={"Range": f"bytes=0-{DATA_FETCH_MAX_BYTES}"},
                selector_config=dict(_SELECTOR_CONFIG),
            )
        except Exception as exc:  # noqa: BLE001 - curl_cffi raises its own types
            logger.warning("data_fetch failed for %s", url, exc_info=True)
            return _failure(url, str(exc) or exc.__class__.__name__)

        # A bot wall is not the page. Retry in a browser when one exists.
        if (
            settings.data_fetch_escalate_on_challenge
            and _looks_challenged(response)
            and await is_render_available()
        ):
            escalated = await _fetch_rendered(url)
            if escalated is not None:
                response = escalated

    return await _finalize(url, response, selector)


async def _fetch_rendered(url: str) -> Any | None:
    """Browser tier. Returns None on any failure; the caller keeps tier 0."""
    stealthy = _load_stealthy_fetcher()
    if stealthy is None:
        _disable_render("StealthyFetcher could not be imported")
        return None
    try:
        async with _get_render_semaphore():
            return await stealthy.async_fetch(
                url,
                headless=True,
                solve_cloudflare=settings.data_fetch_solve_cloudflare,
                network_idle=True,
                disable_resources=True,
                block_ads=True,
                # This tier takes milliseconds; the static tier takes seconds.
                timeout=settings.data_fetch_render_timeout_seconds * 1000,
                selector_config=dict(_SELECTOR_CONFIG),
            )
    except Exception as exc:  # noqa: BLE001 - playwright raises its own types
        _disable_render(str(exc) or exc.__class__.__name__)
        return None


async def _finalize(url: str, response: Any, selector: str | None) -> str:
    """Validate the landed response and turn it into a prompt block."""
    status = getattr(response, "status", 200)
    if status >= 400:
        return _failure(url, f"HTTP {status}")

    # The redirect target is re-checked here, after the request. libcurl's SAFE
    # mode already refuses private-IP hops on the static tier; this catches a
    # libcurl that ignored it, and covers the browser tier, which has no
    # equivalent. It stops the body reaching the LLM — it does not prevent the
    # request that fetched it.
    final_url = str(getattr(response, "url", "") or url)
    if final_url != url:
        if _validate_url(final_url) is not None:
            return _failure(url, "the URL redirected to an unsupported address")
        final_host = urlsplit(final_url).hostname or ""
        if not await asyncio.to_thread(_resolve_is_public, final_host):
            return _failure(url, "the URL redirected to a non-public host")

    body = getattr(response, "body", b"") or b""
    if len(body) > DATA_FETCH_MAX_BYTES:
        return _failure(
            url, f"the response exceeded the {DATA_FETCH_MAX_BYTES}-byte cap"
        )

    if selector:
        matches = _extract_matches(response, selector)
        if matches is None:
            return _failure(url, f'invalid CSS selector "{selector}"')
        return _selector_block(url, selector, matches)

    if "html" in _content_type(getattr(response, "headers", None)):
        try:
            text = str(
                response.get_all_text(
                    separator="\n", strip=True, ignore_tags=DATA_FETCH_IGNORED_TAGS
                )
            )
        except Exception:  # noqa: BLE001 - fall back to the stdlib stripper
            logger.warning("scrapling text extraction failed for %s", url)
            text = html_to_text(_decode(body))
    else:
        # JSON, CSV and plain text must not go through the HTML tree.
        text = _decode(body)

    block = _text_block(url, text)
    if block is None:
        return _failure(url, "the page contained no readable text")
    return block


def _decode(body: bytes | str) -> str:
    return body if isinstance(body, str) else body.decode("utf-8", errors="replace")


async def _fetch_httpx(url: str, selector: str | None) -> str:
    """The pre-Scrapling engine: streaming GET with a mid-stream byte cap.

    Kept intact as the DATA_FETCH_ENGINE=httpx rollback and as the fallback
    when scrapling is not installed. It has no HTML tree, so ``selector`` is
    reported as unavailable rather than silently ignored.
    """
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
    block = _text_block(url, text)
    if block is None:
        return _failure(url, "the page contained no readable text")
    if selector:
        block = (
            f"{block}\n(CSS selectors are unavailable on the current fetch "
            "engine; the full page text is shown instead.)"
        )
    return block


def _failure(url: str, reason: str) -> str:
    return (
        f'Could not fetch "{url}": {reason}. '
        "Continue without it and note the limitation."
    )
