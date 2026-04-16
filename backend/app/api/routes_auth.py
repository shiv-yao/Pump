from fastapi import APIRouter, HTTPException

from app.models.schemas import LoginRequest, SignUpRequest
from app.services.auth import login, signup

router = APIRouter(tags=["auth"])


@router.post("/signup")
def signup_route(payload: SignUpRequest):
    try:
        user = signup(payload.email, payload.password, payload.full_name)
        return {"user": user, "message": "Signup successful"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/login")
def login_route(payload: LoginRequest):
    try:
        return login(payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))\n