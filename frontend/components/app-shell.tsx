"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const nav = [
  ["◈", "Portfolio", "/portfolio", "Decision overview"],
  ["⌖", "Zones", "/zones/demo", "Heat evidence"],
  ["◌", "Plans", "/plans/demo", "Governed workflow"],
  ["◇", "Optimize", "/optimize", "Deterministic allocation"],
  ["◫", "Verify", "/verify/demo", "Measured outcomes"],
  ["⌁", "Ask CoolProof", "/ask", "Bounded commands"],
];

export function AppShell({ children, title = "Portfolio" }: { children: React.ReactNode; title?: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [apiState, setApiState] = useState<"checking" | "healthy" | "unavailable">("checking");
  useEffect(() => {
    let active = true;
    fetch("/api/backend/health/ready", { cache: "no-store" })
      .then((response) => { if (active) setApiState(response.ok ? "healthy" : "unavailable"); })
      .catch(() => { if (active) setApiState("unavailable"); });
    return () => { active = false; };
  }, []);
  async function logout() {
    setBusy(true);
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }
  const isActive = (href: string) => href === "/portfolio"
    ? pathname === href
    : pathname === href || pathname.startsWith(`/${href.split("/")[1]}/`);
  return <div className="app-shell">
    <a className="skip" href="#main-content">Skip to content</a>
    <aside className="rail">
      <Link href="/portfolio" className="brand"><span className="brand-mark" aria-hidden="true">✦</span><span>CoolProof</span><span className="brand-beta">OPS</span></Link>
      <div className="org-switcher" aria-label="Current organization"><div className="eyebrow">Organization</div><strong>Aurorium Nexus Cooling</strong><div className="muted org-meta">Production · us-east-2</div></div>
      <nav className="nav" aria-label="Main navigation">{nav.map(([icon, label, href, description]) => <Link key={href} href={href} className={`nav-link ${isActive(href) ? "active" : ""}`} aria-current={isActive(href) ? "page" : undefined} title={description}><span className="nav-icon" aria-hidden="true">{icon}</span><span className="nav-label">{label}</span>{isActive(href) && <span className="nav-current" aria-hidden="true" />}</Link>)}</nav>
      <div className="rail-bottom"><div className="system-chip" role="status"><span aria-hidden="true" className={apiState === "unavailable" ? "status-dot down" : "status-dot"} /> <span>{apiState === "checking" ? "Checking API…" : apiState === "healthy" ? "API healthy" : "API unavailable"}</span><small>{apiState === "healthy" ? "AWS readiness confirmed" : apiState === "checking" ? "connecting to AWS" : "retry or contact an admin"}</small></div><button className="user-chip" onClick={logout} disabled={busy} aria-label={busy ? "Signing out" : "Sign out Aurorium Nexus"}><span className="avatar" aria-hidden="true">AN</span><span>{busy ? "Signing out…" : "Aurorium Nexus"}</span><span className="user-chevron" aria-hidden="true">↗</span></button></div>
    </aside>
    <div className="main"><header className="topbar"><div className="breadcrumb"><span>CoolProof</span><span className="breadcrumb-separator" aria-hidden="true">/</span><strong>{title}</strong></div><div className="top-actions"><span className="live-indicator"><span className="dot" /> AWS CONNECTED</span><span className="top-project">Aurorium Nexus Cooling</span></div></header><main id="main-content" className="main-content">{children}</main></div>
    <nav className="mobile-nav" aria-label="Mobile navigation">{nav.map(([icon, label, href]) => <Link key={href} href={href} className={isActive(href) ? "active" : ""} aria-current={isActive(href) ? "page" : undefined}><span aria-hidden="true">{icon}</span><span>{label.split(" ")[0]}</span></Link>)}</nav>
  </div>;
}
