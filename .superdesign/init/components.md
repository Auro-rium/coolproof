# CoolProof UI components

The current frontend is a dependency-free static HTML/CSS/JavaScript surface.
There is no React/Next.js component library yet. Reusable primitives currently
exist as CSS classes in `frontend/styles.css`.

## Status card
Source: `frontend/index.html`
Description: Live API/readiness/telemetry status card.

```html
<article class="status-card"><div class="card-top"><span class="dot pending" id="live-dot"></span><span>API liveness</span><span class="status-label" id="live-status">checking</span></div><strong id="live-value">—</strong><small>Public edge response</small></article>
```

## Workflow step
Source: `frontend/index.html`
Description: Five-stage operating-loop tile.

```html
<div class="step"><span>01</span><h3>Heat</h3><p>Asynchronous hyperlocal temperature evidence from FortyGuard.</p></div>
```
