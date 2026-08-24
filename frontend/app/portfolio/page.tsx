"use client";

import Link from "next/link";
import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, ArrowUpRight, FolderKanban, MapPinned, Plus, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import { AppShell } from "../../components/app-shell";
import { backendFetch, Project } from "../../components/data";

type ProjectRow = Project & { zoneCount: number | null };

export default function PortfolioPage() {
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [creating, setCreating] = useState(false);

  const loadProjects = useCallback(async (isRefresh = false) => {
    setError("");
    if (isRefresh) setRefreshing(true); else setLoading(true);
    try {
      const result = await backendFetch<Project[]>("/api/v1/projects");
      const rows = await Promise.all(result.map(async (project): Promise<ProjectRow> => {
        try {
          const zones = await backendFetch<Array<{ id: string }>>(`/api/v1/projects/${project.id}/zones`);
          return { ...project, zoneCount: zones.length };
        } catch { return { ...project, zoneCount: null }; }
      }));
      setProjects(rows);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "The workspace could not be loaded."); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { void loadProjects(); }, [loadProjects]);

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectName.trim()) return;
    setCreating(true); setError("");
    try {
      await backendFetch("/api/v1/projects", { method: "POST", body: JSON.stringify({ name: projectName.trim(), description: projectDescription.trim() || null }) });
      setProjectName(""); setProjectDescription(""); setShowCreate(false); await loadProjects(true);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "The project could not be created."); }
    finally { setCreating(false); }
  }

  const zoneCount = useMemo(() => projects.reduce((total, project) => total + (project.zoneCount ?? 0), 0), [projects]);
  const mappedProjects = projects.filter((project) => (project.zoneCount ?? 0) > 0).length;

  return (
    <AppShell title="Overview">
      <header className="page-head portfolio-head">
        <div><span className="eyebrow">PORTFOLIO OVERVIEW</span><h1>Your cooling workspace</h1><p>Move from neighborhood heat to an approved, measurable action plan.</p></div>
        <div className="page-actions"><button className="button" type="button" onClick={() => void loadProjects(true)} disabled={loading || refreshing}><RefreshCw size={15} className={refreshing ? "spin" : ""} />{refreshing ? "Refreshing" : "Refresh"}</button><button className="button primary" type="button" onClick={() => setShowCreate((value) => !value)}><Plus size={16} />New project</button></div>
      </header>

      {showCreate ? <section className="create-panel"><div><span className="eyebrow">NEW PROJECT</span><h2>Start a cooling decision</h2><p>Create the workspace first. You can add a project area and request heat evidence next.</p></div><form onSubmit={createProject}><div className="field"><label htmlFor="project-name">Project name</label><input id="project-name" value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="e.g. Central school corridor" required autoFocus /></div><div className="field"><label htmlFor="project-description">Description</label><input id="project-description" value={projectDescription} onChange={(event) => setProjectDescription(event.target.value)} placeholder="What decision is this project supporting?" /></div><div className="create-actions"><button className="button" type="button" onClick={() => setShowCreate(false)}>Cancel</button><button className="button primary" disabled={creating}>{creating ? "Creating…" : "Create project"}</button></div></form></section> : null}

      {error ? <div className="error portfolio-error" role="alert"><strong>Workspace unavailable</strong><span>{error}</span><button className="button" onClick={() => void loadProjects()}>Try again</button></div> : null}

      <section className="overview-grid" aria-label="Portfolio status">
        <article className="overview-primary"><div className="overview-icon"><FolderKanban size={21} /></div><span className="eyebrow">ACTIVE PORTFOLIO</span><strong>{loading ? "—" : projects.length}</strong><p>{projects.length === 1 ? "project in this workspace" : "projects in this workspace"}</p><Link href="#projects">Review projects <ArrowRight size={14} /></Link></article>
        <article className="stat-card"><div className="stat-icon green"><MapPinned size={18} /></div><div><small>Mapped zones</small><strong>{loading ? "—" : zoneCount}</strong><span>areas ready for evidence</span></div></article>
        <article className="stat-card"><div className="stat-icon amber"><Sparkles size={18} /></div><div><small>Zones mapped</small><strong>{loading ? "—" : mappedProjects}</strong><span>projects ready to request evidence</span></div></article>
        <article className="stat-card"><div className="stat-icon blue"><ShieldCheck size={18} /></div><div><small>Decision control</small><strong>Human</strong><span>manager approval required</span></div></article>
      </section>

      <section className="workspace-grid">
        <article className="card projects-card" id="projects">
          <div className="card-head"><div><span className="eyebrow">PROJECTS</span><h2>Decisions in progress</h2><p>Open a project to add zones and request heat evidence.</p></div><span className="count-pill">{loading ? "…" : projects.length}</span></div>
          {loading ? <div className="skeleton-list" role="status"><span /><span /><span /></div> : projects.length === 0 ? <div className="empty-state"><span className="empty-icon"><FolderKanban size={24} /></span><h3>No projects yet</h3><p>Start with the area or investment decision your team needs to evaluate.</p><button className="button primary" onClick={() => setShowCreate(true)}><Plus size={15} />Create your first project</button></div> : <div className="project-list">{projects.map((project) => <Link className="project-row" href={`/projects/${project.id}`} key={project.id}><span className="project-avatar"><FolderKanban size={18} /></span><span className="project-main"><strong>{project.name}</strong><small>{project.description ?? "No description added"}</small></span><span className="project-zones"><b>{project.zoneCount ?? "—"}</b><small>zones</small></span><span className={`readiness ${project.zoneCount ? "ready" : "needs-work"}`}>{project.zoneCount ? "Ready for evidence" : "Add a zone"}</span><ArrowUpRight className="project-arrow" size={17} /></Link>)}</div>}
        </article>

        <aside className="next-step-card"><span className="eyebrow">RECOMMENDED NEXT STEP</span><div className="next-step-number">01</div><h2>{projects.length ? "Strengthen the evidence" : "Create a project"}</h2><p>{projects.length ? "Open a project, confirm its mapped zones, and request provider-backed heat evidence before comparing interventions." : "Give the decision a clear name and purpose. You can map the affected area immediately after."}</p>{projects.length ? <Link className="button primary" href={`/projects/${projects[0].id}`}>Open latest project <ArrowRight size={15} /></Link> : <button className="button primary" onClick={() => setShowCreate(true)}>Start now <ArrowRight size={15} /></button>}<div className="next-step-foot"><ShieldCheck size={15} /><span>Every recommendation remains manager-controlled.</span></div></aside>
      </section>
    </AppShell>
  );
}
