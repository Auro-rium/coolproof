"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  Activity,
  BarChart3,
  Calculator,
  ChevronRight,
  ClipboardCheck,
  LayoutDashboard,
  LogOut,
  MapPinned,
  PanelLeftClose,
  PanelLeftOpen,
  Sparkles,
} from "lucide-react";

type Session = {
  organization?: { name?: string };
  membership?: { role?: string };
  user?: { email?: string };
};

const navGroups = [
  {
    label: "Workspace",
    items: [
      { label: "Overview", href: "/portfolio", icon: LayoutDashboard },
      { label: "Projects & evidence", href: "/portfolio#projects", icon: MapPinned },
    ],
  },
  {
    label: "Decision cycle",
    items: [
      { label: "Optimize", href: "/optimize", icon: Calculator },
      { label: "Plans", href: "/plans", icon: ClipboardCheck },
      { label: "Verification", href: "/verify", icon: BarChart3 },
    ],
  },
  {
    label: "Assistant",
    items: [{ label: "Ask CoolProof", href: "/ask", icon: Sparkles }],
  },
] as const;

const mobileItems = [
  navGroups[0].items[0],
  navGroups[1].items[0],
  navGroups[1].items[1],
  navGroups[1].items[2],
  navGroups[2].items[0],
];

function initials(value: string) {
  const parts = value.split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? `${parts[0][0]}${parts[1][0]}` : value.slice(0, 2)).toUpperCase();
}

export function AppShell({ children, title = "Overview" }: { children: React.ReactNode; title?: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [apiState, setApiState] = useState<"checking" | "healthy" | "unavailable">("checking");
  const [session, setSession] = useState<Session | null>(null);
  const [identityState, setIdentityState] = useState<"checking" | "available" | "unavailable">("checking");
  const [hash, setHash] = useState("");

  useEffect(() => {
    const updateHash = () => setHash(window.location.hash);
    updateHash();
    window.addEventListener("hashchange", updateHash);
    return () => window.removeEventListener("hashchange", updateHash);
  }, [pathname]);

  useEffect(() => {
    let active = true;
    const health = fetch("/api/backend/health/ready", { cache: "no-store" })
      .then((response) => { if (active) setApiState(response.ok ? "healthy" : "unavailable"); })
      .catch(() => { if (active) setApiState("unavailable"); });
    const identity = fetch("/api/backend/api/v1/auth/session", { cache: "no-store" })
      .then(async (response) => {
        if (!active) return;
        if (response.ok) {
          setSession(await response.json() as Session);
          setIdentityState("available");
          return;
        }
        setSession(null);
        setIdentityState("unavailable");
        if (response.status === 401 || response.status === 403) {
          await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
          router.replace(`/login?returnTo=${encodeURIComponent(pathname)}`);
          router.refresh();
        }
      })
      .catch(() => { if (active) setIdentityState("unavailable"); });
    void Promise.all([health, identity]);
    return () => { active = false; };
  }, [pathname, router]);

  async function logout() {
    setBusy(true);
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  const isActive = (href: string) => {
    if (href === "/portfolio#projects") {
      return (pathname === "/portfolio" && hash === "#projects") || pathname.startsWith("/projects/") || pathname.startsWith("/zones/");
    }
    if (href === "/portfolio") return pathname === "/portfolio" && hash !== "#projects";
    const base = href.split("#")[0];
    return pathname === base || pathname.startsWith(`${base}/`);
  };
  const organization = session?.organization?.name?.trim() || null;
  const organizationLabel = organization ?? (identityState === "checking" ? "Checking workspace" : "Workspace unavailable");
  const role = session?.membership?.role?.trim() || (identityState === "checking" ? "Checking access" : "Identity unavailable");

  return (
    <div className={`app-shell ${collapsed ? "rail-collapsed" : ""}`}>
      <a className="skip" href="#main-content">Skip to content</a>
      <aside className="rail">
        <div className="rail-header">
          <Link href="/portfolio" className="brand" aria-label="CoolProof overview">
            <span className="brand-mark" aria-hidden="true"><Activity size={19} strokeWidth={2.4} /></span>
            <span className="brand-copy"><strong>CoolProof</strong><small>Climate decisions</small></span>
          </Link>
          <button className="rail-toggle" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}>
            {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </button>
        </div>

        <div className="org-switcher" role="group" aria-label="Current organization">
          <span className="org-avatar">{initials(organization ?? "CoolProof")}</span>
          <span className="org-copy"><small>Organization</small><strong>{organizationLabel}</strong></span>
        </div>

        <nav className="nav" aria-label="Main navigation">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-group-label">{group.label}</span>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = isActive(item.href);
                return <Link key={item.href} href={item.href} className={`nav-link ${active ? "active" : ""}`} aria-current={active ? "page" : undefined} title={collapsed ? item.label : undefined}>
                  <span className="nav-icon"><Icon size={18} strokeWidth={1.9} /></span>
                  <span className="nav-label">{item.label}</span>
                </Link>;
              })}
            </div>
          ))}
        </nav>

        <div className="rail-bottom">
          <div className={`system-chip ${apiState}`} role="status">
            <span className="status-dot" aria-hidden="true" />
            <span className="system-copy"><strong>{apiState === "checking" ? "Checking services" : apiState === "healthy" ? "All systems ready" : "Backend offline"}</strong><small>{apiState === "healthy" ? "Live data connected" : apiState === "checking" ? "One moment" : "Live actions unavailable"}</small></span>
          </div>
          <button className="user-chip" onClick={logout} disabled={busy} aria-label={busy ? "Signing out" : `Sign out${organization ? ` of ${organization}` : ""}`}>
            <span className="avatar">{initials(organization ?? "CoolProof")}</span>
            <span className="user-copy"><strong>{organizationLabel}</strong><small>{role}</small></span>
            <LogOut className="user-chevron" size={16} />
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><ChevronRight size={14} /><strong>{title}</strong></div>
          <div className="top-actions"><span className={`live-indicator ${apiState}`}><span className="dot" />{apiState === "healthy" ? "Live" : apiState === "checking" ? "Connecting" : "Offline"}</span><span className="top-project">{organizationLabel}</span></div>
        </header>
        <motion.main id="main-content" className="main-content" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}>
          {children}
        </motion.main>
      </div>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        {mobileItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.href);
          return <Link key={item.href} href={item.href} className={active ? "active" : ""} aria-current={active ? "page" : undefined}><Icon size={19} /><span>{item.label.split(" ")[0]}</span></Link>;
        })}
      </nav>
    </div>
  );
}
