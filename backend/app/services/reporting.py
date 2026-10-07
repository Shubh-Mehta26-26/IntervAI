"""Versioned interview reports and a dependency-free, source-snapshot PDF renderer."""

from datetime import datetime, timezone
from io import BytesIO

from sqlalchemy import func, select

from app.core.errors import fail
from app.models.career import CareerAnalysis
from app.models.coding import CodingProblem, CodingSubmission
from app.models.identity import Candidate, User
from app.models.intelligence import JobDescription, Resume
from app.models.interviews import (
    AdaptiveDecision,
    AnswerEvaluation,
    Interview,
    InterviewAnswer,
    InterviewQuestion,
)
from app.models.knowledge import EvaluationSource, KnowledgeChunk, KnowledgeDocument
from app.models.learning import LearningItem, LearningPlan
from app.models.memory import CandidateMemory, KnowledgeGap
from app.models.reporting import Report, ReportVersion
from app.models.vision import IntegrityEvent
from app.models.voice import VoiceSession, VoiceTurn
from app.services.career_policy import digest
from app.services.interviews import build_summary

SCHEMA_VERSION = 1
DIMENSIONS = ("correctness", "relevance", "completeness", "technical_depth", "reasoning", "clarity")


async def build_snapshot(db, candidate_id, interview_id):
    interview = await db.scalar(
        select(Interview).where(
            Interview.id == interview_id,
            Interview.candidate_id == candidate_id,
        )
    )
    if interview is None:
        fail(404, "interview_missing", "The interview was not found.")
    if interview.status != "completed":
        fail(409, "interview_incomplete", "Complete the interview before generating its report.")
    candidate = await db.get(Candidate, candidate_id)
    user = await db.get(User, candidate.user_id)
    job = await db.get(JobDescription, interview.job_id) if interview.job_id else None
    resume = await db.get(Resume, interview.resume_id) if interview.resume_id else None
    evaluations = (
        await db.execute(
            select(InterviewQuestion, InterviewAnswer, AnswerEvaluation)
            .join(InterviewAnswer, InterviewAnswer.question_id == InterviewQuestion.id)
            .join(AnswerEvaluation, AnswerEvaluation.answer_id == InterviewAnswer.id)
            .where(InterviewQuestion.interview_id == interview_id)
            .order_by(InterviewQuestion.sequence)
        )
    ).all()
    summary = await build_summary(db, interview_id)
    evaluation_rows = []
    for question, answer, evaluation in evaluations:
        decision = await db.scalar(
            select(AdaptiveDecision).where(AdaptiveDecision.evaluation_id == evaluation.id)
        )
        source_rows = (
            await db.execute(
                select(EvaluationSource, KnowledgeChunk, KnowledgeDocument)
                .join(KnowledgeChunk, KnowledgeChunk.id == EvaluationSource.chunk_id)
                .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
                .where(EvaluationSource.evaluation_id == evaluation.id)
                .order_by(EvaluationSource.retrieval_rank)
            )
        ).all()
        evaluation_rows.append(
            {
                "question_id": str(question.id),
                "answer_id": str(answer.id),
                "sequence": question.sequence,
                "question": question.text[:1200],
                "topic": question.topic,
                "skill": question.skill,
                "difficulty": question.difficulty,
                "answer_excerpt": answer.text[:900],
                "answer_truncated": len(answer.text) > 900,
                "dimensions": {name: float(getattr(evaluation, name)) for name in DIMENSIONS},
                "confidence": float(evaluation.confidence),
                "grounding_status": evaluation.grounding_status,
                "strengths": evaluation.strengths[:8],
                "development_areas": evaluation.weaknesses[:8],
                "adaptive_decision": {
                    "action": decision.action,
                    "reason": decision.explanation,
                    "policy_version": decision.policy_version,
                }
                if decision
                else None,
                "sources": [
                    {
                        "chunk_id": str(source.chunk_id),
                        "title": document.title,
                        "source": document.source,
                        "relationship": source.relationship,
                        "claim": source.supported_claim[:400],
                        "similarity": float(source.similarity),
                    }
                    for source, _, document in source_rows
                ],
            }
        )

    coding_rows = (
        await db.execute(
            select(CodingSubmission, CodingProblem)
            .join(CodingProblem, CodingProblem.id == CodingSubmission.problem_id)
            .where(
                CodingSubmission.candidate_id == candidate_id,
                CodingSubmission.interview_id == interview_id,
                CodingSubmission.mode == "submit",
            )
            .order_by(CodingSubmission.created_at)
        )
    ).all()
    coding = [
        {
            "submission_id": str(submission.id),
            "problem_id": str(problem.id),
            "problem": problem.title,
            "topic": problem.topic,
            "difficulty": problem.difficulty,
            "language": submission.language,
            "status": submission.status,
            "execution_status": submission.execution_status,
            "tests_passed": (submission.result or {}).get("tests_passed"),
            "tests_total": (submission.result or {}).get("tests_total"),
            "execution_time_ms": (submission.result or {}).get("execution_time_ms"),
            "memory_kb": (submission.result or {}).get("memory_kb"),
            "complexity_estimate": {
                k: (submission.analysis or {}).get(k)
                for k in ("time_complexity", "space_complexity")
            },
        }
        for submission, problem in coding_rows
    ]

    voice_session = await db.scalar(select(VoiceSession).where(VoiceSession.interview_id == interview_id))
    voice_turns = (
        await db.scalars(
            select(VoiceTurn)
            .where(VoiceTurn.session_id == voice_session.id, VoiceTurn.kind == "stt")
            .order_by(VoiceTurn.created_at)
        )
    ).all() if voice_session else []
    communication = [
        {
            "question_id": str(turn.question_id),
            **{
                name: (turn.metrics or {}).get(name)
                for name in ("duration_seconds", "speech_duration_seconds", "silence_duration_seconds", "pause_count", "word_count", "filler_count", "speaking_rate_wpm", "method")
            },
        }
        for turn in voice_turns
        if turn.metrics
    ]

    events = (
        await db.scalars(
            select(IntegrityEvent)
            .where(IntegrityEvent.candidate_id == candidate_id, IntegrityEvent.interview_id == interview_id)
            .order_by(IntegrityEvent.started_at)
            .limit(300)
        )
    ).all()
    event_counts = {}
    for event in events:
        event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
    integrity = {
        "total_events": len(events),
        "event_counts": event_counts,
        "review_events": [
            {
                "type": event.event_type,
                "severity": event.severity,
                "started_at": event.started_at.isoformat(),
                "ended_at": event.ended_at.isoformat() if event.ended_at else None,
                "duration_ms": event.duration_ms,
                "confidence": event.confidence,
                "provenance": event.details.get("provenance", "server_inference"),
            }
            for event in events
        ],
        "note": "Observable visual signals only. They do not establish identity, intent, policy violation, or dishonesty and are not a hiring score.",
    }

    memory_gaps = (
        await db.execute(
            select(KnowledgeGap, CandidateMemory)
            .join(CandidateMemory, CandidateMemory.id == KnowledgeGap.memory_id)
            .where(
                KnowledgeGap.candidate_id == candidate_id,
                KnowledgeGap.status.in_(["confirmed", "learning", "improving"]),
            )
            .order_by(KnowledgeGap.status, CandidateMemory.subject)
            .limit(30)
        )
    ).all()
    gaps = [
        {
            "id": str(gap.id),
            "subject": memory.subject,
            "topic": memory.topic,
            "status": gap.status,
            "independent_evidence_count": gap.independent_count,
            "last_seen": gap.last_seen.isoformat(),
        }
        for gap, memory in memory_gaps
    ]
    plans = (
        await db.scalars(
            select(LearningPlan).where(LearningPlan.candidate_id == candidate_id)
            .order_by(LearningPlan.created_at.desc()).limit(20)
        )
    ).all()
    item_progress = (
        await db.execute(
            select(LearningItem.plan_id, LearningItem.status, func.count())
            .where(LearningItem.plan_id.in_([p.id for p in plans]))
            .group_by(LearningItem.plan_id, LearningItem.status)
        )
    ).all() if plans else []
    learning = [
        {
            "plan_id": str(plan.id),
            "title": plan.title,
            "status": plan.status,
            "completed_items": sum(count for pid, status, count in item_progress if pid == plan.id and status == "completed"),
            "total_items": sum(count for pid, _, count in item_progress if pid == plan.id),
        }
        for plan in plans
    ]
    career = await db.scalar(
        select(CareerAnalysis).where(CareerAnalysis.candidate_id == candidate_id)
        .order_by(CareerAnalysis.version.desc()).limit(1)
    )
    career_summary = None
    if career:
        career_summary = {
            "analysis_version": career.version,
            "generated_at": career.created_at.isoformat(),
            "roles": [
                {
                    "name": row["role"]["name"],
                    "status_counts": row["counts"],
                }
                for row in career.result["alignments"]
            ],
            "note": "Career analysis is a separate candidate-controlled evidence snapshot.",
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "candidate": {"display_name": user.display_name, "headline": candidate.headline},
        "interview": {
            "id": str(interview.id),
            "type": interview.interview_type,
            "mode": interview.mode,
            "status": interview.status,
            "created_at": interview.created_at.isoformat(),
            "started_at": interview.started_at.isoformat() if interview.started_at else None,
            "completed_at": interview.completed_at.isoformat() if interview.completed_at else None,
            "duration_minutes": interview.duration_minutes,
            "job_id": str(job.id) if job else None,
            "job_title": job.title if job else None,
            "resume_version": resume.version if resume else None,
        },
        "performance": summary,
        "evaluations": evaluation_rows,
        "strengths": summary["strengths"],
        "development_areas": summary["development_areas"],
        "coding": coding,
        "communication": communication,
        "integrity": integrity,
        "knowledge_gaps": gaps,
        "learning": learning,
        "career": career_summary,
        "evidence_references": [
            {"kind": "question", "id": row["question_id"], "label": f"Question {row['sequence']}"}
            for row in evaluation_rows
        ],
        "limitations": [
            "Evaluation dimensions are answer-level evidence, not a hiring score.",
            "Communication values are measurements, not personality or competence judgments.",
            integrity["note"],
            "LLM complexity and qualitative code analysis are estimates when present.",
        ],
    }


async def generate(db, candidate_id, interview_id):
    snapshot = await build_snapshot(db, candidate_id, interview_id)
    fingerprint = digest(snapshot | {"schema_version": SCHEMA_VERSION})
    report = await db.scalar(
        select(Report).where(Report.candidate_id == candidate_id, Report.interview_id == interview_id)
    )
    if report is None:
        report = Report(candidate_id=candidate_id, interview_id=interview_id, latest_version=0)
        db.add(report)
        await db.flush()
    existing = await db.scalar(
        select(ReportVersion).where(
            ReportVersion.report_id == report.id,
            ReportVersion.source_fingerprint == fingerprint,
        )
    )
    if existing:
        return report, existing
    version = report.latest_version + 1
    row = ReportVersion(
        report_id=report.id,
        candidate_id=candidate_id,
        version=version,
        schema_version=SCHEMA_VERSION,
        source_fingerprint=fingerprint,
        snapshot=snapshot,
        generated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    report.latest_version = version
    await db.commit()
    await db.refresh(row)
    return report, row


def output(report, version):
    return {
        "id": str(report.id),
        "interview_id": str(report.interview_id),
        "candidate_id": str(report.candidate_id),
        "version": version.version,
        "schema_version": version.schema_version,
        "generated_at": version.generated_at.isoformat(),
        "snapshot": version.snapshot,
        "pdf_url": f"/api/v1/reports/{report.id}/pdf?version={version.version}",
    }


def make_pdf(snapshot, version):
    """Render the immutable snapshot using built-in PDF text/shape operators."""
    pages = []
    ops = []
    y = 746
    page_no = 0

    def literal(value):
        encoded = str(value).encode("cp1252", errors="replace").decode("cp1252")
        return encoded.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("\r", " ").replace("\n", " ")

    def new_page():
        nonlocal ops, y, page_no
        if ops:
            ops.extend(["0.32 0.4 0.5 rg", "BT /F1 8 Tf 48 27 Td (IntervAI | Evidence report | Page %d) Tj ET" % page_no])
            pages.append("\n".join(ops).encode("cp1252", errors="replace"))
        page_no += 1
        ops = ["0.05 0.12 0.2 rg", "0 744 612 48 re f", "1 1 1 rg", "BT /F2 15 Tf 48 760 Td (IntervAI | Interview report) Tj ET", "0 0 0 rg"]
        y = 716

    def text(value, *, size=10, indent=0, color="0.12 0.18 0.25"):
        nonlocal y
        value = str(value or "")
        max_chars = max(24, int((516 - indent) / (size * 0.52)))
        words = value.split()
        lines = []
        current = ""
        for word in words:
            if len(current) + len(word) + 1 > max_chars and current:
                lines.append(current)
                current = word
            else:
                current = (current + " " + word).strip()
        if current:
            lines.append(current)
        if not lines:
            lines = [""]
        for line in lines:
            if y < 58:
                new_page()
            ops.extend([f"{color} rg", f"BT /F1 {size} Tf {48+indent} {y} Td ({literal(line)}) Tj ET", "0 0 0 rg"])
            y -= size + 5

    def heading(value):
        nonlocal y
        if y < 84:
            new_page()
        y -= 8
        ops.extend(["0.08 0.35 0.55 rg", f"BT /F2 13 Tf 48 {y} Td ({literal(value)}) Tj ET", "0.75 0.82 0.87 RG", f"48 {y-5} m 564 {y-5} l S", "0 0 0 rg"])
        y -= 20

    def bullets(values, empty="No persisted data recorded."):
        if not values:
            text(empty, size=9, indent=8, color="0.35 0.4 0.46")
        for item in values:
            text("• " + str(item), size=9, indent=8)

    new_page()
    candidate = snapshot["candidate"]
    interview = snapshot["interview"]
    text(candidate["display_name"], size=22, color="0.08 0.2 0.3")
    text(candidate.get("headline") or "Candidate interview evidence", size=11)
    text(f"{interview['type'].title()} interview · {interview['mode']} · completed {interview.get('completed_at') or 'date not recorded'}", size=9)
    text(f"Report version {version} · Generated {datetime.now(timezone.utc).date().isoformat()} · Job: {interview.get('job_title') or 'Not job-specific'}", size=9)
    heading("Performance overview")
    dimensions = snapshot["performance"]["dimension_averages"]
    labels = ["Correctness", "Relevance", "Completeness", "Technical depth", "Reasoning", "Clarity"]
    keys = list(DIMENSIONS)
    for index, (label, key) in enumerate(zip(labels, keys)):
        value = dimensions.get(key)
        text(f"{label}: {f'{value:.2f} / 1.00' if value is not None else 'Insufficient data'}", size=9)
        if value is not None:
            width = int(float(value) * 270)
            ops.extend(["0.9 0.93 0.95 rg", f"160 {y+3} 270 7 re f", "0.1 0.48 0.62 rg", f"160 {y+3} {width} 7 re f", "0 0 0 rg"])
    text(f"Evaluated answers: {snapshot['performance']['evaluated_answers']}. These are descriptive answer-level values, not a hiring score.", size=8)
    heading("Strengths")
    bullets(snapshot["strengths"])
    heading("Development areas")
    bullets(snapshot["development_areas"])
    heading("Interview evidence")
    for item in snapshot["evaluations"]:
        text(f"Question {item['sequence']} · {item.get('topic') or 'Topic not recorded'} · difficulty {item['difficulty']}", size=10)
        text("Question: " + item["question"], size=8, indent=8)
        text("Answer excerpt: " + item["answer_excerpt"] + (" …" if item["answer_truncated"] else ""), size=8, indent=8)
        text("Evidence dimensions: " + ", ".join(f"{k} {v:.2f}" for k, v in item["dimensions"].items()), size=8, indent=8)
        for source in item["sources"]:
            text(f"Source: {source['title']} · {source['relationship']} · reference {source['chunk_id']}", size=7, indent=16)
        if item["adaptive_decision"]:
            text(f"Next action: {item['adaptive_decision']['action']} — {item['adaptive_decision']['reason']}", size=8, indent=8)
    heading("Knowledge gaps and learning")
    bullets([f"{gap['subject']} · {gap['status']} · {gap['independent_evidence_count']} independent checks" for gap in snapshot["knowledge_gaps"]])
    bullets([f"{plan['title']} · {plan['completed_items']}/{plan['total_items']} items complete" for plan in snapshot["learning"]])
    heading("Coding results")
    bullets([f"{row['problem']} · {row['language']} · {row['status']} · {row['tests_passed']}/{row['tests_total']} tests · {row['execution_time_ms']} ms. Complexity is an estimate." for row in snapshot["coding"]])
    heading("Communication measurements")
    bullets([f"Question {row['question_id']}: {row['speech_duration_seconds']} seconds detected speech; {row['silence_duration_seconds']} seconds silence; {row['pause_count']} pauses; {row['word_count']} words; {row['speaking_rate_wpm']} words/min; {row['filler_count']} filler occurrences." for row in snapshot["communication"]])
    text("These are measurements only and do not infer intelligence, personality, honesty, or competence.", size=8)
    heading("Integrity events")
    text(f"Recorded events: {snapshot['integrity']['total_events']} · " + ", ".join(f"{k}: {v}" for k,v in snapshot["integrity"]["event_counts"].items()), size=9)
    text(snapshot["integrity"]["note"], size=8)
    heading("Career context")
    career = snapshot["career"]
    bullets([f"{row['name']}: {row['status_counts']}" for row in career["roles"]] if career else [])
    heading("Limitations")
    bullets(snapshot["limitations"])
    if ops:
        ops.extend(["0.32 0.4 0.5 rg", "BT /F1 8 Tf 48 27 Td (IntervAI | Evidence report | Page %d) Tj ET" % page_no])
        pages.append("\n".join(ops).encode("cp1252", errors="replace"))

    objects = []
    # Use stable object ids: catalog, page tree, two fonts, then page/content pairs.
    next_id = 5
    pairs = []
    for page_data in pages:
        page_id, stream_id = next_id, next_id + 1
        next_id += 2
        pairs.append((page_id, stream_id, page_data))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        ("<< /Type /Pages /Kids [" + " ".join(f"{pid} 0 R" for pid, _, _ in pairs) + f"] /Count {len(pairs)} >>").encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    for page_id, stream_id, page_data in pairs:
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {stream_id} 0 R >>".encode())
        objects.append(b"<< /Length " + str(len(page_data)).encode() + b" >>\nstream\n" + page_data + b"\nendstream")
    output_bytes = BytesIO()
    output_bytes.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, item in enumerate(objects, 1):
        offsets.append(output_bytes.tell())
        output_bytes.write(f"{index} 0 obj\n".encode() + item + b"\nendobj\n")
    xref = output_bytes.tell()
    output_bytes.write(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output_bytes.write(f"{offset:010d} 00000 n \n".encode())
    output_bytes.write(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return output_bytes.getvalue()
