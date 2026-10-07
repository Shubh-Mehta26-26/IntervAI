"use client";

import { useEffect, useState } from "react";

type Health = { api: string; database: string; vector: string };

async function fetchHealth(): Promise<Health> {
  try {
    const response = await fetch("/api/health", { cache: "no-store", signal: AbortSignal.timeout(9000) });
    return await response.json();
  } catch {
    return { api: "unavailable", database: "unknown", vector: "unknown" };
  }
}

export function SystemStatus() {
  const [health, setHealth] = useState<Health | null>(null);
  const [checking, setChecking] = useState(true);
  async function check() {
    setChecking(true);
    setHealth(await fetchHealth());
    setChecking(false);
  }

  useEffect(() => {
    let active = true;
    fetchHealth().then((result) => {
      if (active) { setHealth(result); setChecking(false); }
    });
    return () => { active = false; };
  }, []);

  const items = [
    ["Frontend", "connected"],
    ["API service", health?.api],
    ["PostgreSQL", health?.database],
    ["Vector extension", health?.vector],
  ];

  return <section className="status-card" aria-labelledby="status-title">
    <div className="section-heading"><div><p className="eyebrow">LIVE CONNECTION CHECK</p><h2 id="status-title">System readiness</h2></div>
      <button onClick={() => void check()} disabled={checking}>{checking ? "Checking…" : "Check again ↗"}</button>
    </div>
    <div className="status-grid" aria-live="polite" aria-busy={checking}>
      {items.map(([label, status]) => {
        const good = status === "connected" || status === "available";
        return <div className="status-item" key={label}><span className={`dot ${checking ? "pending" : good ? "good" : "pending"}`} />
          <div><h3>{label}</h3><p>{checking ? "Checking" : status === "unknown" ? "Not verified" : status || "Not verified"}</p></div></div>;
      })}
    </div>
    <p className="status-note">These checks use the running services. An unavailable dependency needs setup before the next phase.</p>
  </section>;
}
