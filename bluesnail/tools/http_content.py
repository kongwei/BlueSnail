"""Extract useful text content from HTTP response bodies."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any

MAX_CONTENT_CHARS = 100_000

_SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "iframe",
        "object",
        "embed",
        "canvas",
    }
)
_VOID_IGNORE_TAGS = frozenset({"link", "meta", "base", "area", "wbr", "source", "track", "param"})
_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "th",
        "tr",
        "ul",
    }
)
_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_HTML_SNIFF_RE = re.compile(
    r"^\s*(?:<!doctype\s+html|<html\b|<head\b|<body\b)",
    re.IGNORECASE,
)


class _HTMLTextExtractor(HTMLParser):
    """Collect visible text from HTML, skipping scripts/styles/chrome."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.body_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._in_head = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name == "head":
            self._in_head = True
            return
        if name == "title":
            self._in_title = True
            return
        if name in _VOID_IGNORE_TAGS:
            return
        if name in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if name == "br" or name in _BLOCK_TAGS:
            self.body_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name == "title":
            self._in_title = False
            return
        if name == "head":
            self._in_head = False
            return
        if name in _SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if name in _BLOCK_TAGS and name != "br":
            self.body_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
            return
        if self._skip_depth or self._in_head:
            return
        text = data.strip()
        if text:
            self.body_parts.append(text)
            self.body_parts.append(" ")


def _normalize_whitespace(text: str) -> str:
    lines = [_WHITESPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    return _BLANK_LINES_RE.sub("\n\n", cleaned).strip()


def _truncate(text: str, limit: int = MAX_CONTENT_CHARS) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _mime_type(content_type: str | None) -> str:
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def detect_content_kind(body: str, content_type: str | None) -> str:
    """Classify response body as html, json, text, or other."""
    mime = _mime_type(content_type)
    if mime in {"text/html", "application/xhtml+xml"}:
        return "html"
    if mime in {"application/json", "application/ld+json"} or mime.endswith("+json"):
        return "json"
    if mime.startswith("text/") or mime in {
        "application/xml",
        "application/javascript",
        "application/xhtml+xml",
    }:
        if mime == "application/javascript":
            return "other"
        if "html" in mime or _HTML_SNIFF_RE.match(body):
            return "html"
        return "text"
    stripped = body.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(stripped)
            return "json"
        except json.JSONDecodeError:
            pass
    if _HTML_SNIFF_RE.match(body):
        return "html"
    if mime.startswith("text/") or not mime:
        # Prefer text for unknown textual payloads; binary usually fails decode earlier.
        if body and "\x00" not in body[:1000]:
            return "text"
    return "other"


def extract_html_text(html: str) -> dict[str, str]:
    """Strip tags/styles/scripts and return title + visible text."""
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # Fall back to a coarse tag strip if HTML is badly malformed.
        coarse = re.sub(
            r"(?is)<(script|style|noscript|svg|iframe).*?>.*?</\1>",
            " ",
            html,
        )
        coarse = re.sub(r"(?is)<style.*?>.*?</style>", " ", coarse)
        coarse = re.sub(r"(?s)<[^>]+>", " ", coarse)
        return {"title": "", "text": _normalize_whitespace(coarse)}

    title = _normalize_whitespace(" ".join(parser.title_parts))
    text = _normalize_whitespace("".join(parser.body_parts))
    return {"title": title, "text": text}


def extract_json_text(body: str) -> str:
    """Compact JSON to reduce token size while keeping structure."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return _normalize_whitespace(body)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def extract_useful_content(
    body: str,
    content_type: str | None = None,
    *,
    max_chars: int = MAX_CONTENT_CHARS,
) -> dict[str, Any]:
    """Extract LLM-friendly content from an HTTP response body."""
    kind = detect_content_kind(body, content_type)
    title = ""
    if kind == "html":
        extracted = extract_html_text(body)
        title = extracted["title"]
        content = extracted["text"]
    elif kind == "json":
        content = extract_json_text(body)
    elif kind == "text":
        content = _normalize_whitespace(body)
    else:
        content = (
            f"[Non-text content omitted: {_mime_type(content_type) or 'unknown'}]"
        )

    content, content_truncated = _truncate(content, max_chars)
    result: dict[str, Any] = {
        "content_kind": kind,
        "content": content,
        "content_truncated": content_truncated,
        "original_chars": len(body),
        "extracted_chars": len(content),
    }
    if title:
        result["title"] = title
    return result
