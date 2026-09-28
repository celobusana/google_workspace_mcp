"""Helpers for download_drive_file: what to fetch and how to hand it to the caller."""

from __future__ import annotations

import base64
import json
import re
from typing import Optional

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_PDF = "application/pdf"

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
# C0/C1 controls, line/paragraph separators and bidi overrides can spoof or break the sandbox path.
_CONTROL_CHARS = re.compile(
    "[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]"
)


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
    if clean in ("", ".", ".."):
        clean = "download"
    if extension and not clean.lower().endswith(f".{extension.lower()}"):
        clean = f"{clean}.{extension}"
    return clean


def _format_size(num_bytes: int, *, trim: bool = False) -> str:
    value, unit = (
        (num_bytes / (1024 * 1024), "MB")
        if num_bytes >= 1024 * 1024
        else (num_bytes / 1024, "KB")
    )
    text = f"{value:.1f}"
    if trim and text.endswith(".0"):
        text = text[:-2]
    return f"{text} {unit}"


def too_large_message(file_name: str, size_bytes: int, max_bytes: int) -> str:
    return (
        f'Error: "{file_name}" is {_format_size(size_bytes)}; '
        f"the download limit is {_format_size(max_bytes, trim=True)}."
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
