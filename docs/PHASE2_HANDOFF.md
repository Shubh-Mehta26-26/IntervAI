# PHASE 2 HANDOFF

Status: authentication and candidate profiles implemented and verified. Phase 3 has not started. Existing Next.js, FastAPI, PostgreSQL/pgvector, Alembic and Docker Compose infrastructure is retained.

## What was implemented

- Registration creates a candidate user, empty profile and default preferences in one transaction. The browser then logs in and opens profile onboarding.
- Login, current session/user, logout, expiration, disabled-user rejection and server-side session revocation.
- Protected dashboard and profile pages with backend candidate authorization and owner-scoped queries.
- Persistent name, phone, location, headline, biography, timezone, experience in months, career interests, target roles, education, work history and interview preferences.
- Responsive login/register pages, navigation, form labels, loading/error/success feedback, editable education/work entries and conflict detection for concurrent profile edits.
- Dashboard content comes from the signed-in candidate. Completion counts describe profile setup only; there are no fabricated interview metrics.

## Database changes

Alembic revision `585d0358e2de` follows the existing `0001_foundation` baseline. The foundation's vector extension behavior is retained. The Phase 2 downgrade removes only Phase 2 tables in dependency order.

| Table | Implemented purpose and fields |
|---|---|
| `users` | UUID, normalized email, Argon2 password hash, canonical full name as `display_name`, candidate/recruiter/admin role, disabled and email-verification timestamps |
| `sessions` | User FK, unique session-token digest, CSRF digest, expiry/revocation/last-seen timestamps |
| `candidates` | Unique user FK, phone, location, headline, biography, timezone, experience_months, bounded career_interests array, profile revision and future memory revision |
| `candidate_goals` | Candidate FK, role title, priority, active flag; unique role per candidate |
| `candidate_education` | Candidate FK, institution, qualification, field of study, start/end dates |
| `candidate_experience` | Candidate FK, organization, title, description, start/end dates |
| `candidate_preferences` | Unique candidate FK, interview mode, duration and locale |
| `auth_rate_limits` | HMAC bucket key and window-start composite primary key, attempt count |

The first seven tables have generated UUIDs and created/updated timestamps. FKs cascade within the identity aggregate. Database constraints enforce email uniqueness, allowed roles, nonnegative revisions/priority, experience bounds, date ordering, session expiry and preference mode/duration. `is_active` is derived from `disabled_at`; the name is stored once on the user. Experience uses months to avoid fractional-year ambiguity. No profile POST is needed because registration creates the profile atomically.

## API endpoints

All paths below have the prefix `/api/v1`. The frontend forwards only allowlisted paths/methods to the fixed backend URL. Running OpenAPI at `http://localhost:8000/docs` contains the exact Pydantic schemas.

| Method/path | Contract |
|---|---|
| POST `/auth/register` | `{email,password,display_name}` → 201 `UserOut`; creates profile/preferences; does not issue a session |
| POST `/auth/login` | `{email,password}` → `{user,csrf_token,expires_at}` and session cookie |
| GET `/auth/session` | Cookie → `{user,csrf_token,expires_at}` |
| GET `/auth/me` | Alias of session endpoint with the same response |
| POST `/auth/logout` | Cookie, trusted Origin and `X-CSRF-Token` → 204; revokes session and expires cookie |
| GET `/candidates/me` | Candidate session → complete `ProfileOut` |
| PATCH `/candidates/me` | Candidate session, trusted Origin, CSRF and `{expected_revision,...changes}` → updated `ProfileOut` |

`UserOut` exposes only id, email, display_name, role, is_active and created_at. `ProfileOut` includes identity/contact fields, goals, education, experience, preferences, revision and timestamps. Password/session hashes are never serialized.

PATCH omits unchanged fields; nullable contact fields can be cleared with null. Supplied goal/education/experience arrays replace that collection; `[]` clears it. Supplied preferences are a complete object with schema defaults for omitted subfields. Required scalar/list fields cannot be null. A row lock plus `expected_revision` prevents silent lost updates; stale revisions return 409. There is no route for accessing another candidate by ID.

Validation/error responses use the existing `{error:{code,message,details?,request_id}}` envelope. Main statuses: 401 invalid/expired authentication, 403 role/CSRF/origin rejection, 409 duplicate email or stale revision, 413 oversized request, 422 invalid input, 429 rate limit and 503 unavailable database. Login failures use the same message for absent users and wrong passwords.

## Frontend pages and components

- `/login` and `/register`: shared authentication layout/form, onboarding copy, password confirmation, browser and server validation.
- `/dashboard`: authenticated welcome, actual target roles and profile completion, links to profile editing.
- `/profile`: personal/contact details, target roles/interests, education, work history and interview preferences.
- `/`: redirects to dashboard when authenticated or login otherwise.
- Shared application shell/logout button; root and candidate loading/error boundaries; separate browser and server API clients.

Next.js server checks protect navigation, and FastAPI independently enforces session validity, roles and ownership. Sessions and CSRF values are not persisted in localStorage. Expired-session/profile-conflict errors retain the form draft rather than silently discarding edits.

## Authentication and security

Opaque server-side sessions fit this same-origin web application and allow immediate logout/revocation without JWT revocation infrastructure. A random session token is placed in `intervai_session`; PostgreSQL stores only its SHA-256 digest. Login rotates the existing browser session. Default absolute expiry is 24 hours; there is no sliding renewal.

- Argon2id password hashing: time cost 2, memory 19,456 KiB, parallelism 1; rehash on successful login when needed. Registration accepts 12–128 characters and rejects blank passwords. Unknown-user login performs dummy hash verification.
- Cookies: HttpOnly, SameSite=Lax, Path=/; `COOKIE_SECURE=true` required in production. Local HTTP development uses false.
- `AUTH_SECRET` is generated locally, read from environment, and must be at least 32 characters. It signs CSRF derivation and obscures throttle identifiers; it is not committed or printed by initialization.
- Login/register validate Origin. Authenticated mutations require both trusted Origin and a session-bound CSRF token. CORS uses explicit configured origins; wildcard origins are rejected.
- Production configuration requires HTTPS origins and secure cookies. TLS termination and public deployment are outside this local verification.
- Registration always assigns candidate; client-supplied role/owner fields are rejected. Reusable role guards prepare recruiter/admin authorization without enabling those workflows.
- PostgreSQL atomic fixed-window throttling applies per action and email/IP bucket: default 10 email attempts and 100 source-IP attempts per 900 seconds. Successful attempts also count. Old throttle windows are pruned.
- JSON inputs reject unknown fields, constrain lengths/counts/dates/timezones and cap mutation bodies at 64 KiB. Proxy/backend request time limits bound reads.
- Authentication responses use no-store. Validation errors omit submitted raw input; database errors hide SQL parameters and return generic messages. Passwords and opaque tokens are not deliberately logged.

## Tests and results

| Verification | Result |
|---|---|
| Backend pytest | **33 passed**, including existing health tests and real PostgreSQL identity tests |
| Backend/scripts Ruff | Passed |
| Frontend ESLint | Passed |
| TypeScript type check | Passed |
| Next.js production build | Passed locally and in Docker |
| Clean database migration | Upgrade → downgrade to base → upgrade passed in a disposable database |
| Live Alembic state | Revision `585d0358e2de`; metadata check found no new upgrade operations |
| Container dependency check | `pip check` passed |
| Docker Compose | Frontend, backend and PostgreSQL healthy; migration service exited successfully |
| Live API smoke through Next.js | Registration, login/session, profile save, logout/replay rejection and persistence after fresh login passed |
| Direct PostgreSQL verification | Account role/password hash and saved profile values confirmed |
| Browser desktop/mobile | Registration, login, incorrect-password feedback, logout, protected redirects, profile loading/editing and persistence passed |

Identity tests cover all 13 requested cases, plus CSRF, cross-session tokens, role enforcement, session rotation/expiry/disabled users, rate limiting, profile revision conflicts, nested defaults, invalid dates/timezones, secure-cookie behavior and oversized inputs. These tests create a uniquely named disposable PostgreSQL database, migrate it, and drop only that database afterward.

Browser verification used 1440×1000 desktop and 390×844 mobile viewports. Profile/mobile layouts were checked for horizontal overflow. The clearly named temporary development QA account and the live API smoke account were removed after their saved rows were verified. No sample candidate accounts or fake interview analytics were seeded.

Screenshots show the temporary QA account before cleanup:

- [Desktop dashboard](screenshots/phase2-dashboard.png)
- [Mobile dashboard](screenshots/phase2-mobile.png)

## Commands to run the project

From the repository root in PowerShell, with Docker Desktop running:

```powershell
# Use python instead on a fresh machine with Python on PATH.
./.venv/Scripts/python.exe scripts/init_environment.py
docker compose config --quiet
docker compose up --build -d
docker compose ps
./scripts/check.ps1
```

Open `http://localhost:3000/register`. Existing accounts can use `/login`. There is no seeded password. On this workstation, Docker may need its per-user installation added to PATH:

```powershell
$env:PATH = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;" + $env:PATH
```

Run validation with the development PostgreSQL service available and backend development dependencies installed:

```powershell
./.venv/Scripts/python.exe -m pytest tests/backend -q
./.venv/Scripts/python.exe -m ruff check --config backend/pyproject.toml backend tests/backend scripts
./.venv/Scripts/python.exe scripts/smoke_identity.py
cd frontend
npm run lint
npm run typecheck
npm run build
```

Tests require create/drop database and pgvector installation privileges on the development PostgreSQL instance. Do not run them against production. See the root README for native setup and the Windows-compatible backend launcher. Docker applies migrations automatically; `docker compose down` preserves the named database volume. Do not use `down -v` unless intentionally deleting local data.

## Remaining limitations

- Email verification, password recovery, MFA, email changes, account deletion and session-management UI are not implemented.
- Recruiter/admin roles and guards exist; their workflows and provisioning UI are deferred.
- Interview mode/language/duration are stored preferences only. Interviews, resume/JD ingestion, AI, scoring, voice and all other Phase 3+ features remain unimplemented.
- Browser traffic shares the Next.js proxy's source-IP throttle bucket. Public deployment needs a deliberate trusted-ingress/client-IP policy and tuned abuse limits; forwarded client IPs are not blindly trusted.
- Sessions use absolute expiry. Expired/revoked session rows have no scheduled retention cleanup yet; last_seen_at is initialized but not continuously updated.
- Supplied child collections are replaced transactionally; their internal database IDs are not public stable editing identifiers in this phase.
- This verifies local development, not a production deployment or independent penetration test. Production secrets, TLS, backups, operational monitoring and deployment configuration still need provisioning.

Phase 2 is complete. Stop here before implementing Phase 3.
