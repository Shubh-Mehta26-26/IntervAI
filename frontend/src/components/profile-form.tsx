"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Education, Experience, Preferences, Profile, Session } from "@/lib/types";

export function ProfileForm({ initial }: { initial: Profile }) {
  const router = useRouter();
  const [profile, setProfile] = useState(initial);
  const [goals, setGoals] = useState(initial.goals.map(g => g.role_title).join(", "));
  const [interests, setInterests] = useState(initial.career_interests.join(", "));
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [expired, setExpired] = useState(false);
  function update<K extends keyof Profile>(key: K, value: Profile[K]) { setProfile(p => ({ ...p, [key]: value })); setMessage(""); }
  function updateEducation(index: number, value: Partial<Education>) { update("education", profile.education.map((item, i) => i === index ? { ...item, ...value } : item)); }
  function updateExperience(index: number, value: Partial<Experience>) { update("experience", profile.experience.map((item, i) => i === index ? { ...item, ...value } : item)); }
  function preference<K extends keyof Preferences>(key: K, value: Preferences[K]) { update("preferences", { ...profile.preferences, [key]: value }); }
  const split = (value: string) => value.split(",").map(v => v.trim()).filter(Boolean);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setPending(true); setError(""); setMessage(""); setFields({}); setExpired(false);
    try {
      const session = await api<Session>("/auth/session");
      const { display_name, phone, location, headline, biography, timezone, experience_months, education, experience, preferences } = profile;
      const saved = await api<Profile>("/candidates/me", { method: "PATCH", headers: { "X-CSRF-Token": session.csrf_token }, body: JSON.stringify({
        expected_revision: profile.revision, display_name, phone: phone || null, location: location || null,
        headline: headline || null, biography: biography || null, timezone, experience_months, education, experience, preferences,
        career_interests: split(interests), goals: split(goals).map((role_title, priority) => ({ role_title, priority, active: true })),
      }) });
      setProfile(saved); setMessage("Profile saved. Your changes are ready for your next visit."); router.refresh();
    } catch (problem) {
      const issue = problem as ApiError;
      setError(issue.message); setFields(issue.fields || {}); setExpired(issue.status === 401);
    } finally { setPending(false); }
  }

  function field(name: string, label: string, value: string, onChange: (value: string) => void, maxLength: number, required = false, type = "text") {
    return <label className="field">{label}<input name={name} value={value} onChange={e => onChange(e.target.value)} maxLength={maxLength} required={required} type={type} aria-invalid={!!fields[name]} aria-describedby={`${name}-error`} /><span className="field-error" id={`${name}-error`}>{fields[name]}</span></label>;
  }

  return <form className="profile-form" onSubmit={save}>
    <div className="profile-heading"><div><p className="eyebrow">THE PERSON BEHIND THE POTENTIAL</p><h1>Your story.<br /><em>Your direction.</em></h1><p className="subtle-copy">A few details today. More personal preparation tomorrow.</p></div><div className="profile-stamp"><span>{profile.display_name.charAt(0).toUpperCase()}</span><p>YOUR PROFILE<br /><strong>Always evolving</strong></p></div></div>
    <fieldset disabled={pending} className="profile-fields">
    <section className="content-card"><div className="form-section-title"><span>01</span><div><h2>The essentials</h2><p>How you introduce yourself to the world.</p></div></div><div className="form-grid">
      {field("display_name", "Full name", profile.display_name, value => update("display_name", value), 120, true)}
      <label className="field">Email address<input value={profile.email} disabled type="email" /><span className="field-help">Account email. Email changes will be supported in a later phase.</span></label>
      {field("phone", "Phone (optional)", profile.phone || "", value => update("phone", value), 40, false, "tel")}
      {field("location", "Location", profile.location || "", value => update("location", value), 160)}
      <div className="full-span">{field("headline", "Professional headline", profile.headline || "", value => update("headline", value), 200)}</div>
      <label className="field full-span">About you<textarea name="biography" rows={4} maxLength={3000} value={profile.biography || ""} onChange={e => update("biography", e.target.value)} placeholder="What are you curious about? What are you working towards?" /><span className="field-help">{profile.biography?.length || 0} / 3,000 characters</span></label>
    </div></section>
    <section className="content-card"><div className="form-section-title"><span>02</span><div><h2>Your next chapter</h2><p>Give your preparation a little direction.</p></div></div><div className="form-grid">
      <label className="field full-span">Target roles<input name="goals" value={goals} onChange={e => { setGoals(e.target.value); setMessage(""); }} maxLength={1200} placeholder="Backend engineer, AI engineer" /><span className="field-help">Separate up to 10 roles with commas. Put your first choice first.</span></label>
      <label className="field full-span">Career interests<input name="career_interests" value={interests} onChange={e => { setInterests(e.target.value); setMessage(""); }} maxLength={960} placeholder="Artificial intelligence, distributed systems" /><span className="field-help">Separate up to 12 interests with commas.</span></label>
      <label className="field">Total professional experience (months)<input name="experience_months" type="number" min={0} max={720} step={1} required value={profile.experience_months} onChange={e => update("experience_months", Number(e.target.value))} /><span className="field-help">Use 0 if you’re just getting started.</span></label>
      {field("timezone", "Timezone", profile.timezone, value => update("timezone", value), 64, true)}
    </div></section>
    <section className="content-card"><div className="form-section-title"><span>03</span><div><h2>Education</h2><p>What you’ve studied, and what you’re studying now.</p></div></div>
      {profile.education.length === 0 && <p className="empty-row">No education added yet. Add it when you’re ready.</p>}
      {profile.education.map((item, index) => <div className="repeat-card" key={index}><div className="repeat-heading"><h3>Education {index + 1}</h3><button type="button" className="remove-button" onClick={() => update("education", profile.education.filter((_, i) => i !== index))}>Remove education {index + 1}</button></div><div className="form-grid">
        {field(`education.${index}.institution`, "Institution", item.institution, value => updateEducation(index, { institution: value }), 160, true)}
        {field(`education.${index}.qualification`, "Qualification", item.qualification, value => updateEducation(index, { qualification: value }), 160, true)}
        <div className="full-span">{field(`education.${index}.field_of_study`, "Field of study", item.field_of_study || "", value => updateEducation(index, { field_of_study: value }), 160)}</div>
        {field(`education.${index}.start_date`, "Education start date", item.start_date || "", value => updateEducation(index, { start_date: value || null }), 10, false, "date")}
        {field(`education.${index}.end_date`, "Education end date (optional)", item.end_date || "", value => updateEducation(index, { end_date: value || null }), 10, false, "date")}
      </div></div>)}
      <button type="button" className="secondary-button" disabled={profile.education.length >= 20} onClick={() => update("education", [...profile.education, { institution: "", qualification: "", field_of_study: null, start_date: null, end_date: null }])}>+ Add education</button>
    </section>
    <section className="content-card"><div className="form-section-title"><span>04</span><div><h2>Experience</h2><p>Roles, internships, and the work you’ve done.</p></div></div>
      {profile.experience.length === 0 && <p className="empty-row">Your experience doesn’t have to be extensive. Start wherever you are.</p>}
      {profile.experience.map((item, index) => <div className="repeat-card" key={index}><div className="repeat-heading"><h3>Experience {index + 1}</h3><button type="button" className="remove-button" onClick={() => update("experience", profile.experience.filter((_, i) => i !== index))}>Remove experience {index + 1}</button></div><div className="form-grid">
        {field(`experience.${index}.organization`, "Organization", item.organization, value => updateExperience(index, { organization: value }), 160, true)}
        {field(`experience.${index}.title`, "Role title", item.title, value => updateExperience(index, { title: value }), 160, true)}
        {field(`experience.${index}.start_date`, "Role start date", item.start_date || "", value => updateExperience(index, { start_date: value || null }), 10, false, "date")}
        {field(`experience.${index}.end_date`, "Role end date (optional)", item.end_date || "", value => updateExperience(index, { end_date: value || null }), 10, false, "date")}
        <label className="field full-span">What did you work on?<textarea rows={3} maxLength={2000} value={item.description || ""} onChange={e => updateExperience(index, { description: e.target.value })} /></label>
      </div></div>)}
      <button type="button" className="secondary-button" disabled={profile.experience.length >= 20} onClick={() => update("experience", [...profile.experience, { organization: "", title: "", description: null, start_date: null, end_date: null }])}>+ Add experience</button>
    </section>
    <section className="content-card"><div className="form-section-title"><span>05</span><div><h2>How you’d like to practice</h2><p>Save your preferences for future interview features.</p></div></div><div className="form-grid">
      <label className="field">Preferred interaction<select name="interview_mode" value={profile.preferences.interview_mode} onChange={e => preference("interview_mode", e.target.value as Preferences["interview_mode"])}><option value="text">Text</option><option value="voice">Voice (future feature)</option></select></label>
      <label className="field">Preferred interview length<select name="interview_duration_minutes" value={profile.preferences.interview_duration_minutes} onChange={e => preference("interview_duration_minutes", Number(e.target.value) as Preferences["interview_duration_minutes"])}>{[10,20,30,45,60].map(value => <option key={value} value={value}>{value} minutes</option>)}</select></label>
      <label className="field">Preferred language<select name="locale" value={profile.preferences.locale} onChange={e => preference("locale", e.target.value as Preferences["locale"])}><option value="en">English</option><option value="en-IN">English (India)</option><option value="hi">Hindi</option></select><span className="field-help">A saved preference, not a guarantee of model language support.</span></label>
    </div></section>
    </fieldset>
    <div className="save-bar"><div aria-live="polite">{message && <p className="success-message" role="status">{message}</p>}{error && <div className="error-message" role="alert"><p>{error}</p>{Object.entries(fields).map(([name, text]) => <p key={name}>{name}: {text}</p>)}{expired && <a href="/login" target="_blank" rel="noopener noreferrer">Sign in in a new tab, then save again. Your draft stays here.</a>}</div>}{!message && !error && <p>Your profile is private to your account.</p>}</div><button className="action-button" type="submit" disabled={pending}>{pending ? "Saving…" : "Save profile ↗"}</button></div>
  </form>;
}
