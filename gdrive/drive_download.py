"""Helpers for download_drive_file: what to fetch and how to hand it to the caller."""

from __future__ import annotations

import base64
import json
import re
from typing import Optional

from core.file_limits import get_download_max_bytes

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_PDF = "application/pdf"

# Google native type -> (default extension, {extension: export mime})
_EXPORTS: dict[str, tuple[str, dict[str, str]]] = {
    "application/vnd.google-apps.document": (
        "docx",
        {
            "docx": _DOCX,
            "pdf": _PDF,
            "odt": "application/vnd.oasis.opendocument.text",
            "txt": "text/plain",
        },
    ),
    "application/vnd.google-apps.spreadsheet": (
        "xlsx",
        {
            "xlsx": _XLSX,
            "csv": "text/csv",
            "pdf": _PDF,
            "ods": "application/vnd.oasis.opendocument.spreadsheet",
        },
    ),
    "application/vnd.google-apps.presentation": (
        "pptx",
        {
            "pptx": _PPTX,
            "pdf": _PDF,
            "odp": "application/vnd.oasis.opendocument.presentation",
        },
    ),
    "application/vnd.google-apps.drawing": (
        "png",
        {"png": "image/png", "pdf": _PDF, "svg": "image/svg+xml"},
    ),
}

_GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."
_UNSAFE_PATH_CHARS = re.compile(r"[/\\]")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

__all__ = [
    "DownloadNotSupportedError",
    "build_filename",
    "build_payload",
    "get_download_max_bytes",
    "resolve_export",
    "too_large_message",
]


class DownloadNotSupportedError(ValueError):
    """The file type or requested export format cannot be downloaded."""


def resolve_export(
    source_mime: str, export_format: Optional[str]
) -> Optional[tuple[str, str]]:
    if source_mime in _EXPORTS:
        default_ext, formats = _EXPORTS[source_mime]
        ext = (export_format or default_ext).lower()
        if ext not in formats:
            allowed = ", ".join(formats)
            raise DownloadNotSupportedError(
                f"export_format '{export_format}' is not supported for this file. "
                f"Allowed values: {allowed}."
            )
        return ext, formats[ext]
    if source_mime.startswith(_GOOGLE_NATIVE_PREFIX):
        raise DownloadNotSupportedError("This file type cannot be downloaded.")
    return None


def build_filename(name: str, extension: Optional[str]) -> str:
    # The filename becomes a path inside the sandbox.
    clean = _CONTROL_CHARS.sub("", _UNSAFE_PATH_CHARS.sub("-", name or "")).strip()
    if not clean:
        clean = "download"
    if extension and not clean.lower().endswith(f".{extension.lower()}"):
        clean = f"{clean}.{extension}"
    return clean


def too_large_message(file_name: str, size_bytes: int, max_bytes: int) -> str:
    mb = 1024 * 1024
    return (
        f'Error: "{file_name}" is {size_bytes / mb:.1f} MB; '
        f"the download limit is {max_bytes / mb:.0f} MB."
    )


def build_payload(
    *,
    filename: str,
    mime_type: str,
    data: bytes,
    file_id: str,
    source_mime: str,
    web_view_link: Optional[str],
    exported: bool,
) -> str:
    return json.dumps(
        {
            "filename": filename,
            "mimeType": mime_type,
            "fileSize": len(data),
            "base64Data": base64.b64encode(data).decode("ascii"),
            "storeAsFile": True,
            "source": {
                "provider": "googledrive",
                "fileId": file_id,
                "sourceMimeType": source_mime,
                "webViewLink": web_view_link,
                "exported": exported,
            },
        }
    )
