"""
UUID validation for identifiers used in filesystem paths and container names.

THREAT_MODEL C2.3: project_id must match the UUID pattern before it touches
any filesystem path or container name, preventing path-traversal attacks.
"""
from __future__ import annotations

import re

# DATA_MODEL §1: server-generated UUIDv4, validated before any path use
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def validate_project_id(project_id: str) -> str:
    """
    Validate that project_id is a well-formed UUIDv4 hex string.

    Returns the project_id unchanged if valid.
    Raises ValueError with a clear message if invalid.

    This MUST be called before project_id is used in:
      - filesystem path construction
      - Docker container/image naming
      - database queries that use the id in path-like operations
    """
    if not _UUID_PATTERN.match(project_id):
        raise ValueError(
            f"Invalid project_id: {project_id!r}. "
            "Expected a UUID v4 string (e.g. '550e8400-e29b-41d4-a716-446655440000')."
        )
    return project_id
