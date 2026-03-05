from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session
import os

from app.database import SessionLocal
from app.models import User

bearer = HTTPBearer()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def decode_token(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    token = credentials.credentials
    
    # Ask Supabase to validate the token — works with any algorithm
    import requests
    supabase_url = os.environ.get("SUPABASE_URL", "")
    service_key  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    
    res = requests.get(
        f"{supabase_url}/auth/v1/user",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": service_key,
        }
    )
    
    if res.status_code != 200:
        print(f"[AUTH] Supabase rejected token: {res.text}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user_data = res.json()
    print(f"[AUTH] Token valid for: {user_data.get('email')}")
    
    # Return a payload-like dict so the rest of the code works unchanged
    return {"sub": user_data["id"], "email": user_data.get("email")}


def get_current_user(
    payload: dict = Depends(decode_token),
    db: Session = Depends(get_db),
) -> User:
    supabase_uid = payload.get("sub")
    if not supabase_uid:
        raise HTTPException(status_code=401, detail="Token missing subject")
    user = db.query(User).filter(User.supabase_uid == supabase_uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found in local DB")
    return user

def require_teacher(user: User = Depends(get_current_user)) -> User:
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher access required")
    return user

def require_student(user: User = Depends(get_current_user)) -> User:
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Student access required")
    return user

