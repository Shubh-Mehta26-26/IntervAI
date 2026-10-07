"""Idempotently import eligible stored Phase 4/5 evaluations into candidate memory."""

import asyncio
import sys

from app.db.session import SessionFactory, engine
from app.models.interviews import AnswerEvaluation, Interview
from app.services.memory import CandidateMemoryService
from sqlalchemy import or_, select


async def main():
    count = 0
    try:
        async with SessionFactory() as db:
            ids = (
                await db.scalars(
                    select(AnswerEvaluation.id)
                    .join(Interview)
                    .where(or_(Interview.mode == "practice", Interview.status == "completed"))
                    .order_by(AnswerEvaluation.created_at, AnswerEvaluation.id)
                )
            ).all()
        for identifier in ids:
            async with SessionFactory() as db:
                evaluation = await db.get(AnswerEvaluation, identifier)
                if evaluation:
                    await CandidateMemoryService.update(db, evaluation)
                    await db.commit()
                    count += 1
        print(
            f"Memory backfill inspected {count} stored evaluations. Duplicate evidence was skipped."
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
