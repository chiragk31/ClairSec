"""
Pre-flight secret deny-list and regex redaction (THREAT_MODEL C5.1, C5.2, C5.4, LLM.md §8).
Applied before ANY content enters a prompt or persistence layer.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path
import re
from typing import Sequence

# C5.1 Deny-list: filenames and patterns forbidden from LLM context
DENY_LIST_PATTERNS = [
    ".env*",
    "*.pem",
    "*.key",
    "id_*",
    "credentials*",
    "*.p12",
    "*.pkcs12",
    "*.crt",
    "*.der",
    "*.pfx",
    ".aws/*",
    ".git/*",
    "node_modules/*",
    "venv/*",
    ".venv/*",
]

# C5.2 Outbound Regex Scrubbers
REDACTION_RULES = [
    # AWS Access Key ID
    (re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), r"<redacted:aws_key>"),
    # GitHub personal access tokens
    (re.compile(r"\b(ghp_[a-zA-Z0-9]{36})\b"), r"<redacted:gh_token>"),
    # OpenAI / generic API keys
    (re.compile(r"\b(sk-[a-zA-Z0-9_-]{20,})\b"), r"<redacted:api_key>"),
    # Internal secret token patterns (including our fixture canary)
    (re.compile(r"\b(sec-[a-zA-Z0-9_-]{16,})\b"), r"<redacted:internal_key>"),
    (re.compile(r"\b(CANARY_SECRET_[A-Z0-9_-]+)\b"), r"<redacted:canary_secret>"),
    # Connection strings with inline passwords: proto://user:pass@host:port/db
    (
        re.compile(r"(mongodb(?:\+srv)?|postgres(?:ql)?|mysql)://([^:\s]+):([^@\s]+)@"),
        r"\1://\2:<redacted:password>@",
    ),
    # PEM Private Keys
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"),
        r"<redacted:private_key_pem>",
    ),
    # JWT tokens
    (
        re.compile(r"\beyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b"),
        r"<redacted:jwt>",
    ),
]


def is_file_denied(file_path: str | Path) -> bool:
    """Return True if the file matches any C5.1 deny-list pattern."""
    name = Path(file_path).name.lower()
    path_str = str(file_path).replace("\\", "/").lower()

    for pattern in DENY_LIST_PATTERNS:
        pat_lower = pattern.lower()
        if fnmatch.fnmatch(name, pat_lower) or fnmatch.fnmatch(path_str, f"*/{pat_lower}"):
            return True
        if "/*" in pat_lower:
            dir_part = pat_lower.split("/*")[0]
            if f"/{dir_part}/" in f"/{path_str}/":
                return True
    return False


def filter_allowed_files(files: Sequence[Path]) -> list[Path]:
    """Filter out any files that match the deny-list."""
    return [f for f in files if not is_file_denied(f)]


def redact_secrets(text: str) -> str:
    """
    Apply C5.2 regex scrubbers to sanitize outbound prompt text or evidence payloads.
    Synthetic principal tokens (alice-token-123, bob-token-456) are deliberately preserved
    per DATA_MODEL.md §4 exception.
    """
    if not text:
        return text

    scrubbed = text
    for pattern, replacement in REDACTION_RULES:
        scrubbed = pattern.sub(replacement, scrubbed)

    return scrubbed
