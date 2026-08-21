# CoolProof frontend plan — point 18

## Product boundary

The Vercel frontend is an authenticated operations console, not a chatbot. It
must make the evidence-to-decision workflow legible:

```text
Portfolio → Zone → Plan → Optimize → Verify
                         ↘ Ask CoolProof
```

The AWS FastAPI API remains the source of truth. The frontend never calculates
heat exposure, intervention impact, portfolio allocations, or verification
statistics locally.

## Route contract

| Route | Primary job | API dependencies |
|---|---|---|
| `/portfolio` | Budget, projects, exposure, recent impact | `GET /api/v1/projects`, `GET /api/v1/portfolio-runs` |
| `/zones/[zoneId]` | FortyGuard evidence and provenance | `GET /api/v1/projects/{id}/zones`, `POST /api/v1/heat-analyses`, `GET /api/v1/heat-analyses/{id}`, documents/retrieval |
| `/plans/[runId]` | Agent workflow, alternatives, approval | `POST/GET /api/v1/agent-runs`, approval transition endpoints |
| `/optimize` | Constraint editor and allocation result | `POST /api/v1/portfolio-runs`, `GET /api/v1/portfolio-runs/{id}` |
| `/verify/[reportId]` | Expected vs observed impact | `GET /api/v1/verifications`, `GET /api/v1/reports/{id}` |
| `/ask` | Bounded command interface | agent-run creation plus SSE events |

## App shell

Desktop uses a persistent left rail:

```text
CoolProof logo
Organization switcher
─────────────────
Portfolio
Zones
Plans
Optimize
Verify
─────────────────
Ask CoolProof
API / system status
User menu
```

Every page has a top context bar with organization, project/zone context,
request status, and a visible approval state. The mobile layout collapses the
rail into a bottom navigation and keeps the primary action sticky.

## Page UX

### Portfolio

- KPI cards: available budget, committed budget, exposed population, verified cooling.
- Projects table: project, zones, heat score, budget, current stage, verification result.
- Recent agent runs: five-step timeline with queued/running/succeeded/failed states.
- Primary action: `Start a plan`.
- Empty state: explain how to create a project and request heat evidence.

### Zone

- MapLibre map backed by the returned FortyGuard GeoJSON.
- Heat metric cards: mean temperature, exceedance, persistence, source timestamp.
- Evidence drawer: document title, page, excerpt, citation link, retrieval score.
- Explicit provider state: queued, processing, completed, stale, or retryable failure.
- Never show an inferred metric without a source/provenance badge.

### Plan

- Agent timeline: Heat → Evidence → Optimize → Govern → Verify.
- Main panel: recommendation, alternatives, tradeoffs, cited evidence.
- Right rail: budget, equity constraints, required/incompatible interventions.
- Approval footer: manager/admin identity, comment, approve/revise/reject.
- Rejection/revision returns to the relevant agent stage; it does not silently mutate the plan.

### Optimize

- Constraint form with server-side validation messages.
- Before/after budget summary.
- Allocation table with units, cost, benefit, uncertainty, and binding constraints.
- Solver status and duration are telemetry, not model claims.

### Verify

- Expected vs observed chart.
- Treatment/control comparison and weather adjustment explanation.
- Confidence interval, sample size, cost per degree, cost per exposure-hour.
- S3 report download with generated-at and data-window metadata.

### Ask CoolProof

This is a narrow command bar, not free-form chat. Examples:

> Reduce the budget to $750k while preserving school projects.

The UI renders explicit execution stages:

```text
Analyzing constraint
  ↓
Running optimizer
  ↓
Comparing portfolio
  ↓
Checking evidence
  ↓
Recommendation ready
```

The command cannot directly approve or commit a plan. A separate approval
transition is always required.

## Data and auth integration

- Vercel environment: `NEXT_PUBLIC_API_BASE_URL=https://3.15.34.25.sslip.io`.
- Cognito client-side login returns an ID token; store it in an HttpOnly secure session cookie through a Vercel server route, not localStorage.
- Every AWS request sends `Authorization: Bearer <id-token>` and `X-Organization-ID`.
- API errors are rendered from `error.code`, `error.message`, `error.retryable`, and `error.request_id`.
- Polling is used for heat analyses; SSE is used for agent-run events.
- Query cache keys include organization ID and resource ID to prevent cross-tenant stale data.
- Sign-out clears the session and all organization-scoped client cache.

## Deployment contract

1. Vercel builds the Next.js app from the frontend repository.
2. Preview deployments point to a non-production AWS API environment.
3. Production points to the current Caddy HTTPS endpoint.
4. CORS on FastAPI allowlists the Vercel production and preview domains explicitly.
5. Vercel health check calls `/health/ready` before showing the app as online.
6. CI runs TypeScript typecheck, ESLint, unit tests, Playwright smoke tests, and OpenAPI contract checks.
7. A deployment is accepted only after login → organization → project → zone → heat → optimize → approval is replayed against AWS.

## Build sequence

1. Create Next.js app shell, Cognito session, organization context, API client, and error boundary.
2. Build `/portfolio` and `/zones/[zoneId]` from the confirmed Superdesign shell.
3. Build `/plans/[runId]`, SSE event rendering, and approval controls.
4. Build `/optimize`, `/verify/[reportId]`, and report download.
5. Build `/ask` with bounded command parsing and visible execution stages.
6. Deploy to Vercel, configure AWS CORS/redirects, and run the full authenticated smoke test.

## Acceptance criteria

- A real Cognito user can sign in and see only the selected organization.
- A project and zone can be created from the UI and are visible after refresh.
- A FortyGuard analysis shows queued → processing → completed with source metadata.
- A cited intervention evidence panel links every recommendation to a document/page.
- The portfolio table exactly matches the OR-Tools API result.
- Approval is disabled for non-manager/admin roles and leaves an audit event.
- Verification shows expected vs observed values and downloads the S3 report.
- No secrets, source documents, raw prompts, completions, or stack traces appear in browser storage, URLs, logs, or telemetry.
