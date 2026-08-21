"use client";

import Link from "next/link";
import { useState } from "react";
import { AppShell } from "../../components/app-shell";
import { backendFetch } from "../../components/data";

type Allocation = { zone_id?: string; intervention_id?: string; units?: number; cost?: number; benefit?: number; uncertainty?: number };
type SolverResult = { status: string; portfolio_run_id?: string; total_cost?: number; total_benefit?: number; total_uncertainty?: number; remaining_budget?: number; rejected?: string[]; binding_constraints?: string[]; allocations?: Allocation[] };
type DraftIntervention = { id: string; name: string; unitCost: number; score: number; uncertainty: number; uses: string[]; enabled: boolean };

const zoneDefaults = [
  { id: "phoenix-central", name: "Phoenix Central", landUse: "residential", equity: true, school: false, exposure: 8.4, capacity: 2 },
  { id: "school-corridor", name: "School corridor", landUse: "civic", equity: false, school: true, exposure: 6.7, capacity: 1 },
];

function money(value?: number) { return typeof value === "number" ? new Intl.NumberFormat("en-US", { style: "currency", maximumFractionDigits: 0, currency: "USD" }).format(value) : "—"; }

export default function OptimizePage() {
  const [budget, setBudget] = useState("100000");
  const [penalty, setPenalty] = useState("0.2");
  const [minEquity, setMinEquity] = useState("1");
  const [minSchool, setMinSchool] = useState("1");
  const [interventions, setInterventions] = useState<DraftIntervention[]>([
    { id: "shade-trees", name: "Shade trees", unitCost: 25000, score: 8, uncertainty: 0.1, uses: ["residential", "civic"], enabled: true },
    { id: "cool-pavement", name: "Cool pavement", unitCost: 60000, score: 11.5, uncertainty: 0.25, uses: ["residential", "civic"], enabled: true },
  ]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SolverResult | null>(null);
  const [error, setError] = useState("");
  const [planBusy, setPlanBusy] = useState(false);
  const [planError, setPlanError] = useState("");
  const [agentRunId, setAgentRunId] = useState("");

  function toggleIntervention(id: string) { setInterventions((current) => current.map((item) => item.id === id ? { ...item, enabled: !item.enabled } : item)); }

  async function runOptimizer() {
    const numericBudget = Number(budget); const numericPenalty = Number(penalty); const equity = Number(minEquity); const school = Number(minSchool);
    if (!Number.isFinite(numericBudget) || numericBudget < 0) { setError("Enter a budget of $0 or more."); return; }
    if (!Number.isFinite(numericPenalty) || numericPenalty < 0 || !Number.isFinite(equity) || equity < 0 || !Number.isFinite(school) || school < 0) { setError("Constraints must be zero or greater."); return; }
    const selected = interventions.filter((item) => item.enabled);
    if (!selected.length) { setError("Select at least one intervention before running the solver."); return; }
    setRunning(true); setError(""); setResult(null); setPlanError(""); setAgentRunId("");
    try {
      const response = await backendFetch<SolverResult>("/api/v1/portfolio-runs", { method: "POST", body: JSON.stringify({
        budget: numericBudget, min_equity_units: equity, min_school_units: school, uncertainty_penalty: numericPenalty,
        zones: zoneDefaults.map((zone) => ({ zone_id: zone.id, land_use: zone.landUse, equity_priority: zone.equity, is_school: zone.school, exposure_score: zone.exposure, implementation_capacity: zone.capacity })),
        interventions: selected.map((item) => ({ intervention_id: item.id, name: item.name, unit_cost: item.unitCost, cooling_score: item.score, eligible_land_uses: item.uses, uncertainty: item.uncertainty })),
      }) });
      setResult(response);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "The AWS optimizer could not complete this request."); }
    finally { setRunning(false); }
  }

  async function createPlan() {
    if (!result) return;
    setPlanBusy(true); setPlanError("");
    try {
      const run = await backendFetch<{ run_id: string }>("/api/v1/agent-runs", { method: "POST", body: JSON.stringify({ input: { portfolio_run_id: result.portfolio_run_id, portfolio: result, source: "optimizer" } }) });
      setAgentRunId(run.run_id);
    } catch (cause) { setPlanError(cause instanceof Error ? cause.message : "The governed plan could not be created."); }
    finally { setPlanBusy(false); }
  }

  return <AppShell title="Optimize">
    <div className="page-head"><div><div className="eyebrow">OR-TOOLS / DETERMINISTIC</div><h1>Optimize portfolio</h1><p>Define constraints. AWS runs the allocation solver; this screen presents its result with provenance and next actions.</p></div><button className="button primary" onClick={() => void runOptimizer()} disabled={running}>{running ? "Running solver…" : "Run optimizer →"}</button></div>
    {error && <div className="error" role="alert" style={{ marginBottom: 14 }}><strong>Cannot run optimization.</strong> {error}<span className="muted"> Fix the highlighted inputs and try again.</span></div>}
    <section className="grid two-col"><article className="card"><div className="card-head"><div><div className="card-title">Constraints</div><div className="card-subtitle">Validated server-side before solving</div></div><span className="badge">Draft inputs</span></div><div className="form-grid"><div className="field"><label htmlFor="budget">Total budget (USD)</label><input id="budget" value={budget} onChange={(event) => setBudget(event.target.value)} type="number" min="0" step="1000" aria-describedby="budget-help"/><small id="budget-help" className="muted">Available portfolio budget before this run.</small></div><div className="field"><label htmlFor="penalty">Uncertainty penalty</label><input id="penalty" value={penalty} onChange={(event) => setPenalty(event.target.value)} type="number" min="0" step=".05"/></div><div className="field"><label htmlFor="equity">Minimum equity units</label><input id="equity" value={minEquity} onChange={(event) => setMinEquity(event.target.value)} type="number" min="0" step="1"/></div><div className="field"><label htmlFor="school">Minimum school units</label><input id="school" value={minSchool} onChange={(event) => setMinSchool(event.target.value)} type="number" min="0" step="1"/></div></div><div className="eyebrow" style={{ marginTop: 24, marginBottom: 10 }}>ZONE CAPACITY</div><div className="constraint-list">{zoneDefaults.map((zone) => <div className="constraint" key={zone.id}><span><strong>{zone.name}</strong><br/><small>{zone.landUse} · exposure {zone.exposure.toFixed(1)} · {zone.equity ? "equity priority" : zone.school ? "school protected" : "standard"}</small></span><small>capacity {zone.capacity}</small></div>)}</div><div className="eyebrow" style={{ marginTop: 24, marginBottom: 10 }}>INTERVENTIONS</div><div className="constraint-list">{interventions.map((item) => <label className="constraint" key={item.id} style={{ cursor: "pointer" }}><span><input type="checkbox" checked={item.enabled} onChange={() => toggleIntervention(item.id)} style={{ marginRight: 10 }}/><strong>{item.name}</strong><br/><small>{money(item.unitCost)} / unit · score {item.score.toFixed(1)} · uncertainty {item.uncertainty.toFixed(2)}</small></span><small>{item.uses.join(" · ")}</small></label>)}</div></article>
      <aside className="card"><div className="card-head"><div><div className="card-title">Solver output</div><div className="card-subtitle">{running ? "OR-Tools is evaluating constraints…" : result ? `Run ${result.portfolio_run_id ?? "completed"}` : "No run yet"}</div></div><span className={`badge ${running ? "warn" : result ? "ok" : ""}`} aria-live="polite">{running ? "running" : result ? "completed" : "ready"}</span></div>{!result && !running && <div className="empty">Run the solver to see allocations, binding constraints, uncertainty, and the immutable portfolio run ID.</div>}{running && <div className="empty" aria-live="polite">Sending the selected constraints to the AWS OR-Tools service…</div>}{result && <><div className="grid kpis" style={{ gridTemplateColumns: "repeat(2,1fr)" }}><article className="card"><div className="kpi-label">Total cost</div><strong className="kpi-value">{money(result.total_cost)}</strong><div className="kpi-meta">server result</div></article><article className="card"><div className="kpi-label">Remaining</div><strong className="kpi-value">{money(result.remaining_budget)}</strong><div className="kpi-meta">within budget</div></article><article className="card"><div className="kpi-label">Benefit</div><strong className="kpi-value">{result.total_benefit ?? "—"}</strong><div className="kpi-meta">cooling score</div></article><article className="card"><div className="kpi-label">Uncertainty</div><strong className="kpi-value">{result.total_uncertainty ?? "—"}</strong><div className="kpi-meta">penalized objective</div></article></div><div className="table-wrap"><table className="table"><thead><tr><th>Zone</th><th>Intervention</th><th>Units</th><th>Cost</th><th>Benefit</th></tr></thead><tbody>{result.allocations?.length ? result.allocations.map((allocation, index) => <tr key={`${allocation.zone_id}-${allocation.intervention_id}-${index}`}><td>{allocation.zone_id ?? "—"}</td><td>{allocation.intervention_id ?? "—"}</td><td>{allocation.units ?? "—"}</td><td>{money(allocation.cost)}</td><td>{allocation.benefit ?? "—"}</td></tr>) : <tr><td colSpan={5}>No allocations returned.</td></tr>}</tbody></table></div>{result.binding_constraints?.map((constraint) => <span className="badge warn" style={{ marginTop: 12, marginRight: 6 }} key={constraint}>Binding · {constraint}</span>)}{result.rejected?.length ? <div className="notice">Rejected candidates: {result.rejected.join(", ")}</div> : null}<div className="card" style={{ marginTop: 16, padding: 14 }}><div className="eyebrow">NEXT GOVERNED STEP</div><p className="muted" style={{ fontSize: ".75rem", lineHeight: 1.5 }}>This result is a recommendation. Create a governed four-agent run to attach evidence, request manager review, and record an approval decision.</p>{agentRunId ? <Link href={`/plans/${agentRunId}`} className="button primary">Open governed plan →</Link> : <button className="button primary" onClick={() => void createPlan()} disabled={planBusy}>{planBusy ? "Creating plan…" : "Create governed plan"}</button>}{planError && <div className="error" role="alert" style={{ marginTop: 10 }}>{planError}</div>}</div></>}</aside></section>
    <section className="card" style={{ marginTop: 14 }}><div className="card-head"><div><div className="card-title">Calculation boundary</div><div className="card-subtitle">Trust calibration and auditability</div></div><span className="badge ok">OR-Tools authoritative</span></div><p className="muted" style={{ fontSize: ".76rem", lineHeight: 1.6, margin: 0 }}>The browser sends typed constraints to FastAPI. OR-Tools calculates the allocation on AWS and persists a portfolio run. Agents may explain the output later, but cannot change its measurements or arithmetic.</p></section>
  </AppShell>;
}
