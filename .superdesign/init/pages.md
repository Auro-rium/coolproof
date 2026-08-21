# CoolProof pages

## `/` public demo

Entry: `frontend/index.html`

Dependencies:

- `frontend/styles.css`
- `frontend/app.js`
  - `/health/live`
  - `/health/ready`
  - `/metrics`

## Planned authenticated product surfaces

These do not yet render in the current static frontend and must be designed as
a connected Vercel application against the existing FastAPI OpenAPI contract:

- `/portfolio`: project selector, budget summary, impact cards, recent runs
- `/zones/:zoneId`: map/evidence panel, heat metrics, source provenance
- `/plans/:runId`: four-agent timeline, alternatives, approval controls
- `/optimize`: constraint editor, allocation table, solver explanation
- `/verify/:reportId`: expected/observed comparison and report download
- `/ask`: constrained command composer with visible execution steps
