import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.api.admin import router as admin_router
from app.api.analytics import router as analytics_router
from app.api.applications import router as applications_router
from app.api.career import router as career_router
from app.api.coding import router as coding_router
from app.api.health import router
from app.api.identity import router as identity_router
from app.api.intelligence import router as intelligence_router
from app.api.interviews import router as interviews_router
from app.api.learning import router as learning_router
from app.api.memory import router as memory_router
from app.api.recruiter import router as recruiter_router
from app.api.reports import router as reports_router
from app.api.vision import router as vision_router
from app.api.voice import router as voice_router
from app.core.config import get_settings
from app.core.request_limits import RequestSizeLimit
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="IntervAI API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(router, prefix="/api/v1")
app.include_router(identity_router, prefix="/api/v1")
app.include_router(intelligence_router, prefix="/api/v1")
app.include_router(interviews_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(learning_router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")
app.include_router(vision_router, prefix="/api/v1")
app.include_router(coding_router, prefix="/api/v1")
app.include_router(career_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(applications_router, prefix="/api/v1")
app.include_router(recruiter_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.add_middleware(RequestSizeLimit)


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    logging.getLogger(__name__).error(
        "Database request failed (%s), request=%s", type(exc).__name__, request.state.request_id
    )
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "database_unavailable",
                "message": "The account service is temporarily unavailable. Please try again.",
                "request_id": request.state.request_id,
            }
        },
    )


@app.middleware("http")
async def request_metadata(request: Request, call_next):
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    detail = (
        exc.detail
        if isinstance(exc.detail, dict)
        else {"code": "request_failed", "message": str(exc.detail)}
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {**detail, "request_id": request.state.request_id}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Pydantic's raw errors include input values (including passwords); never return them.
    fields = [
        {"field": ".".join(map(str, error["loc"][1:])), "message": error["msg"]}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Please check the highlighted fields.",
                "details": fields,
                "request_id": request.state.request_id,
            }
        },
    )
