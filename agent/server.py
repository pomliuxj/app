# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Server script for running the AI Test Case Generation API.
"""

import argparse
import signal
import sys
import asyncio
import logging

import uvicorn

from src.config.log import LOGGING_CONFIG

logger = logging.getLogger(__name__)


def handle_shutdown(signum, frame):
    """Handle graceful shutdown on SIGTERM/SIGINT."""
    logger.info("Received shutdown signal. Starting graceful shutdown...")
    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the AI Test Case Generation API")
    parser.add_argument(
        "--host", type=str, default="localhost",
        help="Host to bind the server to (default: localhost)",
    )
    parser.add_argument(
        "--port", type=int, default=9000,
        help="Port to bind the server to (default: 9000)",
    )
    parser.add_argument(
        "--log-level", type=str, default="info",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Log level (default: info)",
    )

    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        logger.info(f"Starting AI Test Case Generation server on {args.host}:{args.port}")
        uvicorn.run(
            "src.server:app",
            host=args.host,
            port=args.port,
            reload=False,       # Must be False: interrupt/resume needs persistent process
            log_level=args.log_level,
            log_config=LOGGING_CONFIG,
        )
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        sys.exit(1)
