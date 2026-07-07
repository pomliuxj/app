# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.server.controller import chat_controller

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Test Case Generation API",
    description="API for AI-driven automated test case generation",
    version="0.1.0",
)

# CORS middleware — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(chat_controller.router)


@app.get("/health")
async def health_check():
    """健康检查：验证 Agent 能否连接到自动化后端服务"""
    base_url = os.getenv("AUTOMATION_BASE_URL", "http://127.0.0.1:8000")
    result = {
        "agent": "ok",
        "backend_url": base_url,
        "backend_status": "unknown",
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base_url}/api/schema/")
            result["backend_status"] = "reachable" if resp.status_code == 200 else f"HTTP {resp.status_code}"
    except Exception as e:
        result["backend_status"] = f"unreachable: {e}"
    status_code = 200 if result["backend_status"] == "reachable" else 503
    return JSONResponse(content=result, status_code=status_code)


@app.on_event("startup")
async def startup():
    """Register all sub-agents on service startup."""
    try:
        import src.agents  # noqa: F401 — triggers sub-agent self-registration
        from src.framework.registry import list_all
        agents = list_all()
        logger.info("Sub-agents registered: %s", list(agents.keys()))
    except Exception as exc:
        logger.error("Failed to register sub-agents: %s", exc)
