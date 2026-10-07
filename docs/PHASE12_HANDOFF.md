# Phase 12 handoff

Phase 12 adds evidence reports, analytics, candidate-consented recruiter review, and administrator operations on top of the Phase 11 implementation. It is a final integration phase; do not begin a Phase 13 task from this handoff.

## Delivered

- Completed interview reports are built from persisted questions, answers, evaluated dimensions, grounding sources, adaptive decisions, coding aggregates, voice measurements, visual event metadata, learning/gap progress, and the latest career snapshot. Report content is a versioned immutable JSON snapshot. A fingerprint makes a repeated generation idempotent until source evidence changes; updated source evidence creates a later version.
- PDF downloads are rendered from the stored snapshot using the Python standard library, so PDF output does not require a runtime package or network installation. The output includes evidence, dates, descriptive dimensions, and limitations. It excludes API keys, contacts, raw audio/video, source code, hidden coding cases, and hidden reference solutions.
- Candidate analytics only query the signed-in candidate's persisted completed interviews, evaluated answers, learning plans/items, and active knowledge gaps. Empty history returns an explicit `insufficient_data` state. Dimension averages are descriptive answer evidence, never a hiring score.
- Recruiters can create and manage their own job postings. Candidate application requires an explicit consent checkbox and an analyzed candidate-owned copy of the exact current job description. Candidate account details, the selected resume/match, and job-linked completed reports are returned only in that recruiter-owned application scope. Candidates may withdraw; job content locks after the first application to keep the consent basis stable.
- Admin-only readiness lists database, worker, queue, provider names/readiness, vision, and sandbox status without returning credentials. Role changes are CSRF-protected and audit logged. The final active administrator cannot be removed or demoted. Audit entries are append-only.
- Worker heartbeat is stored in PostgreSQL, because container-local temporary files are not a valid cross-container health signal.
- Role assignment is deliberately excluded from registration. Use the trusted operator CLI against an existing account: `./.venv/Scripts/python.exe scripts/set_user_role.py user@example.com recruiter` or `admin`.

## Routes

Candidate: `GET /reports`, `POST /reports/{interview_id}/generate`, `GET /reports/{report_id}`, `GET /reports/{report_id}/pdf`; `GET /analytics/overview`, `/analytics/skills`, `/analytics/learning`; `GET /applications/jobs`, `GET /applications`, `POST /applications`, and `PATCH /applications/{application_id}` to withdraw.

Recruiter: `GET/POST /recruiter/jobs`, `PATCH /recruiter/jobs/{job_id}`, `GET /recruiter/jobs/{job_id}/applications`, `GET /recruiter/applications/{application_id}`, and application-scoped report JSON/PDF reads under `/recruiter/applications/{application_id}/reports/{report_id}`. Mutations require CSRF and an allowed Origin.

Admin: `GET /admin/system-status`, `GET /admin/users`, `GET /admin/audit`, and CSRF-protected `PATCH /admin/users/{user_id}/role`.

## Storage and integrity

Migration `9ad2c4f7b611_phase12_reports_recruiting` follows `6180c9689cfe`. It adds owner-bound report/version rows, recruiter postings/applications, append-only admin audit, and worker heartbeat tables; it adds composite owner keys for existing interviews and job targets. Report versions and audit rows are immutable by database trigger. Prior migrations remain unchanged.

## Verification

The Phase 12 focused test checks readable PDF output, empty-state analytics, candidate authorization boundaries, and report generation CSRF/ownership behavior. The disposable PostgreSQL fixture upgrades, downgrades, and re-upgrades all migrations. Frontend pages are included in typecheck/lint/build. See `docs/FINAL_INTEGRATION.md` for final suite results and remaining provider/hardware gates.

## Limits and next operator steps

Live provider credentials and physical microphone/camera permission checks are deployment/operator gates, not simulated as passed. Sandbox readiness reflects the configured service health endpoint; it does not run candidate code. Role assignment is a privileged local operation. This phase was not deployed or published.
