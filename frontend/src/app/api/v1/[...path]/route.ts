import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
const routes: Record<string, string[]> = {
  "career/profile": ["GET", "PATCH"], "career/roles": ["GET"], "career/analyze": ["POST"],
  "career/analyses": ["GET"], "career/readiness": ["GET"], "career/skill-gaps": ["GET"],
  "career/roadmap": ["POST"], "career/choices": ["POST"],
  "auth/register": ["POST"], "auth/login": ["POST"], "auth/logout": ["POST"],
  "auth/session": ["GET"], "auth/me": ["GET"], "candidates/me": ["GET", "PATCH"],
  "resumes": ["GET", "POST"], "jobs": ["GET", "POST"], "skills": ["GET"],
  "coding/problems": ["GET", "POST"], "coding/provider": ["GET"], "coding/problems/generate": ["POST"],
  "interviews": ["GET", "POST"], "interviews/provider": ["GET"],
  "candidates/me/memory": ["GET"], "candidates/me/skills/history": ["GET"],
  "candidates/me/concepts/history": ["GET"], "candidates/me/knowledge-gaps": ["GET"],
  "candidates/me/misconceptions": ["GET"],
  "learning/plans": ["GET", "POST"], "learning/retries": ["POST"],
  "candidates/me/progress": ["GET"],
  "reports": ["GET"], "applications": ["GET", "POST"], "applications/jobs": ["GET"],
  "analytics/overview": ["GET"], "analytics/skills": ["GET"], "analytics/learning": ["GET"],
  "recruiter/jobs": ["GET", "POST"], "admin/system-status": ["GET"], "admin/users": ["GET"], "admin/audit": ["GET"],
};

function allowed(path: string, method: string) {
  if (routes[path]?.includes(method)) return true;
  const id = "[a-fA-F0-9-]{36}";
  if (/^career\/roles\/[a-z0-9-]{1,80}$/.test(path)) return method === "GET";
  if (new RegExp(`^reports/${id}$`).test(path)) return method === "GET";
  if (new RegExp(`^reports/${id}/pdf$`).test(path)) return method === "GET";
  if (new RegExp(`^reports/${id}/generate$`).test(path)) return method === "POST";
  if (new RegExp(`^applications/${id}$`).test(path)) return method === "PATCH";
  if (new RegExp(`^recruiter/jobs/${id}$`).test(path)) return method === "PATCH";
  if (new RegExp(`^recruiter/jobs/${id}/applications$`).test(path)) return method === "GET";
  if (new RegExp(`^recruiter/applications/${id}$`).test(path)) return method === "GET";
  if (new RegExp(`^recruiter/applications/${id}/reports/${id}(/pdf)?$`).test(path)) return method === "GET";
  if (new RegExp(`^admin/users/${id}/role$`).test(path)) return method === "PATCH";
  if (new RegExp(`^career/analyses/${id}$`).test(path)) return method === "GET";
  if (new RegExp(`^career/analyses/${id}/advice$`).test(path)) return method === "POST";
  if (new RegExp(`^interviews/${id}/vision/(session|frame|notice)$`).test(path)) return method === "POST";
  if (new RegExp(`^interviews/${id}/(vision/status|integrity-events)$`).test(path)) return method === "GET";
  if (new RegExp(`^interviews/${id}/coding/(run|submit)$`).test(path)) return method === "POST";
  if (new RegExp(`^interviews/${id}/coding/submissions$`).test(path)) return method === "GET";
  if (new RegExp(`^coding/problems/${id}$`).test(path)) return method === "GET";
  if (new RegExp(`^coding/problems/${id}/validate$`).test(path)) return method === "POST";
  if (new RegExp(`^coding/submissions/${id}(/status)?$`).test(path)) return method === "GET";
  if (new RegExp(`^coding/submissions/${id}/cancel$`).test(path)) return method === "POST";
  if (new RegExp(`^interviews/${id}/voice/(session|event|transcribe|synthesize)$`).test(path)) return method === "POST";
  if (new RegExp(`^interviews/${id}/voice/(status|audio/${id})$`).test(path)) return method === "GET";
  if (new RegExp(`^learning/(plans|items|attempts)/${id}$`).test(path)) return method === "GET";
  if (new RegExp(`^learning/plans/${id}/start$`).test(path)) return method === "POST";
  if (new RegExp(`^learning/items/${id}/(complete|practice|generate)$`).test(path)) return method === "POST";
  if (new RegExp(`^learning/items/${id}/practice/${id}/submit$`).test(path)) return method === "POST";
  if (new RegExp(`^knowledge-gaps/${id}/(learning-plan|retry)$`).test(path)) return method === "POST";
  if (new RegExp(`^candidates/me/knowledge-gaps/${id}$`).test(path)) return method === "GET";
  if (new RegExp(`^candidates/me/memory/${id}/evidence$`).test(path)) return method === "GET";
  if (new RegExp(`^resumes/${id}$`).test(path)) return ["GET", "DELETE"].includes(method);
  if (new RegExp(`^resumes/${id}/file$`).test(path)) return method === "GET";
  if (new RegExp(`^resumes/${id}/(retry|replace)$`).test(path)) return method === "POST";
  if (new RegExp(`^jobs/${id}$`).test(path)) return ["GET", "PATCH", "DELETE"].includes(method);
  if (new RegExp(`^jobs/${id}/analyze$`).test(path)) return method === "POST";
  if (new RegExp(`^jobs/${id}/match$`).test(path)) return ["GET", "POST"].includes(method);
  if (new RegExp(`^interviews/${id}$`).test(path)) return method === "GET";
  if (method === "GET" && new RegExp(`^interviews/${id}/(current|questions|answers|summary)$`).test(path)) return true;
  return new RegExp(`^interviews/${id}/(start|answers|pause|resume|complete|cancel)$`).test(path) && method === "POST";
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const path = (await context.params).path.join("/");
  if (!allowed(path, request.method)) return NextResponse.json({ error: { code: "not_found", message: "Endpoint not found." } }, { status: 404 });
  const headers = new Headers();
  for (const name of ["cookie", "content-type", "origin", "x-csrf-token"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    let body: ArrayBuffer | undefined;
    if (request.method !== "GET" && request.body) {
      const audio = /^interviews\/[a-fA-F0-9-]{36}\/voice\/transcribe$/.test(path);
      const vision = /^interviews\/[a-fA-F0-9-]{36}\/vision\/frame$/.test(path);
      const upload = request.method === "POST" && (vision || audio || path === "resumes" || /^resumes\/[a-fA-F0-9-]{36}\/replace$/.test(path));
      const contentType = request.headers.get("content-type") || "";
      if (!(upload ? contentType.startsWith("multipart/form-data;") : contentType.startsWith("application/json"))) return NextResponse.json({ error: { message: upload ? "A document upload is required." : "JSON content is required." } }, { status: 415 });
      const reader = request.body.getReader();
      const parts: Uint8Array[] = [];
      let size = 0;
      const deadline = Date.now() + 30000;
      while (true) {
        let timer: ReturnType<typeof setTimeout> | undefined;
        const { done, value } = await Promise.race([reader.read(), new Promise<ReadableStreamReadResult<Uint8Array>>((_, reject) => { timer = setTimeout(() => { void reader.cancel(); reject(new Error("Upload timeout")); }, Math.max(1, deadline - Date.now())); })]).finally(() => clearTimeout(timer));
        if (done) break;
        size += value.byteLength;
        if (size > (vision ? 131072 + 8192 : audio ? 6 * 1024 * 1024 + 65536 : upload ? 10 * 1024 * 1024 + 65536 : 65536)) {
          await reader.cancel();
          return NextResponse.json({ error: { message: "Request is too large." } }, { status: 413 });
        }
        parts.push(value);
      }
      const combined = new Uint8Array(size);
      let offset = 0;
      for (const part of parts) { combined.set(part, offset); offset += part.byteLength; }
      body = combined.buffer;
    }
    const result = await fetch(`${process.env.API_INTERNAL_URL || "http://127.0.0.1:8000"}/api/v1/${path}${request.nextUrl.search}`, {
      method: request.method, headers, body, redirect: "manual", cache: "no-store", signal: AbortSignal.timeout(path === "coding/problems/generate" || /^career\/analyses\/[a-fA-F0-9-]{36}\/advice$/.test(path) ? 195000 : /^learning\/items\/[a-fA-F0-9-]{36}\/generate$/.test(path) ? 195000 : 15000),
    });
    const response = new NextResponse(result.status === 204 ? null : result.body, { status: result.status });
    for (const name of ["Content-Type", "Content-Disposition", "Content-Security-Policy", "X-Content-Type-Options"]) {
      const value = result.headers.get(name); if (value) response.headers.set(name, value);
    }
    response.headers.set("Cache-Control", "no-store");
    for (const cookie of result.headers.getSetCookie()) response.headers.append("Set-Cookie", cookie);
    return response;
  } catch {
    return NextResponse.json({ error: { code: "unavailable", message: "The account service is unavailable. Please try again." } }, { status: 503 });
  }
}
export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
