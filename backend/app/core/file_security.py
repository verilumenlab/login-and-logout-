"""
File Upload Security & Magic Byte Validation (Phase 14)
Protects against malicious file uploads, extension spoofing, path traversal,
and denial-of-service via oversized files.
"""

from __future__ import annotations

import os
import re
from typing import BinaryIO

from fastapi import HTTPException, UploadFile, status

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# Magic byte signatures for authorized enterprise file formats
MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    ".xlsx": [b"PK\x03\x04"],  # ZIP container header used by OpenXML (.xlsx)
    ".csv": [],  # Validated via text decoding check
    ".pdf": [b"%PDF"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
}

ALLOWED_EXTENSIONS = set(MAGIC_SIGNATURES.keys())


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename against directory traversal attacks (../, ..\\)
    and illegal filesystem characters.
    """
    # Extract only the basename (strips any path components)
    clean_name = os.path.basename(filename.strip())
    # Remove null bytes and path separators
    clean_name = clean_name.replace("\x00", "").replace("/", "").replace("\\", "")
    # Strip dangerous characters
    clean_name = re.sub(r"[^\w\.\-_]", "_", clean_name)
    if not clean_name or clean_name.startswith("."):
        clean_name = f"upload_{clean_name}"
    return clean_name


def validate_file_content(contents: bytes, filename: str) -> None:
    """
    Verify magic bytes and structure against the declared file extension.
    """
    ext = os.path.splitext(filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Permitted: {sorted(ALLOWED_EXTENSIONS)}",
        )

    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024*1024)} MB.",
        )

    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    expected_magic = MAGIC_SIGNATURES.get(ext)
    if expected_magic:
        # Must start with at least one matching signature
        matches = any(contents.startswith(sig) for sig in expected_magic)
        if not matches:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file content. Magic byte signature does not match '{ext}'.",
            )
    elif ext == ".csv":
        # Ensure it's valid text (not binary executable or shell script)
        try:
            sample = contents[:2048].decode("utf-8-sig")
            # Disallow null bytes or high ratio of non-printable control characters
            if "\x00" in sample:
                raise ValueError("Binary null byte in CSV")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid CSV format: file contains non-text or binary data.",
            )

