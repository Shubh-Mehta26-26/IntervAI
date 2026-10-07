"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Session } from "@/lib/types";

export function LogoutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function logout() {
    setPending(true); setError("");
    try {
      const session = await api<Session>("/auth/session");
      await api("/auth/logout", { method: "POST", headers: { "X-CSRF-Token": session.csrf_token }, body: "{}" });
      router.replace("/login"); router.refresh();
    } catch { setError("Could not sign out. Please try again."); setPending(false); }
  }
  return <div><button type="button" className="logout-button" onClick={logout} disabled={pending}>{pending ? "Signing out…" : "Sign out ↗"}</button>{error && <p role="alert" className="field-error">{error}</p>}</div>;
}
