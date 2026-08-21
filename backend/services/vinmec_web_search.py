"""Strict, public-only Vinmec search/fetch adapter for Agent V2.

This is the sole HTTP boundary for BUILD-8. It never receives patient context,
does not follow redirects, and validates every initial and discovered URL before
network I/O. Returned page text remains untrusted evidence for the Agent layer.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

ALLOWED_VINMEC_HOSTS = frozenset({"vinmec.com", "www.vinmec.com"})
VINMEC_SEARCH_URL = "https://www.vinmec.com/vie/tim-kiem/"
MAX_RESPONSE_CHARS = 1_000_000


class VinmecWebError(RuntimeError):
    """Safe, normalized failure at the allowlisted web boundary."""


@dataclass(frozen=True)
class VinmecHttpResponse:
    url: str
    status_code: int
    headers: Mapping[str, str]
    text: str


class VinmecHttpTransport(Protocol):
    def get(self, url: str, *, params: Mapping[str, str] | None, timeout_seconds: float) -> VinmecHttpResponse: ...


class HttpxVinmecTransport:
    """No-redirect HTTP client; only this module may import an HTTP client."""

    def get(self, url: str, *, params: Mapping[str, str] | None, timeout_seconds: float) -> VinmecHttpResponse:
        try:
            response = httpx.get(url, params=params, timeout=timeout_seconds, follow_redirects=False)
        except httpx.TimeoutException as exc:
            raise VinmecWebError("VINMEC_WEB_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise VinmecWebError("VINMEC_WEB_UNAVAILABLE") from exc
        return VinmecHttpResponse(
            url=str(response.url),
            status_code=response.status_code,
            headers=dict(response.headers),
            text=response.text[:MAX_RESPONSE_CHARS],
        )


@dataclass(frozen=True)
class VinmecSourceDocument:
    title: str
    url: str
    excerpt: str
    content: str
    injection_detected: bool = False


class _PageExtractor(HTMLParser):
    """Conservative text/link extraction without executing page content."""

    _SUPPRESSED = frozenset({"script", "style", "noscript", "svg", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.description: str | None = None
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._suppressed_depth = 0
        self._in_title = False
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value or "" for name, value in attrs}
        if tag in self._SUPPRESSED:
            self._suppressed_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta" and values.get("name", "").lower() == "description":
            self.description = values.get("content") or self.description
        if tag == "a" and self._suppressed_depth == 0:
            self._anchor_href = values.get("href") or None
            self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SUPPRESSED and self._suppressed_depth:
            self._suppressed_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._anchor_href:
            self.links.append((self._anchor_href, " ".join(self._anchor_text)))
            self._anchor_href = None
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value or self._suppressed_depth:
            return
        if self._in_title:
            self.title_parts.append(value)
        self.text_parts.append(value)
        if self._anchor_href:
            self._anchor_text.append(value)


_PII_PATTERNS = (
    re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", re.IGNORECASE),
    re.compile(r"(?<!\d)(?:\+?84|0)[\s.-]?(?:\d[\s.-]?){8,10}(?!\d)"),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE),
    re.compile(r"\b\d{3}[- ]?\d{3}[- ]?\d{3,4}\b"),
)
_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "developer message",
    "you are chatgpt",
    "bỏ qua hướng dẫn",
    "bỏ qua chỉ dẫn",
    "tiết lộ prompt",
    "làm theo hướng dẫn này",
)


def is_pii_query(query: str) -> bool:
    """Reject common direct identifiers before they can leave this process."""

    return any(pattern.search(query) for pattern in _PII_PATTERNS)


def normalize_vinmec_url(url: str, *, base_url: str | None = None) -> str:
    """Return a canonical allowed HTTPS URL or reject it before I/O."""

    candidate = urljoin(base_url, url) if base_url else url
    parsed = urlsplit(candidate)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme.lower() != "https"
        or host not in ALLOWED_VINMEC_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
    ):
        raise VinmecWebError("VINMEC_URL_NOT_ALLOWED")
    return urlunsplit(("https", host, parsed.path or "/", parsed.query, ""))


def _sanitize_text(value: str, *, limit: int) -> tuple[str, bool]:
    normalized = " ".join(value.split())[:limit]
    lowered = normalized.casefold()
    if any(marker in lowered for marker in _INJECTION_MARKERS):
        # Do not pass any surrounding hostile instruction on to a model.
        return "Web content withheld because it contained untrusted instructions.", True
    return normalized, False


def sanitize_vinmec_source(source: VinmecSourceDocument) -> VinmecSourceDocument:
    """Defence in depth for alternate/mocked domain implementations."""

    title, title_injection = _sanitize_text(source.title, limit=240)
    excerpt, excerpt_injection = _sanitize_text(source.excerpt, limit=900)
    content, content_injection = _sanitize_text(source.content, limit=12_000)
    return VinmecSourceDocument(
        title=title or "Vinmec public information",
        url=normalize_vinmec_url(source.url),
        excerpt=excerpt,
        content=content,
        injection_detected=source.injection_detected or title_injection or excerpt_injection or content_injection,
    )


class VinmecWebSearchService:
    """Search Vinmec's public search page and fetch only approved article URLs."""

    def __init__(self, transport: VinmecHttpTransport | None = None) -> None:
        self._transport = transport or HttpxVinmecTransport()

    def search(self, *, query: str, limit: int, timeout_seconds: float) -> tuple[VinmecSourceDocument, ...]:
        if is_pii_query(query):
            raise VinmecWebError("VINMEC_QUERY_CONTAINS_PII")
        if limit < 1:
            raise VinmecWebError("VINMEC_INVALID_LIMIT")
        search_url = normalize_vinmec_url(VINMEC_SEARCH_URL)
        search_response = self._request(search_url, params={"q": query}, timeout_seconds=timeout_seconds)
        extractor = _PageExtractor()
        extractor.feed(search_response.text)
        documents: list[VinmecSourceDocument] = []
        seen: set[str] = set()
        for href, _anchor_text in extractor.links:
            try:
                url = normalize_vinmec_url(href, base_url=search_response.url)
            except VinmecWebError:
                # Discovered external links are never fetched and are not results.
                continue
            if url in seen or url == search_url or not self._is_content_path(url):
                continue
            seen.add(url)
            try:
                # One candidate's own redirect/fetch/content-validation
                # failure is a property of that single link, not of the
                # search dependency as a whole (BUILD-18B defect 1): a
                # standing navigation link that currently 302s must not
                # abort discovery of the next, fetchable candidate. This
                # still never follows a redirect and never fetches outside
                # the vinmec.com allowlist -- ``_request`` continues to
                # reject both unconditionally; the only change is that a
                # rejection here is scoped to this one candidate.
                page = self._request(url, params=None, timeout_seconds=timeout_seconds)
                document = self._document_from_page(page)
            except VinmecWebError:
                continue
            if document.content:
                documents.append(document)
            if len(documents) >= limit:
                break
        return tuple(documents)

    def _request(self, url: str, *, params: Mapping[str, str] | None, timeout_seconds: float) -> VinmecHttpResponse:
        approved = normalize_vinmec_url(url)
        response = self._transport.get(approved, params=params, timeout_seconds=timeout_seconds)
        if 300 <= response.status_code < 400 or "location" in {key.lower() for key in response.headers}:
            raise VinmecWebError("VINMEC_REDIRECT_REJECTED")
        if response.status_code != 200:
            raise VinmecWebError("VINMEC_FETCH_FAILED")
        returned = normalize_vinmec_url(response.url)
        expected_parts = urlsplit(approved)
        returned_parts = urlsplit(returned)
        if (returned_parts.scheme, returned_parts.netloc, returned_parts.path) != (
            expected_parts.scheme,
            expected_parts.netloc,
            expected_parts.path,
        ):
            raise VinmecWebError("VINMEC_RESPONSE_URL_MISMATCH")
        return response

    @staticmethod
    def _is_content_path(url: str) -> bool:
        path = urlsplit(url).path.casefold()
        return "/bai-viet/" in path or "/chuyen-muc/" in path or "/chuyen-khoa/" in path

    @staticmethod
    def _document_from_page(response: VinmecHttpResponse) -> VinmecSourceDocument:
        extractor = _PageExtractor()
        extractor.feed(response.text)
        title, title_injection = _sanitize_text(" ".join(extractor.title_parts), limit=240)
        content, content_injection = _sanitize_text(" ".join(extractor.text_parts), limit=12_000)
        excerpt_source = extractor.description or content
        excerpt, excerpt_injection = _sanitize_text(excerpt_source, limit=900)
        return sanitize_vinmec_source(
            VinmecSourceDocument(
                title=title or "Vinmec public information",
                url=normalize_vinmec_url(response.url),
                excerpt=excerpt,
                content=content,
                injection_detected=title_injection or content_injection or excerpt_injection,
            )
        )
