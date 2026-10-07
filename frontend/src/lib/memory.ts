export type MemoryItem = {
  id: string; kind: string; subject: string; topic: string; evidence_count: number;
  interview_count: number; mean_correctness: number | null; evidence_strength: number;
  trend: string; first_seen: string; last_seen: string;
};
export type Gap = {
  id: string; memory_id: string; subject: string; kind: string; topic: string; status: string;
  evidence_count: number; interview_count: number; independent_count: number;
  weak_interview_count: number; weakness_index: number; trend: string; first_seen: string;
  last_seen: string; policy_version: string; provisional: boolean;
};
export type Observation = {
  id: string; interview_id: string; question_id: string; answer_id: string; evaluation_id: string;
  question: string; answer_excerpt: string; correctness: number; confidence: number; grounded: boolean;
  signals: string[]; observed_at: string;
  sources: { chunk_id: string; title: string; source: string; claim: string; relationship: string }[];
};
export type GapDetail = Gap & {
  evidence: Observation[];
  transitions: { from_status: string | null; to_status: string; reason: string; created_at: string }[];
};
export type History = MemoryItem & {
  history: { id: string; interview_id: string; evaluation_id: string; correctness: number; grounded: boolean; observed_at: string }[];
};
