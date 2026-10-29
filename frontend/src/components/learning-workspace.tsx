"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { mutate } from "@/lib/intelligence";
import type { Attempt } from "@/lib/learning";
import type { Interview, ProviderStatus } from "@/lib/interviews";
import { ImprovementTimeline } from "./learning-timeline";
export { LearningOverview } from "./learning-overview";
export { LearningDetail } from "./learning-detail";
export { ImprovementTimeline } from "./learning-timeline";

export function LearningAttemptRoom({ identifier, retry = false }: { identifier: string; retry?: boolean }) {
  const [attempt, setAttempt] = useState<Attempt>();
  const [interview, setInterview] = useState<Interview>();
  const [provider, setProvider] = useState<ProviderStatus>();
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const answerKey = useRef<string | null>(null);
  const router = useRouter();
  const load = useCallback(async () => { const a = await api<Attempt>(`/learning/attempts/${identifier}`); setAttempt(a); setInterview(await api<Interview>(`/interviews/${a.interview_id}`)); }, [identifier]);
  useEffect(() => { const timer = window.setTimeout(() => void load().catch(e => setError(e.message)), 0); void api<ProviderStatus>("/interviews/provider").then(setProvider).catch(e => setError(e.message)); return () => window.clearTimeout(timer); }, [load]);
  useEffect(() => { if (interview?.status !== "evaluating") return; const timer = window.setInterval(() => void load().catch(e => setError(e.message)), 1800); return () => window.clearInterval(timer); }, [interview?.status, load]);
  async function submit() {
    if (!attempt || !interview?.current) return; setBusy(true); setError(""); answerKey.current ||= crypto.randomUUID();
    try { await mutate(`/learning/items/${attempt.item_id}/practice/${attempt.id}/submit`, "POST", { question_id: interview.current.id, text: answer, expected_revision: interview.revision, idempotency_key: answerKey.current }); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function startRetry() {
    if (!interview) return; setBusy(true); setError("");
    try { if (interview.status === "created") await mutate(`/interviews/${interview.id}/start`, "POST", { expected_revision: interview.revision }); router.push(`/interviews/${interview.id}`); } catch (e) { setError((e as Error).message); setBusy(false); }
  }
  if (!attempt || !interview) return <p role={error ? "alert" : "status"}>{error || "Loading your persisted attempt…"}</p>;
  return <div className="learning-workspace"><Link className="text-link" href={attempt.plan_id ? `/learning/${attempt.plan_id}` : "/learning"}>← Learning workspace</Link><p className="eyebrow">{retry ? "FOCUSED RETRY" : "TARGETED PRACTICE"}</p><h1>{retry ? "Check your weak areas again." : "Explain it in your own words."}</h1>{error && <p className="error-message" role="alert">{error}</p>}{provider && !provider.configured && <div className="provider-warning"><strong>Provider configuration pending</strong><p>{provider.message}</p><small>Your plan and attempt remain saved.</small></div>}{retry ? <section className="content-card"><p>Fresh questions use the existing adaptive interview room. Hints are disabled for an independent check.</p>{attempt.parent_interview_id && <Link className="text-link" href={`/interviews/${attempt.parent_interview_id}`}>Original interview evidence ↗</Link>}<button disabled={busy || !provider?.configured} className="action-button" onClick={() => void startRetry()}>{interview.status === "created" ? "Start focused retry" : "Open retry interview"} ↗</button><ImprovementTimeline attempts={[attempt]} /></section> : <section className="content-card">{interview.status === "waiting_for_answer" && <><h2>{interview.current?.text}</h2><form onSubmit={e => { e.preventDefault(); void submit(); }}><label>Your answer<textarea rows={8} value={answer} onChange={e => setAnswer(e.target.value)} maxLength={12000} required /></label><button className="action-button" disabled={busy || !answer.trim() || !provider?.configured}>Submit for feedback ↗</button></form><p className="subtle-copy">Practice follows learning material, so it does not count as independent gap-recovery evidence.</p></>}{interview.status === "evaluating" && <p role="status">Your saved answer is being evaluated…</p>}{interview.status === "completed" && <><h2>Practice feedback</h2><p>{interview.practice_feedback?.feedback || "No evaluated answer was submitted."}</p>{interview.practice_feedback && <p>Stored correctness: {Math.round(interview.practice_feedback.correctness * 100)}% · {interview.practice_feedback.grounding_status}</p>}<p>{interview.practice_feedback?.hint}</p>{interview.practice_feedback?.knowledge_evidence.map(source => <p key={source.knowledge_chunk_id}><strong>{source.title}</strong>: {source.claim}</p>)}<button className="secondary-button" disabled={busy} onClick={async () => { setBusy(true); try { const next = await mutate<Attempt>(`/learning/items/${attempt.item_id}/practice`, "POST", { idempotency_key: crypto.randomUUID() }); router.push(`/learning/practice/${next.id}`); setAnswer(""); answerKey.current = null; setBusy(false); } catch (e) { setError((e as Error).message); setBusy(false); } }}>Try another practice attempt</button></>}{["failed", "cancelled", "paused"].includes(interview.status) && <Link href={`/interviews/${interview.id}`}>Review interview status ↗</Link>}</section>}</div>;
}
