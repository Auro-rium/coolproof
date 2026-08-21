"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "../../../components/app-shell";
import { backendFetch } from "../../../components/data";

type JsonMap = Record<string, unknown>;
type AgentRun = { run_id: string; thread_id: string; status: string; current_agent: string | null; revision: number; state: JsonMap; error_code?: string | null };
type RunEvent = { sequence: number; event: string; node?: string | null; summary?: string | null };
const stages = [
  { key: "heat_intelligence", label: "Heat intelligence", description: "FortyGuard evidence and exposure" },
  { key: "intervention_analyst", label: "Intervention evidence", description: "Cited, tenant-isolated sources" },
  { key: "portfolio", label: "Portfolio", description: "OR-Tools allocation and constraints" },
  { key: "verification", label: "Verification", description: "Expected versus observed outcome" },
];

function asMap(value: unknown): JsonMap { return value && typeof value === "object" && !Array.isArray(value) ? value as JsonMap : {}; }
function text(value: unknown, fallback = "—") { return typeof value === "string" || typeof value === "number" ? String(value) : fallback; }
function money(value: unknown) { const amount = typeof value === "number" ? value : Number(value); return Number.isFinite(amount) ? new Intl.NumberFormat("en-US", { style: "currency", maximumFractionDigits: 0, currency: "USD" }).format(amount) : "—"; }
function stageStatus(run: AgentRun | null, key: string) {
  if (!run) return "queued";
  const currentIndex = stages.findIndex((stage) => stage.key === run.current_agent);
  const index = stages.findIndex((stage) => stage.key === key);
  if (run.status === "failed" && index === currentIndex) return "failed";
  if (run.status === "running" && index === currentIndex) return "running";
  if (currentIndex >= 0 && index < currentIndex) return "completed";
  if (["waiting_approval", "approved", "completed"].includes(run.status)) return "completed";
  return "queued";
}
function statusBadge(status: string) { return status === "completed" ? "ok" : status === "running" || status === "waiting_approval" ? "warn" : status === "failed" ? "fail" : ""; }

export default function PlanPage() {
  const params = useParams<{ runId: string }>();
  const runId = params?.runId;
  const [run, setRun] = useState<AgentRun | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionError, setDecisionError] = useState("");
  const [comment, setComment] = useState("");
  const [showAudit, setShowAudit] = useState(false);

  const loadRun = useCallback(async () => {
    if (!runId) return;
    setLoading(true); setError("");
    try { setRun(await backendFetch<AgentRun>(`/api/v1/agent-runs/${encodeURIComponent(runId)}`)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to load this plan"); }
    finally { setLoading(false); }
  }, [runId]);
  useEffect(() => { void loadRun(); }, [loadRun]);
  useEffect(() => {
    if (!runId || !run) return;
    const source = new EventSource(`/api/backend/api/v1/agent-runs/${encodeURIComponent(runId)}/events?after=0`);
    source.onmessage = (message) => { try { const event = JSON.parse(message.data) as RunEvent; setEvents((current) => current.some((item) => item.sequence === event.sequence) ? current : [...current, event]); void loadRun(); } catch { /* Durable run state remains authoritative. */ } };
    source.onerror = () => source.close();
    return () => source.close();
  }, [loadRun, run, runId]);

  const portfolio = asMap(run?.state.portfolio);
  const evidence = asMap(run?.state.heat_evidence);
  const citations = Array.isArray(run?.state.citations) ? run.state.citations : [];
  const summaries = asMap(run?.state.summaries);
  const canDecide = run?.status === "waiting_approval";
  const title = text(run?.state.plan_name, run ? `Governed plan ${run.run_id.slice(0, 8)}` : "Governed plan");
  const timeline = useMemo(() => stages.map((stage) => ({ ...stage, status: stageStatus(run, stage.key) })), [run]);

  async function decide(decision: "approve" | "reject" | "revise") {
    if (!runId || !canDecide) return;
    setDecisionBusy(true); setDecisionError("");
    try { await backendFetch(`/api/v1/agent-runs/${encodeURIComponent(runId)}/approval`, { method: "POST", body: JSON.stringify({ decision, comment: comment.trim() || null }) }); setComment(""); await loadRun(); }
    catch (cause) { setDecisionError(cause instanceof Error ? cause.message : "Approval action failed"); }
    finally { setDecisionBusy(false); }
  }

  return <AppShell title="Governed plan">
    <div className="page-head"><div><div className="eyebrow">PLAN / GOVERNANCE</div><h1>{title}</h1><p>Review evidence, deterministic allocation, and the audit trail before a manager commits this plan.</p></div><span className={`badge ${statusBadge(run?.status ?? "queued")}`} aria-live="polite"><span className="dot" /> {run?.status?.replaceAll("_", " ") ?? "loading"}</span></div>
    {error && <div className="error" role="alert" style={{ marginBottom: 14 }}><strong>Plan unavailable.</strong> {error}<div className="top-actions" style={{ marginTop: 10 }}><button className="button" onClick={() => void loadRun()}>Retry</button><Link className="button ghost" href="/optimize">Open optimizer</Link></div></div>}
    {loading && !run && <div className="empty" aria-live="polite">Loading durable run state from AWS…</div>}
    {run && <>
      <section className="grid two-col"><article className="card"><div className="card-head"><div><div className="card-title">Execution timeline</div><div className="card-subtitle">Run {run.run_id} · revision {run.revision} · thread {run.thread_id.slice(0, 12)}…</div></div><span className="badge">SSE events enabled</span></div><div className="timeline">{timeline.map((stage, index) => <div className="timeline-item" key={stage.key}><span className={`stage-dot ${stage.status === "completed" ? "done" : stage.status === "running" ? "running" : ""}`} aria-label={`${stage.label}: ${stage.status}`}>{stage.status === "completed" ? "✓" : index + 1}</span><div><strong>{stage.label}</strong><p>{stage.status === "completed" ? text(summaries[stage.key], stage.description) : stage.description}</p></div><span className={`badge ${statusBadge(stage.status)}`}>{stage.status}</span>{index < timeline.length - 1 && <span className="timeline-line" />}</div>)}</div>{run.status === "failed" && <div className="error" style={{ marginTop: 15 }} role="alert">Execution stopped safely. Error code: <code>{run.error_code ?? "agent_run_failed"}</code>.</div>}</article>
        <aside className="card"><div className="card-head"><div><div className="card-title">Decision facts</div><div className="card-subtitle">Server-calculated outputs · never computed in the browser</div></div><span className="badge ok">source-traceable</span></div><div className="constraint-list"><div className="constraint"><span>Total cost</span><strong>{money(portfolio.total_cost)}</strong></div><div className="constraint"><span>Remaining budget</span><strong>{money(portfolio.remaining_budget)}</strong></div><div className="constraint"><span>Total benefit</span><strong>{text(portfolio.total_benefit)}</strong></div><div className="constraint"><span>Uncertainty penalty</span><strong>{text(portfolio.total_uncertainty)}</strong></div><div className="constraint"><span>Heat mean</span><strong>{text(evidence.mean_temperature_c, "Not available")}{evidence.mean_temperature_c !== undefined ? "°C" : ""}</strong></div></div><div className="card" style={{ marginTop: 14, padding: 14 }}><div className="eyebrow">AI BOUNDARY</div><p className="muted" style={{ fontSize: ".74rem", lineHeight: 1.5, marginBottom: 0 }}>Agents explain and sequence the work. FortyGuard measurements and OR-Tools allocations remain authoritative.</p></div></aside></section>
      <section className="grid two-col" style={{ marginTop: 14 }}><article className="card"><div className="card-head"><div><div className="card-title">Recommendation</div><div className="card-subtitle">Structured output from the governed run</div></div><span className="badge ok">{citations.length} citation{citations.length === 1 ? "" : "s"}</span></div><h2 style={{ fontSize: "1.25rem", letterSpacing: "-.04em", margin: "0 0 10px" }}>{text(run.state.recommendation, "Recommendation details are available after the workflow completes.")}</h2><p className="muted" style={{ fontSize: ".78rem", lineHeight: 1.55 }}>{text(summaries.portfolio, "The portfolio agent has not supplied a summary yet.")}</p><div className="eyebrow" style={{ marginTop: 22, marginBottom: 10 }}>CITED EVIDENCE</div>{citations.length ? <ul style={{ margin: 0, paddingLeft: 20, color: "var(--muted)", fontSize: ".76rem", lineHeight: 1.7 }}>{citations.map((citation) => <li key={String(citation)}>{String(citation)}</li>)}</ul> : <div className="empty">No citations have been recorded for this run.</div>}</article>
        <aside className="card"><div className="card-head"><div><div className="card-title">Constraints and alternatives</div><div className="card-subtitle">Review what the solver preserved</div></div></div><div className="constraint-list">{(Array.isArray(portfolio.binding_constraints) ? portfolio.binding_constraints : []).map((constraint) => <div className="constraint" key={String(constraint)}><span>{String(constraint)}</span><span className="badge warn">binding</span></div>)}</div>{(!Array.isArray(portfolio.binding_constraints) || portfolio.binding_constraints.length === 0) && <div className="empty">No binding constraints were returned.</div>}<div className="eyebrow" style={{ marginTop: 22, marginBottom: 8 }}>PROVENANCE</div><p className="muted" style={{ fontSize: ".73rem", lineHeight: 1.5, marginTop: 0 }}>Run ID {run.run_id}. The API response is tenant-scoped to the active Cognito organization.</p></aside></section>
      <section className="card" style={{ marginTop: 14 }}><div className="card-head"><div><div className="card-title">Audit trail</div><div className="card-subtitle">Safe event summaries only; prompts and completions are never rendered.</div></div><button className="button ghost" onClick={() => setShowAudit((value) => !value)} aria-expanded={showAudit}>{showAudit ? "Hide events" : "Show events"}</button></div>{showAudit && (events.length ? <div className="table-wrap"><table className="table"><thead><tr><th>Sequence</th><th>Event</th><th>Agent</th><th>Summary</th></tr></thead><tbody>{events.map((event) => <tr key={event.sequence}><td>{event.sequence}</td><td><code>{event.event}</code></td><td>{event.node ?? "—"}</td><td>{event.summary ?? "Recorded event"}</td></tr>)}</tbody></table></div> : <div className="empty">No streamed events have arrived yet. Refresh the durable run state to replay the current status.</div>)}</section>
      <section className="approval" style={{ marginTop: 14 }}><div style={{ flex: 1 }}><h3>{canDecide ? "Manager approval required" : `Plan is ${run.status.replaceAll("_", " ")}`}</h3><p>{canDecide ? "Approval creates an append-only audit event. Revision returns the run to the governed workflow." : "Approval controls are only available while the durable run is waiting for approval."}</p>{canDecide && <div className="field" style={{ marginTop: 12 }}><label htmlFor="approval-comment">Review comment (optional)</label><textarea id="approval-comment" rows={2} value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Record why this decision is appropriate for the organization." maxLength={2000} /></div>}{decisionError && <div className="error" role="alert" style={{ marginTop: 10 }}>{decisionError}</div>}</div><div className="approval-actions"><button className="button ghost" disabled={!canDecide || decisionBusy} onClick={() => void decide("revise")}>Request revision</button><button className="button danger" disabled={!canDecide || decisionBusy} onClick={() => void decide("reject")}>Reject</button><button className="button primary" disabled={!canDecide || decisionBusy} onClick={() => void decide("approve")}>{decisionBusy ? "Saving…" : "Approve plan"}</button></div></section>
    </>}
  </AppShell>;
}
