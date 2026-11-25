"""Shared credential detection for captured and reviewed text."""

import os
import re

# These patterns intentionally favor false positives over returning credentials
# to an MCP client. They cover the providers configured by ITALIX plus common
# authorization and environment-variable forms.
_SECRET_PATTERNS = (
    re.compile(
        r"""(?i)(?:\b[A-Z][A-Z0-9_]*_)?(?:api[_-]?key|token|secret|password)["']?\s*[:=]\s*"""
        r"""(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;]+)"""
    ),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+"),
    re.compile(r"\b(?:sk-|gsk_)[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S),
)

_CREDENTIAL_VARIABLES = (
    "ITALIX_VIEWER_TOKEN", "ITALIX_OPERATOR_TOKEN", "ITALIX_OPERATOR_UNLOCK_SECRET",
    "ITALIX_SESSION_SECRET", "GEMINI_API_KEY", "GROQ_API_KEY",
)


def _configured_secrets():
    return [value for name in _CREDENTIAL_VARIABLES
            if len(value := os.getenv(name, "")) >= 12]


def redact(value: str) -> str:
    result = value
    for secret in sorted(_configured_secrets(), key=len, reverse=True):
        result = result.replace(secret, "[REDACTED]")
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def contains_secret(value: str) -> bool:
    return any(secret in value for secret in _configured_secrets()) or any(
        pattern.search(value) for pattern in _SECRET_PATTERNS
    )
