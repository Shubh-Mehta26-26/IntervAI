"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { mutate } from "@/lib/intelligence";
import type { Attempt, LearningItem, LearningPlan } from "@/lib/learning";
import type { ProviderStatus } from "@/lib/interviews";
import { ImprovementTimeline } from "./learning-timeline";

export function LearningDetail({ identifier }: { identifier: string }) {
  const router = useRouter();
  const [plan, setPlan] = useState<LearningPlan>();
  const [provider, setProvider] = useState<ProviderStatus>();
  const [selectedId, setSelectedId] = useState<string>();
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const load = useCallback(async () => {
    const saved = await api<LearningPlan>(`/learning/plans/${identifier}`);
    setPlan(saved);
    return saved;
  }, [identifier]);

  useEffect(() => {
    let active = true;
    api<LearningPlan>(`/learning/plans/${identifier}`).then(value => { if (active) setPlan(value); })
      .catch(e => { if (active) setError(e.message); });
    api<ProviderStatus>("/interviews/provider").then(value => { if (active) setProvider(value); }).catch(() => {});
    return () => { active = false; };
  }, [identifier]);

  async function act(path: string, body: unknown, label: string, message: string) {
    setBusy(label); setError(""); setNotice("");
    try { const saved = await mutate<LearningPlan>(path, "POST", body); setPlan(saved); setNotice(message); return saved; }
    catch (e) {
      setError((e as Error).message);
      if (e instanceof ApiError && e.status === 409) await load().catch(() => {});
    } finally { setBusy(""); }
  }

  async function practice(itemId: string) {
    setBusy("practice"); setError("");
    try {
      const attempt = await mutate<Attempt>(`/learning/items/${itemId}/practice`, "POST", { idempotency_key: crypto.randomUUID() });
      router.push(`/learning/practice/${attempt.id}`);
    } catch (e) { setError((e as Error).message); setBusy(""); }
  }

  async function generate(item: LearningItem) {
    setBusy("generate"); setError(""); setNotice("");
    try { await mutate(`/learning/items/${item.id}/generate`, "POST", { expected_revision: item.content_revision }); await load(); setNotice("Your expanded explanation has been saved."); }
    catch (e) { setError((e as Error).message); } finally { setBusy(""); }
  }

  async function retry() {
    if (!plan) return;
    setBusy("retry"); setError("");
    try {
      const attempt = await mutate<Attempt>("/learning/retries", "POST", { mode: "multiple", gap_ids: plan.targets.map(x => x.gap_id),
        plan_id: plan.id, job_id: plan.job_id, idempotency_key: crypto.randomUUID() });
      router.push(`/learning/retry/${attempt.id}`);
    } catch (e) { setError((e as Error).message); setBusy(""); }
  }

  if (!plan) return <div className="learning-workspace"><p role={error ? "alert" : "status"}>{error || "Opening your saved learning plan…"}</p>
    {error && <button className="secondary-button" onClick={() => void load().then(() => setError("")).catch(e => setError(e.message))}>Try again</button>}</div>;

  const item = plan.items.find(x => x.id === selectedId) || plan.items.find(x => x.status !== "completed") || plan.items[0];
  const started = plan.actions.some(x => x.kind === "start_learning");
  const guided = plan.context.mode === "guided";
  const recentPractice = item ? plan.attempts.find(x => x.kind === "practice" && x.item_id === item.id) : undefined;

  async function complete() {
    if (!item || !plan) return;
    const saved = await act(`/learning/items/${item.id}/complete`, { expected_revision: plan.revision }, "complete", "Lesson completed. Your progress is saved.");
    if (saved) {
      const next = saved.items.find(x => x.ordinal > item.ordinal && x.status !== "completed") || saved.items.find(x => x.status !== "completed");
      setSelectedId(next?.id || item.id);
    }
  }

  return <div className="learning-workspace learning-detail">
    <Link href="/learning" className="text-link">← All learning plans</Link>
    <header className="learning-detail-header"><p className="eyebrow">{guided ? "YOUR STUDY PLAN" : "YOUR INTERVIEW RECOVERY PLAN"}</p>
      <h1>{plan.title}</h1><p>{plan.objective}</p>
      <div className="learning-progress-row"><progress value={plan.progress.completed} max={plan.progress.total || 1} aria-label="Plan progress" />
        <strong>{plan.progress.completed} / {plan.progress.total} completed</strong></div>
      <p className="subtle-copy">{plan.status === "completed" ? "All lessons complete. Revisit any lesson or try explaining the concepts in an interview." : "Your progress saves as you go. You can return at any time."}</p>
    </header>
    {error && <div className="error-message" role="alert">{error}</div>}
    {notice && <div className="learning-notice" role="status">{notice}</div>}
    {plan.stale && <p className="provider-warning">New interview evidence is available. This plan keeps the baseline it was created with.</p>}
    {!started && <div className="content-card learning-start"><div><strong>Ready for a small step?</strong><p>Begin with the first lesson, then work at your own pace.</p></div>
      <button className="action-button" disabled={!!busy} onClick={() => void act(`/learning/plans/${plan.id}/start`, { expected_revision: plan.revision }, "start", "Your plan has started. Open a lesson below.")}>{busy === "start" ? "Starting…" : "Start my plan ↗"}</button></div>}

    {item && <div className="learning-study-grid"><aside className="content-card learning-lesson-nav" aria-label="Lessons in this plan">
      <h2>Your lessons</h2><ol>{plan.items.map(lesson => <li key={lesson.id}><button className={item.id === lesson.id ? "is-current" : ""}
        disabled={!!busy} aria-current={item.id === lesson.id ? "step" : undefined} onClick={() => { setSelectedId(lesson.id); setNotice(""); }}>
        <span className={`learning-step ${lesson.status === "completed" ? "is-done" : ""}`} aria-label={lesson.status === "completed" ? "Completed" : undefined}>{lesson.status === "completed" ? "✓" : lesson.ordinal}</span>
        <span><strong>{lesson.title}</strong><small>{lesson.topic} · {lesson.effort_minutes} min</small></span></button></li>)}</ol>
      <small>Lesson completion tracks study activity. Interview evaluations measure skill progress.</small>
    </aside>
    <article className="content-card learning-lesson" key={item.id}>
      <div className="learning-heading"><p className="eyebrow">LESSON {item.ordinal} OF {plan.items.length} · {item.topic}</p>
        <span className="learning-tag">{item.status === "completed" ? "✓ Complete" : `${item.effort_minutes} minutes`}</span></div>
      <h2>{item.title}</h2>
      <section><h3>Understand the idea</h3><p className="lesson-explanation">{item.content.explanation}</p>
        <small className="source-label">{item.content.grounding_status === "authored" ? "IntervAI starter lesson" : item.content.grounding_status === "insufficient" ? "Learning outline · limited retrieved source coverage" : "Explanation with retrieved reference material"}</small></section>
      {item.content.examples.length > 0 && <section><h3>Walk through an example</h3>{item.content.examples.map((example, index) => <pre className="learning-example" key={index}><code>{example}</code></pre>)}</section>}
      <section className="learning-exercise"><h3>Try it yourself</h3><p>{item.content.practice_question}</p>
        {item.content.hints.length > 0 && <details><summary>Give me a hint</summary><ul>{item.content.hints.map(hint => <li key={hint}>{hint}</li>)}</ul></details>}</section>
      {item.content.quiz && <LessonCheck key={item.id} item={item} busy={!!busy} onCheck={index => act(`/learning/items/${item.id}/check`, { selected_index: index, expected_revision: plan.revision }, "check", "Your self-check is saved.")} />}
      {item.content.sources.length > 0 && <details><summary>Reference material</summary>{item.content.sources.map(source => <section key={source.chunk_id}><h3>{source.title}</h3><small>{source.source}</small><p className="lesson-explanation">{source.content}</p></section>)}</details>}
      <div className="learning-lesson-footer"><button className="action-button" disabled={!!busy || item.status === "completed"} onClick={() => void complete()}>
        {busy === "complete" ? "Saving…" : item.status === "completed" ? "✓ Lesson completed" : "Complete lesson & continue →"}</button>
        {recentPractice && <Link className="text-link" href={`/learning/practice/${recentPractice.id}`}>{recentPractice.status === "completed" ? "Review practice feedback" : "Continue saved practice"} ↗</Link>}</div>
      <details className="learning-ai-tools"><summary>Practise with your AI interviewer</summary>
        <p>Explain this lesson in your own words and get feedback. You can also ask AI to expand the explanation.</p>
        {!provider?.configured && <p className="subtle-copy">{provider ? provider.message : "Checking AI availability…"} Lessons and self-checks remain available.</p>}
        <div className="room-actions"><button className="secondary-button" disabled={!!busy || !provider?.configured} onClick={() => void practice(item.id)}>{busy === "practice" ? "Opening…" : "Practise this lesson ↗"}</button>
          <button className="text-button" disabled={!!busy || !provider?.configured} onClick={() => void generate(item)}>{busy === "generate" ? "Expanding explanation…" : "Expand lesson with AI"}</button></div>
      </details>
    </article></div>}

    {!guided && <section className="content-card"><h2>Check your progress in an interview</h2><p>Fresh questions check the areas behind this plan. Completing a lesson does not automatically resolve a knowledge gap.</p>
      <button className="secondary-button" disabled={!!busy || !provider?.configured || !plan.targets.length} onClick={() => void retry()}>Retry these interview areas ↗</button>
      <details><summary>Why these topics?</summary>{plan.targets.map(target => <div key={target.gap_id}><Link href={`/knowledge-gaps/${target.gap_id}`}>View original evidence ↗</Link><ul>{target.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></div>)}</details>
    </section>}
    {plan.status === "completed" && <section className="content-card learning-finish"><h2>You followed through. Keep going.</h2><p>Practise what you learned in a fresh interview, or choose your next focus.</p>
      <div className="room-actions"><Link className="action-button" href="/interviews/new">Start an interview ↗</Link><Link className="secondary-button" href="/learning">Choose another topic</Link></div></section>}
    {plan.attempts.some(x => x.kind === "retry") && <ImprovementTimeline attempts={plan.attempts} />}
  </div>;
}

function LessonCheck({ item, busy, onCheck }: { item: LearningItem; busy: boolean; onCheck: (index: number) => Promise<unknown> }) {
  const [choice, setChoice] = useState<number | null>(item.check_result?.selected_index ?? null);
  const quiz = item.content.quiz!;
  const result = item.check_result;
  return <section className="learning-check"><p className="eyebrow">QUICK SELF-CHECK</p><h3>{quiz.question}</h3>
    <fieldset disabled={busy}><legend className="sr-only">Choose your answer</legend>{quiz.options.map((option, index) => <label className={choice === index ? "is-selected" : ""} key={option}>
      <input type="radio" name={`quiz-${item.id}`} checked={choice === index} onChange={() => setChoice(index)} /><span>{option}</span></label>)}</fieldset>
    <button className="secondary-button" disabled={busy || choice === null} onClick={() => choice !== null && void onCheck(choice)}>Check my answer</button>
    {result && <div className={`learning-check-feedback ${result.correct ? "is-correct" : ""}`} role="status"><strong>{result.correct ? "You’ve got it." : "A useful thing to revisit."}</strong><p>{result.feedback}</p>
      {!result.correct && <small>Review the example and try another answer when you’re ready.</small>}</div>}
  </section>;
}
