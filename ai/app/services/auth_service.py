from sqlalchemy.orm import Session
from jose import jwt
from datetime import datetime, timedelta

from app.models.user import User
from app.schemas.auth_schema import RegisterRequest
from app.core.security import (
    hash_password,
    verify_password
)
from app.core.config import settings


def register_user(
    db: Session,
    payload: RegisterRequest
):

    existing_user = db.query(User).filter(
        User.email == payload.email
    ).first()

    if existing_user:
        return None

    new_user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


def authenticate_user(
    db: Session,
    email: str,
    password: str
):

    user = db.query(User).filter(
        User.email == email
    ).first()

    if not user:
        return None

    if not verify_password(
        password,
        user.password_hash
    ):
        return None

    return user


def create_access_token(data: dict):

    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({
        "exp": expire
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    return encoded_jwt