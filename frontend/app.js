const checks = [
  { key: "live", url: "/health/live", dot: "live-dot", status: "live-status", value: "live-value", ok: (body) => body.status === "ok", label: "online" },
  { key: "ready", url: "/health/ready", dot: "ready-dot", status: "ready-status", value: "ready-value", ok: (body) => body.status === "healthy", label: "ready" },
  { key: "metrics", url: "/metrics", dot: "metrics-dot", status: "metrics-status", value: "metrics-value", ok: (body) => body.includes("coolproof_http_requests_total"), label: "streaming" },
];

async function check(item) {
  const dot = document.getElementById(item.dot); const status = document.getElementById(item.status); const value = document.getElementById(item.value);
  try {
    const response = await fetch(item.url, { cache: "no-store" });
    const body = item.key === "metrics" ? await response.text() : await response.json();
    const good = response.ok && item.ok(body);
    dot.classList.toggle("pending", false); dot.classList.toggle("bad", !good); status.textContent = good ? item.label : "attention"; value.textContent = good ? "200 OK" : `${response.status} response`;
  } catch { dot.classList.remove("pending"); dot.classList.add("bad"); status.textContent = "offline"; value.textContent = "unreachable"; }
}
checks.forEach(check);
