from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from supabase import create_client

from app.config import SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY
from app.database import SessionLocal
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

# Service-role client — can bypass RLS to read profiles
supa = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Request/response models ───────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    role: str          # "teacher" or "student"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class GoogleRoleRequest(BaseModel):
    """Called once after Google OAuth to set the role chosen by the user."""
    supabase_uid: str
    email: str
    role: str


# ── Email / password sign-up ──────────────────────────────────────────────────

@router.post("/signup")
def signup(data: SignupRequest, db: Session = Depends(get_db)):
    if data.role not in ("teacher", "student"):
        raise HTTPException(400, "role must be 'teacher' or 'student'")

    anon_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

    try:
        res = anon_client.auth.sign_up({
            "email": data.email,
            "password": data.password,
            "options": {
                "data": {"role": data.role}
            }
        })
    except Exception as e:
        raise HTTPException(400, str(e))

    if not res.user:
        raise HTTPException(400, "Signup failed")

    uid = res.user.id

    # ── UPSERT instead of insert — handles duplicate calls gracefully ──
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        # Update supabase_uid in case it changed
        existing.supabase_uid = uid
        existing.role = data.role
    else:
        db.add(User(supabase_uid=uid, email=data.email, role=data.role))
    db.commit()

    return {"message": "Account created", "uid": uid}

# ── Email / password login (returns Supabase JWT) ────────────────────────────

@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    try:
        res = supa.auth.sign_in_with_password(
            {"email": data.email, "password": data.password}
        )
    except Exception:
        raise HTTPException(401, "Invalid credentials")

    session = res.session
    uid     = res.user.id

    # Fetch role from profiles — handle missing profile gracefully
    try:
        profile = supa.table("profiles").select("role").eq("id", uid).single().execute()
        role = profile.data["role"]
    except Exception:
        # Fall back to local users table
        user = db.query(User).filter(User.supabase_uid == uid).first()
        role = user.role if user else "student"

    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "role": role,
        "uid": uid,
        "email": res.user.email,
    }

# ── Google OAuth: called AFTER the client-side redirect completes ─────────────

@router.post("/google/set-role")
def set_google_role(data: GoogleRoleRequest, db: Session = Depends(get_db)):
    """
    After Google sign-in, the frontend calls this once to persist the user's
    chosen role into both the local DB and the Supabase profiles table.
    """
    if data.role not in ("teacher", "student"):
        raise HTTPException(400, "role must be 'teacher' or 'student'")

    # Update Supabase profiles table
    supa.table("profiles").upsert({
        "id": data.supabase_uid,
        "email": data.email,
        "role": data.role,
    }).execute()

    # Mirror / upsert in local DB
    user = db.query(User).filter(User.supabase_uid == data.supabase_uid).first()
    if user:
        user.role = data.role
    else:
        db.add(User(supabase_uid=data.supabase_uid, email=data.email, role=data.role))
    db.commit()

    return {"message": "Role saved", "role": data.role}


# ── Verify token + return profile (used by frontend on page load) ─────────────

@router.get("/me")
def me(uid: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.supabase_uid == uid).first()
    if not user:
        raise HTTPException(404, "User not found")
    return {"uid": user.supabase_uid, "email": user.email, "role": user.role}