"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, Eye, EyeOff, ShieldCheck, TrendingDown } from "lucide-react";
import { defaultOrganizationId } from "../../lib/config";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationId, setOrganizationId] = useState(defaultOrganizationId);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function safeReturnPath() {
    const requested = new URLSearchParams(window.location.search).get("returnTo");
    if (!requested || !requested.startsWith("/") || requested.startsWith("//")) return "/portfolio";
    try {
      const destination = new URL(requested, window.location.origin);
      if (destination.origin !== window.location.origin) return "/portfolio";
      return `${destination.pathname}${destination.search}${destination.hash}`;
    } catch {
      return "/portfolio";
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, organizationId }),
      });
      const body = await response.json().catch(() => ({})) as { error?: string };
      if (!response.ok) setError(body.error ?? "We could not sign you in. Check your details and try again.");
      else router.push(safeReturnPath());
    } catch {
      setError("The sign-in service is unavailable. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-story">
        <Link href="/" className="landing-brand"><span className="landing-logo"><TrendingDown size={18} /></span><span>CoolProof</span></Link>
        <div className="login-story-copy"><span className="eyebrow">YOUR COOLING WORKSPACE</span><h1>Bring the evidence into the room where decisions happen.</h1><p>Review heat exposure, compare interventions, govern the recommendation, and keep the outcome connected.</p><ul><li><Check size={16} /> Evidence-led recommendations</li><li><Check size={16} /> Tenant-scoped access</li><li><Check size={16} /> Manager-controlled approvals</li></ul></div>
        <div className="login-story-foot"><ShieldCheck size={17} /><span>Secure organization access</span></div>
      </section>

      <section className="login-panel">
        <Link href="/" className="login-back"><ArrowLeft size={15} /> Back to CoolProof</Link>
        <div className="login-card">
          <div className="login-heading"><span className="eyebrow">WELCOME BACK</span><h2>Sign in to your workspace</h2><p>Use the email and organization ID provided by your administrator.</p></div>
          <form className="login-form" onSubmit={submit}>
            <div className="field"><label htmlFor="email">Work email</label><input id="email" name="email" autoComplete="username" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@organization.org" required /></div>
            <div className="field"><label htmlFor="password">Password</label><div className="password-field"><input id="password" name="password" autoComplete="current-password" type={showPassword ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" required /><button type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></div>
            <div className="field"><label htmlFor="organization">Organization ID</label><input id="organization" name="organization" autoComplete="organization" value={organizationId} onChange={(event) => setOrganizationId(event.target.value)} required /><small>Your tenant ID keeps workspace data isolated.</small></div>
            {error ? <div className="error" role="alert">{error}</div> : null}
            <button className="button primary login-submit" disabled={busy}>{busy ? "Checking your access…" : <>Continue to workspace <ArrowRight size={16} /></>}</button>
          </form>
          <p className="login-support">Need access? Contact your CoolProof organization administrator.</p>
        </div>
      </section>
    </main>
  );
}
