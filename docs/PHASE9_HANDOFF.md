# Phase 9 handoff — coding interviews and isolated execution

## Delivered scope

The coding interview plugs into the existing interview planner, question state, answer evaluator, adaptive rules, RAG, candidate memory, gaps, learning roadmaps, and retry comparisons. The PostgreSQL leased `interview_jobs` queue remains the only durable queue. Phases 1–8 are retained. No Phase 10, computer vision, career advisor, or recruiter module was added.

Flow: authenticated candidate → validated structured problem → CodeMirror editor → public Run / final Submit → existing worker → dedicated sandbox service → real compiler/runtime tests → persisted safe result → existing answer evaluation plus estimated complexity → existing adaptive decision → existing memory/gap/learning services.

The shipped languages are Python 3.12, C++17 (GCC 12), and Java 17. All three were actually compiled/executed in the sandbox. The browser exposes languages only when the sandbox security readiness probe succeeds and the problem has passed reference validation for its supported languages.

## Problems and editor

Six original curated problems cover arrays, hash tables, and binary search, with two difficulty levels per topic: Ledger balance, Peak ledger balance, Repeated sensor labels, Most frequent label count, First reading at threshold, and Readings within threshold. These were authored for this project; no published collection was imported. Curated problems are preferred to generated problems.

Problems have separate title, description, difficulty, topic, skills, constraints, input/output format, examples, starter code per language, supported languages, limits, provenance, validation status, reference implementations, and test rows. Public cases are serialized explicitly. Hidden cases and reference implementations are never included in candidate DTOs.

Candidate-authored and personalized AI-generated problems start as drafts. Generation reuses the selected `LLMProvider`, existing candidate/job/memory/interview context, and `ProblemInput` validation. Reference implementations for every advertised language must compile and pass all public and hidden cases in the real sandbox before the problem is eligible for selection. Compiler commands, paths, supported language identifiers, source/output limits, and resource limits are application-controlled. A generated reference implementation is treated as untrusted code.

Validation establishes internal consistency against the supplied finite suite. It is not a proof that an AI-authored statement, reference algorithm, or suite is mathematically complete. Curated review and broader test coverage remain important when expanding the collection.

The room uses CodeMirror with Python/C++/Java highlighting, line numbers, indentation, per-language drafts, starter reset, source size checks, approach explanation, Run, final Submit, Stop, public diagnostics, measured summaries, saved source history, and explicitly estimated complexity. Desktop uses problem/editor columns; mobile stacks them. Submission history remains accessible after completion. Final Submit advances the interview after judgment; use Run for iterative revisions.

## Execution service and ephemeral isolation

The API and worker make HTTP requests only. They do not import the sandbox supervisor, launch candidate subprocesses, invoke a shell, access the Docker daemon, or evaluate candidate source. All compiler/runtime process creation occurs inside the dedicated `sandbox` Docker service.

Each compiler and each individual test receives fresh Linux user, PID, network, and mount namespaces through the trusted C guard. These namespaces are short-lived containers within the dedicated service. Candidate processes run as UID/GID 10001, are PID 1 in their private PID namespace, and have zero effective, permitted, inheritable, and bounding capabilities. The trusted guard maps only its own unprivileged outer UID/GID and drops its temporary namespace capabilities before forking/executing the compiler/runtime. There is no privileged Docker container or host capability grant.

The outer Docker service is reused; the implementation does not create/delete a Docker-daemon container object for every submission. Isolation per execution comes from fresh kernel namespaces, irreversible file/syscall restrictions, and job storage cleanup. This avoids a Docker socket or Docker-control API in the application. The mount namespace initially inherits the service's read-only image mounts; Landlock supplies the per-job filesystem boundary. There is no separate VM or independent kernel per submission.

The outer seccomp profile vendors Docker's default profile and adds only `unshare(USER|PID|NET|MOUNT)` with that exact flag value for the trusted guard. It retains the default-deny action and all other Docker rules. After setup, the child filter unconditionally denies `unshare`, `setns`, and mount operations. Upstream license is retained in `sandbox/MOBY_LICENSE`.

Startup/readiness fails closed unless namespace creation, non-root mapping, capability removal, Landlock ABI ≥3, seccomp setup, and the required binaries succeed. Do not remove these checks or enable a host-code fallback when deploying to an incompatible kernel.

## Security controls

| Boundary | Implemented control |
|---|---|
| Network | Fresh network namespace; socket/connect/bind/listen/accept denied by child seccomp. Only anonymous AF_UNIX socketpairs needed by Java file channels are allowed; they cannot address another process. Docker service is on a private internal network with no published host port. |
| Files | Landlock allows read/execute for installed runtimes/libraries and narrowly required Java/loader configuration, plus access to the generated job directory. `/proc`, `/etc/passwd`, supervisor source/config, other job directories, application files, and host files are unavailable to candidate code. Traversal and symlinks cannot broaden the allowlist. |
| Privilege | UID/GID 10001; Docker `cap_drop: ALL`; no-new-privileges; child capabilities removed; no Docker socket; no host directory mounts; read-only image. |
| Processes | Private PID namespace; runtime fork/vfork/process-clone denied. Java thread clones are allowed with process/thread limits. Compilers may spawn required compiler subprocesses under the same namespace, filesystem, resource, and network restrictions; Java annotation processing is disabled. |
| Supervisor protection | Cross-process signal, ptrace, process-memory, namespace, mount, process-group escape, BPF, io_uring, and selected privileged interfaces denied. Java thread signals are limited to the child's own thread group. |
| CPU/time | Outer 1 CPU; per-process CPU rlimit; wall-clock supervisor deadline; fixed 15-second compilation deadline; test limits 100–3000 ms. |
| Memory | Process address-space rlimit; supervisor monitors the process tree's RSS; JVM uses bounded heap/metaspace/class/code caches and a larger address-space allowance for JVM reservations; outer 512 MB hard limit. |
| Output/files | stdout and stderr capped independently at 32768 bytes; per-file size 16 MB; tmpfs 128 MB; source 32768 UTF-8 bytes; at most 20 bounded test cases; fixed source names and compiler arguments. |
| Cleanup | Kill monitored process group on stop/error/timeout/output limit and after completion; private PID namespace destruction terminates remaining descendants; iterative cleanup avoids symlink following and restores directory permissions after hostile chmod. Temporary directories are removed on every completed/error/cancelled execution. Container recreation clears tmpfs after a service crash. |
| Secrets | Fresh child environment contains only fixed PATH/LANG, job-local HOME/TMPDIR, and Python bytecode configuration. Database, auth, AI, speech, and runner keys are not inherited. Logs never include source, test content, or request headers. |

Landlock is a file-content/access boundary, not a complete filesystem-metadata hiding system. Readable installed runtime files are shared immutable resources. Candidate code can replace its executable with another allowed executable, but restrictions remain inherited; process spawning and addressable networking remain denied. Rootless namespaces, seccomp, and the kernel are part of the trusted computing base. This has not undergone an independent sandbox penetration audit and should not be presented as a VM-grade or large-scale public multi-tenant execution platform. Compiler vulnerabilities and shared service resource exhaustion remain material considerations.

## Durable states, correctness, and cancellation

Execution states: `QUEUED`, `RUNNING`, `COMPLETED`, `COMPILE_ERROR`, `RUNTIME_ERROR`, `TIMEOUT`, `MEMORY_LIMIT`, `OUTPUT_LIMIT`, `SYSTEM_ERROR`, `CANCELLED`.

Submission states: `SUBMITTED`, `JUDGING`, `ACCEPTED`, `WRONG_ANSWER`, `PARTIAL`, `ERROR`. Acceptance means the entire selected test suite passed. Partial indicates some cases passed. Runtime/compile/resource failures remain explicit execution states. An address-space allocation failure may raise a controlled runtime exception before RSS exceeds the memory limit; it is therefore a `RUNTIME_ERROR`, not a fabricated `MEMORY_LIMIT` classification.

Run judges only public tests and returns bounded per-case stdout/stderr. Submit judges public and hidden tests and persists only safe aggregate counts/metrics. Hidden stdout, stderr, inputs, expected values, and individual outcomes are withheld even when a candidate deliberately echoes stdin. Compile diagnostics can be returned because compilation occurs before any hidden stdin is supplied; job paths are sanitized.

`execution_time_ms` is measured supervisor wall time summed across executed test processes; compile failure reports measured compilation time. `memory_kb` is Linux `wait4` peak RSS, including launcher/runtime startup; it is not a precise algorithm-only allocation figure. Successful judging metrics exclude successful compilation. Missing measurements remain null. Backend typed validation rejects invalid state/count/metric contracts.

Every final judged attempt except system failure/cancellation becomes an existing `InterviewAnswer` and `answer` job. The original source stays in `CodingSubmission`; the evaluator receives it as untrusted DATA alongside constraints, explanation, safe execution facts, and existing RAG references. Correctness is enforced in application code as `tests_passed/tests_total`, including on cached evaluations, before adaptive decisions and persistence. The candidate feedback states measured correctness deterministically. LLM output cannot change it. Complexity, edge-case reasoning, and code quality are stored separately with provider/model metadata and an explicit estimate label. They are not measured runtime metrics.

Existing memory policy receives actual coding topic/skill outcomes. Execution can ground suite performance without a RAG citation; unsupported qualitative weakness/misconception strings are not promoted as execution-grounded claims. Confidence thresholds, root-question correlation, simulation publication, and repeated-evidence gap thresholds remain the existing policy. One failed submission does not immediately create a confirmed knowledge gap. Off-by-one causes are not inferred from test counts alone.

Existing learning plans/practice remain intact. Retry from coding evidence creates a coding interview, uses the existing planner/worker/comparison pipeline, and excludes earlier problem titles from the eligible validated collection. If no fresh eligible problem exists, selection stops rather than pretending an identical problem is a new independent check. Expand validated problems for broader retry coverage.

Candidate/interview locks serialize execution creation. UUID idempotency keys and payload fingerprints protect retry/replay; a changed payload under the same key returns 409. Another active execution on the question prevents conflicting work. Equal concurrent requests share one submission/job. Worker claims, expected revisions, and current-question checks prevent stale work from advancing an interview. The runner also caches bounded UUID results for worker lease retries. This cache is volatile; after a runner restart an interrupted execution can be safely re-executed, while submission/answer effects remain deduplicated in PostgreSQL.

Stop persists cancellation first. Queued jobs are cancelled immediately; a running worker observes it and signals the runner, which terminates the process group and cleans up. Revision changes such as pause/cancel/completion similarly invalidate running work. Independent hard deadlines remain effective if cancellation transport fails. System/lease exhaustion leaves the coding question available for retry and never fabricates an answer.

## Database and API

Migration `15bfe6482fef` follows `f7e1aed56edc`; previous migrations were not edited. It adds:

* `coding_problems`: structured content, ownership/global curated scope, provenance, reference validation and languages/limits.
* `coding_test_cases`: ordered public/hidden input/expected rows.
* `coding_submissions`: candidate/interview/question/problem/existing-job links; optional existing-answer link; original source/explanation/language/mode/number; replay hash/key; persisted state, safe results, and estimated analysis.
* Optional `interview_questions.coding_problem_id`; `coding` interview type; `coding` and `coding_validate` existing job kinds.
* Uniqueness, range/state/source-byte checks, indexes, and a trigger prohibiting edits to submission source/identity fields. Status/result/analysis may advance without overwriting prior attempt source. Ownership is enforced across each API relationship.

Authentication applies to every API below; mutations also require existing CSRF/origin checks. Private problem/submission IDs owned by another candidate return 404. The frontend proxy uses an explicit allowlist.

| Method | `/api/v1` path | Purpose |
|---|---|---|
| GET | `/coding/provider` | Security readiness and working languages |
| GET / POST | `/coding/problems` | Safe collection / create typed private draft |
| GET | `/coding/problems/{id}` | Safe structured problem |
| POST | `/coding/problems/generate` | Personalized typed draft, queued reference validation |
| POST | `/coding/problems/{id}/validate` | Queue validation through an owned interview |
| POST | `/interviews/{id}/coding/run` | Public judging |
| POST | `/interviews/{id}/coding/submit` | Final public+hidden judgment |
| GET | `/interviews/{id}/coding/submissions` | Owned immutable-source history |
| GET | `/coding/submissions/{id}` and `/status` | Persisted owned state/result |
| POST | `/coding/submissions/{id}/cancel` | Persist stop request |

Existing interview create/start/detail/transition/answer-summary APIs are reused. Create supports `interview_type="coding"` and optional `coding_problem_ids`. Run/Submit require `question_id`, `expected_revision`, `idempotency_key`, `language`, `source_code`, and optional `explanation`. Generate/validate accept an owned `interview_id`, `topic`, and `difficulty`. Typed-answer bypass is rejected for coding interviews. Personal problem count is bounded at 30; attempts per question at 60. List/history responses are bounded.

## Verification actually performed

After the latest OpenAI-primary specification update, all **116 backend tests** were rerun and passed in 158.09 seconds, all **8 frontend voice tests** passed, and all **29 real sandbox checks** were rerun successfully. Lint, TypeScript, production Docker image builds, Alembic schema checks, and final service health passed. The saved desktop/mobile/completion evidence remains from the previously verified, unchanged coding UI; no fresh live OpenAI UI journey is claimed.

* Full backend suite: **116 passed**, including **20 Phase 9 tests**, previous Phase 1–8 tests, a real PostgreSQL disposable database, head→base→head migration cycle, and model metadata comparison.
* Phase 9 checks cover typed/byte limits, private creation, generated draft/reference validation, bad references, auth/ownership, replay/conflicts, actual concurrent Submit requests, persisted states, hidden-output filtering, source immutability, stale jobs, cancellation, lease exhaustion, authoritative correctness despite a deliberately high LLM score, adaptive progression, memory evidence, repeated coding gap confirmation, learning roadmap creation, and fresh coding retry.
* Existing frontend voice suite: **8 passed**. Frontend lint, TypeScript, production Docker build, backend lint, and Alembic schema check passed.
* Real Linux sandbox suite: **29 checks passed**. Python/C++/Java correct programs passed; Python loop timed out; memory allocation failed in a controlled runtime error; network/non-Unix socketpairs/file/proc access were blocked; namespace escape and cross-process signalling were blocked; actual non-root/PID isolation and zero capabilities were checked; fork/fork bomb/shell spawn/output/source/path attacks were controlled; compile/runtime errors persisted; cancellation, replay caching, hostile chmod cleanup, and directory cleanup passed.
* Saved actual execution records: [sandbox verification JSONL](verification/phase9-sandbox.jsonl). `COMPLETED` for a blocking probe means the program caught the denied operation and produced the expected `ok`; it does not mean the attack succeeded.
* Deployed browser QA used a disposable account, **real execution service**, and clearly identified test-only LLM/embedding fixtures. Login, all language starters/draft switching, public Run, hidden Submit, harder adaptive follow-up, timeout, Stop, completion, persisted history, desktop layout, and mobile layout were exercised. At 390px viewport, the page width was 375px with no horizontal overflow. Screenshots: [desktop](verification/phase9-desktop.png), [mobile](verification/phase9-mobile.png), and [completion](verification/phase9-completion.png).

The disposable UI account and its linked records were removed after verification, and the normal worker was restored. No provider fixtures are wired into production configuration. A subsequent live Gemini adapter smoke passed plan, question, grounded-evaluation-schema, and coding-complexity requests with `gemini-3.5-flash-lite`; see [the actual verification record](GEMINI_SMOKE.md). That synthetic provider check is separate from the full coding UI/worker flow. Live OpenAI requests, live embeddings, real Vosk recognition, physical microphone, and cloud speech verification remain final-integration gates. No live OpenAI or speech success is claimed.

## Credentials and startup

No credentials were printed, copied into tests, or exposed to the frontend. `.env` remains ignored; `.env.example` contains blank credential placeholders. The latest specification selects OpenAI as primary with `gpt-6-luna`; Gemini remains an explicit alternative. Settings, Compose, the example environment, and local non-secret selection now agree. Phase 5 embeddings plus pgvector and Phase 8 speech stay independently configured. The existing OpenAI adapter uses Responses structured outputs, which [official model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna) supports. Account access still needs live verification at final integration.

Primary configuration is `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-6-luna`, and locally supplied `LLM_API_KEY` (or `OPENAI_API_KEY`). A nonblank `OPENAI_MODEL` takes precedence over `LLM_MODEL`. Compose now forwards the supported legacy `LLM_API_KEY` to API/worker; it is never browser-visible. No OpenAI key is currently configured, so the existing clear missing-credential state is expected. The prior Gemini key/model are preserved exclusively in local configuration. Selecting `LLM_PROVIDER=gemini` uses `GEMINI_MODEL=gemini-3.5-flash-lite` and `GEMINI_API_KEY`, with no automatic fallback.

At final integration configure account-supported models and actual Gemini/OpenAI/embedding/speech credentials locally in ignored `.env`. The private local runner needs no external vendor credential. For production, configure a shared `CODE_RUNNER_API_KEY` of at least 32 characters on API/worker/runner; production runner startup rejects a missing/short key. It never enters the child environment. Keep the service private; a remote execution deployment also needs appropriate transport security and deployment hardening.

```powershell
docker compose up -d --build
docker compose ps
docker compose logs --tail 50 worker sandbox
```

The worker waits for migrations and sandbox health. Use the configured frontend/API ports; this workspace uses `http://localhost:3001` and `http://localhost:8001`. No runner port is published. Native API/worker development must target a reachable **trusted isolated service**, never a host execution fallback; Docker is the verified local execution deployment.

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini check
.\.venv\Scripts\python.exe -m pytest tests/backend -q --basetemp=.local/phase9-test-new
docker compose exec -T sandbox python /opt/runner/verify.py
```

Use a new pytest basetemp directory for each run. Frontend checks from `frontend`: `npm run lint`, `npm run typecheck`, `npm run test:voice`, `npm run build`. Docker Desktop must use Linux containers with rootless namespace support and Landlock ABI ≥3; unsupported environments fail closed.

## Limits and deferred work

The runner serializes one execution at a time. The original collection is intentionally small and its suites cover basic edge cases rather than exhaustive algorithm benchmarking. SQL/debugging/code-review execution, additional languages, horizontal runner scheduling, VM isolation, a separate kernel per job, and independent security auditing are outside this phase. Kernel/runtime/compiler security updates and a production abuse review are still required before opening execution to an untrusted public population. Candidate source is intentionally retained for owned history; temporary compiler/runtime files are not retained.

Phase 9 implementation and local verification are complete within this documented boundary. Stop here; do not start Phase 10.

Security references: [Linux Landlock documentation](https://docs.kernel.org/userspace-api/landlock.html), [Linux unshare API](https://man7.org/linux/man-pages/man2/unshare.2.html), [Docker seccomp documentation](https://docs.docker.com/engine/security/seccomp/), [vendored Docker default profile source](https://github.com/moby/profiles/blob/main/seccomp/default.json), and [libseccomp comparison definitions](https://github.com/seccomp/libseccomp/blob/main/include/seccomp.h.in).
