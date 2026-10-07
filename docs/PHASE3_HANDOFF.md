# PHASE 3 HANDOFF

Status: complete and verified. This phase adds resume and job-description intelligence to the existing authenticated candidate workspace. Phase 4 and the adaptive interview engine have not started.

## Architecture

The Phase 1–2 modular monolith remains intact. FastAPI routes validate and authorize requests, services own transactions and matching policy, provider modules isolate storage/extraction/parsing/taxonomy behavior, and PostgreSQL is authoritative. Next.js continues to use its fixed same-origin allowlisted proxy.

Resume processing is asynchronous. Upload commits a private file plus `uploaded/pending` database state and returns 202. A separate worker claims rows with `FOR UPDATE SKIP LOCKED`, records a claim UUID and 90-second lease, extracts outside the transaction, then commits only if it still owns that claim. Expired leases recover after restart; three interrupted attempts produce an explicit failure. The UI polls persisted status and never claims success early.

```text
PDF/DOCX → signature/archive checks → private random storage key
         → uploaded state → durable worker lease → isolated text extraction
         → whitespace cleaning → typed deterministic parsing
         → canonical skills + exact evidence quotes → parsed/failed state

Job text → section/requirement extraction → canonical skills + source quotes
         → profile + selected parsed resume evidence
         → demonstrated / partial / not demonstrated → persisted match
```

Resume evidence and the candidate profile coexist. Uploads are immutable historical versions and never overwrite user-entered profile facts. Replacing a resume creates a new version. Matching reads the current profile plus at most one explicitly selected parsed resume.

## Database

Alembic revision `f3a4db968ddc` follows `585d0358e2de`; Phase 1 and Phase 2 revisions were not replaced. Its downgrade removes only Phase 3 tables in dependency order.

| Table | Purpose |
|---|---|
| `skills` | Canonical slug/name/category shared by resume and job evidence |
| `resumes` | Candidate owner, safe original metadata, random storage key, SHA-256, version, processing/parsing states, error, text, typed JSON facts, parser version and worker lease/claim/attempts |
| `resume_skills` | Resume-to-canonical-skill relationship with exact source evidence JSON |
| `job_descriptions` | Candidate owner, title/company/text/source, optimistic version, analysis state/version and typed JSON analysis |
| `job_skills` | Job-to-canonical-skill relationship, required/preferred/unspecified classification and source evidence |
| `candidate_job_matches` | One current persisted result per job, optional resume version and source fingerprint for staleness detection |

Structured resume sections stay inside validated versioned JSON because they are historical extraction evidence with line/section/source locators, not profile records. Skills are normalized relationally because they are reused by jobs, matches and future interview planning. Candidate/job/resume FKs cascade; skill rows are retained as shared vocabulary. Constraints enforce status sets, 10 MB file bounds, version uniqueness and requirement classifications.

## Parsing and taxonomy

PDF extraction uses pypdf; DOCX extraction reads only WordprocessingML paragraphs through defused XML parsing. Basic extraction does not rely on an LLM. The `DocumentExtractor`, `ResumeParser`, optional `StructuredLLMParser`, `Storage`, and taxonomy modules are explicit provider boundaries. No LLM adapter is enabled or simulated in this phase.

`ResumeFacts` validates name, email, phone, location, summary, education, experience, projects, certifications, achievements, links, skills and warnings. Unknown fields remain null/empty. Contact fields are extracted only from explicit patterns. Section content is preserved as exact evidence with line number and source. Skill mentions come only from literal canonical names or reviewed aliases; negative phrases such as “no experience with” are excluded.

The initial versioned vocabulary includes common languages, frameworks, databases, cloud/DevOps, AI/ML, tooling and communication skills. Examples include PostgreSQL/Postgres, React/React.js, Next.js/NextJS, Kubernetes/K8s and RAG/retrieval-augmented generation. Related technologies are not merged: Python does not imply FastAPI, SQL does not imply PostgreSQL, and AWS does not imply general cloud proficiency. Vocabulary entries are product taxonomy, not hard-coded candidate evidence.

Job analysis preserves required, preferred and unspecified importance. A clear heading or wording such as “must”/“preferred” controls classification. Responsibilities, qualifications, education/experience lines, other non-skill requirements and an explicitly supplied domain are stored separately for human review. Editing increments the job version and invalidates the previous analysis.

## Matching logic

Matching has no aggregate percentage. It compares each recognized job skill against exact canonical evidence:

- `demonstrated`: the skill occurs in a resume experience/project line or profile work narrative containing an application verb such as built, developed, deployed or implemented.
- `partial`: the skill is explicitly mentioned elsewhere, such as a skills list, but no application claim was extracted.
- `not_demonstrated`: no canonical evidence was found. The UI explicitly says this does not prove the candidate lacks the skill.

Each outcome stores candidate evidence quotes and job-source quotes. Evidence is self-reported and never presented as assessed proficiency. Qualifications, experience duration, responsibilities and other requirements remain under “needs human review.” A SHA-256 fingerprint over job version, profile revision, selected resume ID/hash/parser version and policy version marks saved matches stale whenever source facts change. Re-running unchanged inputs returns the persisted result without reparsing or recomputing.

## API

All routes use `/api/v1`, candidate authentication and ownership filtering. Mutations require trusted Origin plus session-bound CSRF.

| Method/path | Result |
|---|---|
| GET/POST `/resumes` | List own versions / upload PDF or DOCX and return persisted queued state |
| GET/DELETE `/resumes/{id}` | Read own extraction / erase own file, facts and dependent match |
| GET `/resumes/{id}/file` | Download own original with attachment and sandbox headers |
| POST `/resumes/{id}/replace` | Create a new historical version |
| POST `/resumes/{id}/retry` | Requeue only a failed parse |
| GET/POST `/jobs` | List / create own job target |
| GET/PATCH/DELETE `/jobs/{id}` | Read, versioned edit or delete own target |
| POST `/jobs/{id}/analyze` | Persist current deterministic requirements |
| POST/GET `/jobs/{id}/match` | Save or retrieve evidence comparison and staleness |
| GET `/skills?query=` | Search skills observed in this installation |

Response schemas never expose storage keys, checksums, worker claims or internal ownership columns. Inaccessible UUIDs return 404. Multipart requests pass only the exact allowlisted proxy patterns; query forwarding is restricted to skill search.

## Frontend

- `/resume`: real upload progress, persisted processing status, automatic polling, library/version selection, retry, replace, delete, original download, extracted contacts/sections/skills/links and raw-text review.
- `/jobs`: honest empty state and actual candidate-owned target cards.
- `/jobs/new`: accessible title/company/description form with limits and preserved headings guidance.
- `/jobs/[id]`: original text, edit/delete, extracted requirement categories and quotes, selected resume comparison, saved match, staleness warning and human-review requirements.
- Candidate navigation and dashboard now link to resume and job flows. No interview score, candidate rating or fabricated analytics were added.

## Security

- Uploads require authenticated candidate ownership, trusted Origin and CSRF. FastAPI and the Next.js proxy cap multipart uploads at 10 MB plus envelope overhead and impose timeouts.
- Extension, magic bytes and container structure must agree. Only `.pdf` and `.docx` are accepted. Client filenames are basename-normalized, restricted to safe characters and never used as storage paths. Storage keys are random hex plus an allowlisted suffix; path resolution enforces the private root.
- DOCX validation rejects encryption, duplicate/excessive entries, traversal names, macros, embedded objects, XML entries over 8 MB, expanded archives over 50 MB and suspicious compression ratios. XML entity attacks use defused parsing.
- PDF validation rejects encrypted files, more than 50 pages, forms, open actions, additional actions, JavaScript and embedded files. Extraction text is capped at 200,000 characters with line-length limits. Image-only PDFs fail honestly with an OCR explanation.
- Extraction runs in a child process with a 25-second deadline. Linux workers add CPU/address-space limits; the Compose worker has a 768 MB limit, PID limit, all capabilities dropped and no-new-privileges.
- Uploaded text is always untrusted data. It cannot grant tools, alter policy or execute macros/links/instructions. No provider receives uploaded text in this phase.
- File downloads repeat ownership checks and use attachment, `nosniff` and sandbox headers. Errors avoid raw document contents, SQL parameters and storage locations.

Known security limitation: Phase 3 performs structural rejection, not antivirus/CDR scanning. A production deployment must add a malware scanner/quarantine provider, private object storage, backup/retention policy, operational metrics and hardened worker isolation before accepting public uploads.

## Verification

| Check | Result |
|---|---|
| Backend pytest with real disposable PostgreSQL | **40 passed** |
| Migration chain | clean upgrade → downgrade base → upgrade head passed; `alembic check` found no pending operations |
| Backend/scripts Ruff | Passed |
| Python dependency consistency | Passed |
| Frontend ESLint / TypeScript | Passed |
| Next.js production build | Passed locally and in Docker |
| Docker Compose | PostgreSQL, backend, worker and frontend healthy; migration service exited 0 |
| Real DOCX and PDF extraction | Passed; exact text and structured skills persisted |
| Live full-stack smoke | Registration → upload → worker parse → download byte check → job analysis → saved match → PostgreSQL verification passed |
| Ownership/security | Anonymous and cross-candidate reads/mutations rejected; invalid/oversized files rejected |
| Browser desktop/mobile | Upload status, parsed sections, requirement analysis and persisted match verified; 390×844 view had no horizontal overflow |

The suite covers upload, PDF/DOCX extraction, unsupported/invalid/oversized input, explicit failure and retry, historical replacement, storage deletion, job create/update/delete/version conflict, ownership, analysis, canonical extraction, evidence matching, persistence and authentication. Real extraction tests generate valid documents and inspect actual stored text; production behavior has no fixture parser.

Live browser evidence used a clearly labelled QA DOCX and job. Python/FastAPI appeared as applied claims, Kubernetes as a mention only, AWS as not demonstrated, and REST APIs as an unspecified job skill. The exact created resume/job UUIDs, storage object, temporary QA account and local fixture were removed afterward. The signed-in user's pre-existing profile was not changed.

- [Desktop match evidence](screenshots/phase3-match-desktop.png)
- [Mobile match evidence](screenshots/phase3-match-mobile.png)

## Run commands

Normal local ports are 5433/8000/3000:

```powershell
./.venv/Scripts/python.exe scripts/init_environment.py
docker compose up --build -d
docker compose ps
./scripts/check.ps1
```

Open `http://localhost:3000`. The worker is part of Compose. To use alternate ports for an occupied workstation terminal:

```powershell
$env:POSTGRES_PORT='5434'
$env:API_PORT='8001'
$env:FRONTEND_PORT='3001'
$env:CORS_ORIGINS='["http://localhost:3001","http://127.0.0.1:3001"]'
docker compose up --build -d
./scripts/check.ps1
```

Run verification against a development PostgreSQL instance with create/drop-database privilege:

```powershell
./.venv/Scripts/python.exe -m pytest tests/backend -q -p no:cacheprovider
./.venv/Scripts/python.exe -m ruff check --config backend/pyproject.toml backend tests/backend scripts
./.venv/Scripts/alembic.exe -c backend/alembic.ini check
./.venv/Scripts/python.exe scripts/smoke_intelligence.py
cd frontend
npm run lint
npm run typecheck
npm run build
```

## Limitations and stop condition

- Scanned/image-only PDFs need a future OCR provider. Complex columns/tables can lose reading order; the UI exposes raw text and warnings for review.
- Deterministic contact/section extraction is deliberately conservative. There is no manual fact-correction API yet; candidates can replace the source document while profile data stays editable separately.
- The initial skill taxonomy is curated and finite. There is no embedding/semantic inference, confidence score, proficiency assessment or LLM structuring in this phase.
- Job input is pasted text; job-document upload is deferred because paste already preserves auditable source text without adding another untrusted-file path.
- Resume lists are capped at 20 and jobs at 100 per candidate but are not cursor-paginated yet. Old failed/revoked processing rows have no scheduled retention cleanup.
- Local named-volume storage has no antivirus scanner, object-store durability, cross-host worker sharing or backup lifecycle.

Phase 3 is complete. Adaptive interviews, questions, answers, scoring and all Phase 4 work remain unimplemented.
