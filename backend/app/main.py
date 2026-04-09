import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler

from app.database import Base, engine, SessionLocal
from app.models import Assignment, Submission, Sentence, Match, User
from app.services.embedding_service import generate_embeddings
# check_plagiarism no longer needed — batch checker uses vectorised global matrix
from app.utils.text_utils import split_sentences
from app.auth.router import router as auth_router
from app.auth.dependencies import get_db, require_teacher, require_student, get_current_user

import asyncio
from app.services.pipeline.academic_service import check_academic_plagiarism, result_to_json
from app.services.pipeline.file_extractor import extract_text_from_upload

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
    """
    Fast batch plagiarism check — vectorised global matrix approach.

    OLD approach (slow):
      For each student:
        - Re-query DB for all other sentences
        - Compute similarity vs reference corpus
        - Commit after every student
      → O(k) DB round-trips, O(k²·n·d) similarity ops

    NEW approach (fast):
      1. ONE query: load ALL sentences for the assignment
      2. Build global embedding matrix E ∈ ℝ^(total_sentences × 384)
      3. Compute FULL (total × total) similarity matrix in one numpy call
      4. For each student, slice their rows vs other students' rows — O(1)
      5. ONE bulk INSERT for all matches, ONE commit at the end
      → 2 DB round-trips total, O(total² · d) similarity ops (BLAS-level)
    """
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity

    THRESHOLD = 0.85

    db = SessionLocal()
    try:
        assignment = db.query(Assignment).filter(
            Assignment.id == assignment_id
        ).first()
        if not assignment or assignment.status == "checked":
            return

        print(f"[BATCH] Starting fast batch check for assignment #{assignment_id}")
        t_start = __import__("time").time()

        assignment.status = "closed"
        db.commit()

        # ── Step 1: ONE query — load all submissions + sentences together ────
        submissions = db.query(Submission).filter(
            Submission.assignment_id == assignment_id
        ).all()

        if not submissions:
            assignment.status = "checked"
            db.commit()
            return

        # Build lookup: submission_id → Submission object
        sub_map = {s.id: s for s in submissions}

        # Load ALL sentences for this assignment in a single query
        all_sentence_rows = (
            db.query(Sentence)
            .filter(Sentence.submission_id.in_(sub_map.keys()))
            .all()
        )

        if not all_sentence_rows:
            # No sentences at all — mark everything 0
            now = datetime.now(timezone.utc)
            for sub in submissions:
                sub.plagiarism_percentage = 0.0
                sub.checked_at = now
            assignment.status = "checked"
            db.commit()
            return

        # ── Step 2: Build global embedding matrix in one numpy stack ─────────
        # Group sentences by submission
        from collections import defaultdict
        sub_sentences: dict[int, list] = defaultdict(list)   # sub_id → [Sentence]
        for row in all_sentence_rows:
            sub_sentences[row.submission_id].append(row)

        # Build index arrays for fast slicing
        # global_index[i] = (submission_id, sentence_position, student_id, sentence_text)
        global_texts:   list[str]   = []
        global_sub_ids: list[int]   = []
        global_stu_ids: list[int]   = []
        global_embs:    list        = []

        # Track per-submission slice: sub_id → (start_idx, end_idx)
        sub_slices: dict[int, tuple[int, int]] = {}

        cursor = 0
        for sub_id, rows in sub_sentences.items():
            sub_slices[sub_id] = (cursor, cursor + len(rows))
            for r in rows:
                global_texts.append(r.sentence_text)
                global_sub_ids.append(sub_id)
                global_stu_ids.append(r.student_id)
                global_embs.append(r.embedding)
            cursor += len(rows)

        # Stack into a single matrix — shape: (total_sentences, 384)
        E = np.array(global_embs, dtype=np.float32)

        print(f"[BATCH]  Global matrix: {E.shape[0]} sentences × {E.shape[1]} dims")

        # ── Step 3: ONE global similarity matrix ──────────────────────────────
        # Shape: (total_sentences × total_sentences)
        # Cosine similarity via normalised dot product — BLAS-level speed
        norms = np.linalg.norm(E, axis=1, keepdims=True)
        norms[norms == 0] = 1e-9          # avoid div/zero
        E_norm = E / norms
        SIM = E_norm @ E_norm.T           # shape: (N, N)

        print(f"[BATCH]  Similarity matrix computed: {SIM.shape}")

        # ── Step 4: For each submission, slice its rows vs all OTHER rows ─────
        now = datetime.now(timezone.utc)
        all_sub_ids_set = set(sub_map.keys())

        # Collect all matches to bulk-insert later
        new_matches: list[dict] = []

        # Clear stale matches for this assignment in ONE delete
        db.query(Match).filter(
            Match.submission_id.in_(list(all_sub_ids_set))
        ).delete(synchronize_session=False)

        for sub_id, sub in sub_map.items():
            if sub_id not in sub_slices:
                # No sentences — zero score
                sub.plagiarism_percentage = 0.0
                sub.checked_at = now
                continue

            start, end = sub_slices[sub_id]
            n_sentences = end - start

            # Build a mask that zeros out same-student columns
            # We don't want to compare a student against themselves
            same_sub_mask = np.array(
                [sid == sub_id for sid in global_sub_ids], dtype=bool
            )

            # Slice rows for this submission: shape (n_sentences, N)
            student_rows = SIM[start:end, :]          # this student's similarities

            # Zero out self-comparisons
            student_rows = student_rows.copy()
            student_rows[:, same_sub_mask] = 0.0

            # For each input sentence, find best match among OTHER students
            best_col_idxs = np.argmax(student_rows, axis=1)   # shape: (n_sentences,)
            best_scores   = student_rows[
                np.arange(n_sentences), best_col_idxs
            ]                                                   # shape: (n_sentences,)

            # Count flagged sentences
            flagged_mask = best_scores >= THRESHOLD
            flagged_count = int(np.sum(flagged_mask))

            pct = round((flagged_count / n_sentences) * 100, 2)
            sub.plagiarism_percentage = pct
            sub.checked_at = now

            # Collect match rows for bulk insert
            for local_i in np.where(flagged_mask)[0]:
                global_i  = start + int(local_i)
                global_j  = int(best_col_idxs[local_i])
                sim_score = float(best_scores[local_i])

                new_matches.append({
                    "submission_id":    sub_id,
                    "input_sentence":   global_texts[global_i],
                    "matched_sentence": global_texts[global_j],
                    "student_id":       global_stu_ids[global_j],
                    "similarity":       sim_score,
                })

        # ── Step 5: ONE bulk insert for all matches ───────────────────────────
        if new_matches:
            db.bulk_insert_mappings(Match, new_matches)

        assignment.status = "checked"
        db.commit()

        elapsed = round(__import__("time").time() - t_start, 2)
        print(
            f"[BATCH] Done — assignment #{assignment_id} | "
            f"{len(submissions)} students | "
            f"{len(all_sentence_rows)} sentences | "
            f"{len(new_matches)} matches | "
            f"{elapsed}s"
        )

    except Exception as e:
        print(f"[BATCH] Error on assignment #{assignment_id}: {e}")
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


# ── Similarity pairs endpoint ─────────────────────────────────────────────────

@app.get("/api/assignments/{assignment_id}/similarity-pairs")
def get_similarity_pairs(
    assignment_id: int,
    db: Session = Depends(get_db),
    teacher=Depends(require_teacher),
):
    """
    Returns all student pairs that share at least one matched sentence,
    grouped by pair, with their max similarity and matched sentences.
    """
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(404, "Assignment not found")

    # Get all submissions for this assignment that have been checked
    subs = db.query(Submission).filter(
        Submission.assignment_id == assignment_id,
        Submission.plagiarism_percentage != None,
    ).all()

    if not subs:
        return {"assignment_id": assignment_id, "pairs": []}

    sub_map = {s.id: s for s in subs}

    # Collect all matches across all submissions
    sub_ids = [s.id for s in subs]
    all_matches = db.query(Match).filter(Match.submission_id.in_(sub_ids)).all()

    # Build pairs: {(student_a, student_b) -> {max_sim, examples, sub_ids}}
    pairs: dict = {}
    for m in all_matches:
        sub = sub_map.get(m.submission_id)
        if not sub:
            continue
        student_a = sub.student_id
        student_b = m.student_id
        if student_a == student_b:
            continue

        # Normalise pair key so (a,b) and (b,a) are the same
        key = (min(student_a, student_b), max(student_a, student_b))
        sub_a = m.submission_id
        # Find submission id for student_b
        sub_b_obj = next((s for s in subs if s.student_id == student_b), None)
        sub_b = sub_b_obj.id if sub_b_obj else None

        if key not in pairs:
            pairs[key] = {
                "student_a": key[0],
                "student_b": key[1],
                "submission_a": sub_a if student_a == key[0] else sub_b,
                "submission_b": sub_b if student_b == key[1] else sub_a,
                "max_similarity": 0.0,
                "match_count": 0,
                "examples": [],
            }

        pairs[key]["match_count"] += 1
        if m.similarity > pairs[key]["max_similarity"]:
            pairs[key]["max_similarity"] = m.similarity
        if len(pairs[key]["examples"]) < 3:
            pairs[key]["examples"].append({
                "input_sentence":   m.input_sentence,
                "matched_sentence": m.matched_sentence,
                "similarity":       round(m.similarity * 100, 1),
            })

    # Also include plagiarism percentages per student
    student_scores = {
        s.student_id: {
            "submission_id":         s.id,
            "plagiarism_percentage": s.plagiarism_percentage,
        }
        for s in subs
    }

    result = sorted(
        pairs.values(),
        key=lambda p: p["max_similarity"],
        reverse=True,
    )
    for p in result:
        p["max_similarity"] = round(p["max_similarity"] * 100, 1)
        p["score_a"] = student_scores.get(p["student_a"], {}).get("plagiarism_percentage")
        p["score_b"] = student_scores.get(p["student_b"], {}).get("plagiarism_percentage")

    return {
        "assignment_id":   assignment_id,
        "assignment_title": assignment.title,
        "total_students":  len(subs),
        "pairs":           result,
    }




# ── Academic Check: request schema ───────────────────────────────────────────

class AcademicCheckRequest(BaseModel):
    text:      str
    threshold: Optional[float] = 0.65


# ── POST /api/academic-check  (text) ─────────────────────────────────────────

@app.post("/api/academic-check")
async def academic_check(
    data: AcademicCheckRequest,
    user=Depends(get_current_user),
):
    """
    Academic plagiarism check against arXiv, OpenAlex and GitHub.
    5-stage hybrid pipeline: BM25 → Fingerprint → BERT → Hybrid score.
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


# ── POST /api/academic-check/file  (upload) ───────────────────────────────────

@app.post("/api/academic-check/file")
async def academic_check_file(
    file:      UploadFile = File(..., description="PDF, DOCX or TXT file"),
    threshold: float      = Form(default=0.65, ge=0.5, le=1.0),
    user=Depends(get_current_user),
):
    """
    Academic plagiarism check from an uploaded file (.pdf, .docx, .txt).
    Extracts text then runs the same 5-stage hybrid pipeline.
    """
    text = await extract_text_from_upload(file)
    result = await check_academic_plagiarism(
        submission_text = text,
        threshold       = threshold,
    )
    response = result_to_json(result)
    response["filename"]   = file.filename
    response["char_count"] = len(text)
    return response


# ── POST /api/submissions/{id}/academic-check  (teacher) ─────────────────────

@app.post("/api/submissions/{submission_id}/academic-check")
async def academic_check_for_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    teacher=Depends(require_teacher),
):
    """Run academic check on a stored submission (teacher only)."""
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub:
        raise HTTPException(404, "Submission not found")
    result = await check_academic_plagiarism(sub.text, threshold=0.65)
    return result_to_json(result)

# ── Serve React frontend (catch-all — MUST be last) ───────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend_dist"

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        return FileResponse(str(FRONTEND_DIR / "index.html"))