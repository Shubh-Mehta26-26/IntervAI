from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.dependencies import DB, CandidateActor, csrf_actor
from app.db.session import SessionFactory
from app.models.career import CareerAnalysis, CareerRole
from app.schemas.career import (
    AdviceInput,
    CareerAnalyze,
    CareerChoiceInput,
    CareerProfileInput,
    CareerRoadmap,
)
from app.services import career as service
from app.services.interviews import candidate

router = APIRouter(prefix="/career", tags=["career"])
mutation = [Depends(csrf_actor)]


@router.get("/profile")
async def profile(actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    return await service.profile_value(db, owner.id)


@router.patch("/profile", dependencies=mutation)
async def update_profile(payload: CareerProfileInput, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    return await service.update_profile(db, owner.id, payload)


@router.get("/roles")
async def roles(actor: CandidateActor, db: DB):
    return [
        service.role_value(row)
        for row in (await db.scalars(select(CareerRole).order_by(CareerRole.name))).all()
    ]


@router.get("/roles/{identifier}")
async def role(identifier: str, actor: CandidateActor, db: DB):
    return service.role_value(await service.role(db, identifier))


@router.post("/analyze", dependencies=mutation)
async def analyze(payload: CareerAnalyze, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    row = await service.analyze(db, owner.id, payload)
    return await service.analysis_value(db, owner.id, row)


@router.get("/analyses")
async def analyses(actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    rows = (
        await db.scalars(
            select(CareerAnalysis)
            .where(CareerAnalysis.candidate_id == owner.id)
            .order_by(CareerAnalysis.version.desc())
            .limit(50)
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "version": row.version,
            "generated_at": row.created_at.isoformat(),
            "roles": [r["name"] for r in row.snapshot["roles"]],
            "counts": [a["counts"] for a in row.result["alignments"]],
        }
        for row in rows
    ]


@router.get("/readiness")
async def readiness(actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    row = await db.scalar(
        select(CareerAnalysis)
        .where(CareerAnalysis.candidate_id == owner.id)
        .order_by(CareerAnalysis.version.desc())
        .limit(1)
    )
    return await service.analysis_value(db, owner.id, row, check_stale=True) if row else None


@router.get("/skill-gaps")
async def gaps(actor: CandidateActor, db: DB):
    value = await readiness(actor, db)
    return (
        [
            {
                "role_id": alignment["role"]["id"],
                "role_name": alignment["role"]["name"],
                "development": alignment["roadmap"],
            }
            for alignment in value["result"]["alignments"]
        ]
        if value
        else []
    )


@router.get("/analyses/{identifier}")
async def analysis(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    return await service.analysis_value(
        db, owner.id, await service.owned_analysis(db, owner.id, identifier), check_stale=True
    )


@router.post("/roadmap", dependencies=mutation)
async def roadmap(payload: CareerRoadmap, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    return await service.roadmap(db, owner.id, payload)


@router.post("/choices", dependencies=mutation)
async def choices(payload: CareerChoiceInput, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    return await service.choice(db, owner.id, payload)


@router.post("/analyses/{identifier}/advice", dependencies=mutation)
async def advice(identifier: UUID, payload: AdviceInput, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    await service.owned_analysis(db, owner.id, identifier)
    owner_id = owner.id
    await db.rollback()
    return await service.generate_advice(SessionFactory, owner_id, identifier, payload.use_rag)
