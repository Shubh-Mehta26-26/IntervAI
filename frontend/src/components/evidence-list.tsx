import type { Evidence } from "@/lib/intelligence";

export function EvidenceList({ items, empty = "No information extracted." }: { items: Evidence[]; empty?: string }) {
  if (!items.length) return <p className="subtle-copy">{empty}</p>;
  return <ul className="evidence-list">{items.map((item, index) => <li key={`${item.line}-${index}`}><blockquote>{item.quote}</blockquote><small>{item.source.startsWith("resume:") ? "Selected resume" : item.source === "profile" ? "Candidate profile" : "Job description"} · {item.section} · line {item.line}</small></li>)}</ul>;
}
