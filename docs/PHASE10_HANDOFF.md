# Phase 10 handoff — optional visual observations

Phase 10 adds an optional camera sampler, actual self-hosted computer vision, durable temporal aggregation, and an owned chronological interview timeline. Phases 1–9 remain in place. No Phase 11, recruiter dashboard, career advisor, or final PDF reporting was started.

## Implementation and boundaries

The flow is browser camera → bounded JPEG samples → authenticated multipart API → local OpenCV detector → temporal aggregation → PostgreSQL integrity events → interview timeline. `VisionPanel` lives in the existing interview room alongside the independent voice controls, question/answer workspace, progress, and coding UI. Capture starts only after an explicit click and browser permission. Preview and active/inactive status are visible. Camera capture requests **video only**; it does not take over the microphone.

Detection is implemented in `backend/app/providers/vision.py`, aggregation/ownership/leases in `backend/app/services/vision.py`, and routes in `backend/app/api/vision.py`. Inference runs outside database locks in a thread. A nonblocking admission lock permits one inference per API process and drops competing samples before executor submission. The browser also permits one outstanding sample, drops extra timer ticks, and has a ten-second request deadline. No frame queue or frame retry backlog is created. Horizontal deployments would need an explicit shared admission/scheduling policy; the current deployment has one API process.

The existing worker performs bounded maintenance of enabled sessions. It closes abandoned/inactive sessions without processing frames. A processing claim expires after ten seconds; a later frame can reclaim it. Session revisions and sequences reject stale sessions, old responses, and replays. Late inference cannot write events after a session revision/state change. The fixed model ordinarily completes in a few hundred milliseconds in this environment; the thread itself has no hard process-kill timeout. Worker maintenance is opportunistic between existing jobs, so ten seconds is an abandonment threshold, not a guaranteed cleanup deadline.

Visual observations never enter answer evaluation, adaptive difficulty decisions, candidate skill/memory evidence, knowledge gaps, or learning plans. `context_snapshot` contains the ordinary interview configuration, never these event rows. There is no automatic penalty, disqualification, or hiring score. The structured timeline/API is ready for a future separately designed report integration.

## Models, licenses, and actual capability

Runtime: OpenCV headless **4.12.0.88**, NumPy **2.2.6**, Pillow **12.3.0**, with regenerated runtime/development lock files. Local detector: TensorFlow model-zoo **SSD MobileNet V2 COCO, 2018-03-29**, 300×300 model input. It consumes only COCO person and cell-phone classes. Boxes are discarded; only count/presence and actual model box scores reach aggregation.

OpenCV is Apache-2.0, NumPy BSD-3-Clause, and Pillow HPND. The TensorFlow Models research provenance/license is Apache-2.0. Publisher license files accompany the weights. See [asset provenance and license details](../vision/NOTICE.md) and [fixture attribution](../tests/fixtures/vision/ATTRIBUTION.md). The generated OpenCV Extra graph description has no independent top-level repository license file; its exact provenance is documented rather than asserting a blanket license over unrelated test data. Review model/dataset/image redistribution rights before a production redistribution. No COCO training images, AGPL YOLO code, or paid vision API are included.

Setup downloads from official publisher HTTPS sources with certificate verification, checks upstream archive/member digests and the graph-description SHA-256, extracts only the named regular model file, and retains notices. Validated weights are cached on repeated setup. Models are installed explicitly, never downloaded during inference. Docker packages them under `/opt/vision`, owned by root and not writable by the non-root application user.

This is **person-based presence detection**, not facial identity or verified candidate identity. A person can be occluded, outside the crop, or missed. A detected phone is not necessarily being used or prohibited by a particular interview policy. Head pose, gaze/looking direction, face recognition, demographic/emotion/personality/attention/intelligence/intent inference are not implemented. Browser device-orientation notices are optional, unverified device events; they do not prove camera direction or head orientation.

## Event taxonomy and aggregation

| Event | Confirmation / source | Confidence | Neutral severity |
| --- | --- | --- | --- |
| `CANDIDATE_PRESENT` | Person detections over 2 seconds; also recovery after absence | Actual person box score | INFO |
| `CANDIDATE_ABSENT` | No person detection over 3 seconds | null | NOTICE |
| `MULTIPLE_PERSONS_DETECTED` | More than one person over 2 seconds | null; box scores are not count confidence | REVIEW |
| `PHONE_DETECTED` | Phone detections over 2 seconds | Actual phone box score | REVIEW |
| `CAMERA_INTERRUPTED` | Server sampling gap or explicitly browser-reported interruption | null | NOTICE |
| `CAMERA_ORIENTATION_CHANGED` | Explicit browser device-orientation notice | null | INFO |

Default score threshold is **0.55**, sample interval **1000 ms** (configurable 500–2000), confirmation **2000 ms** and absence **3000 ms**. An episode creates one event after confirmation, updates its observed duration, and closes at the last supporting observation. Single noisy samples do not produce detection events. Gaps longer than four seconds break continuity and create a separately attributed sampling interruption. Detector failures also break continuity; failure is never converted into absence. Inactive sessions or sampling stopped for over ten seconds are closed by worker maintenance, including sessions that never sent a first frame.

Server timestamps define event times. Client capture timestamps only reject samples more than five seconds away from server time; they are not trusted evidence. A consolidated sampling-gap duration describes the transport gap, not proof that a physical camera was unavailable throughout it. Abandonment notices have zero duration rather than inventing duration for an unobserved period. Browser notices are labelled `client_reported_unverified` and debounced for five seconds. Model events are `server_inference`; gaps are `server_observed_sampling_gap` with `not_camera_proof=true`. Scores are labelled model scores in the UI and are not calibrated misconduct probabilities. At most **300 events per interview** are retained; reaching the cap disables monitoring with an explicit status.

## Security, privacy, retention, and configuration

Every route requires the existing candidate session and interview ownership. Mutations require existing CSRF/origin checks. Other candidates receive 404; anonymous access receives 401. Clients cannot submit arbitrary detector event types or confidence. The notice endpoint accepts only two explicitly unverified browser notices.

Frames are limited to **128 KiB**, JPEG/PNG matching actual format, a single image, and dimensions **32–640** per side. API and frontend proxy bound the entire multipart body (128 KiB plus 8 KiB envelope) before parsing. Submitted filenames/paths are ignored. Frames of this size remain below the multipart spool threshold; no candidate image file is written. Decoding/inference are temporary in memory; no raw image, video, snapshot, bounding box, face embedding, or frame payload is stored in database/jobs/logs. Public development fixtures are retained separately with attribution and are not candidate recordings.

Only sessions, safe observation metadata, and events are retained. Events currently follow the owned interview's lifetime and cascade on interview/candidate deletion; there is no independent event TTL. `MEDIA_RETENTION_DAYS` governs existing media and does not pretend to delete these structured event rows. Production retention policy can extend that existing lifecycle explicitly.

`VISION_ENABLED=false` is the default and the existing local configuration was preserved. Feature availability does not automatically acquire a camera. `InterviewCreate.vision_enabled` can independently disable the optional feature per interview; `vision_phone_enabled` independently disables phone event generation (the only supported object class). Sessions always start disabled; required-camera policy is not implemented. Missing models, denied/revoked permission, unsupported browsers, missing/busy devices, detector failures, or a disabled feature leave the interview usable. Stop, hidden tab, pause/end state, and unmount release camera tracks and abort uploads. Late permission grants are stopped immediately after cancellation. Server maintenance closes records if the browser disappears.

Non-secret settings: `VISION_ENABLED`, `VISION_MODEL_DIR` (native default `vision/models`; Docker `/opt/vision`), `VISION_SAMPLE_INTERVAL_MS`, `VISION_DETECTION_THRESHOLD`, `VISION_ABSENCE_MS`, `VISION_CONFIRMATION_MS`. Local CV needs **no external credential**. Existing OpenAI `gpt-6-luna` primary, Gemini alternative, embeddings/pgvector, speech providers, and isolated coding execution remain independently configured. No secret was printed or added to tests/docs/frontend; ignored `.env` credentials were not changed. Remaining live OpenAI/embedding/speech credentials belong to final integration.

## Database and API

New migration **`3ebc31f2890a`**, after `15bfe6482fef`, adds `vision_sessions` (one per interview; enable/revision/sequence/claim/error/aggregation state) and `integrity_events` (candidate/interview/session, controlled type/severity, timestamps/duration, nullable confidence, detector, safe JSON metadata). There are candidate, interview/time, and event-type/time indexes, enum/range/time checks, and cascading foreign keys. Prior migrations were not edited. No frame columns or skill relationships were added.

| Method | `/api/v1` route | Purpose |
| --- | --- | --- |
| GET | `/interviews/{id}/vision/status` | Availability, optional policy, sampling settings, current session, timeline |
| POST | `/interviews/{id}/vision/session` | Enable/disable using `enabled`, `expected_revision` |
| POST | `/interviews/{id}/vision/frame` | Multipart `revision`, `sequence`, `captured_at`, `image`; server inference only |
| POST | `/interviews/{id}/vision/notice` | `revision` plus `interrupted` or `orientation_changed`; unverified provenance |
| GET | `/interviews/{id}/integrity-events` | Chronological owned event data and limitations note |

The frontend same-origin proxy explicitly permits only these operations. Arbitrary `/vision/events` submissions remain unavailable. API status/errors distinguish disabled, unavailable, stale, rate-limited, and busy conditions.

## Verification and limitations

Final verification: **136 backend tests passed**, including **20 Phase 10 tests** and every existing Phase 1–9 test, in a real disposable PostgreSQL database. The fixture verified upgrade → base downgrade → re-upgrade, and metadata consistency; native Alembic check reported no new upgrade operations. Backend lint passed using the repository's `backend/pyproject.toml` configuration. **13 frontend tests passed** (8 existing voice, 5 new camera/sampling); frontend lint and TypeScript passed. Production frontend and backend/worker Docker builds passed. **29 actual Linux sandbox checks passed** again. API, worker, frontend, PostgreSQL, and sandbox health were checked; the migration container exited successfully.

Tests cover image content/MIME/dimensions/size, confidence validation, optional/global/per-interview disabled modes, ownership/auth, replay/stale/rate/busy samples, admission without queued inference, model failure and expiring claims, all detection event types, debounce/durations/recovery, phone policy, abandoned sessions including no first frame, unverified controlled/debounced notices, and pause/resume/completion. Confirmed visual episodes leave evaluation, adaptive decision, memory evidence, gaps, and learning tables unchanged. Camera tests cover video-only acquisition, track release, late permission cancellation, denied/missing/busy device messages, and dropping 100 slow-inference samples without backlog.

Real local model fixtures passed for one person, a blank frame, a two-person composition, and a visible phone. [Measured results](verification/phase10-cv-fixtures.jsonl) report actual scores and inference time. A separate phone photo was missed during exploration; the retained positive phone fixture scores approximately **0.58**, close to the threshold. These four fixtures demonstrate functionality, not a representative accuracy benchmark. The two-person fixture is a labelled composition of a public NASA portrait. Low light, occlusion, crops, small phones, device performance, and an older COCO detector can cause both false positives and false negatives.

The deployed frontend proxy/API and packaged Docker detector processed repeated real fixtures at the configured cadence, persisted five consolidated events (including presence recovery), and returned the same timeline: [API evidence](verification/phase10-api-fixtures.json). The interview question/context was explicitly seeded for this disposable QA account; no live LLM result or physical webcam success is claimed. [Desktop](verification/phase10-desktop.jpg) and [mobile](verification/phase10-mobile.jpg) show the actual persisted timeline with camera inactive. Viewports 1280px and 390px had document widths 1265px and 375px, respectively, with no horizontal overflow. The successful pause/resume path was rechecked after the compatibility fix. The [disabled-feature view](verification/phase10-disabled.jpg) retained the timeline and typed interview workspace with the enable control disabled. Both agent-created disposable QA accounts and their linked records were removed, the QA browser was signed out/closed, and API/worker were recreated with the preserved local vision-disabled configuration. Browser permission mechanics were exercised with frontend test doubles; **physical webcam/permission/preview/end-to-end device testing remains pending final integration**.

A real pause check exposed a pre-existing async serialization issue after `updated_at` expired on a committed update. Interview output now explicitly refreshes expired ORM fields before serialization, so pause/resume/complete return their committed state. This small compatibility fix is regression-tested with the optional-camera lifecycle.

Browser frames/notices are not hardware-attested; a hostile client can supply an image or omit samples. Server inference ensures that the detection score comes from the supplied image, not that it came from a physical live webcam. Do not use these observations as proof of misconduct or identity. Production resource/rate/retention policy and broader representative model evaluation remain deployment work.

## Startup and final integration

From the workspace root, install the local models before the first Docker build:

```powershell
.\.venv\Scripts\python.exe scripts/setup_vision.py
docker compose up -d --build
docker compose ps
```

To make the optional controls available, set the non-secret `VISION_ENABLED=true` locally and recreate the backend/worker. For a temporary process-level override without editing `.env`:

```powershell
$env:VISION_ENABLED='true'
docker compose up -d backend worker
Remove-Item Env:VISION_ENABLED
```

The container keeps the value it started with until recreated. Default configuration remains disabled. The verified local frontend/API ports are `http://localhost:3001` and `http://localhost:8001`. Camera APIs require localhost or a secure HTTPS context.

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe scripts/verify_vision.py
.\.venv\Scripts\python.exe -m pytest tests/backend -q --basetemp=.local/phase10-next-run
.\.venv\Scripts\python.exe -m ruff check --config backend/pyproject.toml backend tests scripts
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini check
docker compose exec -T sandbox python /opt/runner/verify.py
```

From `frontend`, use `npm run lint`, `npm run typecheck`, `npm run test:voice`, `npm run test:vision`, and `npm run build`. Use a fresh pytest basetemp path. At final integration, verify a physical camera grant/denial/revocation, preview, stop/hidden-tab cleanup, microphone independence, representative lighting/framing, and real device orientation where supported. No additional CV API key is required.

Stop after Phase 10; Phase 11 remains unstarted.


## Subsequent Phase 11 status

This file records the Phase 10 acceptance boundary as it stood at handoff. The user subsequently authorized Phase 11, which is now implemented and documented in [Phase 11 handoff](PHASE11_HANDOFF.md). The historical Phase 10 stop instruction was superseded by that request; Phase 12 remains unstarted.
