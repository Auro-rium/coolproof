"use client";

import Link from "next/link";
import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "../../components/app-shell";
import { backendFetch, Project } from "../../components/data";
import { MetricCard } from "../../components/metric-card";
import { Timeline } from "../../components/timeline";

type ProjectRow = Project & { zoneCount: number | null };

function formatUpdated(project: Project) {
  // The projects API intentionally exposes no timestamp yet. Keep the UI explicit
  // instead of inventing one client-side.
  return project.description ? "Description available" : "No activity metadata";
}

export default function PortfolioPage() {
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [creating, setCreating] = useState(false);

  const loadProjects = useCallback(async (isRefresh = false) => {
    setError("");
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const result = await backendFetch<Project[]>("/api/v1/projects");
      const rows = await Promise.all(result.map(async (project): Promise<ProjectRow> => {
        try {
          const zones = await backendFetch<Array<{ id: string }>>(`/api/v1/projects/${project.id}/zones`);
          return { ...project, zoneCount: zones.length };
        } catch {
          // Keep a project visible when a single zone request is unavailable.
          return { ...project, zoneCount: null };
        }
      }));
      setProjects(rows);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "AWS API request failed");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectName.trim()) return;
    setCreating(true); setError("");
    try {
      await backendFetch("/api/v1/projects", { method: "POST", body: JSON.stringify({ name: projectName.trim(), description: projectDescription.trim() || null }) });
      setProjectName(""); setProjectDescription(""); await loadProjects(true);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Project could not be created"); }
    finally { setCreating(false); }
  }

  useEffect(() => { void loadProjects(); }, [loadProjects]);

  const zoneCount = useMemo(
    () => projects.reduce((total, project) => total + (project.zoneCount ?? 0), 0),
    [projects],
  );

  return (
    <AppShell>
      <div className="page-head portfolio-head">
        <div>
          <div className="eyebrow">CITY COOLING / OPERATIONS</div>
          <h1>Portfolio</h1>
          <p>Make the next cooling investment decision from evidence you can trace, constraints you can inspect, and outcomes you can verify.</p>
        </div>
        <div className="page-actions">
          <button className="button ghost" type="button" onClick={() => void loadProjects(true)} disabled={loading || refreshing}>
            {refreshing ? "Refreshing…" : "Refresh data"}
          </button>
          <Link href="/optimize" className="button primary">Start a plan <span aria-hidden="true">→</span></Link>
        </div>
      </div>

      {error && <div className="error portfolio-error" role="alert"><strong>Could not load portfolio data.</strong><span>{error}</span><small>Request a retry or check your Cognito session and organization membership.</small></div>}

      <section className="portfolio-signal" aria-labelledby="signal-title">
        <div className="signal-copy">
          <div className="eyebrow">DECISION SIGNAL</div>
          <h2 id="signal-title">{loading ? "Loading your cooling portfolio" : projects.length ? `${projects.length} project${projects.length === 1 ? "" : "s"} in your cooling portfolio` : "No projects in your cooling portfolio"}</h2>
          <p>{loading ? "Reading tenant-scoped project data from AWS PostgreSQL." : projects.length ? "Project geometry is connected to the tenant-scoped AWS API. Open a zone to request FortyGuard evidence, then send a plan through governed approval." : "Create your first project, then map a zone before requesting heat evidence."}</p>
        </div>
        <div className="signal-detail"><span className="signal-detail-label">NEXT ACTION</span><strong>{projects.length ? "Map evidence" : "Create a project"}</strong><span className="muted">The optimizer requires a validated zone and intervention catalogue.</span></div>
      </section>

      <section className="grid kpis" aria-label="Portfolio indicators">
        <MetricCard label="Projects in scope" value={loading ? "—" : String(projects.length)} meta="AWS PostgreSQL · tenant scoped" />
        <MetricCard label="Zones mapped" value={loading ? "—" : String(zoneCount)} meta="Project geometry" tone="blue" />
        <MetricCard label="Evidence connection" value="Live" meta="FortyGuard analysis API" tone="heat" />
        <MetricCard label="Decision stage" value="Governed" meta="Manager approval required" tone="blue" />
      </section>

      <section className="grid portfolio-grid">
        <article className="card projects-card">
          <div className="card-head">
            <div><div className="card-title">Projects</div><div className="card-subtitle">Tenant-scoped workspaces available to this organization</div></div>
            <Link href="#projects" className="button ghost">View projects <span aria-hidden="true">↗</span></Link>
          </div>
          {loading ? <div className="empty" role="status">Loading projects from AWS…</div> : projects.length === 0 ? <div className="empty portfolio-empty"><strong>Create the first project in this organization.</strong><span>This writes a tenant-scoped project to the AWS API. Then map a zone and request live FortyGuard evidence.</span><form className="inline-form" onSubmit={createProject}><label className="sr-only" htmlFor="project-name">Project name</label><input id="project-name" value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="e.g. Phoenix cooling pilot" required /><label className="sr-only" htmlFor="project-description">Project description</label><input id="project-description" value={projectDescription} onChange={(event) => setProjectDescription(event.target.value)} placeholder="Optional description" /><button className="button primary" disabled={creating}>{creating ? "Creating project…" : "Create project"}</button></form></div> : <div className="table-wrap"><table id="projects" className="table project-table"><caption className="sr-only">CoolProof projects and evidence readiness</caption><thead><tr><th>Project</th><th>Zones</th><th>Evidence readiness</th><th>Workflow</th><th>Metadata</th></tr></thead><tbody>{projects.map(project => <tr key={project.id}><td><Link href={`/projects/${project.id}`}><strong>{project.name}</strong></Link><div className="muted project-description">{project.description ?? "No description provided"}</div></td><td>{project.zoneCount === null ? "—" : project.zoneCount}</td><td>{project.zoneCount === 0 ? <span className="badge warn"><span className="dot" /> Map a zone</span> : project.zoneCount === null ? <span className="badge fail"><span className="dot" /> Unavailable</span> : <span className="badge heat"><span className="dot" /> Ready for heat run</span>}</td><td><span className="badge">Not started</span></td><td className="muted">{formatUpdated(project)}</td></tr>)}</tbody></table></div>}
        </article>

        <aside className="card workflow-card">
          <div className="card-head"><div><div className="card-title">Decision workflow</div><div className="card-subtitle">The governed path for every recommendation</div></div><span className="badge ok"><span className="dot" /> AWS live</span></div>
          <Timeline active={0} />
          <div className="workflow-note"><span className="eyebrow">CONTROL BOUNDARY</span><p>Agents explain and orchestrate. FortyGuard, retrieval, and OR-Tools remain the calculation sources of truth.</p><Link href="/ask" className="button ghost">Open bounded commands <span aria-hidden="true">→</span></Link></div>
        </aside>
      </section>
    </AppShell>
  );
}
