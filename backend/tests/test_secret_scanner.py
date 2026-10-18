"""Exposed-secret detection on import: finds keys, never stores or shows the full value."""
from pathlib import Path

from app.services.secret_scanner import mask, scan_tree

AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
GH = "ghp_" + "a" * 36


def test_finds_secrets_with_masked_previews_only(tmp_path: Path):
    (tmp_path / "config.py").write_text(f'AWS_KEY = "{AWS}"\nAPI_KEY = "change-me-please-123"\n')
    (tmp_path / ".env").write_text(f"GITHUB_TOKEN={GH}\nDATABASE_URL=postgres://admin:hunter2pass@db.local/app\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text(f'k="{AWS}"')
    found = scan_tree(tmp_path)
    kinds = {(f["file"], f["type"]) for f in found}
    assert ("config.py", "AWS access key") in kinds
    assert (".env", "GitHub token") in kinds
    assert (".env", "Database URL with password") in kinds
    assert not any(f["file"].startswith("node_modules") for f in found)
    assert not any("change-me" in f["preview"] for f in found)          # placeholders ignored
    blob = repr(found)
    assert AWS not in blob and GH not in blob and "hunter2pass" not in blob  # never the raw value
    assert any(f["preview"] == "AKIA…OP" for f in found)


def test_mask_never_reveals_usable_value():
    assert mask("short") == "****"
    assert "s3cr3t" not in mask("mongodb://root:s3cr3t@host:27017/db")
