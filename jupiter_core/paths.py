"""Canonicalise a file path so two teammates claiming the same file land on
the same string.

Ported from jupiter-code's lib/paths.ts.

  * ``./a.py`` and ``src/../src/a.py`` resolve to ``a.py`` and ``src/a.py``;
  * paths are NFC-normalised;
  * control characters (including null bytes) are rejected;
  * length is capped.

Case sensitivity is deliberately kept: on Linux ``src/App.py`` and
``src/app.py`` really are two different files.
"""

from __future__ import annotations

import re
import unicodedata

from .errors import unprocessable

MAX_PATH_LENGTH = 1024

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def normalize_path(file_path: str | None) -> str:
    trimmed = (file_path or "").strip()

    if len(trimmed) > MAX_PATH_LENGTH:
        raise unprocessable(f"file_path must be at most {MAX_PATH_LENGTH} characters")
    if _CONTROL_CHARS.search(trimmed):
        raise unprocessable("file_path must not contain control characters")

    cleaned = unicodedata.normalize("NFC", trimmed).replace("\\", "/")
    is_absolute = cleaned.startswith("/")

    out: list[str] = []
    for segment in cleaned.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if out and out[-1] != "..":
                out.pop()
            elif not is_absolute:
                out.append("..")
            continue
        out.append(segment)

    normalized = ("/" if is_absolute else "") + "/".join(out)
    if len(out) == 0:
        raise unprocessable("file_path must not be empty")
    if len(normalized) > MAX_PATH_LENGTH:
        raise unprocessable(f"file_path must be at most {MAX_PATH_LENGTH} characters")
    return normalized
