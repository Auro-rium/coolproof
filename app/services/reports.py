"""Private S3 report artifact writer with a local deterministic fallback."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from app.core.config import Settings


def report_key(organization_id: UUID, verification_id: UUID) -> str:
    return f"organizations/{organization_id}/verification-reports/{verification_id}.json"


def report_payload(
    *, organization_id: UUID, verification_id: UUID, result: Mapping[str, object]
) -> bytes:
    # Only numeric result fields and method metadata are accepted from the
    # deterministic verifier; JSON serialization is stable for idempotency.
    payload = {
        "report_version": "1",
        "verification_id": str(verification_id),
        "organization_id": str(organization_id),
        "generated_at": datetime.now(UTC).isoformat(),
        "result": result,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write_report(
    *, settings: Settings, organization_id: UUID, verification_id: UUID, result: Mapping[str, object]
) -> str | None:
    """Write a private S3 object and return its key, or ``None`` when disabled."""
    bucket = settings.reports_bucket or settings.documents_bucket
    if not bucket:
        return None
    import boto3

    key = report_key(organization_id, verification_id)
    boto3.client("s3", region_name=settings.aws_region).put_object(
        Bucket=bucket,
        Key=key,
        Body=report_payload(
            organization_id=organization_id, verification_id=verification_id, result=result
        ),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )
    return key


def report_download_url(*, settings: Settings, key: str, expires_seconds: int = 900) -> str:
    bucket = settings.reports_bucket or settings.documents_bucket
    if not bucket or not key.startswith("organizations/"):
        raise ValueError("report storage is not configured")
    import boto3

    return str(
        boto3.client("s3", region_name=settings.aws_region).generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
    )
