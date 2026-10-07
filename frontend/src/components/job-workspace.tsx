"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { mutate, type Job, type Match, type Resume } from "@/lib/intelligence";
import { EvidenceList } from "./evidence-list";

export function JobLibrary() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { api<Job[]>("/jobs").then(setJobs).catch(err => setError(err.message)).finally(() => setLoaded(true)); }, []);
  return <div className="intelligence-workspace"><div className="intelligence-heading"><div><span className="eyebrow">A CLEARER NEXT STEP</span><h1>Find your<br /><em>direction.</em></h1><p className="subtle-copy">Understand what a role asks for, and where your evidence connects.</p></div><Link className="action-button" href="/jobs/new">Add a job target ↗</Link></div>{error && <p role="alert" className="error-message">{error}</p>}{!loaded ? <p role="status">Loading job targets…</p> : !jobs.length ? <section className="content-card empty-state"><span className="upload-symbol" aria-hidden="true">◎</span><h2>Your next opportunity starts here</h2><p className="subtle-copy">No job targets yet. Paste a real job description to extract its requirements and compare your evidence.</p><Link className="secondary-button" href="/jobs/new">Create your first target</Link></section> : <div className="job-grid">{jobs.map(job => <Link key={job.id} href={`/jobs/${job.id}`} className="content-card job-card"><span className={`status-pill ${job.status}`}>{job.status}</span><h2>{job.title}</h2><p className="subtle-copy">{job.company || "Company not supplied"}</p><div className="skill-tags">{job.analysis?.skills.slice(0, 5).map(skill => <span key={skill.slug}>{skill.name}</span>)}</div><span className="text-link">Review target →</span></Link>)}</div>}</div>;
}

export function JobForm({ job, onSaved }: { job?: Job; onSaved?: (job: Job) => void }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    const body = { title: String(form.get("title")).trim(), company: String(form.get("company")).trim() || null, description: String(form.get("description")).trim(), ...(job ? { expected_version: job.version } : {}) };
    try { const result = await mutate<Job>(job ? `/jobs/${job.id}` : "/jobs", job ? "PATCH" : "POST", body); if (onSaved) onSaved(result); else router.push(`/jobs/${result.id}`); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <form className="content-card intelligence-form" onSubmit={submit}>{error && <p role="alert" className="error-message">{error}</p>}<div className="form-two"><label>Job title<input name="title" required maxLength={160} defaultValue={job?.title} placeholder="e.g. Backend Engineer" /></label><label>Company <small>(optional)</small><input name="company" maxLength={160} defaultValue={job?.company || ""} placeholder="As supplied in the job posting" /></label></div><label>Job description<textarea name="description" required minLength={30} maxLength={30000} rows={16} defaultValue={job?.description} placeholder="Paste the actual job description, including requirements and preferred skills. Preserve headings and bullet points for clearer extraction." /></label><p className="subtle-copy">Paste up to 30,000 characters. Required and preferred headings help preserve the employer’s intent. Your job targets are private.</p><button className="action-button" disabled={busy}>{busy ? "Saving…" : job ? "Save changes" : "Save job target"}</button></form>;
}

export function NewJob() { return <div className="intelligence-workspace"><Link className="text-link" href="/jobs">← All job targets</Link><div className="intelligence-heading"><div><span className="eyebrow">BUILD YOUR CONTEXT</span><h1>A role worth<br /><em>preparing for.</em></h1><p className="subtle-copy">Start with the real description. We’ll keep each extracted requirement traceable.</p></div></div><JobForm /></div>; }

export function JobDetail({ identifier }: { identifier: string }) {
  const router = useRouter();
  const [job, setJob] = useState<Job>();
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [selected, setSelected] = useState("");
  const [match, setMatch] = useState<Match>();
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const load = useCallback(async () => {
    const [data, documents] = await Promise.all([api<Job>(`/jobs/${identifier}`), api<Resume[]>("/resumes")]);
    setJob(data); setResumes(documents.filter(item => item.status === "parsed"));
    try { const saved = await api<Match>(`/jobs/${identifier}/match`); setMatch(saved); setSelected(saved.resume_id || ""); }
    catch (err) { if ((err as { status?: number }).status !== 404) throw err; }
  }, [identifier]);
  useEffect(() => { const timer = window.setTimeout(() => { void load().catch(err => setError(err.message)); }, 0); return () => window.clearTimeout(timer); }, [load]);
  async function analyze() {
    setBusy(true); setError(""); setNotice("");
    try { setJob(await mutate<Job>(`/jobs/${identifier}/analyze`)); setNotice("Requirements extracted and saved. Review the source quotations below."); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  async function compare() {
    setBusy(true); setError(""); setNotice("");
    try { setMatch(await mutate<Match>(`/jobs/${identifier}/match`, "POST", { resume_id: selected || null })); setNotice("Evidence match saved."); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true); setError("");
    try { await mutate(`/jobs/${identifier}`, "DELETE"); router.push("/jobs"); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return <div className="intelligence-workspace"><Link className="text-link" href="/jobs">← All job targets</Link>{error && <p className="error-message" role="alert">{error}</p>}{notice && <p className="success-message" role="status">{notice}</p>}{!job ? !error && <p role="status">Loading job target…</p> : <><div className="intelligence-heading"><div><span className="eyebrow">YOUR JOB TARGET · VERSION {job.version}</span><h1 className="job-title">{job.title}</h1><p className="subtle-copy">{job.company || "Company not supplied"}</p></div><span className={`status-pill ${job.status}`}>{job.status}</span></div><div className="button-row"><button className="action-button" disabled={busy || editing} onClick={() => void analyze()}>{busy ? "Working…" : job.analysis ? "Refresh analysis" : "Analyze requirements"}</button><button className="secondary-button" disabled={busy} onClick={() => setEditing(!editing)}>{editing ? "Cancel editing" : "Edit description"}</button><button className="text-button danger" onClick={() => setDeleting(true)}>Delete job</button></div>{deleting && <div className="delete-confirm"><p>Delete this job target, requirements and saved match?</p><button className="secondary-button danger" disabled={busy} onClick={() => void remove()}>Confirm delete</button><button className="text-button" onClick={() => setDeleting(false)}>Cancel</button></div>}{editing ? <JobForm job={job} onSaved={data => { setJob(data); setEditing(false); setMatch(old => old ? { ...old, stale: true } : undefined); setNotice("Changes saved. Analyze the updated description before matching again."); }} /> : <details className="content-card"><summary>Original job description</summary><p className="preserve-text">{job.description}</p></details>}
      {!job.analysis ? <section className="content-card empty-state"><h2>Ready to understand this role</h2><p className="subtle-copy">Analyze the saved description to identify explicit skills and requirements.</p></section> : <><section className="content-card"><div className="section-heading"><h2>What this role asks for</h2><span className="muted-label">EXTRACTED FROM YOUR DESCRIPTION</span></div>{["required", "preferred", "unspecified"].map(level => <div className="requirement-section" key={level}><h3>{level === "unspecified" ? "Skills mentioned · importance unspecified" : `${level === "required" ? "Required" : "Preferred"} skills`}</h3>{job.analysis!.skills.filter(skill => skill.requirement === level).map(skill => <details className="skill-requirement" key={skill.slug}><summary><span>{skill.name}</span><small>{skill.category.replaceAll("_", " ")}</small></summary><EvidenceList items={skill.evidence} /></details>)}{!job.analysis!.skills.some(skill => skill.requirement === level) && <p className="subtle-copy">None explicitly identified.</p>}</div>)}{(["responsibilities", "qualifications", "experience_requirements", "other_requirements"] as const).map(section => <details key={section}><summary className="capitalize">{section.replaceAll("_", " ")}</summary><EvidenceList items={job.analysis![section]} /></details>)}<p className="subtle-copy">Domain: {job.analysis.domain || "Not explicitly supplied"}</p><div className="processing-note">{job.analysis.warnings.map(warning => <p key={warning}>{warning}</p>)}</div></section>
      <section className="match-panel"><span className="eyebrow">CONNECT THE EVIDENCE</span><h2>How your experience lines up</h2><p className="subtle-copy">Compare your current profile and one selected resume. No score, no assumed expertise—just source-backed claims and open questions.</p><label className="field-label" htmlFor="match-resume">Resume evidence</label><select id="match-resume" value={selected} onChange={event => setSelected(event.target.value)}><option value="">Profile only</option>{resumes.map(item => <option key={item.id} value={item.id}>{item.original_name} · version {item.version}</option>)}</select>{!resumes.length && <p className="subtle-copy">No parsed resume available. <Link className="text-link" href="/resume">Upload a resume</Link> to include it.</p>}<button className="action-button" disabled={busy || editing} onClick={() => void compare()}>{busy ? "Comparing…" : "Match and save evidence"}</button></section></>}
      {match && <section className="content-card saved-match"><div className="section-heading"><h2>Saved evidence match</h2><span className={`status-pill ${match.stale ? "failed" : "parsed"}`}>{match.stale ? "Needs refresh" : "Saved"}</span></div><p className="subtle-copy">{match.result.explanation}</p>{(match.resume_id || "") !== selected && <p className="processing-note">The selection changed. Run matching to save a result for this selection.</p>}{match.stale && <p className="error-message">The source profile or job changed. Analyze if needed, then run matching again.</p>}{!match.result.skills.length && <p className="subtle-copy">No recognized skill requirements to compare. Review the original job description.</p>}{match.result.skills.map(skill => <article className="match-skill" key={skill.skill_id}><div className="section-heading"><h3>{skill.name} <small>· {skill.requirement}</small></h3><span className={`status-pill ${skill.status}`}>{skill.status === "demonstrated" ? "Applied claim" : skill.status === "partial" ? "Mention only" : "Not demonstrated"}</span></div><p className="subtle-copy">{skill.explanation}</p><EvidenceList items={skill.evidence} empty="No candidate evidence found." /><details><summary>Job source</summary><EvidenceList items={skill.job_evidence} /></details></article>)}<details><summary>Requirements needing human review</summary><p className="subtle-copy">These requirements are not established by skill-name matching.</p><EvidenceList items={match.result.unassessed_requirements} /></details></section>}
    </>}</div>;
}
