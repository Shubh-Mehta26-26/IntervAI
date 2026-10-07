from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.dependencies import DB, CandidateActor
from app.models.interviews import AnswerEvaluation, Interview, InterviewAnswer, InterviewQuestion
from app.models.learning import LearningItem, LearningPlan
from app.models.memory import KnowledgeGap
from app.services.interviews import candidate

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
async def overview(actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    completed = int(await db.scalar(select(func.count()).select_from(Interview).where(Interview.candidate_id == owner.id, Interview.status == "completed")) or 0)
    total = int(await db.scalar(select(func.count()).select_from(Interview).where(Interview.candidate_id == owner.id)) or 0)
    evaluated = int(await db.scalar(select(func.count()).select_from(AnswerEvaluation).join(InterviewAnswer, AnswerEvaluation.answer_id == InterviewAnswer.id).join(InterviewQuestion, InterviewQuestion.id == InterviewAnswer.question_id).join(Interview, Interview.id == InterviewQuestion.interview_id).where(Interview.candidate_id == owner.id)) or 0)
    plans = int(await db.scalar(select(func.count()).select_from(LearningPlan).where(LearningPlan.candidate_id == owner.id)) or 0)
    completed_items = int(await db.scalar(select(func.count()).select_from(LearningItem).join(LearningPlan, LearningPlan.id == LearningItem.plan_id).where(LearningPlan.candidate_id == owner.id, LearningItem.status == "completed")) or 0)
    gaps = int(await db.scalar(select(func.count()).select_from(KnowledgeGap).where(KnowledgeGap.candidate_id == owner.id, KnowledgeGap.status.in_(["confirmed", "learning", "improving"]))) or 0)
    return {"interviews": {"completed": completed, "total": total, "evaluated_answers": evaluated}, "learning": {"plans": plans, "completed_items": completed_items}, "knowledge_gaps": {"active": gaps}, "data_state": "available" if total else "insufficient_data", "note": "All counts describe persisted activity; missing interview evidence is not treated as zero ability."}


@router.get("/skills")
async def skills(actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    rows = (await db.execute(select(InterviewQuestion.skill, AnswerEvaluation.correctness, AnswerEvaluation.relevance, AnswerEvaluation.completeness, AnswerEvaluation.technical_depth, AnswerEvaluation.reasoning, AnswerEvaluation.clarity).join(InterviewAnswer, InterviewAnswer.question_id == InterviewQuestion.id).join(AnswerEvaluation, AnswerEvaluation.answer_id == InterviewAnswer.id).join(Interview, Interview.id == InterviewQuestion.interview_id).where(Interview.candidate_id == owner.id, Interview.status == "completed").order_by(Interview.completed_at, InterviewQuestion.sequence).limit(500))).all()
    grouped = {}
    for skill, *values in rows:
        if not skill:
            continue
        record = grouped.setdefault(skill, {"evidence_count": 0, "dimensions": {name: [] for name in ("correctness", "relevance", "completeness", "technical_depth", "reasoning", "clarity")}})
        record["evidence_count"] += 1
        for name, value in zip(record["dimensions"], values):
            record["dimensions"][name].append(float(value))
    items = [{"skill": key, "evidence_count": value["evidence_count"], "dimensions": {name: round(sum(scores) / len(scores), 3) for name, scores in value["dimensions"].items() if scores}} for key, value in sorted(grouped.items())]
    return {"items": items, "data_state": "available" if items else "insufficient_data", "note": "Descriptive averages of persisted evaluated answers. They are not hiring scores."}


@router.get("/learning")
async def learning(actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    rows = (await db.execute(select(LearningPlan.title, LearningPlan.status, LearningItem.status, func.count(LearningItem.id)).join(LearningItem, LearningItem.plan_id == LearningPlan.id).where(LearningPlan.candidate_id == owner.id).group_by(LearningPlan.id, LearningPlan.title, LearningPlan.status, LearningItem.status).order_by(LearningPlan.created_at.desc()).limit(200))).all()
    plans = {}
    for title, plan_status, item_status, count in rows:
        plan = plans.setdefault(title, {"status": plan_status, "items": {}})
        plan["items"][item_status] = int(count)
    return {"items": [{"title": title, **value} for title, value in plans.items()], "data_state": "available" if plans else "insufficient_data"}
