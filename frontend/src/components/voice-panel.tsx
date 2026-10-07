"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { mutate } from "@/lib/intelligence";
import type { Session } from "@/lib/types";
import { ActivityDetector, CaptureLease, encodeWav } from "@/lib/voice-signal.mjs";

type Turn = { id: string; question_id: string; kind: string; status: string; transcript: string | null; audio_available: boolean; error_code: string | null; metrics: { duration_seconds: number; speech_duration_seconds: number; filler_count: number; word_count: number; speaking_rate_wpm: number | null } | null };
type Voice = { state: string; revision: number; question_id: string; stt: { configured: boolean }; tts: { configured: boolean }; capture: { min_speech_seconds: number; silence_seconds: number; max_seconds: number }; turns: Turn[] };
const labels: Record<string, string> = { idle: "Voice ready", generating_response: "Preparing question audio…", playing_response: "Question audio ready", ai_speaking: "AI speaking…", ready_for_candidate: "Your turn", listening: "Listening…", processing_audio: "Processing audio…", transcribing: "Transcribing…", evaluating: "Evaluating your answer…", error: "Voice unavailable" };

export function VoicePanel({ interviewId, questionId, revision, onTranscript }: { interviewId: string; questionId: string; revision: number; onTranscript: (text: string, turnId: string) => void }) {
  const [voice, setVoice] = useState<Voice>(); const [error, setError] = useState(""); const [pending, setPending] = useState(false);
  const [activity, setActivity] = useState({ active: false, seconds: 0, rms: 0 }); const [online, setOnline] = useState(true);
  const state = useRef<Voice>(undefined); const generation = useRef(0); const starting = useRef(false);
  const microphone = useRef(new CaptureLease()); const painted = useRef(0);
  const media = useRef<{ stream: MediaStream; context: AudioContext; node: AudioWorkletNode; source: MediaStreamAudioSourceNode; chunks: Float32Array[]; vad: ActivityDetector }>(undefined);
  const player = useRef<HTMLAudioElement>(null); const played = useRef(""); const delivered = useRef("");
  const base = `/interviews/${interviewId}/voice`;
  const accept = useCallback((value: Voice) => { state.current = value; setVoice(value); return value; }, []);
  const load = useCallback(async () => accept(await api<Voice>(`${base}/status`)), [base, accept]);
  const cleanup = useCallback(() => { microphone.current.release(); const current = media.current; media.current = undefined; if (current) { current.node.port.onmessage = null; current.node.disconnect(); current.source.disconnect(); void current.context.close(); } }, []);
  useEffect(() => {
    const audioElement = player.current; const epochRef = generation;
    const disconnected = () => { setOnline(navigator.onLine); if (!navigator.onLine) { generation.current++; cleanup(); setError("Connection lost. Your typed answer is still available."); } };
    window.addEventListener("online", disconnected); window.addEventListener("offline", disconnected);
    const changed = () => { if (media.current) { generation.current++; cleanup(); setError("Microphone changed. Retry recording or type your answer instead."); void mutate<Voice>(`${base}/event`, "POST", { event: "abort", expected_revision: revision, voice_revision: state.current?.revision }).then(accept).catch(() => {}); } };
    navigator.mediaDevices?.addEventListener("devicechange", changed);
    return () => { epochRef.current++; cleanup(); audioElement?.pause(); window.removeEventListener("online", disconnected); window.removeEventListener("offline", disconnected); navigator.mediaDevices?.removeEventListener("devicechange", changed); };
  }, [cleanup, base, revision, accept]);
  useEffect(() => { if (!voice || !["generating_response", "processing_audio", "transcribing"].includes(voice.state)) return; const timer = window.setInterval(() => void load().catch(e => setError(e.message)), 1000); return () => window.clearInterval(timer); }, [voice, load]);
  const transcription = voice?.turns.find(turn => turn.question_id === questionId && turn.kind === "stt" && ["ready", "submitted"].includes(turn.status));
  useEffect(() => { if (transcription?.transcript && transcription.id !== delivered.current) { delivered.current = transcription.id; onTranscript(transcription.transcript, transcription.id); } }, [transcription, onTranscript]);
  const audio = voice?.turns.find(turn => turn.question_id === questionId && turn.kind === "tts" && turn.status === "ready" && turn.audio_available);
  const event = useCallback(async (name: string) => { const current = state.current; if (!current) throw new Error("Enable voice first."); return accept(await mutate<Voice>(`${base}/event`, "POST", { event: name, expected_revision: revision, voice_revision: current.revision })); }, [accept, base, revision]);
  async function play(turn: Turn) {
    if (!player.current || starting.current || media.current) return;
    const element = player.current;
    try {
      await event("speaking"); element.src = `/api/v1${base}/audio/${turn.id}`; await element.play(); played.current = turn.id;
    } catch (e) { element.pause(); setError(`Playback unavailable. ${(e as Error).message} You can type your answer instead.`); await load().then(value => ["ai_speaking", "playing_response"].includes(value.state) ? event("ready") : undefined).catch(() => {}); }
  }
  // Playback is attached to a unique completed turn, never to question rerenders.
  useEffect(() => { if (audio && voice?.state === "playing_response" && played.current !== audio.id) { played.current = audio.id; void play(audio); } });
  async function enable() { setPending(true); setError(""); try { const value = accept(await mutate<Voice>(`${base}/session`)); if (!value.stt.configured || !value.tts.configured) setError("Voice unavailable. You can type your answer instead."); if (value.tts.configured) await speak(value); } catch (e) { setError((e as Error).message); } finally { setPending(false); } }
  async function speak(current = state.current) { if (!current) return; setPending(true); setError(""); try { player.current?.pause(); await mutate(`${base}/synthesize`, "POST", { expected_revision: revision, voice_revision: current.revision, question_id: questionId, idempotency_key: crypto.randomUUID() }); await load(); } catch (e) { setError(`Voice unavailable. You can type your answer instead. ${(e as Error).message}`); } finally { setPending(false); } }
  async function finish(send: boolean) {
    const capture = media.current; if (!capture) return;
    const epoch = generation.current; const samples = capture.chunks; const rate = capture.context.sampleRate;
    cleanup(); setPending(true);
    try {
      if (!send || !samples.length) { await event("abort"); return; }
      const file = encodeWav(samples, rate, state.current?.capture.max_seconds); const session = await api<Session>("/auth/session");
      if (epoch !== generation.current) return;
      const form = new FormData(); form.set("file", file, "answer.wav"); form.set("question_id", questionId); form.set("expected_revision", String(revision)); form.set("voice_revision", String(state.current?.revision)); form.set("idempotency_key", crypto.randomUUID());
      const response = await fetch(`/api/v1${base}/transcribe`, { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": session.csrf_token }, body: form, signal: AbortSignal.timeout(30000) });
      if (!response.ok) { const body = await response.json(); throw new Error(body.error?.message || "Upload failed."); }
      if (epoch === generation.current) await load();
    } catch (e) { setError(`Voice unavailable. You can type your answer instead. ${(e as Error).message}`); await load().then(value => value.state === "listening" ? event("abort") : undefined).catch(() => {}); } finally { setPending(false); }
  }
  async function record() {
    if (starting.current || media.current || pending) return;
    starting.current = true; setPending(true); setError(""); const epoch = generation.current;
    let stream: MediaStream | undefined; let context: AudioContext | undefined;
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext || !window.AudioWorkletNode) throw new Error("This browser does not support microphone capture.");
      await event("listen");
      stream = await microphone.current.acquire(() => navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }, video: false }), () => state.current?.state === "listening");
      if (!stream) return;
      if (epoch !== generation.current) { stream.getTracks().forEach(track => track.stop()); return; }
      context = new AudioContext(); await context.resume(); await context.audioWorklet.addModule("/voice-capture.js");
      if (epoch !== generation.current) { stream.getTracks().forEach(track => track.stop()); await context.close(); return; }
      const source = context.createMediaStreamSource(stream); const node = new AudioWorkletNode(context, "voice-capture");
      const vad = new ActivityDetector(state.current?.capture); media.current = { stream, context, source, node, chunks: [], vad };
      source.connect(node); node.connect(context.destination);
      stream.getAudioTracks().forEach(track => { track.onended = () => { if (media.current) { cleanup(); setError("Microphone disconnected. You can type your answer instead."); void event("abort").catch(() => {}); } }; });
      painted.current = 0;
      node.port.onmessage = (message: MessageEvent<Float32Array>) => { const capture = media.current; if (!capture || epoch !== generation.current) return; capture.chunks.push(message.data); const value = vad.push(message.data, capture.context.sampleRate); if (value.seconds - painted.current >= .08 || value.stop) { setActivity(value); painted.current = value.seconds; } if (value.stop) void finish(value.hasSpeech); };
    } catch (e) { stream?.getTracks().forEach(track => track.stop()); if (context && !media.current) void context.close(); cleanup(); setError(`Voice unavailable. You can type your answer instead. ${(e as Error).message}`); await load().then(value => value.state === "listening" ? event("abort") : undefined).catch(() => {}); } finally { starting.current = false; setPending(false); }
  }
  const listening = voice?.state === "listening"; const working = voice && ["generating_response", "processing_audio", "transcribing", "ai_speaking"].includes(voice.state);
  return <section className="voice-panel" aria-label="Voice interview"><div className="voice-heading"><div><p className="eyebrow">SPEAK YOUR ANSWER</p><strong role="status" aria-live="polite">{listening && activity.active ? "Speaking…" : labels[voice?.state || "idle"]}</strong></div><span className={`voice-network ${online ? "" : "offline"}`}>{online ? "● Connected" : "○ Offline"}</span></div><audio ref={player} onEnded={() => void event("ready").catch(e => setError(e.message))} onError={() => { setError("Voice unavailable. You can type your answer instead."); void load().then(value => value.state === "ai_speaking" ? event("ready") : undefined).catch(() => {}); }} /><div className="voice-actions">{!voice ? <button type="button" className="secondary-button" disabled={pending || !online} onClick={() => void enable()}>Enable voice</button> : <><button type="button" className="secondary-button" disabled={pending || !!working || !online || !voice.stt.configured || listening} onClick={() => void record()}>{transcription ? "Record again" : "Start microphone"}</button>{listening && <><button type="button" className="action-button" disabled={pending} onClick={() => void finish(true)}>Finish recording</button><button type="button" className="text-button" onClick={() => void finish(false)}>Discard</button></>}<button type="button" className="text-button" disabled={pending || listening || !!working || !voice.tts.configured || !online} onClick={() => audio ? void play(audio) : void speak()}>Replay question</button></>}</div>{listening && <div className="voice-activity"><meter min={0} max={.1} value={activity.rms} aria-label="Microphone signal level" /><span>{activity.seconds.toFixed(1)}s · {activity.active ? "Speech detected" : "Listening for speech"}</span></div>}{error && <p className="voice-fallback" role="alert">{error}</p>}{voice && (voice.state === "error" || !voice.stt.configured || !voice.tts.configured) && !error && <p className="voice-fallback" role="alert">Voice unavailable. You can type your answer instead.</p>}{transcription?.transcript && <details className="voice-transcript" open><summary>Original transcript · review the answer below before submitting</summary><p>{transcription.transcript}</p>{transcription.metrics && <small>{transcription.metrics.duration_seconds.toFixed(1)}s recorded · {transcription.metrics.word_count} words · {transcription.metrics.filler_count} configured fillers. Signal measurements do not affect knowledge scores.</small>}</details>}<p className="voice-privacy">Microphone runs only during your turn. Recording is temporary; the transcript and measurements are saved. Review or edit your answer before submitting.</p></section>;
}
