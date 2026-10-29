"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { mutate } from "@/lib/intelligence";
import type { Session } from "@/lib/types";
import { ActivityDetector, CaptureLease, encodeWav } from "@/lib/voice-signal.mjs";
import { AvatarAudio, TranscriptCountdown } from "@/lib/avatar-audio.mjs";
import { InterviewerAvatar, type AvatarState } from "./interviewer-avatar";

type Turn = { id: string; question_id: string; kind: string; status: string; transcript: string | null; audio_available: boolean; error_code: string | null; provider_metadata?: { provider?: string } };
type Voice = { state: string; revision: number; question_id: string; stt: { configured: boolean; provider?: string; cloud_audio?: boolean }; tts: { configured: boolean; provider?: string }; capture: { min_speech_seconds: number; silence_seconds: number; max_seconds: number }; turns: Turn[] };
type Props = {
  interviewId: string; questionId: string; revision: number;
  live: boolean; onLiveChange: (enabled: boolean) => void;
  autoSubmit: boolean; onAutoSubmitChange: (enabled: boolean) => void;
  pace: number; onPaceChange: (pace: number) => void;
  autoStop: boolean; onAutoStopChange: (enabled: boolean) => void;
  onTranscript: (text: string, turnId: string) => void;
  onSubmitTranscript: (text: string, turnId: string) => Promise<void>;
  onBusyChange: (busy: boolean) => void;
};
const busyStates = ["generating_response", "processing_audio", "transcribing", "evaluating"];

export function VoicePanel({ interviewId, questionId, revision, live, onLiveChange, autoSubmit, onAutoSubmitChange, pace, onPaceChange, autoStop, onAutoStopChange, onTranscript, onSubmitTranscript, onBusyChange }: Props) {
  const [voice, setVoice] = useState<Voice>();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [recording, setRecording] = useState(false);
  const [online, setOnline] = useState(true);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [activity, setActivity] = useState({ active: false, seconds: 0, rms: 0 });
  const state = useRef<Voice>(undefined);
  const epoch = useRef(0);
  const locked = useRef(false);
  const liveRef = useRef(live);
  const active = useRef(true);
  const initialized = useRef(false);
  const microphone = useRef(new CaptureLease());
  const player = useRef<HTMLAudioElement>(null);
  const animator = useRef<AvatarAudio>(undefined);
  const played = useRef("");
  const delivered = useRef("");
  const requestedTurn = useRef("");
  const autoAllowed = useRef(false);
  const countdownTimer = useRef<TranscriptCountdown>(undefined);
  const media = useRef<{ context: AudioContext; node: AudioWorkletNode; source: MediaStreamAudioSourceNode; chunks: Float32Array[]; vad: ActivityDetector }>(undefined);
  const actions = useRef<{ enable: () => Promise<void>; record: () => Promise<void>; play: (turn: Turn) => Promise<void>; stop: () => void }>({ enable: async () => {}, record: async () => {}, play: async () => {}, stop: () => {} });
  const base = `/interviews/${interviewId}/voice`;

  const accept = useCallback((value: Voice) => {
    if (active.current && value.question_id === questionId && (!state.current || value.revision >= state.current.revision)) {
      state.current = value;
      setVoice(value);
    }
    return value;
  }, [questionId]);
  const load = useCallback(async () => {
    const currentEpoch = epoch.current;
    const value = await api<Voice>(`${base}/status`);
    if (currentEpoch === epoch.current) accept(value);
    return value;
  }, [base, accept]);
  const event = useCallback(async (name: string) => {
    const current = state.current;
    if (!current) throw new Error("Start the interviewer first.");
    const value = await mutate<Voice>(`${base}/event`, "POST", { event: name, expected_revision: revision, voice_revision: current.revision });
    return accept(value);
  }, [base, revision, accept]);
  const cleanupCapture = useCallback(() => {
    microphone.current.release();
    const current = media.current;
    media.current = undefined;
    if (current) {
      current.node.port.onmessage = null;
      current.node.disconnect();
      current.source.disconnect();
      void current.context.close();
    }
    if (active.current) setRecording(false);
  }, []);
  const fail = useCallback((message: string) => {
    if (!active.current) return;
    liveRef.current = false;
    autoAllowed.current = false;
    countdownTimer.current?.cancel();
    onLiveChange(false);
    setCountdown(null);
    setError(message);
  }, [onLiveChange]);

  // Called inside the Start/Replay click, before awaiting network requests.
  async function unlockAudio() {
    if (!player.current) throw new Error("Audio player is not ready.");
    if (!window.AudioContext) throw new Error("This browser does not support avatar audio.");
    animator.current ??= new AvatarAudio(player.current, window.AudioContext);
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      await Promise.race([animator.current.resume(), new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("Select Resume interviewer to allow browser audio.")), 5000);
      })]);
    } finally { clearTimeout(timer); }
  }
  async function recover() {
    try {
      const value = await load();
      if (["listening", "ai_speaking", "playing_response", "error"].includes(value.state)) await event("abort");
    } catch { /* The visible error includes the typed-answer fallback. */ }
  }
  async function enable() {
    if (locked.current) return;
    locked.current = true;
    setPending(true);
    setError("");
    const token = epoch.current;
    try {
      await unlockAudio();
      const value = await mutate<Voice>(`${base}/session`);
      if (token !== epoch.current || !active.current) return;
      accept(value);
      if (!value.tts.configured || !value.stt.configured) throw new Error("Speech services are unavailable. Check the voice configuration.");
      // Recover an interrupted browser session before starting a new local turn.
      if (["listening", "ai_speaking"].includes(value.state)) await event("abort");
      if (token !== epoch.current) return;
      liveRef.current = true;
      onLiveChange(true);
      if (busyStates.includes(state.current?.state || "")) return;
      const ready = value.turns.find(turn => turn.question_id === questionId && turn.kind === "tts" && turn.status === "ready" && turn.audio_available && turn.provider_metadata?.provider === value.tts.provider);
      locked.current = false;
      if (ready) await play(ready);
      else await synthesize();
    } catch (e) {
      fail(`${(e as Error).message} You can still type your answer.`);
    } finally {
      locked.current = false;
      if (active.current) setPending(false);
    }
  }
  async function synthesize() {
    if (locked.current || !state.current) return;
    locked.current = true;
    setPending(true);
    const token = epoch.current;
    try {
      await mutate(`${base}/synthesize`, "POST", { expected_revision: revision, voice_revision: state.current.revision, question_id: questionId, idempotency_key: crypto.randomUUID() });
      if (token === epoch.current) await load();
    } catch (e) { fail(`Question audio could not be prepared. ${(e as Error).message}`); }
    finally { locked.current = false; if (active.current) setPending(false); }
  }
  async function play(turn: Turn) {
    if (locked.current || media.current || !player.current) return;
    countdownTimer.current?.cancel();
    setCountdown(null);
    locked.current = true;
    setPending(true);
    setError("");
    played.current = turn.id;
    const token = epoch.current;
    const element = player.current;
    try {
      await unlockAudio();
      await event("speaking");
      if (token !== epoch.current || !active.current) { element.pause(); return; }
      element.src = `/api/v1${base}/audio/${turn.id}`;
      element.preservesPitch = true;
      element.playbackRate = pace;
      await new Promise(resolve => setTimeout(resolve, 450));
      if (token !== epoch.current || !active.current) return;
      await element.play();
      if (token !== epoch.current) element.pause();
    } catch (e) {
      element.pause();
      fail(`Playback stopped. Select Replay question to try again. ${(e as Error).message}`);
      await recover();
    } finally { locked.current = false; if (active.current) setPending(false); }
  }
  async function record() {
    if (locked.current || media.current) return;
    countdownTimer.current?.cancel();
    setCountdown(null);
    locked.current = true;
    setPending(true);
    setError("");
    setActivity({ active: false, seconds: 0, rms: 0 });
    const token = epoch.current;
    let context: AudioContext | undefined;
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) throw new Error("Microphone capture is not supported in this browser.");
      await event("listen");
      if (token !== epoch.current) { await recover(); return; }
      const stream = await microphone.current.acquire(() => navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }, video: false }), () => active.current && token === epoch.current && state.current?.state === "listening");
      if (!stream) return;
      context = new AudioContext();
      await context.resume();
      await context.audioWorklet.addModule("/voice-capture.js");
      if (token !== epoch.current || !active.current) { cleanupCapture(); await context.close(); return; }
      const source = context.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(context, "voice-capture");
      const vad = new ActivityDetector({ ...state.current?.capture, auto_stop: autoStop });
      media.current = { context, source, node, chunks: [], vad };
      setRecording(true);
      source.connect(node); node.connect(context.destination);
      autoAllowed.current = true;
      stream.getAudioTracks().forEach(track => { track.onended = () => { if (media.current) { cleanupCapture(); fail("Microphone disconnected. Start the interviewer again or type your answer."); void recover(); } }; });
      let painted = 0;
      node.port.onmessage = (message: MessageEvent<Float32Array>) => {
        const current = media.current;
        if (!current || token !== epoch.current) return;
        current.chunks.push(message.data);
        const value = vad.push(message.data, current.context.sampleRate);
        if (value.seconds - painted >= .08 || value.stop) { setActivity(value); painted = value.seconds; }
        if (value.stop) void finish(value.hasSpeech);
      };
    } catch (e) {
      if (context && !media.current && context.state !== "closed") void context.close();
      cleanupCapture();
      fail(`Microphone unavailable. ${(e as Error).message} You can type your answer.`);
      await recover();
    } finally { locked.current = false; if (active.current) setPending(false); }
  }
  async function finish(send: boolean) {
    const capture = media.current;
    if (!capture) return;
    const token = epoch.current;
    const samples = capture.chunks;
    const rate = capture.context.sampleRate;
    cleanupCapture();
    locked.current = true;
    setPending(true);
    try {
      if (!send || !samples.length) {
        autoAllowed.current = false;
        await event("abort");
        if (send === false) setError("Recording discarded. Start the microphone when ready.");
        return;
      }
      const file = encodeWav(samples, rate, state.current?.capture.max_seconds);
      const session = await api<Session>("/auth/session");
      if (token !== epoch.current) return;
      const form = new FormData();
      form.set("file", file, "answer.wav"); form.set("question_id", questionId);
      form.set("expected_revision", String(revision)); form.set("voice_revision", String(state.current?.revision));
      form.set("idempotency_key", crypto.randomUUID());
      const response = await fetch(`/api/v1${base}/transcribe`, { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": session.csrf_token }, body: form, signal: AbortSignal.timeout(30000) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message || "Audio upload failed.");
      if (token !== epoch.current) return;
      requestedTurn.current = body.id;
      await load();
    } catch (e) { fail(`Transcription unavailable. ${(e as Error).message} You can type your answer.`); await recover(); }
    finally { locked.current = false; if (active.current) setPending(false); }
  }
  async function ended() {
    setPlaying(false);
    const token = epoch.current;
    try {
      await event("ready");
      if (token === epoch.current && liveRef.current && !document.hidden) await record();
    } catch (e) { fail((e as Error).message); }
  }
  async function interrupt() {
    if (locked.current) return;
    player.current?.pause();
    setPlaying(false);
    const token = epoch.current;
    locked.current = true;
    setPending(true);
    try { await event("ready"); }
    catch (e) { fail((e as Error).message); return; }
    finally { locked.current = false; setPending(false); }
    if (token === epoch.current) await record();
  }
  function stop() {
    epoch.current++;
    liveRef.current = false;
    autoAllowed.current = false;
    countdownTimer.current?.cancel();
    onLiveChange(false);
    player.current?.pause();
    cleanupCapture();
    setPlaying(false);
    setCountdown(null);
    // In-flight speech jobs can finish, but cannot play or submit after Stop.
    void recover();
  }

  useEffect(() => { actions.current = { enable, record, play, stop }; });
  useEffect(() => { liveRef.current = live; }, [live]);
  useEffect(() => { if (player.current) player.current.playbackRate = pace; }, [pace]);
  // Load provider disclosure before the user activates microphone capture.
  useEffect(() => { void load().catch(() => { if (active.current) setError("Could not connect to speech services. Select Connect speech services to retry."); }); }, [load]);
  useEffect(() => {
    active.current = true;
    const graph = animator;
    const generation = epoch;
    const audio = player.current;
    const changed = () => {
      setOnline(navigator.onLine);
      if (!navigator.onLine) { actions.current.stop(); setError("Connection lost. Reconnect, then start the interviewer again."); }
    };
    const hidden = () => { if (document.hidden) actions.current.stop(); };
    const deviceChanged = () => { if (media.current) { actions.current.stop(); setError("Microphone changed. Start the interviewer again."); } };
    window.addEventListener("online", changed); window.addEventListener("offline", changed);
    document.addEventListener("visibilitychange", hidden);
    navigator.mediaDevices?.addEventListener("devicechange", deviceChanged);
    return () => {
      active.current = false;
      generation.current++;
      cleanupCapture();
      audio?.pause();
      if (graph.current) { void graph.current.dispose(); graph.current = undefined; }
      window.removeEventListener("online", changed); window.removeEventListener("offline", changed);
      document.removeEventListener("visibilitychange", hidden);
      navigator.mediaDevices?.removeEventListener("devicechange", deviceChanged);
    };
  }, [cleanupCapture]);
  useEffect(() => {
    if (!live || initialized.current) return;
    const timer = window.setTimeout(() => { initialized.current = true; void actions.current.enable(); }, 1000);
    return () => window.clearTimeout(timer);
  }, [live]);
  useEffect(() => {
    if (!voice || !busyStates.includes(voice.state)) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { const value = await load(); if (!disposed && value.state === "error") fail("Speech processing failed. Retry the interviewer or type your answer."); }
      catch (e) { if (!disposed) fail((e as Error).message); }
      if (!disposed) timer = setTimeout(poll, 750);
    };
    timer = setTimeout(poll, 750);
    return () => { disposed = true; clearTimeout(timer); };
  }, [voice, load, fail]);
  const transcription = voice?.turns.find(turn => turn.question_id === questionId && turn.kind === "stt" && turn.status === "ready");
  const audio = voice?.turns.find(turn => turn.question_id === questionId && turn.kind === "tts" && turn.status === "ready" && turn.audio_available && turn.provider_metadata?.provider === voice.tts.provider);
  useEffect(() => {
    if (audio && live && voice?.state === "playing_response" && played.current !== audio.id) void actions.current.play(audio);
  }, [audio, live, voice?.state]);
  useEffect(() => {
    if (transcription?.transcript && delivered.current !== transcription.id) {
      delivered.current = transcription.id;
      onTranscript(transcription.transcript, transcription.id);
    }
  }, [transcription, onTranscript]);
  useEffect(() => {
    if (!live || !autoSubmit || !transcription?.transcript || requestedTurn.current !== transcription.id || !autoAllowed.current) return;
    const token = epoch.current;
    const timer = new TranscriptCountdown({
      tick: setCountdown,
      canSubmit: () => token === epoch.current && liveRef.current && autoAllowed.current && !document.hidden,
      submit: () => {
        autoAllowed.current = false;
        setCountdown(null);
        void onSubmitTranscript(transcription.transcript!, transcription.id).catch(e => fail(`Answer was not submitted. ${(e as Error).message}`));
      },
    });
    countdownTimer.current = timer;
    return () => timer.cancel();
  }, [transcription?.id, transcription?.transcript, live, autoSubmit, onSubmitTranscript, fail]);
  const listening = recording;
  const working = !!voice && busyStates.includes(voice.state);
  useEffect(() => { onBusyChange(pending || listening || (live && working) || playing); }, [pending, listening, live, working, playing, onBusyChange]);
  useEffect(() => () => onBusyChange(false), [onBusyChange]);
  const avatarState: AvatarState = playing ? "speaking" : listening ? "listening" : error || !online ? "error" : !live && initialized.current ? "paused" : pending || working ? "thinking" : "idle";

  return <section className="voice-panel avatar-interview" aria-label="Interactive avatar interviewer">
    <InterviewerAvatar state={avatarState} audio={animator} signal={activity.rms} label={working && live ? voice?.state === "generating_response" ? "Preparing question audio…" : "Transcribing your answer…" : undefined}/>
    <div className="avatar-conversation">
      <div className="voice-heading"><div><p className="eyebrow">YOUR INTERVIEWER</p><h2>Live interviewer</h2></div><span className={`voice-network ${online ? "" : "offline"}`}>{online ? "● Online" : "○ Offline"}</span></div>
      <audio ref={player} preload="auto" onPlaying={() => setPlaying(true)} onPause={() => setPlaying(false)} onWaiting={() => setPlaying(false)} onEnded={() => void ended()} onError={() => { fail("Question audio could not be played. Replay the question or use your typed answer."); void recover(); }}/>
      <div className="voice-actions">
        {!live && <button type="button" className="action-button" disabled={pending || working || !online} onClick={() => { if (!voice) { void load().catch(e => fail((e as Error).message)); return; } initialized.current = true; void enable(); }}>{!voice ? "Connect speech services" : initialized.current ? "Resume interviewer" : "Start live interviewer"}</button>}
        {live && <button type="button" className="secondary-button" onClick={stop}>Stop interviewer</button>}
        {voice?.state === "ai_speaking" && <button type="button" className="action-button" disabled={pending} onClick={() => void interrupt()}>Interrupt and answer</button>}
        {listening ? <><button type="button" className="action-button" disabled={pending} onClick={() => void finish(true)}>Finish answer</button><button type="button" className="text-button" disabled={pending} onClick={() => void finish(false)}>Discard recording</button></> : voice && <button type="button" className="secondary-button" disabled={pending || working || voice.state === "ai_speaking" || !online || !voice.stt.configured} onClick={() => { autoAllowed.current = false; setCountdown(null); void record(); }}>Record answer</button>}
        {voice && <button type="button" className="text-button" disabled={pending || listening || working || voice.state === "ai_speaking" || !online || !voice.tts.configured} onClick={() => { autoAllowed.current = false; setCountdown(null); if (audio) void play(audio); else void synthesize(); }}>Replay question</button>}
      </div>
      <div className="voice-preferences">
        <label>Speaking pace<select value={pace} onChange={e => onPaceChange(Number(e.target.value))}><option value={.8}>Extra relaxed · 0.8×</option><option value={.9}>Relaxed · 0.9×</option><option value={1}>Natural · 1×</option></select></label>
        <label>Finish recording<select value={autoStop ? "pause" : "manual"} disabled={listening || pending} onChange={e => onAutoStopChange(e.target.value === "pause")}><option value="manual">When I select Finish answer</option><option value="pause">After a longer pause</option></select></label>
      </div>
      <label className="avatar-handsfree"><input type="checkbox" checked={autoSubmit} onChange={e => { onAutoSubmitChange(e.target.checked); setCountdown(null); }}/><span>Auto-submit transcript<small>Sends after 4 seconds. Leave off to review first.</small></span></label>
      {listening && <div className="voice-activity"><meter min={0} max={.1} value={activity.rms} aria-label="Microphone signal level"/><span>{activity.seconds.toFixed(1)} / {voice?.capture.max_seconds ?? 180}s · {activity.active ? "Hearing your voice" : "Microphone is listening"}</span></div>}
      {countdown !== null && <div className="avatar-countdown" role="status">Submitting in {countdown}s <button type="button" className="secondary-button" onClick={() => { autoAllowed.current = false; onAutoSubmitChange(false); setCountdown(null); }}>Review instead</button></div>}
      {error && <p className="voice-fallback" role="alert">{error}</p>}
      {transcription?.transcript && <details className="voice-transcript"><summary>Your transcript</summary><p>{transcription.transcript}</p></details>}
      <details className="voice-help"><summary>Voice help & privacy</summary>
      <p className="avatar-instructions">Listen, then take your time answering. {autoStop ? `Recording finishes after ${voice?.capture.silence_seconds ?? 3} seconds of silence.` : "Pauses won’t end your answer. Select Finish answer when you’re done."} Review your transcript before submitting.</p>
      <p className="voice-provider-note">{!voice ? "Checking speech services…" : voice.stt.cloud_audio ? `Voice answers are sent to ${voice.stt.provider === "gemini" ? "Google Gemini" : "the configured speech provider"} for transcription. Start the interviewer to use voice, or type below.` : "Voice answers are transcribed locally on this server."}</p>

      <p className="voice-privacy">Microphone access starts after you activate the interviewer. Audio is temporary; transcripts are saved. Stop, leaving this page, or switching tabs releases the microphone. Camera is not required.</p></details>
    </div>
  </section>;
}
