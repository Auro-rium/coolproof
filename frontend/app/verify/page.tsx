"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useState } from "react";
import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ClipboardList,
  CloudSun,
  FileCheck2,
  FileSearch,
  GitCompareArrows,
  Search,
  ShieldCheck,
} from "lucide-react";
import { AppShell } from "../../components/app-shell";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export default function VerifyIndexPage() {
  const router = useRouter();
  const [reportId, setReportId] = useState("");
  const [validationError, setValidationError] = useState("");

  function openReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = reportId.trim();
    if (!UUID_PATTERN.test(normalized)) {
      setValidationError("Enter the complete verification ID returned when the report was created.");
      return;
    }
    setValidationError("");
    router.push(`/verify/${encodeURIComponent(normalized)}`);
  }

  return (
    <AppShell title="Verification">
      <header className="page-head">
        <div>
          <span className="eyebrow">OBSERVED OUTCOMES</span>
          <h1>Measure what changed</h1>
          <p>Compare expected cooling with weather-adjusted observations and matched controls—without overstating causality.</p>
        </div>
        <span className="badge ok"><ShieldCheck size={14} /> Evidence boundary enforced</span>
      </header>

      <section className="grid two-col">
        <article className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">OPEN A REPORT</span>
              <h2>Return to a measured outcome</h2>
              <p>Use the verification ID created from persisted observations.</p>
            </div>
            <span className="badge"><FileSearch size={13} /> Report lookup</span>
          </div>

          <form onSubmit={openReport} noValidate>
            <div className="field">
              <label htmlFor="verification-report-id">Verification ID</label>
              <input
                id="verification-report-id"
                name="verification-report-id"
                value={reportId}
                onChange={(event) => {
                  setReportId(event.target.value);
                  if (validationError) setValidationError("");
                }}
                placeholder="00000000-0000-0000-0000-000000000000"
                autoComplete="off"
                spellCheck={false}
                aria-describedby="verification-id-help"
                aria-invalid={Boolean(validationError)}
              />
              <small id="verification-id-help" className="muted">This ID links to the tenant-scoped calculation and its report artifact.</small>
            </div>
            {validationError ? <div className="error" role="alert" style={{ marginTop: 12 }}>{validationError}</div> : null}
            <div className="top-actions" style={{ marginTop: 14 }}>
              <button className="button primary" type="submit"><Search size={15} /> Open report</button>
              <Link className="button ghost" href="/plans"><ClipboardList size={15} /> Review plans</Link>
            </div>
          </form>

          <div className="empty" style={{ marginTop: 20 }}>
            No report is selected. CoolProof only presents persisted verification results—not illustrative outcome numbers.
          </div>
        </article>

        <aside className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">CLAIM BOUNDARY</span>
              <h2>What the report can say</h2>
              <p>Observed treatment effects are separated from unsupported causal claims.</p>
            </div>
            <BarChart3 size={21} aria-hidden="true" />
          </div>
          <div className="constraint-list">
            <div className="constraint">
              <span><CloudSun size={16} aria-hidden="true" /> Weather-adjusted temperature change</span>
              <span className="badge ok">Measured</span>
            </div>
            <div className="constraint">
              <span><GitCompareArrows size={16} aria-hidden="true" /> Treated area versus matched control</span>
              <span className="badge ok">Compared</span>
            </div>
            <div className="constraint">
              <span><FileCheck2 size={16} aria-hidden="true" /> Expected versus observed outcome</span>
              <span className="badge">Reported</span>
            </div>
          </div>
          <div className="notice" style={{ marginTop: 18 }}>
            A verification report describes the observed effect under its stated method. It does not claim that a single intervention caused an exact change without an experimental design.
          </div>
        </aside>
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <div className="card-head">
          <div>
            <span className="eyebrow">VERIFICATION METHOD</span>
            <h2>From field observations to an accountable result</h2>
            <p>The backend calculates the outcome; the interface presents the method and provenance.</p>
          </div>
          <span className="badge ok"><CheckCircle2 size={13} /> Deterministic</span>
        </div>
        <div className="grid kpis" style={{ marginBottom: 0 }}>
          <div><span className="step-number">01</span><h3>Record</h3><p className="muted">Persist baseline and observed measurements for treatment and control areas.</p></div>
          <div><span className="step-number">02</span><h3>Adjust</h3><p className="muted">Account for weather deltas before comparing the two areas.</p></div>
          <div><span className="step-number">03</span><h3>Compare</h3><p className="muted">Calculate the matched-control effect and target attainment.</p></div>
          <div><span className="step-number">04</span><h3>Report</h3><p className="muted">Materialize a tenant-scoped report artifact with the calculation result.</p></div>
        </div>
        <div className="top-actions" style={{ marginTop: 20 }}>
          <Link className="button primary" href="/plans">Review an approved plan <ArrowRight size={15} /></Link>
          <Link className="button ghost" href="/portfolio"><ClipboardList size={15} /> Return to workspace</Link>
        </div>
      </section>
    </AppShell>
  );
}
