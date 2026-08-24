const stages = ["Heat", "Evidence", "Optimize", "Govern", "Verify"];

/**
 * Lightweight workflow orientation for screens that do not have durable run
 * events. It deliberately does not label earlier stages as completed; confirmed
 * completion belongs on the governed run page where node.completed events exist.
 */
export function Timeline({ active = 0 }: { active?: number }) {
  return (
    <div className="timeline">
      {stages.map((stage, index) => {
        const current = active > 0 && index === active;
        const relative = index < active ? "earlier" : index > active ? "later" : "current";
        return (
          <div className="timeline-item" key={stage}>
            <span className={`stage-dot ${current ? "running" : ""}`}>{index + 1}</span>
            <div>
              <strong>{stage}</strong>
              <p>{active === 0 ? "Status appears after a governed run is created" : current ? "Current workflow focus" : `${relative === "earlier" ? "Earlier" : "Later"} workflow stage; open the run for confirmed events`}</p>
            </div>
            <span className={`badge ${current ? "warn" : ""}`}>{current ? "current" : "stage"}</span>
            {index < stages.length - 1 && <span className="timeline-line" />}
          </div>
        );
      })}
    </div>
  );
}
