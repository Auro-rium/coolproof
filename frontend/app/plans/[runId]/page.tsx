"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "../../../components/app-shell";
import { backendFetch } from "../../../components/data";

type JsonMap = Record<string, unknown>;
type AgentRun = {
  run_id: string;
  thread_id: string;
  status: string;
  current_agent: string | null;
  revision: number;
  state: JsonMap;
  error_code?: string | null;
};
type RunEvent = {
  sequence: number;
  event: string;
  node?: string | null;
  summary?: string | null;
  payload?: JsonMap;
};
type Session = { membership?: { role?: string } };
type StreamState = "connecting" | "replaying" | "complete" | "unavailable";
type StageStatus = "queued" | "running" | "completed" | "failed";

const stages = [
  { key: "heat_intelligence", label: "Heat intelligence", description: "Heat evidence and exposure context" },
  { key: "intervention_analyst", label: "Intervention evidence", description: "Tenant-scoped sources and citations" },
  { key: "portfolio", label: "Portfolio", description: "Deterministic allocation and constraints" },
  { key: "verification", label: "Verification", description: "Expected-versus-observed review" },
] as const;

// EventSource only sends named SSE frames to listeners registered for that
// exact event name. Keep this list aligned with app/agents/runtime.py.
const runEventNames = [
  "run.created",
  "run.started",
  "node.completed",
  "approval.required",
  "run.failed",
  "run.approved",
  "run.rejectd",
  "run.rejected",
  "run.revision_requested",
  "run.completed",
] as const;

function asMap(value: unknown): JsonMap {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonMap : {};
}

function text(value: unknown, fallback = "—") {
  return typeof value === "string" || typeof value === "number" ? String(value) : fallback;
}

function money(value: unknown) {
  const amount = typeof value === "number" ? value : Number(value);
  return Number.isFinite(amount)
    ? new Intl.NumberFormat("en-US", { style: "currency", maximumFractionDigits: 0, currency: "USD" }).format(amount)
    : "—";
}

function statusBadge(status: string) {
  if (["completed", "approved"].includes(status)) return "ok";
  if (["running", "waiting_approval"].includes(status)) return "warn";
  if (["failed", "rejected"].includes(status)) return "fail";
  return "";
}

function stageStatus(run: AgentRun, key: string, events: RunEvent[]): StageStatus {
  // A stage is complete only when its durable node.completed event was replayed.
  if (events.some((event) => event.event === "node.completed" && event.node === key)) return "completed";
  if (run.status === "failed" && run.current_agent === key) return "failed";
  if (run.status === "running" && run.current_agent === key) return "running";
  return "queued";
}

export default function PlanPage() {
  const params = useParams<{ runId: string }>();
  const runId = params?.runId;
  const [run, setRun] = useState<AgentRun | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [streamState, setStreamState] = useState<StreamState>("connecting");
  const [streamVersion, setStreamVersion] = useState(0);
  const [role, setRole] = useState<string | null>(null);
  const [sessionChecked, setSessionChecked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionError, setDecisionError] = useState("");
  const [comment, setComment] = useState("");
  const [showAudit, setShowAudit] = useState(false);

  const loadRun = useCallback(async (silent = false) => {
    if (!runId) return;
    if (!silent) { setLoading(true); setError(""); }
    try {
      setRun(await backendFetch<AgentRun>(`/api/v1/agent-runs/${encodeURIComponent(runId)}`));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load this plan");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [runId]);

  useEffect(() => { void loadRun(); }, [loadRun]);

  useEffect(() => {
    let active = true;
    backendFetch<Session>("/api/v1/auth/session")
      .then((session) => { if (active) setRole(session.membership?.role?.toLowerCase() ?? null); })
      .catch(() => { if (active) setRole(null); })
      .finally(() => { if (active) setSessionChecked(true); });
    return () => { active = false; };
  }, []);

  useEffect(() => { setEvents([]); }, [runId]);

  useEffect(() => {
    if (!runId) return;
    setStreamState("connecting");
    const source = new EventSource(`/api/backend/api/v1/agent-runs/${encodeURIComponent(runId)}/events?after=0`);

    const recordEvent = (rawEvent: Event) => {
      if (!(rawEvent instanceof MessageEvent)) return;
      try {
        const event = JSON.parse(rawEvent.data) as RunEvent;
        if (typeof event.sequence !== "number" || typeof event.event !== "string") return;
        setEvents((current) => current.some((item) => item.sequence === event.sequence)
          ? current
          : [...current, event].sort((left, right) => left.sequence - right.sequence));
      } catch {
        // The durable run response remains authoritative if one frame is invalid.
      }
    };

    const finishReplay = () => {
      setStreamState("complete");
      source.close();
      void loadRun(true);
    };

    source.onopen = () => setStreamState("replaying");
    runEventNames.forEach((eventName) => source.addEventListener(eventName, recordEvent));
    source.addEventListener("stream.end", finishReplay);
    source.onerror = () => {
      setStreamState("unavailable");
      source.close();
    };

    return () => {
      runEventNames.forEach((eventName) => source.removeEventListener(eventName, recordEvent));
      source.removeEventListener("stream.end", finishReplay);
      source.close();
    };
  }, [loadRun, runId, streamVersion]);

  const portfolio = asMap(run?.state.portfolio);
  const evidence = asMap(run?.state.heat_evidence);
  const summaries = asMap(run?.state.summaries);
  const citations = Array.isArray(run?.state.citations)
    ? run.state.citations.filter((citation): citation is string => typeof citation === "string" && citation.trim().length > 0)
    : [];
  const privileged = role === "manager" || role === "admin";
  const waitingForDecision = run?.status === "waiting_approval";
  const canDecide = Boolean(waitingForDecision && sessionChecked && privileged);
  const title = text(run?.state.plan_name, run ? `Governed plan ${run.run_id.slice(0, 8)}` : "Governed plan");
  const timeline = useMemo(() => run ? stages.map((stage) => {
    const checkpoint = events.find((event) => event.event === "node.completed" && event.node === stage.key);
    return { ...stage, status: stageStatus(run, stage.key, events), checkpoint };
  }) : [], [events, run]);

  async function decide(decision: "approve" | "reject" | "revise") {
    if (!runId || !canDecide) return;
    setDecisionBusy(true); setDecisionError("");
    try {
      await backendFetch(`/api/v1/agent-runs/${encodeURIComponent(runId)}/approval`, {
        method: "POST",
        body: JSON.stringify({ decision, comment: comment.trim() || null }),
      });
      setComment("");
      await loadRun(true);
      setStreamVersion((version) => version + 1);
    } catch (cause) {
      setDecisionError(cause instanceof Error ? cause.message : "Approval action failed");
    } finally { setDecisionBusy(false); }
  }

  function retry() {
    void loadRun();
    setStreamVersion((version) => version + 1);
  }

  return (
    <AppShell title="Governed plan">
      <div className="page-head">
        <div><div className="eyebrow">PLAN / GOVERNANCE</div><h1>{title}</h1><p>Review returned evidence, deterministic allocation, and durable events before an authorized manager commits this plan.</p></div>
        <span className={`badge ${statusBadge(run?.status ?? "queued")}`} aria-live="polite"><span className="dot" /> {run?.status?.replaceAll("_", " ") ?? "loading"}</span>
      </div>

      {error && <div className="error" role="alert" style={{ marginBottom: 14 }}><strong>Plan unavailable.</strong> {error}<div className="top-actions" style={{ marginTop: 10 }}><button className="button" onClick={retry}>Retry</button><Link className="button ghost" href="/optimize">Open optimizer</Link></div></div>}
      {loading && !run && <div className="empty" aria-live="polite">Loading durable run state from AWS…</div>}

      {run && <>
        <section className="grid two-col">
          <article className="card">
            <div className="card-head"><div><div className="card-title">Execution timeline</div><div className="card-subtitle">Run {run.run_id} · revision {run.revision} · thread {run.thread_id.slice(0, 12)}…</div></div><span className={`badge ${streamState === "complete" ? "ok" : streamState === "unavailable" ? "fail" : "warn"}`}>{streamState === "complete" ? "event replay complete" : streamState === "unavailable" ? "event replay unavailable" : streamState}</span></div>
            <div className="timeline">
              {timeline.map((stage, index) => <div className="timeline-item" key={stage.key}>
                <span className={`stage-dot ${stage.status === "completed" ? "done" : stage.status === "running" ? "running" : ""}`} aria-label={`${stage.label}: ${stage.status}`}>{stage.status === "completed" ? "✓" : index + 1}</span>
                <div><strong>{stage.label}</strong><p>{stage.status === "completed" ? stage.checkpoint?.summary ?? text(summaries[stage.key], "Checkpoint recorded; no summary returned.") : stage.status === "running" ? "Durable run state identifies this as the current node." : stage.description}</p></div>
                <span className={`badge ${statusBadge(stage.status)}`}>{stage.status}</span>
                {index < timeline.length - 1 && <span className="timeline-line" />}
              </div>)}
            </div>
            {run.status === "failed" && <div className="error" style={{ marginTop: 15 }} role="alert">Execution stopped safely. Error code: <code>{run.error_code ?? "agent_run_failed"}</code>.</div>}
          </article>

          <aside className="card">
            <div className="card-head"><div><div className="card-title">Decision facts</div><div className="card-subtitle">Values returned in durable server state</div></div><span className="badge ok">server returned</span></div>
            <div className="constraint-list"><div className="constraint"><span>Total cost</span><strong>{money(portfolio.total_cost)}</strong></div><div className="constraint"><span>Remaining budget</span><strong>{money(portfolio.remaining_budget)}</strong></div><div className="constraint"><span>Total benefit</span><strong>{text(portfolio.total_benefit)}</strong></div><div className="constraint"><span>Uncertainty penalty</span><strong>{text(portfolio.total_uncertainty)}</strong></div><div className="constraint"><span>Heat mean</span><strong>{text(evidence.mean_temperature_c, "Not returned")}{evidence.mean_temperature_c !== undefined ? "°C" : ""}</strong></div></div>
            <div className="card" style={{ marginTop: 14, padding: 14 }}><div className="eyebrow">CALCULATION BOUNDARY</div><p className="muted" style={{ fontSize: ".74rem", lineHeight: 1.5, marginBottom: 0 }}>Agents sequence and explain work. Only values present in the durable run state are displayed here; missing evidence stays visibly missing.</p></div>
          </aside>
        </section>

        <section className="grid two-col" style={{ marginTop: 14 }}>
          <article className="card">
            <div className="card-head"><div><div className="card-title">Recommendation record</div><div className="card-subtitle">Structured content actually returned by the governed run</div></div><span className={`badge ${citations.length ? "ok" : ""}`}>{citations.length} citation{citations.length === 1 ? "" : "s"}</span></div>
            {typeof run.state.recommendation === "string" && run.state.recommendation.trim() ? <h2 style={{ fontSize: "1.25rem", letterSpacing: "-.04em", margin: "0 0 10px" }}>{run.state.recommendation}</h2> : <div className="empty">No standalone recommendation was returned in this run state.</div>}
            {typeof summaries.portfolio === "string" && summaries.portfolio.trim() ? <p className="muted" style={{ fontSize: ".78rem", lineHeight: 1.55 }}>{summaries.portfolio}</p> : <p className="muted">No portfolio summary was returned.</p>}
            <div className="eyebrow" style={{ marginTop: 22, marginBottom: 10 }}>CITED EVIDENCE</div>
            {citations.length ? <ul style={{ margin: 0, paddingLeft: 20, color: "var(--muted)", fontSize: ".76rem", lineHeight: 1.7 }}>{citations.map((citation, index) => <li key={`${citation}-${index}`}>{citation}</li>)}</ul> : <div className="empty">No citations were returned for this run.</div>}
          </article>

          <aside className="card">
            <div className="card-head"><div><div className="card-title">Constraints and provenance</div><div className="card-subtitle">Only solver fields present in the response are listed</div></div></div>
            <div className="constraint-list">{(Array.isArray(portfolio.binding_constraints) ? portfolio.binding_constraints : []).map((constraint) => <div className="constraint" key={String(constraint)}><span>{String(constraint)}</span><span className="badge warn">binding</span></div>)}</div>
            {(!Array.isArray(portfolio.binding_constraints) || portfolio.binding_constraints.length === 0) && <div className="empty">No binding constraints were returned.</div>}
            <div className="eyebrow" style={{ marginTop: 22, marginBottom: 8 }}>PROVENANCE</div><p className="muted" style={{ fontSize: ".73rem", lineHeight: 1.5, marginTop: 0 }}>Run ID {run.run_id}. The backend returned this run through the active organization-scoped session.</p>
          </aside>
        </section>

        <section className="card" style={{ marginTop: 14 }}>
          <div className="card-head"><div><div className="card-title">Audit trail</div><div className="card-subtitle">Safe event summaries only; prompts and completions are never rendered.</div></div><button className="button ghost" onClick={() => setShowAudit((value) => !value)} aria-expanded={showAudit}>{showAudit ? "Hide events" : "Show events"}</button></div>
          {showAudit && (events.length ? <div className="table-wrap"><table className="table"><thead><tr><th>Sequence</th><th>Event</th><th>Agent</th><th>Summary</th></tr></thead><tbody>{events.map((event) => <tr key={event.sequence}><td>{event.sequence}</td><td><code>{event.event}</code></td><td>{event.node ?? "—"}</td><td>{event.summary ?? "No summary returned"}</td></tr>)}</tbody></table></div> : <div className="empty">No durable events were replayed. Stage completion is not inferred without them.</div>)}
        </section>

        <section className="approval" style={{ marginTop: 14 }}>
          <div style={{ flex: 1 }}>
            <h3>{waitingForDecision ? "Manager approval required" : `Plan is ${run.status.replaceAll("_", " ")}`}</h3>
            <p>{waitingForDecision ? !sessionChecked ? "Checking your organization membership before showing decision controls." : privileged ? "Your manager or admin membership permits a recorded decision." : `Your ${role ?? "current"} membership can review this plan but cannot approve, reject, or request revision.` : "Decision controls are available only for a waiting run and an authorized manager or admin membership."}</p>
            {canDecide && <div className="field" style={{ marginTop: 12 }}><label htmlFor="approval-comment">Review comment (optional)</label><textarea id="approval-comment" rows={2} value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Record why this decision is appropriate for the organization." maxLength={2000} /></div>}
            {decisionError && <div className="error" role="alert" style={{ marginTop: 10 }}>{decisionError}</div>}
          </div>
          {canDecide && <div className="approval-actions"><button className="button ghost" disabled={decisionBusy} onClick={() => void decide("revise")}>Request revision</button><button className="button danger" disabled={decisionBusy} onClick={() => void decide("reject")}>Reject</button><button className="button primary" disabled={decisionBusy} onClick={() => void decide("approve")}>{decisionBusy ? "Saving…" : "Approve plan"}</button></div>}
        </section>
      </>}
    </AppShell>
  );
}
