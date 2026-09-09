"""
Fixer Agent package (PHASES.md Phase 7).
"""
from app.agents.fixer.fixer import FixerAgent
from app.agents.fixer.patch_engine import (
    DiffStats,
    PatchEngine,
    apply_hunks_to_content,
    validate_path_containment,
)
from app.agents.fixer.repository import PatchRepository
from app.agents.fixer.schemas import (
    FileDiff,
    FixerProposal,
    FixerResult,
    PatchRecord,
    PatchValidation,
)

__all__ = [
    "FixerAgent",
    "PatchEngine",
    "PatchRepository",
    "PatchRecord",
    "PatchValidation",
    "DiffStats",
    "FileDiff",
    "FixerProposal",
    "FixerResult",
    "apply_hunks_to_content",
    "validate_path_containment",
]
