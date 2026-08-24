"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { ArrowRight, Check, ChevronRight, Layers3, MapPinned, ShieldCheck, Sparkles, TrendingDown } from "lucide-react";

const reveal = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0 },
};

const steps = [
  { number: "01", icon: MapPinned, title: "See the pressure points", copy: "Understand where heat exposure is concentrated and which communities carry the greatest burden." },
  { number: "02", icon: Layers3, title: "Compare credible actions", copy: "Review interventions against budget, feasibility, equity, and the evidence behind each choice." },
  { number: "03", icon: ShieldCheck, title: "Move with accountability", copy: "Keep recommendations, approvals, and measured outcomes connected from planning through verification." },
];

export default function Home() {
  return (
    <main className="landing-shell">
      <nav className="landing-nav" aria-label="Public navigation">
        <Link href="/" className="landing-brand"><span className="landing-logo"><TrendingDown size={18} /></span><span>CoolProof</span></Link>
        <div className="landing-links"><a href="#product">Product</a><a href="#method">How it works</a><a href="#trust">Why teams trust it</a></div>
        <Link href="/login" className="button landing-signin">Sign in <ArrowRight size={15} /></Link>
      </nav>

      <section className="landing-hero">
        <motion.div className="landing-copy" initial="hidden" animate="visible" variants={reveal} transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}>
          <span className="landing-kicker"><Sparkles size={14} /> Cooling decisions, made clear</span>
          <h1>Turn urban heat into a plan people can stand behind.</h1>
          <p className="landing-lede">CoolProof gives climate teams one place to understand exposure, compare interventions, allocate a budget, and prove what changed.</p>
          <div className="landing-actions"><Link href="/login" className="button primary landing-cta">Open your workspace <ArrowRight size={16} /></Link><a href="#product" className="button landing-secondary">See the product</a></div>
          <div className="landing-proof"><span><Check size={14} /> Evidence stays attached</span><span><Check size={14} /> Constraints stay visible</span><span><Check size={14} /> Approval stays human</span></div>
        </motion.div>

        <motion.div className="product-preview" initial={{ opacity: 0, scale: 0.96, y: 24 }} animate={{ opacity: 1, scale: 1, y: 0 }} transition={{ duration: 0.65, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}>
          <div className="preview-toolbar"><span className="preview-brand"><TrendingDown size={14} /> CoolProof</span><span className="preview-badge"><i /> Illustrative workspace</span></div>
          <div className="preview-body">
            <div className="preview-sidebar"><span className="preview-nav active" /><span className="preview-nav" /><span className="preview-nav short" /><span className="preview-nav" /></div>
            <div className="preview-content">
              <div className="preview-heading"><div><small>PHOENIX COOLING PORTFOLIO</small><strong>Where should the next dollar go?</strong></div><span>Ready to compare</span></div>
              <div className="preview-grid">
                <div className="heat-map"><span className="heat-grid" /><span className="heat-spot one" /><span className="heat-spot two" /><span className="heat-spot three" /><span className="heat-label label-one">41.8°</span><span className="heat-label label-two">38.6°</span><div className="map-note"><small>PRIORITY AREA</small><strong>School corridor</strong></div></div>
                <div className="preview-panel"><small>RECOMMENDED MIX</small><div className="mix-row"><span className="mix-icon trees">T</span><div><strong>Shade trees</strong><small>2 priority zones</small></div><b>$50k</b></div><div className="mix-row"><span className="mix-icon paving">P</span><div><strong>Cool pavement</strong><small>1 civic corridor</small></div><b>$60k</b></div><div className="budget-bar"><span style={{ width: "72%" }} /></div><div className="budget-copy"><span>Portfolio budget</span><strong>$110k / $150k</strong></div><button type="button">Review recommendation <ChevronRight size={13} /></button></div>
              </div>
            </div>
          </div>
        </motion.div>
      </section>

      <section id="product" className="landing-value">
        <motion.div className="value-intro" initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.35 }} variants={reveal} transition={{ duration: 0.45 }}><span className="eyebrow">A SHARED DECISION SPACE</span><h2>Replace the spreadsheet handoff with one continuous workflow.</h2></motion.div>
        <div className="value-grid"><div><strong>Heat intelligence</strong><p>Move from citywide signal to a specific neighborhood and retain the source behind the measurement.</p></div><div><strong>Portfolio decisions</strong><p>Compare interventions against the constraints your team actually works with—not a generic score.</p></div><div><strong>Measured outcomes</strong><p>Carry the approved plan forward so expected and observed cooling can be reviewed together.</p></div></div>
      </section>

      <section id="method" className="landing-method"><div className="method-heading"><span className="eyebrow">HOW IT WORKS</span><h2>From the heat signal to a measurable outcome.</h2><p>Each step keeps the decision grounded and reviewable.</p></div><div className="method-list">{steps.map((step, index) => { const Icon = step.icon; return <motion.article key={step.number} initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.35 }} variants={reveal} transition={{ delay: index * 0.08, duration: 0.4 }}><span className="method-number">{step.number}</span><span className="method-icon"><Icon size={20} /></span><div><h3>{step.title}</h3><p>{step.copy}</p></div></motion.article>; })}</div></section>

      <section id="trust" className="landing-trust"><span className="eyebrow">BUILT FOR TRUST</span><h2>A recommendation should show its work.</h2><div className="trust-grid"><div><small>01</small><strong>Traceable evidence</strong><p>Sources and citations follow the recommendation.</p></div><div><small>02</small><strong>Visible constraints</strong><p>Budget, equity, capacity, and uncertainty remain inspectable.</p></div><div><small>03</small><strong>Human control</strong><p>Managers approve, reject, or request revision.</p></div><div><small>04</small><strong>Outcome verification</strong><p>Expected and observed results stay connected.</p></div></div></section>

      <section className="landing-close"><div><span className="eyebrow">COOLPROOF</span><h2>Make the next cooling decision with the whole picture in view.</h2></div><Link href="/login" className="button primary landing-cta">Enter the workspace <ArrowRight size={16} /></Link></section>
      <footer className="landing-footer"><Link href="/" className="landing-brand"><span className="landing-logo"><TrendingDown size={16} /></span><span>CoolProof</span></Link><span>Cooling decisions with a clear chain of evidence.</span><Link href="/login">Sign in</Link></footer>
    </main>
  );
}
