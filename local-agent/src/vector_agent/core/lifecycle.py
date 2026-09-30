"""Application lifecycle management."""

from __future__ import annotations

from vector_agent.core.logging import get_logger

logger = get_logger(__name__)


async def startup_tasks() -> None:
    """Run tasks that should execute when the agent starts."""
    logger.info("Running startup tasks...")
    # TODO(phase2): Initialize device registry.
    # TODO(phase2): Start ADB server if not running.


async def shutdown_tasks() -> None:
    """Run cleanup tasks when the agent shuts down."""
    logger.info("Running shutdown tasks...")
    # TODO(phase3): Cancel any running scans gracefully.
