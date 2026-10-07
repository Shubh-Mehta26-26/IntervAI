# Phase 4 handoff — core adaptive interview engine

Phase 4 is implemented on the verified Phase 1–3 foundation. It adds a real, persisted text interview loop and stops before RAG, long-term candidate memory, learning plans, voice, coding, vision, career advice, and recruiter workflows.

## Delivered workflow

An authenticated candidate can configure a technical, project, behavioral, or mixed interview in practice or simulation mode. Configuration supports an optional target job and parsed resume, 1–30 questions, an optional 5–120 minute estimate, selected topics, starting difficulty, candidate focus, and interviewer instructions.

`POST /interviews/{id}/start` atomically moves a draft to `planning` and enqueues a durable job. The worker builds a structured plan from the candidate profile, resume facts and quotations, job analysis, and saved candidate-job match. It persists the plan and rounds, then generates and persists one grounded question. An answer submission stores the immutable answer and queues evaluation in the same transaction. The worker validates a six-dimension evaluation, applies deterministic adaptation rules, persists the decision, and either generates the next question or completes the interview.

The frontend provides `/interviews`, `/interviews/new`, and `/interviews/[id]` with history, configuration, planning/evaluation states, the current question, progress, text answer entry, pause/resume/end controls, network errors, practice feedback, and a completion summary. Simulation mode withholds per-answer evaluation and decisions until completion.

## State machine

The backend owns state and rejects invalid transitions:

```text
created -> planning -> waiting_for_answer -> evaluating
                         ^                    |
                         |------ next --------|

waiting_for_answer <-> paused
waiting_for_answer | paused -> completed
any active state -> cancelled
worker retry exhaustion -> failed
evaluating -> completed when question_limit is reached
```

Every mutating command supplies `expected_revision`. The service locks the interview row, compares the revision, validates the current state and question, writes its domain record and durable job, then increments the revision. External provider calls happen after the transaction releases its locks. A worker commit succeeds only when its claimed job, expected revision, and interview state still match; cancellation or a newer turn makes stale work harmless.

Answer submission also requires a client UUID `idempotency_key`. `(interview_id,idempotency_key)` and `question_id` are unique. Repeating the same key and payload returns the original operation; reusing the key for different content returns `409 idempotency_conflict`; a second key for an answered/currently-processing question fails state validation. Question generation is unique by durable operation ID and interview sequence.

## Database

Migration `1acbf47bc035_phase4_adaptive_interviews.py` adds:

- `interviews`: ownership, selected sources, type/mode, authoritative status/revision, counters, configuration, timestamps, summary, and recoverable error.
- `interview_plans`: one persisted structured plan and compact source snapshot per interview.
- `interview_rounds`: ordered topic, objective, budget, and initial difficulty.
- `interview_questions`: immutable shown text, topic, difficulty, parent link, sequence, state, and generating operation.
- `interview_answers`: one answer per question, candidate ownership, sequence, duration, payload hash, and idempotency key.
- `answer_evaluations`: correctness, relevance, completeness, technical depth, reasoning, clarity, strengths, weaknesses, missing concepts, misconceptions, answer excerpts, feedback, hint, confidence, prompt version, provider, and model.
- `adaptive_decisions`: deterministic action, target topic, next difficulty, reason codes, explanation, and policy version.
- `interview_jobs`: leased plan/answer operations, expected revision, dedupe key, retry metadata, errors, and cached validated provider output.

All ownership reads begin with the authenticated candidate. Job and resume IDs are verified against that candidate before the interview is created. Cascades retain the existing user-owned deletion boundary; job/resume deletion sets the interview source ID to null while the persisted plan snapshot preserves the interview history.

## Evaluation model

The LLM returns six values in `[0,1]`:

- `correctness`: factual and conceptual accuracy supported by the answer.
- `relevance`: how directly the answer addresses the question.
- `completeness`: coverage of the material the question requested.
- `technical_depth`: specificity, trade-offs, and implementation detail appropriate to difficulty.
- `reasoning`: coherence of the explanation and decisions.
- `clarity`: understandable structure and expression.

These are evidence scales for the individual answer. The completion summary reports a simple arithmetic mean for each dimension across evaluated answers and the count of evaluated answers. It does not calculate an overall score, hiring recommendation, probability, or inferred score for missing answers. Evidence entries must be short excerpts from the candidate answer; confidence describes the evaluator's confidence in its own assessment.

## Adaptive policy

`phase4-rules-v1` is application code, independent of the LLM:

1. End when the persisted answer count reaches the configured question limit.
2. If a misconception is present, `test_missing_concept` at one lower difficulty, bounded at 1.
3. If important concepts are missing and correctness is below `0.75`, `test_missing_concept` at the current difficulty.
4. After at least two earlier weak (`correctness < 0.5`) answers in the topic, `revisit_topic` one level lower.
5. If correctness is at least `0.8`, completeness at least `0.75`, and reasoning at least `0.7`, `increase_difficulty`, bounded at 5.
6. If correctness is below `0.4`, `decrease_difficulty`, bounded at 1.
7. If correctness is below `0.75` or completeness below `0.65`, `ask_follow_up` at the same difficulty.
8. When another planned topic still has budget, `change_topic`.
9. Otherwise `maintain_difficulty`.

The generator receives the selected action, topic, and difficulty as constraints. It cannot independently select adaptation policy.

## LLM and prompt boundary

`LLMProvider` exposes one typed `structured` operation. The production adapter uses the OpenAI Responses API and strict JSON Schema generated from the same Pydantic models used for application validation. It sends `store: false`; raw prompts and keys are not stored in logs. `QuestionGenerator` and evaluation orchestration depend on the provider interface, so another production adapter can be added without changing routes or policy code.

Configuration:

```env
LLM_PROVIDER=openai
LLM_MODEL=<a structured-output-capable model>
LLM_API_KEY=<secret>
LLM_BASE_URL=https://api.openai.com/v1
LLM_TIMEOUT_SECONDS=45
```

`GET /api/v1/interviews/provider` returns safe readiness metadata. Starting or answering returns `503 llm_not_configured` when provider, model, or key is absent. There is no production fake or generic-question fallback. Test fakes are passed directly to the worker and the readiness dependency is overridden only inside tests.

Planning, question generation, and evaluation prompts live in `app/services/interview_prompts.py`, outside routes. Each prompt labels profile, resume, job, and answer content as untrusted data; commands inside those fields cannot override the developer instruction. Context is compact: profile summaries, bounded resume/job data, the persisted plan, at most six recent question-answer turns, the current evaluation, and deterministic decision.

Provider calls are retried through leased jobs up to three attempts. A validated plan or evaluation is cached on the job before the next provider call, so a worker crash does not repeat completed expensive work. A terminal failure records a safe error on both the job and interview.

## API

All paths use `/api/v1`, all reads require a candidate session, and all mutations require the session CSRF token.

| Method | Path | Contract |
|---|---|---|
| GET | `/interviews/provider` | Safe readiness status |
| POST | `/interviews` | Validate and persist a draft configuration |
| GET | `/interviews` | Own newest history, optional exact status filter |
| GET | `/interviews/{id}` and `/current` | Authoritative recoverable UI state |
| POST | `/interviews/{id}/start` | Revision-checked durable planning operation |
| GET | `/interviews/{id}/questions` | Visible persisted questions |
| POST | `/interviews/{id}/answers` | Idempotent answer plus durable evaluation operation |
| GET | `/interviews/{id}/answers` | Mode-aware answer/evaluation history |
| POST | `/interviews/{id}/pause` | Waiting to paused |
| POST | `/interviews/{id}/resume` | Paused to waiting |
| POST | `/interviews/{id}/complete` | Complete early and persist summary |
| POST | `/interviews/{id}/cancel` | Cancel active work and queued/running jobs |
| GET | `/interviews/{id}/summary` | Completed structured summary |

## Verification

Verified on PostgreSQL 17/pgvector with the real migration chain:

- 45 backend tests passed. The session-scoped fixture creates a random disposable PostgreSQL database, upgrades to head, downgrades to base, upgrades to head again, and drops the database.
- Phase 4 tests cover configuration validation, creation, ownership, provider absence, grounded planning context, first question, answer persistence, duplicate replay, idempotency conflict, stale revision, invalid transitions, six-dimensional evaluation, deterministic actions, difficulty increase, question progression, automatic completion, summary persistence, practice feedback, and simulation feedback hiding.
- Ruff passed for backend, tests, scripts, and migrations.
- Alembic `check` reported no new upgrade operations.
- Frontend ESLint, TypeScript, and the Next.js production build passed, including all three interview routes.
- Docker Compose rebuilt successfully on the isolated ports 5434/8001/3001. PostgreSQL, backend, worker and frontend reported healthy; migration exited 0. Database inspection confirmed Alembic head `1acbf47bc035` and all eight Phase 4 tables.
- Authenticated browser QA verified the history and configuration screens through the Next.js proxy. Desktop 1440×1000 and mobile 390×844 views render the responsive layout, all four interview types, both modes, source selectors, length/difficulty controls, and the explicit provider setup warning. The start button is disabled while provider configuration is absent.

The real-provider script is `scripts/smoke_interviews.py`. It registers a labelled temporary candidate, uploads and parses a resume, creates/analyzes/matches a job, creates and starts an interview, waits for a real plan and first question, submits an answer, waits for a real evaluation and adaptive decision, verifies the next state and PostgreSQL rows, completes the interview, and deletes the QA account. It exits clearly when provider configuration is absent.

## Current limitation

This workspace had empty `LLM_PROVIDER`, `LLM_MODEL`, and `LLM_API_KEY` values during Phase 4 verification. Deterministic integration tests prove the complete domain and worker workflow with a test-only provider, and the real OpenAI adapter/live smoke path are implemented. A live model call could not be honestly executed without credentials. Configure the three values and run `scripts/smoke_interviews.py` to satisfy the real-provider QA gate.

Phase 5 has not started.
