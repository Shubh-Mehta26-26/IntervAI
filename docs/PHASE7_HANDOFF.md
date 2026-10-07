# Phase 7 — personalized learning and retry interviews

Phase 7 adds the persisted loop: confirmed gap → ordered learning plan → lesson → practice feedback → focused retry through the existing interview worker → source-linked evaluation → immutable before/after comparison → Phase 6 memory and gap update. Phase 8 has not started.

## Architecture and data

The new `app/services/learning.py` owns learning policy and persistence. It reuses candidate memory, knowledge gaps, candidate goals/interests, job descriptions, the existing technical corpus, `LLMProvider`, `EmbeddingProvider`, and the Phase 4/5 interview worker. No second skill taxonomy, knowledge base, interview system or evaluator was added.

Migration `66789d3f612f` follows `aa3d013c3e44` and adds six tables:

| Table | Purpose |
| --- | --- |
| learning_plans | Candidate-owned roadmap, job, objective, status, revision, deterministic priority and context |
| learning_targets | Existing gap/memory IDs and immutable baseline evidence IDs/dimension means |
| learning_items | Ordered concept activities, objective, ordering reason, effort, difficulty, typed content and progress |
| learning_actions | Append-only explicit learning starts and item completion, with explanations |
| learning_attempts | Practice/retry links to existing interviews, parent interview, target snapshots and completed comparison |
| learning_requests | Replay keys including clicks which reuse an existing plan or unfinished attempt |

Candidate row locks serialize mutations. Unique keys/fingerprints prevent duplicate plans and attempts. Request payload conflicts return 409. Unfinished practice is reused per item; unfinished retries are reused for the same candidate/plan/target set. Completed attempts remain historical, and a fresh request can start another. Item completion uses plan revision checks and is idempotent. Database triggers reject edits to baseline targets, learning actions, request mappings, attempt target snapshots and completed comparisons. Account deletion cascades through the learning records; shared technical documents remain.

## Plans, priority and regeneration

Only confirmed/learning/improving gaps are eligible; observed or resolved gaps cannot manufacture a learning need. Plans snapshot up to six latest supported independent observations per target, with original evaluation/interview IDs. They reuse the existing memory subject/topic and current self-reported roles/interests. An optional owned job informs priority.

`learning-v1` priority is a deterministic index, not a probability:

`100 × (0.35 × weakness_index + 0.20 × evidence_confidence + 0.15 × min(weak_interviews/3,1) + 0.15 × explicit_job_relevance + 0.05 × explicit_role_or_interest_relevance + 0.10 × (1 − stored_mean_correctness))`

Relevance is conservative normalized text matching of a known concept/topic. Reasons expose the actual contributing values. No LLM chooses priority. Ties use gap UUID. Recommendations prefer one concept per topic for a recommended retry, avoiding redundant topic/misconception targets.

Authored curriculum ordering places prerequisites before mechanisms, then applications/trade-offs. Normalization starts with functional dependencies and candidate keys, then normal forms; deadlock starts with conditions/graphs before prevention/avoidance. Unknown subjects receive an explicit foundations/mechanism/application outline. Effort and difficulty are authored estimates, never measured performance. Plan targets retain their gap IDs and baseline evidence throughout.

Dashboard reads do not regenerate. Default creation deduplicates the candidate/gap set/job/policy. A plan is labelled stale when new evidence changes its target's last-seen timestamp after creation. Explicit `regenerate=true` creates a new persisted snapshot; the previous plan is retained. No background LLM calls occur on reads.

## Learning content and sources

Initial lessons retrieve exact lexical matches from the same ready knowledge documents/chunks. Their explanations are verbatim source extracts, with chunk IDs, titles, provenance and retrieval method. If retrieval finds no source, the item is an explicitly insufficient learning outline; it does not pretend to teach source-grounded technical facts.

The explicit item generation endpoint reuses the production LLM/embedding interfaces and Phase 5 vector retrieval. `LearningContent` bounds and validates explanation, examples, hints, practice question and citation UUIDs. Unknown or duplicate cited chunks are rejected. Source knowledge is kept separate from generated explanations. Generated content without citations is labelled insufficient; cited generated explanations are clearly distinguished from source extracts. Untrusted content remains inside the existing DATA boundary. Provider work occurs outside locks; content revisions prevent stale writes. Provider failure preserves saved content and returns a safe error. This optional generation is synchronous, with bounded provider timeouts; it is not a new durable job queue.

## Practice and retry

Practice creates a one-question existing interview directly from the learning item's saved question. It links the item, gap and target concept. Submission delegates to the existing answer endpoint and durable evaluation worker; feedback and technical sources use the existing output contract. Candidates can repeat practice after feedback. Practice follows explanations/hints, so `learning_practice` is excluded from persistent mastery evidence. Practice counts/results remain visible as activity.

Retry supports single gap, selected multiple gaps, topic, skill, and deterministic recommended sets. It creates a clearly marked ordinary technical interview draft with `retry_targets` in configuration and a `learning_attempts` relationship. Starting uses the existing revision-checked planning job. Application code enforces selected topics/budgets; prompts receive the target subjects and prior question text. Exact normalized repetitions of supplied baseline/recent questions are rejected. Hints are disabled. Normal adaptive decisions and RAG evaluation still govern each turn.

Plan-linked retries retain the plan's pre-learning baseline. Standalone retries snapshot eligible evidence at creation. Parent interview and original evidence locators remain saved; no original questions, answers, evaluations or interviews are overwritten.

## Comparison and gap status

On automatic or manual completion, the existing interview transaction publishes eligible memory evidence and stores the comparison once. For each target, independent supported retry observations supply actual correctness, completeness, reasoning, technical depth and clarity means. Difference = retry mean − baseline mean, rounded to four decimals; absent evidence produces null, never zero. The snapshot contains baseline/retry evaluation and memory evidence IDs, sample counts and completion-time gap status. Later reopening does not rewrite an old comparison.

These descriptive answer-level differences are not a causal learning effect, hiring score or calibrated concept mastery. Difficulty and evaluation prompt versions can differ; they are not a statistically matched experiment. Baselines retain difficulty/prompt metadata for inspection. Concept coverage is represented through targeted subject evidence/counts, without an invented coverage percentage.

An explicit `Start learning` records a separate learning action and moves a confirmed gap to learning. It creates no artificial evaluation or mastery improvement. Phase 6's deterministic `memory-gap-v1` remains authoritative: two strong independent observations exceeding the confirmation baseline by 0.15 can indicate improving; three strong checks across two interviews with two distinct question signatures can resolve. Follow-up chains stay correlated; confidence/grounding/hint exclusions remain. Three later weak roots across two interviews can reopen. Lesson completion alone never resolves a gap.

## API

All paths use `/api/v1`. All reads require candidate authentication; mutations require origin/CSRF checks. Foreign IDs return 404. The fixed-origin Next.js proxy explicitly allowlists these paths; responses are no-store.

| Method | Path | Input/behavior |
| --- | --- | --- |
| GET/POST | /learning/plans | Own saved plans; POST gap_ids, optional job_id, idempotency_key, regenerate |
| GET | /learning/plans/{id} | Items, targets, priority reasons, progress, actions and attempt history |
| POST | /learning/plans/{id}/start | expected_revision; explicit learning action |
| GET | /learning/items/{id} | Saved lesson and sources |
| POST | /learning/items/{id}/complete | expected_revision of the parent plan |
| POST | /learning/items/{id}/generate | expected_revision of content; configured providers required |
| POST | /learning/items/{id}/practice | idempotency_key; saved practice attempt/interview |
| POST | /learning/items/{id}/practice/{attempt_id}/submit | Existing AnswerInput; durable evaluation operation |
| GET | /learning/attempts/{id} | Interview link/state and completed comparison |
| POST | /learning/retries | idempotency_key, mode, gap_ids/subject, optional plan_id/job_id, question_limit |
| POST | /knowledge-gaps/{id}/learning-plan | Single-gap shortcut with idempotency_key |
| POST | /knowledge-gaps/{id}/retry | Single-gap shortcut with idempotency_key |
| GET | /candidates/me/progress | Saved learning/retry activity and recommendations; optional job_id |

## UI

`/learning` shows real saved progress, priority explanations, job selection, gap selection and retry modes. `/learning/[id]` provides an interactive ordered roadmap, source/explanation disclosure, AI generation, completion controls, targeted practice and retry actions. `/learning/practice/[id]` supports answer submission, feedback, sources and repeated attempts. `/learning/retry/[id]` starts/opens the existing interview room and shows stored comparisons. Dashboard/progress include learning and retry history; confirmed gap detail links to learning. No fabricated analytics are displayed.

## Verification

Deterministic PostgreSQL tests exercise the complete persisted learning/practice/retry/RAG/memory loop, known improvement (+0.65 from stored 0.25 to 0.90), recovery, reopening, retained original evaluations, priority, ordering, progress/revisions, duplicate/replayed operations, concurrent plan/retry creation, ownership/CSRF, immutable history, deletion, lexical/vector sources, rejected citations, stale generated content and repeated-question rejection. Test providers are injected only in tests; no production mock registry was added.

Final verification: **72 backend tests passed in 116.63 seconds**, including 11 Phase 7 tests, against real PostgreSQL/pgvector with injected deterministic test providers. The migration suite upgraded to head, downgraded to base and re-upgraded a disposable database; model/metadata comparison passed. Native Alembic check reported no new upgrade operations. Ruff and dependency checks passed. Frontend ESLint, TypeScript and the production build passed, including all four new learning routes. Docker rebuilt successfully; database, API, worker and frontend are healthy, and migration head is `66789d3f612f`.

Browser QA verified the real dashboard learning summary and learning empty states on desktop (1440×1000) and mobile (390×844). Screenshots are saved as `docs/screenshots/phase7-learning-desktop.jpg` and `phase7-learning-mobile.jpg`. A labelled temporary UI account was used and removed after verification; the user's existing account was unchanged. Populated lifecycle and comparison behavior were tested in disposable databases, without adding fabricated performance to the application database. No live-provider call was claimed.

## Startup and final provider configuration

```powershell
docker compose up -d --build
docker compose ps
```

This workspace uses frontend `http://localhost:3001`, API `http://localhost:8001`, and PostgreSQL port 5434. Native startup remains the README workflow. For backend verification, create `.local` first and use a fresh temporary folder:

```powershell
New-Item -ItemType Directory -Path .local -Force | Out-Null
.\.venv\Scripts\python.exe -m pytest tests/backend -q --basetemp=.local/phase7-check
cd frontend
npm run lint
npm run typecheck
npm run build
```

Configure real LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY, EMBEDDING_PROVIDER and EMBEDDING_MODEL locally at final integration. `.env.example` documents placeholders and existing timeout/retrieval settings. No secrets need to be pasted into chat. Then ingest the existing corpus and run the existing live interview smoke, followed by the learning/retry UI journey. No live-provider success is claimed during Phase 7.

## Limits and stop boundary

- Curriculum/alias coverage is authored and finite. Unknown subjects get a conservative outline. Lexical matches can be broad; optional vector retrieval and generated lessons require configured providers.
- Phase 6 attributes answer-level scores to concepts; these are not separately calibrated per-concept assessments. Paraphrase matching/transfer-question quality needs live review; the retry guard rejects exact normalized repeats, not all semantic paraphrases.
- Responses are bounded: 50 plans, 30 recommendations, 100 candidate attempts, 50 attempts and 100 learning actions per plan. This is suitable for the current local workload; larger histories need paginated/aggregated views.
- Arbitrary administrative removal of an individual historical evaluation/interview requires controlled recomputation, as in Phase 6. Account erasure cascades are tested.
- No speech, vision, code execution, career advising, recruiter dashboard or Phase 8 features were implemented.
