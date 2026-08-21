# CoolProof frontend design system

## Product
CoolProof is an urban-cooling investment and verification console. It is not a chat app. The primary job is to help a city manager move from FortyGuard heat evidence to an approved, explainable portfolio and then verify delivery.

## Primary surfaces
- Portfolio: city budget, projects, exposure, active runs, impact summary.
- Zone: FortyGuard map evidence, exposure metrics, provenance and cited documents.
- Plan: visible five-stage agent workflow, alternatives, evidence, approval controls.
- Optimize: budget and equity constraints, deterministic allocation table, solver rationale.
- Verify: expected vs observed cooling, matched control, weather adjustment, report artifact.
- Ask CoolProof: narrow command bar for bounded changes such as reducing a budget while preserving school projects.

## Visual direction
Dark operational console with a clear evidence hierarchy. Preserve the current CoolProof identity: navy #08111f background, panel #101d2e, cyan #63e6d0 as primary action/signal, blue #79a9ff as secondary, warm orange #ffca7a/#ed7e68 only for heat intensity, ink #edf5ff, muted #8fa4bb, line #203149. Use Inter/system sans, 8px control radius, 12px card radius, thin borders, compact uppercase labels, restrained shadows, and accessible contrast. No chat bubbles, neon gradients, decorative illustrations, or invented brand marks.

## UX principles
1. Evidence before allocation: show source, timestamp, resolution and confidence beside every recommendation.
2. Agents are visible as a governed process timeline, not as a conversation transcript.
3. Deterministic outputs are visually distinct from model explanations.
4. Human approval is an explicit, high-friction state transition with reviewer role and audit timestamp.
5. Every async operation has queued/running/succeeded/failed states with retryable error copy and request ID.
6. Dense desktop console first, responsive tablet/mobile fallback second.
7. Keep the judge narrative one screen away: heat → evidence → optimize → approve → verify.

## Backend contract and state
API origin is a Vercel environment variable `NEXT_PUBLIC_API_BASE_URL`, pointing to the AWS Caddy endpoint. Authentication uses Cognito ID token; every tenant request sends `X-Organization-ID`. Core API routes are `/api/v1/projects`, `/api/v1/heat-analyses`, `/api/v1/documents`, `/api/v1/interventions`, `/api/v1/portfolio-runs`, `/api/v1/agent-runs`, `/api/v1/verifications`, and `/api/v1/reports`.

## Motion
Use short 150–220ms transitions for route/state changes. Async agent stages use a subtle cyan progress pulse; never animate metrics in a way that implies new evidence. Heat map changes use opacity fade, not bouncing markers.

## Responsive behavior
Desktop: persistent left navigation and split workspaces. Tablet: collapsible navigation. Mobile: stacked evidence/decision cards with bottom action bar; maps and allocation tables scroll horizontally.

## Fidelity constraint
Use only these fonts, colors, spacing, radii and component styles. Do not introduce unrelated visual styles.
