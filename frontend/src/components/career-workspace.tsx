"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { mutate } from "@/lib/intelligence";
import { statusLabels, statusOrder } from "@/lib/career";
import type { CareerAlignment, CareerAnalysis, CareerProfile, CareerRole } from "@/lib/career";
import { CareerEvidenceDetail as EvidenceDetail } from "@/components/career-direction";

function RoleCard({ value }: { value: CareerAlignment }) {
  const total = value.skills.length;
  return <section className="content-card career-role-card"><p className="eyebrow">A PATH TO EXPLORE</p><h2><Link href={`/career/roles/${value.role.id}`}>{value.role.name} ↗</Link></h2><p>{value.role.description}</p><div className="career-distribution" role="img" aria-label={statusOrder.map(status => `${statusLabels[status]}: ${value.counts[status]}`).join(", ")}>{statusOrder.filter(status => value.counts[status] > 0).map(status => <span key={status} className={`career-${status.toLowerCase()}`} style={{ flex: value.counts[status] }} />)}</div><dl className="career-counts">{statusOrder.map(status => <div key={status}><dt>{statusLabels[status]}</dt><dd>{value.counts[status]} / {total}</dd></div>)}</dl><p className="subtle-copy">Counts describe recorded evidence, not a career score. {value.role.provenance.scope}</p></section>;
}

export { CareerWorkspace } from "@/components/career-direction";

export function CareerProfileEditor() {
  const [profile,setProfile]=useState<CareerProfile|null>(null);
  const [roles,setRoles]=useState<CareerRole[]>([]);
  const [fields,setFields]=useState<Record<string,string>>({});
  const [message,setMessage]=useState("");
  const [busy,setBusy]=useState(false);
  useEffect(()=>{ let mounted=true; Promise.all([api<CareerProfile>("/career/profile"),api<CareerRole[]>("/career/roles")]).then(([p,r])=>{if(mounted){setProfile(p);setRoles(r);setFields({career_interests:p.career_interests.join(", "),...Object.fromEntries(Object.entries(p.preferences).map(([k,v])=>[k,v.join(", ")]))});}}).catch(error=>{if(mounted)setMessage(error.message);});return()=>{mounted=false;};},[]);
  if(!profile)return <section className="content-card"><h1>Career preferences</h1><p role="status">{message||"Loading your saved preferences…"}</p></section>;
  const names:Record<string,string>={career_interests:"Career interests",preferred_domains:"Preferred technical domains",geographic_preferences:"Geographic preferences you choose",industry_preferences:"Industry preferences",role_preferences:"Work and role preferences"};
  return <div className="career-workspace"><Link href="/career">← Career workspace</Link><section className="content-card"><p className="eyebrow">YOUR DIRECTION</p><h1>Make these goals your own.</h1><p>Only preferences you provide are stored. Leave fields empty when you do not have a preference.</p><p>{profile.experience_months} months of self-reported experience · <Link href="/profile">Edit experience and education ↗</Link></p><form onSubmit={event=>{event.preventDefault();setBusy(true);setMessage("");void mutate<CareerProfile>("/career/profile","PATCH",{expected_revision:profile.revision,expected_candidate_revision:profile.candidate_revision,target_roles:profile.target_roles,dismissed_roles:profile.dismissed_roles,...Object.fromEntries(Object.keys(names).map(name=>[name,(fields[name]||"").split(",").map(x=>x.trim()).filter(Boolean)]))}).then(value=>{setProfile(value);setMessage("Career preferences saved.");}).catch(error=>setMessage(error.message)).finally(()=>setBusy(false));}}><fieldset className="career-role-picker"><legend>Target roles · choose up to eight</legend>{roles.map(role=><label key={role.id}><input type="checkbox" checked={profile.target_roles.includes(role.id)} disabled={!profile.target_roles.includes(role.id)&&profile.target_roles.length>=8} onChange={event=>setProfile({...profile,target_roles:event.target.checked?[...profile.target_roles,role.id]:profile.target_roles.filter(id=>id!==role.id)})}/>{role.name}</label>)}</fieldset>{Object.entries(names).map(([name,label])=><label className="career-field" key={name}>{label}<input value={fields[name]||""} maxLength={650} onChange={event=>setFields({...fields,[name]:event.target.value})}/><small>Separate entries with commas. Empty means no preference specified.</small></label>)}<details><summary>Dismiss role suggestions</summary><p>Dismissal is your preference, not a judgment about suitability. You can still select and compare the role.</p>{roles.map(role=><label className="career-gap-choice" key={role.id}><input type="checkbox" checked={profile.dismissed_roles.includes(role.id)} onChange={event=>setProfile({...profile,dismissed_roles:event.target.checked?[...profile.dismissed_roles,role.id]:profile.dismissed_roles.filter(id=>id!==role.id)})}/>{role.name}</label>)}</details><p className="subtle-copy">Other existing goals remain available in your <Link href="/profile">candidate profile</Link>: {profile.other_goals.join(", ")||"none recorded"}.</p><button className="primary-button" disabled={busy}>{busy?"Saving…":"Save career preferences ↗"}</button>{message&&<p role="status">{message}</p>}</form></section></div>;
}

export function CareerRoleDetail({ identifier }: { identifier:string }) {
  const [role,setRole]=useState<CareerRole|null>(null);
  const [analysis,setAnalysis]=useState<CareerAnalysis|null>(null);
  const [message,setMessage]=useState("");
  useEffect(()=>{let mounted=true;Promise.all([api<CareerRole>(`/career/roles/${identifier}`),api<CareerAnalysis|null>("/career/readiness")]).then(([r,a])=>{if(mounted){setRole(r);setAnalysis(a);}}).catch(error=>{if(mounted)setMessage(error.message);});return()=>{mounted=false;};},[identifier]);
  if(!role)return <section className="content-card"><p role="status">{message||"Loading role definition…"}</p></section>;
  const alignment=analysis?.result.alignments.find(value=>value.role.id===identifier);
  return <div className="career-workspace"><Link href="/career">← Compare career paths</Link><section className="content-card"><p className="eyebrow">ILLUSTRATIVE ROLE DEFINITION · VERSION {role.version}</p><h1>{role.name}</h1><p>{role.description}</p><ul>{role.responsibilities.map(item=><li key={item}>{item}</li>)}</ul><p className="subtle-copy">{role.provenance.source}. {role.provenance.scope}</p><div className="career-requirements">{["required","preferred"].map(kind=><div key={kind}><h2>{kind==="required"?"Illustrative core skills":"Additional areas to explore"}</h2><ul>{role.requirements.filter(item=>item.requirement===kind).map(item=><li key={item.skill}>{item.skill}</li>)}</ul></div>)}</div></section>{alignment?<><RoleCard value={alignment}/><section className="content-card"><h2>Your saved evidence for this path</h2><p>Analysis {analysis?.version}. {analysis?.stale?"Relevant evidence has changed; request a refresh in the career workspace.":"Labels reflect this saved snapshot."}</p>{alignment.skills.map(skill=><div className="career-job-skill" key={skill.skill}><strong>{skill.skill} · {statusLabels[skill.status]}</strong><EvidenceDetail value={skill}/></div>)}</section></>:<section className="content-card"><h2>No analysis for this role yet.</h2><p>Select this role in the career workspace to compare your actual evidence.</p><Link className="primary-link" href="/career">Explore this role ↗</Link></section>}</div>;
}
