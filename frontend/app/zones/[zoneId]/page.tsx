"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "../../../components/app-shell";
import { backendFetch } from "../../../components/data";

type Zone = { id: string; name: string; project_id: string; geometry: Record<string, unknown> };

export default function ZonePage() {
  const { zoneId } = useParams<{ zoneId: string }>();
  const [zones, setZones] = useState<Zone[]>([]);
  const [error, setError] = useState("");
  const [requested, setRequested] = useState(false);
  useEffect(() => {
    if (!zoneId || zoneId === "demo") return;
    backendFetch<Zone[]>(`/api/v1/projects/${zoneId}/zones`).then(setZones).catch((e) => setError(e.message));
  }, [zoneId]);
  const zone = zones.find((item) => item.id === zoneId) ?? { id: zoneId, name: zoneId === "demo" ? "Phoenix Central" : "Selected zone", project_id: zoneId, geometry: {} };
  async function requestAnalysis() {
    setRequested(true);
    if (zoneId === "demo") return;
    try { await backendFetch("/api/v1/heat-analyses", { method: "POST", body: JSON.stringify({ project_id: zone.project_id, zone_id: zone.id, parameters: { analytic_type: "exceedance", threshold: 35, granularity: 100 } }) }); } catch (e) { setError(e instanceof Error ? e.message : "Analysis request failed"); }
  }
  return <AppShell title="Zone intelligence"><div className="page-head"><div><div className="eyebrow">FORTYGUARD / ZONE INTELLIGENCE</div><h1>{zone.name}</h1><p>Inspect the heat signal, request an asynchronous analysis, and keep every decision tied to an auditable zone.</p></div><button className="button primary" onClick={requestAnalysis} disabled={requested}>{requested ? "Analysis queued ✓" : "Request heat analysis →"}</button></div>
    {error && <div className="error" style={{ marginBottom: 14 }}>{error}</div>}
    <section className="grid two-col"><article className="card map-card"><div className="map-grid"/><div className="map-glow"/><div className="map-label"><span className="badge heat"><span className="dot"/> heat signal</span><h2 style={{ marginTop: 14 }}>Exposure pattern</h2><p className="muted">35°C threshold · 100m grid · U.S. demo zone</p></div><div className="legend"><span className="muted">Relative temperature</span><div className="legend-bar"/><div className="muted" style={{ display: "flex", justifyContent: "space-between" }}><span>cool</span><span>hot</span></div></div></article><aside className="card"><div className="card-head"><div><div className="card-title">Evidence state</div><div className="card-subtitle">Provider activity and next action</div></div><span className={`badge ${requested ? "ok" : "heat"}`}>{requested ? "queued" : "ready"}</span></div><div className="grid" style={{ gap: 16 }}><div><div className="kpi-label">Provider</div><strong className="kpi-value" style={{ fontSize: "1.3rem" }}>FortyGuard</strong><div className="kpi-meta">Asynchronous activity polling</div></div><div><div className="kpi-label">Dataset freshness</div><strong className="kpi-value" style={{ fontSize: "1.3rem" }}>Awaiting analysis</strong><div className="kpi-meta">No measurements invented locally</div></div></div><div className="approval" style={{ marginTop: 22, display: "block" }}><h3>Evidence boundary</h3><p>Deterministic services calculate measurements. Agents can explain results but cannot fabricate heat values.</p></div></aside></section>
    <section className="card" style={{ marginTop: 14 }}><div className="card-head"><div><div className="card-title">Zone workflow</div><div className="card-subtitle">From live signal to governed decision</div></div><Link className="button ghost" href="/ask">Ask about this zone →</Link></div><div className="grid kpis" style={{ gridTemplateColumns: "repeat(3,1fr)", marginBottom: 0 }}><div><div className="kpi-label">Heat analysis</div><strong className="kpi-value" style={{ fontSize: "1.25rem" }}>{requested ? "Queued" : "Not started"}</strong></div><div><div className="kpi-label">Cited interventions</div><strong className="kpi-value" style={{ fontSize: "1.25rem" }}>Awaiting evidence</strong></div><div><div className="kpi-label">Verification</div><strong className="kpi-value" style={{ fontSize: "1.25rem" }}>Not measured</strong></div></div></section></AppShell>;
}
