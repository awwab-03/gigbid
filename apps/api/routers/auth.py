"""Sign-in, onboarding (register + choose persona) and the Upwork OAuth connect flow."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from apps.api import db
from apps.api.auth.security import check_pw, create_user, current_user, issue
from apps.api.schemas.models import LoginIn, RegisterIn, TokenOut, UserOut
from shared.token_store import TokenStore

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(u: dict) -> UserOut:
    connected = TokenStore().load(u["id"], "upwork") is not None
    return UserOut(id=u["id"], email=u["email"], name=u.get("name"), account=u["account"], settings=u.get("settings") or {},
                   upwork_connected=connected)


@router.post("/register", response_model=TokenOut, operation_id="register")
def register(body: RegisterIn) -> TokenOut:
    if db.get_user_by_email(body.email):
        raise HTTPException(409, "email already registered")
    u = create_user(body.email, body.password, body.name, body.account)
    return TokenOut(access_token=issue(u["id"]), user=user_out(u))


@router.post("/login", response_model=TokenOut, operation_id="login")
def login(body: LoginIn) -> TokenOut:
    u = db.get_user_by_email(body.email)
    if not u or not check_pw(body.password, u["password_hash"]):
        raise HTTPException(401, "wrong email or password")
    return TokenOut(access_token=issue(u["id"]), user=user_out(u))


@router.get("/me", response_model=UserOut, operation_id="me")
def me(user: dict = Depends(current_user)) -> UserOut:
    return user_out(user)
