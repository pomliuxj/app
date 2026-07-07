"""Checkpoint configuration — persistent state for interrupt / resume.

Default is ``InMemorySaver``.  Set ``CHECKPOINT_BACKEND=sqlite`` for
persistent state that survives server restarts.

The SQLite path uses ``AsyncSqliteSaver`` with a manually-managed
``aiosqlite`` connection — bypassing ``from_conn_string``'s async
context manager which auto-closes and triggers aiosqlite thread-reuse
crashes on the next request.
"""

from __future__ import annotations

import os
from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

logger = __import__("logging").getLogger(__name__)

_DEFAULT_DB_PATH = str(Path(__file__).resolve().parent.parent.parent / "checkpoints.db")

_CHECKPOINTER: BaseCheckpointSaver | None = None


async def aget_checkpointer(db_path: str | None = None) -> BaseCheckpointSaver:
    """Return a process-lifetime checkpointer singleton.

    ``CHECKPOINT_BACKEND=memory`` (default):
        ``InMemorySaver`` — fast, zero connection overhead.

    ``CHECKPOINT_BACKEND=sqlite``:
        ``AsyncSqliteSaver`` backed by a persistent ``aiosqlite``
        connection that lives for the server process lifetime.
    """
    global _CHECKPOINTER

    if _CHECKPOINTER is not None:
        return _CHECKPOINTER

    backend = os.getenv("CHECKPOINT_BACKEND", "memory").lower()

    if backend == "sqlite":
        resolved_path = db_path or _DEFAULT_DB_PATH
        try:
            import aiosqlite
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            conn = await aiosqlite.connect(resolved_path)
            _CHECKPOINTER = AsyncSqliteSaver(conn)
            logger.info("AsyncSqliteSaver connected to %s", resolved_path)
            return _CHECKPOINTER
        except ImportError:
            logger.warning("AsyncSqliteSaver unavailable, falling back to InMemorySaver")

    logger.info("Using InMemorySaver")
    _CHECKPOINTER = InMemorySaver()
    return _CHECKPOINTER


def reset_checkpointer() -> None:
    """Clear the cached checkpointer (useful in tests)."""
    global _CHECKPOINTER
    _CHECKPOINTER = None
