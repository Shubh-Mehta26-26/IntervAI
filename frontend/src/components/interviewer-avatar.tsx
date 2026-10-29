"use client";

import { useEffect, useId, useRef, type RefObject } from "react";
import type { AvatarAudio } from "@/lib/avatar-audio.mjs";

export type AvatarState = "idle" | "speaking" | "listening" | "thinking" | "paused" | "error";
const captions: Record<AvatarState, string> = {
  idle: "Ready when you are", speaking: "Asking your question", listening: "Your turn — I’m listening",
  thinking: "Preparing your next step", paused: "Take your time", error: "Let’s reconnect",
};

// Smoothly moving control points create flowing light, rather than a rotating globe.
function ribbonPath(phase: number, lane: number) {
  const t = phase + lane * 2.1;
  const wave = Math.sin(t), swell = Math.cos(t * .73);
  return `M 77 ${152 + wave * 30} C ${104 + swell * 28} ${38 + wave * 24}, ${218 + wave * 40} ${82 + swell * 34}, 180 159 S ${258 - swell * 35} ${283 + wave * 18}, 283 ${162 - wave * 38}`;
}

export function InterviewerAvatar({ state, audio, signal = 0, label }: {
  state: AvatarState; audio?: RefObject<AvatarAudio | undefined>; signal?: number; label?: string;
}) {
  const id = useId().replaceAll(":", "");
  const scene = useRef<HTMLDivElement>(null);
  const ribbons = useRef<(SVGPathElement | null)[]>([]);
  const phase = useRef(0);
  const micLevel = useRef(signal);
  useEffect(() => { micLevel.current = signal; }, [signal]);
  useEffect(() => {
    const active = state !== "paused" && state !== "error";
    const soundActive = state === "speaking" || state === "listening";
    let frame = 0, previous = 0, smoothed = 0;
    const tick = (now: number) => {
      if (document.hidden) return;
      // Cap DOM updates to 30 fps; no React rerenders on audio frames.
      if (previous && now - previous < 32) { frame = requestAnimationFrame(tick); return; }
      const elapsed = previous ? Math.min(80, now - previous) : 33;
      previous = now;
      const raw = state === "speaking" ? audio?.current?.sample() || 0
        : state === "listening" ? micLevel.current * 12 : 0;
      const level = Number.isFinite(raw) ? Math.max(0, Math.min(1, raw)) : 0;
      smoothed += (level - smoothed) * (1 - Math.exp(-elapsed / 90));
      scene.current?.style.setProperty("--signal", String(smoothed));
      scene.current?.style.setProperty("--orb-scale", String(!active ? 1 : 1 + Math.sin(phase.current * 1.8) * .025 + smoothed * .1));
      if (active) {
        const pace = state === "thinking" ? 1.65 : state === "speaking" ? 1.35 : .85;
        phase.current += elapsed / 1000 * (pace + smoothed * 1.15);
        ribbons.current.forEach((path, n) => path?.setAttribute("d", ribbonPath(phase.current, n)));
        scene.current?.style.setProperty("--plasma-turn", `${phase.current * 24}deg`);
      }
      scene.current?.style.setProperty("--orb-lift", `${active ? Math.sin(phase.current * 1.3) * 5 : 0}px`);
      if (soundActive || (active)) frame = requestAnimationFrame(tick);
    };
    const resume = () => {
      cancelAnimationFrame(frame);
      scene.current?.classList.toggle("orb-suspended", document.hidden);
      previous = 0;
      if (!document.hidden) frame = requestAnimationFrame(tick);
    };
    resume();
    document.addEventListener("visibilitychange", resume);
    return () => { cancelAnimationFrame(frame); document.removeEventListener("visibilitychange", resume); };
  }, [state, audio]);

  return <div className={`live-avatar live-avatar--plasma live-avatar--${state} orb-motion-enabled`}>
    <div className="live-avatar-scene voice-orb-scene" ref={scene}>
      <span className="live-avatar-badge">IntervAI <span>AI interviewer</span></span>
      <svg viewBox="50 35 260 275" role="img" aria-label={`Voice orb: ${label || captions[state]}`}>
        <defs>
          <radialGradient id={`${id}-halo`}><stop stopColor="#b09ae8" stopOpacity=".28"/><stop offset="1" stopColor="#d5bcf5" stopOpacity="0"/></radialGradient>
          <radialGradient id={`${id}-pearl`} cx=".34" cy=".25" r=".83"><stop stopColor="#fffaff"/><stop offset=".42" stopColor="#efe5fc" stopOpacity=".8"/><stop offset=".73" stopColor="#d7c3ef" stopOpacity=".7"/><stop offset="1" stopColor="#bca3df" stopOpacity=".85"/></radialGradient>
          <linearGradient id={`${id}-flow`} x1=".1" y1="0" x2=".9" y2="1"><stop stopColor="#8765d3"/><stop offset=".34" stopColor="#8dbbe7"/><stop offset=".62" stopColor="#ca8be2"/><stop offset="1" stopColor="#f7b28e"/></linearGradient>
          <linearGradient id={`${id}-rim`} x1="0" y1="0" x2="1" y2="1"><stop stopColor="#fff"/><stop offset=".3" stopColor="#b59ce8"/><stop offset=".65" stopColor="#f8c3cb"/><stop offset="1" stopColor="#fff"/></linearGradient>
          <radialGradient id={`${id}-shine`} cx=".28" cy=".18" r=".8"><stop stopColor="#fff" stopOpacity=".9"/><stop offset=".36" stopColor="#fff" stopOpacity="0"/><stop offset=".85" stopColor="#fff" stopOpacity="0"/><stop offset="1" stopColor="#fff" stopOpacity=".55"/></radialGradient>
          <filter id={`${id}-soft`} x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="9"/></filter>
          <filter id={`${id}-rim-soft`} x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3"/></filter>
          <clipPath id={`${id}-clip`}><circle cx="180" cy="159" r="100"/></clipPath>
        </defs>
        <ellipse cx="180" cy="280" rx="66" ry="8" fill="#b098d1" opacity=".16" filter={`url(#${id}-soft)`}/>
        <circle className="plasma-halo" cx="180" cy="159" r="140" fill={`url(#${id}-halo)`}/>
        <g className="voice-orb-core">
          <circle cx="180" cy="159" r="100" fill={`url(#${id}-pearl)`}/>
          <g clipPath={`url(#${id}-clip)`}>
            <g className="plasma-current" fill="none" stroke={`url(#${id}-flow)`} strokeLinecap="round" filter={`url(#${id}-soft)`}>
              {[0,1,2].map(n => <path key={n} ref={element => { ribbons.current[n] = element; }} d={ribbonPath(0,n)} strokeWidth={n === 1 ? 30 : 20} opacity={n === 1 ? .85 : .65} transform={`rotate(${n * 115} 180 159)`}/>)}
            </g>
            <circle cx="180" cy="159" r="100" fill={`url(#${id}-shine)`}/>
          </g>
          <circle className="plasma-edge-glow" cx="180" cy="159" r="99" fill="none" stroke={`url(#${id}-rim)`} strokeWidth="7" filter={`url(#${id}-rim-soft)`}/>
          <circle cx="180" cy="159" r="100" fill="none" stroke={`url(#${id}-rim)`} strokeWidth="1.8"/>
          <path d="M107 102 A91 91 0 0 1 172 68" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" opacity=".7"/>
        </g>
        <g className="plasma-wave" stroke="currentColor" strokeWidth="3" strokeLinecap="round" aria-hidden="true">
          {[0,1,2,3,4].map(n => <line key={n} x1={162+n*9} x2={162+n*9} y1="291" y2="295" style={{ transformOrigin:`${162+n*9}px 293px`,transform:`scaleY(calc(1 + var(--signal) * ${n === 2 ? 5 : n % 2 ? 3 : 1.5}))` }}/>)}
        </g>
      </svg>
    </div>
    <div className="live-avatar-caption"><span className="avatar-state-dot"/><span role="status" aria-live="polite">{label || captions[state]}</span></div>
  </div>;
}
