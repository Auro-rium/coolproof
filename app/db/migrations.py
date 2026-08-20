"""Small, idempotent schema bootstrap used by the single-host deployment.

The project is intentionally deployed as one Compose host, so a full migration
runner is not required to start the service. This module gives that deployment
an explicit, repeatable schema step while keeping local SQLite tests working.
It can later be replaced by Alembic revisions without changing the deployment
contract.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine


async def migrate() -> None:
    """Create the current schema and enable pgvector where supported."""
    async with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(migrate())
