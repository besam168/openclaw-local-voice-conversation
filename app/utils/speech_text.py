from __future__ import annotations

import re
from typing import Any


_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MARKDOWN_MARK_RE = re.compile(r"[*_#>~]+")
_WHITESPACE_RE = re.compile(r"\s+")


def cleanup_for_speech(text: Any, *, max_chars: int = 700) -> str:
    """Make model output friendlier for TTS without changing the saved text reply."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    cleaned = _CODE_FENCE_RE.sub("这里有一段代码，已省略朗读。", cleaned)
    cleaned = _INLINE_CODE_RE.sub(r"\1", cleaned)
    cleaned = _MARKDOWN_LINK_RE.sub(r"\1", cleaned)
    cleaned = _URL_RE.sub("链接", cleaned)
    cleaned = cleaned.replace("|", "，")
    cleaned = cleaned.replace("- [ ]", "").replace("- [x]", "")
    cleaned = _MARKDOWN_MARK_RE.sub("", cleaned)

    lines = []
    for line in cleaned.splitlines():
        stripped = line.strip(" \t-•0123456789.、")
        if stripped:
            lines.append(stripped)
    cleaned = "，".join(lines) if lines else cleaned
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()

    if max_chars > 0 and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip("，。,. ") + "。后面内容较长，我先读到这里。"
    return cleaned
