"""Tests for HTTP request tools."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from bluesnail.agent.tools import ToolManager
from bluesnail.agent.types import ToolCall
from bluesnail.tools import create_default_tools
from bluesnail.tools.http import (
    http_request,
    register_http_tools,
    validate_url,
)


class _Handler(BaseHTTPRequestHandler):
    responses: dict[str, dict[str, Any]] = {}

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _reply(self) -> None:
        spec = self.responses.get(self.path, {"status": 404, "body": "not found"})
        status = int(spec.get("status", 200))
        body = str(spec.get("body", "")).encode("utf-8")
        headers = dict(spec.get("headers") or {})
        self.send_response(status)
        self.send_header("Content-Type", headers.pop("Content-Type", "text/plain; charset=utf-8"))
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self._reply()

    def do_HEAD(self) -> None:  # noqa: N802
        self._reply()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length).decode("utf-8")
        self.responses["_last_post"] = {"body": payload, "headers": dict(self.headers)}
        self._reply()


@pytest.fixture
def http_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    _Handler.responses = {
        "/ok": {"status": 200, "body": '{"hello":"world"}', "headers": {"Content-Type": "application/json"}},
        "/redirect": {
            "status": 302,
            "body": "",
            "headers": {"Location": f"{base_url}/ok"},
        },
        "/echo": {"status": 200, "body": "posted"},
        "/error": {"status": 503, "body": "unavailable"},
    }
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def tools() -> ToolManager:
    manager = ToolManager()
    register_http_tools(manager, block_private=False)
    return manager


def test_create_default_tools_registers_http_request():
    manager = create_default_tools()
    names = {tool.name for tool in manager.registry.list_tools()}
    assert "http_request" in names


def test_http_request_get_json(http_server: str):
    result = http_request(f"{http_server}/ok", block_private=False)
    assert result["status_code"] == 200
    assert result["truncated"] is False
    assert '"hello"' in result["body"]


def test_http_request_tool_via_manager(tools: ToolManager, http_server: str):
    result = tools.run(
        ToolCall(
            id="call_1",
            name="http_request",
            arguments={"url": f"{http_server}/ok", "method": "GET"},
        )
    )
    assert not result.is_error
    payload = json.loads(result.content)
    assert payload["status_code"] == 200
    assert "world" in payload["body"]


def test_http_request_post(http_server: str):
    result = http_request(
        f"{http_server}/echo",
        method="POST",
        body='{"a":1}',
        headers={"Content-Type": "application/json"},
        block_private=False,
    )
    assert result["status_code"] == 200
    assert _Handler.responses["_last_post"]["body"] == '{"a":1}'


def test_http_request_follows_redirect(http_server: str):
    result = http_request(f"{http_server}/redirect", block_private=False)
    assert result["status_code"] == 200
    assert result["url"].endswith("/ok")
    assert "world" in result["body"]


def test_http_request_returns_error_body(http_server: str):
    result = http_request(f"{http_server}/error", block_private=False)
    assert result["status_code"] == 503
    assert result["body"] == "unavailable"


def test_validate_url_rejects_non_http_scheme():
    with pytest.raises(ValueError, match="Only http and https"):
        validate_url("ftp://example.com/file")


def test_validate_url_rejects_credentials():
    with pytest.raises(ValueError, match="credentials"):
        validate_url("https://user:pass@example.com/")


def test_validate_url_blocks_private_hosts():
    with pytest.raises(ValueError, match="private/local"):
        validate_url("http://127.0.0.1/")
    with pytest.raises(ValueError, match="private/local"):
        validate_url("http://localhost/")


def test_http_request_blocks_private_by_default():
    with pytest.raises(ValueError, match="private/local"):
        http_request("http://127.0.0.1:1/")


def test_http_request_rejects_body_on_get():
    with pytest.raises(ValueError, match="cannot include a body"):
        http_request(
            "https://example.com/",
            method="GET",
            body="nope",
            block_private=False,
        )


def test_http_request_invalid_method_via_tool(tools: ToolManager):
    result = tools.run(
        ToolCall(
            id="call_1",
            name="http_request",
            arguments={"url": "https://example.com/", "method": "TRACE"},
        )
    )
    assert result.is_error
    assert "Unsupported HTTP method" in result.content
