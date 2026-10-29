"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { mutate, type Job } from "@/lib/intelligence";
import type { Attempt, LearningCatalog, LearningPlan, LearningProgress, LearningTopic } from "@/lib/learning";
import { ImprovementTimeline } from "./learning-timeline";

export function LearningOverview({ compact = false }: { compact?: boolean }) {
  const router = useRouter();
  const [data, setData] = useState<LearningProgress>();
  const [catalog, setCatalog] = useState<LearningCatalog>();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState("");
  const [topics, setTopics] = useState<string[]>([]);
  const [gaps, setGaps] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [jobsError, setJobsError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const request = useRef<{ signature: string; key: string } | null>(null);

  useEffect(() => {
    if (compact) return;
    let active = true;
    api<Job[]>("/jobs").then(value => { if (active) setJobs(value); })
      .catch(e => { if (active) setJobsError(e.message); });
    return () => { active = false; };
  }, [compact]);

  useEffect(() => {
    let active = true;
    const query = jobId ? `?job_id=${jobId}` : "";
    const load = async () => {
      try {
        const [progress, choices] = await Promise.all([
          api<LearningProgress>(`/candidates/me/progress${query}`),
          compact ? Promise.resolve(undefined) : api<LearningCatalog>(`/learning/catalog${query}`),
        ]);
        if (!active) return;
        setData(progress);
        if (choices) {
          setCatalog(choices);
          setTopics(choices.suggested.slice(0, 2).map(x => x.id));
        }
        setError("");
        setGaps([]);
      } catch (e) { if (active) setError((e as Error).message); }
      finally { if (active) setLoading(false); }
    };
    void load();
    return () => { active = false; };
  }, [jobId, compact, refresh]);

  async function createPlan(gapIds?: string[]) {
    const payload = { gap_ids: gapIds || [], topics: gapIds ? [] : topics, job_id: jobId || null };
    const signature = JSON.stringify(payload);
    if (request.current?.signature !== signature) request.current = { signature, key: crypto.randomUUID() };
    setBusy(true); setError("");
    try {
      const plan = await mutate<LearningPlan>("/learning/plans", "POST", { ...payload, idempotency_key: request.current.key });
      router.push(`/learning/${plan.id}`);
    } catch (e) { setError((e as Error).message); setBusy(false); }
  }

  async function retry() {
    setBusy(true); setError("");
    try {
      const attempt = await mutate<Attempt>("/learning/retries", "POST", {
        mode: gaps.length ? "multiple" : "recommended", gap_ids: gaps,
        job_id: jobId || null, idempotency_key: crypto.randomUUID(),
      });
      router.push(`/learning/retry/${attempt.id}`);
    } catch (e) { setError((e as Error).message); setBusy(false); }
  }

  function toggleTopic(id: string) {
    setTopics(previous => previous.includes(id) ? previous.filter(x => x !== id) : [...previous, id]);
  }

  function topicCard(topic: LearningTopic) {
    const selected = topics.includes(topic.id);
    return <label className={`learning-topic ${selected ? "is-selected" : ""}`} key={topic.id}>
      <span className="learning-topic-top"><span className="learning-tag">{topic.category}</span>
        <input type="checkbox" checked={selected} disabled={busy || loading || !selected && topics.length >= 4}
          onChange={() => toggleTopic(topic.id)} /></span>
      <strong>{topic.title}</strong><span>{topic.description}</span>
      <small>{topic.lesson_count} lessons · {topic.effort_minutes} min</small>
    </label>;
  }

  if (!data) return <section className="learning-workspace">
    <p role={error ? "alert" : "status"}>{error || "Loading your learning workspace…"}</p>
    {error && <button className="secondary-button" onClick={() => { setLoading(true); setRefresh(x => x + 1); }}>Try again</button>}
  </section>;

  const suggestedIds = catalog?.suggested.map(x => x.id) || [];
  const suggestedTopics = catalog?.topics.filter(x => suggestedIds.includes(x.id)) || [];
  const otherTopics = catalog?.topics.filter(x => !suggestedIds.includes(x.id)) || [];
  const totalMinutes = catalog?.topics.filter(x => topics.includes(x.id)).reduce((sum, x) => sum + x.effort_minutes, 0) || 0;
  const completed = data.plans.reduce((sum, x) => sum + x.progress.completed, 0);

  return <section className={`learning-workspace ${compact ? "learning-compact" : ""}`}>
    {!compact && <header className="learning-page-header"><p className="eyebrow">YOUR NEXT STEP FORWARD</p>
      <h1>A little learning. <em>More confidence.</em></h1>
      <p>Choose what you want to improve. Learn the idea, try an example, and put it into practice.</p>
      <div className="learning-summary"><span><strong>{data.plans.filter(x => x.status === "active").length}</strong> active plans</span>
        <span><strong>{completed}</strong> lessons completed</span><span><strong>{data.attempts.filter(x => x.kind === "practice").length}</strong> practice attempts</span></div>
    </header>}
    {error && <div className="error-message" role="alert"><p>{error}</p>
      <button className="text-button" disabled={busy} onClick={() => { setLoading(true); setRefresh(x => x + 1); }}>Reload learning data</button></div>}

    {!compact && catalog && <section className="content-card learning-builder" id="plan-builder" aria-busy={loading}>
      <div className="learning-heading"><div><p className="eyebrow">BUILD YOUR PLAN</p><h2>What would you like to work on?</h2></div>
        <span className="learning-tag">Works before your first interview</span></div>
      <label className="learning-job">Target job <span className="subtle-copy">optional</span>
        <select value={jobId} disabled={busy} onChange={e => { setJobId(e.target.value); setLoading(true); }}>
          <option value="">Choose my own focus</option>{jobs.map(job => <option value={job.id} key={job.id}>{job.title}</option>)}
        </select></label>
      {jobsError && <p className="subtle-copy">Job targets could not be loaded. You can still choose topics and create a plan.</p>}
      <p className="subtle-copy">{loading ? "Finding topics for this job…" : catalog.job_title ? `Suggested for ${catalog.job_title}. Choose up to four topics.` : catalog.resume_name ? "Suggested from skills in your latest resume. Choose up to four topics, or explore others." : "Start with a suggested topic, or explore the full collection. Choose up to four."}</p>
      <div className="learning-topic-grid">{suggestedTopics.map(topicCard)}</div>
      {otherTopics.length > 0 && <details className="learning-browse"><summary>Explore {otherTopics.length} more topics</summary>
        <div className="learning-topic-grid">{otherTopics.map(topicCard)}</div></details>}
      <div className="learning-builder-footer"><div><strong>{topics.length ? `${topics.length} ${topics.length === 1 ? "topic" : "topics"} selected` : "Choose a topic to begin"}</strong>
        <p>{topics.length ? `${topics.length * 2} short lessons · about ${totalMinutes} minutes, at your pace` : "Lessons, worked examples, and self-checks are included."}</p></div>
        <button className="action-button" disabled={busy || loading || !topics.length} onClick={() => void createPlan()}>{busy ? "Opening your plan…" : "Create my learning plan ↗"}</button></div>
    </section>}

    <section className="learning-section"><div className="learning-heading"><h2>{compact ? "Your next learning step" : "Your learning plans"}</h2>
      {compact && <Link className="text-link" href="/learning">Explore learning ↗</Link>}</div>
      {data.plans.length ? <div className="learning-plan-grid">{data.plans.slice(0, compact ? 2 : 50).map(plan =>
        <Link className="content-card learning-plan-card" href={`/learning/${plan.id}`} key={plan.id}>
          <div className="learning-heading"><span className="learning-tag">{plan.context.mode === "guided" ? "Topic learning" : "Interview recovery"}</span>
            <span className={`status-pill ${plan.status === "completed" ? "parsed" : ""}`}>{plan.status === "completed" ? "Completed" : "In progress"}</span></div>
          <h3>{plan.title}</h3><progress value={plan.progress.completed} max={plan.progress.total || 1} aria-label={`${plan.title} progress`} />
          <p>{plan.progress.completed} of {plan.progress.total} lessons completed</p>
          <strong className="learning-continue">{plan.status === "completed" ? "Review your plan" : plan.progress.completed ? "Continue learning" : "Open your first lesson"} ↗</strong>
        </Link>)}</div> : <div className="content-card learning-empty"><span aria-hidden="true">↗</span><h3>Your next skill starts here.</h3>
          <p>Create a plan from a topic or target job. Your lessons and progress will be saved here.</p>
          {compact && <Link className="action-button" href="/learning">Create a learning plan</Link>}</div>}
    </section>

    {!compact && data.recommendations.length > 0 && <section className="learning-section">
      <div><p className="eyebrow">FROM YOUR INTERVIEWS</p><h2>Give these areas another look</h2><p className="subtle-copy">These suggestions come from repeated interview evidence. Select up to six to build a focused plan.</p></div>
      <div className="learning-plan-grid">{data.recommendations.map(rec => <article className="content-card" key={rec.gap_id}>
        <label className="learning-gap-choice"><input type="checkbox" checked={gaps.includes(rec.gap_id)} disabled={busy || !gaps.includes(rec.gap_id) && gaps.length >= 6}
          onChange={e => setGaps(e.target.checked ? [...gaps, rec.gap_id] : gaps.filter(x => x !== rec.gap_id))} /><strong>{rec.subject}</strong></label>
        <p>{rec.topic}</p><details><summary>Why this focus?</summary><ul>{rec.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></details>
        <Link className="text-link" href={`/knowledge-gaps/${rec.gap_id}`}>View interview evidence ↗</Link>
      </article>)}</div>
      <div className="room-actions"><button className="action-button" disabled={busy || !gaps.length} onClick={() => void createPlan(gaps)}>Create focused plan{gaps.length ? ` (${gaps.length})` : ""}</button>
        <button className="secondary-button" disabled={busy} onClick={() => void retry()}>Retry {gaps.length ? "selected" : "recommended"} areas ↗</button></div>
    </section>}
    {data.attempts.some(x => x.kind === "retry") && <ImprovementTimeline attempts={data.attempts} compact={compact} />}
  </section>;
}
