from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.phase3_models import Document, DocumentChunk, DocumentStatus

EMBEDDING_DIMENSIONS = 1536
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_CONTENT_TYPES = frozenset({"application/pdf", "text/plain", "text/markdown"})


@dataclass(frozen=True)
class SafeUpload:
    key: str
    sha256: str
    content_type: str


def extract_text_chunks(content: bytes, *, chunk_words: int = 180) -> list[tuple[int | None, str]]:
    """Extract text/markdown bytes into deterministic, page-aware chunks.

    PDF extraction is intentionally delegated to the deployment worker; this
    safe fallback handles uploaded text and keeps tests/offline operation useful.
    """
    if not content:
        return []
    # The API accepts PDFs and text, but never silently treats arbitrary binary
    # data as UTF-8.  A worker with a PDF extractor can replace this path later.
    if content.startswith(b"%PDF-"):
        try:
            import io

            from pypdf import PdfReader  # type: ignore[import-not-found]
            pages_text = [(index + 1, page.extract_text() or "") for index, page in enumerate(PdfReader(io.BytesIO(content)).pages)]
            pdf_chunks: list[tuple[int | None, str]] = []
            for page_number, page_text in pages_text:
                words = page_text.split()
                pdf_chunks.extend((page_number, " ".join(words[start : start + chunk_words])) for start in range(0, len(words), chunk_words) if words[start : start + chunk_words])
            return pdf_chunks
        except Exception as exc:
            raise ValueError("PDF extraction failed") from exc
    if b"\x00" in content[:8192]:
        raise ValueError("binary document content is not supported")
    try:
        text = content.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise ValueError("document must be valid UTF-8 text") from exc
    pages = text.split("\f")
    chunks: list[tuple[int | None, str]] = []
    for page_index, page in enumerate(pages, start=1):
        words = page.split()
        for start in range(0, len(words), chunk_words):
            value = " ".join(words[start : start + chunk_words]).strip()
            if value:
                chunks.append((page_index if len(pages) > 1 else None, value))
    return chunks


def embed_text(text: str, *, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Create a deterministic local embedding for offline and test operation.

    Production can replace this function with the configured embedding service;
    the persisted JSON shape is intentionally identical to a pgvector
    ``vector(1536)`` column, so the migration can change the physical type
    without changing the retrieval contract.
    """
    if dimensions < 8:
        raise ValueError("embedding dimensions must be at least eight")
    vector = [0.0] * dimensions
    for token in re.findall(r"[a-z0-9]+", text.casefold()):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = 1.0 if digest[8] & 1 else -1.0
        vector[index] += sign
    norm = sum(value * value for value in vector) ** 0.5
    return [value / norm for value in vector] if norm else vector


async def finalize_document(
    session: AsyncSession,
    document: Document,
    content: bytes,
) -> int:
    """Persist extracted chunks and atomically mark a document ready."""
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("document exceeds 25 MiB limit")
    if document.content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("unsupported document content type")
    if document.content_type == "application/pdf" and not content.startswith(b"%PDF-"):
        raise ValueError("PDF magic bytes are invalid")
    chunks = extract_text_chunks(content)
    await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    document.sha256 = hashlib.sha256(content).hexdigest()
    document.status = DocumentStatus.READY if chunks else DocumentStatus.FAILED
    if not chunks:
        document.metadata_json = {"error": "no_extractable_text", "version": document.version}
    for ordinal, (page_number, text) in enumerate(chunks):
        chunk_id = uuid4()
        session.add(
            DocumentChunk(
                id=chunk_id,
                organization_id=document.organization_id,
                document_id=document.id,
                ordinal=ordinal,
                page_number=page_number,
                text=text,
                lexical_text=text.casefold(),
                embedding=embed_text(text),
                metadata_json={"extractor": "text", "ordinal": ordinal},
            )
        )
        # Keep a native pgvector copy where the production migration is
        # installed; SQLite simply skips this optional physical projection.
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            vector_literal = "[" + ",".join(str(value) for value in embed_text(text)) + "]"
            await session.execute(
                sql_text("UPDATE document_chunks SET embedding_vector = CAST(:vector AS vector) WHERE id = :id"),
                {"vector": vector_literal, "id": chunk_id},
            )
    await session.commit()
    return len(chunks)


def create_presigned_put_url(
    *,
    bucket: str,
    key: str,
    content_type: str,
    expires_seconds: int = 900,
    s3_client: Any | None = None,
) -> str:
    """Create a bounded PUT URL. Credentials stay in the AWS SDK environment."""
    if not bucket:
        raise ValueError("documents bucket is required")
    if s3_client is None:
        import boto3

        s3_client = boto3.client("s3")
    return str(
        s3_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_seconds,
            HttpMethod="PUT",
        )
    )


def s3_object_key(organization_id: UUID, document_id: UUID, filename: str) -> str:
    safe_name = PurePosixPath(filename.replace("\\", "/")).name
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", safe_name)[:180] or "upload"
    return f"organizations/{organization_id}/documents/{document_id}/{safe_name}"


def prepare_upload(
    organization_id: UUID, document_id: UUID, filename: str, content: bytes, content_type: str
) -> SafeUpload:
    if not content:
        raise ValueError("document content cannot be empty")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("unsupported document content type")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("document exceeds 25 MiB limit")
    if content_type == "application/pdf" and not content.startswith(b"%PDF-"):
        raise ValueError("PDF magic bytes are invalid")
    return SafeUpload(
        s3_object_key(organization_id, document_id, filename),
        hashlib.sha256(content).hexdigest(),
        content_type,
    )
