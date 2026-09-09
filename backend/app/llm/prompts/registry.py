"""
File-based versioned prompt registry with startup SHA-256 digest (LLM.md §4).
Prompts are files, immutable once used in experiment runs.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, Tuple

PROMPTS_DIR = Path(__file__).resolve().parent


class PromptNotFoundError(KeyError):
    """Raised when a requested prompt ID and version does not exist."""


class PromptRegistry:
    """Singleton prompt registry loaded and frozen at initialization."""

    def __init__(self, root_dir: Path = PROMPTS_DIR):
        self._root_dir = root_dir
        self._prompts: dict[tuple[str, str], str] = {}
        self._digest: str = ""
        self._load_and_compute_digest()

    def _load_and_compute_digest(self) -> None:
        """Load all .md prompt files recursively and compute startup SHA-256."""
        hasher = hashlib.sha256()
        loaded: dict[tuple[str, str], str] = {}

        for md_file in sorted(self._root_dir.glob("*/*.md")):
            # Expected name: {agent}/{name}.{version}.md
            agent_dir = md_file.parent.name
            parts = md_file.stem.split(".")
            if len(parts) >= 2:
                name = ".".join(parts[:-1])
                version = parts[-1]
            else:
                name = parts[0]
                version = "v1"

            prompt_id = f"{agent_dir}.{name}"
            content = md_file.read_text(encoding="utf-8").strip()
            loaded[(prompt_id, version)] = content

        self._prompts = loaded

        # Hash prompt keys and contents in deterministic order
        for (p_id, ver), text in sorted(self._prompts.items()):
            hasher.update(f"{p_id}:{ver}\n{text}\n".encode("utf-8"))

        self._digest = hasher.hexdigest()

    @property
    def digest(self) -> str:
        """SHA-256 digest of all loaded prompts at startup."""
        return self._digest

    def get_prompt(self, prompt_id: str, version: str, **kwargs: str) -> str:
        """Retrieve and format a versioned prompt template with named parameters."""
        key = (prompt_id, version)
        if key not in self._prompts:
            raise PromptNotFoundError(
                f"Prompt '{prompt_id}' version '{version}' not found in registry."
            )

        template = self._prompts[key]
        if kwargs:
            return template.format(**kwargs)
        return template

    def list_prompts(self) -> list[tuple[str, str]]:
        return sorted(self._prompts.keys())


# Global singleton instance
registry = PromptRegistry()
