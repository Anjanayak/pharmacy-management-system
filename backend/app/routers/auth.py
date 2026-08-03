from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import schemas, models
from ..database import get_db
from ..auth import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_refresh_token, get_current_user, require_roles,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == user_in.username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    if db.query(models.User).filter(models.User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled")

    access_token = create_access_token({"sub": user.username, "role": user.role.value})
    refresh_token = create_refresh_token({"sub": user.username})
    return schemas.Token(access_token=access_token, refresh_token=refresh_token, role=user.role, username=user.username)


@router.post("/refresh", response_model=schemas.Token)
def refresh(payload: schemas.RefreshRequest, db: Session = Depends(get_db)):
    """Exchanges a valid, unexpired refresh token for a new access + refresh
    token pair, without requiring the user to log in again with a password."""
    username = decode_refresh_token(payload.refresh_token)
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    access_token = create_access_token({"sub": user.username, "role": user.role.value})
    refresh_token = create_refresh_token({"sub": user.username})
    return schemas.Token(access_token=access_token, refresh_token=refresh_token, role=user.role, username=user.username)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.get("/users", response_model=list[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin)),
):
    return db.query(models.User).all()
