"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Clock3,
  ExternalLink,
  Flame,
  MapPinned,
  Plus,
  RefreshCw,
  ThermometerSun,
} from "lucide-react";
import { AppShell } from "../../../components/app-shell";
import { backendFetch, Project } from "../../../components/data";

type Zone = { id: string; name: string; project_id: string; geometry: Record<string, unknown> };
type AnalysisStatus = "queued" | "running" | "succeeded" | "failed";
type HeatAnalysis = {
  id: string;
  project_id: string;
  zone_id: string;
  status: AnalysisStatus;
  result: Record<string, unknown> | null;
  cached: boolean;
  stale: boolean;
  stale_warning: string | null;
  error: { code: string; message: string } | null;
};
type AnalysisView = HeatAnalysis & { pollError?: string; pollPaused?: boolean };

const analysisStorageKey = (zoneId: string) => `coolproof:heat-analysis:${zoneId}`;

function badgeTone(status: AnalysisStatus) {
  if (status === "succeeded") return "ok";
  if (status === "failed") return "fail";
  return "warn";
}

function resultEntries(result: Record<string, unknown> | null) {
  if (!result) return [];
  return Object.entries(result).filter(([, value]) => ["string", "number", "boolean"].includes(typeof value)).slice(0, 6);
}

function formatFieldName(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatResultValue(value: unknown) {
  if (typeof value === "number") return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

export default function ProjectPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const [project, setProject] = useState<Project | null>(null);
  const [zones, setZones] = useState<Zone[]>([]);
  const [analyses, setAnalyses] = useState<Record<string, AnalysisView>>({});
  const [analysisLookupErrors, setAnalysisLookupErrors] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [loading, setLoading] = useState(true);
  const [requestingZone, setRequestingZone] = useState<string | null>(null);
  const [zoneName, setZoneName] = useState("");
  const [geometry, setGeometry] = useState('{"type":"Polygon","coordinates":[]}');
  const [creatingZone, setCreatingZone] = useState(false);

  const loadProject = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [projects, projectZones] = await Promise.all([
        backendFetch<Project[]>("/api/v1/projects"),
        backendFetch<Zone[]>(`/api/v1/projects/${encodeURIComponent(projectId)}/zones`),
      ]);
      setProject(projects.find((item) => item.id === projectId) ?? null);
      setZones(projectZones);
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "Unable to load project data.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { void loadProject(); }, [loadProject]);

  const readAnalysis = useCallback(async (zoneId: string, analysisId: string) => {
    try {
      const current = await backendFetch<HeatAnalysis>(`/api/v1/heat-analyses/${encodeURIComponent(analysisId)}`);
      setAnalyses((previous) => ({ ...previous, [zoneId]: { ...current, pollPaused: false } }));
      setAnalysisLookupErrors((previous) => {
        if (!previous[zoneId]) return previous;
        const next = { ...previous };
        delete next[zoneId];
        return next;
      });
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Unable to read analysis status.";
      setAnalyses((previous) => previous[zoneId]
        ? { ...previous, [zoneId]: { ...previous[zoneId], pollError: message, pollPaused: true } }
        : previous);
      setAnalysisLookupErrors((previous) => ({ ...previous, [zoneId]: message }));
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || zones.length === 0) return;
    for (const zone of zones) {
      if (analyses[zone.id]) continue;
      const analysisId = window.localStorage.getItem(analysisStorageKey(zone.id));
      if (analysisId) void readAnalysis(zone.id, analysisId);
    }
  }, [analyses, readAnalysis, zones]);

  useEffect(() => {
    const pending = Object.entries(analyses).filter(([, analysis]) =>
      ["queued", "running"].includes(analysis.status) && !analysis.pollPaused,
    );
    if (pending.length === 0) return;
    const timer = window.setTimeout(() => {
      for (const [zoneId, analysis] of pending) void readAnalysis(zoneId, analysis.id);
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [analyses, readAnalysis]);

  async function requestHeat(zone: Zone) {
    setRequestingZone(zone.id);
    setActionError("");
    setAnalysisLookupErrors((previous) => {
      const next = { ...previous };
      delete next[zone.id];
      return next;
    });
    try {
      const analysis = await backendFetch<HeatAnalysis>("/api/v1/heat-analyses", {
        method: "POST",
        body: JSON.stringify({
          project_id: projectId,
          zone_id: zone.id,
          parameters: { analytic_type: "exceedance", threshold: 35, granularity: 100 },
        }),
      });
      setAnalyses((previous) => ({ ...previous, [zone.id]: { ...analysis, pollPaused: false } }));
      window.localStorage.setItem(analysisStorageKey(zone.id), analysis.id);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Heat analysis could not be queued.");
    } finally {
      setRequestingZone(null);
    }
  }

  async function createZone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreatingZone(true);
    setActionError("");
    try {
      const parsed = JSON.parse(geometry) as Record<string, unknown>;
      if (!parsed || typeof parsed !== "object" || typeof parsed.type !== "string" || !Array.isArray(parsed.coordinates) || parsed.coordinates.length === 0) {
        throw new Error("Enter a GeoJSON geometry with a type and non-empty coordinates.");
      }
      await backendFetch(`/api/v1/projects/${encodeURIComponent(projectId)}/zones`, {
        method: "POST",
        body: JSON.stringify({ name: zoneName.trim(), geometry: parsed }),
      });
      setZoneName("");
      setGeometry('{"type":"Polygon","coordinates":[]}');
      setZones(await backendFetch<Zone[]>(`/api/v1/projects/${encodeURIComponent(projectId)}/zones`));
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Zone could not be created. Check the GeoJSON.");
    } finally {
      setCreatingZone(false);
    }
  }

  const completedCount = useMemo(() => Object.values(analyses).filter((analysis) => analysis.status === "succeeded").length, [analyses]);

  return (
    <AppShell title={project?.name ?? "Project"}>
      <header className="page-head">
        <div>
          <span className="eyebrow">PROJECT / LIVE EVIDENCE</span>
          <h1>{loading ? "Loading project…" : project?.name ?? "Project not found"}</h1>
          <p>{project?.description ?? "Map a real project area, request provider-backed heat evidence, and follow the durable analysis to completion."}</p>
        </div>
        <Link href="/portfolio" className="button ghost">Back to workspace</Link>
      </header>

      {loadError ? <div className="error" role="alert"><strong>Project unavailable.</strong> {loadError}<button className="button" onClick={() => void loadProject()}><RefreshCw size={15} /> Retry</button></div> : null}
      {actionError ? <div className="error" role="alert" style={{ marginTop: 12 }}>{actionError}</div> : null}
      {!loading && !project && !loadError ? <div className="empty">This project is not available in your organization.</div> : null}

      {project ? <>
        <section className="grid kpis" aria-label="Project evidence status">
          <article className="card"><div className="kpi-label">Mapped zones</div><strong className="kpi-value">{zones.length}</strong><div className="kpi-meta">tenant-scoped project areas</div></article>
          <article className="card"><div className="kpi-label">Completed analyses</div><strong className="kpi-value">{completedCount}</strong><div className="kpi-meta">provider results received</div></article>
          <article className="card"><div className="kpi-label">Analysis method</div><strong className="kpi-value" style={{ fontSize: "1.15rem" }}>35°C exceedance</strong><div className="kpi-meta">100m request granularity</div></article>
          <article className="card"><div className="kpi-label">Evidence source</div><strong className="kpi-value" style={{ fontSize: "1.15rem" }}>FortyGuard</strong><div className="kpi-meta">asynchronous provider activity</div></article>
        </section>

        <section className="card projects-card">
          <div className="card-head">
            <div><span className="eyebrow">MAPPED ZONES</span><h2>Heat evidence by area</h2><p>A request is not evidence until the provider analysis succeeds.</p></div>
            <span className="count-pill">{zones.length}</span>
          </div>
          {zones.length === 0 ? <div className="empty-state"><MapPinned size={25} /><h3>No zones mapped</h3><p>Add the exact GeoJSON area you want the provider to analyze.</p></div> : <div className="project-list">
            {zones.map((zone) => {
              const analysis = analyses[zone.id];
              const lookupError = analysisLookupErrors[zone.id];
              const isRequesting = requestingZone === zone.id;
              const result = resultEntries(analysis?.result ?? null);
              const zoneHref = `/zones/${encodeURIComponent(zone.id)}?projectId=${encodeURIComponent(projectId)}${analysis ? `&analysisId=${encodeURIComponent(analysis.id)}` : ""}`;
              return <div className="project-row" key={zone.id} style={{ gridTemplateColumns: "40px minmax(180px,1fr) auto auto" }}>
                <span className="project-avatar"><ThermometerSun size={18} /></span>
                <span className="project-main">
                  <strong>{zone.name}</strong>
                  <small>{analysis ? `Analysis ${analysis.id.slice(0, 8)} · ${analysis.status}` : "No heat analysis requested"}</small>
                  {analysis?.stale_warning ? <small style={{ color: "var(--amber-dark)" }}>{analysis.stale_warning}</small> : null}
                  {analysis?.error ? <small style={{ color: "var(--danger)" }}>{analysis.error.message}</small> : null}
                  {analysis?.pollError || lookupError ? <small style={{ color: "var(--danger)" }}>Status refresh failed: {analysis?.pollError ?? lookupError}</small> : null}
                  {analysis?.status === "succeeded" && result.length > 0 ? <small>{result.map(([key, value]) => `${formatFieldName(key)}: ${formatResultValue(value)}`).join(" · ")}</small> : null}
                </span>
                <span className={`badge ${analysis ? badgeTone(analysis.status) : ""}`}>
                  {analysis?.status === "succeeded" ? <CheckCircle2 size={13} /> : analysis?.status === "failed" ? <CircleAlert size={13} /> : analysis ? <Clock3 size={13} /> : <Flame size={13} />}
                  {analysis ? (analysis.stale ? "stale result" : analysis.status) : "not started"}
                </span>
                <span className="top-actions">
                  {analysis?.pollPaused ? <button className="button" type="button" onClick={() => void readAnalysis(zone.id, analysis.id)}><RefreshCw size={14} /> Retry status</button> : null}
                  {!analysis || ["succeeded", "failed"].includes(analysis.status) ? <button className="button primary" type="button" onClick={() => void requestHeat(zone)} disabled={isRequesting}>{isRequesting ? "Requesting…" : analysis ? "Request again" : "Request heat"}</button> : null}
                  <Link className="button ghost" href={zoneHref}>Open zone <ExternalLink size={14} /></Link>
                </span>
              </div>;
            })}
          </div>}
        </section>

        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head"><div><span className="eyebrow">MAP AN AREA</span><h2>Add a project zone</h2><p>Paste the actual GeoJSON geometry that should be sent to the heat provider.</p></div><Plus size={20} aria-hidden="true" /></div>
          <form className="form-grid" onSubmit={createZone}>
            <div className="field"><label htmlFor="zone-name">Zone name</label><input id="zone-name" value={zoneName} onChange={(event) => setZoneName(event.target.value)} placeholder="e.g. Central school corridor" required /></div>
            <div className="field"><label htmlFor="zone-geometry">GeoJSON geometry</label><input id="zone-geometry" value={geometry} onChange={(event) => setGeometry(event.target.value)} aria-describedby="zone-geometry-help" required /><small id="zone-geometry-help" className="muted">Coordinates must be non-empty; CoolProof will not substitute a demo boundary.</small></div>
            <button className="button primary" disabled={creatingZone}>{creatingZone ? "Mapping zone…" : <>Create zone <ArrowRight size={15} /></>}</button>
          </form>
        </section>
      </> : null}
    </AppShell>
  );
}
