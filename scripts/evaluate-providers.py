#!/usr/bin/env python3
"""Run the frozen agent contract suite against the configured provider.

Set COOLPROOF_AGENT_PROVIDER to ``nvidia_nim`` or ``backboard`` at runtime.
The script prints aggregate metrics and case IDs only; credentials, prompts,
completions, and source text are never printed.
"""
from __future__ import annotations

import asyncio
import json

from app.agents.evaluation import evaluate_provider
from app.agents.providers import provider_from_settings
from app.core.config import Settings


async def main() -> None:
    report = await evaluate_provider(provider_from_settings(Settings()))
    print(json.dumps(report.as_dict(), sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
