"""Secret hygiene. Nothing that looks like a credential is ever persisted."""

from __future__ import annotations

import os
import re
from typing import Any

SECRET_ENV_KEYS = (
    "NVIDIA_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
    "CLOUDFLARE_API_TOKEN", "HF_TOKEN", "GITHUB_TOKEN", "GH_TOKEN",
    "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID",
)

SECRET_PATTERNS = [
    re.compile(r"nvapi-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"gsk_[A-Za-z0-9]{10,}"),
    re.compile(r"sk-or-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
]


def _env_secret_values() -> list[str]:
    vals = []
    for k in SECRET_ENV_KEYS:
        v = os.environ.get(k)
        if v and len(v) >= 8:
            vals.append(v)
    return vals


def redact_text(text: str) -> str:
    for v in _env_secret_values():
        text = text.replace(v, "[REDACTED]")
    for p in SECRET_PATTERNS:
        text = p.sub("[REDACTED]", text)
    return text


def redact(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if _is_secret_key(k) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    return obj


def _is_secret_key(key: Any) -> bool:
    k = str(key).lower()
    return any(t in k for t in ("api_key", "apikey", "token", "secret", "password", "authorization"))


def contains_secret(text: str) -> bool:
    return redact_text(text) != text
