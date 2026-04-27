"""Helpers for packaging the Chromium companion extension."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


def build_extension_zip_bytes(extension_dir: Path) -> bytes:
    """Build a ZIP archive from an unpacked extension directory."""
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(extension_dir.rglob("*")):
            if file_path.is_dir():
                continue
            archive.write(file_path, arcname=file_path.relative_to(extension_dir))

    return buffer.getvalue()
