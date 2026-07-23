"""HTTP request tools for fetching external data."""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from bluesnail.agent.tools import ToolManager
from bluesnail.tools.http_content import extract_useful_content

DEFAULT_TIMEOUT_SECONDS = 15
MAX_TIMEOUT_SECONDS = 60
MAX_RESPONSE_BYTES = 1_048_576
MAX_REDIRECTS = 5
USER_AGENT = "BlueSnail/0.1 (http tool)"

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"})

HTTP_REQUEST_PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "Absolute HTTP or HTTPS URL to request",
        },
        "method": {
            "type": "string",
            "description": "HTTP method (GET, POST, PUT, PATCH, DELETE, HEAD). Defaults to GET",
            "enum": sorted(ALLOWED_METHODS),
        },
        "headers": {
            "type": "object",
            "description": "Optional request headers as string key/value pairs",
            "additionalProperties": {"type": "string"},
        },
        "body": {
            "type": "string",
            "description": "Optional request body for POST/PUT/PATCH",
        },
        "timeout": {
            "type": "number",
            "description": (
                f"Request timeout in seconds "
                f"(default {DEFAULT_TIMEOUT_SECONDS}, max {MAX_TIMEOUT_SECONDS})"
            ),
        },
        "extract": {
            "type": "boolean",
            "description": (
                "If true (default), extract useful content from the response: "
                "HTML keeps visible text only (scripts/styles/css removed), "
                "JSON is compacted, plain text is normalized. "
                "If false, return the raw response body."
            ),
        },
    },
    "required": ["url"],
}


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _is_blocked_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def resolve_host_ips(hostname: str) -> list[str]:
    """Resolve a hostname to one or more IP addresses."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Failed to resolve host: {hostname}") from exc

    addresses: list[str] = []
    seen: set[str] = set()
    for info in infos:
        addr = info[4][0]
        if addr not in seen:
            seen.add(addr)
            addresses.append(addr)
    if not addresses:
        raise ValueError(f"Failed to resolve host: {hostname}")
    return addresses


def validate_url(url: str, *, block_private: bool = True) -> urllib.parse.ParseResult:
    """Validate URL scheme/host and optionally reject private/local targets."""
    raw = url.strip()
    if not raw:
        raise ValueError("url is required")

    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError("Only http and https URLs are allowed")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not allowed")

    if block_private:
        for address in resolve_host_ips(parsed.hostname):
            if _is_blocked_ip(address):
                raise ValueError(
                    f"Requests to private/local addresses are blocked: {parsed.hostname}"
                )
    return parsed


def _normalize_timeout(timeout: float | None) -> float:
    if timeout is None:
        return float(DEFAULT_TIMEOUT_SECONDS)
    value = float(timeout)
    if value <= 0:
        raise ValueError("timeout must be positive")
    return min(value, float(MAX_TIMEOUT_SECONDS))


def _normalize_headers(headers: dict[str, str] | None) -> dict[str, str]:
    result: dict[str, str] = {"User-Agent": USER_AGENT}
    if not headers:
        return result
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("headers must be string key/value pairs")
        lowered = key.lower()
        if lowered == "host":
            raise ValueError("Overriding the Host header is not allowed")
        result[key] = value
    return result


def _decode_body(raw: bytes, content_type: str | None) -> str:
    charset = "utf-8"
    if content_type:
        for part in content_type.split(";"):
            part = part.strip().lower()
            if part.startswith("charset="):
                charset = part.split("=", 1)[1].strip() or "utf-8"
                break
    try:
        return raw.decode(charset)
    except (LookupError, UnicodeDecodeError):
        return raw.decode("utf-8", errors="replace")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Disable automatic redirects so each hop can be validated."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoRedirectHandler)


def _read_limited(response: Any) -> tuple[bytes, bool]:
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    truncated = len(raw) > MAX_RESPONSE_BYTES
    if truncated:
        raw = raw[:MAX_RESPONSE_BYTES]
    return raw, truncated


def _build_result(
    *,
    url: str,
    status_code: int,
    content_type: str | None,
    text: str,
    truncated: bool,
    extract: bool,
    response_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "url": url,
        "status_code": int(status_code),
        "content_type": content_type or "",
        "truncated": truncated,
    }
    if extract:
        extracted = extract_useful_content(text, content_type)
        result.update(extracted)
        result["truncated"] = truncated or bool(extracted.get("content_truncated"))
    else:
        result["headers"] = response_headers or {}
        result["body"] = text
    return result


def http_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
    timeout: float | None = None,
    extract: bool = True,
    *,
    block_private: bool = True,
) -> dict[str, Any]:
    """Perform an HTTP request and return a structured response.

    When ``extract`` is true (default), HTML/JSON/text bodies are reduced to
    useful content before being returned to the agent.
    """
    method_upper = (method or "GET").strip().upper()
    if method_upper not in ALLOWED_METHODS:
        raise ValueError(f"Unsupported HTTP method: {method}")

    current_url = url.strip()
    validate_url(current_url, block_private=block_private)
    timeout_seconds = _normalize_timeout(timeout)
    request_headers = _normalize_headers(headers)
    opener = _build_opener()

    data: bytes | None = None
    if body is not None:
        if method_upper in {"GET", "HEAD", "DELETE"}:
            raise ValueError(f"{method_upper} requests cannot include a body")
        data = body.encode("utf-8")
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError(
                f"Request body too large ({len(data)} bytes, max {MAX_RESPONSE_BYTES})"
            )
        request_headers.setdefault("Content-Type", "application/json")

    redirects = 0
    while True:
        request = urllib.request.Request(
            current_url,
            data=data,
            headers=request_headers,
            method=method_upper,
        )
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                status = getattr(response, "status", None) or response.getcode()
                response_headers = {
                    key: value for key, value in response.headers.items()
                }
                raw, truncated = _read_limited(response)
                content_type = response.headers.get("Content-Type")
                text = _decode_body(raw, content_type)
                return _build_result(
                    url=current_url,
                    status_code=int(status),
                    content_type=content_type,
                    text=text,
                    truncated=truncated,
                    extract=extract,
                    response_headers=response_headers,
                )
        except urllib.error.HTTPError as exc:
            # Redirects become HTTPError because automatic following is disabled.
            if 300 <= exc.code < 400:
                location = exc.headers.get("Location") if exc.headers else None
                if not location:
                    raise RuntimeError(
                        f"Redirect response missing Location header ({exc.code})"
                    ) from exc
                redirects += 1
                if redirects > MAX_REDIRECTS:
                    raise RuntimeError(
                        f"Too many redirects (max {MAX_REDIRECTS})"
                    ) from exc
                current_url = urllib.parse.urljoin(current_url, location)
                validate_url(current_url, block_private=block_private)
                # Drop body when converting to GET on common redirect codes.
                if exc.code in {301, 302, 303} and method_upper != "HEAD":
                    method_upper = "GET"
                    data = None
                continue

            raw, truncated = _read_limited(exc)
            content_type = exc.headers.get("Content-Type") if exc.headers else None
            text = _decode_body(raw, content_type)
            response_headers = {
                key: value
                for key, value in (exc.headers.items() if exc.headers else [])
            }
            return _build_result(
                url=current_url,
                status_code=int(exc.code),
                content_type=content_type,
                text=text,
                truncated=truncated,
                extract=extract,
                response_headers=response_headers,
            )
        except urllib.error.URLError as exc:
            raise RuntimeError(f"HTTP request failed: {exc.reason}") from exc


def register_http_tools(
    manager: ToolManager,
    *,
    block_private: bool | None = None,
) -> None:
    """Register HTTP tools for fetching external data."""
    if block_private is None:
        block_private = not _env_flag("BLUESNAIL_HTTP_ALLOW_PRIVATE", default=False)

    @manager.tool(
        name="http_request",
        description=(
            "Fetch external data over HTTP/HTTPS. Supports GET/POST/PUT/PATCH/DELETE/HEAD. "
            "By default extracts useful content: HTML pages become visible text only "
            "(CSS/scripts/styles removed), JSON is compacted. "
            "Private/local network targets are blocked by default."
        ),
        parameters=HTTP_REQUEST_PARAMETERS,
    )
    def http_request_tool(
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout: float | None = None,
        extract: bool = True,
    ) -> str:
        result = http_request(
            url=url,
            method=method,
            headers=headers,
            body=body,
            timeout=timeout,
            extract=extract,
            block_private=block_private,
        )
        return json.dumps(result, ensure_ascii=False)
