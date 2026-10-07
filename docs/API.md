# REST API contract

Target API, implemented incrementally through Phase 7 learning and retry. Implemented sections/handoffs supersede later blueprint routes. See [Phase 4 exact contracts](PHASE4_HANDOFF.md#api) and the running `/docs` OpenAPI schema. All business routes use `/api/v1`; examples below are relative to that prefix. UUID path IDs are ownership-scoped. JSON request/response schemas are implemented in Pydantic and become OpenAPI source of truth. `?` indicates optional input. No table row is automatically a public response: password hashes, storage keys, hidden question reasons, prompt context and provider operation details are never serialized.

## Shared behavior

- Authentication uses opaque cookie sessions. Authenticated mutations require a CSRF token and valid origin; login/register require a valid origin. Session bootstrap returns the CSRF token; keep it in memory. Cookies use Secure in production and HTTP-compatible settings locally.
- Standard error: `{error:{code,message,details?,request_id}}`. Use 401 unauthenticated, 403 forbidden action, 404 inaccessible/missing object, 409 conflicting revision/idempotency body, 422 invalid data, 429 quota, 503 provider unavailable.
- Lists return `{items,next_cursor}`; `limit` defaults to 20, max 100. Cursors are stable `(created_at,id)` pairs and queries enforce ownership before pagination.
- Long tasks return `202 {job_id,status,status_url}`. Poll GET `/operations/{job_id}` for `{status,result?,error?}`. Never return HTTP 200 with fake success after a provider error.
- Answer/start/end/retry writes require `Idempotency-Key: UUID`; state mutations include `expected_revision`. Same key and payload returns original result; changed payload is 409.

## Authentication and identity

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| POST | `/auth/register` | Create candidate account and empty profile | `{email,password,display_name}` | 201 `{id,email,display_name,role,is_active,created_at}`; no session cookie |
| POST | `/auth/login` | Start session | `{email,password}` | 200 `{user,csrf_token,expires_at}` + Set-Cookie |
| GET | `/auth/session` or `/auth/me` | Restore session | Cookie | 200 `{user,csrf_token,expires_at}` |
| POST | `/auth/logout` | Revoke current session | `{}` + CSRF | 204 + expired cookie |
| POST | `/auth/password-reset` | Request reset, later | `{email}` | 202 generic response |
| POST | `/auth/password-reset/confirm` | One-use password reset | `{token,new_password}` | 204; revoke sessions |
| GET | `/candidates/me` | Current profile | â€” | `ProfileOut` including contact, education, experience, goals, preferences and revision |
| PATCH | `/candidates/me` | Update profile facts | `{expected_revision,display_name?,headline?,biography?,timezone?,goals?,...}` + CSRF | Updated `ProfileOut`; stale revision returns 409 |
| POST | `/candidates/me/export` | Private data export | `{}` | 202 operation |
| DELETE | `/candidates/me` | Account/data erasure | Reauthentication proof | 202 erasure operation |
| GET | `/skills` | Canonical skill search | `?query=&cursor=` | Skill page |
| PUT | `/candidates/me/skills/{skill_id}` | Self-reported skill | `{self_reported_level}` | Skill + distinct assessed fields |
| DELETE | `/candidates/me/skills/{skill_id}` | Remove self-report | â€” | 204; assessed evidence governed separately |

## Documents, jobs and projects

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| POST | `/resumes` | Upload and queue extraction | Multipart `file` (PDF/DOCX, ≤10MB) | 202 `ResumeOut` with persisted uploaded state |
| GET | `/resumes` | List own versions | â€” | `ResumeOut[]` newest first |
| GET | `/resumes/{id}` | Status, extracted text and typed facts | â€” | `ResumeOut` |
| GET | `/resumes/{id}/file` | Download own original | â€” | Private attachment response |
| POST | `/resumes/{id}/replace` | Add replacement as new historical version | Multipart file | 202 new `ResumeOut` |
| POST | `/resumes/{id}/retry` | Requeue a failed parse | `{}` | 202 `ResumeOut` |
| DELETE | `/resumes/{id}` | Erase file, facts and dependent match | CSRF | 204 |
| POST | `/jobs` | Create JD target | `{title,company?,description}` | 201 `JobOut` draft |
| GET | `/jobs` | Own JD list | â€” | `JobOut[]` |
| GET | `/jobs/{id}` | JD and analysis | â€” | `JobOut` |
| PATCH | `/jobs/{id}` | Revise owned JD | `{title,company?,description,expected_version}` | Updated draft; old analysis cleared |
| DELETE | `/jobs/{id}` | Delete target/requirements/match | CSRF | 204 |
| POST | `/jobs/{id}/analyze` | Deterministically extract requirements | `{}` | Analyzed `JobOut` |
| POST | `/jobs/{id}/match` | Save profile + selected resume comparison | `{resume_id?}` | `MatchOut` |
| GET | `/jobs/{id}/match` | Read saved result and staleness | â€” | `MatchOut` |
| GET | `/skills` | Search observed canonical skills | `?query=` | Up to 100 skills |
| POST | `/projects` | Save project | `{title,description,repository_url?,skill_ids}` | 201 project |
| GET | `/projects` | Own projects | Cursor | Project page |
| PATCH | `/projects/{id}` | Edit project | `{title?,description?,skill_ids?}` | Updated project |
| POST | `/projects/{id}/documents` | Ingest project text later | Multipart file | 202 ingestion operation |
| DELETE | `/projects/{id}` | Delete project context | â€” | 204 or 202 for derivative erasure |

## Interview lifecycle

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| GET | `/interviews/provider` | Safe provider readiness | â€” | `{configured,provider?,model?,message}`; never includes secrets |
| POST | `/interviews` | Create draft | `{interview_type,mode,resume_id?,job_id?,question_limit,duration_minutes?,selected_topics,difficulty,candidate_focus,instructions,show_hints}` | 201 authoritative interview |
| POST | `/interviews/{id}/start` | Plan/generate first question | `{expected_revision}` | 202 operation |
| GET | `/interviews` | Own history | `?status=` | Up to 100 newest authoritative interviews |
| GET | `/interviews/{id}` | Authoritative UI state | â€” | Interview, current question, plan, progress and mode-safe feedback |
| GET | `/interviews/{id}/current` | Poll authoritative UI state | â€” | Same contract as detail |
| GET | `/interviews/{id}/questions` | Visible question history | â€” | Question array; no hidden generation reason |
| GET | `/interviews/{id}/answers` | Submitted answer history | â€” | Practice feedback immediately; simulation feedback only after completion |
| POST | `/interviews/{id}/answers` | Atomically save and queue turn | `{question_id,text,duration_seconds?,expected_revision,idempotency_key}` | 202 `{interview_id,operation_id,status,revision}` |
| POST | `/interviews/{id}/pause` | Pause outstanding question | `{expected_revision}` | Authoritative interview |
| POST | `/interviews/{id}/resume` | Resume saved outstanding question | `{expected_revision}` | `{status,revision,current_question}` |
| POST | `/interviews/{id}/complete` | Finish from waiting/paused | `{expected_revision}` | Completed interview and stored summary |
| POST | `/interviews/{id}/cancel` | Stop and invalidate pending work | `{expected_revision}` | `{status,revision}` |
| GET | `/interviews/{id}/summary` | Completed structured summary | â€” | Dimension averages, strengths and development areas; no overall hiring score |

Focused retry creation is implemented through Phase 7 learning routes below; public operation inspection and separate answer-evaluation routes remain blueprint extensions.

## Learning, progress and reporting

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| GET | `/knowledge-gaps` | Own gap list | `?status=&cursor=` | Gap page including provisional flag/evidence counts |
| GET | `/knowledge-gaps/{id}` | Explain gap | â€” | `{concept,status,evidence,transitions,policy_version}` |
| GET | `/misconceptions` | Own supported misconceptions | Cursor | Claim/correction/evidence page |
| POST | `/learning-plans` | Generate grounded plan | `{interview_id?,gap_ids}` | 202 operation |
| GET | `/learning-plans` | Own plans | Cursor | Plan page |
| GET | `/learning-plans/{id}` | Plan with resources/practice | â€” | `{id,title,items,status}` |
| PATCH | `/learning-items/{id}` | Track activity, not mastery | `{status}` | Updated item |
| GET | `/progress` | Comparable aggregate history | `?concept_id=&from=&to=` | `{series,coverage,sample_counts,comparability}` |
| GET | `/dashboard` | Actual summary | â€” | Latest report, evidence coverage, active gaps and next learning item |
| POST | `/career-profiles` | Compute new advice, later | `{target_role_ids?}` | 202 operation |
| GET | `/career-profiles/latest` | Latest career snapshot | â€” | `{roles,alignment,coverage,reasons,recommendations,version}` or 404 |
| GET | `/interviews/{id}/report` | Structured report | â€” | Versioned report snapshot/status |
| POST | `/interviews/{id}/report` | Generate/retry PDF | `{}` | 202 operation; idempotent by source revision |
| GET | `/reports/{id}/download` | Authorized PDF | â€” | Stream application/pdf or short-lived private redirect |

## Later voice, coding, vision and administrative routes

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| POST | `/interviews/{id}/audio` | Transcribe candidate audio | Multipart audio + question_id | 202 `{audio_file_id,job_id}`; result contains editable transcript |
| POST | `/questions/{id}/speech` | Generate/cache TTS | `{voice,locale}` | 202 operation or existing authorized audio URL |
| POST | `/answers/{id}/code-submissions` | Execute isolated code | `{problem_id,language,source}` | 202 operation |
| GET | `/code-submissions/{id}` | Actual execution results | â€” | `{status,public_tests,hidden_pass_count,errors,limits}` |
| POST | `/interviews/{id}/frames` | Bounded opt-in frame batch | Multipart frames + timestamps | 202; server determines events |
| GET | `/interviews/{id}/integrity-events` | Review recorded signals | Cursor | Event page |
| GET | `/recruiter/jobs` | Organization-owned jobs | Cursor | JD page |
| POST | `/recruiter/jobs` | Create organization JD | `{organization_id,title,description}` | 202 operation |
| GET | `/recruiter/jobs/{id}/applications` | Consenting candidates only | Cursor | Authorized application page |
| GET | `/recruiter/applications/{id}` | Granted profile/reports/history | â€” | Scoped candidate evidence |
| POST | `/recruiter/comparisons` | Compare granted candidates | `{application_ids,concept_ids?}` | `{profiles,coverage,comparable_dimensions}` |
| PATCH | `/integrity-events/{id}/review` | Human review | `{review_status,note}` | Reviewed event + audit record |
| POST | `/admin/knowledge-documents` | Quarantined KB ingestion | Multipart file + metadata | 202 ingestion operation |
| POST | `/admin/knowledge-documents/{id}/approve` | Publish reviewed source | `{expected_version}` | Published version |
| GET | `/admin/operations` | Failure/queue inspection | Status/cursor | Redacted job page |

## Phase 1 endpoints

- `GET /api/v1/health/live` → 200 `{status:"ok",service:"intervai-api"}`. Liveness does not require a database.
- `GET /api/v1/health/ready` → 200 `{status:"ready",database:"connected",vector:"available"}` only after a real SQL query and installed-extension check; otherwise 503 with a non-sensitive unavailable state.
- `GET /docs` and `/openapi.json` → local development documentation.

Future WebSocket endpoint, only if streaming becomes necessary: `/api/v1/interviews/{id}/stream`, authenticated at upgrade with session/origin validation; messages have `{event_id,revision,type,payload}` and support replay from last event. Do not send auth tokens in query strings. HTTP state fetch is still the recovery authority.

## Implemented Phase 6 candidate memory API

All GET routes below require a candidate session and return only the actor's private memory. `/api/v1/candidates/me/memory` returns structured performance memory and self-reported target roles. `/skills/history` and `/concepts/history` under the same prefix return chronological stored observations. `/knowledge-gaps` accepts an optional status; `/knowledge-gaps/{id}` returns source-linked evidence and transition reasons. `/misconceptions` returns misconception memory with gap status. `/memory/{id}/evidence` provides question/answer/evaluation/source locators and accepts an optional `before` timestamp. Foreign IDs return 404. Reads are no-store. History is bounded; no learning mutations are implemented. Interview configuration adds `use_memory: boolean=true`. See [Phase 6 handoff](PHASE6_HANDOFF.md).


## Implemented Phase 7 learning API

Candidate authentication and mutation CSRF/origin checks apply to every path. `GET/POST /learning/plans` lists or creates structured plans from `gap_ids`, optional `job_id`, UUID `idempotency_key` and `regenerate`. `GET /learning/plans/{id}` returns items, targets, baseline evidence, progress and attempts. `POST /learning/plans/{id}/start` takes `expected_revision` and records an explicit learning action. `GET /learning/items/{id}` reads the lesson; `/complete` takes the parent plan revision; `/generate` takes the content revision and requires configured providers. `/practice` takes an idempotency key and returns an attempt/interview. `/learning/items/{id}/practice/{attempt_id}/submit` delegates the existing AnswerInput to the durable interview evaluator. `GET /learning/attempts/{id}` returns own persisted activity/comparison. `POST /learning/retries` supports single/multiple/topic/skill/recommended selections, optional plan/job and a question budget. `/knowledge-gaps/{id}/learning-plan` and `/retry` are single-gap shortcuts. `GET /candidates/me/progress?job_id=` exposes real learning/retry progress and deterministic recommendations. Foreign IDs are 404, conflicts 409, unavailable providers 503, and responses no-store. [Phase 7 handoff](PHASE7_HANDOFF.md) contains the endpoint table and exact revision/idempotency rules.

## Implemented Phase 8 speech endpoints

Authenticated candidate routes under `/interviews/{id}/voice`: POST `/session`, GET `/status`, POST `/event`, POST `/synthesize`, POST multipart `/transcribe`, GET `/audio/{turn_id}`. All mutations retain CSRF/Origin enforcement and speech actions validate interview/current-question state and both revisions. Uploads accept only mono PCM16 16 kHz WAV, at most 6 MB/180 s. Temporary candidate recordings cannot be downloaded. TTS requests read server-owned question text. Duplicate speech keys reuse the original operation; changed payloads conflict. Slow operations use existing interview_jobs and status polling. Existing POST answers accepts optional `voice_turn_id` for a ready, owned transcript on the current question; typed clients remain compatible. The [Phase 8 handoff](PHASE8_HANDOFF.md) contains exact inputs, statuses and retention rules.


## Implemented Phase 9 coding API

Every endpoint requires candidate authentication; mutations require the existing CSRF/origin checks. Foreign private problem/submission/interview references return 404. DTOs explicitly exclude hidden test contents and reference solutions. The frontend proxy allowlist includes these paths under `/api/v1`.

| Method | Path | Contract |
|---|---|---|
| GET | `/coding/provider` | `ready`, supported languages, safe unavailable message |
| GET / POST | `/coding/problems` | Safe collection / typed private draft including public and hidden tests and reference solutions as input only |
| GET | `/coding/problems/{id}` | Safe problem fields and public cases only |
| POST | `/coding/problems/generate` | Owned `interview_id`, `topic`, `difficulty`; generated draft queued for reference validation |
| POST | `/coding/problems/{id}/validate` | Owned `interview_id`, `topic`, `difficulty`; existing leased validation job |
| POST | `/interviews/{id}/coding/run` | Public tests; question/revision/replay key/language/source/explanation |
| POST | `/interviews/{id}/coding/submit` | Final public+hidden judging with safe aggregate response |
| GET | `/interviews/{id}/coding/submissions` | Owned attempt history, latest 100 |
| GET | `/coding/submissions/{id}` and `/status` | Owned persisted source/state/results/estimated analysis |
| POST | `/coding/submissions/{id}/cancel` | Persist stop request; worker signals isolated runner |

Interview creation accepts `interview_type="coding"` and optional `coding_problem_ids`; existing start/detail/progression APIs are reused. Run/Submit input: `question_id`, `expected_revision`, `idempotency_key`, language `python|cpp|java`, source <=32768 UTF-8 bytes, optional explanation <=4000 characters. Equal retries/concurrent requests reuse the submission; conflicting payloads, active work, stale revisions, or noncurrent questions return 409. A coding question cannot bypass execution through the typed-answer route. Final Submit advances through the existing answer evaluator after judging; Run permits revision. Hidden runtime stdout/stderr/per-case outcomes never enter candidate responses or AI context. See [Phase 9 handoff](PHASE9_HANDOFF.md) for full schemas, state semantics, limits, and verification.


### Current provider configuration

The existing authenticated interview-provider status endpoint uses configuration-selected `LLMProvider`. Primary selection is `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-6-luna`; `OPENAI_MODEL` overrides the model alias when nonblank. OpenAI uses `OPENAI_API_KEY` or legacy `LLM_API_KEY`. Gemini remains selectable with `GEMINI_MODEL` and `GEMINI_API_KEY`. These keys are server-side only, never part of the provider-status DTO. Missing configuration is reported explicitly; no silent fallback occurs. Coding routes and their safe execution results are unchanged. Live OpenAI account access remains a final-integration verification gate.


## Phase 10 visual observations

All routes below use candidate authentication and existing interview ownership. Mutations also require CSRF and allowed Origin. Cross-owner IDs return 404. Vision is optional and cannot alter interview answer/adaptive/skill state.

| Method | Route under `/api/v1` | Contract |
| --- | --- | --- |
| GET | `/interviews/{id}/vision/status` | Provider availability, optional policy, sampling settings, session revision/sequence/error, event timeline |
| POST | `/interviews/{id}/vision/session` | JSON `enabled`, `expected_revision`; active interviews only when enabling |
| POST | `/interviews/{id}/vision/frame` | Multipart `revision`, `sequence`, timezone-aware `captured_at`, JPEG/PNG `image`; server-owned inference/aggregation |
| POST | `/interviews/{id}/vision/notice` | JSON `revision`, `notice` restricted to `interrupted` or `orientation_changed`; explicitly unverified client provenance |
| GET | `/interviews/{id}/integrity-events` | Owned chronological event data plus observable-only limitations note |

`InterviewCreate` supports `vision_enabled` and `vision_phone_enabled` (both per-interview flags default true; global feature defaults disabled). No `/vision/events` route accepts detector claims/confidence. Frames are limited to 128 KiB and 32–640px per side, validated by actual format; the total multipart body is capped at 136 KiB. Old timestamps/session revisions return 409; concurrent/too-frequent samples are dropped with 429; replayed sequences do not rerun inference. Model failure yields an explicit vision error without fabricating absence. Events expose only id/type/severity, start/end/duration, genuine nullable model score, detector, safe provenance metadata. See [Phase 10 handoff](PHASE10_HANDOFF.md) for exact aggregation, privacy, and lifecycle contracts.


## Phase 11 career guidance

Career routes require candidate authentication; mutations additionally require CSRF and allowed Origin. Analysis, profile, role, roadmap, advice, and choice references are ownership-scoped. Readiness is deterministic application output; LLM advice is optional and cannot alter readiness labels.

| Method | Route under `/api/v1` | Contract |
| --- | --- | --- |
| GET/PATCH | `/career/profile` | Candidate-owned preferences and target goals; PATCH requires career and candidate revision tokens |
| GET | `/career/roles`, `/career/roles/{id}` | Seeded versioned taxonomy and role details/provenance |
| POST | `/career/analyze` | Explicit analysis with role list, optional owned job ID, expected profile revision, idempotency key |
| GET | `/career/analyses`, `/career/analyses/{id}` | Version history and owned immutable evidence snapshot; detail/readiness reports staleness |
| GET | `/career/readiness`, `/career/skill-gaps` | Latest persisted analysis and development steps; no read-side LLM generation |
| POST | `/career/choices` | Revision-checked pursue/dismiss choice on a historical roadmap skill |
| POST | `/career/roadmap` | Existing gap IDs for steps explicitly marked pursue, passed to the Phase 7 learning-plan service with an idempotency key |
| POST | `/career/analyses/{id}/advice` | Optional structured LLM reflection; optional existing pgvector retrieval with traceable sources |

Taxonomy requirements are illustrative. Job-specific requirements remain separate. See [Phase 11 handoff](PHASE11_HANDOFF.md) for the detailed contract, readiness policy, and limitations.

## Phase 12 reports, analytics, applications, and operations

Candidate routes require candidate authentication. All mutations require CSRF and an allowed Origin. Recruiter routes require recruiter role and enforce recruiter-owned posting/application scope. Admin routes require admin role; role changes are audited.

| Method | Route under `/api/v1` | Contract |
| --- | --- | --- |
| GET | `/reports` | Candidate's latest immutable report versions |
| POST | `/reports/{interview_id}/generate` | Build or reuse the fingerprinted snapshot of an owned completed interview |
| GET | `/reports/{report_id}?version={n}` | Read an owned report version; defaults to latest |
| GET | `/reports/{report_id}/pdf?version={n}` | Download PDF rendered from that stored snapshot |
| GET | `/analytics/overview`, `/analytics/skills`, `/analytics/learning` | Candidate activity counts, descriptive skill evidence, and plan progress; empty values indicate insufficient data |
| GET | `/applications/jobs`, `/applications` | Public active-posting list; signed-in candidate's own application history |
| POST | `/applications` | Candidate applies with explicit `share_consent: true` and an analyzed exact-match candidate job copy |
| PATCH | `/applications/{application_id}` | Candidate withdraws own application |
| GET/POST | `/recruiter/jobs` | List owned postings / create posting |
| PATCH | `/recruiter/jobs/{job_id}` | Revision-checked update; content locks after first application |
| GET | `/recruiter/jobs/{job_id}/applications` | Paginated consented applicants for an owned posting |
| GET | `/recruiter/applications/{application_id}` | Candidate data only within that recruiter-owned consent scope |
| GET | `/recruiter/applications/{application_id}/reports/{report_id}` | Latest report for a completed interview linked to that exact candidate job |
| GET | `/recruiter/applications/{application_id}/reports/{report_id}/pdf` | Same ownership checks, PDF response |
| GET | `/admin/system-status`, `/admin/users`, `/admin/audit` | Admin-only safe readiness, account roles, and append-only audit records |
| PATCH | `/admin/users/{user_id}/role` | Admin role assignment; protected against self-demotion and removing the final active admin |

Provider responses include names and readiness only, never API key material. See [Phase 12 handoff](PHASE12_HANDOFF.md) for the exact consent scope and output limits.
