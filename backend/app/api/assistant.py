"""Ask ClairSec assistant API (FEATURES.md F11)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.assistant.service import AskRequest, AskResponse, ask
from app.database.client import get_database

router = APIRouter()

# Suggested questions per screen (the offline assistant answers all of these).
SUGGESTIONS: dict[str, list[str]] = {
    "dashboard": ["What is happening right now?", "What should I do next?", "Why did it fail?"],
    "projects": ["Why did it fail?", "What should I do next?", "What is happening right now?"],
    "scan": ["What is happening right now?", "Explain the score", "What should I do next?"],
    "finding": ["Explain this finding simply", "Is the fix safe?", "What should I do next?"],
    "fix": ["Is the fix safe?", "Explain this finding simply", "What should I do next?"],
    "reports": ["Explain the score", "What should I do next?", "What is happening right now?"],
}


@router.post("/assistant/ask", response_model=AskResponse, summary="Ask about what ClairSec has recorded")
async def assistant_ask(body: AskRequest, db: AsyncIOMotorDatabase = Depends(get_database)) -> AskResponse:
    return await ask(db, body)


@router.get("/assistant/suggestions", summary="Suggested questions for a screen")
async def assistant_suggestions(screen: str = "dashboard") -> dict[str, Any]:
    return {"screen": screen, "questions": SUGGESTIONS.get(screen, SUGGESTIONS["dashboard"])}
