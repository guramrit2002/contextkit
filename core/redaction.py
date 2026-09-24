"""Secret redaction utilities for contextkit."""
import re
from typing import Optional


class SecretRedactor:
    """Redacts sensitive information from text."""

    # Common secret patterns
    PATTERNS = [
        # API keys and tokens
        r"(?i)(api[_-]?key|token|secret|password)[=:\s]+([^\s,;'\"]*)",
        # AWS patterns
        r"AKIA[0-9A-Z]{16}",
        r"aws_secret_access_key[=:\s]+([^\s,;'\"]*)",
        # GitHub patterns
        r"gh[pousr]_[A-Za-z0-9_]{36,255}",
        # Generic URL credentials
        r"https?://[^:]+:([^@]+)@",
        # SSH keys (private key markers)
        r"-----BEGIN (RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY",
    ]

    @staticmethod
    def redact(text: str) -> str:
        """Redact secrets from text."""
        if not text or not isinstance(text, str):
            return text

        redacted = text
        for pattern in SecretRedactor.PATTERNS:
            try:
                redacted = re.sub(
                    pattern,
                    "[REDACTED]",
                    redacted,
                    flags=re.IGNORECASE | re.MULTILINE,
                )
            except re.error as e:
                # Log but don't fail on invalid patterns
                continue

        return redacted

    @staticmethod
    def redact_dict(data: dict) -> dict:
        """Redact secrets from a dictionary."""
        redacted = {}
        for key, value in data.items():
            if isinstance(value, str):
                redacted[key] = SecretRedactor.redact(value)
            elif isinstance(value, dict):
                redacted[key] = SecretRedactor.redact_dict(value)
            elif isinstance(value, list):
                redacted[key] = [
                    SecretRedactor.redact(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                redacted[key] = value
        return redacted


def validate_project_id(project_id: Optional[str]) -> str:
    """Validate project ID format."""
    if not project_id:
        raise ValueError("Project ID cannot be empty")

    if not isinstance(project_id, str):
        raise TypeError("Project ID must be a string")

    if len(project_id) > 500:
        raise ValueError("Project ID is too long (max 500 characters)")

    if project_id.startswith("."):
        raise ValueError("Project ID cannot start with a dot")

    return project_id


def validate_text(text: Optional[str], field_name: str, max_length: int = 10000) -> Optional[str]:
    """Validate text input."""
    if text is None:
        return None

    if not isinstance(text, str):
        raise TypeError(f"{field_name} must be a string")

    text = text.strip()

    if len(text) == 0:
        raise ValueError(f"{field_name} cannot be empty")

    if len(text) > max_length:
        raise ValueError(f"{field_name} exceeds maximum length of {max_length} characters")

    return text
