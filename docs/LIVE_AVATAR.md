# Interactive interviewer: voice orb and natural speech

Open a non-coding interview and select **Start live interviewer**. The question is spoken in a calm neural voice, then the microphone opens. **Finish answer** ends recording by default, so thinking pauses no longer cut off an answer. Review/edit the transcript in **Your answer**, then submit.

## Controls

- **Speaking pace:** relaxed 0.9x by default, with 0.8x and 1x options. Pitch is preserved. This preference survives question changes within the current interview page.
- **Finish recording:** manual by default, or automatic after three seconds of silence. All recordings remain bounded by the configured maximum (180 seconds by default).
- **Auto-submit transcript:** off by default. When enabled, each completed transcript has a four-second review countdown. Editing, Review instead, Stop, or leaving the page cancels automatic submission. Enable automatic recording finish separately for a hands-free flow.
- **Interrupt and answer**, **Replay question**, **Record answer**, and **Discard recording** remain available. Switching tabs, pausing, or finishing the interview releases the microphone.

## Appearance and delivery

The former cartoon character is replaced with a cyan/indigo glass-style SVG orb. Its scale and signal bars follow actual decoded playback energy while speaking and the microphone level while listening. Buffering, mute, pause, and silence stop the speaking response. Thinking has a distinct orbit animation; reduced-motion preferences disable rotation and scaling. No avatar service, video asset, or large model download is required.

Automatic next-question activation includes a one-second breathing space; playback starts after a further short lead-in. Gemini TTS receives the exact question separately from delivery metadata requesting a warm, conversational voice at around 130 words/minute with sentence pauses. This pace is a synthesis instruction, not a guaranteed measured speed. The user also controls playback speed.

## Speech configuration

This installation now uses the existing Gemini key with:

```dotenv
STT_PROVIDER=gemini
STT_MODEL=gemini-3.5-transcribe
TTS_PROVIDER=gemini
TTS_MODEL=gemini-3.8-flash-tts
TTS_VOICE=Sulafat
SPEECH_LOCALE=en-IN
VOICE_SILENCE_SECONDS=3
```

`STT_API_KEY`/`TTS_API_KEY` may override `GEMINI_API_KEY`. Credentials stay on the server. `TTS_STYLE` can override delivery instructions. `SPEECH_VOCABULARY` accepts a JSON array of domain vocabulary; it provides recognition hints, not an expected answer. The adapter uses **VERBATIM** transcription, preserving fillers, repetitions, and conceptual mistakes for fair evaluation. It does not use an LLM to rewrite the answer or fabricate confidence scores/timestamps. Noise suppression, echo cancellation and automatic microphone gain are requested when supported by the browser.

Voice recordings are sent to Google for transcription, and question text is sent for speech generation. The UI discloses cloud transcription before microphone activation. Local temporary-audio cleanup and saved transcripts retain the existing lifecycle; local cleanup does not describe Google's retention policy. Local Vosk/eSpeak and the existing OpenAI adapters remain available via configuration. The Gemini adapters target the named transcription model and the 3.8 TTS WAV contract, not older PCM TTS models.

Speech remains turn-based, with explicit interruption rather than automatic full-duplex barge-in. Provider failures show the typed-answer fallback. Transcripts remain editable; real-world accuracy depends on the microphone, accent and background noise. No camera is required.

## Verification

- TypeScript, ESLint and the production Next.js build passed.
- 10 microphone/VAD tests and 4 playback/countdown tests passed, including long pauses in manual recording and automatic capture's longer pause tolerance.
- 38 backend tests passed, covering speech lifecycle plus Gemini HTTP contracts, malformed/empty/blocked output, timeouts, authentication/quota failures, invalid audio, cloud disclosure and verbatim answer preservation.
- A real Gemini voice sample and dedicated transcription call succeeded, recognizing PostgreSQL and Python correctly. These used generic synthetic speech, not a physical microphone.
- A temporary account exercised the running frontend API proxy, real question generation, worker neural TTS (11.2 seconds of valid WAV), playback/listening state transitions, and worker transcription of the synthetic sample. The transcript reached review state; the temporary account and audio were removed. App and API health checks returned HTTP 200.
- The orb SVG was rendered and visually inspected locally.
- Browser interaction and physical-microphone accuracy could not be verified in this session because browser access was rejected. Synthetic provider tests do not substitute for a device test.

Provider references: [Gemini speech generation](https://ai.google.dev/gemini-api/docs/generate-content/speech-generation), [Gemini transcription](https://ai.google.dev/gemini-api/docs/generate-content/transcribe).
