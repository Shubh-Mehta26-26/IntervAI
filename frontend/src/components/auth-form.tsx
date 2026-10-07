"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const register = mode === "register";
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [created, setCreated] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(""); setFields({}); setPending(true);
    const values = { email: String(form.get("email")), password: String(form.get("password")) };
    if (register && values.password !== form.get("confirm_password")) { setFields({ confirm_password: "Passwords must match." }); setPending(false); return; }
    try {
      if (register && !created) {
        await api("/auth/register", { method: "POST", body: JSON.stringify({ ...values, display_name: form.get("display_name") }) });
        setCreated(true);
      }
      await api("/auth/login", { method: "POST", body: JSON.stringify(values) });
      router.replace(register ? "/profile" : "/dashboard"); router.refresh();
    } catch (problem) { const issue = problem as ApiError; setError(issue.message); setFields(issue.fields || {}); }
    finally { setPending(false); }
  }
  return <form onSubmit={submit} className="auth-form">
    {created && <p className="success-message" role="status">Your account is created. Sign in to continue.</p>}
    {error && <p className="error-message" role="alert">{error}</p>}
    {register && <label className="field">Full name<input name="display_name" autoComplete="name" required maxLength={120} aria-invalid={!!fields.display_name} aria-describedby="name-error" /><span id="name-error" className="field-error">{fields.display_name}</span></label>}
    <label className="field">Email address<input name="email" type="email" autoComplete="email" required maxLength={320} placeholder="you@example.com" aria-invalid={!!fields.email} aria-describedby="email-error" /><span id="email-error" className="field-error">{fields.email}</span></label>
    <label className="field">Password<span className="password-wrap"><input name="password" type={showPassword ? "text" : "password"} autoComplete={register ? "new-password" : "current-password"} required minLength={register ? 12 : 1} maxLength={128} aria-invalid={!!fields.password} aria-describedby="password-help password-error" /><button type="button" className="password-toggle" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? "Hide" : "Show"}</button></span><span id="password-help" className="field-help">{register ? "Use 12 or more characters. A memorable passphrase works well." : "Use the password you created for IntervAI."}</span><span id="password-error" className="field-error">{fields.password}</span></label>
    {register && <label className="field">Confirm password<input name="confirm_password" type="password" autoComplete="new-password" required minLength={12} maxLength={128} aria-invalid={!!fields.confirm_password} aria-describedby="confirm-error" /><span id="confirm-error" className="field-error">{fields.confirm_password}</span></label>}
    <button className="action-button" disabled={pending} type="submit">{pending ? "One moment…" : register && !created ? "Create your account ↗" : "Sign in ↗"}</button>
    <p className="auth-switch">{register ? "Already have an account?" : "New to IntervAI?"} <Link href={register ? "/login" : "/register"}>{register ? "Sign in" : "Start your journey"}</Link></p>
  </form>;
}
