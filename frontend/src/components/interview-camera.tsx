"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { mutate } from "@/lib/intelligence";
import type { Session } from "@/lib/types";
import { CameraLease, SampleGate, cameraError } from "@/lib/vision-camera.mjs";
import { Icon } from "./ui/icon";

type CameraEvent = { id: string; event_type: string; started_at: string; duration_ms: number | null; ended_at: string | null };
type Vision = { enabled: boolean; revision: number; sequence: number; error_code: string | null; provider: { available: boolean; message: string }; sampling: { interval_ms: number }; events: CameraEvent[] };
const labels: Record<string, string> = { CANDIDATE_PRESENT: "Person present", CANDIDATE_ABSENT: "No person detected", MULTIPLE_PERSONS_DETECTED: "Multiple persons detected", PHONE_DETECTED: "Phone detected", CAMERA_INTERRUPTED: "Camera interrupted", CAMERA_ORIENTATION_CHANGED: "Camera orientation changed" };

export function InterviewCamera({ interviewId, active }: { interviewId: string; active: boolean }) {
  const base = `/interviews/${interviewId}/vision`;
  const [vision, setVision] = useState<Vision | null>(null);
  const [camera, setCamera] = useState(false);
  const [starting, setStarting] = useState(false);
  const [message, setMessage] = useState("");
  const [observationMessage, setObservationMessage] = useState("");
  const [monitoring, setMonitoring] = useState(false);
  const [monitorBusy, setMonitorBusy] = useState(false);
  const [mirrored, setMirrored] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const panel = useRef<HTMLElement>(null);
  const lease = useRef(new CameraLease());
  const gate = useRef(new SampleGate());
  const controller = useRef<AbortController | null>(null);
  const current = useRef<Vision | null>(null);
  const mounted = useRef(false);
  const activeRef = useRef(active);
  const wanted = useRef(true);
  const observing = useRef(false);
  const ownsObservations = useRef(false);

  const accept = useCallback((value: Vision) => {
    if (!mounted.current || value.revision < (current.current?.revision ?? -1)) return;
    current.current = value; setVision(value);
  }, []);
  const load = useCallback(async () => {
    try { accept(await api<Vision>(`${base}/status`)); }
    catch { if (mounted.current) setObservationMessage("Camera observations are unavailable. Your live preview still works."); }
  }, [accept, base]);

  const stopObservations = useCallback(async () => {
    observing.current = false;
    controller.current?.abort();
    if (mounted.current) setMonitoring(false);
    const state = current.current;
    const owned = ownsObservations.current;
    ownsObservations.current = false;
    if (owned && state?.enabled) {
      try { accept(await mutate<Vision>(`${base}/session`, "POST", { enabled: false, expected_revision: state.revision })); }
      catch { if (mounted.current) setObservationMessage("Sampling has stopped. The observation service could not be reached."); }
    }
  }, [accept, base]);

  const release = useCallback(() => {
    lease.current.stop(); controller.current?.abort();
    if (video.current) video.current.srcObject = null;
    if (mounted.current) setCamera(false);
  }, []);

  const startCamera = useCallback(async () => {
    if (!activeRef.current || !mounted.current || document.hidden || lease.current.pending || Boolean(lease.current.stream)) return;
    if (!navigator.mediaDevices?.getUserMedia) { setMessage("This browser cannot open a camera. Use a browser with camera support on HTTPS or localhost."); return; }
    setStarting(true); setMessage("");
    try {
      const stream = await lease.current.start(navigator.mediaDevices);
      if (!stream) return;
      if (!mounted.current || !activeRef.current || document.hidden || !wanted.current) { release(); return; }
      if (video.current) { video.current.srcObject = stream; await video.current.play(); }
      if (lease.current.stream !== stream || !mounted.current) return;
      setCamera(true);
      stream.getVideoTracks()[0].onended = () => {
        wanted.current = false; release(); void stopObservations();
        if (mounted.current) setMessage("Your camera disconnected or permission was revoked. Reconnect it, then turn the camera on again.");
      };
    } catch (e) {
      release();
      if (mounted.current) { wanted.current = false; setMessage(cameraError(e as Error)); }
    } finally { if (mounted.current) setStarting(false); }
  }, [release, stopObservations]);

  useEffect(() => {
    mounted.current = true;
    const cameraLease = lease.current;
    void load();
    return () => { mounted.current = false; cameraLease.stop(); controller.current?.abort(); void stopObservations(); };
  }, [load, stopObservations]);

  useEffect(() => {
    activeRef.current = active;
    const timer = window.setTimeout(() => {
      if (active && wanted.current) void startCamera();
      else if (!active) { release(); void stopObservations(); }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [active, startCamera, release, stopObservations]);

  useEffect(() => {
    const visibility = () => {
      if (document.hidden) { release(); void stopObservations(); }
      else if (activeRef.current && wanted.current) void startCamera();
    };
    const fullScreen = () => setExpanded(document.fullscreenElement === panel.current);
    document.addEventListener("visibilitychange", visibility);
    document.addEventListener("fullscreenchange", fullScreen);
    return () => { document.removeEventListener("visibilitychange", visibility); document.removeEventListener("fullscreenchange", fullScreen); };
  }, [release, startCamera, stopObservations]);

  useEffect(() => {
    if (!camera || !monitoring || !active) return;
    const sample = async (sequence: number) => {
      const element = video.current, state = current.current, stream = lease.current.stream;
      if (!element || element.readyState < 2 || !element.videoWidth || !state?.enabled || !stream || !observing.current) return;
      const canvas = document.createElement("canvas");
      const scale = Math.min(640 / element.videoWidth, 640 / element.videoHeight, 1);
      canvas.width = Math.round(element.videoWidth * scale); canvas.height = Math.round(element.videoHeight * scale);
      canvas.getContext("2d")?.drawImage(element, 0, 0, canvas.width, canvas.height);
      const captured = new Date().toISOString();
      let blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/jpeg", .85));
      if (blob && blob.size > 131072) blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/jpeg", .65));
      canvas.width = canvas.height = 0;
      if (!blob || blob.size > 131072 || lease.current.stream !== stream || !observing.current) return;
      const form = new FormData(); form.set("image", blob, "sample.jpg"); form.set("revision", String(state.revision)); form.set("sequence", String(sequence)); form.set("captured_at", captured);
      const session = await api<Session>("/auth/session");
      if (lease.current.stream !== stream || !observing.current || !activeRef.current) return;
      controller.current = new AbortController();
      const response = await fetch(`/api/v1${base}/frame`, { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": session.csrf_token }, body: form, signal: AbortSignal.any([controller.current.signal, AbortSignal.timeout(10000)]) });
      if (response.status === 429) return;
      if (!response.ok) throw new Error("Camera observations paused because the service could not process a sample. Your preview remains live.");
      const next: Vision = await response.json();
      if (lease.current.stream !== stream || !observing.current || next.revision !== current.current?.revision) return;
      accept(next);
      if (!next.enabled || next.error_code) { setObservationMessage("Camera observations are unavailable. Your preview remains live."); void stopObservations(); }
    };
    const timer = window.setInterval(() => void gate.current.run(sample).catch((e: Error) => {
      if (e.name !== "AbortError" && mounted.current) { setObservationMessage(e.message); void stopObservations(); }
    }), vision?.sampling.interval_ms || 1000);
    return () => window.clearInterval(timer);
  }, [active, camera, monitoring, base, accept, stopObservations, vision?.sampling.interval_ms]);

  async function startObservations() {
    const stream = lease.current.stream;
    if (!stream) return;
    setMonitorBusy(true); setObservationMessage(""); ownsObservations.current = true;
    try {
      const latest = await api<Vision>(`${base}/status`);
      const state = await mutate<Vision>(`${base}/session`, "POST", { enabled: true, expected_revision: latest.revision });
      if (!mounted.current || lease.current.stream !== stream || !activeRef.current || !ownsObservations.current) {
        await mutate(`${base}/session`, "POST", { enabled: false, expected_revision: state.revision }); return;
      }
      gate.current.sequence = state.sequence + 1;
      accept(state); observing.current = true; setMonitoring(true);
    } catch (e) { ownsObservations.current = false; if (mounted.current) setObservationMessage((e as Error).message); }
    finally { if (mounted.current) setMonitorBusy(false); }
  }

  function toggleCamera() {
    if (camera || starting) { wanted.current = false; release(); void stopObservations(); }
    else { wanted.current = true; void startCamera(); }
  }

  async function fullscreen() {
    try { if (document.fullscreenElement === panel.current) await document.exitFullscreen(); else await panel.current?.requestFullscreen(); }
    catch { setMessage("Full-screen preview is unavailable in this browser. You can keep using the preview here."); }
  }

  const warnings = monitoring ? (vision?.events || []).filter(event =>
    !event.ended_at && ["PHONE_DETECTED", "MULTIPLE_PERSONS_DETECTED", "CANDIDATE_ABSENT"].includes(event.event_type)
  ) : [];
  return <section ref={panel} className="interview-camera" aria-label="Your live camera preview">
    <header className="camera-heading"><div><p className="eyebrow">YOUR CAMERA</p><h2>You’re in the room.</h2></div>
      <span className={`camera-status ${camera ? "is-live" : ""}`} role="status"><i />{camera ? "Live" : starting ? "Connecting" : active ? "Off" : "Paused"}</span></header>
    <div className={`camera-stage ${camera ? "is-on" : ""}`}>
      <video ref={video} autoPlay muted playsInline className={mirrored ? "is-mirrored" : ""} aria-label="Live video of you" />
      {!camera && <div className="camera-placeholder"><span><Icon name="camera" size={30} /></span><strong>{starting ? "Opening your camera…" : !active ? "Camera paused" : "Your space to show up"}</strong>
        <p>{starting ? "Allow camera access in your browser to see your live preview." : !active ? "Resume the interview to return to your camera." : "Turn on your camera to see yourself as you answer."}</p></div>}
      <div className="camera-nameplate"><span>You</span><small>{monitoring ? "Observations enabled" : "Private preview"}</small></div>
    </div>
    <div className="camera-toolbar"><button type="button" className={`camera-toggle ${camera ? "is-on" : ""}`} aria-label={starting ? "Cancel camera connection" : camera ? "Turn camera off" : "Turn camera on"} aria-pressed={camera} disabled={!active} onClick={toggleCamera}>
      <Icon name={camera ? "camera" : "cameraOff"} size={18} />{starting ? "Cancel" : camera ? "Camera on" : "Turn camera on"}</button>
      <div><button type="button" className="camera-icon-button" aria-label="Mirror preview" title="Mirror preview" aria-pressed={mirrored} onClick={() => setMirrored(x => !x)}><Icon name="mirror" size={18} /></button>
        <button type="button" className="camera-icon-button" aria-label={expanded ? "Exit full screen" : "Expand camera preview"} title={expanded ? "Exit full screen" : "Expand preview"} onClick={() => void fullscreen()}><Icon name="expand" size={18} /></button></div></div>
    {message && <p className="camera-message" role="alert">{message}</p>}
    <p className="camera-privacy"><Icon name="shield" size={14} />{monitoring ? "Only sampled observations are saved. Video is not recorded." : "Visible only to you. Video is not recorded or uploaded."}</p>
    <div className="camera-monitor-status">
      <strong>{monitoring ? "Observation checks active" : "Preview only — detection is off"}</strong>
      <button type="button" className="secondary-button" disabled={monitorBusy || !camera || !active || !monitoring && !vision?.provider.available} onClick={() => void (monitoring ? stopObservations() : startObservations())}>
        {monitorBusy ? "Connecting…" : monitoring ? "Stop observations" : "Enable observations"}</button>
      <small>Optional local checks for a phone, extra person, or an empty camera view.</small>
      {observationMessage && <p role="status">{observationMessage}</p>}
    </div>
    {warnings.length > 0 && <div className="camera-detection-warning" role="alert">
      <strong>Please check your camera view</strong>
      {warnings.map(event => <p key={event.id}>{event.event_type === "PHONE_DETECTED" ? "A possible phone is visible. Move it out of the camera view." : event.event_type === "MULTIPLE_PERSONS_DETECTED" ? "Another person may be visible. Please keep only yourself in the frame." : "No person is currently detected. Please return to the camera view."}</p>)}
      <small>Automated observations can be mistaken and do not affect your score.</small>
    </div>}
    <details className="camera-observations"><summary>Observation details & timeline</summary>
      <p>Enable occasional image checks for a timestamped timeline. Samples are processed on the IntervAI server and discarded. Observations do not affect interview scores.</p>
      {!vision?.provider.available && <p className="subtle-copy">{vision?.provider.message || "Checking observation availability…"}</p>}
      {!!vision?.events.length && <><h3>Observation timeline</h3><p className="subtle-copy">Observations may be inaccurate and do not prove misconduct.</p><ol className="vision-timeline">{vision.events.map(event => <li key={event.id}>
        <time dateTime={event.started_at}>{new Date(event.started_at).toLocaleTimeString()}</time><strong>{labels[event.event_type] || "Camera observation"}</strong>
        {event.duration_ms !== null && <small>{(event.duration_ms / 1000).toFixed(1)} seconds</small>}</li>)}</ol></>}
    </details>
  </section>;
}
