"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "../../../components/app-shell";
import { backendFetch } from "../../../components/data";

type Report = { verification_id: string; status: string; report_url?: string | null; result?: Record<string, number | string | boolean> };

export default function VerifyPage() {
  const { reportId } = useParams<{ reportId: string }>();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { if (reportId !== "demo") backendFetch<Report>(`/api/v1/reports/${reportId}`).then(setReport).catch((e) => setError(e.message)); }, [reportId]);
  const result = report?.result ?? {};
  const value = (key: string, fallback: string) => result[key] === undefined ? fallback : String(result[key]);
  return <AppShell title="Verification report"><div className="page-head"><div><div className="eyebrow">OBSERVED TREATMENT EFFECT / REPORT</div><h1>Verification report</h1><p>Weather-adjusted matched-control evidence, presented with the restraint required for scientific claims.</p></div><span className="badge ok"><span className="dot"/> {report?.status ?? (reportId === "demo" ? "demo report" : "loading")}</span></div>
    {error && <div className="error" style={{ marginBottom: 14 }}>{error}</div>}
    <section className="grid kpis"><article className="card"><div className="kpi-label">Observed cooling</div><strong className="kpi-value">{value("cooling_effect", "—")}°C</strong><div className="kpi-meta">Treatment relative to matched control</div></article><article className="card"><div className="kpi-label">Expected cooling</div><strong className="kpi-value">{value("expected_cooling", "—")}°C</strong><div className="kpi-meta">Portfolio target</div></article><article className="card"><div className="kpi-label">Target achievement</div><strong className="kpi-value">{result.attainment_ratio === undefined ? "—" : `${(Number(result.attainment_ratio) * 100).toFixed(0)}%`}</strong><div className="kpi-meta">Observed / expected</div></article><article className="card"><div className="kpi-label">Confidence interval</div><strong className="kpi-value">—</strong><div className="kpi-meta">Not estimated for aggregate input</div></article></section>
    <section className="grid two-col"><article className="card"><div className="card-head"><div><div className="card-title">Matched-control calculation</div><div className="card-subtitle">Transparent difference-in-differences</div></div><span className="badge heat">observational</span></div><div className="chart"><div className="chart-control"/><div className="chart-line"/></div><div className="grid kpis" style={{ gridTemplateColumns: "repeat(2,1fr)", marginTop: 18, marginBottom: 0 }}><div><div className="kpi-label">Treated adjusted delta</div><strong>{value("treated_weather_adjusted_delta", "—")}°C</strong></div><div><div className="kpi-label">Control adjusted delta</div><strong>{value("control_weather_adjusted_delta", "—")}°C</strong></div></div></article><aside className="card"><div className="card-head"><div><div className="card-title">Evidence boundary</div><div className="card-subtitle">What this report can claim</div></div></div><p className="muted" style={{ lineHeight: 1.6, fontSize: ".82rem" }}>This is an observed treatment effect after weather adjustment. It does not claim that one intervention caused an exact temperature change without an experimental design.</p>{report?.report_url && <a className="button primary" href={report.report_url}>Download S3 report ↗</a>}{!report?.report_url && <div className="empty">Report artifact will appear after S3 materialization.</div>}<Link className="button ghost" style={{ display: "inline-block", marginTop: 10 }} href="/portfolio">Return to portfolio</Link></aside></section></AppShell>;
}
