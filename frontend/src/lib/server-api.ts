import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { Profile, Session } from "./types";

export async function serverFetch(path: string) {
  return fetch(`${process.env.API_INTERNAL_URL || "http://127.0.0.1:8000"}/api/v1${path}`, {
    headers: { Cookie: (await cookies()).toString() },
    cache: "no-store", signal: AbortSignal.timeout(8000),
  });
}

export async function requireSession(): Promise<Session> {
  const response = await serverFetch("/auth/session");
  if (response.status === 401) redirect("/login");
  if (!response.ok) throw new Error("The account service is unavailable. Please try again.");
  return response.json();
}

export async function getProfile(): Promise<Profile> {
  const response = await serverFetch("/candidates/me");
  if (response.status === 401) redirect("/login");
  if (!response.ok) throw new Error("Your profile could not be loaded. Please try again.");
  return response.json();
}
