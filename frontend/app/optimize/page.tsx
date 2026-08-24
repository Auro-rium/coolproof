"use client";

import { ArrowRight, Calculator, CheckCircle2, CircleDollarSign, FileCheck2, Scale, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AppShell } from "../../components/app-shell";
import { backendFetch } from "../../components/data";

type Allocation = { zone_id?: string; intervention_id?: string; units?: number; cost?: number; benefit?: number; uncertainty?: number };
type SolverResult = { status: string; portfolio_run_id?: string; total_cost?: number; total_benefit?: number; total_uncertainty?: number; remaining_budget?: number; rejected?: string[]; binding_constraints?: string[]; allocations?: Allocation[] };
type DraftIntervention = { id: string; name: string; unitCost: number; score: number; uncertainty: number; uses: string[]; enabled: boolean };

const scenarioZones = [
  { id: "phoenix-central", name: "Phoenix Central", landUse: "residential", equity: true, school: false, exposure: 8.4, capacity: 2 },
  { id: "school-corridor", name: "School corridor", landUse: "civic", equity: false, school: true, exposure: 6.7, capacity: 1 },
];

function money(value?: number) {
  return typeof value === "number"
    ? new Intl.NumberFormat("en-US", { style: "currency", maximumFractionDigits: 0, currency: "USD" }).format(value)
    : "—";
}

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

  function toggleIntervention(id: string) {
    setInterventions((current) => current.map((item) => item.id === id ? { ...item, enabled: !item.enabled } : item));
  }

  async function runOptimizer() {
    const numericBudget = Number(budget);
    const numericPenalty = Number(penalty);
    const equity = Number(minEquity);
    const school = Number(minSchool);
    if (!Number.isFinite(numericBudget) || numericBudget < 0) { setError("Enter a budget of $0 or more."); return; }
    if (!Number.isFinite(numericPenalty) || numericPenalty < 0 || !Number.isFinite(equity) || equity < 0 || !Number.isFinite(school) || school < 0) { setError("Each constraint must be zero or greater."); return; }
    const selected = interventions.filter((item) => item.enabled);
    if (!selected.length) { setError("Select at least one intervention before building the portfolio."); return; }

    setRunning(true); setError(""); setResult(null); setPlanError(""); setAgentRunId("");
    try {
      const response = await backendFetch<SolverResult>("/api/v1/portfolio-runs", {
        method: "POST",
        body: JSON.stringify({
          budget: numericBudget,
          min_equity_units: equity,
          min_school_units: school,
          uncertainty_penalty: numericPenalty,
          zones: scenarioZones.map((zone) => ({ zone_id: zone.id, land_use: zone.landUse, equity_priority: zone.equity, is_school: zone.school, exposure_score: zone.exposure, implementation_capacity: zone.capacity })),
          interventions: selected.map((item) => ({ intervention_id: item.id, name: item.name, unit_cost: item.unitCost, cooling_score: item.score, eligible_land_uses: item.uses, uncertainty: item.uncertainty })),
        }),
      });
      setResult(response);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The optimization service could not complete this request.");
    } finally { setRunning(false); }
  }

  async function createPlan() {
    if (!result) return;
    setPlanBusy(true); setPlanError("");
    try {
      const run = await backendFetch<{ run_id: string }>("/api/v1/agent-runs", {
        method: "POST",
        body: JSON.stringify({ input: { portfolio_run_id: result.portfolio_run_id, portfolio: result, source: "optimizer" } }),
      });
      setAgentRunId(run.run_id);
    } catch (cause) {
      setPlanError(cause instanceof Error ? cause.message : "The governed plan could not be created.");
    } finally { setPlanBusy(false); }
  }

  return (
    <AppShell title="Optimize">
      <div className="page-head">
        <div>
          <div className="eyebrow">PORTFOLIO BUILDER</div>
          <h1>Find the strongest investment mix</h1>
          <p>Set the budget and public-interest safeguards. CoolProof returns an auditable allocation from the deterministic solver—not an AI guess.</p>
        </div>
        <button className="button primary" onClick={() => void runOptimizer()} disabled={running}>
          <Calculator size={16} aria-hidden="true" /> {running ? "Evaluating portfolio…" : "Build portfolio"}
        </button>
      </div>

      {error && <div className="error" role="alert" style={{ marginBottom: 14 }}><strong>Portfolio could not be built.</strong> {error}</div>}

      <section className="grid two-col">
        <article className="card">
          <div className="card-head">
            <div><div className="card-title">Investment guardrails</div><div className="card-subtitle">Validated again by the backend before solving</div></div>
            <span className="badge"><Scale size={13} aria-hidden="true" /> Scenario inputs</span>
          </div>
          <div className="form-grid">
            <div className="field"><label htmlFor="budget">Available budget (USD)</label><input id="budget" value={budget} onChange={(event) => setBudget(event.target.value)} type="number" min="0" step="1000" aria-describedby="budget-help" /><small id="budget-help" className="muted">Maximum spend for this portfolio run.</small></div>
            <div className="field"><label htmlFor="penalty">Uncertainty penalty</label><input id="penalty" value={penalty} onChange={(event) => setPenalty(event.target.value)} type="number" min="0" step=".05" /><small className="muted">Higher values favor better-supported options.</small></div>
            <div className="field"><label htmlFor="equity">Minimum equity-priority units</label><input id="equity" value={minEquity} onChange={(event) => setMinEquity(event.target.value)} type="number" min="0" step="1" /></div>
            <div className="field"><label htmlFor="school">Minimum school-area units</label><input id="school" value={minSchool} onChange={(event) => setMinSchool(event.target.value)} type="number" min="0" step="1" /></div>
          </div>

          <div className="notice" style={{ marginTop: 16 }}>These are explicit scenario inputs, not live observations. Only a completed backend response appears as a calculated result.</div>

          <div className="eyebrow" style={{ marginTop: 22, marginBottom: 10 }}>AREAS IN THIS SCENARIO</div>
          <div className="constraint-list">
            {scenarioZones.map((zone) => <div className="constraint" key={zone.id}><span><strong>{zone.name}</strong><br /><small>{zone.landUse} · exposure input {zone.exposure.toFixed(1)} · {zone.equity ? "equity priority" : zone.school ? "school area" : "standard"}</small></span><small>up to {zone.capacity} units</small></div>)}
          </div>

          <div className="eyebrow" style={{ marginTop: 22, marginBottom: 10 }}>OPTIONS TO CONSIDER</div>
          <div className="constraint-list">
            {interventions.map((item) => <label className="constraint" key={item.id} style={{ cursor: "pointer" }}><span><input type="checkbox" checked={item.enabled} onChange={() => toggleIntervention(item.id)} style={{ marginRight: 10 }} /><strong>{item.name}</strong><br /><small>{money(item.unitCost)} per unit · score input {item.score.toFixed(1)} · uncertainty {item.uncertainty.toFixed(2)}</small></span><small>{item.uses.join(" · ")}</small></label>)}
          </div>
        </article>

        <aside className="card">
          <div className="card-head">
            <div><div className="card-title">Recommended portfolio</div><div className="card-subtitle">{running ? "Evaluating eligible combinations…" : result ? `Run ${result.portfolio_run_id ?? "completed"}` : "Waiting for your inputs"}</div></div>
            <span className={`badge ${running ? "warn" : result ? "ok" : ""}`} aria-live="polite">{result && !running ? <CheckCircle2 size={13} aria-hidden="true" /> : <Calculator size={13} aria-hidden="true" />} {running ? "evaluating" : result ? result.status : "ready"}</span>
          </div>

          {!result && !running && <div className="empty"><CircleDollarSign size={28} aria-hidden="true" /><p>Build a portfolio to see cost, benefit, uncertainty, allocations, and binding safeguards returned by the solver.</p></div>}
          {running && <div className="empty" aria-live="polite">The backend is solving the submitted scenario. No result is shown until that calculation completes.</div>}

          {result && <>
            <div className="grid kpis" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
              <article className="card"><div className="kpi-label">Recommended spend</div><strong className="kpi-value">{money(result.total_cost)}</strong><div className="kpi-meta">backend result</div></article>
              <article className="card"><div className="kpi-label">Budget remaining</div><strong className="kpi-value">{money(result.remaining_budget)}</strong><div className="kpi-meta">backend result</div></article>
              <article className="card"><div className="kpi-label">Cooling benefit</div><strong className="kpi-value">{result.total_benefit ?? "—"}</strong><div className="kpi-meta">solver score</div></article>
              <article className="card"><div className="kpi-label">Total uncertainty</div><strong className="kpi-value">{result.total_uncertainty ?? "—"}</strong><div className="kpi-meta">penalized objective</div></article>
            </div>
            <div className="table-wrap"><table className="table"><thead><tr><th>Area</th><th>Intervention</th><th>Units</th><th>Cost</th><th>Benefit</th></tr></thead><tbody>{result.allocations?.length ? result.allocations.map((allocation, index) => <tr key={`${allocation.zone_id}-${allocation.intervention_id}-${index}`}><td>{allocation.zone_id ?? "—"}</td><td>{allocation.intervention_id ?? "—"}</td><td>{allocation.units ?? "—"}</td><td>{money(allocation.cost)}</td><td>{allocation.benefit ?? "—"}</td></tr>) : <tr><td colSpan={5}>The solver returned no allocations.</td></tr>}</tbody></table></div>
            {result.binding_constraints?.map((constraint) => <span className="badge warn" style={{ marginTop: 12, marginRight: 6 }} key={constraint}>Binding · {constraint}</span>)}
            {result.rejected?.length ? <div className="notice">Options excluded by the solver: {result.rejected.join(", ")}</div> : null}
            <div className="card" style={{ marginTop: 16, padding: 16 }}>
              <div className="eyebrow">REVIEW BEFORE APPROVAL</div>
              <p className="muted" style={{ fontSize: ".78rem", lineHeight: 1.55 }}>Turn this recommendation into a governed plan to attach evidence, run verification checks, and request a manager decision.</p>
              {agentRunId ? <Link href={`/plans/${agentRunId}`} className="button primary">Open plan <ArrowRight size={15} aria-hidden="true" /></Link> : <button className="button primary" onClick={() => void createPlan()} disabled={planBusy}><FileCheck2 size={16} aria-hidden="true" /> {planBusy ? "Creating plan…" : "Create reviewable plan"}</button>}
              {planError && <div className="error" role="alert" style={{ marginTop: 10 }}>{planError}</div>}
            </div>
          </>}
        </aside>
      </section>

      <section className="card" style={{ marginTop: 14 }}>
        <div className="card-head"><div><div className="card-title">How the recommendation is protected</div><div className="card-subtitle">Clear boundaries between calculation, explanation, and approval</div></div><span className="badge ok"><ShieldCheck size={13} aria-hidden="true" /> Deterministic result</span></div>
        <p className="muted" style={{ fontSize: ".78rem", lineHeight: 1.6, margin: 0 }}>FastAPI receives typed constraints. OR-Tools calculates and persists the allocation on AWS. Agents may retrieve evidence and explain the result, but they cannot rewrite measurements, arithmetic, or the manager approval record.</p>
      </section>
    </AppShell>
  );
}
