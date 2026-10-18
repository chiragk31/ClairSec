r"""
GitHub repository URL and ref validator (FEATURES.md F2, THREAT_MODEL C2).

Enforces:
- Scheme must be https only (rejects http, file, git, ssh, ext, etc.)
- Host must be in settings.git_allowed_hosts (default github.com)
- Path must strictly match ^/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(\.git)?/?$
- No userinfo (user:pass@)
- No explicit ports (:443, :8000, etc.)
- No query strings (?foo=bar)
- No URL fragments (#readme)
- No path traversal (..)
- No non-ASCII hostnames (IDN homograph protection)
- Optional ref must match ^[A-Za-z0-9._/-]{1,100}$ and must not start with '-'
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

from app.core.config import settings

_PATH_REGEX = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(\.git)?/?$")
_REF_REGEX = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")


@dataclass(frozen=True)
class GitUrlInfo:
    url: str
    normalized_url: str
    owner: str
    repo: str
    ref: str | None = None


def validate_github_url(url: str, ref: str | None = None, allowed_hosts: list[str] | None = None) -> GitUrlInfo:
    """
    Validate a public GitHub URL and optional git ref.

    Raises ValueError with a human-readable reason on any violation.
    Returns a GitUrlInfo on success.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string.")

    raw_url = url.strip()

    # Reject leading dashes / flags
    if raw_url.startswith("-"):
        raise ValueError("URL cannot start with a dash or flag.")

    # Reject whitespace or control characters
    if any(c.isspace() or ord(c) < 32 for c in raw_url):
        raise ValueError("URL contains illegal characters or whitespace.")

    # Reject dangerous protocols upfront
    for prefix in ("file:", "ext:", "git@", "ssh:", "ftp:", "javascript:"):
        if raw_url.lower().startswith(prefix):
            raise ValueError(f"Scheme not permitted: URL starts with '{prefix}'. Only HTTPS is allowed.")

    try:
        parsed = urllib.parse.urlsplit(raw_url)
    except Exception as exc:
        raise ValueError(f"Malformed URL: {exc}") from exc

    # 1. Scheme must be strictly https
    if parsed.scheme.lower() != "https":
        raise ValueError(f"Scheme must be 'https', got '{parsed.scheme}'.")

    # 2. Reject userinfo (username / password in URL)
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise ValueError("Userinfo (credentials in URL) is strictly prohibited.")

    # 3. Reject explicit port
    if parsed.port is not None or ":" in parsed.netloc:
        raise ValueError("Explicit ports in repository URLs are prohibited.")

    # 4. Reject query string
    if parsed.query:
        raise ValueError("Query parameters in repository URLs are prohibited.")

    # 5. Reject fragment
    if parsed.fragment:
        raise ValueError("Fragments (#) in repository URLs are prohibited.")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("URL must include a valid hostname.")

    # 6. Reject non-ASCII hostname (IDN homograph protection)
    try:
        hostname.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError("Non-ASCII hostnames are prohibited (potential homograph attack).")

    # 7. Host must be in allowed_hosts
    hosts = allowed_hosts if allowed_hosts is not None else settings.git_allowed_hosts
    normalized_hosts = [h.lower() for h in hosts]
    if hostname not in normalized_hosts:
        raise ValueError(f"Host '{hostname}' is not in the allowed git hosts: {normalized_hosts}")

    # 8. Path traversal and segments check
    path = parsed.path
    if ".." in path:
        raise ValueError("Path traversal ('..') is strictly prohibited.")

    match = _PATH_REGEX.match(path)
    if not match:
        raise ValueError(
            f"Invalid repository path '{path}'. Expected format: '/<owner>/<repo>' with alphanumeric, "
            "dot, dash, or underscore characters only."
        )

    owner, repo, _ = match.groups()
    if owner in (".", "..") or repo in (".", ".."):
        raise ValueError("Owner and repository names cannot be '.' or '..'.")

    # 9. Ref validation (branch, tag, commit SHA)
    validated_ref: str | None = None
    if ref is not None and ref.strip() != "":
        clean_ref = ref.strip()
        if clean_ref.startswith("-"):
            raise ValueError("Git ref cannot start with a dash or flag.")
        if not _REF_REGEX.match(clean_ref):
            raise ValueError(
                f"Invalid git ref '{clean_ref}'. Must be 1-100 characters matching [A-Za-z0-9._/-]."
            )
        if ".." in clean_ref:
            raise ValueError("Git ref cannot contain '..'.")
        validated_ref = clean_ref

    normalized_url = f"https://{hostname}/{owner}/{repo}"

    return GitUrlInfo(
        url=raw_url,
        normalized_url=normalized_url,
        owner=owner,
        repo=repo,
        ref=validated_ref,
    )


def is_valid_github_url(url: str, ref: str | None = None, allowed_hosts: list[str] | None = None) -> tuple[bool, str | None]:
    """
    Convenience function returning (is_valid, error_message).
    """
    try:
        validate_github_url(url, ref=ref, allowed_hosts=allowed_hosts)
        return True, None
    except ValueError as e:
        return False, str(e)
