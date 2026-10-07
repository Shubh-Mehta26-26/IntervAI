from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import DB, CandidateActor
from app.models.identity import CandidateGoal
from app.services.memory import CandidateMemoryService
from app.services.profile import get_candidate

router = APIRouter(prefix="/candidates/me", tags=["candidate memory"])
GapStatus = Literal["observed", "confirmed", "learning", "improving", "resolved"]


@router.get("/memory")
async def memory(actor: CandidateActor, db: DB):
    owner = await get_candidate(db, actor.user.id)
    goals = (
        await db.scalars(
            select(CandidateGoal)
            .where(
                CandidateGoal.candidate_id == owner.id,
                CandidateGoal.active.is_(True),
            )
            .order_by(CandidateGoal.priority)
            .limit(20)
        )
    ).all()
    return {
        "items": await CandidateMemoryService.memories(db, owner.id),
        "target_roles": [
            {"role_title": x.role_title, "source": "candidate_profile", "assessed": False}
            for x in goals
        ],
        "note": "Memory summarizes recorded interview evidence. It is not a hiring score.",
    }


@router.get("/memory/{identifier}/evidence")
async def evidence(identifier: UUID, actor: CandidateActor, db: DB, before: datetime | None = None):
    owner = await get_candidate(db, actor.user.id)
    return await CandidateMemoryService.evidence(db, owner.id, identifier, before=before)


@router.get("/skills/history")
async def skills(actor: CandidateActor, db: DB):
    owner = await get_candidate(db, actor.user.id)
    return await CandidateMemoryService.history(db, owner.id, "skill")


@router.get("/concepts/history")
async def concepts(actor: CandidateActor, db: DB):
    owner = await get_candidate(db, actor.user.id)
    return await CandidateMemoryService.history(db, owner.id, "concept")


@router.get("/knowledge-gaps")
async def gaps(actor: CandidateActor, db: DB, status: GapStatus | None = Query(default=None)):
    owner = await get_candidate(db, actor.user.id)
    return await CandidateMemoryService.gaps(db, owner.id, status=status)


@router.get("/knowledge-gaps/{identifier}")
async def gap(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await get_candidate(db, actor.user.id)
    return await CandidateMemoryService.gap_detail(db, owner.id, identifier)


@router.get("/misconceptions")
async def misconceptions(actor: CandidateActor, db: DB):
    owner = await get_candidate(db, actor.user.id)
    return await CandidateMemoryService.gaps(db, owner.id, kind="misconception")
