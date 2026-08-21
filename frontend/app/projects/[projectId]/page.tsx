"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { AppShell } from "../../../components/app-shell";
import { backendFetch, Project } from "../../../components/data";

type Zone = { id: string; name: string; project_id: string; geometry: Record<string, unknown> };

export default function ProjectPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const [project, setProject] = useState<Project | null>(null);
  const [zones, setZones] = useState<Zone[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [queued, setQueued] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([
      backendFetch<Project[]>("/api/v1/projects").then((items) => setProject(items.find((item) => item.id === projectId) ?? null)),
      backendFetch<Zone[]>(`/api/v1/projects/${projectId}/zones`).then(setZones),
    ]).catch((cause) => setError(cause instanceof Error ? cause.message : "Unable to load project data")).finally(() => setLoading(false));
  }, [projectId]);

  async function requestHeat(zone: Zone) {
    setQueued(zone.id); setError("");
    try {
      await backendFetch("/api/v1/heat-analyses", { method: "POST", body: JSON.stringify({ project_id: projectId, zone_id: zone.id, parameters: { analytic_type: "exceedance", threshold: 35, granularity: 100 } }) });
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Heat analysis could not be queued"); }
  }

  return <AppShell title={project?.name ?? "Project"}><div className="page-head"><div><div className="eyebrow">PROJECT / LIVE EVIDENCE</div><h1>{loading ? "Loading project…" : project?.name ?? "Project not found"}</h1><p>{project?.description ?? "Inspect mapped zones and request provider-backed heat evidence."}</p></div><Link href="/portfolio" className="button ghost">Back to portfolio</Link></div>{error && <div className="error" role="alert">{error}</div>}{!loading && !project && !error && <div className="empty">This project is not available in your organization.</div>}{project && <section className="card"><div className="card-head"><div><div className="card-title">Mapped zones</div><div className="card-subtitle">Every request is scoped to this project and organization.</div></div><span className="badge ok">AWS connected</span></div>{zones.length === 0 ? <div className="empty">No zones are mapped yet. Create one through the project API before requesting heat evidence.</div> : <div className="constraint-list">{zones.map((zone) => <div className="constraint" key={zone.id}><span><strong>{zone.name}</strong><br/><small>FortyGuard · 35°C exceedance · 100m grid</small></span><button className="button primary" onClick={() => void requestHeat(zone)} disabled={queued === zone.id}>{queued === zone.id ? "Queued ✓" : "Request heat"}</button></div>)}</div>}</section>}</AppShell>;
}
