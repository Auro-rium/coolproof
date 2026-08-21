import Link from "next/link";

const steps = [
  ["01", "Read the heat", "Connect a supported zone to live FortyGuard evidence with a durable activity record."],
  ["02", "Build the case", "Retrieve cited intervention evidence and keep source provenance beside every recommendation."],
  ["03", "Govern the decision", "Run deterministic portfolio optimization, then route the result through manager approval."],
];

export default function Home() {
  return <main className="landing-shell">
    <nav className="landing-nav"><Link href="/" className="landing-brand"><span className="brand-mark">✦</span> CoolProof <span className="brand-beta">OPS</span></Link><div className="landing-links"><a href="#how-it-works">How it works</a><a href="#boundaries">Trust boundary</a><Link href="/login" className="button ghost">Sign in</Link></div></nav>
    <section className="landing-hero"><div className="landing-eyebrow">EVIDENCE-LED CLIMATE OPERATIONS</div><h1>Turn urban heat evidence into decisions your team can defend.</h1><p className="landing-lede">CoolProof connects live heat intelligence, cited intervention research, deterministic portfolio optimization, and governed approval in one tenant-scoped workspace.</p><div className="landing-actions"><Link href="/login" className="button primary">Open operations console <span aria-hidden="true">→</span></Link><a href="https://3.15.34.25.sslip.io/docs" className="button ghost">View API contract</a></div><div className="landing-proof"><span className="proof-dot" /> AWS-backed · Cognito protected · OR-Tools authoritative</div></section>
    <section className="landing-signal"><div><span className="eyebrow">THE OPERATING MODEL</span><h2>Evidence first. Calculation stays deterministic. Approval stays human.</h2></div><p>Agents orchestrate the workflow and explain outputs. They do not invent heat measurements or alter allocations.</p></section>
    <section id="how-it-works" className="landing-section"><div className="eyebrow">HOW IT WORKS</div><h2>One path from signal to proof.</h2><div className="landing-steps">{steps.map(([number, title, copy]) => <article className="landing-step" key={number}><span className="step-number">{number}</span><h3>{title}</h3><p>{copy}</p></article>)}</div></section>
    <section id="boundaries" className="landing-section landing-boundary"><div><div className="eyebrow">TRUST BOUNDARY</div><h2>The UI shows the work. AWS owns the facts.</h2></div><div className="boundary-list"><div><strong>FortyGuard</strong><span>Provider heat evidence and activity state</span></div><div><strong>PostgreSQL + pgvector</strong><span>Tenant-isolated sources and citations</span></div><div><strong>OR-Tools</strong><span>Budget, equity, capacity, and uncertainty constraints</span></div><div><strong>LangGraph</strong><span>Checkpointed four-agent workflow with approval gates</span></div></div></section>
    <footer className="landing-footer"><span>CoolProof · Aurorium Nexus Cooling</span><span>Built for auditable urban-cooling decisions.</span></footer>
  </main>;
}
