"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { LogoutButton } from "./logout-button";
import { Icon } from "./ui/icon";
import { WorkspaceSearch } from "./workspace-search";
import { ThemeToggle } from "./ui/theme";
import type { User } from "@/lib/types";
const candidateGroups = [
    { title: "01 / Practice", links: [["/dashboard", "Overview", "grid"], ["/interviews", "Interviews", "mic"], ["/reports", "Reports", "file"], ["/analytics", "Analytics", "chart"]] },
    { title: "02 / Prepare", links: [["/profile", "My profile", "user"], ["/resume", "My resume", "file"], ["/jobs", "Job targets", "briefcase"], ["/applications", "Opportunities", "compass"]] },
    { title: "03 / Grow", links: [["/knowledge-gaps", "Knowledge gaps", "target"], ["/learning", "Learning plans", "book"], ["/career", "Career direction", "compass"], ["/progress", "My progress", "chart"]] }
];
export function AppShell({ user, children }: {
    user: User;
    children: React.ReactNode;
}) {
    const pathname = usePathname();
    const [open, setOpen] = useState(false);
    const [collapsed, setCollapsed] = useState(false);
    useEffect(() => { const timer = window.setTimeout(() => { try { setCollapsed(localStorage.getItem("intervai-sidebar") === "collapsed"); } catch {} }, 0); return () => clearTimeout(timer); }, []);
    function toggleSidebar() { setCollapsed(value => { const next = !value; try { localStorage.setItem("intervai-sidebar", next ? "collapsed" : "expanded"); } catch {} return next; }); }
    const [expandedGroup, setExpandedGroup] = useState<{ path: string; title: string } | null>(null);
    const menuButton = useRef<HTMLButtonElement>(null);
    const sidebar = useRef<HTMLElement>(null);
    const groups = user.role === "candidate" ? candidateGroups : [{ title: "01 / Practice", links: user.role === "recruiter" ? [["/recruiter", "Recruiter workspace", "briefcase"]] : [["/admin", "System administration", "shield"]] }];
    const current = groups.flatMap(g => g.links).find(([href]) => pathname === href || pathname.startsWith(`${href}/`));
    const currentGroup = groups.find(group => group.links.some(([href]) => pathname === href || pathname.startsWith(`${href}/`)))?.title || groups[0].title;
    const visibleGroup = expandedGroup?.path === pathname ? expandedGroup.title : currentGroup;
    const home = user.role === "candidate" ? "/dashboard" : user.role === "recruiter" ? "/recruiter" : "/admin";
    useEffect(() => { if (!open)
        return; const previous = document.body.style.overflow; document.body.style.overflow = "hidden"; sidebar.current?.querySelector<HTMLElement>("a,button")?.focus(); function keydown(e: KeyboardEvent) { if (e.key === "Escape") {
        setOpen(false);
        menuButton.current?.focus();
    } if (e.key !== "Tab")
        return; const items = Array.from(sidebar.current?.querySelectorAll<HTMLElement>("a,button:not(:disabled)") || []); const first = items[0], last = items[items.length - 1]; if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
    }
    else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
    } } document.addEventListener("keydown", keydown); return () => { document.body.style.overflow = previous; document.removeEventListener("keydown", keydown); }; }, [open]);
    function closeMenu() { setOpen(false); menuButton.current?.focus(); }
    return <div className={`app-shell${collapsed ? " sidebar-collapsed" : ""}${open ? " navigation-open" : ""}`}><a className="skip-link" href="#workspace-main">Skip to content</a>{open && <button className="navigation-backdrop" onClick={closeMenu} aria-label="Close navigation" tabIndex={-1}/>}
 <aside ref={sidebar} className="sidebar" id="workspace-navigation" role={open ? "dialog" : undefined} aria-modal={open || undefined} aria-label="Workspace navigation"><button className="sidebar-collapse-toggle" type="button" onClick={toggleSidebar} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>{collapsed ? "»" : "«"}</button><div className="sidebar-brand-row"><Link className="brand" aria-label="IntervAI home" href={home} onClick={() => setOpen(false)}><span className="brand-mark"><Icon name="spark" size={23}/></span>Interv<span className="brand-ai">AI</span></Link><button className="icon-button mobile-close" onClick={closeMenu} aria-label="Close navigation"><Icon name="close"/></button></div><div className="workspace-switch"><span className="workspace-monogram">{user.role === "candidate" ? "P" : user.role === "recruiter" ? "R" : "A"}</span><span>{user.role === "candidate" ? "Personal workspace" : user.role === "recruiter" ? "Recruiter workspace" : "Administration"}<small>Prepare for what’s next</small></span></div>
 <nav className="app-navigation" aria-label="Main navigation">{groups.map((group, index) => <div className="nav-group" key={group.title}>
   <button className="nav-group-toggle" type="button" aria-expanded={visibleGroup === group.title} aria-controls={`navigation-group-${index}`} onClick={() => setExpandedGroup({ path: pathname, title: visibleGroup === group.title ? "" : group.title })}><span>{group.title}</span><Icon name="chevron" size={13}/></button>
   <div id={`navigation-group-${index}`} className="nav-group-links" hidden={!collapsed && visibleGroup !== group.title}>{group.links.map(([href, label, icon]) => { const active = pathname === href || pathname.startsWith(`${href}/`); return <Link href={href} key={href} title={label} aria-label={label} aria-current={active ? "page" : undefined} className={active ? "is-active" : undefined} onClick={() => { setOpen(false); setExpandedGroup(null); }}><Icon name={icon} size={18}/><span>{label}</span>{active && <span className="active-dot"/>}</Link>; })}</div>
 </div>)}</nav>
 {user.role === "candidate" && <Link className="sidebar-practice" href="/interviews/new" onClick={() => setOpen(false)}><Icon name="spark"/><span>A little practice. A big next step.<small>Open your interview studio</small></span><Icon name="arrow" size={16}/></Link>}
 <div className="sidebar-account"><div className="account-menu"><span className="avatar-initial">{user.display_name.charAt(0).toUpperCase()}</span><span className="account-name">{user.display_name}<small>{user.role === "admin" ? "Administrator" : `${user.role} account`}</small></span></div><LogoutButton /></div></aside>
 <main id="workspace-main" tabIndex={-1}><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" ref={menuButton} onClick={() => setOpen(true)} aria-expanded={open} aria-controls="workspace-navigation" aria-label="Open navigation"><Icon name="menu"/></button><Link href={home} className="breadcrumb-home">Workspace</Link><Icon name="chevron" size={14}/><strong>{current?.[1] || "Overview"}</strong></div><div className="topbar-actions"><WorkspaceSearch destinations={groups.flatMap(group => group.links.map(([href, label, icon]) => ({ href, label, icon, group: group.title.split(" / ").pop() || group.title })))}/><span className="workspace-private"><Icon name="shield" size={14}/> Private workspace</span><ThemeToggle />{user.role === "candidate" && <Link href="/interviews/new" className="action-button topbar-start"><Icon name="plus" size={16}/> New interview</Link>}</div></header><div className="page-content" key={pathname}>{children}</div></main></div>;
}
