import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import fail
from app.core.security import COOKIE_NAME, digest
from app.db.session import get_session
from app.models.identity import Session, User

DB = Annotated[AsyncSession, Depends(get_session)]


@dataclass
class Actor:
    user: User
    session: Session
    token: str


def require_origin(request: Request):
    if request.headers.get("origin") not in get_settings().cors_origins:
        fail(403, "origin_rejected", "This request origin is not allowed.")


async def current_actor(request: Request, db: DB) -> Actor:
    token = request.cookies.get(COOKIE_NAME, "")
    if not token or len(token) > 128:
        fail(401, "authentication_required", "Please sign in to continue.")
    row = (
        await db.execute(
            select(Session, User)
            .join(User)
            .where(
                Session.token_hash == digest(token),
                Session.revoked_at.is_(None),
                Session.expires_at > datetime.now(timezone.utc),
                User.disabled_at.is_(None),
            )
        )
    ).first()
    if row is None:
        fail(401, "authentication_required", "Your session has ended. Please sign in again.")
    return Actor(user=row.User, session=row.Session, token=token)


Authenticated = Annotated[Actor, Depends(current_actor)]


async def csrf_actor(request: Request, actor: Authenticated) -> Actor:
    require_origin(request)
    supplied = request.headers.get("x-csrf-token", "")
    if not supplied or not hmac.compare_digest(digest(supplied), actor.session.csrf_hash):
        fail(403, "csrf_rejected", "Security check failed. Refresh the page and try again.")
    return actor


MutationActor = Annotated[Actor, Depends(csrf_actor)]


def require_roles(*roles: str):
    async def check(actor: Authenticated):
        if actor.user.role not in roles:
            fail(403, "role_forbidden", "This feature is available to candidates only.")
        return actor

    return check


CandidateActor = Annotated[Actor, Depends(require_roles("candidate"))]
RecruiterActor = Annotated[Actor, Depends(require_roles("recruiter"))]
AdminActor = Annotated[Actor, Depends(require_roles("admin"))]
