from fastapi import FastAPI
from database.connection import SessionLocal
from auth.schemas import LoginRequest, RegisterRequest, UserResponse
from auth.password import hash_password
from database.models import User
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from auth.password import verify_password
from auth.jwt import create_access_token, get_current_user

from fastapi import HTTPException, status
from sqlalchemy import select
from fastapi import Depends

app = FastAPI()

@app.post("/register")
def register(user: RegisterRequest):
    db = SessionLocal()
    try:
        existing_user = db.execute(
            select(User).where(User.email == user.email)
        ).scalar_one_or_none()

        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        new_user = User(
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            email=user.email,
            password=hash_password(user.password),
        )

        db.add(new_user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            ) from None
    finally:
        db.close()

    return {"message": "User registered"}

@app.post("/login")
def login(user: LoginRequest):
    db = SessionLocal()

    result = db.execute(
        select(User).where(
            or_(
                User.username == user.identifier,
                User.email == user.identifier,
            )
        )
    )

    db_user = result.scalar_one_or_none()

    db.close()

    if db_user is None:
        return {"message": "User not found"}

    if not verify_password(user.password, db_user.password):
        return {"message": "Invalid credentials"}

    access_token = create_access_token(str(db_user.id))

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@app.get("/me", response_model=UserResponse)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user
