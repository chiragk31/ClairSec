"""
Secure FastAPI Application — Negative Reference Fixture for ClairSec Benchmark.
Endpoints are identical to vulnerable_fastapi_app, but secured against:
  1. BOLA (CWE-639): Ownership verification on GET /documents/{doc_id}.
  2. BOPLA_MASS_ASSIGN (CWE-915): Strict Pydantic schema with extra="forbid"
     and explicit field allowlisting on PUT /users/{user_id}/profile.
  3. SECURITY_MISCONFIG (CWE-16): debug=False, restricted CORS, debug route removed.

Per TESTING.md §5 and METHODOLOGY.md §2.3:
Any finding reported against this application is a FALSE POSITIVE by construction.
"""
from __future__ import annotations

import copy
from typing import Any
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

app = FastAPI(
    title="Notes & Identity API (Secure)",
    version="1.0.0",
    debug=False,  # SECURED: Debug mode disabled
)

# SECURED: Restricted CORS without wildcard credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ─────────────────────────────────────────────────────────────────────────────
# In-memory test store & Principals (Identical test principals)
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
# 1. BOLA Fix: Ownership verification
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/documents/{doc_id}")
def get_document(
    doc_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    doc = DOCUMENTS.get(doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # SECURED: Explicit ownership predicate enforced
    if doc["owner_id"] != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this document.",
        )
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
# 2. BOPLA_MASS_ASSIGN Fix: Strict schema with extra='forbid' & explicit field copy
# ─────────────────────────────────────────────────────────────────────────────

class SecureProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    bio: str | None = None

    model_config = ConfigDict(extra="forbid")  # SECURED: Extra fields rejected


@app.put("/users/{user_id}/profile")
def update_profile(
    user_id: str,
    payload: SecureProfileUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit another user")

    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # SECURED: Only declared and validated fields are copied
    if payload.display_name is not None:
        user["display_name"] = payload.display_name
    if payload.bio is not None:
        user["bio"] = payload.bio

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
# 3. SECURITY_MISCONFIG Fix: Debug route completely removed
# ─────────────────────────────────────────────────────────────────────────────
# Note: /debug/config is omitted. Requests to it return 404 Not Found.
