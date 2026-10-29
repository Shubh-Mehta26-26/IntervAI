# Local verification — 29 October 2026

Current local stack: frontend 3001, API 8001, PostgreSQL/pgvector 5434, sandbox 8081, native durable worker.

## Passed during this run

- Full backend regression suite: 191 passed in 140.45 seconds. Uses a disposable test database.
- Frontend voice/avatar/camera logic: 21 passed.
- Frontend ESLint and TypeScript checks; backend/scripts/tests Ruff lint.
- API and frontend readiness; database and vector extension available.
- Worker heartbeat: running, five seconds old when checked.
- Real Gemini planning, question generation, grounded-evaluation schema and coding-complexity schema checks.
- Real embeddings: three valid 1536-dimensional vectors.
- Real TTS and STT round trip with synthetic speech, normalized to browser-equivalent mono 16 kHz WAV. Transcript matched the supplied sentence.
- Four local vision fixtures: one person, empty view, two people, phone.
- Real sandbox verification: Python/C++/Java, resource limits, isolation probes, cancellation, cleanup and duplicate execution.

The backend suite covers identity, profile, resume and job matching, interviews/adaptation, RAG, memory/gaps, learning and retries, speech, coding, observations, career, reporting, analytics, recruiter consent and administration. These are automated covered scenarios, not a claim that every possible interaction is flawless.

## Limits and findings

Existing interview jobs include three failed speech jobs and one failed LLM job. Another successful job retains an earlier llm_failed code. Current synthetic provider checks passed; historical failures were not erased or retried against the user's interviews.

Physical microphone quality, accent/noise handling, camera permissions and real-room phone/person detection need a human session. Production build, public deployment, load/endurance, and a complete new browser walkthrough of every page were not repeated in this run. Previous audit details remain in PROJECT_AUDIT_2026-10-28.md. The latest UI/orb changes passed current lint and TypeScript checks.

No existing candidate data was deliberately modified by these verification probes. Synthetic provider checks consume a small amount of API quota.
