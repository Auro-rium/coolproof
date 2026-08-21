import Link from "next/link";
import { AppShell } from "../../components/app-shell";

export default function VerifyIndexPage() {
  return <AppShell title="Verify"><div className="page-head"><div><div className="eyebrow">MEASURED OUTCOMES</div><h1>Verification</h1><p>Verification compares expected versus observed cooling using weather-adjusted matched controls.</p></div><Link href="/optimize" className="button ghost">Return to optimizer</Link></div><section className="card plans-empty"><div className="step-number">02</div><h2>No verification report selected</h2><p>Complete a governed plan first. A verification report is created from a persisted portfolio run and its observed outcomes.</p></section></AppShell>;
}
