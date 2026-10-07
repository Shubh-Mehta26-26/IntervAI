# Phase 6: persistent candidate memory and knowledge gaps

Phase 6 extends the existing interview/evaluation transaction. It does not implement learning plans, retry learning, speech, vision, code execution, or career advising.

## Implemented workflow

Interview answer → Phase 5 RAG evaluation and sources → immutable memory evidence → skill/topic/concept aggregates → deterministic gap state → relevant history in future planning.

`CandidateMemoryService` is independent of the HTTP routes and providers. Practice evaluations update memory inside the worker's existing commit. Simulation evaluations update only on automatic or manual completion, preventing feedback disclosure through memory endpoints during an active simulation. A failed or cancelled worker commit creates no partial memory.

The service locks the candidate row before updating. Uniqueness on candidate/kind/normalized subject and memory/evaluation prevents duplicate subjects and replayed evidence. Concurrent evaluations serialize per candidate. Evidence retains links to the evaluation, interview, root question, and candidate; answer/question/source locators are reconstructed through their existing relationships.

## Database and history

Migration `aa3d013c3e44` adds:

- `candidate_memory`: structured kind, normalized subject, topic, first/latest observation, evidence/interview counts, supported mean correctness, evidence strength, trend.
- `memory_evidence`: append-only per-evaluation observations, confidence, grounding, assistance, question signature, deterministic signals and source evaluation.
- `knowledge_gaps`: derived lifecycle and evidence index, independent-check count, weak-interview count, confirmation baseline, timestamps and policy version.
- `gap_transitions`: append-only old/new status, reason, evidence IDs and triggering evaluation.

Topics and concepts have separate aggregates; skill history reuses memory evidence rather than duplicating scores. Strengths, weaknesses and misconceptions have structured categories plus evidence links. Candidate goals/target roles are read from the existing profile table as self-reported goals, never inferred assessed facts.

PostgreSQL triggers reject updates to evidence and transition history. Derived memory and gaps are mutable. Account deletion cascades through all private records, while shared technical sources remain. The migration also aligns the Phase 5 timestamp nullability with existing model metadata without editing previous migrations.

## Policy: memory-gap-v1

Scores shown are stored answer correctness (0–1), not an invented overall skill or hiring score.

1. A grounded observation requires `grounding_status=grounded` and a persisted supporting/contradicting Phase 5 citation. Confidence must be ≥0.70 to influence persistent conclusions.
2. Low correctness (<0.60), incompleteness (<0.65), failed follow-up, reported weakness or misconception can create an **observed** record. Ungrounded/low-confidence evidence remains provisional.
3. Follow-up chains count as one root question. A later unassisted, supported correction replaces an earlier failure only in derived calculation. The original evidence stays immutable. Hinted follow-ups are excluded from confirmation/recovery.
4. Keep at most two independent root observations per interview and subject. Weight `w=confidence × exp(-age_days/90)`; weakness index is `Σw(1-correctness)/Σw`. Age is measured against the latest recorded observation for deterministic replay.
5. **Confirmed** requires three independent weak roots across at least two interviews and weakness index ≥0.40.
6. Strong evidence requires correctness ≥0.80, completeness ≥0.75, no reported misconception, eligible grounding/confidence, and no known hint assistance.
7. **Improving** requires two consecutive new strong checks and mean correctness ≥ confirmation baseline +0.15. A later eligible weak check returns improving to confirmed.
8. **Resolved** requires three consecutive independent strong checks across at least two interviews, including two distinct question signatures. All prior history is retained.
9. Reopening requires three new weak roots across two interviews after resolution. A single later failure does not reopen a gap.
10. **Learning** is reserved for a future explicit learning action. No Phase 6 endpoint manufactures a learning state.

Gap transitions are decided in Python, never hidden LLM reasoning. Known concept aliases cover the curated corpus. Additional missing-concept labels are normalized conservatively. Repeated prose misconceptions/weaknesses use exact normalized keys; arbitrary paraphrases are not silently merged. Strong grounded checks of an explicit known concept can contribute recovery evidence to related prior misconception/weakness items.

## Future planning

`use_memory` defaults to true and is selectable in interview setup. The planner receives at most six confirmed/improving topic/concept records and two supporting observation locators per item. Explicit selected topics and current job analysis constrain relevance. Behavioral interviews do not receive technical gap memory. The prompt requires current job/type/topic scope to take priority and asks fair concept checks rather than assuming a past weakness persists. Current adaptive rules continue to own next-question difficulty/actions.

## Candidate API

All routes require a candidate session; actor ownership is resolved before querying.

| GET path under /api/v1 | Output |
| --- | --- |
| /candidates/me/memory | Structured items, current self-reported target roles |
| /candidates/me/memory/{id}/evidence | Own question/answer excerpt, evaluation and technical source locators; optional before timestamp |
| /candidates/me/skills/history | Stored append-only skill observations |
| /candidates/me/concepts/history | Stored concept observations and aggregates |
| /candidates/me/knowledge-gaps | Gaps with optional exact status filter |
| /candidates/me/knowledge-gaps/{id} | Evidence and explained transition history |
| /candidates/me/misconceptions | Evidence-backed misconception items and lifecycle |

Foreign identifiers return 404. Anonymous reads return 401. Responses are private/no-store through the existing fixed-origin Next.js allowlist proxy. No keys or sensitive evidence are logged.

## Frontend

`/knowledge-gaps` shows status, provisional designation, topic, counts, dates and trend. Detail views explain why the gap appears through stored questions, answer excerpts, citation titles and state changes. `/progress` plots individual stored correctness values for skills and concepts. Limited-source results are distinguished; no data yields an honest empty state. Charts link to the original interview.

## Maintenance

For already stored Phase 4/5 evaluations, run the idempotent backfill:

```powershell
.\.venv\Scripts\python.exe scripts\backfill_memory.py
```

The script runs chronological eligible evaluations and skips duplicate evidence. New evaluations update automatically; memory reads query indexed derived records, not entire interview transcripts.

## Verification and limits

Final verification: **61 backend tests passed** against PostgreSQL; Ruff and dependency checks passed. Alembic reported no new upgrade operations, and migration/model metadata matched. ESLint, TypeScript and the Next.js production build passed. The rebuilt database, API, worker and frontend containers are healthy, with the app at `http://localhost:3001` and API at `http://localhost:8001`.

Browser checks verified the knowledge-gap and progress empty states, mobile layout and the enabled memory option in interview setup. Screenshots are saved in `docs/screenshots/phase6-gaps-desktop.jpg` and `docs/screenshots/phase6-progress-mobile.jpg`. The existing application database had no evaluations to backfill; the backfill completed with zero records. Populated lifecycle behavior was verified with test fixtures, without adding fabricated performance to the user's account.

Verification includes real PostgreSQL migrations upgrade → base downgrade → re-upgrade, metadata comparison, deterministic lifecycle rules, complete RAG-to-memory worker integration, repeated misconceptions, recovery, non-identical checks, hint exclusion, immutable history, ownership, deletion cascades, duplicate replay and concurrent updates.

The full real-provider gate remains unavailable until local LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY, EMBEDDING_PROVIDER and EMBEDDING_MODEL are populated. Test providers are injected only in tests; no production fake is used.

Concept attribution uses question/topic text and missing-concept labels. Answer-level correctness is reused as evidence for those concepts; it is not a separately calibrated per-concept assessment. Paraphrase merging/review and a richer concept taxonomy are future improvements. Known displayed hints on follow-ups are excluded; assistance outside the application cannot be detected. History responses are bounded (100 evidence items, 500 history observations across up to 50 subjects). Derived values refresh on accepted evidence; arbitrary administrative deletion of an individual historical interview requires a controlled recomputation rather than direct SQL.

Phase 7 is outside this handoff.

