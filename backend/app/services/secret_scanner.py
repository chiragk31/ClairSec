"""
Exposed-secret detection for imported code (FEATURES.md F2 import notes).

Finds credentials committed to a repository (API keys, tokens, private keys,
connection strings with passwords) and reports WHERE they are and WHAT kind
they are. The secret value itself is never stored or displayed: only a masked
preview (first 4 + last 2 characters) leaves this module, so a report or a
projector never re-leaks someone's live key.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 512 * 1024
MAX_FINDINGS = 50
_SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}
_TEXT_SUFFIXES = {
    ".py", ".env", ".txt", ".md", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".js", ".ts", ".sh", ".ps1", ".dockerfile", ".properties", ".xml", ".html", "",
}

# (type, regex) — the first capture group is the secret value.
RULES: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key", re.compile(r"\b(AKIA[0-9A-Z]{16})\b")),
    ("GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,})\b")),
    ("OpenAI-style API key", re.compile(r"\b(sk-(?:proj-)?[A-Za-z0-9_-]{20,})\b")),
    ("Anthropic API key", re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{20,})\b")),
    ("Google API key", re.compile(r"\b(AIza[0-9A-Za-z_-]{35})\b")),
    ("Groq API key", re.compile(r"\b(gsk_[A-Za-z0-9]{20,})\b")),
    ("Slack token", re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{10,})\b")),
    ("Stripe secret key", re.compile(r"\b(sk_live_[A-Za-z0-9]{16,})\b")),
    ("Private key", re.compile(r"(-----BEGIN [A-Z ]*PRIVATE KEY-----)")),
    ("Database URL with password",
     re.compile(r"\b((?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis)://[^:\s/]+:[^@\s]+@[^\s'\"]+)")),
    ("JWT", re.compile(r"\b(eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,})\b")),
    ("Hard-coded secret assignment",
     re.compile(r"""(?i)\b(?:secret_key|api_key|apikey|access_token|auth_token|password|passwd)\s*[:=]\s*["']([^"'\s]{12,})["']""")),
]

_PLACEHOLDER = re.compile(r"(?i)(change[-_ ]?me|example|your[-_]|dummy|placeholder|xxxx|<.*>|\$\{|os\.environ|getenv)")


def mask(value: str) -> str:
    """Show just enough to recognise the key, never enough to use it."""
    v = value.strip()
    if v.startswith("-----BEGIN"):
        return "-----BEGIN … PRIVATE KEY----- (redacted)"
    if "://" in v and "@" in v:
        scheme = v.split("://", 1)[0]
        host = v.rsplit("@", 1)[1]
        return f"{scheme}://****:****@{host[:40]}"
    if len(v) <= 8:
        return "****"
    return f"{v[:4]}…{v[-2:]}"


def scan_tree(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if len(findings) >= MAX_FINDINGS:
            break
        rel = path.relative_to(root)
        if any(part in _SKIP_DIRS for part in rel.parts) or path.is_symlink() or not path.is_file():
            continue
        name = path.name.lower()
        if path.suffix.lower() not in _TEXT_SUFFIXES and not name.startswith(".env"):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for kind, rx in RULES:
                m = rx.search(line)
                if not m:
                    continue
                value = m.group(1)
                if kind == "Hard-coded secret assignment" and _PLACEHOLDER.search(value):
                    continue
                findings.append({
                    "type": kind,
                    "file": rel.as_posix(),
                    "line": lineno,
                    "preview": mask(value),
                })
                break
            if len(findings) >= MAX_FINDINGS:
                break
    return findings
