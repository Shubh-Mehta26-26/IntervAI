"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Icon } from "./ui/icon";

export type WorkspaceDestination = { href: string; label: string; icon: string; group: string; keywords?: string };

/** Navigation search stays local; it never indexes or sends candidate data. */
export function WorkspaceSearch({ destinations }: { destinations: WorkspaceDestination[] }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const results = destinations.filter(item => `${item.label} ${item.group} ${item.keywords || ""}`.toLowerCase().includes(query.toLowerCase().trim()));

  function open() {
    setQuery("");
    dialog.current?.showModal();
    input.current?.focus();
  }

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (dialog.current?.open) dialog.current.close();
        else { setQuery(""); dialog.current?.showModal(); input.current?.focus(); }
      }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);

  return <>
    <button className="workspace-search-trigger" type="button" onClick={open} aria-haspopup="dialog" aria-label="Search workspace pages">
      <Icon name="search" size={17} /><span>Go to a page…</span><kbd>Ctrl K</kbd>
    </button>
    <dialog ref={dialog} className="workspace-search-dialog" aria-labelledby="workspace-search-title" onClick={event => { if (event.target === dialog.current) dialog.current.close(); }}>
      <div className="workspace-search-body">
        <header><div><p className="eyebrow">QUICK NAVIGATION</p><h2 id="workspace-search-title">Where would you like to go?</h2></div><button className="icon-button" type="button" aria-label="Close search" onClick={() => dialog.current?.close()}><Icon name="close" size={18} /></button></header>
        <label className="workspace-search-input"><Icon name="search" /><input ref={input} value={query} onChange={event => setQuery(event.target.value)} placeholder="Try interviews, resume, or learning…" aria-label="Search pages" autoComplete="off" /></label>
        <p className="search-result-count" role="status">{results.length} {results.length === 1 ? "page" : "pages"}</p>
        <div className="workspace-search-results">{results.length ? results.map(item => <Link key={item.href} href={item.href} onClick={() => dialog.current?.close()}><span className="search-result-icon"><Icon name={item.icon} size={18} /></span><span><strong>{item.label}</strong><small>{item.group}</small></span><Icon name="arrow" size={17} /></Link>) : <p className="search-empty">No pages match “{query}”. Try a different word.</p>}</div>
        <footer><span>Type to filter · Tab to browse</span><span><kbd>Esc</kbd> to close</span></footer>
      </div>
    </dialog>
  </>;
}
