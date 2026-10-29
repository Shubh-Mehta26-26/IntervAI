"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { api } from "@/lib/api";
import { mutate } from "@/lib/intelligence";
import type { Job } from "@/lib/intelligence";
import { statusOrder } from "@/lib/career";
import type { CareerAdvice, CareerAlignment, CareerAnalysis, CareerHistory, CareerProfile, CareerRole, CareerSkill, CareerStatus } from "@/lib/career";
import { Icon } from "@/components/ui/icon";
import styles from "./career-direction.module.css";

type View = "overview" | "evidence" | "roadmap";
const views: { id: View; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "compass" },
  { id: "evidence", label: "Skill evidence", icon: "chart" },
  { id: "roadmap", label: "Next steps", icon: "target" },
];
const shortLabels: Record<CareerStatus, string> = {
  DEMONSTRATED: "Demonstrated", DEVELOPING: "Developing",
  LIMITED_EVIDENCE: "Limited evidence", NOT_DEMONSTRATED: "Not demonstrated",
};

function SkillStatus({ status }: { status: CareerStatus }) {
  return <span className={`${styles.status} ${styles[status]}`}>{shortLabels[status]}</span>;
}

function stepDescription(step: CareerAlignment["roadmap"][number]) {
  if (step.kind === "existing_gap_learning") return "Build a learning plan from your confirmed gaps, then try another interview to check your progress.";
  if (step.kind === "collect_evidence") return `Practise ${step.skill} in an interview or project to gather more evidence.`;
  return step.next_step;
}

export function CareerEvidenceDetail({ value }: { value: CareerSkill }) {
  return <details className={styles.evidence}>
    <summary>View supporting evidence <span>({value.evidence_count} checks · {value.claim_count} claims)</span></summary>
    <div className={styles.evidenceBody}>
      <p>{value.reason}</p>
      <p className={styles.muted}>{value.last_observed_at ? `Last checked ${new Date(value.last_observed_at).toLocaleDateString()}` : "No qualifying recent check"} · Trend: {value.trend}. Recency and independence limits apply.</p>
      <ul>{value.evidence.map((item, index) => <li key={`${item.id}-${index}`}>
        <strong>{item.kind === "interview_check" ? "Evaluated interview check" : item.source_label}</strong>
        <p>{item.quote || `Recorded correctness ${item.correctness?.toFixed(2)} · evaluation confidence ${item.confidence?.toFixed(2)}`}</p>
        {item.interview_id ? <Link href={`/interviews/${item.interview_id}`}>View interview ↗</Link> : <Link href={item.kind === "resume" ? "/resume" : "/profile"}>View source record ↗</Link>}
        <small>Reference {item.id}</small>
      </li>)}</ul>
      {!value.evidence.length && <p>No supporting check or self-reported claim was found. This does not mean you lack this skill.</p>}
      {value.gaps.map(gap => <p key={gap.id}><Link href={`/knowledge-gaps/${gap.id}`}>{gap.subject} · {gap.status} ↗</Link></p>)}
    </div>
  </details>;
}

export function CareerWorkspace() {
  const [profile, setProfile] = useState<CareerProfile | null>(null);
  const [roles, setRoles] = useState<CareerRole[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [job, setJob] = useState("");
  const [analysis, setAnalysis] = useState<CareerAnalysis | null>(null);
  const [history, setHistory] = useState<CareerHistory[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [rag, setRag] = useState(true);
  const [selectedGaps, setSelectedGaps] = useState<Record<string, string[]>>({});
  const [planLinks, setPlanLinks] = useState<Record<string, string>>({});
  const [view, setView] = useState<View>("overview");
  const [activeRoleId, setActiveRoleId] = useState("");
  const [editingTargets, setEditingTargets] = useState(false);
  const [skillFilter, setSkillFilter] = useState<"all" | CareerStatus>("all");
  const tabs = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const [p, r, a, h, j] = await Promise.all([
        api<CareerProfile>("/career/profile"), api<CareerRole[]>("/career/roles"),
        api<CareerAnalysis | null>("/career/readiness"), api<CareerHistory[]>("/career/analyses"), api<Job[]>("/jobs"),
      ]);
      setProfile(p); setRoles(r); setSelected(a ? a.result.alignments.map(value => value.role.id) : p.target_roles);
      setAnalysis(a); setHistory(h); setJobs(j); setMessage("");
      const savedJob = a?.snapshot?.job;
      setJob(savedJob && j.some(item => item.id === savedJob.id) ? savedJob.id : "");
    } catch (error) { setMessage((error as Error).message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);

  async function act(action: () => Promise<void>) {
    setBusy(true); setMessage("");
    try { await action(); } catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  }

  async function analyze() {
    if (!profile) return;
    await act(async () => {
      const value = await mutate<CareerAnalysis>("/career/analyze", "POST", {
        expected_revision: profile.revision, idempotency_key: crypto.randomUUID(), role_ids: selected, job_id: job || null,
      });
      setAnalysis(value); setActiveRoleId(value.result.alignments[0]?.role.id || "");
      setSelectedGaps({}); setPlanLinks({}); setView("overview"); setSkillFilter("all"); setEditingTargets(false);
      setHistory(await api<CareerHistory[]>("/career/analyses"));
    });
  }

  async function choose(roleId: string, skill: string, state: string) {
    if (!analysis) return;
    const prior = analysis.choices.find(choice => choice.role_id === roleId && choice.skill === skill);
    await act(async () => {
      await mutate("/career/choices", "POST", { analysis_id: analysis.id, role_id: roleId, skill, state, expected_revision: prior?.revision || 0 });
      if (state === "dismissed") {
        const gaps = analysis.result.alignments.find(item => item.role.id === roleId)?.skills.find(item => item.skill === skill)?.gap_ids || [];
        setSelectedGaps(current => ({ ...current, [roleId]: (current[roleId] || []).filter(id => !gaps.includes(id)) }));
      }
      setAnalysis(await api<CareerAnalysis>(`/career/analyses/${analysis.id}`));
    });
  }

  function openView(next: View) {
    setView(next);
    tabs.current?.querySelector<HTMLButtonElement>(`[data-view="${next}"]`)?.focus({ preventScroll: true });
    tabs.current?.scrollIntoView({ block: "nearest", behavior: "instant" });
  }

  function onTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % views.length;
    else if (event.key === "ArrowLeft") next = (index + views.length - 1) % views.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = views.length - 1;
    else return;
    event.preventDefault(); openView(views[next].id);
  }

  const alignments = analysis?.result.alignments || [];
  const activeRole = alignments.find(value => value.role.id === activeRoleId) || alignments[0];
  const nextStep = activeRole?.roadmap.find(step => analysis?.choices.some(choice => choice.role_id === activeRole.role.id && choice.skill === step.skill && choice.state === "pursue"))
    || activeRole?.roadmap.find(step => !analysis?.choices.some(choice => choice.role_id === activeRole.role.id && choice.skill === step.skill && choice.state === "dismissed"));
  const filteredSkills = activeRole?.skills.filter(skill => skillFilter === "all" || skill.status === skillFilter) || [];

  if (loading) return <section className={styles.loading} role="status"><Icon name="compass" size={24} /><h1>Career direction</h1><p>Loading your goals and saved evidence…</p></section>;

  return <div className={styles.workspace}>
    <header className={styles.header}>
      <div><p className={styles.eyebrow}>YOUR NEXT CHAPTER</p><h1>Career direction</h1><p>Explore a role, understand your skills, and choose your next step.</p></div>
      <Link className="secondary-button" href="/career/profile"><Icon name="user" size={16} />Edit goals</Link>
    </header>
    {message && <div className={styles.alert} role="alert"><p>{message}</p>{!profile && <button className="secondary-button" type="button" disabled={busy} onClick={() => void act(load)}>Try again</button>}</div>}

    <section className={`${styles.panel} ${styles.targets}`} aria-labelledby="career-target-title">
      <div className={styles.targetHeading}>
        <span className={styles.targetIcon}><Icon name="compass" size={21} /></span>
        <div><h2 id="career-target-title">{analysis ? "Your comparison" : "Where would you like to go?"}</h2><p>{analysis ? alignments.map(value => value.role.name).join(" · ") || "Choose roles to explore" : "Choose up to eight roles to explore using your interview and profile evidence."}{analysis?.snapshot?.job && <span className={styles.jobContext}>Job context: {analysis.snapshot.job.title}</span>}</p></div>
        {analysis && <button className="secondary-button" type="button" aria-expanded={editingTargets} aria-controls="career-target-editor" disabled={busy} onClick={() => setEditingTargets(!editingTargets)}>{editingTargets ? "Close" : "Change roles"}</button>}
      </div>
      <div id="career-target-editor" hidden={!!analysis && !editingTargets} className={styles.targetEditor}>
        <fieldset className={styles.rolePicker} disabled={busy}>
          <legend>Roles to explore <span>{selected.length} / 8 selected</span></legend>
          <div>{roles.map(role => <label key={role.id} className={selected.includes(role.id) ? styles.selectedRole : undefined}>
            <input type="checkbox" checked={selected.includes(role.id)} disabled={!selected.includes(role.id) && selected.length >= 8} onChange={event => setSelected(current => event.target.checked ? [...current, role.id] : current.filter(id => id !== role.id))} />
            <span>{role.name}{profile?.dismissed_roles.includes(role.id) && <small>Previously dismissed</small>}</span>
          </label>)}</div>
        </fieldset>
        <div className={styles.setupActions}>
          <label htmlFor="career-job">Compare with a job <span>Optional</span><select id="career-job" value={job} disabled={busy} onChange={event => setJob(event.target.value)}><option value="">General role requirements</option>{jobs.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
          <button className="action-button" type="button" disabled={busy || !selected.length || !profile} aria-busy={busy} onClick={() => void analyze()}>{busy ? "Working…" : analysis ? "Update comparison" : "Explore selected roles"}<Icon name="arrow" size={16} /></button>
        </div>
        <p className={styles.hint}>Your comparison updates when you request it. Roles are shown without ranking a winner.</p>
      </div>
    </section>

    {!analysis ? <section className={`${styles.panel} ${styles.empty}`}>
      <span className={styles.emptyIcon}><Icon name="target" size={26} /></span>
      <h2>A clearer direction starts with your experience.</h2><p>Select your roles above to see what your recorded evidence supports and what to practise next.</p>
      <div className={styles.inlineLinks}><Link href="/resume">Add a resume <Icon name="arrow" size={14} /></Link><Link href="/interviews">Practise an interview <Icon name="arrow" size={14} /></Link></div>
    </section> : <section className={`${styles.panel} ${styles.results}`} aria-label="Career comparison results">
      <div className={styles.resultToolbar}>
        <label htmlFor="career-active-role">Viewing role<select id="career-active-role" value={activeRole?.role.id || ""} disabled={busy || !alignments.length} onChange={event => { setActiveRoleId(event.target.value); setSkillFilter("all"); }}>
          {alignments.map(value => <option key={value.role.id} value={value.role.id}>{value.role.name}</option>)}
          {!alignments.length && <option value="">No roles in this analysis</option>}
        </select></label>
        <div className={styles.snapshot}><span>Analysis {analysis.version} · {new Date(analysis.generated_at).toLocaleDateString()}</span><span className={analysis.stale ? styles.stale : styles.saved}>{analysis.stale ? "Evidence has changed" : "Saved comparison"}</span></div>
      </div>
      {analysis.stale && <div className={styles.refreshNotice}><p>Your evidence has changed since this comparison.</p><button className="text-button" type="button" disabled={busy} onClick={() => setEditingTargets(true)}>Review roles & update <Icon name="arrow" size={14} /></button></div>}
      <div className={styles.tabs} ref={tabs} role="tablist" aria-label="Career details">{views.map((item, index) => <button type="button" key={item.id} data-view={item.id} id={`career-tab-${item.id}`} role="tab" aria-selected={view === item.id} aria-controls={`career-panel-${item.id}`} tabIndex={view === item.id ? 0 : -1} onClick={() => setView(item.id)} onKeyDown={event => onTabKeyDown(event, index)}><Icon name={item.icon} size={16} />{item.label}</button>)}</div>

      {activeRole ? <>
        <section id="career-panel-overview" role="tabpanel" aria-labelledby="career-tab-overview" hidden={view !== "overview"} className={styles.tabPanel}>
          <div className={styles.roleHeading}><div><h2>{activeRole.role.name}</h2><p>{activeRole.role.description}</p></div><Link href={`/career/roles/${activeRole.role.id}`} className={styles.definitionLink}>Role details <Icon name="arrow" size={14} /></Link></div>
          <dl className={styles.metrics}>{statusOrder.map(status => <div key={status}><dt><span className={`${styles.statusDot} ${styles[status]}`} />{shortLabels[status]}</dt><dd>{activeRole.counts[status]}<span> / {activeRole.skills.length}</span></dd></div>)}</dl>
          <p className={styles.hint}>These counts describe evidence for this role, rather than a career or hiring score.</p>
          <div className={styles.overviewGrid}>
            <article className={styles.nextStep}><span className={styles.eyebrow}>YOUR NEXT STEP</span><h3>{nextStep?.skill || "Keep building your evidence"}</h3><p>{nextStep ? stepDescription(nextStep) : "No development step is suggested by this snapshot. Keep practising as your goals change."}</p><button className="action-button" type="button" onClick={() => openView(nextStep ? "roadmap" : "evidence")}>{nextStep ? "View next steps" : "Explore skill evidence"}<Icon name="arrow" size={15} /></button></article>
            <article className={styles.evidenceSummary}><Icon name="chart" size={21} /><h3>Understand the evidence</h3><p>See which skills have supporting checks and where more practice could help.</p><button className="text-button" type="button" onClick={() => openView("evidence")}>Review {activeRole.skills.length} skills<Icon name="arrow" size={15} /></button></article>
          </div>
          <details className={styles.disclosure}><summary><span><Icon name="shield" size={17} />How to read this comparison</span></summary><div className={styles.disclosureBody}><p>{analysis.result.note}</p><p>{activeRole.role.provenance.source}. {activeRole.role.provenance.scope}</p>{activeRole.tradeoff && <p>{activeRole.tradeoff}</p>}<p>Qualifying checks are grounded, unassisted, have confidence of at least 0.70, and are from the last 180 days. Claims alone do not establish proficiency.</p></div></details>
          <details className={styles.disclosure}><summary><span><Icon name="spark" size={17} />AI guidance</span><span className={styles.summaryNote}>Optional</span></summary><div className={styles.disclosureBody}>
            <p>Request an explanation of this saved comparison. You decide which steps to pursue.</p>
            <label className={styles.checkRow}><input type="checkbox" checked={rag} disabled={busy} onChange={event => setRag(event.target.checked)} />Use technical knowledge sources when available</label>
            <button className="secondary-button" type="button" disabled={busy || analysis.advice?.status === "completed"} onClick={() => void act(async () => { const advice = await mutate<CareerAdvice>(`/career/analyses/${analysis.id}/advice`, "POST", { use_rag: rag }); setAnalysis({ ...analysis, advice }); })}>{analysis.advice?.status === "completed" ? "Explanation saved" : "Explain this comparison"}</button>
            {analysis.advice && <div className={styles.advice}><p>{analysis.advice.status === "failed" ? "The AI explanation is unavailable. You can still use your saved comparison." : `Explanation: ${analysis.advice.status} · retrieval: ${analysis.advice.retrieval_status}`}</p>{analysis.advice.content?.observations.map((item, index) => <p key={index}><strong>{roles.find(role => role.id === item.role_id)?.name} · {item.skill}</strong><br />{item.explanation}</p>)}<ul>{analysis.advice.content?.reflective_questions.map(question => <li key={question}>{question}</li>)}</ul>{analysis.advice.sources.map(source => <p key={source.chunk_id}>Retrieved source: {source.title} · {source.source}</p>)}<small>{analysis.advice.note}</small></div>}
          </div></details>
          <details className={styles.disclosure}><summary><span><Icon name="book" size={17} />Learning & background</span><span className={styles.summaryNote}>{analysis.result.learning_progress.length} learning plans</span></summary><div className={styles.disclosureBody}>
            <p>Activity completion is recorded separately from readiness. Later independent checks can show improvement.</p>
            {analysis.result.learning_progress.map(plan => <p key={plan.id}><Link href={`/learning/${plan.id}`}>{plan.title} ↗</Link> · {plan.completed_items} / {plan.total_items} complete</p>)}
            {!analysis.result.learning_progress.length && <p>No learning plans in this snapshot.</p>}
            {analysis.result.retry_progress.map(attempt => <p key={attempt.id}><Link href={`/interviews/${attempt.interview_id}`}>View retry interview ↗</Link> · {attempt.comparison ? "Comparison available" : "Comparison pending"}</p>)}
            {!!analysis.result.coding.length && <details className={styles.nestedDetails}><summary>Coding evidence ({analysis.result.coding.length})</summary>{analysis.result.coding.map(item => <p key={item.id}><Link href={`/interviews/${item.interview_id}`}>{item.language} · {item.status} ↗</Link> · {item.problem.title} · difficulty {item.problem.difficulty} / 5 · {item.results.tests_passed ?? "Not recorded"} / {item.results.tests_total ?? "Not recorded"} tests passed · {item.results.execution_time_ms == null ? "Execution time not recorded" : `${item.results.execution_time_ms} ms`} · AI complexity reasoning remains an estimate.</p>)}</details>}
            <details className={styles.nestedDetails}><summary>Resume projects & professional background</summary>{analysis.result.background.resume?.projects.map((project, index) => <p key={index}>Self-reported project: {project.quote}</p>)}{analysis.result.background.experience.map(item => <p key={item.id}><strong>{item.title}</strong> · {item.description}</p>)}{analysis.result.background.education.map(item => <p key={item.id}>{item.qualification} · {item.field}</p>)}<Link href="/profile">Edit source profile ↗</Link></details>
          </div></details>
        </section>

        <section id="career-panel-evidence" role="tabpanel" aria-labelledby="career-tab-evidence" hidden={view !== "evidence"} className={styles.tabPanel}>
          <div className={styles.sectionHeading}><div><h2>Skills for {activeRole.role.name}</h2><p>Open a skill’s evidence to see how its label was determined.</p></div><label className={styles.filter} htmlFor="career-skill-filter">Show<select id="career-skill-filter" value={skillFilter} onChange={event => setSkillFilter(event.target.value as "all" | CareerStatus)}><option value="all">All skills ({activeRole.skills.length})</option>{statusOrder.map(status => <option key={status} value={status}>{shortLabels[status]} ({activeRole.counts[status]})</option>)}</select></label></div>
          <ul className={styles.skills}>{filteredSkills.map(skill => <li key={`${activeRole.role.id}-${skill.skill}`}><div className={styles.skillHeading}><div><strong>{skill.skill}</strong><small>{skill.requirement === "required" ? "Core requirement" : skill.requirement === "preferred" ? "Additional skill" : skill.requirement}</small></div><SkillStatus status={skill.status} /></div><CareerEvidenceDetail value={skill} /></li>)}</ul>
          {!filteredSkills.length && <p className={styles.inlineEmpty}>No skills have this label in the saved comparison.</p>}
          {!!analysis.result.job_alignment.length && <details className={styles.disclosure}><summary><span><Icon name="briefcase" size={17} />Job-specific requirements</span><span className={styles.summaryNote}>{analysis.result.job_alignment.length} skills</span></summary><div className={styles.disclosureBody}><p>These use the selected job’s extracted requirements.</p><ul className={styles.skills}>{analysis.result.job_alignment.map(skill => <li key={skill.skill}><div className={styles.skillHeading}><strong>{skill.skill}</strong><SkillStatus status={skill.status} /></div><CareerEvidenceDetail value={skill} /></li>)}</ul></div></details>}
        </section>

        <section id="career-panel-roadmap" role="tabpanel" aria-labelledby="career-tab-roadmap" hidden={view !== "roadmap"} className={styles.tabPanel}>
          <div className={styles.sectionHeading}><div><h2>Your next steps</h2><p>Choose what to work on for {activeRole.role.name}.</p></div><span className={styles.summaryNote}>{activeRole.roadmap.filter(step => analysis.choices.some(choice => choice.role_id === activeRole.role.id && choice.skill === step.skill && choice.state === "pursue")).length} chosen</span></div>
          <ol className={styles.roadmap}>{activeRole.roadmap.map((step, index) => {
            const choice = analysis.choices.find(item => item.role_id === activeRole.role.id && item.skill === step.skill);
            return <li key={`${activeRole.role.id}-${step.skill}`} className={choice?.state === "dismissed" ? styles.dismissed : undefined}>
              <span className={styles.stepNumber}>{choice?.state === "pursue" ? <Icon name="check" size={15} /> : String(index + 1).padStart(2, "0")}</span>
              <div className={styles.stepContent}><div className={styles.skillHeading}><h3>{step.skill}</h3><span className={choice?.state === "pursue" ? styles.chosen : styles.summaryNote}>{choice?.state === "pursue" ? "Chosen by you" : choice?.state === "dismissed" ? "Dismissed" : "Suggested step"}</span></div>
                <p>{stepDescription(step)}</p>
                <div className={styles.stepActions}><button className="secondary-button" type="button" disabled={busy || choice?.state === "pursue"} onClick={() => void choose(activeRole.role.id, step.skill, "pursue")}>{choice?.state === "pursue" ? "Added to your steps" : choice?.state === "dismissed" ? "Restore & pursue" : "Pursue this step"}</button>{choice?.state !== "dismissed" && <button className="text-button" type="button" disabled={busy} onClick={() => void choose(activeRole.role.id, step.skill, "dismissed")}>Dismiss</button>}{!step.gap_ids.length && <Link href="/interviews/new">Practise in an interview <Icon name="arrow" size={14} /></Link>}</div>
                {step.gap_ids.length > 0 && choice?.state !== "pursue" && choice?.state !== "dismissed" && <p className={styles.hint}>Pursue this step to add its confirmed gaps to a learning plan.</p>}
                {choice?.state === "pursue" && step.gap_ids.length > 0 && <div className={styles.gapChoices}><span>Select confirmed gaps for your learning plan</span>{step.gap_ids.map(id => {
                  const gap = activeRole.skills.flatMap(skill => skill.gaps).find(item => item.id === id);
                  return <label className={styles.checkRow} key={id}><input type="checkbox" checked={(selectedGaps[activeRole.role.id] || []).includes(id)} disabled={busy || !(selectedGaps[activeRole.role.id] || []).includes(id) && (selectedGaps[activeRole.role.id] || []).length >= 6} onChange={event => { const checked = event.target.checked; setSelectedGaps(current => ({ ...current, [activeRole.role.id]: checked ? [...new Set([...(current[activeRole.role.id] || []), id])].slice(0, 6) : (current[activeRole.role.id] || []).filter(item => item !== id) })); }} />{gap?.subject || "Existing confirmed gap"}</label>;
                })}</div>}
              </div>
            </li>;
          })}</ol>
          {!activeRole.roadmap.length && <div className={styles.inlineEmpty}><Icon name="check" size={22} /><h3>No development steps suggested</h3><p>Keep collecting evidence as your goals change.</p><Link href="/interviews/new">Practise an interview ↗</Link></div>}
          {(selectedGaps[activeRole.role.id] || []).length > 0 && <div className={styles.planAction}><span>{selectedGaps[activeRole.role.id].length} confirmed gaps selected</span><button className="action-button" type="button" disabled={busy} onClick={() => void act(async () => { const plan = await mutate<{ id: string }>("/career/roadmap", "POST", { analysis_id: analysis.id, role_id: activeRole.role.id, gap_ids: selectedGaps[activeRole.role.id], idempotency_key: crypto.randomUUID() }); setPlanLinks(current => ({ ...current, [activeRole.role.id]: plan.id })); })}>Create learning plan <Icon name="arrow" size={15} /></button></div>}
          {planLinks[activeRole.role.id] && <p className={styles.planSuccess} role="status"><Icon name="check" size={17} />Your learning plan is ready. <Link href={`/learning/${planLinks[activeRole.role.id]}`}>Open plan ↗</Link></p>}
          <p className={styles.hint}>Limited evidence suggests more assessment. Only confirmed knowledge gaps can be added to a learning plan.</p>
        </section>
      </> : <p className={styles.inlineEmpty}>Choose roles above and update your comparison to see their evidence.</p>}
    </section>}

    <details className={`${styles.panel} ${styles.history}`}>
      <summary><span><Icon name="book" size={17} />Past comparisons</span><span className={styles.summaryNote}>{history.length} saved</span></summary>
      <div className={styles.historyBody}><p className={styles.hint}>Each version keeps its original evidence snapshot.</p><ol>{history.map(item => <li key={item.id}><div><strong>Analysis {item.version}</strong><small>{new Date(item.generated_at).toLocaleDateString()} · {item.roles.join(" · ")}</small></div><button className="secondary-button" type="button" disabled={busy} aria-label={`Open analysis ${item.version}`} onClick={() => void act(async () => { const value = await api<CareerAnalysis>(`/career/analyses/${item.id}`); setAnalysis(value); setActiveRoleId(value.result.alignments[0]?.role.id || ""); setSelected(value.result.alignments.map(role => role.role.id)); const savedJob = value.snapshot?.job; setJob(savedJob && jobs.some(item => item.id === savedJob.id) ? savedJob.id : ""); setEditingTargets(false); setSelectedGaps({}); setPlanLinks({}); setView("overview"); setSkillFilter("all"); tabs.current?.scrollIntoView({ block: "nearest", behavior: "instant" }); })}>{analysis?.id === item.id ? "Viewing" : "Open"}<Icon name="arrow" size={14} /></button></li>)}</ol>{!history.length && <p>Your first comparison will appear here.</p>}</div>
    </details>
  </div>;
}
