"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.data.db.session import get_db
from src.data.db.models import User
from src.api.auth import hash_password, verify_password, create_token, require_auth
from src.api.schemas import UserRegister, UserLogin, TokenResponse, UserResponse

router = APIRouter()


@router.post("/register", response_model=TokenResponse)
def register(body: UserRegister, db: Session = Depends(get_db)):
    """Create a new user account."""
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role="admin" if db.query(User).count() == 0 else "user",  # first user is admin
    )
    db.add(user)
    db.flush()

    token = create_token({"sub": user.email})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(body: UserLogin, db: Session = Depends(get_db)):
    """Authenticate and get a JWT token."""
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = create_token({"sub": user.email})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(require_auth)):
    """Get current user profile."""
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name, role=user.role)
