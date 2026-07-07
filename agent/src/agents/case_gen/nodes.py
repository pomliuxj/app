# -*- coding: utf-8 -*-
"""
AI Test Case Generation — LangGraph node functions.

Workflow:
    intent_recognition → select_apis → case_generate → case_run → case_update → final_report
"""

import json
import logging
from src.llms.llm import get_llm_by_type
from src.config.agents import AGENT_LLM_MAP

from src.shared.tools import (
    start_test_tool, add_test_tool, update_test_tool, search_tool,
    set_runtime_case_group_id,
)
from src.utils.post_hook_tool import post_model_hook
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import END
from langgraph.types import Command, interrupt
from src.framework.state import Ai_test_State
from src.prompts.prompt_model.ai_test_model import CaseItem, CaseList, FailCase, CaseRunDetails, ScenarioStepResult, ScenarioRunResult

logger = logging.getLogger(__name__)

# ── Tool instances ──────────────────────────────────────────────────────

# ── Max retry limit for the fix-and-rerun loop ─────────────────────────
MAX_UPDATE_ITERATIONS = 5


# ═══════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
# Node: case_generate
# ═══════════════════════════════════════════════════════════════════════

async def case_generate(state: Ai_test_State):
    """Generate test cases (including assertions) for each user-selected API.

    Uses the ``selected_apis`` list from state (populated by the
    ``select_apis`` node or the user's interrupt resume) as input.
    """
    from src.agents.agents import create_agent
    selected_apis = state.get("selected_apis", [])

    if not selected_apis:
        logger.warning("No APIs selected for test generation")
        return Command(
            update={
                "messages": [AIMessage(
                    content="没有选中任何API接口，无法生成测试用例。",
                    name="case_generate",
                )],
                "all_case_generate": CaseList(all_cases=[]),
            },
            goto="case_run",
        )

    # Build a structured prompt with FULL API details (including params & response)
    api_details = []
    for api in selected_apis:
        api_details.append({
            "api_id": api.get("api_id", api.get("id", "")),
            "接口名称": api.get("name", ""),
            "接口地址": api.get("api_address", api.get("apiAddress", "")),
            "请求方法": api.get("request_type", api.get("requestType", "POST")),
            "协议类型": api.get("http_type", api.get("httpType", "HTTP")),
            "接口描述": api.get("description", ""),
            "请求头": api.get("head_dict", api.get("headDict", [])),
            "请求参数类型": api.get("request_parameter_type", api.get("requestParameterType", "raw")),
            "请求体": api.get("request_list", api.get("requestList", "{}")),
            "响应结构": api.get("response_schema", []),
            "期望HTTP状态": api.get("mock_code", ""),
            "响应示例": api.get("mock_response", ""),
        })

    api_list_json = json.dumps(api_details, ensure_ascii=False, indent=2)
    user_prompt = (
        f"以下是需要生成测试用例的接口完整信息（含请求参数和响应断言）：\n\n"
        f"{api_list_json}"
    )

    logger.info("Generating test cases for %d selected APIs", len(api_details))

    agent = await create_agent(
        agent_type="case_generate",
        agent_name="case_generate",
        prompt_template="case_generate",
        post_model_hook=post_model_hook,
        tools=[add_test_tool],
        # No output_format — let ReAct loop make multiple tool calls
    )

    result = await agent.ainvoke({"messages": [HumanMessage(content=user_prompt)]})

    # Extract created cases from tool call results in the message history
    tool_names = []  # (tool_call_id, case_name)
    tool_results = []  # (tool_call_id, api_id)
    case_group_id = 0

    for msg in result.get("messages", []):
        if hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls:
                if tc.get("name") == "add_automation_api":
                    tool_names.append((tc.get("id"), tc.get("args", {}).get("name", "")))
        if hasattr(msg, "tool_call_id"):
            tc_id = msg.tool_call_id
            try:
                resp = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                if isinstance(resp, dict) and resp.get("code") == "999999":
                    api_id = resp.get("data", {}).get("api_id") if isinstance(resp.get("data"), dict) else None
                    cg_id = resp.get("case_group_id", 0)
                    if api_id:
                        tool_results.append((tc_id, str(api_id)))
                        if not case_group_id and cg_id:
                            case_group_id = cg_id
                            set_runtime_case_group_id(case_group_id)
            except (json.JSONDecodeError, TypeError):
                pass

    name_map = dict(tool_names)
    case_items = []
    for tc_id, api_id in tool_results:
        case_items.append(CaseItem(
            case_id=api_id,
            api_name=name_map.get(tc_id, ""),
            request_type="",
            api_address="",
            http_code="",
        ))

    all_cases = CaseList(all_cases=case_items)
    case_count = len(case_items)
    logger.info("Generated %d test cases", case_count)

    return Command(
        update={
            "messages": [AIMessage(
                content=f"已生成 {case_count} 个测试用例",
                name="case_generate",
            )],
            "all_case_generate": all_cases,
            "case_group_id": case_group_id,
        },
        goto="case_run",
    )


# ═══════════════════════════════════════════════════════════════════════
# Node: case_run
# ═══════════════════════════════════════════════════════════════════════

async def case_run(state: Ai_test_State):
    """Execute generated test cases via the automation backend."""
    from src.agents.agents import create_agent

    all_case_generate = state.get("all_case_generate", [])
    update_count = int(state.get("update_count", 0))

    logger.info("Running test cases (attempt %d) ...", update_count + 1)

    # Extract case IDs — from generated cases (first run) or failed cases (retry)
    case_ids = []
    if update_count == 0:
        if hasattr(all_case_generate, "all_cases") and all_case_generate.all_cases:
            case_ids = [
                case.case_id for case in all_case_generate.all_cases
                if hasattr(case, "case_id")
            ]
    else:
        case_ids = [
            case.case_id for case in state.get("fail_case", [])
            if hasattr(case, "case_id")
        ]

    logger.info("Case IDs to execute: %s", case_ids)

    if not case_ids:
        return Command(
            update={
                "messages": [AIMessage(content="没有可执行的测试用例", name="case_run")],
                "fail_case": [],
            },
            goto=END,
        )

    # Convert string case_ids to int for the tool
    case_ids_int = [int(c) for c in case_ids if str(c).isdigit()]

    CASE_RUN_STRUCTURED_PROMPT = (
        "You are a structured-output assistant. "
        "Based on the conversation above, produce EXACTLY ONE CaseRunDetails JSON object. "
        "CRITICAL RULES:\n"
        "1. Return a single JSON object (curly braces), NOT an array / list.\n"
        "2. Use the schema fields exactly: run_fail_cases, total_count, pass_count, fail_count.\n"
        "3. run_fail_cases is a list of FailCase objects — include one entry for each failed case.\n"
        "4. Never wrap the output in an array — the response must start with '{' and end with '}'."
    )

    MAX_STRUCTURED_RETRIES = 2
    agent_input = {"messages": [HumanMessage(
        content=f"请执行以下测试用例，用例ID列表: {case_ids_int}"
    )]}

    last_error = None
    structured_response = None
    for attempt in range(1 + MAX_STRUCTURED_RETRIES):
        agent = await create_agent(
            agent_type="case_run",
            agent_name="case_run",
            prompt_template="case_run",
            post_model_hook=post_model_hook,
            tools=[start_test_tool],
            output_format=(CASE_RUN_STRUCTURED_PROMPT, CaseRunDetails),
        )

        try:
            result = await agent.ainvoke(agent_input)
            structured_response = result.get("structured_response")
            break
        except Exception as e:
            last_error = e
            if "ValidationError" in type(e).__name__ or "validation error" in str(e).lower():
                logger.warning(
                    "case_run structured-output attempt %d/%d failed, retrying...",
                    attempt + 1, 1 + MAX_STRUCTURED_RETRIES,
                )
                continue
            break

    if structured_response is None:
        logger.error("case_run failed after %d attempts: %s", 1 + MAX_STRUCTURED_RETRIES, last_error, exc_info=True)
        return Command(
            update={
                "messages": [AIMessage(content=f"用例执行出错：{last_error}", name="case_run")],
            },
            goto=END,
        )

    # Build name lookup from generated cases
    name_by_id = {}
    if hasattr(all_case_generate, "all_cases") and all_case_generate.all_cases:
        for case in all_case_generate.all_cases:
            if hasattr(case, "case_id") and hasattr(case, "api_name"):
                name_by_id[case.case_id] = case.api_name

    # Extract per-case results from start_automation_test response
    fail_list = structured_response.run_fail_cases

    logger.info(
        "Execution complete — %d failed, %d passed",
        len(fail_list),
        len(case_ids_int) - len(fail_list),
    )

    try:
        return Command(
            update={
                "messages": [AIMessage(
                    content=result["messages"][-1].content if result.get("messages") else "执行完成",
                    name="case_run",
                )],
                "fail_case": fail_list,
            },
            goto="case_update",
        )
    except Exception as e:
        logger.error("case_run error: %s", e)
        return Command(
            update={
                "messages": [AIMessage(content=f"执行测试时发生错误：{e}", name="case_run")],
                "fail_case": [],
            },
            goto=END,
        )


# ═══════════════════════════════════════════════════════════════════════
# Node: case_update
# ═══════════════════════════════════════════════════════════════════════

async def case_update(state: Ai_test_State):
    from src.agents.agents import create_agent
    """Fix failed test cases and loop back to re-run.

    On each iteration ``update_count`` is incremented.  After
    ``MAX_UPDATE_ITERATIONS`` the loop terminates and the flow moves to
    ``final_report``.
    """
    from src.agents.agents import create_agent
    fail_case = state.get("fail_case", [])
    # fail_case = [FailCase(name='', case_id='122', status='失败', detail='{"password": ["该字段不能为空。"], "code": 400}')]
    update_count = int(state.get("update_count", 0))

    logger.info("Processing failures — count=%d, iteration=%d", len(fail_case), update_count)

    # ── Guard: too many retries ─────────────────────────────────────────
    if update_count >= MAX_UPDATE_ITERATIONS:
        logger.info("Max update iterations (%d) reached, ending loop", MAX_UPDATE_ITERATIONS)
        return Command(
            update={
                "messages": [AIMessage(
                    content=f"已达到最大修复次数（{MAX_UPDATE_ITERATIONS}次），流程结束",
                    name="case_update",
                )],
            },
            goto="final_report",
        )

    # ── Guard: no failures ─────────────────────────────────────────────
    if not fail_case:
        logger.info("All test cases passed!")
        return Command(
            update={
                "messages": [AIMessage(content="所有测试用例执行成功！", name="case_update")],
            },
            goto="final_report",
        )

    # ── Fix failures ───────────────────────────────────────────────────
    agent = await create_agent(
        agent_type="case_update",
        agent_name="case_update",
        prompt_template="case_update",
        post_model_hook=post_model_hook,
        tools=[search_tool, update_test_tool],
    )

    fix_list = "\n".join(
        f"case_id={f.case_id}, name={f.name}, 失败详情detail: {f.detail}"
        for f in fail_case
    )
    agent_input = {
        "messages": [HumanMessage(
            content=f"以下用例执行失败，请逐个查询并修复：\n\n{fix_list}"
        )],
    }

    try:
        result = await agent.ainvoke(agent_input)
        logger.info("Failures fixed, re-running (iteration %d → %d)", update_count, update_count + 1)

        return Command(
            update={
                "messages": [AIMessage(content=result["messages"][-1].content, name="case_update")],
                "update_count": update_count + 1,
            },
            goto="case_run",
        )
    except Exception as e:
        logger.error("case_update error: %s", e)
        return Command(
            update={
                "messages": [AIMessage(content=f"修复测试用例时发生错误：{e}", name="case_update")],
            },
            goto=END,
        )


# ═══════════════════════════════════════════════════════════════════════
# Node: final_report
# ═══════════════════════════════════════════════════════════════════════

async def final_report(state: Ai_test_State):
    """Generate a final test report summarising all results."""
    fail_case = state.get("fail_case", [])
    update_count = int(state.get("update_count", 0))

    logger.info("Generating final report — failures=%d, fix iterations=%d", len(fail_case), update_count)

    llm = get_llm_by_type(AGENT_LLM_MAP.get("basic", "basic"))

    all_cases = state.get("all_case_generate", [])
    case_count = (
        len(all_cases.all_cases)
        if hasattr(all_cases, "all_cases")
        else len(all_cases) if isinstance(all_cases, list)
        else 0
    )
    fail_count = len(fail_case) if fail_case else 0
    pass_count = case_count - fail_count if case_count else 0

    report_prompt = f"""请根据以下信息生成测试报告：

from src.llms.llm import get_llm_by_type; from src.config.agents import AGENT_LLM_MAP
- 总用例数：{case_count}
- 通过：{pass_count}
- 失败：{fail_count}
- 修复重试次数：{update_count}

{'仍有失败用例：' + str(fail_case) if fail_case else '全部用例通过！'}

请用中文输出一份简洁的测试报告（Markdown格式）。"""

    try:
        response = await llm.ainvoke([HumanMessage(content=report_prompt)])
        report_text = response.content

        return Command(
            update={
                "messages": [AIMessage(content=report_text, name="final_report")],
                "final_report": report_text,
            },
            goto=END,
        )
    except Exception as e:
        logger.error("final_report error: %s", e)
        return Command(
            update={
                "messages": [AIMessage(content=f"生成报告时出错：{e}", name="final_report")],
                "final_report": f"Report generation failed: {e}",
            },
            goto=END,
        )


# ═══════════════════════════════════════════════════════════════════════
# Node: scenario_design
# ═══════════════════════════════════════════════════════════════════════
