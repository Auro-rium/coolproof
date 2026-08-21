"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import type { FormEvent } from "react";
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
  const [zoneName, setZoneName] = useState("");
  const [geometry, setGeometry] = useState('{"type":"Polygon","coordinates":[]}');
  const [creatingZone, setCreatingZone] = useState(false);

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

  async function createZone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreatingZone(true); setError("");
    try {
      const parsed = JSON.parse(geometry) as Record<string, unknown>;
      await backendFetch(`/api/v1/projects/${projectId}/zones`, { method: "POST", body: JSON.stringify({ name: zoneName.trim(), geometry: parsed }) });
      setZoneName(""); setGeometry('{"type":"Polygon","coordinates":[]}');
      setZones(await backendFetch<Zone[]>(`/api/v1/projects/${projectId}/zones`));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Zone could not be created. Check the GeoJSON."); }
    finally { setCreatingZone(false); }
  }

  return <AppShell title={project?.name ?? "Project"}><div className="page-head"><div><div className="eyebrow">PROJECT / LIVE EVIDENCE</div><h1>{loading ? "Loading project…" : project?.name ?? "Project not found"}</h1><p>{project?.description ?? "Inspect mapped zones and request provider-backed heat evidence."}</p></div><Link href="/portfolio" className="button ghost">Back to portfolio</Link></div>{error && <div className="error" role="alert">{error}</div>}{!loading && !project && !error && <div className="empty">This project is not available in your organization.</div>}{project && <><section className="card"><div className="card-head"><div><div className="card-title">Mapped zones</div><div className="card-subtitle">Every request is scoped to this project and organization.</div></div><span className="badge ok">AWS connected</span></div>{zones.length === 0 ? <div className="empty">No zones are mapped yet. Create the first zone below, then request live heat evidence.</div> : <div className="constraint-list">{zones.map((zone) => <div className="constraint" key={zone.id}><span><strong>{zone.name}</strong><br/><small>FortyGuard · 35°C exceedance · 100m grid</small></span><button className="button primary" onClick={() => void requestHeat(zone)} disabled={queued === zone.id}>{queued === zone.id ? "Queued ✓" : "Request heat"}</button></div>)}</div>}</section><section className="card" style={{ marginTop: 14 }}><div className="card-head"><div><div className="card-title">Map a zone</div><div className="card-subtitle">Paste a GeoJSON geometry for the provider request.</div></div></div><form className="form-grid" onSubmit={createZone}><div className="field"><label htmlFor="zone-name">Zone name</label><input id="zone-name" value={zoneName} onChange={(event) => setZoneName(event.target.value)} placeholder="Phoenix Central" required /></div><div className="field"><label htmlFor="zone-geometry">GeoJSON geometry</label><input id="zone-geometry" value={geometry} onChange={(event) => setGeometry(event.target.value)} required /></div><button className="button primary" disabled={creatingZone}>{creatingZone ? "Mapping zone…" : "Create zone"}</button></form></section></>}</AppShell>;
}
