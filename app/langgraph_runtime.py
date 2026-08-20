"""Long-lived LangGraph runtime process for the Compose deployment."""

from __future__ import annotations

import asyncio
import logging

from app.agents.providers import provider_from_settings
from app.agents.runtime import compile_langgraph
from app.core.config import get_settings


async def run() -> None:
    settings = get_settings()
    # Compile once at startup so provider/configuration errors are visible in
    # the process health and the worker can execute governed runs durably.
    compile_langgraph(provider_from_settings(settings))
    logging.getLogger(__name__).info("langgraph runtime ready")
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(run())
