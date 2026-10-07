import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.errors import fail
from app.core.security import COOKIE_NAME, DUMMY_HASH, csrf_for, digest, hasher, verify_password
from app.models.identity import AuthRateLimit, Candidate, CandidatePreferences, Session, User
from app.schemas.identity import SessionOut, UserOut


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.disabled_at is None,
        created_at=user.created_at,
    )


async def throttle(db, request: Request, email: str, action: str):
    config = get_settings()
    seconds = config.auth_rate_limit_window_seconds
    now = datetime.now(timezone.utc)
    start = datetime.fromtimestamp(int(now.timestamp()) // seconds * seconds, timezone.utc)
    ip = request.client.host if request.client else "unknown"
    exceeded = False
    for key, limit in [
        (f"{action}:email:{email}", config.auth_rate_limit_attempts),
        (f"{action}:ip:{ip}", config.auth_rate_limit_ip_attempts),
    ]:
        hashed = hmac.new(
            config.auth_secret.get_secret_value().encode(), key.encode(), hashlib.sha256
        ).digest()
        stmt = insert(AuthRateLimit).values(bucket_key=hashed, window_start=start, attempts=1)
        count = await db.scalar(
            stmt.on_conflict_do_update(
                index_elements=[AuthRateLimit.bucket_key, AuthRateLimit.window_start],
                set_={"attempts": AuthRateLimit.attempts + 1},
            ).returning(AuthRateLimit.attempts)
        )
        exceeded |= count > limit
    await db.execute(
        delete(AuthRateLimit).where(AuthRateLimit.window_start < now - timedelta(days=1))
    )
    await db.commit()  # Failed credential transactions cannot undo throttling.
    if exceeded:
        fail(429, "rate_limited", "Too many attempts. Please wait before trying again.")


async def register(db, payload, request):
    await throttle(db, request, str(payload.email), "register")
    password_hash = await run_in_threadpool(hasher.hash, payload.password)
    user = User(
        email=str(payload.email),
        display_name=payload.display_name,
        password_hash=password_hash,
        role="candidate",
    )
    try:
        db.add(user)
        await db.flush()
        profile = Candidate(user_id=user.id)
        db.add(profile)
        await db.flush()
        db.add(CandidatePreferences(candidate_id=profile.id))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        fail(409, "email_registered", "An account with this email already exists. Try signing in.")
    return user_out(user)


async def login(db, payload, request, response: Response):
    await throttle(db, request, str(payload.email), "login")
    user = await db.scalar(select(User).where(User.email == str(payload.email)))
    correct = await run_in_threadpool(
        verify_password, payload.password, user.password_hash if user else DUMMY_HASH
    )
    if not correct or user is None or user.disabled_at is not None:
        fail(401, "invalid_credentials", "Email or password is incorrect.")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = await run_in_threadpool(hasher.hash, payload.password)
    old_token = request.cookies.get(COOKIE_NAME)
    if old_token:
        await db.execute(
            update(Session)
            .where(Session.token_hash == digest(old_token))
            .values(revoked_at=datetime.now(timezone.utc))
        )
    token = secrets.token_urlsafe(32)
    csrf = csrf_for(token)
    config = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(seconds=config.session_ttl_seconds)
    db.add(
        Session(
            user_id=user.id, token_hash=digest(token), csrf_hash=digest(csrf), expires_at=expires
        )
    )
    await db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=config.session_ttl_seconds,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/",
    )
    return SessionOut(user=user_out(user), csrf_token=csrf, expires_at=expires)
