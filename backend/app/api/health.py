import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)


class LiveResponse(BaseModel):
    status: str = "ok"
    service: str = "intervai-api"


class ReadyResponse(BaseModel):
    status: str
    database: str
    vector: str


async def probe_database() -> bool:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
        return bool(
            await connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            )
        )


@router.get("/live", response_model=LiveResponse)
async def live():
    return LiveResponse()


@router.get("/ready", response_model=ReadyResponse, responses={503: {"model": ReadyResponse}})
async def ready():
    try:
        has_vector = await asyncio.wait_for(probe_database(), timeout=5)
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        # Do not emit exception text: database errors may contain credentials/host details.
        logger.warning("Database readiness failed: %s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "database": "unavailable",
                "vector": "unknown",
            },
        )
    if not has_vector:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "database": "connected",
                "vector": "missing",
            },
        )
    return ReadyResponse(status="ready", database="connected", vector="available")
