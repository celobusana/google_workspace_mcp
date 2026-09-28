"""Helpers for download_drive_file: what to fetch and how to hand it to the caller."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
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


_MAX_FILENAME_LENGTH = 200
_MAX_EXTENSION_LENGTH = 16
# mimetypes prefers odd extensions for some types (e.g. .jpe), so pin the common ones.
_PREFERRED_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "application/zip": ".zip",
    "application/json": ".json",
    _DOCX: ".docx",
    _XLSX: ".xlsx",
    _PPTX: ".pptx",
}


def _extension_for_mime(mime_type: str) -> Optional[tuple[str, set[str]]]:
    # ".bin" says nothing about the content, so leave generic files as named.
    if mime_type == "application/octet-stream":
        return None
    preferred = _PREFERRED_EXTENSIONS.get(mime_type) or mimetypes.guess_extension(
        mime_type
    )
    if not preferred:
        return None
    return preferred, {preferred, *mimetypes.guess_all_extensions(mime_type)}


def build_filename(
    name: str, extension: Optional[str], source_mime: Optional[str] = None
) -> str:
    """Sanitize a Drive name and make sure it carries the extension of what is delivered.

    ``extension`` is the export target for native files; for binaries, pass
    ``source_mime`` so a missing extension is inferred from the mime type.
    """
    # The filename becomes a path inside the sandbox.
    clean = _CONTROL_CHARS.sub("", _UNSAFE_PATH_CHARS.sub("-", name or "")).strip()
    if clean in ("", ".", ".."):
        clean = "download"

    if extension:
        target = f".{extension.lower()}"
        if not clean.lower().endswith(target):
            clean = f"{clean.rstrip('. ')}{target}"
    elif source_mime:
        inferred = _extension_for_mime(source_mime.lower())
        if inferred:
            preferred, accepted = inferred
            suffix = os.path.splitext(clean)[1].lower()
            # A dot in the name ("Q3 v2.1") is not an extension unless it is a known one.
            if suffix not in accepted and suffix not in mimetypes.types_map:
                clean = f"{clean.rstrip('. ')}{preferred}"

    if len(clean) > _MAX_FILENAME_LENGTH:
        stem, suffix = os.path.splitext(clean)
        if len(suffix) > _MAX_EXTENSION_LENGTH:
            stem, suffix = clean, ""
        clean = f"{stem[: _MAX_FILENAME_LENGTH - len(suffix)]}{suffix}"
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
