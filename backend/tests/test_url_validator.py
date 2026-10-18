"""
Tests for URL validator (FEATURES.md F2 exit gate).

Requires >= 25 test cases covering all security boundaries:
- https only (rejects http, file://, ext::, git@, ssh://, ftp, javascript)
- host allowlist (rejects spoofed subdomains like github.com.evil.com)
- no credentials/userinfo
- no ports
- no query or fragments
- no path traversal (..)
- no IDN homographs
- flags / command injection refused
- ref validation
"""
import pytest

from app.services.url_validator import GitUrlInfo, is_valid_github_url, validate_github_url

TEST_CASES = [
    # ── Valid URLs ──────────────────────────────────────────────────────────
    ("https://github.com/tiangolo/fastapi", None, True, "tiangolo", "fastapi"),
    ("https://github.com/encode/starlette.git", None, True, "encode", "starlette"),
    ("https://github.com/owner-name/repo_name.1", None, True, "owner-name", "repo_name.1"),
    ("https://github.com/owner/repo/", None, True, "owner", "repo"),
    ("https://github.com/org.team/app-service_v2.git/", None, True, "org.team", "app-service_v2"),
    ("https://github.com/owner/repo", "main", True, "owner", "repo"),
    ("https://github.com/owner/repo", "v1.2.3", True, "owner", "repo"),
    ("https://github.com/owner/repo", "feature/my-branch_v1", True, "owner", "repo"),
    ("https://github.com/owner/repo", "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2", True, "owner", "repo"),

    # ── Forbidden Protocols & Schemes ────────────────────────────────────────
    ("http://github.com/owner/repo", None, False, None, None),
    ("file:///etc/passwd", None, False, None, None),
    ("file://localhost/d:/repo", None, False, None, None),
    ("ext::sh -c evil", None, False, None, None),
    ("git@github.com:owner/repo.git", None, False, None, None),
    ("ssh://git@github.com/owner/repo", None, False, None, None),
    ("ftp://github.com/owner/repo", None, False, None, None),
    ("javascript:alert(1)", None, False, None, None),

    # ── Credentials & Userinfo ───────────────────────────────────────────────
    ("https://user:pw@github.com/owner/repo", None, False, None, None),
    ("https://token@github.com/owner/repo", None, False, None, None),

    # ── Spoofed Hosts & Non-Allowlisted Hosts ────────────────────────────────
    ("https://github.com.evil.com/owner/repo", None, False, None, None),
    ("https://evil-github.com/owner/repo", None, False, None, None),
    ("https://notgithub.org/owner/repo", None, False, None, None),
    ("https://[::1]/owner/repo", None, False, None, None),
    ("https://127.0.0.1/owner/repo", None, False, None, None),
    ("https://gith\u0443b.com/owner/repo", None, False, None, None),  # Cyrillic 'у' (U+0443) homograph

    # ── Ports, Queries, Fragments ────────────────────────────────────────────
    ("https://github.com:443/owner/repo", None, False, None, None),
    ("https://github.com:8080/owner/repo", None, False, None, None),
    ("https://github.com/owner/repo?token=secret", None, False, None, None),
    ("https://github.com/owner/repo#readme", None, False, None, None),

    # ── Path Traversal & Malformed Paths ─────────────────────────────────────
    ("https://github.com/owner/repo/../evil/repo", None, False, None, None),
    ("https://github.com/owner/repo/sub/dir", None, False, None, None),
    ("https://github.com/owner", None, False, None, None),
    ("https://github.com/", None, False, None, None),
    ("https://github.com", None, False, None, None),
    ("https://github.com/./repo", None, False, None, None),

    # ── Command Injection / Flags ────────────────────────────────────────────
    ("--upload-pack=evil", None, False, None, None),
    ("-oProxyCommand=evil", None, False, None, None),
    ("https://github.com/owner/repo;rm -rf /", None, False, None, None),
    ("https://github.com/owner/repo|sh", None, False, None, None),
    ("https://github.com/owner/repo `id`", None, False, None, None),

    # ── Ref Security Violations ──────────────────────────────────────────────
    ("https://github.com/owner/repo", "--upload-pack", False, None, None),
    ("https://github.com/owner/repo", "-b", False, None, None),
    ("https://github.com/owner/repo", "branch with spaces", False, None, None),
    ("https://github.com/owner/repo", "branch;evil", False, None, None),
    ("https://github.com/owner/repo", "heads/../../etc/passwd", False, None, None),
    ("https://github.com/owner/repo", "a" * 101, False, None, None),
]


def test_url_validator_cases_count():
    """V3 exit gate requires >= 25 test cases."""
    assert len(TEST_CASES) >= 25, f"Expected >= 25 test cases, got {len(TEST_CASES)}"


@pytest.mark.parametrize("url,ref,is_valid,expected_owner,expected_repo", TEST_CASES)
def test_url_validator_table(url, ref, is_valid, expected_owner, expected_repo):
    valid, err = is_valid_github_url(url, ref=ref)
    assert valid == is_valid, f"URL '{url}' (ref={ref}) expected valid={is_valid}, got err: {err}"

    if is_valid:
        info = validate_github_url(url, ref=ref)
        assert isinstance(info, GitUrlInfo)
        assert info.owner == expected_owner
        assert info.repo == expected_repo
        assert info.normalized_url == f"https://github.com/{expected_owner}/{expected_repo}"
        if ref:
            assert info.ref == ref
    else:
        with pytest.raises(ValueError):
            validate_github_url(url, ref=ref)
