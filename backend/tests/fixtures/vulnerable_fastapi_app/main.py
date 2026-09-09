"""
Vulnerable FastAPI Application — Reference Fixture for ClairSec Benchmark & Agents.
Contains three seeded vulnerabilities per VULN_TAXONOMY.md §4:
  1. BOLA (CWE-639) at GET /documents/{doc_id}
  2. BOPLA_MASS_ASSIGN (CWE-915) at PUT /users/{user_id}/profile
  3. SECURITY_MISCONFIG (CWE-16) at GET /debug/config
"""
from __future__ import annotations

import copy
from typing import Any
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

app = FastAPI(
    title="Notes & Identity API (Vulnerable)",
    version="1.0.0",
    debug=True,  # SECURITY_MISCONFIG: Debug mode enabled in production build
)

# SECURITY_MISCONFIG: Wildcard CORS with credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# In-memory test store & Principals (BOLA and BFLA requirement)
# ─────────────────────────────────────────────────────────────────────────────

INITIAL_USERS: dict[str, dict[str, Any]] = {
    "usr_alice_01": {
        "user_id": "usr_alice_01",
        "username": "alice",
        "token": "Bearer alice-token-123",
        "display_name": "Alice Smith",
        "bio": "Security enthusiast & note-taker.",
        "role": "member",
        "is_admin": False,
    },
    "usr_bob_02": {
        "user_id": "usr_bob_02",
        "username": "bob",
        "token": "Bearer bob-token-456",
        "display_name": "Bob Jones",
        "bio": "Backend software engineer.",
        "role": "member",
        "is_admin": False,
    },
}

INITIAL_DOCUMENTS: dict[str, dict[str, Any]] = {
    "doc_alice_01": {
        "doc_id": "doc_alice_01",
        "owner_id": "usr_alice_01",
        "title": "Alice's Secret Strategy",
        "content": "Confidential Q3 financial targets and product launch roadmap.",
    },
    "doc_bob_02": {
        "doc_id": "doc_bob_02",
        "owner_id": "usr_bob_02",
        "title": "Bob's Personal Budget",
        "content": "Personal compensation breakdown and private home address.",
    },
}

USERS: dict[str, dict[str, Any]] = copy.deepcopy(INITIAL_USERS)
DOCUMENTS: dict[str, dict[str, Any]] = copy.deepcopy(INITIAL_DOCUMENTS)


def reset_state() -> None:
    """Reset in-memory databases to default seed state."""
    global USERS, DOCUMENTS
    USERS = copy.deepcopy(INITIAL_USERS)
    DOCUMENTS = copy.deepcopy(INITIAL_DOCUMENTS)


# ─────────────────────────────────────────────────────────────────────────────
# Authentication dependency
# ─────────────────────────────────────────────────────────────────────────────

def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials.",
        )
    for user in USERS.values():
        if user["token"] == authorization:
            return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Baseline endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"app": "Notes & Identity API", "status": "running"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. BOLA: Broken Object Level Authorization (OWASP API1, CWE-639)
# Root Cause: Depends(get_current_user) authenticates caller, but document lookup
# lacks an ownership predicate. Alice can view Bob's document.
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/documents/{doc_id}")
def get_document(
    doc_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    doc = DOCUMENTS.get(doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    # VULNERABILITY: Missing ownership check (doc["owner_id"] == current_user["user_id"])
    return doc


@app.post("/documents")
def create_document(
    payload: dict[str, str],
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    doc_id = f"doc_{len(DOCUMENTS) + 1:02d}"
    doc = {
        "doc_id": doc_id,
        "owner_id": current_user["user_id"],
        "title": payload.get("title", "Untitled"),
        "content": payload.get("content", ""),
    }
    DOCUMENTS[doc_id] = doc
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# 2. BOPLA_MASS_ASSIGN: Mass Assignment (OWASP API3, CWE-915)
# Root Cause: Pydantic model allows extra fields; payload dictionary is unpacked
# directly into user record without field whitelisting. Caller can escalate role.
# ─────────────────────────────────────────────────────────────────────────────

class ProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    bio: str | None = None

    model_config = ConfigDict(extra="allow")  # VULNERABILITY: Unvalidated extra fields accepted


@app.put("/users/{user_id}/profile")
def update_profile(
    user_id: str,
    payload: ProfileUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit another user")

    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # VULNERABILITY: Arbitrary fields from extra are persisted to the user model
    update_data = payload.model_dump(exclude_unset=True)
    user.update(update_data)
    return {"status": "updated", "user": user}


@app.get("/users/{user_id}")
def get_user_profile(
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# ─────────────────────────────────────────────────────────────────────────────
# 3. SECURITY_MISCONFIG: Security Misconfiguration (OWASP API8, CWE-16)
# Root Cause: Sensitive debug configuration and internal database credentials
# are exposed via an unauthenticated debug route.
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/debug/config")
def get_debug_config() -> dict[str, Any]:
    # VULNERABILITY: Unauthenticated route exposes internal environment & secrets
    return {
        "debug_mode": True,
        "environment": "production",
        "database_url": "postgresql://postgres:prod_secret_pass_99@db.internal:5432/main",
        "internal_api_key": "sec-prod-internal-master-key-999",
        "cors_allow_all": True,
    }
