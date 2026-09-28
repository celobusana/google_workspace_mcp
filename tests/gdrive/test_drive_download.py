"""Tests for download_drive_file helpers and tool."""

import base64
import json

import pytest

from gdrive.drive_download import (
    DownloadNotSupportedError,
    build_filename,
    build_payload,
    get_download_max_bytes,
    resolve_export,
    too_large_message,
)

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@pytest.mark.parametrize(
    "source,fmt,expected",
    [
        ("application/vnd.google-apps.document", None, ("docx", DOCX)),
        ("application/vnd.google-apps.document", "pdf", ("pdf", "application/pdf")),
        ("application/vnd.google-apps.spreadsheet", None, ("xlsx", XLSX)),
        ("application/vnd.google-apps.spreadsheet", "csv", ("csv", "text/csv")),
        ("application/vnd.google-apps.presentation", None, ("pptx", PPTX)),
        ("application/vnd.google-apps.drawing", None, ("png", "image/png")),
        (PPTX, None, None),
        (PPTX, "pdf", None),
        ("application/pdf", None, None),
    ],
)
def test_resolve_export(source, fmt, expected):
    assert resolve_export(source, fmt) == expected


def test_resolve_export_rejects_unknown_format():
    with pytest.raises(DownloadNotSupportedError, match="docx, pdf, odt, txt"):
        resolve_export("application/vnd.google-apps.document", "pptx")


@pytest.mark.parametrize(
    "source",
    [
        "application/vnd.google-apps.form",
        "application/vnd.google-apps.site",
        "application/vnd.google-apps.folder",
    ],
)
def test_resolve_export_rejects_non_exportable_native(source):
    with pytest.raises(DownloadNotSupportedError, match="cannot be downloaded"):
        resolve_export(source, None)


@pytest.mark.parametrize(
    "name,ext,expected",
    [
        ("Q3 v2.1 plan", "docx", "Q3 v2.1 plan.docx"),
        ("deck.pptx", "pptx", "deck.pptx"),
        ("Deck.PPTX", "pptx", "Deck.PPTX"),
        ("a/b\\c", "pdf", "a-b-c.pdf"),
        ("bad\x00\x1fname.pdf", None, "badname.pdf"),
        ("   ", "docx", "download.docx"),
        ("report.pdf", None, "report.pdf"),
    ],
)
def test_build_filename(name, ext, expected):
    assert build_filename(name, ext) == expected


def test_download_max_bytes_default(monkeypatch):
    monkeypatch.delenv("WORKSPACE_MCP_DOWNLOAD_MAX_BYTES", raising=False)
    assert get_download_max_bytes() == 15 * 1024 * 1024


def test_download_max_bytes_env(monkeypatch):
    monkeypatch.setenv("WORKSPACE_MCP_DOWNLOAD_MAX_BYTES", "1024")
    assert get_download_max_bytes() == 1024


@pytest.mark.parametrize("raw", ["0", "-1", "abc"])
def test_download_max_bytes_invalid(monkeypatch, raw):
    monkeypatch.setenv("WORKSPACE_MCP_DOWNLOAD_MAX_BYTES", raw)
    with pytest.raises(ValueError):
        get_download_max_bytes()


def test_too_large_message():
    msg = too_large_message("big.pptx", 20 * 1024 * 1024, 15 * 1024 * 1024)
    assert msg.startswith("Error:")
    assert "big.pptx" in msg and "20.0 MB" in msg and "15 MB" in msg


def test_build_payload_roundtrip():
    raw = build_payload(
        filename="deck.pptx",
        mime_type=PPTX,
        data=b"PK\x03\x04abc",
        file_id="f1",
        source_mime="application/vnd.google-apps.presentation",
        web_view_link="https://docs.google.com/presentation/d/f1/edit",
        exported=True,
    )
    payload = json.loads(raw)
    assert payload["storeAsFile"] is True
    assert payload["filename"] == "deck.pptx"
    assert payload["mimeType"] == PPTX
    assert payload["fileSize"] == 7
    assert base64.b64decode(payload["base64Data"]) == b"PK\x03\x04abc"
    assert payload["source"] == {
        "provider": "googledrive",
        "fileId": "f1",
        "sourceMimeType": "application/vnd.google-apps.presentation",
        "webViewLink": "https://docs.google.com/presentation/d/f1/edit",
        "exported": True,
    }
