# IntervAI functional audit — 28 October 2026

## Outcome

The tested local stack passed its automated regression suite and the live integration checks listed below. This is evidence for the covered workflows, not a guarantee that every possible input, device, or deployment environment is defect-free.

The active stack uses Next.js on port 3001, the native API on 8001, PostgreSQL/pgvector on 5434, the native durable worker, and the dedicated coding sandbox on 8081. Docker and application processes were stopped at the beginning of the audit and were restarted.

## Automated verification

| Check | Result |
| --- | --- |
| Complete backend pytest suite | **191 passed**, 0 failures/errors/skips; 124.54 seconds |
| Frontend voice, avatar, and camera logic | **21 passed** |
| Backend/scripts/test Ruff lint | Passed |
| Full frontend ESLint | Passed |
| TypeScript `tsc --noEmit` | Passed |
| Production Next.js webpack build | Passed for the complete route inventory |
| Real sandbox verification | Passed: Python, C++, Java, time/memory/output limits, cancellation, duplicate execution, and isolation/security checks |
| Local vision detector | 4 fixture checks passed: one person, no person, multiple people, phone |

The backend suite creates a uniquely named disposable PostgreSQL database, verifies migration upgrade/downgrade/re-upgrade, and removes it afterward. It covers identity and CSRF, profiles, resume documents, job analysis/matching, interview modes and transitions, adaptive policies, grounded evaluation, coding results, candidate memory and gaps, guided/evidence-based learning and retries, speech, camera observations, career guidance, report snapshots/PDF, analytics, recruiter consent and ownership, and administrator authorization/audit rules. Provider success/failure cases in this suite use injected test providers; the live checks below separately exercise configured services.

## Live integration verification

| Module | Verified workflow |
| --- | --- |
| Identity/profile | Register, login, edit profile, persisted database values, logout, revoked-cookie replay rejection, login again |
| Resume/job preparation | Upload synthetic DOCX, durable worker extraction, extracted skills, download preserves original bytes, job requirements, matching and persistence |
| AI interview | Real Gemini plan/question, submitted answer, persisted evaluation/adaptive decision, next state and completion |
| RAG | Real Gemini embeddings (1,536 dimensions), query embedding and pgvector retrieval from curated sources |
| Voice | Real Gemini TTS and STT using synthetic speech normalized to the browser's mono 16 kHz PCM WAV input format |
| Coding | Real coding interview -> API queue -> native worker -> sandbox -> completed submission and report |
| Reports | Generated persisted versioned report, fetched PDF with valid `%PDF` header (6,737 bytes in the checked example) |
| Learning | Created a topic plan in the browser, started it, submitted a correct self-check, received feedback, completed a lesson; `1 / 4 completed` survived reload |
| Career | Saved preferences, selected a role, generated analysis; browser Overview and Skill evidence tabs rendered real saved results |
| Recruiting | Separate temporary recruiter created a job; candidate analyzed matching job copy, applied with consent, recruiter reviewed it; withdrawal revoked recruiter access |
| Administrator | Separate temporary staff account checked system readiness, user search and audit endpoints; worker `running`, sandbox `ready` |
| Role enforcement | Candidate requests to admin and recruiter APIs returned 403 |
| Workspace routes | Authenticated HTTP checks passed on 15 candidate pages plus recruiter and admin pages; checked proxy endpoints returned 200 |
| Browser shell | Login, dashboard, navigation search filtering/navigation, theme switching and saved page content; no console errors in the inspected browser log |

Synthetic accounts and records were used for mutations. No existing candidate's profile, interviews, resume, applications, or permissions were edited. Temporary staff and ordinary smoke-test candidate accounts were removed after verification. The synthetic candidate owning the tested PDF report was disabled and its sessions revoked; immutable report protection prevents deleting that account through the database cascade. Its temporary credential file was removed.

## Corrections made during the audit

- Isolated the missing-LLM-configuration test from the workstation's real configured provider. It now explicitly injects the missing-provider status, so the expected 503 does not depend on `.env`.
- Made `smoke_identity.py` accept `INTERVAI_BASE_URL`, matching the other smoke scripts; revoked-session verification now uses the same selected application endpoint. Its original fixed 3000/8000 URLs did not match this local stack.
- Corrected import ordering and marked deliberate post-bootstrap imports in knowledge ingestion/retrieval scripts. All lint checks pass.

The first pytest attempt began before Docker was ready and reported database setup errors. It was superseded by a clean complete run after PostgreSQL was healthy. An early speech probe fed TTS output directly into STT at the wrong sample rate; the correctly formatted browser-equivalent 16 kHz probe passed. Neither intermediate result is counted as an application defect.

## Remaining verification limits

- Physical microphone capture, real-room transcription accuracy, playback quality, webcam framing and OS/browser permission prompts need a human device session. Synthetic audio and mocked capture lifecycle tests cannot certify these experiences.
- Camera detection was checked on fixture images, not a live camera. Detection accuracy varies with lighting and scene; observations are not proof of misconduct.
- Only configured Gemini services were tested live; other optional providers were not enabled or certified.
- Account erasure for a user who owns a report is not supported by the current immutable-report trigger: cascading deletion raises `Report versions are immutable`. A future account-erasure feature needs an explicit retention/anonymization design. The trigger was left intact; one disabled synthetic audit record and its report remain locally.
- The current native development stack was tested. This audit does not certify a fresh all-Docker deployment, Vercel/public hosting, TLS, production capacity, email delivery, or long-duration load.
- Automated PDF extraction/validation tests and a live DOCX upload passed; this does not prove support for every scanned, encrypted, malformed, or unusual resume file.
- An unrelated legacy container belongs to Compose project `intervaig` and is unhealthy. It is not the backend serving this workspace and was not modified.
- Email verification, password reset and MFA are documented as deferred in the project's README; they are not certified features.

## Reproduction

From the repository root with local services running:

```powershell
./.venv/Scripts/python.exe -m pytest tests/backend -q
./.venv/Scripts/python.exe -m ruff check --config backend/pyproject.toml backend tests/backend scripts
$env:PYTHONPATH = 'backend'
$env:INTERVAI_BASE_URL = 'http://localhost:3001'
./.venv/Scripts/python.exe scripts/smoke_identity.py
./.venv/Scripts/python.exe scripts/smoke_intelligence.py
./.venv/Scripts/python.exe scripts/smoke_interviews.py
./.venv/Scripts/python.exe scripts/smoke_llm.py
./.venv/Scripts/python.exe scripts/smoke_embeddings.py
./.venv/Scripts/python.exe scripts/smoke_retrieval.py
./.venv/Scripts/python.exe scripts/verify_vision.py
docker exec intervai-sandbox-1 python /opt/runner/verify.py
cd frontend
node --test tests/voice.test.mjs tests/avatar.test.mjs tests/vision.test.mjs
npm run lint
npm run typecheck
node node_modules/next/dist/bin/next build --webpack
```

Machine-readable final backend results: `.local/audit-backend-final.xml`. Full backend summary: `.local/audit-backend-final.log`. These local artifacts may be ignored by Git.
