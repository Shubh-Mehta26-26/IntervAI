import Link from "next/link";
import { redirect } from "next/navigation";
import { AuthForm } from "./auth-form";
import { serverFetch } from "@/lib/server-api";
import { Icon } from "./ui/icon";
import { ThemeToggle } from "./ui/theme";
import { PracticeIllustration } from "./practice-illustration";
export async function AuthPage({ mode }: {
    mode: "login" | "register";
}) {
    let signedIn = false;
    try {
        signedIn = (await serverFetch("/auth/session")).ok;
    }
    catch { /* The form reports service failures. */ }
    if (signedIn)
        redirect("/dashboard");
    const register = mode === "register";
    return <div className="auth-layout">
      <section className="auth-story">
        <Link className="brand" href="/"><span className="brand-mark"><Icon name="spark" size={23}/></span>Interv<span className="brand-ai">AI</span></Link>
        <div className="auth-story-main"><span className="auth-kicker"><span className="dot"/> A SPACE FOR YOUR NEXT CHAPTER</span><h1>Find your voice.<br/><em>Meet your future.</em></h1><p className="story-copy">A little practice. A clearer direction. Interviews that adapt to you, and feedback that helps you grow.</p><PracticeIllustration /></div>
        <p className="story-footer"><Icon name="shield" size={15}/> Your preparation. Your pace. Your private space.</p>
      </section>
      <section className="auth-panel"><div className="auth-panel-top"><span>PREPARE / PRACTICE / PROGRESS</span><ThemeToggle /></div>
        <div className="auth-content"><span className="auth-form-icon"><Icon name={register ? "user" : "spark"} size={25}/></span><p className="eyebrow">{register ? "MAKE ROOM FOR WHAT’S NEXT" : "YOUR WORKSPACE IS WAITING"}</p><h2>{register ? "Let’s begin your next chapter." : "Good to have you back."}</h2><p className="auth-subtitle">{register ? "Create an account to start practising and building your skills." : "Sign in and pick up where you left off."}</p><AuthForm mode={mode}/><p className="auth-footnote"><Icon name="shield" size={15}/> Your profile, practice sessions, and progress stay in your account.</p></div>
        <p className="auth-bottom">Built for your next opportunity.<span>IntervAI</span></p>
      </section>
    </div>;
}
