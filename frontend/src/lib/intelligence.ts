import { api } from "./api";
import type { Session } from "./types";

export type Evidence = { source: string; quote: string; line: number; section: string; kind: string };
export type Skill = { slug: string; name: string; category: string; evidence: Evidence[] };
export type Facts = {
  name: string | null; email: string | null; phone: string | null; location: string | null; summary: string | null;
  skills: Skill[]; education: Evidence[]; experience: Evidence[]; projects: Evidence[]; certifications: Evidence[]; achievements: Evidence[]; links: string[]; warnings: string[];
};
export type Resume = { id: string; original_name: string; size_bytes: number; version: number; status: string; parsing_status: string; error: string | null; extracted_text: string | null; parsed_data: Facts | null; created_at: string };
export type Requirement = Skill & { requirement: string };
export type Job = { id: string; title: string; company: string | null; description: string; source: string; status: string; version: number; created_at: string; updated_at: string; analysis: { skills: Requirement[]; responsibilities: Evidence[]; qualifications: Evidence[]; experience_requirements: Evidence[]; other_requirements: Evidence[]; domain: string | null; warnings: string[] } | null };
export type Match = { id: string; resume_id: string | null; created_at: string; stale: boolean; result: { explanation: string; unassessed_requirements: Evidence[]; skills: { skill_id: string; name: string; category: string; requirement: string; status: string; explanation: string; evidence: Evidence[]; job_evidence: Evidence[] }[] } };

export async function mutate<T>(path: string, method = "POST", body: unknown = {}) {
  const session = await api<Session>("/auth/session");
  return api<T>(path, { method, headers: { "X-CSRF-Token": session.csrf_token }, body: method === "DELETE" ? undefined : JSON.stringify(body) });
}

export async function uploadResume(file: File, progress: (value: number) => void, replaceId?: string): Promise<Resume> {
  const session = await api<Session>("/auth/session");
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `/api/v1/resumes${replaceId ? `/${replaceId}/replace` : ""}`);
    request.setRequestHeader("X-CSRF-Token", session.csrf_token);
    request.timeout = 45000;
    request.upload.onprogress = event => { if (event.lengthComputable) progress(Math.round(event.loaded / event.total * 100)); };
    request.onerror = () => reject(new Error("Upload could not reach IntervAI. Please try again."));
    request.ontimeout = () => reject(new Error("Upload timed out. Check the resume list before retrying."));
    request.onload = () => {
      try { const result = JSON.parse(request.responseText); if (request.status >= 200 && request.status < 300) resolve(result); else reject(new Error(result.error?.message || "Upload failed.")); }
      catch { reject(new Error("The upload response was unavailable. Refresh the resume list.")); }
    };
    const form = new FormData(); form.append("file", file); request.send(form);
  });
}
