export class ApiError extends Error {
  constructor(public status: number, message: string, public fields: Record<string, string> = {}) { super(message); }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...options, cache: "no-store", credentials: "same-origin", signal: AbortSignal.timeout(/^\/learning\/items\/[a-fA-F0-9-]{36}\/generate$/.test(path) ? 200000 : 20000),
      headers: { "Content-Type": "application/json", ...options.headers },
    });
  } catch { throw new ApiError(503, "We couldn’t reach IntervAI. Your changes are still here; please try again."); }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const fields = Object.fromEntries((body.error?.details || []).map((item: { field: string; message: string }) => [item.field, item.message]));
    throw new ApiError(response.status, body.error?.message || "Something went wrong. Please try again.", fields);
  }
  return response.status === 204 ? undefined as T : response.json();
}
