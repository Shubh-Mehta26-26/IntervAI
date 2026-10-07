# Final integration checklist

This checklist closes the Phase 12 implementation while keeping environment-dependent verification explicit.

## Local startup

1. Preserve the existing `.env`; do not paste or print provider keys into logs or issue reports.
2. Start services with the documented Docker Compose or native workflow in `README.md`.
3. Apply migrations with `./.venv/Scripts/alembic.exe -c backend/alembic.ini upgrade head`.
4. Provision trusted recruiter/admin accounts from an operator shell using `scripts/set_user_role.py` after account creation. Public registration always assigns candidate role.
5. Open candidate analytics/reports/opportunities; complete an interview to generate a report. Use separately provisioned recruiter/admin accounts to verify their role-specific pages.

## Verification completed in Phase 12

- Full backend suite: **163 passed** against the disposable PostgreSQL fixture. Phase 12 includes a candidate→interview→report/PDF→consented application→recruiter PDF→withdrawal flow.
- Frontend `typecheck`, `lint`, and production `build` passed. Existing voice and vision browser tests passed (8 and 5 tests).
- Additive migration applied to local development database; Alembic metadata check reports no pending schema changes.
- Phase 12 backend tests cover report PDF parsing/text, persisted-data empty states, cross-role denial, and CSRF/ownership checks.
- Frontend route build/typecheck/lint and existing voice/vision tests cover integration of the new pages and proxy routes.
- Existing local API liveness/readiness and frontend root returned HTTP 200. These were health checks only; services were not rebuilt or restarted for this implementation.
- Docker Compose configuration validation could not run: Docker was absent from `PATH`, and Windows denied starting the installed per-user executable. No deployment was attempted.
- Backend suite runs against a uniquely named disposable PostgreSQL database, never the configured development database. On restricted Windows workspaces pass `--basetemp=.local/pytest-phase12` so pytest temp files stay inside the writable project root.
- Docker Compose deployment, external publication, and production migration were not performed.

## External/provider and device gates

- LLM interview generation/evaluation, embeddings/pgvector retrieval, cloud STT/TTS, and camera permission/device behavior depend on local provider credentials and installed optional models. The admin page reports configuration/readiness but never emits credentials.
- On 2026-10-04, the local Gemini configuration passed real structured-output LLM checks, 1,536-dimensional document/query embedding checks, ingestion of four curated sources, retrieval of the expected transaction source, and the complete synthetic interview journey through the frontend proxy. The Gemini embedding adapter and source re-ingestion on provider/model changes are covered by the focused knowledge tests (10 passed); focused resume and knowledge tests together passed (18). Frontend typecheck/lint passed. Gemini's free-tier rate limit returned HTTP 429 once during these checks; the worker now retries embedding-limited jobs after 60 seconds, and a later retrieval check passed. These checks used synthetic data and do not establish production quota or privacy suitability.
- The sandbox is checked through its health endpoint. A complete stack check should also run the existing isolated-code security smoke tests on a Linux host with supported rootless namespaces and Landlock; Windows cannot validate those kernel controls.
- Browser microphone and camera flows require a human browser permission/device check. Camera stays opt-in, video-only, and never produces a hiring score.

## Privacy and scope checks

- Candidate application consent appears before application data is shared. Withdrawn applications leave recruiter active-applicant views.
- Recruiter routes scope every application, candidate, report, and PDF through the authenticated recruiter's own posting and the candidate's exact analyzed job copy.
- Report versions and admin audit history are append-only. Reports contain summarized coding outcomes, never code or hidden cases.
- Admin status uses safe provider labels/readiness only; keys and raw configuration values stay server-side.
