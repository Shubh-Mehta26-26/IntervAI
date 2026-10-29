"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Interview } from "@/lib/interviews";
import { Icon } from "./ui/icon";
export function DashboardActivity() {
    const [rows, setRows] = useState<Interview[]>();
    const [error, setError] = useState("");
    useEffect(() => { api<Interview[]>("/interviews").then(setRows).catch(e => setError(e.message)); }, []);
    if (error)
        return <div className="error-message" role="alert">{error} <Link href="/interviews">Open interviews to try again</Link></div>;
    if (!rows)
        return <div className="metric-grid" role="status" aria-label="Loading interview activity">{[1, 2, 3].map(i => <div className="content-card skeleton-card" key={i}><span className="skeleton"/><span className="skeleton short"/></div>)}</div>;
    const active = rows.filter(r => !["completed", "cancelled", "failed"].includes(r.status));
    return <><div className="metric-grid">{[["Completed interviews", rows.filter(r => r.status === "completed").length, "mic", "Keep building your experience"], ["In progress", active.length, "target", "Pick up where you left off"], ["Answers submitted", rows.reduce((n, r) => n + r.progress.answered, 0), "chart", "Evidence behind your progress"]].map(([label, value, icon, description]) => <article className="content-card metric-card" key={label}><div><span>{label}</span><Icon name={String(icon)}/></div><strong>{value}</strong><small>{description}</small></article>)}</div><section className="content-card recent-interviews"><div className="section-heading"><div><p className="eyebrow">KEEP YOUR MOMENTUM</p><h2>Recent interviews</h2></div><Link className="text-link" href="/interviews">View all <Icon name="arrow" size={15}/></Link></div>{rows.length ? <div>{[...rows].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 3).map(row => <Link className="recent-row" href={`/interviews/${row.id}`} key={row.id}><span className="feature-icon"><Icon name={row.interview_type === "coding" ? "code" : "mic"}/></span><span><strong>{row.interview_type} interview</strong><small>{row.mode} · {new Date(row.created_at).toLocaleDateString()}</small></span><span className={`status-pill ${row.status}`}>{row.status.replaceAll("_", " ")}</span><span className="recent-count">{row.progress.answered}/{row.question_limit} answers</span><Icon name="chevron" size={17}/></Link>)}</div> : <div className="dashboard-empty"><span className="feature-icon"><Icon name="mic" size={24}/></span><div><h3>Your first interview starts here</h3><p>Choose a topic, set your pace, and make room to improve.</p></div><Link className="secondary-button" href="/interviews/new">Start practicing <Icon name="arrow" size={16}/></Link></div>}</section></>;
}
