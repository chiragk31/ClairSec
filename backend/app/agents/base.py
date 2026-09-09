"""
Agent base class.

Per docs/ARCHITECTURE.md §5: use explicit states instead of relying on
informal LLM conversation.

State machine:
    CREATED → ANALYZING → TARGET_READY → ATTACKING → EVALUATING → FIXING → VERIFYING → COMPLETED
    Any state → FAILED | CANCELLED | PARTIAL

Only Builder's portion (CREATED → ANALYZING → COMPLETED/FAILED) is active in Phase 4.
The full machine is defined here so Attacker/Evaluator/Fixer can implement it without rework.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum


class AgentState(str, Enum):
    """
    Explicit states for the agent pipeline.
    Per docs/ARCHITECTURE.md §5.
    """
    CREATED = "created"
    ANALYZING = "analyzing"       # Builder is running
    TARGET_READY = "target_ready" # Builder done, target context stored
    ATTACKING = "attacking"       # Attacker is running
    EVALUATING = "evaluating"     # Evaluator is running
    FIXING = "fixing"             # Fixer is running
    VERIFYING = "verifying"       # Re-test is running
    COMPLETED = "completed"

    # Safe terminal states
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"           # Partial results available (some steps failed)


class AgentRole(str, Enum):
    """The four specialized agent roles."""
    BUILDER = "builder"
    ATTACKER = "attacker"
    EVALUATOR = "evaluator"
    FIXER = "fixer"


class BaseAgent(ABC):
    """
    Abstract base for all pipeline agents.

    Each concrete agent implements run() which advances the pipeline state
    and persists its output to MongoDB via the injected repository.

    Design note: agents are stateless Python objects — all state lives in MongoDB.
    This allows agents to be restarted, retried, or run headless for research.
    """

    @property
    @abstractmethod
    def role(self) -> AgentRole:
        """The role this agent fulfills in the pipeline."""

    @abstractmethod
    async def run(self, scan_id: str, project_id: str, **kwargs) -> AgentState:
        """
        Execute this agent's work for the given scan.

        Returns the resulting AgentState (COMPLETED, FAILED, PARTIAL, etc.).
        Implementations must:
          - Emit agent_events records during execution (even before Phase 9 WebSocket).
          - Persist their structured output to agent_context.
          - Never return without updating scan state.
          - Handle LLM provider errors with bounded retries.
        """
