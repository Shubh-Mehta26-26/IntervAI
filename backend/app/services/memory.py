"""Candidate-scoped persistent evidence, derived memory, and explainable gaps."""

import hashlib

from sqlalchemy import func, select

from app.core.errors import fail
from app.models.identity import Candidate
from app.models.interviews import AnswerEvaluation, Interview, InterviewAnswer, InterviewQuestion
from app.models.knowledge import EvaluationSource, KnowledgeChunk, KnowledgeDocument
from app.models.memory import CandidateMemory, GapTransition, KnowledgeGap, MemoryEvidence
from app.services.memory_policy import (
    POLICY_VERSION,
    concepts,
    gap_decision,
    independent,
    normalized,
)


class CandidateMemoryService:
    @staticmethod
    async def update(db, evaluation: AnswerEvaluation):
        answer = await db.get(InterviewAnswer, evaluation.answer_id)
        interview = await db.get(Interview, evaluation.interview_id)
        if (
            not answer
            or not interview
            or answer.candidate_id != interview.candidate_id
            or answer.interview_id != interview.id
        ):
            raise ValueError("Evaluation ownership mismatch")
        if interview.mode == "simulation" and interview.status != "completed":
            return
        if interview.configuration.get("learning_practice"):
            # Rehearsal follows shown explanations/hints and cannot establish
            # independent recovery. Feedback still uses the existing evaluator.
            return
        owner = await db.scalar(
            select(Candidate).where(Candidate.id == answer.candidate_id).with_for_update()
        )
        if owner is None:
            raise ValueError("Candidate no longer exists")
        question = await db.get(InterviewQuestion, answer.question_id)
        if question is None or question.interview_id != interview.id:
            raise ValueError("Question ownership mismatch")
        root = question
        while root.parent_question_id:
            parent = await db.get(InterviewQuestion, root.parent_question_id)
            if parent is None or parent.interview_id != interview.id:
                raise ValueError("Question chain ownership mismatch")
            root = parent
        source_count = await db.scalar(
            select(func.count())
            .select_from(EvaluationSource)
            .where(
                EvaluationSource.evaluation_id == evaluation.id,
                EvaluationSource.relationship.in_(["supports", "contradicts"]),
            )
        )
        assisted = False
        if question.parent_question_id and interview.configuration.get("show_hints", False):
            parent_answer = await db.scalar(
                select(InterviewAnswer).where(
                    InterviewAnswer.question_id == question.parent_question_id,
                )
            )
            prior_evaluation = (
                await db.scalar(
                    select(AnswerEvaluation).where(
                        AnswerEvaluation.answer_id == parent_answer.id,
                    )
                )
                if parent_answer
                else None
            )
            assisted = bool(prior_evaluation and prior_evaluation.hint)
        grounded = evaluation.grounding_status == "grounded" and source_count > 0
        score, confidence = float(evaluation.correctness), float(evaluation.confidence)
        if interview.interview_type == "coding":
            from app.models.coding import CodingSubmission
            execution = await db.scalar(select(CodingSubmission).where(CodingSubmission.answer_id == answer.id))
            if execution and execution.result and execution.execution_status not in {"SYSTEM_ERROR", "CANCELLED"}:
                # Suite outcomes ground topic/skill evidence; they do not prove every qualitative claim.
                grounded = True
        signals = []
        if score < 0.6:
            signals.append("low_correctness")
        if float(evaluation.completeness) < 0.65:
            signals.append("incomplete_answer")
        if question.parent_question_id and score < 0.6:
            signals.append("failed_follow_up")
        if evaluation.misconceptions:
            signals.append("reported_misconception")
        weak = bool(signals)
        strong = (
            score >= 0.8
            and float(evaluation.completeness) >= 0.75
            and not evaluation.misconceptions
        )
        subjects = {("topic", normalized(question.topic)): question.topic}
        if question.skill:
            subjects[("skill", normalized(question.skill))] = question.skill
        concept_names = set(concepts(question.text + " " + question.topic))
        concept_names.update(
            normalized(x) for x in evaluation.missing_concepts if isinstance(x, str) and x.strip()
        )
        for concept in concept_names:
            subjects[("concept", normalized(concept))] = concept
        # A later explicit concept check contributes recovery evidence to prior
        # misconceptions about that concept, rather than erasing the original claim.
        if strong and grounded:
            prior = (
                await db.scalars(
                    select(CandidateMemory).where(
                        CandidateMemory.candidate_id == owner.id,
                        CandidateMemory.kind.in_(["misconception", "weakness"]),
                        CandidateMemory.topic == question.topic,
                    )
                )
            ).all()
            for item in prior:
                if set(concepts(item.subject)).intersection(concept_names):
                    subjects[(item.kind, item.subject_key)] = item.subject
        for kind, items in (
            ("weakness", evaluation.weaknesses),
            ("strength", evaluation.strengths),
            ("misconception", evaluation.misconceptions),
        ):
            if interview.interview_type == "coding" and source_count == 0:
                continue  # Do not ground subjective LLM misconceptions from execution alone.
            for value in items[:8]:
                if isinstance(value, str) and value.strip():
                    # Conservative exact normalization; no invented equivalence of paraphrases.
                    key = normalized(question.topic + ": " + value)
                    subjects[(kind, key)] = value[:240]
        for (kind, key), subject in sorted(subjects.items()):
            if not key:
                continue
            memory = await db.scalar(
                select(CandidateMemory).where(
                    CandidateMemory.candidate_id == owner.id,
                    CandidateMemory.kind == kind,
                    CandidateMemory.subject_key == key,
                )
            )
            if memory is None:
                memory = CandidateMemory(
                    candidate_id=owner.id,
                    kind=kind,
                    subject_key=key,
                    subject=subject,
                    topic=question.topic,
                    first_seen=evaluation.created_at,
                    last_seen=evaluation.created_at,
                )
                db.add(memory)
                await db.flush()
            duplicate = await db.scalar(
                select(MemoryEvidence.id).where(
                    MemoryEvidence.memory_id == memory.id,
                    MemoryEvidence.evaluation_id == evaluation.id,
                )
            )
            if duplicate:
                continue
            evidence = MemoryEvidence(
                candidate_id=owner.id,
                memory_id=memory.id,
                evaluation_id=evaluation.id,
                interview_id=interview.id,
                root_question_id=root.id,
                correctness=score,
                confidence=confidence,
                grounded=grounded,
                assisted=assisted,
                question_hash=hashlib.sha256(normalized(question.text).encode()).hexdigest(),
                weak=weak or (not strong and kind in {"weakness", "misconception"}),
                strong=strong,
                signals=signals,
                observed_at=evaluation.created_at,
                policy_version=POLICY_VERSION,
            )
            db.add(evidence)
            await db.flush()
            observations = (
                await db.scalars(
                    select(MemoryEvidence)
                    .where(MemoryEvidence.memory_id == memory.id)
                    .order_by(MemoryEvidence.observed_at, MemoryEvidence.id)
                )
            ).all()
            accepted = independent(observations)
            memory.evidence_count = len(observations)
            memory.interview_count = len({x.interview_id for x in observations})
            memory.mean_correctness = (
                sum(x.correctness for x in accepted) / len(accepted) if accepted else None
            )
            memory.evidence_strength = (
                sum(x.confidence for x in accepted) / len(accepted) if accepted else 0
            )
            memory.first_seen = min(x.observed_at for x in observations)
            memory.last_seen = max(x.observed_at for x in observations)
            memory.trend = "insufficient"
            if len(accepted) >= 2:
                delta = accepted[-1].correctness - accepted[0].correctness
                memory.trend = (
                    "improving" if delta >= 0.15 else "declining" if delta <= -0.15 else "stable"
                )
            if kind not in {"topic", "concept", "weakness", "misconception"}:
                continue
            gap = await db.scalar(select(KnowledgeGap).where(KnowledgeGap.memory_id == memory.id))
            if gap is None and not evidence.weak:
                continue
            new = gap is None
            if new:
                gap = KnowledgeGap(
                    candidate_id=owner.id,
                    memory_id=memory.id,
                    status="observed",
                    detected_at=evaluation.created_at,
                    last_seen=evaluation.created_at,
                    policy_version=POLICY_VERSION,
                )
                db.add(gap)
                await db.flush()
            decision = gap_decision(
                observations,
                gap.status,
                gap.baseline_correctness,
                gap.resolved_at,
                now=memory.last_seen,
            )
            before = None if new else gap.status
            if before != decision.status:
                db.add(
                    GapTransition(
                        gap_id=gap.id,
                        evaluation_id=evaluation.id,
                        from_status=before,
                        to_status=decision.status,
                        reason=decision.reason,
                        evidence_ids=decision.evidence_ids,
                        policy_version=POLICY_VERSION,
                    )
                )
            if decision.status == "confirmed" and before != "confirmed":
                gap.confirmed_at = memory.last_seen
                gap.baseline_correctness = memory.mean_correctness
            if decision.status == "resolved" and before != "resolved":
                gap.resolved_at = memory.last_seen
            gap.status = decision.status
            gap.weakness_index = decision.weakness_index
            gap.independent_count = decision.independent_count
            gap.weak_interview_count = decision.weak_interviews
            gap.last_seen = memory.last_seen
        await db.flush()

    @staticmethod
    async def complete_interview(db, interview_id):
        evaluations = (
            await db.scalars(
                select(AnswerEvaluation)
                .where(AnswerEvaluation.interview_id == interview_id)
                .order_by(AnswerEvaluation.created_at, AnswerEvaluation.id)
            )
        ).all()
        for evaluation in evaluations:
            await CandidateMemoryService.update(db, evaluation)

    @staticmethod
    async def memories(db, candidate_id, *, kind=None, limit=100):
        query = select(CandidateMemory).where(CandidateMemory.candidate_id == candidate_id)
        if kind:
            query = query.where(CandidateMemory.kind == kind)
        rows = (
            await db.scalars(
                query.order_by(CandidateMemory.last_seen.desc(), CandidateMemory.id).limit(limit)
            )
        ).all()
        return [memory_value(x) for x in rows]

    @staticmethod
    async def gaps(db, candidate_id, *, status=None, kind=None):
        query = select(KnowledgeGap, CandidateMemory).join(
            CandidateMemory, CandidateMemory.id == KnowledgeGap.memory_id
        )
        query = query.where(KnowledgeGap.candidate_id == candidate_id)
        if status:
            query = query.where(KnowledgeGap.status == status)
        if kind:
            query = query.where(CandidateMemory.kind == kind)
        rows = (
            await db.execute(
                query.order_by(KnowledgeGap.last_seen.desc(), KnowledgeGap.id).limit(100)
            )
        ).all()
        return [gap_value(gap, memory) for gap, memory in rows]

    @staticmethod
    async def evidence(db, candidate_id, memory_id, *, before=None):
        memory = await db.scalar(
            select(CandidateMemory).where(
                CandidateMemory.id == memory_id, CandidateMemory.candidate_id == candidate_id
            )
        )
        if memory is None:
            fail(404, "memory_missing", "Memory item was not found.")
        query = (
            select(MemoryEvidence, InterviewQuestion, InterviewAnswer, AnswerEvaluation)
            .join(AnswerEvaluation, AnswerEvaluation.id == MemoryEvidence.evaluation_id)
            .join(InterviewAnswer, InterviewAnswer.id == AnswerEvaluation.answer_id)
            .join(InterviewQuestion, InterviewQuestion.id == InterviewAnswer.question_id)
            .where(
                MemoryEvidence.candidate_id == candidate_id, MemoryEvidence.memory_id == memory_id
            )
        )
        if before:
            query = query.where(MemoryEvidence.observed_at < before)
        rows = (
            await db.execute(
                query.order_by(MemoryEvidence.observed_at.desc(), MemoryEvidence.id).limit(100)
            )
        ).all()
        results = []
        for evidence, question, answer, evaluation in rows:
            sources = (
                await db.execute(
                    select(EvaluationSource, KnowledgeChunk, KnowledgeDocument)
                    .join(KnowledgeChunk, KnowledgeChunk.id == EvaluationSource.chunk_id)
                    .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
                    .where(EvaluationSource.evaluation_id == evaluation.id)
                )
            ).all()
            results.append(
                {
                    "id": evidence.id,
                    "interview_id": evidence.interview_id,
                    "question_id": question.id,
                    "answer_id": answer.id,
                    "evaluation_id": evaluation.id,
                    "root_question_id": evidence.root_question_id,
                    "question": question.text,
                    "answer_excerpt": answer.text[:600],
                    "correctness": evidence.correctness,
                    "confidence": evidence.confidence,
                    "grounded": evidence.grounded,
                    "signals": evidence.signals,
                    "observed_at": evidence.observed_at,
                    "sources": [
                        {
                            "chunk_id": s.chunk_id,
                            "title": d.title,
                            "source": d.source,
                            "claim": s.supported_claim,
                            "relationship": s.relationship,
                        }
                        for s, c, d in sources
                    ],
                }
            )
        return results

    @staticmethod
    async def gap_detail(db, candidate_id, identifier):
        row = (
            await db.execute(
                select(KnowledgeGap, CandidateMemory)
                .join(CandidateMemory)
                .where(KnowledgeGap.id == identifier, KnowledgeGap.candidate_id == candidate_id)
            )
        ).first()
        if row is None:
            fail(404, "gap_missing", "Knowledge gap was not found.")
        gap, memory = row
        transitions = (
            await db.scalars(
                select(GapTransition)
                .where(GapTransition.gap_id == gap.id)
                .order_by(GapTransition.created_at, GapTransition.id)
                .limit(100)
            )
        ).all()
        return {
            **gap_value(gap, memory),
            "learning_actions": await learning_actions(db, candidate_id, gap.id),
            "evidence": await CandidateMemoryService.evidence(db, candidate_id, memory.id),
            "transitions": [
                {
                    "from_status": x.from_status,
                    "to_status": x.to_status,
                    "reason": x.reason,
                    "evidence_ids": x.evidence_ids,
                    "created_at": x.created_at,
                    "policy_version": x.policy_version,
                }
                for x in transitions
            ],
        }

    @staticmethod
    async def history(db, candidate_id, kind):
        memories = await CandidateMemoryService.memories(db, candidate_id, kind=kind, limit=50)
        query = (
            select(MemoryEvidence)
            .join(CandidateMemory)
            .where(MemoryEvidence.candidate_id == candidate_id, CandidateMemory.kind == kind)
        )
        # Bound history independently of aggregate reads; no interview transcript reload.
        rows = (
            await db.scalars(
                query.order_by(MemoryEvidence.observed_at.desc(), MemoryEvidence.id).limit(500)
            )
        ).all()
        by_id = {}
        for item in reversed(rows):
            by_id.setdefault(item.memory_id, []).append(
                {
                    "id": item.id,
                    "interview_id": item.interview_id,
                    "evaluation_id": item.evaluation_id,
                    "correctness": item.correctness,
                    "grounded": item.grounded,
                    "observed_at": item.observed_at,
                }
            )
        return [{**item, "history": by_id.get(item["id"], [])} for item in memories]

    @staticmethod
    async def planning_context(db, candidate_id, context):
        if not context["configuration"].get("use_memory", True):
            return {"enabled": False, "items": []}
        if context.get("interview_type") == "behavioral":
            return {"enabled": True, "items": [], "policy_version": POLICY_VERSION}
        explicit = context["configuration"].get("selected_topics", [])
        job = context.get("job")
        focus = " ".join(explicit) if explicit else str(job.get("analysis", "")) if job else ""
        query = (
            select(KnowledgeGap, CandidateMemory)
            .join(CandidateMemory)
            .where(
                KnowledgeGap.candidate_id == candidate_id,
                KnowledgeGap.status.in_(["confirmed", "learning", "improving"]),
                CandidateMemory.kind.in_(["topic", "concept"]),
            )
            .order_by(KnowledgeGap.last_seen.desc())
            .limit(30)
        )
        rows = (await db.execute(query)).all()
        items = []
        for gap, memory in rows:
            if focus and not any(
                normalized(x) in normalized(focus) for x in (memory.topic, memory.subject)
            ):
                continue
            items.append(
                {
                    "memory_id": str(memory.id),
                    "subject": memory.subject,
                    "topic": memory.topic,
                    "status": gap.status,
                    "evidence_count": memory.evidence_count,
                    "independent_count": gap.independent_count,
                    "trend": memory.trend,
                    "evidence_strength": memory.evidence_strength,
                    "last_seen": memory.last_seen.isoformat(),
                }
            )
            recent = (
                await db.scalars(
                    select(MemoryEvidence)
                    .where(
                        MemoryEvidence.memory_id == memory.id,
                        MemoryEvidence.candidate_id == candidate_id,
                        MemoryEvidence.grounded.is_(True),
                    )
                    .order_by(MemoryEvidence.observed_at.desc())
                    .limit(2)
                )
            ).all()
            items[-1]["supporting_observations"] = [
                {
                    "evidence_id": str(x.id),
                    "evaluation_id": str(x.evaluation_id),
                    "interview_id": str(x.interview_id),
                    "correctness": x.correctness,
                    "confidence": x.confidence,
                }
                for x in recent
            ]
            if len(items) == 6:
                break
        return {
            "enabled": True,
            "items": items,
            "policy_version": POLICY_VERSION,
            "priority_rule": "Current job and selected topics take priority; memory suggests relevant concept checks only.",
        }


def memory_value(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "kind",
            "subject",
            "topic",
            "evidence_count",
            "interview_count",
            "mean_correctness",
            "evidence_strength",
            "trend",
            "first_seen",
            "last_seen",
        )
    }


def gap_value(gap, memory):
    return {
        "id": gap.id,
        "memory_id": memory.id,
        "subject": memory.subject,
        "kind": memory.kind,
        "topic": memory.topic,
        "status": gap.status,
        "evidence_count": memory.evidence_count,
        "interview_count": memory.interview_count,
        "independent_count": gap.independent_count,
        "weak_interview_count": gap.weak_interview_count,
        "weakness_index": gap.weakness_index,
        "trend": memory.trend,
        "first_seen": gap.detected_at,
        "last_seen": gap.last_seen,
        "policy_version": gap.policy_version,
        "provisional": gap.status == "observed",
    }


async def learning_actions(db, candidate_id, gap_id):
    from app.models.learning import LearningAction

    rows = (await db.scalars(select(LearningAction).where(
        LearningAction.candidate_id == candidate_id,
        LearningAction.gap_id == gap_id,
    ).order_by(LearningAction.created_at).limit(100))).all()
    return [{"from_status": x.from_status, "to_status": x.to_status,
             "reason": x.reason, "created_at": x.created_at,
             "plan_id": x.plan_id} for x in rows]
