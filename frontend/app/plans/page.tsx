"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useState } from "react";
import {
  ArrowRight,
  Calculator,
  CheckCircle2,
  ClipboardCheck,
  FileSearch,
  GitPullRequestArrow,
  LockKeyhole,
  Search,
  ShieldCheck,
} from "lucide-react";
import { AppShell } from "../../components/app-shell";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export default function PlansIndexPage() {
  const router = useRouter();
  const [runId, setRunId] = useState("");
  const [validationError, setValidationError] = useState("");

  function openPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = runId.trim();
    if (!UUID_PATTERN.test(normalized)) {
      setValidationError("Enter the complete run ID returned by the optimizer.");
      return;
    }
    setValidationError("");
    router.push(`/plans/${encodeURIComponent(normalized)}`);
  }

  return (
    <AppShell title="Plans">
      <header className="page-head">
        <div>
          <span className="eyebrow">GOVERNED DECISIONS</span>
          <h1>Plans ready for human judgment</h1>
          <p>Review the evidence, allocation, and audit trail behind a recommendation before anything is approved.</p>
        </div>
        <span className="badge ok"><ShieldCheck size={14} /> Manager-controlled</span>
      </header>

      <section className="grid two-col">
        <article className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">CONTINUE A PLAN</span>
              <h2>Open a durable workflow</h2>
              <p>Use the run ID created after a successful portfolio optimization.</p>
            </div>
            <span className="badge"><FileSearch size={13} /> Run lookup</span>
          </div>

          <form onSubmit={openPlan} noValidate>
            <div className="field">
              <label htmlFor="plan-run-id">Plan run ID</label>
              <input
                id="plan-run-id"
                name="plan-run-id"
                value={runId}
                onChange={(event) => {
                  setRunId(event.target.value);
                  if (validationError) setValidationError("");
                }}
                placeholder="00000000-0000-0000-0000-000000000000"
                autoComplete="off"
                spellCheck={false}
                aria-describedby="plan-run-help"
                aria-invalid={Boolean(validationError)}
              />
              <small id="plan-run-help" className="muted">The ID is shown when CoolProof creates the governed run.</small>
            </div>
            {validationError ? <div className="error" role="alert" style={{ marginTop: 12 }}>{validationError}</div> : null}
            <div className="top-actions" style={{ marginTop: 14 }}>
              <button className="button primary" type="submit"><Search size={15} /> Open plan</button>
              <Link className="button ghost" href="/optimize"><Calculator size={15} /> Create from optimizer</Link>
            </div>
          </form>

          <div className="empty" style={{ marginTop: 20 }}>
            No plan is selected. CoolProof does not display placeholder runs or sample approvals here.
          </div>
        </article>

        <aside className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">APPROVAL STANDARD</span>
              <h2>What a reviewer receives</h2>
              <p>Each plan keeps the decision evidence and workflow state together.</p>
            </div>
            <ClipboardCheck size={21} aria-hidden="true" />
          </div>
          <div className="constraint-list">
            <div className="constraint">
              <span><FileSearch size={16} aria-hidden="true" /> Cited heat and intervention evidence</span>
              <span className="badge ok">Traceable</span>
            </div>
            <div className="constraint">
              <span><GitPullRequestArrow size={16} aria-hidden="true" /> Deterministic allocation and constraints</span>
              <span className="badge ok">Reproducible</span>
            </div>
            <div className="constraint">
              <span><LockKeyhole size={16} aria-hidden="true" /> Explicit manager or admin decision</span>
              <span className="badge warn">Required</span>
            </div>
          </div>
          <div className="notice" style={{ marginTop: 18 }}>
            Agents can retrieve and explain the evidence. They cannot approve a plan or change solver-calculated allocations.
          </div>
        </aside>
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <div className="card-head">
          <div>
            <span className="eyebrow">FROM RESULT TO DECISION</span>
            <h2>A visible, reversible workflow</h2>
            <p>Each transition is persisted so a review can resume without losing its provenance.</p>
          </div>
        </div>
        <div className="grid kpis" style={{ marginBottom: 0 }}>
          <div><span className="step-number">01</span><h3>Calculate</h3><p className="muted">The optimizer returns the portfolio and preserved constraints.</p></div>
          <div><span className="step-number">02</span><h3>Review</h3><p className="muted">The governed run assembles evidence, citations, and its audit trail.</p></div>
          <div><span className="step-number">03</span><h3>Decide</h3><p className="muted">A manager can approve, reject, or request a revision with a recorded comment.</p></div>
          <div><span className="step-number">04</span><h3>Measure</h3><p className="muted">Approved work can move into observed-outcome verification.</p></div>
        </div>
        <div className="top-actions" style={{ marginTop: 20 }}>
          <Link className="button primary" href="/optimize">Build a portfolio <ArrowRight size={15} /></Link>
          <Link className="button ghost" href="/verify"><CheckCircle2 size={15} /> Go to verification</Link>
        </div>
      </section>
    </AppShell>
  );
}
