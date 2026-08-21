const stages = ["Heat", "Evidence", "Optimize", "Govern", "Verify"];
export function Timeline({ active = 2 }: { active?: number }) {
  return <div className="timeline">{stages.map((stage, index) => <div className="timeline-item" key={stage}><span className={`stage-dot ${index < active ? "done" : index === active ? "running" : ""}`}>{index < active ? "✓" : index + 1}</span><div><strong>{stage}</strong><p>{index < active ? "Completed with recorded evidence" : index === active ? "Running deterministic workflow" : "Awaiting prior stage"}</p></div><span className={`badge ${index < active ? "ok" : index === active ? "warn" : ""}`}>{index < active ? "done" : index === active ? "running" : "queued"}</span>{index < stages.length - 1 && <span className="timeline-line" />}</div>)}</div>;
}
