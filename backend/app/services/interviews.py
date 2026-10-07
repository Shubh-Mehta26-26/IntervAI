import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, inspect, select

from app.core.errors import fail
from app.models.identity import Candidate, Education, Experience, User
from app.models.intelligence import CandidateJobMatch, JobDescription, Resume
from app.models.interviews import (
    AdaptiveDecision,
    AnswerEvaluation,
    Interview,
    InterviewAnswer,
    InterviewJob,
    InterviewPlan,
    InterviewQuestion,
    InterviewRound,
)
from app.models.knowledge import EvaluationSource, KnowledgeChunk, KnowledgeDocument, RetrievalLog
from app.providers.embeddings import EmbeddingProvider
from app.providers.llm import LLMProvider
from app.schemas.interviews import (
    EvaluationOut,
    GroundedEvaluationResult,
    InterviewOut,
    PlanResult,
    PlanTopic,
    QuestionResult,
)
from app.services.adaptive import POLICY_VERSION, decide
from app.services.coding import (
    authoritative_evaluation,
    evaluation_context,
    qualitative_analysis,
    question_fields,
    select_problem,
)
from app.services.interview_prompts import (
    PROMPT_VERSION,
    evaluation_prompt,
    plan_prompt,
    question_prompt,
)
from app.services.knowledge import RETRIEVAL_VERSION, retrieve, validate_citations
from app.services.memory import CandidateMemoryService
from app.services.memory_policy import normalized


def check_retry_question(question, context, previous=()):
    if not context.get("retry_targets"):
        return
    seen = [q.text for q in previous]
    for target in context["retry_targets"]:
        seen.extend(target.get("previous_questions", []))
        seen.extend(target["baseline"].get("questions", []))
    if normalized(question.question) in {normalized(text) for text in seen}:
        from app.providers.llm import LLMOutputError
        raise LLMOutputError("Retry question repeats a prior independent check.")


async def candidate(db, user_id: UUID) -> Candidate:
    row = await db.scalar(select(Candidate).where(Candidate.user_id == user_id))
    if row is None:
        fail(404, "candidate_missing", "Candidate profile was not found.")
    return row


async def owned(db, identifier: UUID, candidate_id: UUID, lock: bool = False) -> Interview:
    statement = select(Interview).where(
        Interview.id == identifier, Interview.candidate_id == candidate_id
    )
    if lock:
        statement = statement.with_for_update()
    row = await db.scalar(statement)
    if row is None:
        fail(404, "interview_missing", "Interview was not found.")
    return row


def check_revision(row: Interview, expected: int):
    if row.revision != expected:
        fail(409, "revision_conflict", "This interview changed. Reload before continuing.")


def compact(value, limit=4000):
    if value is None:
        return None
    if isinstance(value, str):
        return value[:limit]
    return value


async def context_snapshot(db, row: Interview) -> dict:
    profile = await db.get(Candidate, row.candidate_id)
    user = await db.scalar(select(User).where(User.id == profile.user_id))
    experiences = (
        await db.scalars(select(Experience).where(Experience.candidate_id == profile.id))
    ).all()
    education = (
        await db.scalars(select(Education).where(Education.candidate_id == profile.id))
    ).all()
    resume = await db.get(Resume, row.resume_id) if row.resume_id else None
    job = await db.get(JobDescription, row.job_id) if row.job_id else None
    match = (
        await db.scalar(select(CandidateJobMatch).where(CandidateJobMatch.job_id == row.job_id))
        if row.job_id
        else None
    )
    result = {
        "interview_type": row.interview_type,
        "configuration": row.configuration,
        "question_limit": row.question_limit,
        "candidate": {
            "display_name": user.display_name,
            "headline": profile.headline,
            "biography": compact(profile.biography, 1500),
            "experience_months": profile.experience_months,
            "career_interests": profile.career_interests,
            "experience": [
                {
                    "title": x.title,
                    "organization": x.organization,
                    "description": compact(x.description, 800),
                }
                for x in experiences[:8]
            ],
            "education": [
                {
                    "qualification": x.qualification,
                    "field": x.field_of_study,
                    "institution": x.institution,
                }
                for x in education[:6]
            ],
        },
        "resume": (
            {"name": resume.original_name, "parsed": resume.parsed_data}
            if resume and resume.status == "parsed"
            else None
        ),
        "job": (
            {
                "title": job.title,
                "company": job.company,
                "analysis": job.analysis,
                "description": compact(job.description, 5000),
            }
            if job
            else None
        ),
        "match": match.result if match else None,
    }
    result["candidate_memory"] = await CandidateMemoryService.planning_context(db, row.candidate_id, result)
    result["retry_targets"] = row.configuration.get("retry_targets", [])
    return result


def allocate_topics(plan: PlanResult, limit: int) -> PlanResult:
    topics = plan.topics[:limit]
    remaining = limit
    for index, topic in enumerate(topics):
        slots_left = len(topics) - index - 1
        topic.question_budget = max(1, min(topic.question_budget, remaining - slots_left))
        remaining -= topic.question_budget
    if remaining:
        topics[-1].question_budget += remaining
    plan.topics = topics
    return plan


def next_topic(rounds: list[InterviewRound], current: str, counts: dict[str, int]) -> str | None:
    for item in rounds:
        if counts.get(item.topic, 0) < item.question_budget and item.topic != current:
            return item.topic
    return None


async def job_snapshot(factory, job_id: UUID, claim_id: UUID):
    async with factory() as db:
        job = await db.scalar(
            select(InterviewJob).where(InterviewJob.id == job_id, InterviewJob.claim_id == claim_id)
        )
        if job is None:
            return None
        interview = await db.get(Interview, job.interview_id)
        if (
            interview is None
            or interview.revision != job.expected_revision
            or interview.status in {"cancelled", "completed"}
        ):
            job.status = "cancelled"
            await db.commit()
            return None
        context = await context_snapshot(db, interview)
        questions = (
            await db.scalars(
                select(InterviewQuestion)
                .where(InterviewQuestion.interview_id == interview.id)
                .order_by(InterviewQuestion.sequence)
            )
        ).all()
        answers = (
            await db.scalars(
                select(InterviewAnswer)
                .where(InterviewAnswer.interview_id == interview.id)
                .order_by(InterviewAnswer.sequence)
            )
        ).all()
        rounds = (
            await db.scalars(
                select(InterviewRound)
                .where(InterviewRound.interview_id == interview.id)
                .order_by(InterviewRound.ordinal)
            )
        ).all()
        return job, interview, context, questions, answers, rounds


async def save_job_result(factory, job_id, claim_id, result):
    async with factory() as db:
        job = await db.scalar(
            select(InterviewJob)
            .where(InterviewJob.id == job_id, InterviewJob.claim_id == claim_id)
            .with_for_update()
        )
        if job and job.status == "running":
            job.result = result
            await db.commit()


async def process_interview_job(
    factory,
    job_id: UUID,
    claim_id: UUID,
    provider: LLMProvider,
    embedding_provider: EmbeddingProvider | None = None,
):
    snapshot = await job_snapshot(factory, job_id, claim_id)
    if snapshot is None:
        return
    job, interview, context, questions, answers, rounds = snapshot
    cached = job.result or {}
    if job.kind == "plan":
        if "plan" in cached:
            plan = PlanResult.model_validate(cached["plan"])
        else:
            system, user = plan_prompt(context)
            plan = allocate_topics(
                await provider.structured(
                    system=system, user=user, schema=PlanResult, name="interview_plan"
                ),
                interview.question_limit,
            )
            if interview.interview_type == "coding":
                topics = interview.configuration.get("selected_topics") or ["Arrays", "Hash tables", "Binary search"]
                plan = allocate_topics(PlanResult(objectives=plan.objectives, topics=[PlanTopic(title=t, objective="Solve an original validated algorithm problem and explain the approach.", question_budget=1, initial_difficulty=interview.configuration.get("difficulty", 2)) for t in topics[:interview.question_limit]]), interview.question_limit)
            if context["retry_targets"]:
                # The provider can phrase objectives; target scope and budgets
                # remain authoritative application state.
                targets = context["retry_targets"]
                topics = list(dict.fromkeys(x["topic"] for x in targets))
                plan = allocate_topics(PlanResult(
                    objectives=["Independently reassess the persisted retry targets."],
                    topics=[PlanTopic(title=topic,
                        objective="Check: " + ", ".join(x["subject"] for x in targets if x["topic"] == topic)[:440],
                        question_budget=1, initial_difficulty=2) for topic in topics],
                ), interview.question_limit)
            cached["plan"] = plan.model_dump()
            await save_job_result(factory, job.id, claim_id, cached)
        target = plan.topics[0]
        qcontext = {
            **context,
            "plan": plan.model_dump(),
            "target_topic": target.title,
            "target_difficulty": target.initial_difficulty,
            "adaptive_action": "first_question",
            "previous_questions": [],
        }
        system, user = question_prompt(qcontext)
        question = (QuestionResult(question="Solve the selected validated coding problem.", topic=target.title, skill=target.title, difficulty=target.initial_difficulty, question_type="technical", reason="Validated coding problem selected for planned topic.") if interview.interview_type == "coding" else await provider.structured(
            system=system, user=user, schema=QuestionResult, name="interview_question"
        ))
        question.topic, question.difficulty = target.title, target.initial_difficulty
        check_retry_question(question, context)
        async with factory() as db:
            stored_job = await db.scalar(
                select(InterviewJob)
                .where(InterviewJob.id == job.id, InterviewJob.claim_id == claim_id)
                .with_for_update()
            )
            row = await db.scalar(
                select(Interview).where(Interview.id == interview.id).with_for_update()
            )
            if (
                not stored_job
                or row.revision != stored_job.expected_revision
                or row.status != "planning"
            ):
                if stored_job:
                    stored_job.status = "cancelled"
                    await db.commit()
                return
            saved_plan = InterviewPlan(
                interview_id=row.id,
                objectives=plan.objectives,
                topics=[x.model_dump() for x in plan.topics],
                context_snapshot=context,
                prompt_version=PROMPT_VERSION,
                provider=provider.name,
                model=provider.model,
            )
            db.add(saved_plan)
            await db.flush()
            saved_rounds = []
            for ordinal, item in enumerate(plan.topics, 1):
                round_row = InterviewRound(
                    interview_id=row.id,
                    ordinal=ordinal,
                    title=item.title,
                    topic=item.title,
                    objective=item.objective,
                    question_budget=item.question_budget,
                    initial_difficulty=item.initial_difficulty,
                    status="active" if ordinal == 1 else "pending",
                )
                db.add(round_row)
                saved_rounds.append(round_row)
            await db.flush()
            coding_fields = question_fields(await select_problem(db, row, question.topic, question.difficulty, [])) if row.interview_type == "coding" else {}
            db.add(
                InterviewQuestion(
                    interview_id=row.id,
                    round_id=saved_rounds[0].id,
                    sequence=1,
                    **({"text": question.question, "topic": question.topic, "skill": question.skill, "difficulty": question.difficulty, "question_type": question.question_type} | coding_fields),
                    reason=question.reason,
                    operation_id=stored_job.id,
                )
            )
            row.status, row.started_at, row.current_round, row.current_question = (
                "waiting_for_answer",
                datetime.now(timezone.utc),
                1,
                1,
            )
            row.revision += 1
            stored_job.status, stored_job.lease_until = "succeeded", None
            await db.commit()
        return

    answer = next((x for x in answers if x.id == job.answer_id), None)
    question = next((x for x in questions if answer and x.id == answer.question_id), None)
    if answer is None or question is None:
        raise RuntimeError("Interview answer context is missing")
    if embedding_provider is None:
        raise RuntimeError("Embedding provider is required for grounded answer evaluation")
    async with factory() as db:
        retrieval_query, retrieved = await retrieve(
            db, embedding_provider, question=question, answer=answer
        )
        coding_context = await evaluation_context(db, answer)
    if "evaluation" in cached:
        evaluation = GroundedEvaluationResult.model_validate(cached["evaluation"])
    else:
        econtext = {
            **context,
            "question": {
                "text": question.text,
                "topic": question.topic,
                "difficulty": question.difficulty,
            },
            "candidate_answer": answer.text,
            "coding_evidence": coding_context,
            "retrieved_knowledge": [item.prompt_value() for item in retrieved],
        }
        system, user = evaluation_prompt(econtext)
        evaluation = await provider.structured(
            system=system, user=user, schema=GroundedEvaluationResult, name="answer_evaluation"
        )
        validate_citations(evaluation, retrieved)
        evaluation = authoritative_evaluation(evaluation, coding_context)
        cached["evaluation"] = evaluation.model_dump(mode="json")
        await save_job_result(factory, job.id, claim_id, cached)
    evaluation = authoritative_evaluation(evaluation, coding_context)
    coding_analysis = None
    if coding_context:
        if "coding_analysis" not in cached:
            cached["coding_analysis"] = (await qualitative_analysis(provider, coding_context)).model_dump()
            await save_job_result(factory, job.id, claim_id, cached)
        coding_analysis = cached["coding_analysis"]
    topic_weak = 0
    for prior in questions:
        if prior.topic != question.topic:
            continue
        prior_answer = next((x for x in answers if x.question_id == prior.id), None)
        if prior_answer:
            async with factory() as db:
                prior_eval = await db.scalar(
                    select(AnswerEvaluation).where(AnswerEvaluation.answer_id == prior_answer.id)
                )
                if prior_eval and float(prior_eval.correctness) < 0.5:
                    topic_weak += 1
    counts = {r.topic: sum(1 for q in questions if q.topic == r.topic) for r in rounds}
    decision = decide(
        evaluation,
        current_difficulty=question.difficulty,
        topic=question.topic,
        answered_count=len(answers),
        question_limit=interview.question_limit,
        topic_weak_count=topic_weak,
        next_topic=next_topic(rounds, question.topic, counts),
    )
    next_question = None
    if decision.action != "end_interview":
        qcontext = {
            **context,
            "plan": [r.topic for r in rounds],
            "target_topic": decision.target_topic,
            "target_difficulty": decision.difficulty,
            "adaptive_action": decision.action,
            "previous_questions": [
                {
                    "question": q.text,
                    "answer": next((a.text for a in answers if a.question_id == q.id), None),
                }
                for q in questions[-6:]
            ],
            "previous_evaluation": evaluation.model_dump(mode="json"),
        }
        system, user = question_prompt(qcontext)
        next_question = (QuestionResult(question="Solve the next validated coding problem.", topic=decision.target_topic or question.topic, skill=question.skill, difficulty=decision.difficulty, question_type="technical", reason=decision.explanation) if interview.interview_type == "coding" else await provider.structured(
            system=system, user=user, schema=QuestionResult, name="interview_question"
        ))
        next_question.topic, next_question.difficulty = (
            decision.target_topic or question.topic,
            decision.difficulty,
        )
        check_retry_question(next_question, context, questions)
    async with factory() as db:
        stored_job = await db.scalar(
            select(InterviewJob)
            .where(InterviewJob.id == job.id, InterviewJob.claim_id == claim_id)
            .with_for_update()
        )
        row = await db.scalar(
            select(Interview).where(Interview.id == interview.id).with_for_update()
        )
        if (
            not stored_job
            or row.revision != stored_job.expected_revision
            or row.status != "evaluating"
        ):
            if stored_job:
                stored_job.status = "cancelled"
                await db.commit()
            return
        stored_answer = await db.get(InterviewAnswer, answer.id)
        stored_question = await db.get(InterviewQuestion, question.id)
        evaluation_row = AnswerEvaluation(
            interview_id=row.id,
            answer_id=answer.id,
            **evaluation.model_dump(exclude={"knowledge_evidence"}),
            prompt_version=PROMPT_VERSION,
            provider=provider.name,
            model=provider.model,
        )
        db.add(evaluation_row)
        if coding_analysis:
            from app.models.coding import CodingSubmission
            submission = await db.scalar(select(CodingSubmission).where(CodingSubmission.answer_id == answer.id))
            submission.analysis = {**coding_analysis, "kind": "LLM-estimated complexity", "provider": provider.name, "model": provider.model}
        await db.flush()
        retrieved_by_id = {item.chunk_id: item for item in retrieved}
        db.add(
            RetrievalLog(
                evaluation_id=evaluation_row.id,
                interview_id=row.id,
                answer_id=answer.id,
                query=retrieval_query,
                filters={
                    "status": "ready",
                    "embedding_provider": embedding_provider.name,
                    "embedding_model": embedding_provider.model,
                },
                results=[item.log_value() for item in retrieved],
                provider=embedding_provider.name,
                model=embedding_provider.model,
                retrieval_version=RETRIEVAL_VERSION,
            )
        )
        for evidence in evaluation.knowledge_evidence:
            item = retrieved_by_id[evidence.knowledge_chunk_id]
            db.add(
                EvaluationSource(
                    evaluation_id=evaluation_row.id,
                    chunk_id=item.chunk_id,
                    retrieval_rank=item.rank,
                    similarity=item.similarity,
                    relationship=evidence.relationship,
                    supported_claim=evidence.claim,
                )
            )
        db.add(
            AdaptiveDecision(
                interview_id=row.id,
                evaluation_id=evaluation_row.id,
                action=decision.action,
                target_topic=decision.target_topic,
                difficulty=decision.difficulty,
                reason_codes=decision.reason_codes,
                explanation=decision.explanation,
                policy_version=POLICY_VERSION,
            )
        )
        stored_answer.status, stored_question.state = "evaluated", "answered"
        if next_question is None:
            row.status, row.completed_at = "completed", datetime.now(timezone.utc)
            row.summary = await build_summary(db, row.id)
        else:
            target_round = next((r for r in rounds if r.topic == next_question.topic), rounds[0])
            coding_fields = question_fields(await select_problem(db, row, next_question.topic, next_question.difficulty, questions)) if row.interview_type == "coding" else {}
            db.add(
                InterviewQuestion(
                    interview_id=row.id,
                    round_id=target_round.id,
                    parent_question_id=question.id
                    if decision.action in {"ask_follow_up", "test_missing_concept"}
                    else None,
                    sequence=len(questions) + 1,
                    **({"text": next_question.question, "topic": next_question.topic, "skill": next_question.skill, "difficulty": next_question.difficulty,
                    "question_type": "follow_up"
                    if decision.action in {"ask_follow_up", "test_missing_concept"}
                    else next_question.question_type} | coding_fields),
                    reason=next_question.reason,
                    operation_id=stored_job.id,
                )
            )
            row.status, row.current_question = "waiting_for_answer", len(questions) + 1
            row.current_round = target_round.ordinal
        row.revision += 1
        stored_job.status, stored_job.lease_until = "succeeded", None
        await db.flush()
        if row.mode == "practice":
            await CandidateMemoryService.update(db, evaluation_row)
        elif row.status == "completed":
            await CandidateMemoryService.complete_interview(db, row.id)
        from app.services.learning import record_comparison
        await record_comparison(db, row)
        await db.commit()


async def build_summary(db, interview_id: UUID) -> dict:
    evaluations = (
        await db.scalars(
            select(AnswerEvaluation).where(AnswerEvaluation.interview_id == interview_id)
        )
    ).all()
    dimensions = [
        "correctness",
        "relevance",
        "completeness",
        "technical_depth",
        "reasoning",
        "clarity",
    ]
    values = {name: [float(getattr(x, name)) for x in evaluations] for name in dimensions}
    strengths = [item for x in evaluations for item in x.strengths]
    weaknesses = [item for x in evaluations for item in x.weaknesses]
    return {
        "dimension_averages": {
            name: round(sum(items) / len(items), 3) if items else None
            for name, items in values.items()
        },
        "evaluated_answers": max((len(items) for items in values.values()), default=0),
        "strengths": list(dict.fromkeys(strengths))[:8],
        "development_areas": list(dict.fromkeys(weaknesses))[:8],
        "note": "Dimension values summarize stored answer evaluations on a 0 to 1 evidence scale; they are not a hiring score.",
    }


async def output(db, row: Interview) -> InterviewOut:
    # UPDATE expressions such as updated_at=now() can expire after a commit.
    # Explicit async refresh prevents implicit database IO during serialization.
    if inspect(row).expired_attributes:
        await db.refresh(row)
    current = (
        await db.scalar(
            select(InterviewQuestion).where(
                InterviewQuestion.interview_id == row.id,
                InterviewQuestion.sequence == row.current_question,
            )
        )
        if row.current_question
        else None
    )
    plan = await db.scalar(select(InterviewPlan).where(InterviewPlan.interview_id == row.id))
    practice_eval = practice_decision = None
    if row.mode == "practice":
        evaluation = await db.scalar(
            select(AnswerEvaluation)
            .where(AnswerEvaluation.interview_id == row.id)
            .order_by(AnswerEvaluation.created_at.desc())
            .limit(1)
        )
        if evaluation:
            practice_eval = await evaluation_output(db, evaluation)
            practice_decision = await db.scalar(
                select(AdaptiveDecision).where(AdaptiveDecision.evaluation_id == evaluation.id)
            )
    answered = await db.scalar(
        select(func.count())
        .select_from(InterviewAnswer)
        .where(InterviewAnswer.interview_id == row.id)
    )
    return InterviewOut(
        **{
            key: getattr(row, key)
            for key in [
                "id",
                "interview_type",
                "mode",
                "status",
                "revision",
                "job_id",
                "resume_id",
                "question_limit",
                "duration_minutes",
                "configuration",
                "current_round",
                "current_question",
                "started_at",
                "completed_at",
                "created_at",
                "updated_at",
                "summary",
            ]
        },
        progress={"answered": answered, "total": row.question_limit},
        current=current,
        plan=plan,
        practice_feedback=practice_eval,
        practice_decision=practice_decision,
        error={"code": row.error_code, "message": row.error_message} if row.error_code else None,
    )


async def evaluation_output(db, evaluation: AnswerEvaluation) -> EvaluationOut:
    sources = (
        await db.execute(
            select(EvaluationSource, KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeChunk, KnowledgeChunk.id == EvaluationSource.chunk_id)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(EvaluationSource.evaluation_id == evaluation.id)
            .order_by(EvaluationSource.retrieval_rank)
        )
    ).all()
    return EvaluationOut.model_validate(
        {
            **evaluation.__dict__,
            "knowledge_evidence": [
                {
                    "knowledge_chunk_id": source.chunk_id,
                    "document_id": document.id,
                    "title": document.title,
                    "source": document.source,
                    "content": chunk.content,
                    "retrieval_rank": source.retrieval_rank,
                    "similarity": source.similarity,
                    "claim": source.supported_claim,
                    "relationship": source.relationship,
                }
                for source, chunk, document in sources
            ],
        }
    )


def answer_hash(question_id: UUID, text: str, duration: int | None) -> str:
    return hashlib.sha256(
        json.dumps([str(question_id), text, duration], separators=(",", ":")).encode()
    ).hexdigest()
