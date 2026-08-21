import Link from "next/link";
import { AppShell } from "../../components/app-shell";

export default function PlansIndexPage() {
  return <AppShell title="Plans"><div className="page-head"><div><div className="eyebrow">GOVERNED WORKFLOW</div><h1>Plans</h1><p>A plan is created from a deterministic portfolio result, then reviewed by a manager before it can be approved.</p></div><Link href="/optimize" className="button primary">Start with optimizer →</Link></div><section className="card plans-empty"><div className="step-number">01</div><h2>No plan selected</h2><p>Run the optimizer to create a durable plan with evidence, agent checkpoints, citations, and an approval decision.</p><Link href="/optimize" className="button ghost">Open portfolio optimizer</Link></section></AppShell>;
}
