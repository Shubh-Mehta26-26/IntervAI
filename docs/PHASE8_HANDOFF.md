# Phase 8 handoff — turn-based voice interview

## Scope and implemented behavior

Phase 8 wraps the existing interview engine with speech. Phases 1–7 remain the source of truth for authentication, questions, RAG retrieval, answer evaluation, adaptive decisions, memory, gaps, learning, and retries. There is no second scoring pipeline, knowledge base, vector store, or queue. No Phase 9 work is included.

The room supports question audio, microphone capture during a candidate turn, signal-based VAD, asynchronous transcription, original transcript display, explicit transcript review/editing, submission through the existing answer endpoint, and the next adaptive question. The typed textarea remains available on every voice failure. Nothing submits a transcript automatically. Audio measurements are never sent to the evaluator or used as knowledge evidence.

## Provider architecture and configuration

The existing `LLMProvider.structured()` is the single interface. `GeminiProvider` uses Gemini generateContent with JSON Schema and validated Pydantic output. `OpenAIProvider` continues to use Responses structured output. Configuration selects one vendor; there is no automatic fallback or provider switch. Gemini is the development default in Settings and the example environment.

* Gemini: `LLM_PROVIDER=gemini`, `GEMINI_MODEL`, `GEMINI_API_KEY`.
* OpenAI: `LLM_PROVIDER=openai`, `OPENAI_MODEL`, `OPENAI_API_KEY`.
* `LLM_MODEL` remains a compatibility alias when the selected vendor's model variable is blank. Legacy OpenAI `LLM_API_KEY` remains supported. Vendor-specific model configuration takes precedence.
* The requested conceptual OpenAI model `gpt-5.6-luna` is not assumed to be an available public API model. Configure an account-supported model at final integration; no model name is hard-coded in business logic.
* Embeddings remain independently selected through the existing `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, dimensions and OpenAI credential. Selecting Gemini does not change or replace embeddings.

`SpeechToTextProvider.transcribe(audio)` returns validated `Transcript(text, language?, segments, confidence?)`. Confidence is absent unless supplied; Vosk word confidences remain provider-supplied segment values. Empty, invalid, or failed output never becomes a fabricated answer. Duration comes from actual WAV frames.

* Local STT: `STT_PROVIDER=vosk`, `VOSK_MODEL_PATH` pointing to an installed Vosk language model. Vosk is included in the dependency lock. The adapter starts an isolated subprocess and never downloads a model automatically. Readiness checks model files and the installed package. Docker defaults to `/app/storage/models/vosk`; the model must be placed in that shared storage volume before final verification.
* Cloud STT: `STT_PROVIDER=openai`, `STT_MODEL`, `STT_API_KEY` (or existing `OPENAI_API_KEY`). Uses multipart WAV and JSON transcription; `SPEECH_LANGUAGE` is a configured ISO two-letter recognition hint, not inferred transcript metadata.
* Local TTS: `TTS_PROVIDER=espeak`, `ESPEAK_EXECUTABLE=espeak-ng`, `TTS_VOICE=en`, `TTS_SPEED=1`. Docker installs eSpeak NG. Native Windows needs a locally installed executable or absolute executable path. Text goes over stdin with no shell. Streamed WAV lengths are finalized before validation.
* Cloud TTS: `TTS_PROVIDER=openai`, `TTS_MODEL`, `TTS_API_KEY` (or `OPENAI_API_KEY`), `TTS_VOICE`, `TTS_SPEED`. Uses WAV output from the speech endpoint. The configured cloud voice must be supported by that model; the local `en` voice is not a cloud voice default.

All credentials remain backend-only SecretStr settings. `.env` is ignored; `.env.example` contains blank credential placeholders. Tests inject speech/LLM fixtures directly; no production mock provider is registered. HTTP adapters mask provider errors and never return upstream credentials or raw error bodies. Timeouts, rate limits, authentication failures and malformed output are covered by tests.

Official adapter references: [Gemini generateContent](https://ai.google.dev/api/generate-content), [OpenAI transcription](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create), [OpenAI speech](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create), [Vosk WAV example](https://github.com/alphacep/vosk-api/blob/master/python/example/test_simple.py), [eSpeak commands](https://espeak.sourceforge.net/commands.html).

## Durable state and worker integration

One `voice_sessions` row per existing interview records current question, state, monotonically increasing voice revision, and safe error code. `voice_turns` records each STT/TTS operation, question, original transcript, actual metadata/measurements, provider identity, temporary audio reference, and an optional existing answer link.

States are `idle`, `generating_response`, `playing_response`, `ai_speaking`, `ready_for_candidate`, `listening`, `processing_audio`, `transcribing`, `evaluating`, and `error`. API events enforce transitions and both interview and voice revisions. Polling reconciles the voice state with the current interview question/state. Pause/end/cancel prevents further capture requests or stale speech results from committing.

The existing PostgreSQL `interview_jobs` queue accepts `stt` and `tts` in addition to `plan`/`answer`. The existing worker claims jobs using SKIP LOCKED, leases and claim IDs. Speech processing validates the question and interview revision before and after the provider call. Speech errors affect the voice turn/session and leave the interview waiting for text. Interrupted speech claims can be recovered, with a bounded limit of three recovered attempts; ordinary speech provider errors are terminal for that turn and the user can explicitly retry. A new retry uses a new request key. Duplicate keys return the original operation; changed payloads conflict. Only one pending speech operation per session is accepted.

LLM-generated question text may include a brief neutral transition/acknowledgment through the existing question prompt. There is no hard-coded dialogue or extra LLM system. Simulation prompts prohibit revealing feedback or scores in these transitions.

## Browser capture, playback and VAD

Voice is explicitly enabled. Question playback is attached to a unique completed TTS turn, with replay available; rerenders cannot replay the same operation automatically. Browser autoplay restrictions surface a playback fallback and explicit replay remains available. The visible text question always remains accessible.

The microphone uses getUserMedia and a same-origin AudioWorklet. Only mono input is used, output is silent, and PCM is downsampled to 16 kHz PCM16 WAV. There is no WebRTC/full duplex, MediaRecorder codec dependency, or FFmpeg requirement. The capture lease handles permission denial, duplicate starts, cancellation while permission is pending, stale listening state and stream release. Tracks, nodes and AudioContext are cleaned up on finish/discard/unmount, network loss, device changes and disconnection.

VAD uses RMS signal activity with a noise-adaptive threshold, accumulated active duration and trailing silence. Default minimum active speech is 0.4 s, trailing silence 1.4 s and maximum answer 180 s; settings are `VOICE_MIN_SPEECH_SECONDS`, `VOICE_SILENCE_SECONDS`, `VOICE_MAX_SECONDS`. Silence alone cannot complete a speech turn early; the maximum bounds all recordings. Finish/discard remain explicit controls. The signal meter is throttled to keep the room responsive.

## Transcript convergence and measurements

Typed: textarea → existing AnswerInput → existing InterviewAnswer → existing leased answer job → RAG evaluation → adaptive decision → memory/learning.

Voice: WAV → STT turn → original transcript → reviewed textarea → the same AnswerInput with optional `voice_turn_id` → the same InterviewAnswer and downstream pipeline. The server validates the ready transcript's interview/question ownership and links it atomically with the answer. Reviewed edits are retained in the answer; the original transcript is never rewritten. A PostgreSQL trigger protects persisted original transcript, provider metadata and metrics from later modification. Duplicate answer submissions reuse the existing answer job.

Measurements use actual PCM windows and transcript tokens: response duration, signal-active speech estimate, silence estimate, internal pauses of at least 300 ms, words per active minute, word/character count, configured filler occurrences. The exact calculation method is stored (`pcm_rms_20ms_threshold_0.012`). Default fillers are `um`, `uh`, `you know`; `SPEECH_FILLERS` is configurable JSON. No intelligence, honesty, personality, mental-state or competence inference is made. Background noise can affect amplitude measurements, so these are explicitly estimates rather than semantic speech labels. The filler list should match the deployment language.

## API contract

All paths below are under `/api/v1/interviews/{interview_id}/voice`. Candidate session authentication and interview ownership are required. Mutations require existing CSRF and Origin validation. Responses are no-store; the Next.js proxy permits only these explicit routes and never exposes provider secrets.

| Method/path | Input/result |
| --- | --- |
| POST `/session` | Idempotently enable/retrieve the interview voice session; active interviews only. |
| GET `/status` | State/revisions, readiness, capture settings and newest 20 private turns. |
| POST `/event` | `expected_revision`, `voice_revision`, event `speaking`, `ready`, `listen`, or `abort`. |
| POST `/synthesize` | `expected_revision`, `voice_revision`, `question_id`, `idempotency_key`; queues persisted current question text, never arbitrary client text. Returns 202 turn. |
| POST `/transcribe` | Multipart `file`, `question_id`, `expected_revision`, `voice_revision`, `idempotency_key`; listening required. Returns 202 turn. |
| GET `/audio/{turn_id}` | Own current-question ready TTS WAV before expiry; 410 when expired. Raw candidate audio has no download endpoint. |

The existing POST `/interviews/{id}/answers` accepts optional `voice_turn_id`. Existing typed requests remain compatible. Wrong owner is 404, unauthenticated 401, CSRF failure 403, stale/state/idempotency conflict 409, audio MIME failure 415, invalid WAV/duration 422 and oversized audio 413. The response contains safe metadata, never filesystem paths.

Only mono, uncompressed PCM16 WAV at 16 kHz is accepted for candidate audio. Magic bytes, channel/bit depth, frame completeness, duration and maximum 6 MB are checked server-side. The proxy and ASGI middleware separately bound uploads (6 MB plus multipart allowance) with upload deadlines. Provider output is also bounded and validated. Filenames are ignored; only generated UUID WAV keys can be resolved in the private storage namespace.

## Database migration and privacy

New revision `f7e1aed56edc` follows `66789d3f612f`; previous migrations are unchanged. It adds the two voice tables, FK/unique/check constraints, session index, transcript immutability trigger, and extends the existing job-kind constraint. Account/interview deletion cascades private voice records. Downgrade removes voice records and speech-only jobs, retaining previous-phase tables/jobs.

Candidate WAV files live in `STORAGE_ROOT/voice` only while queued/processing and are removed after STT success/failure/stale processing. No durable recording is enabled. Question TTS is temporary and expires after `VOICE_AUDIO_TTL_SECONDS` (default 600 s). The existing worker sweeps expired files, including cancelled/orphaned uploads. Interrupted processes or cancelled/deleted accounts can leave files until that sweep; stopping the worker delays physical deletion until it resumes. Database references alone never expose files.

Transcripts, reviewed answers and measurement/provider metadata are retained with the private interview history until account/interview deletion. Local Vosk/eSpeak keeps processing local; selecting a cloud speech adapter sends audio or question text to the selected service under its policy. No audio/transcript content is logged by the speech implementation.

## Verification

Deterministic backend tests cover real PostgreSQL migration upgrade → base downgrade → re-upgrade; voice creation, authentication/ownership/CSRF, invalid state and stale revisions, audio type/size/WAV/duration, injected STT/TTS, failures/text fallback, original transcript persistence/immutability, duplicate submissions, linked reviewed answers, reuse of RAG/adaptive evaluation, next question and interview completion, stale jobs, measurements/fillers/pauses, audio expiry, missing configuration and mocked Gemini/cloud provider error contracts.

Frontend Node tests exercise actual capture lease and VAD/WAV utilities with test-only microphone streams: idle rejection, duplicate starts, denied permission, cancellation during permission, release, signal/silence detection, maximum duration and WAV transport. These do not assert physical microphone or real recognition accuracy.

Release verification on this workstation:

| Check | Result |
| --- | --- |
| Full backend regression, including existing phases | **96 passed**, 132.17 seconds; disposable PostgreSQL upgrade → base downgrade → head upgrade included. |
| Final targeted speech/provider recheck | **24 passed**, 46.00 seconds after the final language configuration change. |
| Frontend capture/VAD/WAV tests | **8 passed**, including clipping a worklet block at the configured upload duration. |
| Backend Ruff, frontend lint and TypeScript | Passed without errors/warnings. |
| Native and Docker frontend production builds | Passed. |
| Alembic metadata check | No new upgrade operations detected. |
| Docker services | db, backend, worker and frontend healthy; migrate exited successfully. |
| Readiness and AudioWorklet asset | API readiness, frontend health and `/voice-capture.js` each returned HTTP 200. Docker explicitly copies public assets into the standalone image. |
| Actual local TTS | eSpeak NG generated a 22,050 Hz WAV with 5.992 s of actual audio, processed by the real worker; browser playback returned to Your turn. |
| Browser layout/fallback | Desktop 1280×900 and mobile 390×844 checked; fallback remained visible, typed draft survived and Submit answer stayed enabled. |

[Desktop evidence](verification/phase8/desktop.png) and [mobile evidence](verification/phase8/mobile.png) show a clearly labeled temporary verification question. The QA account, its interview/voice rows and its temporary TTS audio were removed afterward. No real candidate data or fabricated scores were seeded. The temporary browser tab was closed and the viewport override reset.

No live Gemini/OpenAI generation, embeddings, cloud STT/TTS or real Vosk recognition is claimed. Physical microphone capture and recognition accuracy remain a final integration gate; mocked microphone lifecycle and backend transcript convergence have deterministic coverage.

## Known limitations and final integration gate

* No live Gemini/OpenAI request has been made for Phase 8. Final provider credentials and supported model/voice selections remain to be configured in the ignored local environment.
* A real Vosk model is not bundled/downloaded. Local recognition accuracy and language coverage need verification using the installed model and actual speech. eSpeak is intentionally a practical free synthesizer; its voice quality differs from cloud TTS.
* Browser capture needs a secure context (HTTPS or localhost), AudioWorklet and microphone permission. Physical device behavior, browser autoplay, Safari/iOS and noisy-room VAD need final hardware/browser verification. This phase uses turn-based capture, no streaming.
* Signal activity is an amplitude estimate; filler detection is lexical/configured. Neither affects scores.
* Database queue has no separate speech pool; one long speech job temporarily occupies the existing worker. Speech deadlines are bounded; worker health tolerates this budget.
* Temporary cleanup needs the worker running. There is no product recording retention switch.

## Startup and test commands

From the repository root, initialize the ignored environment with the existing setup script if needed, configure provider/model variables locally, then:

```powershell
docker compose up -d --build
docker compose ps
```

Compose runs the new migration before backend/worker start and installs local speech dependencies. Keep the configured ports from `.env` (this workstation uses frontend 3001/API 8001/PG 5434). The native flow is unchanged: activate `.venv`, install backend locked dependencies, run `python -m alembic -c backend/alembic.ini upgrade head`, start the API and `python -m app.worker`; run the frontend npm dev command separately. Native local TTS also needs eSpeak installed.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/backend -q --tb=short --basetemp=.local/phase8-check-new
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini check
.\.venv\Scripts\python.exe -m ruff check --config backend/pyproject.toml backend tests/backend/test_voice.py
cd frontend
npm run test:voice
npm run lint
npm run typecheck
npm run build
```

Use a fresh basetemp directory for each run. Backend tests create/drop their own disposable database and do not migrate/downgrade the application database.

Phase 9 remains untouched.
