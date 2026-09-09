"""
Pure Python unified diff parser, validator, and applier.
(THREAT_MODEL.md C2.1, C2.2, C2.4, T8, DATA_MODEL.md §2 & §3, LLM.md §6 capability starvation).

Zero shell execution. Zero exec().
Strict path containment inside modified_workspace/.
Pre-apply AST validation and 256 KB diff ceiling enforcement.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
import re
from typing import Any

from app.agents.fixer.schemas import DiffStats, PatchValidation

logger = logging.getLogger(__name__)

# Size limit per DATA_MODEL.md §2: 256 KB cap, reject-and-record
DIFF_SIZE_CAP_BYTES = 256 * 1024


class PatchEngineError(Exception):
    """Base exception for patch engine errors."""
    pass


class PathContainmentError(PatchEngineError):
    """Raised when a target path resolves outside modified_workspace (C2.1)."""
    pass


class SymlinkSecurityError(PatchEngineError):
    """Raised when a target path involves a symlink (C2.2)."""
    pass


class HallucinatedPathError(PatchEngineError):
    """Raised when a target path does not exist in workspace inventory (C2.4)."""
    pass


class PatchTooLargeError(PatchEngineError):
    """Raised when diff exceeds the 256 KB ceiling (T8, DATA_MODEL.md §2)."""
    pass


class UnparseablePatchError(PatchEngineError):
    """Raised when the patched source code fails AST parsing (T8)."""
    pass


class DiffApplicationError(PatchEngineError):
    """Raised when unified diff cannot be applied to original text."""
    pass


def extract_target_path(diff_text: str, fallback_path: str = "") -> str:
    """
    Extract the relative target path from unified diff headers (--- / +++).
    Strips 'a/' and 'b/' git prefixes if present.
    """
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            raw = line[4:].strip()
            # e.g., "b/main.py" or "main.py" or "/dev/null"
            if raw.startswith("b/"):
                raw = raw[2:]
            elif raw.startswith("a/"):
                raw = raw[2:]
            # Strip timestamp if present (tab separated)
            raw = raw.split("\t")[0].strip()
            if raw and raw != "/dev/null":
                return raw
        elif line.startswith("--- ") and not fallback_path:
            raw = line[4:].strip()
            if raw.startswith("a/"):
                raw = raw[2:]
            raw = raw.split("\t")[0].strip()
            if raw and raw != "/dev/null":
                fallback_path = raw
    return fallback_path


def validate_path_containment(
    rel_path: str,
    modified_root: Path,
    inventory_files: set[str] | None = None,
) -> tuple[bool, Path | None, str]:
    """
    Verify path containment (THREAT_MODEL.md C2.1, C2.2, C2.4):
    1. Resolved path must be strictly inside modified_root (C2.1).
    2. Symlinks must not be followed (C2.2).
    3. File must exist in workspace inventory (C2.4 / No invented files).
    """
    clean_rel = rel_path.replace("\\", "/").strip()
    if clean_rel.startswith("a/") or clean_rel.startswith("b/"):
        clean_rel = clean_rel[2:]
    clean_rel = clean_rel.lstrip("/")

    # Disallow empty or bare dot paths
    if not clean_rel or clean_rel == ".":
        return False, None, "path_containment_violation: empty relative path"

    resolved_root = modified_root.resolve()
    candidate_path = resolved_root / clean_rel

    # C2.2: Symlinks inside workspace are not followed (check candidate_path before resolve)
    curr = candidate_path
    while curr != resolved_root and curr != curr.parent:
        if curr.is_symlink():
            return False, None, f"symlink_detected: symlink in path {curr}"
        curr = curr.parent

    target_abs = candidate_path.resolve()

    # C2.1: Must be relative to modified_root
    try:
        if not target_abs.is_relative_to(resolved_root):
            return (
                False,
                None,
                f"path_outside_workspace: {rel_path} resolves to {target_abs} outside {resolved_root}",
            )
    except AttributeError:
        # Python < 3.9 fallback if any
        if not str(target_abs).startswith(str(resolved_root)):
            return False, None, f"path_outside_workspace: {rel_path} outside {resolved_root}"

    # C2.4: Target path must exist in inventory
    if inventory_files is not None:
        normalized_inventory = {f.replace("\\", "/").lstrip("/") for f in inventory_files}
        # Also allow filename matching if relative path has directory prefix
        if (
            clean_rel not in normalized_inventory
            and Path(clean_rel).name not in normalized_inventory
            and not target_abs.exists()
        ):
            return (
                False,
                None,
                f"hallucinated_path: {clean_rel} not found in workspace inventory",
            )

    return True, target_abs, ""


def apply_hunks_to_content(original_content: str, diff_text: str) -> tuple[str, DiffStats]:
    """
    Apply unified diff hunks to original file content in memory.
    Pure Python line-by-line application with fuzzy context alignment.
    """
    orig_lines = original_content.splitlines(keepends=False)
    diff_lines = diff_text.splitlines(keepends=False)

    hunk_regex = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    hunks: list[tuple[int, list[str]]] = []
    current_hunk_lines: list[str] = []
    current_old_start = 0

    added_count = 0
    removed_count = 0

    for line in diff_lines:
        match = hunk_regex.match(line)
        if match:
            if current_hunk_lines:
                hunks.append((current_old_start, current_hunk_lines))
                current_hunk_lines = []
            current_old_start = int(match.group(1))
        elif current_old_start > 0:
            if line.startswith(("+", "-", " ")):
                current_hunk_lines.append(line)
                if line.startswith("+"):
                    added_count += 1
                elif line.startswith("-"):
                    removed_count += 1

    if current_hunk_lines:
        hunks.append((current_old_start, current_hunk_lines))

    if not hunks:
        raise DiffApplicationError("No valid @@ hunk headers found in diff")

    result_lines = list(orig_lines)
    offset = 0

    for old_start, hunk in hunks:
        # Determine expected context and deletions
        expected_old_chunk: list[str] = []
        replacement_chunk: list[str] = []

        for h_line in hunk:
            tag = h_line[0]
            val = h_line[1:]
            if tag == " ":
                expected_old_chunk.append(val)
                replacement_chunk.append(val)
            elif tag == "-":
                expected_old_chunk.append(val)
            elif tag == "+":
                replacement_chunk.append(val)

        # Target index in result_lines
        nominal_idx = (old_start - 1) + offset

        # Search for matching position in result_lines
        matched_idx = -1
        search_radius = max(10, len(result_lines))

        # Check nominal position first
        if 0 <= nominal_idx <= len(result_lines) - len(expected_old_chunk):
            slice_to_check = result_lines[nominal_idx : nominal_idx + len(expected_old_chunk)]
            if [s.rstrip() for s in slice_to_check] == [s.rstrip() for s in expected_old_chunk]:
                matched_idx = nominal_idx

        # If not matched, search within window
        if matched_idx == -1:
            best_dist = 999999
            for i in range(len(result_lines) - len(expected_old_chunk) + 1):
                slice_to_check = result_lines[i : i + len(expected_old_chunk)]
                if [s.rstrip() for s in slice_to_check] == [s.rstrip() for s in expected_old_chunk]:
                    dist = abs(i - nominal_idx)
                    if dist < best_dist:
                        best_dist = dist
                        matched_idx = i

        if matched_idx == -1:
            raise DiffApplicationError(
                f"Failed to align hunk at nominal line {old_start}. Expected context:\n"
                + "\n".join(expected_old_chunk[:5])
            )

        # Splice in the replacement
        result_lines[matched_idx : matched_idx + len(expected_old_chunk)] = replacement_chunk
        offset += len(replacement_chunk) - len(expected_old_chunk)

    new_text = "\n".join(result_lines)
    if original_content.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"

    stats = DiffStats(files=1, added=added_count, removed=removed_count)
    return new_text, stats


class PatchEngine:
    """
    Coordinates pre-apply validation, AST checks, and atomic file modification.
    """

    def __init__(self, modified_root: Path, inventory_files: set[str] | None = None):
        self.modified_root = Path(modified_root).resolve()
        self.inventory_files = inventory_files

    def evaluate_and_apply(
        self,
        rel_path: str,
        diff_text: str,
        dry_run: bool = False,
    ) -> tuple[bool, PatchValidation, DiffStats, str | None, str | None]:
        """
        Validate and apply patch to file under modified_root.
        Returns:
            (applied: bool, validation: PatchValidation, stats: DiffStats, new_content: str|None, error: str|None)
        """
        validation = PatchValidation(
            ast_parsed=False,
            path_check_passed=False,
            size_ok=False,
        )
        empty_stats = DiffStats()

        # Step 1: Check diff size cap (DATA_MODEL.md §2, T8)
        diff_bytes = diff_text.encode("utf-8")
        if len(diff_bytes) > DIFF_SIZE_CAP_BYTES:
            validation.size_ok = False
            return (
                False,
                validation,
                empty_stats,
                None,
                f"patch_too_large: diff size {len(diff_bytes)} bytes exceeds 256 KB ceiling",
            )
        validation.size_ok = True

        # Step 2: Resolve target path from diff header or rel_path
        target_path_str = extract_target_path(diff_text, fallback_path=rel_path)
        if not target_path_str:
            target_path_str = rel_path

        # Step 3: Path containment checks (C2.1, C2.2, C2.4)
        is_path_ok, target_abs, path_err = validate_path_containment(
            target_path_str,
            self.modified_root,
            inventory_files=self.inventory_files,
        )
        if not is_path_ok or target_abs is None:
            validation.path_check_passed = False
            return False, validation, empty_stats, None, path_err
        validation.path_check_passed = True

        # Target file must exist on disk in modified_root
        if not target_abs.exists():
            validation.path_check_passed = False
            return (
                False,
                validation,
                empty_stats,
                None,
                f"file_not_found: target {target_abs} does not exist in modified_workspace",
            )

        # Step 4: Read current content
        try:
            current_content = target_abs.read_text(encoding="utf-8")
        except Exception as exc:
            return (
                False,
                validation,
                empty_stats,
                None,
                f"read_error: failed to read {target_abs}: {exc}",
            )

        # Step 5: Apply hunks in memory
        try:
            new_content, stats = apply_hunks_to_content(current_content, diff_text)
        except Exception as exc:
            return (
                False,
                validation,
                empty_stats,
                None,
                f"diff_apply_error: {exc}",
            )

        # Step 6: AST syntax validation on patched source (T8)
        if target_abs.suffix == ".py":
            try:
                ast.parse(new_content, filename=target_abs.name)
                validation.ast_parsed = True
            except SyntaxError as exc:
                validation.ast_parsed = False
                return (
                    False,
                    validation,
                    stats,
                    None,
                    f"unparseable_patch_syntax_error: {exc.msg} at line {exc.lineno}",
                )
        else:
            validation.ast_parsed = True

        # Step 7: Write to disk in modified_workspace (if not dry_run)
        if not dry_run:
            try:
                target_abs.write_text(new_content, encoding="utf-8")
                logger.info("Successfully patched %s in modified_workspace", target_abs)
            except Exception as exc:
                return (
                    False,
                    validation,
                    stats,
                    None,
                    f"write_error: failed to write {target_abs}: {exc}",
                )

        return True, validation, stats, new_content, None
