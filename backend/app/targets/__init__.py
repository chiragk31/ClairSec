"""Target access abstractions and test seams for ClairSec."""
from app.targets.handle import (
    TargetHandle,
    ContainerTargetHandle,
    LocalFixtureTargetHandle,
    TargetAccessForbiddenError,
)

__all__ = [
    "TargetHandle",
    "ContainerTargetHandle",
    "LocalFixtureTargetHandle",
    "TargetAccessForbiddenError",
]
