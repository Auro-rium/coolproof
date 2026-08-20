from uuid import uuid4

import pytest

from app.retrieval.documents import create_presigned_put_url, prepare_upload, s3_object_key
from app.retrieval.hybrid import hybrid_score


def test_document_key_is_tenant_bound_and_sanitized() -> None:
    key = s3_object_key(uuid4(), uuid4(), "../../private report.pdf")
    assert key.startswith("organizations/")
    assert ".." not in key
    assert key.endswith("private_report.pdf")


def test_prepare_upload_hashes_content() -> None:
    upload = prepare_upload(uuid4(), uuid4(), "a.txt", b"proof", "text/plain")
    assert len(upload.sha256) == 64


def test_hybrid_score_validates_weight() -> None:
    assert hybrid_score(lexical_rank=1, vector_similarity=0, lexical_weight=0.4) == 0.4
    with pytest.raises(ValueError):
        hybrid_score(lexical_rank=1, vector_similarity=0, lexical_weight=2)


def test_phase3_models_register_with_canonical_metadata() -> None:
    pytest.importorskip("sqlalchemy")
    from app.db import models  # noqa: F401
    from app.db.base import Base

    assert {"documents", "document_chunks", "interventions", "portfolio_runs"} <= set(
        Base.metadata.tables
    )


def test_presigned_upload_binds_bucket_key_and_content_type() -> None:
    class Client:
        def generate_presigned_url(self, operation: str, **kwargs: object) -> str:
            assert operation == "put_object"
            assert kwargs["Params"] == {
                "Bucket": "docs",
                "Key": "tenant/key",
                "ContentType": "text/plain",
            }
            return "https://upload.example"

    assert (
        create_presigned_put_url(
            bucket="docs", key="tenant/key", content_type="text/plain", s3_client=Client()
        )
        == "https://upload.example"
    )
