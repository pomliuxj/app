# -*- coding: utf-8 -*-
"""
AI Test Case Generation — LangGraph node functions.

Workflow:
    intent_recognition → select_apis → case_generate → case_run → case_update → final_report
                       → general_response
"""

import logging as logger
from src.shared.tools import (

    AUTOMATION_BASE_URL,
    AUTOMATION_PROJECT_ID,
    api_doc_tool, list_apis_tool,

)
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import END
from langgraph.types import Command, interrupt
from src.framework.state import Ai_test_State

async def select_apis(state: Ai_test_State):
    """Query APIs and let the user pick which to test.

    Uses LangGraph's ``interrupt()`` for human-in-the-loop.
    On first run: queries the backend, builds the options list, pauses.
    On resume: ``_api_list_ready`` flag is set → skips the query and
    goes directly to ``interrupt()`` + processing the user's selection.
    """
    messages = state.get("messages", [])
    if messages:
        last = messages[-1]
        user_input = last.content if hasattr(last, "content") else str(last)
    else:
        user_input = ""

    # ── 断点恢复判断：如果标识已置位，跳过查询直接走 interrupt ──
    if state.get("_api_list_ready"):
        api_options = state.get("available_apis", [])
        logger.info("Resuming from interrupt — using cached %d API options", len(api_options))
    else:
        # ── 首次执行：查询后端获取接口列表 ──────────────────────────────
        logger.info("Selecting APIs — querying project %s ...", AUTOMATION_PROJECT_ID)

        try:
            apis_response = await list_apis_tool._arun(project_id=str(AUTOMATION_PROJECT_ID))
        except Exception as e:
            logger.error("Failed to query project APIs: %s", e)
            apis_response = {"data": {"data": []}}

        api_list_data = []
        if isinstance(apis_response, dict):
            if "error" in apis_response:
                error_msg = apis_response.get("error", "未知错误")
                logger.error("Backend connection failed: %s (base_url=%s)", error_msg, AUTOMATION_BASE_URL)
                return Command(
                    update={
                        "messages": [AIMessage(
                            content=f"无法连接到后端服务 ({AUTOMATION_BASE_URL}): {error_msg}\n\n"
                                    f"请检查：\n"
                                    f"1. Django 服务是否已启动（端口 8000）\n"
                                    f"2. AUTOMATION_BASE_URL 环境变量是否正确\n"
                                    f"3. 防火墙是否放行端口 8000",
                            name="select_apis",
                        )],
                        "selected_apis": [],
                        "available_apis": [],
                    },
                    goto=END,
                )
            data_container = apis_response.get("data", {})
            if isinstance(data_container, dict):
                api_list_data = data_container.get("data", [])

        logger.info("Found %d APIs in project", len(api_list_data))

        if not api_list_data:
            return Command(
                update={
                    "messages": [AIMessage(
                        content="当前项目中暂无已注册的API接口，请先在项目中添加接口。",
                        name="select_apis",
                    )],
                    "selected_apis": [],
                    "available_apis": [],
                },
                goto=END,
            )

        # ── Build a clean options list for the user ────────────────────────
        api_options = []
        for api in api_list_data:
            api_options.append({
                "api_id": api.get("id", ""),
                "name": api.get("name", ""),
                "api_address": api.get("apiAddress", ""),
                "request_type": api.get("requestType", "GET"),
                "http_type": api.get("httpType", "HTTP"),
            })

    # ── Interrupt and wait for user selection ──────────────────────────
    interrupt_payload = {
        "type": "select_apis",
        "message": f"项目中已有 {len(api_options)} 个API接口，请选择需要生成测试用例的接口：",
        "available_apis": api_options,
        "user_input": user_input,
    }
    logger.info("Interrupting for API selection — %d options", len(api_options))

    user_selection = interrupt(interrupt_payload)

    # ── Process the user's selection ───────────────────────────────────
    if not user_selection:
        logger.info("User did not select any APIs, ending flow")
        return Command(
            update={
                "messages": [AIMessage(content="未选择任何接口，流程结束。", name="select_apis")],
                "selected_apis": [],
            },
            goto=END,
        )

    selected = user_selection if isinstance(user_selection, list) else [user_selection]
    logger.info("User selected %d APIs for test generation", len(selected))

    # ── Enrich selected APIs with full details ─────────────────────────
    enriched_apis = []
    for api in selected:
        api_id = api.get("api_id", api.get("id", ""))
        if api_id:
            try:
                resp = await api_doc_tool._arun(api_id=str(api_id))
                if isinstance(resp, dict) and resp.get("code") == "999999":
                    detail = resp.get("data", {})
                    # Build request_list from correct source based on parameter type
                    req_param_type = detail.get("requestParameterType", "raw")
                    if req_param_type == "form-data":
                        request_list = detail.get("requestParameter", [])
                    else:
                        raw_obj = detail.get("requestParameterRaw") or {}
                        request_list = raw_obj.get("data", "{}")

                    enriched = {
                        "api_id": api_id,
                        "name": detail.get("name", api.get("name", "")),
                        "api_address": detail.get("apiAddress", api.get("api_address", "")),
                        "request_type": detail.get("requestType", api.get("request_type", "POST")),
                        "http_type": detail.get("httpType", api.get("http_type", "HTTP")),
                        "head_dict": detail.get("headers", []),
                        "request_list": request_list,
                        "request_parameter_type": req_param_type,
                        # Real data from ApiInfo (not AutomationCaseApi fallbacks)
                        "description": detail.get("description", ""),
                        # response fields include tier for JSONPath construction:
                    # [{name, tier, _type, value, required, description}, ...]
                    "response_schema": detail.get("response", []),
                        "mock_code": detail.get("mockCode", ""),
                        "mock_response": detail.get("data", ""),
                    }
                    enriched_apis.append(enriched)
                    logger.info("Enriched API '%s' with full details", enriched["name"])
                    continue
            except Exception as e:
                logger.warning("Failed to get detail for api_id=%s: %s", api_id, e)
        enriched_apis.append(api)

    logger.info("Enriched %d APIs with full details", len(enriched_apis))

    # ── Route based on intent type and API count ─────────────────────
    intent_type = state.get("intent_type", "test_case_generation")

    # Fallback: if intent_type is missing / default but the user's last
    # message strongly suggests a scenario test, treat it as one.
    if intent_type != "scenario_test_generation" and len(enriched_apis) > 1:
        scenario_keywords = ["场景", "流程", "链路", "业务", "端到端", "串联"]
        if any(kw in (user_input or "") for kw in scenario_keywords):
            intent_type = "scenario_test_generation"
            logger.info("Fallback: detected scenario keywords in user input → routing to scenario_design")

    if intent_type == "scenario_test_generation":
        next_node = "scenario_design"
        msg = f"已选择 {len(enriched_apis)} 个接口，开始分析接口依赖并设计业务场景..."
    else:
        next_node = "case_generate"
        msg = f"已选择 {len(enriched_apis)} 个接口，开始生成测试用例..."

    return Command(
        update={
            "messages": [AIMessage(content=msg, name="select_apis")],
            "selected_apis": enriched_apis,
        },
        goto=next_node,
    )


# ═══════════════════════════════════════════════════════════════════════
# Node: case_generate
# ═══════════════════════════════════════════════════════════════════════

