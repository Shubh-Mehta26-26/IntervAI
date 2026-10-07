# Phase 11 Handoff — AI Career Advisor and Career Readiness

## Status

Phase 11 implementation is complete in the working tree. The career workspace is an evidence-informed exploration tool; candidates control their goals and choices. It does not rank roles, issue a hiring decision, certify a skill, or promise an employment outcome. Phase 12 has not started.

## Delivered

- Persistent candidate career preferences with revision-checked edits; target roles reuse existing `candidate_goals` and the existing candidate profile stores interests/experience.
- A bounded, seeded, versioned, extensible role taxonomy with structured required/preferred requirements, responsibilities, and project-authored illustrative provenance. Candidate-owned job requirements remain separate.
- Candidate-owned analysis versions with immutable result/evidence snapshots, fingerprint deduplication, request idempotency, and stale detection when evidence/preferences/role versions or the seven-day review period change. Reads never invoke an LLM.
- Multi-role readiness and skill-gap detail with evidence ids, claims, counts, recency, conservative status labels, and a trend only with sufficient checks/history. Resume and experience claims remain visibly self-reported; absent resume evidence is not treated as proof of inability.
- A responsive career dashboard, editable profile/preferences page, role detail route, comparison cards, evidence details, historical analyses, progress, roadmap, and optional advisor reflection.
- Roadmap choices are persisted. Real confirmed knowledge-gap ids are passed to the existing Phase 7 learning planner, retaining its deduplication and existing plan behavior. A missing gap suggests evidence collection and cannot fabricate a gap.
- Optional AI explanations use the existing provider abstraction and validated structured output. Optional career RAG uses the existing PostgreSQL/pgvector retrieval and records source metadata. Provider/RAG failures leave deterministic readiness intact.

## Readiness and evidence policy

Policy version `career-readiness-v1` uses canonical skill/alias matching and the existing independent-memory filter. Proficiency checks must be independent, grounded, unassisted, recent (180 days), and confidence-qualified. `DEMONSTRATED` requires at least three recent strong checks, across two or more interviews and two distinct questions, with no active related confirmed gap. Other valid checks indicate `DEVELOPING`; claims or stale/assisted/uncertain observations remain `LIMITED_EVIDENCE`; no matching evidence yields `NOT_DEMONSTRATED` with an explicit statement that this is not proof of absent knowledge. A trend requires at least four checks over at least two interviews. Only stored completed coding measurements are included in the separate coding evidence summary; source code and hidden-case data are excluded.

Snapshots explicitly exclude Phase 10 CV/integrity events, Phase 8 voice acoustic metrics, personal contact data, candidate source code, and raw transcripts. LLM content can explain and ask reflective questions but cannot change computed readiness, invent preferences/gaps, or claim unsupported RAG grounding.

## API and data

All career routes are under `/api/v1/career`. Candidate authentication is required; mutations require CSRF and allowed Origin; records are owner-scoped. Routes include profile GET/PATCH, roles GET/detail, analyze POST, analyses/history/detail, readiness, skill-gaps, choices, roadmap, and optional analysis advice. See [API reference](API.md).

Migration `6180c9689cfe` follows Phase 10 and does not edit earlier migrations. It adds `career_roles`, `career_profiles`, `career_analyses`, `career_requests`, `career_choices`, and `career_advice`. Candidate deletion cascades private records; composite owner foreign keys and immutable-history triggers preserve ownership and snapshots. See [database schema notes](DATABASE.md).

## LLM, RAG, and credentials

OpenAI remains the primary configured provider (`LLM_PROVIDER=openai`, `LLM_MODEL=gpt-6-luna`); Gemini remains the existing alternative. Career uses the same server-side `LLMProvider`; it does not hard-code either vendor. AI advice is optional and request-triggered. RAG is optional per advice request and reuses the technical pgvector corpus; if retrieval is unavailable/empty, advice must report insufficient grounding. No new secret or dependency is required for deterministic role comparison/readiness. Real provider credentials remain a local final-integration task; do not paste them into chat or commit them.

## Verification

- Career suite: **21 passed** (including policy boundaries, insufficient/conflicting/uncertain evidence, role/profile edits, ownership/CSRF/deletion, idempotency/concurrency, immutable history, roadmap/learning reuse and pursue-choice enforcement, AI malformed/provider/timeout paths, RAG provenance/injection, resume/job separation, coding-data privacy, retry improvement, and weekly staleness).
- Full backend regression: **156 passed, 1 transient database 503** in the full run; the exact failing learning ownership test passed on isolated rerun (1 passed). The failure did not reproduce. The separate final Phase 11 career suite passed again after the explicit-pursue guard was added.
- Ruff: passed.
- Frontend ESLint and TypeScript: passed.
- Voice UI tests: 8 passed; vision UI tests: 5 passed.
- Production Next.js build: passed and includes `/career`, `/career/profile`, and `/career/roles/[id]`.
- Alembic metadata check: no new upgrade operations detected.
- Browser navigation to `/career` redirected to `/login` as expected because no candidate session was active; the authenticated end-to-end data flow is exercised by the automated integration suite. No login or account creation was performed through the browser.

## Limits and final checks

Role requirements are illustrative project-authored examples, not a current labor-market dataset. Only existing recorded evidence can influence deterministic readiness; communication style/personality and camera integrity are out of scope. Live OpenAI/Gemini response quality and RAG against production-curated role content require configured real credentials/data. Physical webcam verification from Phase 10 remains a separate final-integration item.

Run locally from the repository root:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8001
cd frontend
npm run dev -- --port 3001
```

Use the root Compose setup for the full stack when PostgreSQL, pgvector, worker, and coding sandbox are needed. Candidate app routes are `/career`, `/career/profile`, and `/career/roles/{id}`. For regression checks run backend pytest with a fresh writable `--basetemp=.local/phase11-<run>` and frontend lint/typecheck/build. Continue only after the user explicitly requests Phase 12.
