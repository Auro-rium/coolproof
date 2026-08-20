# CoolProof Phase 1 Operations

## Required runtime configuration

Runtime configuration is supplied by AWS Secrets Manager or deployment environment variables. Do not commit values for any credential.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Async PostgreSQL connection string for RDS. |
| `REDIS_URL` | ElastiCache Redis connection string. |
| `COGNITO_REGION` | AWS region containing the Cognito user pool. |
| `COGNITO_USER_POOL_ID` | Cognito user-pool identifier. |
| `COGNITO_APP_CLIENT_ID` | Cognito application client identifier. |
| `AWS_REGION` | AWS deployment region (`us-east-2`). |
| `S3_ARTIFACT_BUCKET` | Private S3 bucket for artifacts. |

FortyGuard, Backboard, and NVIDIA credentials are introduced in later phases and must only be injected at runtime.

## Deployment check

After Docker Compose is running on the EC2 host, run:

```bash
COOLPROOF_API_URL=https://api.example ./scripts/smoke-api.sh
```

`/health/live` proves that the API process can serve requests. `/health/ready` must also prove that required dependencies are reachable before traffic is accepted.

## Incident handling

1. Inspect CloudWatch service logs and metrics using the request ID; never paste credentials, prompts, completions, or uploaded source content into tickets.
2. If readiness fails, verify RDS/Redis security groups, secret injection, and database migrations before restarting workloads.
3. If liveness fails, roll back to the last known-good image and preserve structured logs for investigation.

## Phase 5 verification runbook

Verification is a deterministic matched-control, weather-adjusted
difference-in-differences calculation.  Operators provide treated/control
baseline and observed temperatures plus the weather deltas for the same
windows.  The API stores the numeric result under the organization tenant and
uses an idempotency hash, so a retried request cannot create a second run.

Create a run with `POST /api/v1/verifications` using an authenticated analyst,
manager, or admin and the `X-Organization-ID` header.  A successful response
contains `cooling_effect`, `expected_cooling`, `expected_minus_observed`,
`attainment_ratio`, and `met_expectation`.  A report can be materialized with
`POST /api/v1/verifications/{id}/report`; it is encrypted at rest in the
configured private S3 bucket and is returned as a short-lived presigned URL.

If S3 is temporarily unavailable, the calculation remains durable and the
response has a null `report_key`.  Retry the report endpoint after restoring
the instance role/bucket access.  Never place observations, uploaded source,
API keys, prompts, or completions in logs or incident tickets.  The telemetry
helpers only emit event labels, statuses, durations, counts, and redacted
field lengths.
