"""
Single conversion from Pydantic models to stored documents.

Enum members are stored as their plain values. Real MongoDB already does this for
str-based enums, but the in-memory fallback (mongomock) stores the Python objects,
so without this the app behaved differently in Demo/memory mode (statuses read
back as "EvaluationStatus.CONFIRMED"). Datetimes are left as datetimes so
existing MongoDB data keeps its types and sort order.
"""
from __future__ import annotations

from enum import Enum
from typing import Any


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def to_document(model: Any) -> dict[str, Any]:
    data = model.model_dump() if hasattr(model, "model_dump") else dict(model)
    return _plain(data)
