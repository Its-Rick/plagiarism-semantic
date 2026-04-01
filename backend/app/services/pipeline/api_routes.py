"""
api_routes.py — Academic Check FastAPI Router
──────────────────────────────────────────────
Drop this router into main.py with:
    from app.services.pipeline.api_routes import router as academic_router
    app.include_router(academic_router, prefix="/api")
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user, require_teacher
from app.database import SessionLocal
from app.models import Submission

from .academic_service import check_academic_plagiarism, result_to_json

router = APIRouter(tags=["academic-check"])


# ── Request schema ────────────────────────────────────────────────────────────

class AcademicCheckRequest(BaseModel):
    text:      str
    threshold: Optional[float] = 0.65   # 0.5 – 1.0


# ── POST /api/academic-check ──────────────────────────────────────────────────

@router.post("/academic-check")
async def academic_check(
    data: AcademicCheckRequest,
    user=Depends(get_current_user),
):
    """
    Multi-source academic plagiarism check.
    Compares input text against arXiv, OpenAlex, and GitHub simultaneously.

    Input:
        { "text": "...", "threshold": 0.65 }

    Output:
        {
          "plagiarism_percentage": 34.5,
          "matches": [
            {
              "input_sentence":   "...",
              "matched_sentence": "...",
              "source":           "arXiv",
              "similarity":       0.78,
              "similarity_pct":   78.0,
              "title":            "Paper title",
              "url":              "https://..."
            }
          ],
          "sources_checked":   42,
          "sentences_checked": 12,
          "elapsed_seconds":   8.4,
          "flagged":           false
        }
    """
    if len(data.text.strip()) < 50:
        raise HTTPException(400, "Text too short — minimum 50 characters")

    if not (0.5 <= data.threshold <= 1.0):
        raise HTTPException(400, "Threshold must be between 0.5 and 1.0")

    result = await check_academic_plagiarism(
        submission_text = data.text.strip(),
        threshold       = data.threshold,
    )
    return result_to_json(result)


# ── POST /api/submissions/{id}/academic-check  (teacher only) ─────────────────

@router.post("/submissions/{submission_id}/academic-check")
async def academic_check_for_submission(
    submission_id: int,
    teacher=Depends(require_teacher),
):
    """Run academic check on an already-stored submission (teacher only)."""
    db = SessionLocal()
    try:
        sub = db.query(Submission).filter(Submission.id == submission_id).first()
        if not sub:
            raise HTTPException(404, "Submission not found")
        result = await check_academic_plagiarism(sub.text, threshold=0.65)
        return result_to_json(result)
    finally:
        db.close()