# Live Gemini provider verification

Verified on 2026-10-01 through the existing `GeminiProvider` REST adapter.

Configuration used during this recorded smoke (the later Phase 9 specification selects OpenAI as primary; these Gemini settings remain preserved as the alternative):

```dotenv
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash-lite
LLM_MODEL=
```

Configure the actual key only as `GEMINI_API_KEY` in ignored `.env`. Gemini does
not read `LLM_API_KEY`; that legacy field belongs to the OpenAI configuration.
The existing local key was moved to the Gemini setting without displaying it.
`GEMINI_MODEL` takes precedence over `LLM_MODEL`. If using the compatibility
alias instead, set `LLM_MODEL=gemini-3.5-flash-lite` and leave `GEMINI_MODEL` blank.
Do not prefix the configured identifier with `models/`: the adapter adds it.

Google's authenticated model list succeeded. Although it listed
`gemini-2.5-flash`, an actual structured generation call returned HTTP 404
`NOT_FOUND`. The selected stable `gemini-3.5-flash-lite` succeeded with the
adapter's existing `generateContent`, `responseMimeType`, and
`responseJsonSchema` request, with no adapter changes.

Four real requests passed application Pydantic validation:

| Check | Application schema | Measured duration |
|---|---|---|
| Interview plan | `PlanResult` | 1.69 s |
| Question | `QuestionResult` | 13.92 s |
| Answer evaluation | `GroundedEvaluationResult` | 2.36 s |
| Coding complexity estimate | `ComplexityAnalysis` | 11.19 s |

The smoke uses only synthetic prompts, makes no candidate/database records,
prints no credentials or provider response bodies, and exits nonzero on failure.
It exercises the real provider abstraction rather than a mock. It establishes
provider/schema compatibility; the full UI/worker interview journey, live
embeddings, cloud speech, and physical microphone gates are separate checks.

Run from the repository root:

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe scripts/smoke_llm.py
```

Reload services after changing local configuration:

```powershell
docker compose up -d backend worker
```

Provider-specific settings and `.env.example` now use the verified model.
Secrets remain exclusively in the ignored local environment file.

References: [Google model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite),
[structured output documentation](https://ai.google.dev/gemini-api/docs/structured-output).
