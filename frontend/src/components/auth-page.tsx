import Link from "next/link";
import { redirect } from "next/navigation";
import { AuthForm } from "./auth-form";
import { serverFetch } from "@/lib/server-api";

export async function AuthPage({ mode }: { mode: "login" | "register" }) {
  let signedIn = false;
  try { signedIn = (await serverFetch("/auth/session")).ok; } catch { /* The form offers a retry if the API is down. */ }
  if (signedIn) redirect("/dashboard");
  const register = mode === "register";
  return <div className="auth-layout"><section className="auth-story"><Link className="brand" href="/"><span className="brand-mark">i<span>↗</span></span>Interv<span className="brand-ai">AI</span></Link><div><p className="eyebrow">YOUR NEXT CHAPTER</p><h1>Big ambitions.<br />Small steps.<br /><em>Real progress.</em></h1><p className="story-copy">A thoughtful space to prepare for what comes next. Start with your story, your experience, and the work you want to do.</p><div className="story-steps"><span>01 <strong>Build your profile</strong></span><span>02 <strong>Define your direction</strong></span><span>03 <strong>Get ready to grow</strong></span></div></div><p className="story-footer">Personal by design. Built for your journey.</p></section><section className="auth-panel"><div className="auth-content"><span className="pill">{register ? "LET’S GET TO KNOW YOU" : "YOUR WORKSPACE AWAITS"}</span><h2>{register ? "Make room for\nyour next chapter." : "Welcome back."}</h2><p className="auth-subtitle">{register ? "Create your account, then shape a profile that reflects where you want to go." : "Sign in to pick up where you left off."}</p><AuthForm mode={mode} /><p className="auth-footnote">Your profile stays private to your account. Interview features are arriving in future phases.</p></div></section></div>;
}
