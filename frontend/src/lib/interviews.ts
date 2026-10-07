export type ProviderStatus = { configured: boolean; provider: string | null; model: string | null; message: string };
export type Question = { coding_problem_id: string | null; id: string; sequence: number; text: string; topic: string; skill: string | null; difficulty: number; question_type: string; state: string };
export type KnowledgeEvidence = { knowledge_chunk_id: string; document_id: string; title: string; source: string; content: string; retrieval_rank: number; similarity: number; claim: string; relationship: "supports" | "contradicts" | "insufficient" };
export type Evaluation = { correctness: number; relevance: number; completeness: number; technical_depth: number; reasoning: number; clarity: number; strengths: string[]; weaknesses: string[]; missing_concepts: string[]; misconceptions: string[]; evidence: string[]; feedback: string; hint: string | null; confidence: number; grounding_status: "grounded" | "insufficient"; evaluation_notes: string; knowledge_evidence: KnowledgeEvidence[] };
export type Decision = { action: string; target_topic: string | null; difficulty: number; reason_codes: string[]; explanation: string; policy_version: string };
export type Interview = {
  id: string; interview_type: "technical" | "project" | "behavioral" | "mixed" | "coding"; mode: "practice" | "simulation";
  status: string; revision: number; job_id: string | null; resume_id: string | null; question_limit: number;
  duration_minutes: number | null; configuration: { selected_topics: string[]; difficulty: number; candidate_focus: string; instructions: string; show_hints: boolean };
  current_round: number; current_question: number; progress: { answered: number; total: number }; started_at: string | null;
  completed_at: string | null; created_at: string; updated_at: string; current: Question | null;
  plan: { id: string; objectives: string[]; topics: { title: string; objective: string; question_budget: number; initial_difficulty: number }[] } | null;
  practice_feedback: Evaluation | null; practice_decision: Decision | null; summary: { dimension_averages: Record<string, number | null>; evaluated_answers: number; strengths: string[]; development_areas: string[]; note: string } | null;
  error: { code: string; message: string } | null;
};
