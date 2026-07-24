from __future__ import annotations

from typing import Any


MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_UPLOAD_BATCH_BYTES = 100 * 1024 * 1024


class UploadTooLargeError(ValueError):
    pass


def read_upload_bytes(file: Any, *, limit: int = MAX_UPLOAD_BYTES) -> bytes:
    declared_size = getattr(file, "content_length", None)
    try:
        parsed_size = int(declared_size) if declared_size is not None else 0
    except (TypeError, ValueError):
        parsed_size = 0
    if parsed_size > limit:
        raise UploadTooLargeError(f"File exceeds the {format_byte_limit(limit)} limit.")

    content = file.read(limit + 1)
    if len(content) > limit:
        raise UploadTooLargeError(f"File exceeds the {format_byte_limit(limit)} limit.")
    return content


def format_byte_limit(value: int) -> str:
    return f"{max(0, int(value)) // (1024 * 1024)} MiB"
