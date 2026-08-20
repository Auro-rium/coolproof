# CoolProof backend

CoolProof is a governed backend for evidence-backed cooling-investment planning. This repository contains no browser application or public map UI.

## Phase 1

Phase 1 provides a FastAPI service foundation with tenant-aware authorization, auditability, health endpoints, uniform errors, and AWS deployment scaffolding. Later phases add FortyGuard intelligence, cited evidence retrieval and optimization, governed LangGraph workflows, and verification reporting.

## Local development

```bash
python3.12 -m venv .venv
. .venv/bin/activate
make install
make check
make run
```

The API should expose `GET /health/live` and `GET /health/ready`. Run `make smoke` against a running local instance, or set `COOLPROOF_API_URL` for a deployed service.

## Security boundary

Credentials are deployment-time secrets only. Do not commit keys, include them in HTTP responses, or emit them in logs/traces. Tenant-owned data is organization-scoped; authorization decisions and state-changing actions are audit logged.

See [operations guidance](docs/operations.md) for configuration and deployment checks.
