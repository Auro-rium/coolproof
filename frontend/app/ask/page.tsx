"use client";

import { ArrowRight, CheckCircle2, FileSearch, LockKeyhole, MessageSquareText, Send, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AppShell } from "../../components/app-shell";
import { backendFetch } from "../../components/data";
import { Timeline } from "../../components/timeline";

type GovernedRun = { id: string; status: string };

const suggestedQuestions = [
  { label: "Protect required projects while lowering cost", prompt: "Reduce the budget to $750k while preserving school projects." },
  { label: "Compare lower-cost options for one area", prompt: "Compare lower-cost alternatives for Phoenix Central." },
  { label: "Find work that still needs proof", prompt: "Show projects awaiting verification." },
];

export default function AskPage() {
  const [command, setCommand] = useState("");
  const [running, setRunning] = useState(false);
  const [run, setRun] = useState<GovernedRun | null>(null);
  const [error, setError] = useState("");

  async function analyze() {
    const normalizedCommand = command.trim();
    if (!normalizedCommand || running) return;
    setRunning(true); setError(""); setRun(null);
    try {
      const response = await backendFetch<{ status: string; run_id: string }>("/api/v1/agent-runs", {
        method: "POST",
        body: JSON.stringify({ input: { command: normalizedCommand, request_type: "bounded_portfolio_question" } }),
      });
      setRun({ id: response.run_id, status: response.status });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The governed analysis could not be started.");
    } finally { setRunning(false); }
  }

  return (
    <AppShell title="Ask CoolProof">
      <div className="page-head">
        <div>
          <div className="eyebrow">EVIDENCE ASSISTANT</div>
          <h1>Ask about the portfolio</h1>
          <p>Ask for a comparison, a constraint change, or the evidence behind a recommendation. CoolProof creates a traceable run and keeps every approval with a human manager.</p>
        </div>
        <span className="badge ok"><LockKeyhole size={13} aria-hidden="true" /> Human approval required</span>
      </div>

      <section className="grid two-col">
        <article className="card">
          <div className="card-head">
            <div><div className="card-title">What do you want to understand?</div><div className="card-subtitle">Ask one specific question about cost, evidence, or readiness</div></div>
            <MessageSquareText size={19} aria-hidden="true" />
          </div>
          <div className="field">
            <label htmlFor="portfolio-question">Portfolio question</label>
            <textarea id="portfolio-question" value={command} onChange={(event) => setCommand(event.target.value)} placeholder="For example: Which interventions protect school areas within a $750k budget?" rows={6} maxLength={2000} />
            <small className="muted">{command.length.toLocaleString()} / 2,000 characters</small>
          </div>
          <div className="top-actions" style={{ marginTop: 14 }}>
            <button className="button primary" disabled={!command.trim() || running} onClick={() => void analyze()}><Send size={15} aria-hidden="true" /> {running ? "Creating governed run…" : "Analyze question"}</button>
          </div>

          {error && <div className="error" role="alert" style={{ marginTop: 14 }}><strong>Analysis could not start.</strong> {error}</div>}
          {run && <div className="approval" style={{ marginTop: 14 }} aria-live="polite"><div><h3><CheckCircle2 size={16} aria-hidden="true" /> Governed run created</h3><p>Run {run.id} is {run.status}. No approval has been granted by this action.</p></div><Link href={`/plans/${run.id}`} className="button primary">Open run <ArrowRight size={15} aria-hidden="true" /></Link></div>}

          <div className="eyebrow" style={{ marginTop: 28, marginBottom: 10 }}>START WITH A FOCUSED QUESTION</div>
          <div className="constraint-list">
            {suggestedQuestions.map((suggestion) => <button className="constraint" key={suggestion.prompt} onClick={() => setCommand(suggestion.prompt)} type="button"><span>{suggestion.label}</span><ArrowRight size={15} aria-hidden="true" /></button>)}
          </div>
        </article>

        <aside className="card">
          <div className="card-head">
            <div><div className="card-title">Visible from question to decision</div><div className="card-subtitle">The workflow records evidence and handoffs as it runs</div></div>
            <span className={`badge ${running ? "warn" : run ? "ok" : ""}`} aria-live="polite">{running ? "working" : run ? "ready for review" : "ready"}</span>
          </div>
          <Timeline active={running ? 1 : run ? 3 : 0} />
          <div className="notice"><ShieldCheck size={14} aria-hidden="true" /> Agents can retrieve and explain evidence. Deterministic services calculate heat and budget allocations; managers control approval.</div>
        </aside>
      </section>

      <section className="card" style={{ marginTop: 14 }}>
        <div className="card-head"><div><div className="card-title">What happens after you ask</div><div className="card-subtitle">A question creates a reviewable record, not an automatic decision</div></div><FileSearch size={19} aria-hidden="true" /></div>
        <div className="grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}>
          <div className="constraint"><span><strong>1. Gather</strong><br /><small>Retrieve organization-scoped evidence and prior results.</small></span></div>
          <div className="constraint"><span><strong>2. Explain</strong><br /><small>Show citations, preserved constraints, and open questions.</small></span></div>
          <div className="constraint"><span><strong>3. Review</strong><br /><small>Hand the recommendation to a manager for a recorded decision.</small></span></div>
        </div>
      </section>
    </AppShell>
  );
}
