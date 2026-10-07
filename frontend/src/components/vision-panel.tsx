"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { mutate } from "@/lib/intelligence";
import type { Session } from "@/lib/types";
import { CameraLease, SampleGate, cameraError } from "@/lib/vision-camera.mjs";

type IntegrityEvent = { id: string; event_type: string; started_at: string; ended_at: string | null; duration_ms: number | null; confidence: number | null; detector: string; metadata: { provenance: string } };
type Vision = { enabled: boolean; revision: number; sequence: number; error_code: string | null; provider: { available: boolean; message: string }; sampling: { interval_ms: number }; events: IntegrityEvent[] };
const labels: Record<string, string> = { CANDIDATE_PRESENT: "Person present", CANDIDATE_ABSENT: "No person detected", MULTIPLE_PERSONS_DETECTED: "Multiple persons detected", PHONE_DETECTED: "Phone detected", CAMERA_INTERRUPTED: "Camera or sampling interrupted", CAMERA_ORIENTATION_CHANGED: "Camera orientation changed" };

export function VisionPanel({ interviewId, active }: { interviewId: string; active: boolean }) {
  const base = `/interviews/${interviewId}/vision`;
  const [vision, setVision] = useState<Vision | null>(null);
  const [message, setMessage] = useState("");
  const [camera, setCamera] = useState(false);
  const [starting, setStarting] = useState(false);
  const current = useRef<Vision | null>(null);
  const lease = useRef(new CameraLease());
  const gate = useRef(new SampleGate());
  const video = useRef<HTMLVideoElement>(null);
  const controller = useRef<AbortController | null>(null);
  const accept = useCallback((value: Vision) => { current.current = value; setVision(value); }, []);
  const load = useCallback(async () => { try { accept(await api<Vision>(`${base}/status`)); } catch (e) { setMessage((e as Error).message); } }, [accept, base]);
  const release = useCallback(() => { lease.current.stop(); controller.current?.abort(); setCamera(false); if (video.current) video.current.srcObject = null; }, []);
  const stop = useCallback(async () => {
    release();
    const state = current.current;
    if (state?.enabled) {
      try { accept(await mutate<Vision>(`${base}/session`, "POST", { enabled: false, expected_revision: state.revision })); }
      catch (e) { setMessage((e as Error).message); }
    }
  }, [accept, base, release]);
  useEffect(() => { const cameraLease = lease.current; const timer = window.setTimeout(() => void load(), 0); return () => { window.clearTimeout(timer); cameraLease.stop(); controller.current?.abort(); }; }, [load]);
  useEffect(() => { if (active) return; const timer = window.setTimeout(() => { void stop(); void load(); }, 0); return () => window.clearTimeout(timer); }, [active, stop, load]);
  useEffect(() => {
    if (!camera) return;
    const visible = () => { if (document.hidden) void stop(); };
    const orientation = () => { const state = current.current; if (state?.enabled) void mutate<Vision>(`${base}/notice`, "POST", { revision: state.revision, notice: "orientation_changed" }).then(accept).catch(() => {}); };
    document.addEventListener("visibilitychange", visible);
    window.addEventListener("orientationchange", orientation);
    return () => { document.removeEventListener("visibilitychange", visible); window.removeEventListener("orientationchange", orientation); };
  }, [camera, base, stop, accept]);
  useEffect(() => {
    if (!camera || !active) return;
    const sample = async (sequence: number) => {
      const element = video.current, state = current.current;
      if (!element || element.readyState < 2 || !state?.enabled || !lease.current.stream) return;
      const canvas = document.createElement("canvas");
      const scale = Math.min(640 / element.videoWidth, 640 / element.videoHeight, 1);
      canvas.width = Math.round(element.videoWidth * scale); canvas.height = Math.round(element.videoHeight * scale);
      canvas.getContext("2d")?.drawImage(element, 0, 0, canvas.width, canvas.height);
      const captured = new Date().toISOString();
      const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/jpeg", .65));
      canvas.width = canvas.height = 0;
      if (!blob || blob.size > 131072 || !lease.current.stream) return;
      const form = new FormData(); form.set("image", blob, "sample.jpg"); form.set("revision", String(state.revision)); form.set("sequence", String(sequence)); form.set("captured_at", captured);
      const session = await api<Session>("/auth/session");
      if (!lease.current.stream) return;
      controller.current = new AbortController();
      const response = await fetch(`/api/v1${base}/frame`, { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": session.csrf_token }, body: form, signal: AbortSignal.any([controller.current.signal, AbortSignal.timeout(10000)]) });
      if (response.status === 429) { setMessage("Processing a recent sample; extra frames are dropped."); return; }
      if (!response.ok) throw new Error("Visual monitoring could not process the sample. Your interview remains available.");
      const next: Vision = await response.json();
      if (lease.current.stream && next.revision === current.current?.revision) accept(next);
      setMessage(next.error_code ? "Local detector unavailable; samples are not being judged." : "");
      if (!next.enabled) release();
    };
    const timer = window.setInterval(() => { void gate.current.run(sample).catch((e: Error) => { if (e.name !== "AbortError") { setMessage(e.message); void stop(); } }); }, vision?.sampling.interval_ms || 1000);
    return () => window.clearInterval(timer);
  }, [active, camera, base, accept, release, stop, vision?.sampling.interval_ms]);
  async function start() {
    if (!navigator.mediaDevices?.getUserMedia) { setMessage("Camera capture is unsupported in this browser. Continue without it."); return; }
    setStarting(true); setMessage("");
    try {
      const stream = await lease.current.start(navigator.mediaDevices);
      if (!stream) return;
      const state = await mutate<Vision>(`${base}/session`, "POST", { enabled: true, expected_revision: current.current?.revision || 0 });
      if (!lease.current.stream) { await mutate(`${base}/session`, "POST", { enabled: false, expected_revision: state.revision }); return; }
      gate.current.sequence = state.sequence + 1;
      accept(state); setCamera(true);
      if (video.current) { video.current.srcObject = stream; await video.current.play(); }
      stream.getVideoTracks()[0].onended = () => { const state = current.current; if (state?.enabled) void mutate(`${base}/notice`, "POST", { revision: state.revision, notice: "interrupted" }).catch(() => {}); setMessage("Camera permission was revoked or the feed ended. Continue without monitoring."); void stop(); };
    } catch (e) { release(); setMessage(cameraError(e as Error)); await stop(); }
    finally { setStarting(false); }
  }
  return <section className="vision-panel content-card" aria-label="Optional visual monitoring">
    <div className="vision-heading"><div><h2>Optional camera signals</h2><p>Sampled images are processed locally on the IntervAI server and discarded. Only timestamped observations are saved. They do not change your scores or indicate misconduct.</p></div><span role="status">{camera ? "Camera active · monitoring" : "Camera inactive"}</span></div>
    <video ref={video} muted playsInline className={camera ? "vision-preview" : "vision-preview inactive"} aria-label="Camera preview" />
    {active && <div className="room-actions"><button className="secondary-button" disabled={camera || starting || !vision?.provider.available} onClick={() => void start()}>{starting ? "Requesting camera permission…" : "Enable optional camera"}</button><button className="text-button" disabled={!camera && !starting} onClick={() => void stop()}>Stop camera</button></div>}
    {vision && !vision.provider.available && <p>{vision.provider.message}</p>}
    {message && <p role="alert">{message}</p>}
    <details open={!active}><summary>Visual event timeline ({vision?.events.length || 0})</summary>
      <p className="subtle-copy">Detector results can be wrong. No identity, emotion, attention, or intent is inferred. Browser-reported camera notices are unverified.</p>
      <ol className="vision-timeline">{vision?.events.map(event => <li key={event.id}><time dateTime={event.started_at}>{new Date(event.started_at).toLocaleTimeString()}</time><strong>{labels[event.event_type]}</strong><span>{event.duration_ms === null ? "Duration pending" : `${(event.duration_ms / 1000).toFixed(1)} s observed`}{event.confidence === null ? "" : ` · model score ${event.confidence.toFixed(2)}`}</span><small>{event.metadata.provenance === "client_reported_unverified" ? "Browser-reported · unverified" : event.detector}</small></li>)}</ol>
      {!vision?.events.length && <p>No visual events recorded. This does not establish whether a person or object was present.</p>}
    </details>
  </section>;
}
