# IntervAI

Adaptive interview and learning platform. **Current implementation: Phase 12 evidence reports, analytics, consent-based recruiter review, and role-scoped administration, building on Phases 1–11.**

## Blueprint

- [Architecture, workflows, policies, roadmap and testing](docs/ARCHITECTURE.md)
- [Complete database design](docs/DATABASE.md)
- [REST API contracts](docs/API.md)
- [Phase 1 verification record](docs/PHASE1_VERIFICATION.md)
- [Phase 2 handoff, API contracts and verification](docs/PHASE2_HANDOFF.md)
- [Phase 3 handoff, parsing, matching and verification](docs/PHASE3_HANDOFF.md)
- [Phase 4 handoff, adaptive engine and verification](docs/PHASE4_HANDOFF.md)
- [Phase 5 handoff, RAG evaluation and verification](docs/PHASE5_HANDOFF.md)
- [Phase 6 handoff, candidate memory and knowledge gaps](docs/PHASE6_HANDOFF.md)
- [Phase 7 handoff, learning/practice/retry and verification](docs/PHASE7_HANDOFF.md)
- [Phase 8 handoff, speech/providers/privacy and verification](docs/PHASE8_HANDOFF.md)
- [Phase 9 handoff, isolated coding interviews](docs/PHASE9_HANDOFF.md)
- [Phase 10 handoff, optional visual integrity signals](docs/PHASE10_HANDOFF.md)
- [Phase 11 handoff, evidence-based career guidance](docs/PHASE11_HANDOFF.md)
- [Phase 12 handoff, reports, analytics, recruiter/admin workspaces](docs/PHASE12_HANDOFF.md)
- [Final integration and verification checklist](docs/FINAL_INTEGRATION.md)

## Prerequisites

- Docker Desktop with Linux containers and Compose v2 for the full stack.
- For native development: Node.js 22, Python 3.12+, and PostgreSQL 17 with pgvector.
- Configure OpenAI or Gemini for generation and, independently, for 1,536-dimensional embeddings used in grounded evaluation. Gemini can use one `GEMINI_API_KEY` for both. Local Vosk/eSpeak or explicit cloud speech providers enable voice. Real credentials belong only in ignored `.env`. Profile, resume, job analysis, and matching require no AI credentials.

For Gemini-backed interviews, set `LLM_PROVIDER=gemini`, `GEMINI_MODEL=gemini-3.5-flash-lite`, `EMBEDDING_PROVIDER=gemini`, `EMBEDDING_MODEL=gemini-embedding-2`, and `EMBEDDING_DIMENSIONS=1536` in `.env`, along with your private `GEMINI_API_KEY`. The Gemini embedding adapter uses `RETRIEVAL_DOCUMENT` for knowledge ingestion and `RETRIEVAL_QUERY` for candidate-answer retrieval. Run `scripts/smoke_llm.py` and `scripts/smoke_embeddings.py` before ingesting `knowledge_base/sources` with `scripts/ingest_knowledge.py`. Re-ingestion rebuilds existing sources when the embedding provider or model changes. Gemini free-tier quotas and data-use terms should be checked before sending real candidate data.

## Full stack with Docker

From the repository root in PowerShell:

```powershell
python scripts/init_environment.py
docker compose config --quiet
docker compose up --build -d
docker compose ps
./scripts/check.ps1
```

Open [frontend](http://localhost:3000), [API docs](http://localhost:8000/docs), and [readiness](http://localhost:8000/api/v1/health/ready).

The initializer preserves existing configuration and generates a random `AUTH_SECRET` when missing. If Python is not on PATH on this workstation, use `./.venv/Scripts/python.exe scripts/init_environment.py`. Register your own account in the UI; no demo account is seeded. Registration creates an empty candidate profile and default preferences, then the UI signs you in and opens profile onboarding.

If Docker is installed per-user but not on PATH (as on this workstation), add it for the current terminal before running Docker commands:

```powershell
$env:PATH = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;" + $env:PATH
```

The database and private resume storage use named volumes. Bootstrap enables pgvector on first creation. Migrations run once before the backend and worker; the frontend waits for backend readiness. `docker compose down` stops containers while retaining both volumes. Do not add `-v` unless intentionally deleting local database and resume data.

Recruiter and administrator accounts are provisioned from a trusted local operator shell only after an account exists: `./.venv/Scripts/python.exe scripts/set_user_role.py user@example.com recruiter` (or `admin`). Registration always creates a candidate account. Protect the operator shell and never put this role assignment into a public registration flow.

Published ports can be changed with `POSTGRES_PORT`, `API_PORT`, and `FRONTEND_PORT`. Keep matching browser origins in `CORS_ORIGINS`. This workspace was verified on 5434/8001/3001 because another local project already owned the defaults.

Default credentials and localhost-bound ports are for local development only. Use a URL-safe development password because Compose builds a database URL from its parts. For production, supply an encoded secret-managed DSN, separate migration/runtime database users, TLS ingress, private networking and pinned image digests.

## Native development

Create `.env` once (do not overwrite an existing configured file). Python must be installed or supplied with an absolute path.

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.lock
./.venv/Scripts/python.exe -m pip install --no-deps -e backend
./.venv/Scripts/python.exe scripts/init_environment.py
docker compose up -d db
./.venv/Scripts/alembic.exe -c backend/alembic.ini upgrade head
./.venv/Scripts/python.exe scripts/run_backend.py
```

In another backend terminal, start the durable resume and interview worker:

```powershell
./.venv/Scripts/python.exe -m app.worker
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

The frontend defaults to API `http://127.0.0.1:8000`. To override, set `$env:API_INTERNAL_URL` in its terminal or use `frontend/.env.local`; Next.js does not load the repository root `.env`. Docker sets this automatically. Backend settings load root `.env`. If using an existing database, change `DATABASE_URL` and ask its administrator to install `vector`; do not point tests at a production database.

The native launcher selects the Windows event loop required by psycopg. Stop Docker frontend/backend services before native startup to free ports 3000/8000. Authentication and profiles require PostgreSQL; health liveness remains available during database outages, while readiness returns 503.

Upgrade an existing local database with `./.venv/Scripts/alembic.exe -c backend/alembic.ini upgrade head`. The admin readiness page reports provider names/status and worker/job health; it never returns API keys. Recruiters see candidate information only after explicit application consent, and report access is limited to completed interviews for the applied job.

## Checks

```powershell
./.venv/Scripts/python.exe -m pytest tests/backend -q
./.venv/Scripts/python.exe -m ruff check --config backend/pyproject.toml backend tests/backend scripts
./.venv/Scripts/python.exe scripts/smoke_identity.py
./.venv/Scripts/python.exe scripts/smoke_intelligence.py
./.venv/Scripts/python.exe scripts/smoke_interviews.py
cd frontend
npm run lint
npm run typecheck
npm run build
```

Tests use real PostgreSQL in a uniquely named disposable database. The configured development database user needs permission to create/drop databases and install pgvector. Fixtures verify migration upgrade, downgrade and re-upgrade, then remove that test database. Never configure tests against production. Live smoke scripts require the full stack, verify labelled temporary records directly in PostgreSQL, and remove those records afterward. Readiness unit tests inject database outcomes only in tests.

## Implemented scope

Implemented: Next.js responsive foundation screen, actual readiness display via a fixed backend proxy, Tailwind setup, FastAPI, validated environment loading, async SQLAlchemy/psycopg connection, liveness/readiness routes, Alembic baseline, Dockerfiles/Compose, environment template, and health tests.

Phase 2 adds registration, login, logout, persisted opaque cookie sessions, backend authorization, protected dashboard/profile pages, and editable candidate details, education, work experience, target roles and interview preferences. See the handoff for security controls and validation results.

Phase 3 adds private PDF/DOCX resume versions, durable extraction status, typed evidence parsing, canonical skills, job targets, requirement analysis and persisted candidate–job matches with exact source quotations. Profile facts remain separate and are never overwritten by an upload.

Phase 4 adds technical, project, behavioral and mixed text interviews in practice and simulation modes. Plans, questions, answers, six-dimensional evaluations, deterministic adaptive decisions and completion summaries are persisted. LLM work runs in the durable PostgreSQL worker; revision checks, row locks, idempotency keys and operation deduplication protect against refreshes and double submissions. Configure `LLM_PROVIDER=openai`, `LLM_MODEL`, and `LLM_API_KEY`. Missing credentials produce an explicit configuration error; production never falls back to fake interview content.

Phases 4–9 are documented in their local verification handoffs. Phase 10 adds opt-in local vision observations, and Phase 11 adds evidence-based career guidance; recruiter/admin workflows and final PDF reporting remain future work. Email verification, password reset and MFA are also deferred. No fake candidate scores or simulated interview results are seeded.

## Personalized learning and retry

Open `/learning` to build a saved roadmap from confirmed gaps, inspect priority reasons, practice an item and create a focused retry through the existing interview engine. Dashboard and `/progress` show real persisted learning activity and before/after evidence. Completion records activity; independent repeated evaluations determine gap recovery. Real credentials are configured locally at final integration. No live-provider success is claimed yet. See [Phase 7 handoff](docs/PHASE7_HANDOFF.md) for exact contracts, policy, startup and limits.

## Phase 8: turn-based voice

The interview room now supports temporary WAV recording, signal VAD, provider-independent STT/TTS, original transcript review, question replay and text fallback. Voice answers use the same RAG/evaluation/adaptive/memory/learning pipeline as typed answers. OpenAI is the primary configurable LLM with GPT-6 Luna; Gemini remains an explicit alternative, and embeddings stay independently configured. Docker includes Vosk and eSpeak NG; install a Vosk model separately and configure provider secrets only in ignored `.env` at final integration. No cloud speech request or physical microphone verification is claimed; the separate Gemini LLM adapter smoke is recorded in docs/GEMINI_SMOKE.md. See [Phase 8 handoff](docs/PHASE8_HANDOFF.md) for contracts, retention, setup, tests and limitations. Run `npm run test:voice` in frontend for capture/VAD/WAV checks. Coding is documented in the Phase 9 section below.


## Phase 9: coding interviews

The interview room now includes CodeMirror, original validated DSA problems, Python/C++/Java, public Run, final hidden Submit, Stop, measured execution results, and saved submission/estimated-analysis history. Coding reuses the existing RAG/adaptive/memory/gap/learning pipeline. Actual test outcomes determine correctness; AI estimates cannot replace execution.

Start the verified Docker deployment with `docker compose up -d --build`. The dedicated non-root sandbox has a private network, read-only image, tmpfs, resource bounds, and fresh rootless user/PID/network/mount namespaces plus Landlock/seccomp for each compiler/runtime. Candidate code never runs in the API/worker/host and no Docker socket or host directory is mounted. The worker waits for sandbox security readiness. A Linux kernel with rootless namespace support and Landlock ABI >=3 is required; incompatible hosts fail closed.

Local verification: 116 backend tests, 8 frontend voice tests, 29 real sandbox checks, lint/TypeScript/build/migrations, and deployed desktop/mobile coding flows. Real AI/embedding/speech credentials remain for final integration in ignored `.env`; the separate Gemini adapter smoke passed, while live OpenAI/embedding/speech verification remains pending. Production also requires a configured shared runner key. See [Phase 9 handoff](docs/PHASE9_HANDOFF.md) for exact security assumptions, startup commands, API/schema, test evidence, and limitations. Phase 10 is described below.


## Phase 10 — optional camera observations

The interview room now supports optional video-only preview and bounded sampling, actual local person/phone detection, temporal confirmation, durable observation events, and a chronological timeline. Raw candidate frames/video are discarded, and events never change technical scores, adaptive difficulty, memory, knowledge gaps, or learning. No identity, emotion, attention, or misconduct inference is implemented.

Install the publisher model with `.\.venv\Scripts\python.exe scripts/setup_vision.py` before a fresh Docker build. `VISION_ENABLED=false` is the default; set this non-secret option true and recreate API/worker when optional monitoring is wanted. Each camera session additionally requires an explicit click and browser permission. Interview creation supports `vision_enabled` and `vision_phone_enabled` to disable availability or phone observations per interview. Local CV requires no API key.

Verification includes the complete backend suite, frontend checks, the real sandbox checks, lint/TypeScript/production builds/migrations/service health, local model fixtures, and deployed API/UI checks. Physical webcam/permission/device verification remains pending final integration. See [Phase 10 handoff](docs/PHASE10_HANDOFF.md) and [Phase 11 handoff](docs/PHASE11_HANDOFF.md) for exact phase-specific counts, startup, evidence, privacy/security, and limitations. Phase 11 uses the existing provider abstraction; live provider credentials remain a final integration task.

## Phase 12 — reporting, analytics, and consent-based recruiting

Phase 12 adds immutable report snapshots and PDF downloads, candidate activity analytics, a recruiter job board and application review flow, and admin-only provider/worker readiness and role management. Application consent scopes recruiter access to the selected analyzed posting, resume evidence, matching result, and related completed interview reports. Candidates can withdraw applications. The product preserves prior phases and keeps scoring/evidence limits explicit.

See [Phase 12 handoff](docs/PHASE12_HANDOFF.md) and [final integration checklist](docs/FINAL_INTEGRATION.md) for API/schema details, role setup, testing, provider gates, and local startup. No deployment was performed for this phase.
