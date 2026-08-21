# Sections 19–20: judge demo and frozen architecture

The public demo follows the intended narrative:

1. FortyGuard supplies hyperlocal heat evidence.
2. Tenant-isolated retrieval returns cited intervention evidence.
3. OR-Tools calculates a budget/equity-constrained portfolio.
4. Four governed agents explain the result and wait for manager approval.
5. Verification compares treatment and matched-control observations with weather adjustment.

`GET /demo/manifest` exposes this workflow and the non-secret provider configuration state. It is deliberately limited to architecture and capability metadata; it never returns prompts, completions, uploaded source text, credentials, or stack traces.

The deployment is frozen as FastAPI + LangGraph + PostgreSQL/pgvector + Redis + S3 + Cognito on EC2/Docker Compose behind Caddy, with OpenTelemetry, Prometheus, Grafana, and CloudWatch operational tooling. The bundled `frontend/` is a small backend demo surface for the hackathon deployment; the API remains the source of truth.
