"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { python } from "@codemirror/lang-python";
import { cpp } from "@codemirror/lang-cpp";
import { java } from "@codemirror/lang-java";
import { api } from "@/lib/api";
import { mutate } from "@/lib/intelligence";
import type { Interview } from "@/lib/interviews";

const Editor = dynamic(() => import("@uiw/react-codemirror"), { ssr: false, loading: () => <p>Loading code editor…</p> });
type Language = "python" | "cpp" | "java";
type Case = { input: string; expected: string };
type Problem = { id: string; title: string; description: string; topic: string; difficulty: number; constraints: string[]; input_format: string; output_format: string; examples: Case[]; public_tests: Case[]; starter_code: Record<Language, string>; supported_languages: Language[]; validation_status: string; time_ms: number; memory_mb: number };
type Submission = { id: string; question_id: string; mode: string; status: string; execution_status: string; submission_number: number; language: Language; source_code: string; result: { tests_total: number; tests_passed: number; execution_time_ms: number | null; memory_kb: number | null; compile_error?: string; cases?: { passed: boolean; stdout: string; stderr: string; status: string }[] } | null; analysis: { kind: string; time_complexity: string; space_complexity: string; reasoning: string; code_quality: string; edge_cases: string } | null };
const names = { python: "Python 3.12", cpp: "C++17", java: "Java 17" };
const extensions = { python: python(), cpp: cpp(), java: java() };
const pending = (s?: Submission) => !!s && ["QUEUED", "RUNNING"].includes(s.execution_status);

function SavedSubmission({ submission: s }: { submission: Submission }) {
  return <article><p>Attempt {s.submission_number} · {s.mode} · {names[s.language]} · {s.execution_status} · {s.status}</p>{s.result && <p>{s.result.tests_passed}/{s.result.tests_total} tests passed · {s.result.execution_time_ms ?? "—"} ms measured · {s.result.memory_kb ?? "—"} KB measured peak</p>}{s.analysis && <details><summary>Estimated complexity and code review</summary><p>Time: {s.analysis.time_complexity} · Space: {s.analysis.space_complexity}</p><p>{s.analysis.reasoning}</p><p>{s.analysis.code_quality}</p><p>{s.analysis.edge_cases}</p><small>{s.analysis.kind}; estimates are separate from measured metrics.</small></details>}<details><summary>Saved source</summary><pre>{s.source_code}</pre></details></article>;
}

export function CodingHistory({ interviewId }: { interviewId: string }) {
  const [history, setHistory] = useState<Submission[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { api<Submission[]>(`/interviews/${interviewId}/coding/submissions`).then(setHistory).catch(e => setError(e.message)); }, [interviewId]);
  return <section className="content-card coding-workspace"><h2>Coding submission history</h2>{error && <p role="alert">{error}</p>}{history.map(s => <SavedSubmission key={s.id} submission={s} />)}</section>;
}

export function ProblemSelector() {
  const [problems, setProblems] = useState<Problem[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { api<Problem[]>("/coding/problems").then(setProblems).catch(e => setError(e.message)); }, []);
  return <label>Coding problem<select name="coding_problem"><option value="">Adaptive selection from the original curated collection</option>{problems.filter(p => p.validation_status !== "rejected").map(p => <option key={p.id} value={p.id}>{p.title} · {p.topic} · difficulty {p.difficulty}</option>)}</select><small>Problem reference solutions are checked in the secure sandbox before use.</small>{error && <span role="alert">{error}</span>}</label>;
}

export function CodingPanel({ row, onRefresh }: { row: Interview; onRefresh: () => Promise<void> }) {
  const interviewId = row.id, questionId = row.current?.id, problemId = row.current?.coding_problem_id;
  const [problem, setProblem] = useState<Problem>();
  const [language, setLanguage] = useState<Language>("python");
  const [source, setSource] = useState("");
  const [explanation, setExplanation] = useState("");
  const [available, setAvailable] = useState<Language[]>([]);
  const [submission, setSubmission] = useState<Submission>();
  const [history, setHistory] = useState<Submission[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const drafts = useRef<Partial<Record<Language, string>>>({});
  const requestKey = useRef<{ fingerprint: string; key: string } | null>(null);
  const refreshHistory = useCallback(async () => {
    const items = await api<Submission[]>(`/interviews/${interviewId}/coding/submissions`);
    setHistory(items);
    const active = items.find(s => s.question_id === questionId);
    if (active) setSubmission(active);
  }, [interviewId, questionId]);
  useEffect(() => {
    let disposed = false;
    Promise.all([api<Problem>(`/coding/problems/${problemId}`), api<{ ready: boolean; languages: Language[] }>("/coding/provider"), api<Submission[]>(`/interviews/${interviewId}/coding/submissions`)]).then(([p, provider, items]) => {
      if (disposed) return;
      setProblem(p); setAvailable(provider.languages); setSource(p.starter_code.python || "");
      setHistory(items);
      const previous = items.find(s => s.question_id === questionId);
      if (previous) { setSubmission(previous); setLanguage(previous.language); setSource(previous.source_code); }
      if (!provider.ready) setError("The secure execution service is unavailable. Your code can still be edited.");
    }).catch(e => !disposed && setError(e.message));
    return () => { disposed = true; };
  }, [problemId, interviewId, questionId]);
  useEffect(() => {
    if (!pending(submission)) return;
    let disposed = false;
    const timer = window.setInterval(() => {
      api<Submission>(`/coding/submissions/${submission!.id}/status`).then(async value => {
        if (disposed) return;
        setSubmission(value);
        if (!pending(value)) { await refreshHistory(); await onRefresh(); }
      }).catch(e => !disposed && setError(e.message));
    }, 1000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [submission, onRefresh, refreshHistory]);
  function changeLanguage(value: Language) {
    drafts.current[language] = source;
    setLanguage(value); setSource(drafts.current[value] ?? problem?.starter_code[value] ?? "");
  }
  async function execute(mode: "run" | "submit") {
    if (inFlight.current || !row.current) return;
    inFlight.current = true; setBusy(true); setError("");
    const fingerprint = JSON.stringify([mode, row.current.id, language, source, explanation]);
    if (requestKey.current?.fingerprint !== fingerprint) requestKey.current = { fingerprint, key: crypto.randomUUID() };
    try {
      setSubmission(await mutate<Submission>(`/interviews/${row.id}/coding/${mode}`, "POST", { question_id: row.current.id, expected_revision: row.revision, idempotency_key: requestKey.current!.key, language, source_code: source, explanation }));
    } catch (e) { setError((e as Error).message); await onRefresh(); }
    finally { setBusy(false); inFlight.current = false; }
  }
  async function stop() {
    if (!submission) return;
    try { setSubmission(await mutate<Submission>(`/coding/submissions/${submission.id}/cancel`, "POST", {})); requestKey.current = null; }
    catch (e) { setError((e as Error).message); }
  }
  if (!problem) return <section className="content-card"><p role="status">Loading coding problem…</p>{error && <p role="alert">{error}</p>}</section>;
  const locked = busy || pending(submission);
  const oversized = new TextEncoder().encode(source).length > 32768;
  return <section className="coding-workspace" aria-label="Coding interview workspace">
    <div className="coding-columns">
      <article className="content-card coding-problem"><p className="eyebrow">{problem.topic} · DIFFICULTY {problem.difficulty}</p><h2>{problem.title}</h2><p>{problem.description}</p><h3>Constraints</h3><ul>{problem.constraints.map(c => <li key={c}>{c}</li>)}</ul><h3>Input</h3><p>{problem.input_format}</p><h3>Output</h3><p>{problem.output_format}</p><h3>Examples</h3>{problem.examples.map((c, i) => <div className="coding-example" key={i}><strong>Input</strong><pre>{c.input}</pre><strong>Expected output</strong><pre>{c.expected}</pre></div>)}<details><summary>Public tests ({problem.public_tests.length})</summary>{problem.public_tests.map((c, i) => <pre key={i}>Input: {c.input}{"\n"}Expected: {c.expected}</pre>)}</details><p className="subtle-copy">Per test: {problem.time_ms} ms · {problem.memory_mb} MB. Hidden test content stays private.</p></article>
      <div className="content-card coding-editor"><div className="coding-toolbar"><label>Language<select value={language} onChange={e => changeLanguage(e.target.value as Language)} disabled={locked}>{problem.supported_languages.filter(l => available.includes(l)).map(l => <option value={l} key={l}>{names[l]}</option>)}</select></label><button className="secondary-button" disabled={locked} onClick={() => { setSource(problem.starter_code[language]); requestKey.current = null; }}>Reset to starter</button></div><Editor value={source} height="420px" extensions={[extensions[language]]} onChange={setSource} editable={!locked} aria-label="Solution source code" basicSetup={{ lineNumbers: true, highlightActiveLine: true, tabSize: 4 }} /><label>Explain your approach<textarea value={explanation} onChange={e => setExplanation(e.target.value)} maxLength={4000} rows={3} placeholder="Describe the algorithm, edge cases, and complexity." /></label><div className="room-actions"><button className="secondary-button" disabled={locked || oversized || !source || !available.includes(language)} onClick={() => void execute("run")}>Run public tests</button><button className="action-button" disabled={locked || oversized || !source || !available.includes(language)} onClick={() => void execute("submit")}>Submit final solution</button>{pending(submission) && <button className="text-button danger" onClick={() => void stop()}>Stop execution</button>}</div><small>Submit judges public and hidden tests, then advances the interview. Run allows revisions.</small>{oversized && <p role="alert">Source exceeds the 32 KB limit.</p>}</div>
    </div>
    {error && <p className="error-message" role="alert">{error}</p>}
    <section className="content-card coding-results" aria-live="polite"><h2>Execution results</h2>{!submission ? <p>Run the public tests to check your solution.</p> : <><strong>{submission.execution_status.replaceAll("_", " ")} · {submission.status.replaceAll("_", " ")}</strong>{submission.result && <><p>{submission.result.tests_passed}/{submission.result.tests_total} tests passed{typeof submission.result.execution_time_ms === "number" && ` · ${submission.result.execution_time_ms} ms measured runtime`}{typeof submission.result.memory_kb === "number" && ` · ${submission.result.memory_kb} KB measured peak memory`}</p>{submission.result.compile_error && <pre>{submission.result.compile_error}</pre>}{submission.result.cases?.map((c, i) => <details key={i}><summary>Public test {i + 1}: {c.passed ? "Passed" : c.status === "COMPLETED" ? "Wrong answer" : c.status.replaceAll("_", " ")}</summary><pre>{c.stdout || "No stdout"}</pre>{c.stderr && <pre>{c.stderr}</pre>}</details>)}{submission.mode === "submit" && <small>Hidden inputs, expected outputs, stdout, and runtime diagnostics are withheld.</small>}</>}{submission.analysis && <div><h3>Estimated complexity</h3><p>Time: {submission.analysis.time_complexity} · Space: {submission.analysis.space_complexity}</p><p>{submission.analysis.reasoning}</p><p>{submission.analysis.code_quality}</p><small>{submission.analysis.kind}; separate from measured runtime.</small></div>}</>}</section>
    {history.length > 0 && <details className="content-card"><summary>Submission history ({history.length})</summary>{history.map(s => <SavedSubmission key={s.id} submission={s} />)}</details>}
  </section>;
}
