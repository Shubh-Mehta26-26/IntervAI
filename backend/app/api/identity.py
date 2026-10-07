from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import DB, Authenticated, CandidateActor, MutationActor, require_origin
from app.core.config import get_settings
from app.core.security import COOKIE_NAME, csrf_for
from app.schemas.identity import (
    LoginInput,
    ProfileOut,
    ProfilePatch,
    RegisterInput,
    SessionOut,
    UserOut,
)
from app.services import auth, profile

router = APIRouter()


@router.post(
    "/auth/register",
    status_code=201,
    response_model=UserOut,
    tags=["auth"],
    dependencies=[Depends(require_origin)],
)
async def register(payload: RegisterInput, request: Request, db: DB):
    return await auth.register(db, payload, request)


@router.post(
    "/auth/login", response_model=SessionOut, tags=["auth"], dependencies=[Depends(require_origin)]
)
async def login(payload: LoginInput, request: Request, response: Response, db: DB):
    return await auth.login(db, payload, request, response)


@router.get("/auth/session", response_model=SessionOut, tags=["auth"])
@router.get("/auth/me", response_model=SessionOut, tags=["auth"])
async def session(actor: Authenticated):
    return SessionOut(
        user=auth.user_out(actor.user),
        csrf_token=csrf_for(actor.token),
        expires_at=actor.session.expires_at,
    )


@router.post("/auth/logout", status_code=204, tags=["auth"])
async def logout(actor: MutationActor, db: DB, response: Response):
    actor.session.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    response.delete_cookie(
        COOKIE_NAME, path="/", httponly=True, secure=get_settings().cookie_secure, samesite="lax"
    )


@router.get("/candidates/me", response_model=ProfileOut, tags=["candidate"])
async def get_profile(actor: CandidateActor, db: DB):
    return await profile.profile_out(db, actor.user)


@router.patch(
    "/candidates/me",
    response_model=ProfileOut,
    tags=["candidate"],
    dependencies=[Depends(require_origin)],
)
async def patch_profile(payload: ProfilePatch, actor: CandidateActor, csrf: MutationActor, db: DB):
    return await profile.update_profile(db, actor.user, payload)
