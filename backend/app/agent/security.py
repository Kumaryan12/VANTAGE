"""Content minimization and redaction, independent of model instructions."""

import re

from app.core.config import settings

SECRET_PATTERNS = [
    r"\bsk-[A-Za-z0-9_-]{12,}\b",
    r"(?i)\bBearer\s+[A-Za-z0-9._-]{8,}",
    r"(?i)(?:api[_ -]?key|api[_ -]?secret|access[_ -]?token|password)\s*[:=]\s*[^\s,;\"}]{4,}",
    r"(?i)postgres(?:ql)?(?:\+\w+)?://[^\s]+",
]


def redact(text: str) -> str:
    config = settings()
    for name in (
        "kite_api_key",
        "kite_api_secret",
        "alpha_vantage_api_key",
        "fred_api_key",
        "openai_api_key",
    ):
        value = getattr(config, name, "")
        if value and len(value) >= 4:
            text = text.replace(value, "[REDACTED]")
    for pattern in SECRET_PATTERNS:
        text = re.sub(pattern, "[REDACTED]", text)
    return text.replace("\x00", "")


def prohibited(question: str) -> bool:
    # Defense in depth: executable capabilities do not exist in the tool registry.
    return bool(
        re.search(
            r"(?i)\b(execute|place|submit|buy|sell)\b.{0,35}\b(order|trade|shares|stock)\b|\b(shell|sql|password|api.?key|access.?token|exfiltrat|ignore.{0,15}(rules|instructions)|promote.{0,20}champion)\b",
            question,
        )
    )
