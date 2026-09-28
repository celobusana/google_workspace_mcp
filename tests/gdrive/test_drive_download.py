"""Tests for download_drive_file helpers and tool."""

import base64
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from googleapiclient.errors import HttpError

from core.file_limits import get_download_max_bytes
from core.server import server
from gdrive.drive_download import (
    DownloadNotSupportedError,
    build_filename,
    build_payload,
    resolve_export,
    too_large_message,
)
from gdrive.drive_tools import download_drive_file

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
        ("..", None, "download"),
        (".", "docx", "download.docx"),
        ("a\x85b\x9fc", None, "abc"),
        ("a\u2028b\u2029c", None, "abc"),
        ("evil\u202egpj.exe", None, "evilgpj.exe"),
        ("x\u2066y\u2069z", None, "xyz"),
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


def test_too_large_message_small_cap():
    msg = too_large_message("a.bin", 2048, 1024)
    assert "2.0 KB" in msg and "limit is 1 KB" in msg


def test_too_large_message_fractional_cap():
    msg = too_large_message("a.bin", 5 * 1024 * 1024, int(1.5 * 1024 * 1024))
    assert "limit is 1.5 MB" in msg


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


def _unwrap(tool):
    fn = tool.fn if hasattr(tool, "fn") else tool
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def _meta(name, mime, size=None):
    meta = {"name": name, "mimeType": mime, "webViewLink": "https://drive/x"}
    if size is not None:
        meta["size"] = str(size)
    return meta


def _fake_download(content: bytes, calls: list, tmp_dir: Path):
    async def _download(service, file_id, export_mime_type=None):
        calls.append((file_id, export_mime_type))
        tmp = tmp_dir / f"dl_{len(calls)}"
        tmp.write_bytes(content)
        return tmp

    return _download


async def _call(
    tmp_dir, meta, content=b"PK\x03\x04data", export_format=None, calls=None
):
    calls = [] if calls is None else calls
    with (
        patch("gdrive.drive_tools.resolve_drive_item", return_value=("f1", meta)),
        patch(
            "gdrive.drive_tools._download_file_to_temp",
            side_effect=_fake_download(content, calls, tmp_dir),
        ),
    ):
        return await _unwrap(download_drive_file)(
            Mock(), "user@example.com", "f1", export_format
        )


@pytest.mark.asyncio
async def test_binary_pptx_returns_original_bytes(tmp_path):
    calls = []
    raw = await _call(tmp_path, _meta("deck.pptx", PPTX, 8), calls=calls)
    payload = json.loads(raw)
    assert calls == [("f1", None)]
    assert payload["filename"] == "deck.pptx"
    assert payload["mimeType"] == PPTX
    assert payload["storeAsFile"] is True
    assert base64.b64decode(payload["base64Data"]) == b"PK\x03\x04data"
    assert payload["source"]["exported"] is False
    assert payload["source"]["provider"] == "googledrive"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,fmt,ext,mime",
    [
        ("application/vnd.google-apps.presentation", None, "pptx", PPTX),
        ("application/vnd.google-apps.document", None, "docx", DOCX),
        ("application/vnd.google-apps.spreadsheet", None, "xlsx", XLSX),
        ("application/vnd.google-apps.presentation", "pdf", "pdf", "application/pdf"),
    ],
)
async def test_native_exports(tmp_path, source, fmt, ext, mime):
    calls = []
    raw = await _call(
        tmp_path, _meta("Q3 v2.1 plan", source), export_format=fmt, calls=calls
    )
    payload = json.loads(raw)
    assert calls == [("f1", mime)]
    assert payload["filename"] == f"Q3 v2.1 plan.{ext}"
    assert payload["mimeType"] == mime
    assert payload["source"]["exported"] is True
    assert payload["source"]["sourceMimeType"] == source


@pytest.mark.asyncio
async def test_invalid_export_format_errors_without_download(tmp_path):
    calls = []
    raw = await _call(
        tmp_path,
        _meta("Doc", "application/vnd.google-apps.document"),
        export_format="pptx",
        calls=calls,
    )
    assert raw.startswith("Error:") and "Allowed values" in raw
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mime", ["application/vnd.google-apps.form", "application/vnd.google-apps.folder"]
)
async def test_unsupported_types_error_without_download(tmp_path, mime):
    calls = []
    raw = await _call(tmp_path, _meta("X", mime), calls=calls)
    assert raw == "Error: This file type cannot be downloaded."
    assert calls == []


@pytest.mark.asyncio
async def test_metadata_size_over_limit_skips_download(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_MCP_DOWNLOAD_MAX_BYTES", "4")
    calls = []
    raw = await _call(tmp_path, _meta("big.pdf", "application/pdf", 10), calls=calls)
    assert raw.startswith("Error:") and "download limit" in raw
    assert calls == []


@pytest.mark.asyncio
async def test_export_over_limit_removes_temp_file(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_MCP_DOWNLOAD_MAX_BYTES", "4")
    raw = await _call(
        tmp_path,
        _meta("Deck", "application/vnd.google-apps.presentation"),
        content=b"0123456789",
    )
    assert raw.startswith("Error:") and "download limit" in raw
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_temp_file_removed_on_success(tmp_path):
    await _call(tmp_path, _meta("deck.pptx", PPTX, 8))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_temp_file_removed_when_read_fails(tmp_path):
    with (
        patch(
            "gdrive.drive_tools.resolve_drive_item",
            return_value=("f1", _meta("deck.pptx", PPTX, 8)),
        ),
        patch(
            "gdrive.drive_tools._download_file_to_temp",
            side_effect=_fake_download(b"abc", [], tmp_path),
        ),
        patch("gdrive.drive_tools.asyncio.to_thread", side_effect=OSError("boom")),
    ):
        with pytest.raises(OSError):
            await _unwrap(download_drive_file)(Mock(), "u@example.com", "f1", None)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_export_size_limit_exceeded_is_explained():
    err = HttpError(
        Mock(status=403, reason="Forbidden"),
        b'{"error": {"errors": [{"reason": "exportSizeLimitExceeded"}]}}',
    )
    with (
        patch(
            "gdrive.drive_tools.resolve_drive_item",
            return_value=(
                "f1",
                _meta("Deck", "application/vnd.google-apps.presentation"),
            ),
        ),
        patch("gdrive.drive_tools._download_file_to_temp", side_effect=err),
    ):
        raw = await _unwrap(download_drive_file)(Mock(), "u@example.com", "f1", None)
    assert raw.startswith("Error:") and "10 MB" in raw


@pytest.mark.asyncio
async def test_tool_is_read_only_without_structured_output():
    # A structured copy would send the base64 payload twice.
    tool = await server.get_tool("download_drive_file")
    assert tool.output_schema is None
    assert tool.annotations.readOnlyHint is True


@pytest.mark.parametrize(
    "name,mime,expected",
    [
        ("Q3 v2.1", "application/pdf", "Q3 v2.1.pdf"),
        ("report.pdf", "application/pdf", "report.pdf"),
        ("REPORT.PDF", "application/pdf", "REPORT.PDF"),
        ("photo", "image/jpeg", "photo.jpg"),
        ("photo.jpeg", "image/jpeg", "photo.jpeg"),
        ("deck", PPTX, "deck.pptx"),
        ("name.", "application/pdf", "name.pdf"),
        ("blob", "application/octet-stream", "blob"),
        ("notes.custom", "application/octet-stream", "notes.custom"),
    ],
)
def test_build_filename_infers_extension_from_mime(name, mime, expected):
    assert build_filename(name, None, mime) == expected


def test_build_filename_trailing_dot_with_export_extension():
    assert build_filename("name.", "docx") == "name.docx"


def test_build_filename_caps_length_and_keeps_extension():
    result = build_filename("a" * 500 + ".pdf", None, "application/pdf")
    assert len(result) == 200 and result.endswith(".pdf")
    result = build_filename("b" * 500, "docx")
    assert len(result) == 200 and result.endswith(".docx")


@pytest.mark.asyncio
async def test_shortcut_is_resolved_to_its_target(tmp_path):
    items = {
        "short1": {
            "id": "short1",
            "name": "link",
            "mimeType": "application/vnd.google-apps.shortcut",
            "shortcutDetails": {"targetId": "real1", "targetMimeType": PPTX},
        },
        "real1": {
            "id": "real1",
            "name": "deck.pptx",
            "mimeType": PPTX,
            "webViewLink": "https://drive/real1",
            "size": "8",
        },
    }
    service = Mock()
    service.files.return_value.get.side_effect = lambda fileId, **_: Mock(
        execute=lambda: items[fileId]
    )
    calls = []
    with patch(
        "gdrive.drive_tools._download_file_to_temp",
        side_effect=_fake_download(b"PK\x03\x04data", calls, tmp_path),
    ):
        raw = await _unwrap(download_drive_file)(
            service, "user@example.com", "short1", None
        )
    payload = json.loads(raw)
    assert calls == [("real1", None)]
    assert payload["filename"] == "deck.pptx"
    assert payload["source"]["fileId"] == "real1"
    assert payload["source"]["sourceMimeType"] == PPTX
