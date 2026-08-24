"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  CircleAlert,
  Clock3,
  CloudSun,
  FileJson2,
  Flame,
  GitCompareArrows,
  MapPinned,
  RefreshCw,
  ShieldCheck,
  ThermometerSun,
} from "lucide-react";
import { AppShell } from "../../../components/app-shell";
import { backendFetch } from "../../../components/data";

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

const analysisStorageKey = (zoneId: string) => `coolproof:heat-analysis:${zoneId}`;

function badgeTone(status: AnalysisStatus) {
  if (status === "succeeded") return "ok";
  if (status === "failed") return "fail";
  return "warn";
}

function statusIcon(status: AnalysisStatus) {
  if (status === "succeeded") return <CheckCircle2 size={14} />;
  if (status === "failed") return <CircleAlert size={14} />;
  return <Clock3 size={14} />;
}

function resultEntries(result: Record<string, unknown> | null) {
  if (!result) return [];
  return Object.entries(result).filter(([, value]) => ["string", "number", "boolean"].includes(typeof value)).slice(0, 8);
}

function formatFieldName(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatResultValue(value: unknown) {
  if (typeof value === "number") return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function countCoordinatePairs(value: unknown): number {
  if (!Array.isArray(value)) return 0;
  if (value.length >= 2 && typeof value[0] === "number" && typeof value[1] === "number") return 1;
  return value.reduce<number>((total, item) => total + countCoordinatePairs(item), 0);
}

export default function ZonePage({
  params,
  searchParams,
}: {
  params: Promise<{ zoneId: string }>;
  searchParams: Promise<{ projectId?: string; analysisId?: string }>;
}) {
  const { zoneId } = use(params);
  const query = use(searchParams);
  const projectId = query.projectId;
  const [zone, setZone] = useState<Zone | null>(null);
  const [analysis, setAnalysis] = useState<HeatAnalysis | null>(null);
  const [analysisId, setAnalysisId] = useState<string | null>(query.analysisId ?? null);
  const [loading, setLoading] = useState(Boolean(projectId));
  const [requesting, setRequesting] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [pollError, setPollError] = useState("");
  const [pollPaused, setPollPaused] = useState(false);

  const loadZone = useCallback(async () => {
    if (!projectId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError("");
    try {
      const zones = await backendFetch<Zone[]>(`/api/v1/projects/${encodeURIComponent(projectId)}/zones`);
      const selected = zones.find((item) => item.id === zoneId) ?? null;
      setZone(selected);
      if (!selected) setLoadError("This zone was not found in the selected project or organization.");
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "Unable to load this project zone.");
    } finally {
      setLoading(false);
    }
  }, [projectId, zoneId]);

  useEffect(() => { void loadZone(); }, [loadZone]);

  useEffect(() => {
    if (analysisId || typeof window === "undefined") return;
    const retained = window.localStorage.getItem(analysisStorageKey(zoneId));
    if (retained) setAnalysisId(retained);
  }, [analysisId, zoneId]);

  const readAnalysis = useCallback(async (id: string) => {
    setPollError("");
    try {
      const current = await backendFetch<HeatAnalysis>(`/api/v1/heat-analyses/${encodeURIComponent(id)}`);
      if (current.zone_id !== zoneId || (projectId && current.project_id !== projectId)) {
        throw new Error("The retained analysis does not belong to this project zone.");
      }
      setAnalysis(current);
      setPollPaused(false);
      window.localStorage.setItem(analysisStorageKey(zoneId), current.id);
    } catch (cause) {
      setPollError(cause instanceof Error ? cause.message : "Unable to read analysis status.");
      setPollPaused(true);
    }
  }, [projectId, zoneId]);

  useEffect(() => {
    if (!zone || !analysisId || analysis) return;
    void readAnalysis(analysisId);
  }, [analysis, analysisId, readAnalysis, zone]);

  useEffect(() => {
    if (!analysis || !["queued", "running"].includes(analysis.status) || pollPaused) return;
    const timer = window.setTimeout(() => void readAnalysis(analysis.id), 2500);
    return () => window.clearTimeout(timer);
  }, [analysis, pollPaused, readAnalysis]);

  async function requestAnalysis() {
    if (!zone || !projectId) return;
    setRequesting(true);
    setActionError("");
    setPollError("");
    setPollPaused(false);
    try {
      const current = await backendFetch<HeatAnalysis>("/api/v1/heat-analyses", {
        method: "POST",
        body: JSON.stringify({
          project_id: projectId,
          zone_id: zone.id,
          parameters: { analytic_type: "exceedance", threshold: 35, granularity: 100 },
        }),
      });
      setAnalysis(current);
      setAnalysisId(current.id);
      window.localStorage.setItem(analysisStorageKey(zone.id), current.id);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Analysis request failed.");
    } finally {
      setRequesting(false);
    }
  }

  const scalarResults = useMemo(() => resultEntries(analysis?.result ?? null), [analysis?.result]);
  const coordinatePairs = useMemo(() => countCoordinatePairs(zone?.geometry.coordinates), [zone?.geometry.coordinates]);
  const geometryType = typeof zone?.geometry.type === "string" ? zone.geometry.type : "Unspecified";
  const backHref = projectId ? `/projects/${encodeURIComponent(projectId)}` : "/portfolio";

  return (
    <AppShell title="Zone intelligence">
      <header className="page-head">
        <div>
          <span className="eyebrow">FORTYGUARD / ZONE INTELLIGENCE</span>
          <h1>{loading ? "Loading zone…" : zone?.name ?? "Zone unavailable"}</h1>
          <p>{zone ? "Follow the real provider activity from request through terminal evidence." : "A zone must be opened from its tenant-scoped project context."}</p>
        </div>
        <div className="top-actions">
          <Link className="button ghost" href={backHref}><ArrowLeft size={15} /> Back to project</Link>
          {zone ? <button className="button primary" type="button" onClick={() => void requestAnalysis()} disabled={requesting || analysis?.status === "queued" || analysis?.status === "running"}>
            {requesting ? "Requesting…" : analysis?.status === "failed" ? "Retry analysis" : analysis?.status === "succeeded" ? "Request current evidence" : "Request heat analysis"}
          </button> : null}
        </div>
      </header>

      {!projectId ? <section className="card plans-empty"><MapPinned size={26} /><h2>Project context required</h2><p>This backend does not expose a direct zone-by-ID lookup. Open the zone from its real project so tenant ownership can be verified.</p><Link className="button primary" href="/portfolio">Choose a project</Link></section> : null}
      {loadError ? <div className="error" role="alert"><strong>Zone unavailable.</strong> {loadError}<div className="top-actions" style={{ marginTop: 10 }}><button className="button" onClick={() => void loadZone()}><RefreshCw size={14} /> Retry</button><Link className="button ghost" href={backHref}>Return to project</Link></div></div> : null}
      {actionError ? <div className="error" role="alert" style={{ marginTop: 12 }}>{actionError}</div> : null}

      {zone ? <>
        <section className="grid two-col">
          <article className="card">
            <div className="card-head"><div><span className="eyebrow">MAPPED AREA</span><h2>{zone.name}</h2><p>The provider receives this persisted geometry with the analysis parameters.</p></div><FileJson2 size={21} aria-hidden="true" /></div>
            <div className="constraint-list">
              <div className="constraint"><span>Geometry type</span><strong>{geometryType}</strong></div>
              <div className="constraint"><span>Coordinate pairs</span><strong>{coordinatePairs}</strong></div>
              <div className="constraint"><span>Threshold</span><strong>35°C exceedance</strong></div>
              <div className="constraint"><span>Requested granularity</span><strong>100m</strong></div>
            </div>
            <div className="notice" style={{ marginTop: 18 }}>Geometry comes from the persisted project zone. This screen does not substitute a demo boundary or synthetic heat layer.</div>
          </article>

          <aside className="card">
            <div className="card-head">
              <div><span className="eyebrow">PROVIDER ACTIVITY</span><h2>Evidence state</h2><p>Only a succeeded activity can supply result data.</p></div>
              <span className={`badge ${analysis ? badgeTone(analysis.status) : ""}`}>{analysis ? statusIcon(analysis.status) : <Flame size={14} />}{analysis ? (analysis.stale ? "stale result" : analysis.status) : "not started"}</span>
            </div>
            <div className="constraint-list">
              <div className="constraint"><span>Provider</span><strong>FortyGuard</strong></div>
              <div className="constraint"><span>Analysis ID</span><strong>{analysis?.id ? analysis.id.slice(0, 12) : "Not created"}</strong></div>
              <div className="constraint"><span>Response source</span><strong>{analysis?.cached ? "Backend cache" : analysis ? "Provider activity" : "Awaiting request"}</strong></div>
              <div className="constraint"><span>Freshness</span><strong>{analysis?.stale ? "Stale fallback" : analysis?.status === "succeeded" ? "Within cache window" : "Not established"}</strong></div>
            </div>
            {pollError ? <div className="error" role="alert" style={{ marginTop: 14 }}>Status refresh paused: {pollError}<button className="button" onClick={() => analysisId && void readAnalysis(analysisId)}><RefreshCw size={14} /> Retry status</button></div> : null}
            {analysis?.stale_warning ? <div className="notice" style={{ marginTop: 14 }}>{analysis.stale_warning}</div> : null}
            {analysis?.error ? <div className="error" role="alert" style={{ marginTop: 14 }}><strong>{analysis.error.code}</strong> {analysis.error.message}</div> : null}
          </aside>
        </section>

        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head"><div><span className="eyebrow">PROVIDER RESULT</span><h2>Heat evidence</h2><p>Values below are rendered only when present in the persisted provider result.</p></div>{analysis?.status === "succeeded" ? <span className="badge ok"><ShieldCheck size={13} /> Result received</span> : null}</div>
          {!analysis ? <div className="empty">No analysis has been requested for this zone.</div> : ["queued", "running"].includes(analysis.status) ? <div className="empty"><Clock3 size={20} /><strong>Analysis {analysis.status}</strong><br />CoolProof is polling the durable activity; no measurements are shown yet.</div> : analysis.status === "failed" ? <div className="empty"><CircleAlert size={20} /><strong>Analysis failed</strong><br />No heat evidence was produced. Review the provider error above before retrying.</div> : scalarResults.length > 0 ? <div className="grid kpis" style={{ marginBottom: 0 }}>{scalarResults.map(([key, value]) => <div key={key}><div className="kpi-label">{formatFieldName(key)}</div><strong className="kpi-value" style={{ fontSize: "1.2rem" }}>{formatResultValue(value)}</strong><div className="kpi-meta">FortyGuard result field</div></div>)}</div> : <div className="empty">The succeeded provider result contains no scalar summary fields to present. The structured result remains available from the tenant-scoped analysis API.</div>}
        </section>

        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head"><div><span className="eyebrow">DECISION HANDOFF</span><h2>What happens next</h2><p>Heat evidence is one input to a governed cooling decision.</p></div></div>
          <div className="grid kpis" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))", marginBottom: 0 }}>
            <div><ThermometerSun size={18} /><div className="kpi-label">Heat analysis</div><strong>{analysis?.status ?? "Not started"}</strong></div>
            <div><GitCompareArrows size={18} /><div className="kpi-label">Intervention evidence</div><strong>{analysis?.status === "succeeded" ? "Ready to retrieve" : "Awaiting heat evidence"}</strong></div>
            <div><CloudSun size={18} /><div className="kpi-label">Verification</div><strong>Requires observed outcomes</strong></div>
          </div>
        </section>
      </> : null}
    </AppShell>
  );
}
