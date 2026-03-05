import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler

from app.database import Base, engine, SessionLocal
from app.models import Assignment, Submission, Sentence, Match, User
from app.services.embedding_service import generate_embeddings
from app.services.plagiarism_service import check_plagiarism
from app.utils.text_utils import split_sentences
from app.auth.router import router as auth_router
from app.auth.dependencies import get_db, require_teacher, require_student, get_current_user

Base.metadata.create_all(bind=engine)

app = FastAPI(title="EduCheck API", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://localhost:3000",
        "http://localhost:8000", "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class AssignmentCreate(BaseModel):
    title: str
    deadline: Optional[str] = None   # ISO 8601 e.g. "2025-03-10T23:59:00Z"

class AssignmentUpdate(BaseModel):
    title: Optional[str] = None
    deadline: Optional[str] = None

class SubmissionCreate(BaseModel):
    assignment_id: int
    text: str


# ── Background plagiarism checker ─────────────────────────────────────────────

def run_plagiarism_for_assignment(assignment_id: int):
    """Runs after deadline — checks ALL submissions for an assignment at once."""
    db = SessionLocal()
    try:
        assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
        if not assignment or assignment.status == "checked":
            return

        print(f"[SCHEDULER] Starting plagiarism check for assignment #{assignment_id}")
        assignment.status = "closed"
        db.commit()

        submissions = db.query(Submission).filter(
            Submission.assignment_id == assignment_id
        ).all()

        for submission in submissions:
            sentences  = [s.sentence_text for s in submission.sentences]
            embeddings = [s.embedding     for s in submission.sentences]

            if not sentences:
                submission.plagiarism_percentage = 0.0
                submission.checked_at = datetime.now(timezone.utc)
                db.commit()
                continue

            plagiarism_pct, matches = check_plagiarism(
                sentences, embeddings, assignment_id, submission.student_id
            )

            submission.plagiarism_percentage = plagiarism_pct
            submission.checked_at = datetime.now(timezone.utc)
            db.commit()

            # Clear old matches, store new ones
            db.query(Match).filter(Match.submission_id == submission.id).delete()
            for m in matches:
                db.add(Match(
                    submission_id    = submission.id,
                    input_sentence   = m["input_sentence"],
                    matched_sentence = m["matched_sentence"],
                    student_id       = m["student_id"],
                    similarity       = m["final_similarity"],
                ))
            db.commit()

        assignment.status = "checked"
        db.commit()
        print(f"[SCHEDULER] Done — assignment #{assignment_id} fully checked")

    except Exception as e:
        print(f"[SCHEDULER] Error on assignment #{assignment_id}: {e}")
        import traceback; traceback.print_exc()
    finally:
        db.close()


# ── APScheduler ───────────────────────────────────────────────────────────────

scheduler = BackgroundScheduler(timezone="UTC")


def schedule_assignment_check(assignment_id: int, deadline: datetime):
    job_id = f"check_{assignment_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(
        run_plagiarism_for_assignment,
        trigger="date",
        run_date=deadline,
        args=[assignment_id],
        id=job_id,
        replace_existing=True,
    )
    print(f"[SCHEDULER] Assignment #{assignment_id} check scheduled at {deadline}")


@app.on_event("startup")
def startup():
    scheduler.start()
    # Re-schedule open assignments that have future deadlines (server restart recovery)
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        open_assignments = db.query(Assignment).filter(
            Assignment.status == "open",
            Assignment.deadline != None,
        ).all()
        for a in open_assignments:
            if a.deadline > now:
                schedule_assignment_check(a.id, a.deadline)
            else:
                # Deadline passed while server was offline — run now
                print(f"[STARTUP] Deadline passed for #{a.id} while offline, running now")
                import threading
                t = threading.Thread(target=run_plagiarism_for_assignment, args=(a.id,))
                t.start()
    finally:
        db.close()


@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()


# ── Assignment endpoints ───────────────────────────────────────────────────────

@app.get("/api/assignments")
def list_assignments(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    now  = datetime.now(timezone.utc)
    rows = db.query(Assignment).all()
    result = []
    for a in rows:
        is_open = a.status == "open" and (a.deadline is None or a.deadline > now)
        result.append({
            "id":       a.id,
            "title":    a.title,
            "deadline": a.deadline.isoformat() if a.deadline else None,
            "status":   a.status,
            "is_open":  is_open,
        })
    return result


@app.post("/api/assignments", status_code=201)
def create_assignment(
    data: AssignmentCreate,
    db: Session = Depends(get_db),
    teacher=Depends(require_teacher),
):
    deadline_dt = None
    if data.deadline:
        deadline_dt = datetime.fromisoformat(data.deadline.replace("Z", "+00:00"))

    assignment = Assignment(
        title      = data.title,
        teacher_id = teacher.id,
        deadline   = deadline_dt,
        status     = "open",
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    if deadline_dt:
        schedule_assignment_check(assignment.id, deadline_dt)

    return {
        "assignment_id": assignment.id,
        "title":         assignment.title,
        "deadline":      assignment.deadline.isoformat() if assignment.deadline else None,
        "status":        assignment.status,
        "is_open":       True,
    }


@app.patch("/api/assignments/{assignment_id}")
def update_assignment(
    assignment_id: int,
    data: AssignmentUpdate,
    db: Session = Depends(get_db),
    teacher=Depends(require_teacher),
):
    a = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not a:
        raise HTTPException(404, "Assignment not found")

    if data.title:
        a.title = data.title

    if data.deadline is not None:
        new_deadline = datetime.fromisoformat(data.deadline.replace("Z", "+00:00"))
        a.deadline = new_deadline
        a.status   = "open"   # re-open if deadline extended
        schedule_assignment_check(assignment_id, new_deadline)

    db.commit()
    db.refresh(a)
    now = datetime.now(timezone.utc)
    return {
        "assignment_id": a.id,
        "title":         a.title,
        "deadline":      a.deadline.isoformat() if a.deadline else None,
        "status":        a.status,
        "is_open":       a.status == "open" and (a.deadline is None or a.deadline > now),
    }


@app.delete("/api/assignments/{assignment_id}", status_code=204)
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    teacher=Depends(require_teacher),
):
    a = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not a:
        raise HTTPException(404, "Assignment not found")
    job_id = f"check_{assignment_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    db.delete(a)
    db.commit()
    return None


# ── Submission endpoints ───────────────────────────────────────────────────────

@app.post("/api/submissions", status_code=201)
def create_submission(
    data: SubmissionCreate,
    db: Session = Depends(get_db),
    student=Depends(require_student),
):
    assignment = db.query(Assignment).filter(Assignment.id == data.assignment_id).first()
    if not assignment:
        raise HTTPException(404, "Assignment not found")

    now = datetime.now(timezone.utc)
    if assignment.deadline and now > assignment.deadline:
        raise HTTPException(400, "Submission deadline has passed")
    if assignment.status in ("closed", "checked"):
        raise HTTPException(400, "This assignment is no longer accepting submissions")

    existing = db.query(Submission).filter(
        Submission.assignment_id == data.assignment_id,
        Submission.student_id    == student.id,
    ).first()
    if existing:
        raise HTTPException(400, "You have already submitted this assignment")

    # Store submission + embeddings only — plagiarism runs after deadline
    sentences  = split_sentences(data.text)
    embeddings = generate_embeddings(sentences)

    submission = Submission(
        student_id            = student.id,
        assignment_id         = data.assignment_id,
        text                  = data.text,
        plagiarism_percentage = None,   # NULL until checked
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    for i, sentence in enumerate(sentences):
        db.add(Sentence(
            submission_id = submission.id,
            student_id    = student.id,
            sentence_text = sentence,
            embedding     = embeddings[i].tolist(),
        ))
    db.commit()

    return {
        "submission_id": submission.id,
        "status":        "pending",
        "message":       "Submitted! Results will be available after the deadline passes.",
    }


@app.get("/api/submissions")
def list_submissions(
    db: Session = Depends(get_db),
    teacher=Depends(require_teacher),
):
    subs = db.query(Submission).all()
    return [
        {
            "id":                    s.id,
            "student_id":            s.student_id,
            "assignment_id":         s.assignment_id,
            "plagiarism_percentage": s.plagiarism_percentage,
            "submitted_at":          s.submitted_at.isoformat() if s.submitted_at else None,
            "checked_at":            s.checked_at.isoformat()   if s.checked_at   else None,
        }
        for s in subs
    ]


@app.get("/api/submissions/my")
def my_submissions(
    db: Session = Depends(get_db),
    student=Depends(require_student),
):
    subs = db.query(Submission).filter(Submission.student_id == student.id).all()
    return [
        {
            "id":                    s.id,
            "assignment_id":         s.assignment_id,
            "plagiarism_percentage": s.plagiarism_percentage,   # None = still pending
            "submitted_at":          s.submitted_at.isoformat() if s.submitted_at else None,
            "checked_at":            s.checked_at.isoformat()   if s.checked_at   else None,
        }
        for s in subs
    ]


@app.get("/api/submissions/{submission_id}")
def get_submission_detail(
    submission_id: int,
    db: Session = Depends(get_db),
    teacher=Depends(require_teacher),
):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub:
        raise HTTPException(404, "Submission not found")
    matches = db.query(Match).filter(Match.submission_id == submission_id).all()
    return {
        "submission": {
            "id":                    sub.id,
            "student_id":            sub.student_id,
            "assignment_id":         sub.assignment_id,
            "plagiarism_percentage": sub.plagiarism_percentage,
        },
        "matches": [
            {
                "input_sentence":   m.input_sentence,
                "matched_sentence": m.matched_sentence,
                "student_id":       m.student_id,
                "similarity":       m.similarity,
            }
            for m in matches
        ],
    }


# ── Serve React frontend (catch-all — MUST be last) ───────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend_dist"

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        return FileResponse(str(FRONTEND_DIR / "index.html"))