"""Tests for HTTP response content extraction."""

from __future__ import annotations

from bluesnail.tools.http_content import (
    detect_content_kind,
    extract_html_text,
    extract_useful_content,
)


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>News Page</title>
  <style type="text/css">
    body { color: red; }
    .hidden { display: none; }
  </style>
  <link rel="stylesheet" href="theme.css">
  <script>window.track = true;</script>
</head>
<body>
  <nav>Home | About</nav>
  <h1>Breaking Story</h1>
  <p>Hello <b>world</b> &amp; friends.</p>
  <style>.more { font-size: 12px; }</style>
  <script type="text/javascript">alert('x');</script>
  <footer>Copyright 2026</footer>
</body>
</html>
"""


def test_extract_html_removes_style_and_script():
    result = extract_html_text(SAMPLE_HTML)
    assert result["title"] == "News Page"
    assert "Breaking Story" in result["text"]
    assert "Hello world & friends." in result["text"]
    assert "Copyright 2026" in result["text"]
    assert "color: red" not in result["text"]
    assert "theme.css" not in result["text"]
    assert "window.track" not in result["text"]
    assert "alert(" not in result["text"]
    assert "<style" not in result["text"]
    assert "<script" not in result["text"]


def test_extract_useful_content_html():
    result = extract_useful_content(SAMPLE_HTML, "text/html; charset=utf-8")
    assert result["content_kind"] == "html"
    assert result["title"] == "News Page"
    assert "Breaking Story" in result["content"]
    assert result["extracted_chars"] < result["original_chars"]
    assert result["content_truncated"] is False


def test_extract_useful_content_json_compacts():
    body = '{\n  "hello": "world",\n  "n": 1\n}'
    result = extract_useful_content(body, "application/json")
    assert result["content_kind"] == "json"
    assert result["content"] == '{"hello":"world","n":1}'


def test_extract_useful_content_plain_text():
    result = extract_useful_content("  line1 \n\n\n line2  ", "text/plain")
    assert result["content_kind"] == "text"
    assert result["content"] == "line1\nline2"


def test_detect_html_by_sniffing_without_content_type():
    assert detect_content_kind("<!DOCTYPE html><html><body>Hi</body></html>", None) == "html"


def test_extract_truncates_long_content():
    long_text = "a" * 250
    result = extract_useful_content(long_text, "text/plain", max_chars=100)
    assert result["content_truncated"] is True
    assert len(result["content"]) == 100
