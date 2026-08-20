"""Tenant-filtered hybrid retrieval contract.

Production adapters execute lexical ranking (tsvector) and pgvector cosine
ranking in PostgreSQL. This module deliberately contains no cross-tenant query.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy import text as sql_text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.phase3_models import Document, DocumentChunk, DocumentStatus


@dataclass(frozen=True)
class Citation:
    document_id: UUID
    chunk_id: UUID
    filename: str
    page_number: int | None
    excerpt: str
    score: float


@dataclass(frozen=True)
class RetrievalQuery:
    organization_id: UUID
    text: str
    embedding: tuple[float, ...] | None = None
    limit: int = 8
    project_id: UUID | None = None


def hybrid_score(
    *, lexical_rank: float, vector_similarity: float, lexical_weight: float = 0.4
) -> float:
    if not 0 <= lexical_weight <= 1:
        raise ValueError("lexical_weight must be between zero and one")
    return lexical_weight * lexical_rank + (1 - lexical_weight) * vector_similarity


class HybridRetriever:
    """Tenant-scoped lexical/vector-compatible retrieval.

    SQLite uses token overlap and JSON embeddings; PostgreSQL deployments can
    replace this query with ``pgvector`` cosine distance without changing the
    citation contract.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def search(self, query: RetrievalQuery) -> list[Citation]:
        if not query.text.strip():
            return []
        statement = (
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.organization_id == query.organization_id,
                Document.organization_id == query.organization_id,
                Document.status == DocumentStatus.READY,
            )
        )
        if query.project_id is not None:
            statement = statement.where(Document.project_id == query.project_id)
        # PostgreSQL performs lexical candidate selection in the database.  A
        # missing pgvector column (older rollout) transparently falls back to
        # the portable JSON/token implementation below.
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            try:
                embedding = list(query.embedding or ())
                vector_literal = "[" + ",".join(str(float(value)) for value in embedding) + "]"
                project_clause = "AND d.project_id = :project_id" if query.project_id else ""
                pg_rows = await self.session.execute(
                    sql_text(
                        f"""SELECT dc.id AS chunk_id, d.id AS document_id, d.filename,
                        dc.page_number, dc.text,
                        (0.4 * ts_rank_cd(to_tsvector('simple', dc.lexical_text), plainto_tsquery('simple', :query))
                         + 0.6 * (1 - (dc.embedding_vector <=> CAST(:embedding AS vector)))) AS score
                        FROM document_chunks dc JOIN documents d ON d.id = dc.document_id
                        WHERE dc.organization_id = :organization_id AND d.organization_id = :organization_id
                          AND d.status = 'ready' AND dc.embedding_vector IS NOT NULL {project_clause}
                        ORDER BY score DESC LIMIT :limit"""
                    ),
                    {"query": query.text, "embedding": vector_literal,
                     "organization_id": str(query.organization_id),
                     "project_id": str(query.project_id) if query.project_id else None,
                     "limit": max(1, query.limit)},
                )
                rows_with_rank = pg_rows.mappings().all()
                if rows_with_rank:
                    return [
                        Citation(row["document_id"], row["chunk_id"], row["filename"], row["page_number"], row["text"], round(float(row["score"]), 6))
                        for row in rows_with_rank if float(row["score"]) > 0
                    ]
            except SQLAlchemyError:
                # Keep compatibility with existing databases while migration
                # 0003 is being rolled out.
                await self.session.rollback()
        rows = await self.session.execute(statement)
        terms = {part.lower() for part in query.text.split() if part.strip()}

        def cosine(left: list[float] | None, right: tuple[float, ...] | None) -> float:
            if not left or not right or len(left) != len(right):
                return 0.0
            dot = sum(a * b for a, b in zip(left, right, strict=True))
            norm_l = sum(a * a for a in left) ** 0.5
            norm_r = sum(b * b for b in right) ** 0.5
            return dot / (norm_l * norm_r) if norm_l and norm_r else 0.0

        ranked: list[Citation] = []
        for chunk, document in rows.all():
            words = set(chunk.lexical_text.casefold().split())
            lexical = len(terms & words) / len(terms) if terms else 0.0
            score = hybrid_score(
                lexical_rank=lexical,
                vector_similarity=cosine(chunk.embedding, query.embedding),
            )
            if score > 0:
                ranked.append(
                    Citation(
                        document.id,
                        chunk.id,
                        document.filename,
                        chunk.page_number,
                        chunk.text,
                        round(score, 6),
                    )
                )
        ranked.sort(key=lambda item: (-item.score, str(item.document_id), str(item.chunk_id)))
        return ranked[: max(1, query.limit)]
