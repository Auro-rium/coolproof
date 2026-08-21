export function MetricCard({ label, value, meta, tone = "ok" }: { label: string; value: string; meta: string; tone?: "ok" | "heat" | "blue" }) {
  return <article className="card"><div className="kpi-label">{label}</div><strong className="kpi-value">{value}</strong><div className={`kpi-meta ${tone === "heat" ? "" : ""}`}>{meta}</div></article>;
}
