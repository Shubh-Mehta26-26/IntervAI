"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { mutate, uploadResume, type Resume } from "@/lib/intelligence";
import { EvidenceList } from "./evidence-list";

export function ResumeWorkspace() {
  const [items, setItems] = useState<Resume[]>([]);
  const [selected, setSelected] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [replaceId, setReplaceId] = useState<string>();
  const [removeId, setRemoveId] = useState<string>();
  const input = useRef<HTMLInputElement>(null);
  const load = useCallback(async () => {
    const data = await api<Resume[]>("/resumes"); setItems(data); setLoaded(true);
    setSelected(old => data.some(item => item.id === old) ? old : data[0]?.id || "");
  }, []);
  useEffect(() => { const timer = window.setTimeout(() => { void load().catch(err => { setError(err.message); setLoaded(true); }); }, 0); return () => window.clearTimeout(timer); }, [load]);
  const pending = items.some(item => ["uploaded", "processing"].includes(item.status));
  useEffect(() => { if (!pending) return; const timer = setInterval(() => { load().catch(err => setError(err.message)); }, 2500); return () => clearInterval(timer); }, [pending, load]);
  async function upload(file?: File) {
    if (!file) return;
    setError(""); setNotice("");
    if (!/\.(pdf|docx)$/i.test(file.name) || file.size > 10 * 1024 * 1024 || !file.size) { setError("Choose a non-empty PDF or DOCX, up to 10 MB."); return; }
    setBusy(true); setProgress(0);
    try { const row = await uploadResume(file, setProgress, replaceId); setSelected(row.id); await load(); setNotice("Upload saved. Parsing runs separately; this page will update when it finishes."); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); setReplaceId(undefined); if (input.current) input.current.value = ""; }
  }
  async function action(path: string, method = "POST") {
    setBusy(true); setError(""); setNotice("");
    try { await mutate(path, method); await load(); setNotice(method === "DELETE" ? "Resume and its saved match evidence deleted." : "Retry queued."); setRemoveId(undefined); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  const row = items.find(item => item.id === selected);
  const facts = row?.parsed_data;
  return <div className="intelligence-workspace"><div className="intelligence-heading"><div><span className="eyebrow">YOUR EVIDENCE</span><h1>Your story,<br /><em>in context.</em></h1><p className="subtle-copy">Turn your resume into traceable evidence for your next opportunity.</p></div><Link className="secondary-button" href="/jobs">Explore job targets ↗</Link></div>
    {error && <p role="alert" className="error-message">{error}</p>}{notice && <p role="status" className="success-message">{notice}</p>}
    <section className="upload-card"><span className="upload-symbol" aria-hidden="true">↥</span><div><h2>{replaceId ? "Upload a new version" : "Bring your experience into focus"}</h2><p className="subtle-copy">PDF or DOCX · up to 10 MB · text-based documents only.<br />Your original file stays private. Your profile stays in your control.</p><label className="field-label" htmlFor="resume-file">{replaceId ? "Replacement resume" : "Choose a resume"}</label><input ref={input} id="resume-file" type="file" accept=".pdf,.docx" disabled={busy} onChange={event => void upload(event.target.files?.[0])} />{replaceId && <button className="text-button" onClick={() => setReplaceId(undefined)}>Cancel replacement</button>}{busy && <div role="status"><progress value={progress} max={100} aria-label="Upload progress" /><p className="subtle-copy">{progress < 100 ? `Uploading · ${progress}%` : "Upload sent · waiting for confirmation…"}</p></div>}</div></section>
    {!loaded ? <p role="status">Loading your resumes…</p> : !items.length ? <section className="content-card empty-state"><h2>No resume yet</h2><p className="subtle-copy">Upload your first document to see its extracted details and skills here.</p></section> : <div className="evidence-workspace"><aside className="resume-versions"><h2>Resume library</h2><p className="subtle-copy">Replacement uploads create historical versions.</p>{items.map(item => <button key={item.id} className={`resume-version ${selected === item.id ? "selected" : ""}`} onClick={() => { setSelected(item.id); setRemoveId(undefined); }}><span>{item.original_name}</span><small>Version {item.version} · {(item.size_bytes / 1024).toFixed(1)} KB</small><span className={`status-pill ${item.status}`}>{item.status}</span></button>)}</aside><section className="content-card resume-detail">{row && <><div className="section-heading"><div><span className={`status-pill ${row.status}`}>{row.status}</span><h2>{row.original_name}</h2></div><a className="text-link" href={`/api/v1/resumes/${row.id}/file`}>Download original</a></div><div className="button-row"><button className="secondary-button" disabled={busy} onClick={() => { setReplaceId(row.id); input.current?.focus(); }}>Replace with new version</button><button className="text-button danger" disabled={busy} onClick={() => setRemoveId(row.id)}>Delete</button></div>{removeId === row.id && <div className="delete-confirm"><p>Delete this file, parsed data and any saved match using it?</p><button className="secondary-button danger" disabled={busy} onClick={() => void action(`/resumes/${row.id}`, "DELETE")}>Confirm delete</button><button className="text-button" onClick={() => setRemoveId(undefined)}>Cancel</button></div>}
    {row.status === "failed" && <div role="alert" className="error-message"><p>{row.error}</p><button className="secondary-button" disabled={busy} onClick={() => void action(`/resumes/${row.id}/retry`)}>Retry parsing</button></div>}{["uploaded", "processing"].includes(row.status) && <p role="status" className="processing-note">{row.status === "uploaded" ? "Saved and waiting for the document worker." : "Extracting text and validating structured evidence…"} This page updates automatically.</p>}
    {facts && <><div className="facts-grid"><div><small>NAME</small><p>{facts.name || "Not extracted"}</p></div><div><small>EMAIL</small><p>{facts.email || "Not extracted"}</p></div><div><small>PHONE</small><p>{facts.phone || "Not extracted"}</p></div><div><small>LOCATION</small><p>{facts.location || "Not extracted"}</p></div></div>{facts.summary && <section><h3>Summary</h3><p className="preserve-text">{facts.summary}</p></section>}<section><h3>Recognized skills</h3><div className="skill-tags">{facts.skills.map(skill => <span key={skill.slug}>{skill.name}</span>)}</div>{!facts.skills.length && <p className="subtle-copy">No vocabulary matches found. Review the extracted text below.</p>}</section>{(["education", "experience", "projects", "certifications", "achievements"] as const).map(section => <section key={section}><h3 className="capitalize">{section}</h3><EvidenceList items={facts[section]} /></section>)}<section><h3>Links in document</h3>{facts.links.map(link => <p className="preserve-text" key={link}>{link}</p>)}{!facts.links.length && <p className="subtle-copy">No links extracted.</p>}</section><div className="processing-note">{facts.warnings.map(warning => <p key={warning}>{warning}</p>)}</div></>}{row.extracted_text && <details><summary>Review extracted text</summary><pre className="extracted-text">{row.extracted_text}</pre></details>}</>}</section></div>}
  </div>;
}
