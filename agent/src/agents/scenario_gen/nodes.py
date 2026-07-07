# -*- coding: utf-8 -*-
"""
AI Test Case Generation — LangGraph node functions.

Workflow:
    intent_recognition → select_apis → case_generate → case_run → case_update → final_report
                       → general_response
"""

import json
import logging
import requests
from src.llms.llm import get_llm_by_type
from src.config.agents import AGENT_LLM_MAP
from src.shared.tools import (
    AUTOMATION_BASE_URL,
    AUTOMATION_PROJECT_ID,
    AUTOMATION_HOST_ID,
    AUTOMATION_AUTH_TOKEN,
    add_test_tool, update_test_tool, search_tool,
    create_global_var_tool, list_global_vars_tool,
    set_runtime_case_group_id,
    get_runtime_case_group_id,
)
from src.utils.post_hook_tool import post_model_hook
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import END
from langgraph.types import Command, interrupt
from src.framework.state import Ai_test_State, ScenarioPlan
from src.prompts.prompt_model.ai_test_model import  ScenarioRunResult

logger = logging.getLogger(__name__)

# ── Tool instances ──────────────────────────────────────────────────────

"""Scenario-generation node functions."""

# ── Max retry limit for the scenario fix-and-rerun loop ────────────────
MAX_SCENARIO_UPDATE_ITERATIONS = 5

async def scenario_design(state: Ai_test_State):
    """Analyse selected APIs and design a business scenario flow.

    Uses LLM to identify dependencies between APIs, design the execution
    order, and specify data interrelate mappings. Then interrupts the
    graph to present the plan to the user for confirmation.
    """
    from src.agents.agents import create_agent
    selected_apis = state.get("selected_apis", [])

    if not selected_apis:
        return Command(
            update={
                "messages": [AIMessage(content="没有选中任何API接口，无法设计场景。", name="scenario_design")],
            },
            goto=END,
        )

    # ── Handle resume: if plan is already designed, skip to interrupt ──
    if state.get("_scenario_plan_ready"):
        scenario_plan_dict = state.get("scenario_plan", {})
        logger.info("Resuming scenario_design interrupt with cached plan")
    else:
        # Build API details prompt for the LLM
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
            f"以下是用户选择的接口完整信息，请分析它们之间的依赖关系并设计业务场景：\n\n"
            f"{api_list_json}\n\n"
            f"请以 JSON 格式输出 ScenarioPlan 对象，包含场景名称、场景描述和有序步骤列表。"
            f"每个步骤必须指定 step_order（从1开始）、api_id、api_name、description、"
            f"depends_on（依赖的前置步骤序号）、dependencies（具体的数据依赖，包括"
            f"target_field、source_step、source_api_id、source_json_path）。\n\n"
            f"重要提示：确定 source_json_path 时，先查看每个API的[响应结构]字段来推断响应结构。"
            f"如果[响应结构]为空，请使用 Search_Api_Info 工具查询该API的完整文档获取响应示例。"
            f"JSONPath 以 . 分隔层级路径（如 .data.token, .code），"
            f"必须精确匹配实际响应结构的嵌套层级。"
            f"例如响应为 {{\"data\":{{\"data\":{{\"token\":\"xxx\"}}}}}} 时路径应为 .data.data.token，而非 .data.token。"
        )

        logger.info("Designing scenario for %d APIs", len(api_details))

        # ── Structured output guide (helps the model produce correct JSON) ──
        SCENARIO_DESIGN_GUIDE = (
            "You are a structured-output assistant. "
            "Analyse the provided APIs and design a business scenario flow. "
            "Output EXACTLY ONE ScenarioPlan JSON object. "
            "CRITICAL RULES:\n"
            "1. Return a single JSON object (curly braces), NOT an array.\n"
            "2. step_order must start from 1 and be sequential.\n"
            "3. Each dependency must reference a real source_step (less than current step_order).\n"
            "4. api_id values must come from the provided API list.\n"
            "5. The response must start with '{' and end with '}'."
        )

        MAX_DESIGN_RETRIES = 2
        scenario_plan = None
        last_error = None

        for attempt in range(1 + MAX_DESIGN_RETRIES):
            try:
                agent = await create_agent(
                    agent_type="scenario_design",
                    agent_name="scenario_design",
                    prompt_template="scenario_design",
                    post_model_hook=post_model_hook,
                    tools=[search_tool],
                    output_format=(SCENARIO_DESIGN_GUIDE, ScenarioPlan),
                )

                result = await agent.ainvoke({"messages": [HumanMessage(content=user_prompt)]})
                scenario_plan = result.get("structured_response")
                if scenario_plan is not None:
                    break
                logger.warning(
                    "scenario_design attempt %d/%d: structured_response is None, retrying...",
                    attempt + 1, 1 + MAX_DESIGN_RETRIES,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "scenario_design attempt %d/%d failed: %s",
                    attempt + 1, 1 + MAX_DESIGN_RETRIES, exc,
                )

        if scenario_plan is None:
            logger.error(
                "scenario_design: LLM did not return structured response after %d attempts. Last error: %s",
                1 + MAX_DESIGN_RETRIES, last_error,
            )
            return Command(
                update={
                    "messages": [AIMessage(
                        content="场景方案设计失败，请重试或简化输入（选择更少的API接口）。",
                        name="scenario_design",
                    )],
                },
                goto=END,
            )

        scenario_plan_dict = scenario_plan.model_dump()
        logger.info(
            "Designed scenario '%s' with %d steps",
            scenario_plan.scenario_name, len(scenario_plan.steps),
        )

    # ── Build interrupt payload for user confirmation ─────────────────
    steps_display = []
    for s in scenario_plan_dict.get("steps", []):
        step_info = {
            "step": s.get("step_order"),
            "api_id": s.get("api_id"),
            "api_name": s.get("api_name"),
            "description": s.get("description"),
            "depends_on": s.get("depends_on", []),
            "dependencies": [
                {
                    "target_field": d.get("target_field"),
                    "source_step": d.get("source_step"),
                    "source_json_path": d.get("source_json_path"),
                    "description": d.get("description", ""),
                }
                for d in (s.get("dependencies") or [])
            ],
        }
        steps_display.append(step_info)

    interrupt_payload = {
        "type": "scenario_confirm",
        "message": f"已设计业务场景「{scenario_plan_dict.get('scenario_name')}」，请确认场景方案：",
        "scenario_name": scenario_plan_dict.get("scenario_name"),
        "scenario_description": scenario_plan_dict.get("scenario_description"),
        "steps": steps_display,
    }

    logger.info("Interrupting for scenario confirmation")
    user_response = interrupt(interrupt_payload)

    # ── Process user response ─────────────────────────────────────────
    if not user_response:
        return Command(
            update={
                "messages": [AIMessage(content="场景设计已取消。", name="scenario_design")],
            },
            goto=END,
        )

    if isinstance(user_response, dict) and user_response.get("action") == "confirm":
        return Command(
            update={
                "messages": [AIMessage(
                    content=f"场景方案「{scenario_plan_dict.get('scenario_name')}」已确认，"
                            f"共 {len(scenario_plan_dict.get('steps', []))} 个步骤，"
                            f"开始生成场景测试用例...",
                    name="scenario_design",
                )],
                "scenario_plan": scenario_plan_dict,
                "scenario_steps": scenario_plan_dict.get("steps", []),
                "_scenario_plan_ready": True,
            },
            goto="scenario_generate",
        )
    elif isinstance(user_response, dict) and user_response.get("action") == "modify":
        return Command(
            update={
                "messages": [AIMessage(
                    content=f"根据反馈调整场景方案：{user_response.get('feedback', '')}",
                    name="scenario_design",
                )],
                "_scenario_plan_ready": False,
            },
            goto="scenario_design",
        )
    else:
        return Command(
            update={
                "messages": [AIMessage(content="场景设计已取消。", name="scenario_design")],
            },
            goto=END,
        )


# ═══════════════════════════════════════════════════════════════════════
# Node: scenario_generate
# ═══════════════════════════════════════════════════════════════════════

async def scenario_generate(state: Ai_test_State):
    """Generate test cases for each scenario step with interrelate parameters.

    Takes the confirmed scenario plan and creates test cases via
    add_automation_api, setting interrelate=True for dependent parameters.
    The ReAct agent makes tool calls sequentially, so it can use the
    returned api_id from step N to construct interrelate values for step N+1.
    """
    from src.agents.agents import create_agent
    scenario_steps = state.get("scenario_steps", [])
    scenario_plan = state.get("scenario_plan", {})
    selected_apis = state.get("selected_apis", [])

    if not scenario_steps:
        return Command(
            update={
                "messages": [AIMessage(content="没有场景步骤信息，无法生成用例。", name="scenario_generate")],
            },
            goto=END,
        )

    # Build API detail lookup by api_id (normalise to str for consistent lookup)
    api_id_map = {}
    for api in selected_apis:
        raw_id = api.get("api_id", api.get("id", ""))
        api_id_map[str(raw_id)] = api

    # Build detailed prompt for scene generation
    step_details = []
    for step in scenario_steps:
        step_api = api_id_map.get(step.get("api_id", ""), {})
        step_details.append({
            "step_order": step.get("step_order"),
            "api_id": step.get("api_id"),
            "api_name": step.get("api_name"),
            "description": step.get("description", ""),
            "depends_on": step.get("depends_on", []),
            "dependencies": [
                {
                    "target_field": d.get("target_field"),
                    "source_step": d.get("source_step"),
                    "source_api_id": d.get("source_api_id"),
                    "source_json_path": d.get("source_json_path"),
                }
                for d in (step.get("dependencies") or [])
            ],
            "api_details": {
                "接口地址": step_api.get("api_address", step_api.get("apiAddress", "")),
                "请求方法": step_api.get("request_type", step_api.get("requestType", "POST")),
                "请求头": step_api.get("head_dict", step_api.get("headDict", [])),
                "请求参数类型": step_api.get("request_parameter_type", step_api.get("requestParameterType", "raw")),
                "请求体": step_api.get("request_list", step_api.get("requestList", "{}")),
                "响应结构": step_api.get("response_schema", []),
                "期望HTTP状态": step_api.get("mock_code", ""),
                "响应示例": step_api.get("mock_response", ""),
            },
        })

    user_prompt = json.dumps({
        "scenario_name": scenario_plan.get("scenario_name", ""),
        "scenario_description": scenario_plan.get("scenario_description", ""),
        "steps": step_details,
        "instruction": "请按以下顺序执行：\n"
                       "1. 分析哪些步骤需要动态值，用 create_global_variable 创建全局变量\n"
                       "2. 按 step_order 顺序调用 add_automation_api 创建所有步骤的测试用例\n"
                       "   - 需要动态值的参数使用 $变量名 引用（如 $reg_username）\n"
                       "   - 需要从前置步骤取数据的参数使用 $N.字段路径 引用（如 $1.data.token）\n"
                       "   - 不需要设置 interrelate 标志，系统自动识别 $ 前缀",
    }, ensure_ascii=False, indent=2)

    logger.info("Generating scenario test cases for %d steps", len(scenario_steps))

    agent = await create_agent(
        agent_type="scenario_generate",
        agent_name="scenario_generate",
        prompt_template="scenario_generate",
        post_model_hook=post_model_hook,
        tools=[add_test_tool, create_global_var_tool, list_global_vars_tool],
    )

    result = await agent.ainvoke({"messages": [HumanMessage(content=user_prompt)]})

    # Extract created case IDs from tool call results, preserving step order
    step_case_ids = []
    case_group_id = 0
    for msg in result.get("messages", []):
        if hasattr(msg, "tool_call_id"):
            try:
                resp = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                if isinstance(resp, dict) and resp.get("code") == "999999":
                    data = resp.get("data")
                    if isinstance(data, dict):
                        api_id = data.get("api_id")
                        if api_id:
                            step_case_ids.append(str(api_id))
                    cg_id = resp.get("case_group_id", 0)
                    if cg_id and not case_group_id:
                        case_group_id = cg_id
                        set_runtime_case_group_id(case_group_id)
            except (json.JSONDecodeError, TypeError):
                pass

    logger.info("Generated %d scenario step test cases (group_id=%d)", len(step_case_ids), case_group_id)

    return Command(
        update={
            "messages": [AIMessage(
                content=f"场景测试用例已生成：共 {len(step_case_ids)} 个步骤用例",
                name="scenario_generate",
            )],
            "scenario_case_ids": step_case_ids,
            "case_group_id": case_group_id or get_runtime_case_group_id(),
        },
        goto="scenario_run",
    )


# ═══════════════════════════════════════════════════════════════════════
# Node: scenario_run
# ═══════════════════════════════════════════════════════════════════════

async def scenario_run(state: Ai_test_State):
    """Execute scenario steps via the LLM agent calling ``execute_scenario_step``.

    Each tool call emits SSE events (tool_call / tool_result), giving the
    frontend full per-step visibility.  The LLM calls ``execute_scenario_step``
    once per case ID, then generates the structured summary.
    """
    from src.agents.agents import create_agent
    from src.shared.tools import execute_step_tool

    scenario_case_ids = state.get("scenario_case_ids", [])
    scenario_steps = state.get("scenario_steps", [])
    scenario_plan = state.get("scenario_plan", {})

    if not scenario_case_ids:
        return Command(
            update={
                "messages": [AIMessage(content="没有可执行的场景用例。", name="scenario_run")],
            },
            goto=END,
        )

    scenario_name = scenario_plan.get("scenario_name", "场景测试")

    # Build step metadata
    name_by_order = {s.get("step_order"): s.get("api_name", "") for s in scenario_steps}
    step_info = []
    for i, case_id in enumerate(scenario_case_ids):
        step_order = i + 1
        step_info.append({
            "step_order": step_order,
            "case_id": case_id,
            "api_name": name_by_order.get(step_order, f"Step {step_order}"),
        })

    logger.info("Running scenario '%s' with %d steps (agent-driven)", scenario_name, len(step_info))

    # ── Phase 1: LLM agent calls execute_scenario_step for each case ──
    step_instructions = "\n".join(
        f"  Step {s['step_order']}: case_id={s['case_id']}, api_name={s['api_name']}"
        for s in step_info
    )
    case_ids_csv = ",".join(str(s["case_id"]) for s in step_info)

    SCENARIO_RUN_SUMMARY_PROMPT = (
        "You are a structured-output assistant. "
        "After all steps have been executed, produce EXACTLY ONE ScenarioRunResult "
        "JSON object summarising the results. "
        "CRITICAL RULES:\n"
        "1. Return a single JSON object (curly braces), NOT an array / list.\n"
        "2. Use the exact field names from the tool results.\n"
        "3. Do NOT invent or modify step results — pass them through as-is.\n"
        "4. The response must start with '{' and end with '}'."
    )

    agent = await create_agent(
        agent_type="scenario_run",
        agent_name="scenario_run",
        prompt_template="scenario_run",
        post_model_hook=post_model_hook,
        tools=[execute_step_tool],
        output_format=(SCENARIO_RUN_SUMMARY_PROMPT, ScenarioRunResult),
    )

    try:
        result = await agent.ainvoke({
            "messages": [HumanMessage(
                content=(
                    f"请按顺序执行以下场景步骤，每次调用 execute_scenario_step 执行一个 case_id：\n"
                    f"{step_instructions}\n\n"
                    f"所有步骤的 case_id 列表: {case_ids_csv}\n"
                    f"请逐个执行，全部完成后输出 ScenarioRunResult 汇总结果。"
                )
            )],
        })

        structured_response = result.get("structured_response")
        scenario_results_dict = (
            structured_response.model_dump()
            if hasattr(structured_response, "model_dump")
            else {}
        )

        # Count pass/fail from the structured response
        step_results = scenario_results_dict.get("step_results", [])
        passed = sum(1 for s in step_results if s.get("success"))
        failed = len(step_results) - passed

        return Command(
            update={
                "messages": [AIMessage(
                    content=(
                        f"场景「{scenario_name}」执行完成："
                        f"共 {len(step_results)} 步，通过 {passed}，失败 {failed}"
                    ),
                    name="scenario_run",
                )],
                "scenario_results": scenario_results_dict,
            },
            goto="scenario_fix",
        )
    except Exception as e:
        logger.error("scenario_run error: %s", e, exc_info=True)
        return Command(
            update={
                "messages": [AIMessage(content=f"场景执行出错：{e}", name="scenario_run")],
            },
            goto=END,
        )


# ═══════════════════════════════════════════════════════════════════════
# Node: scenario_fix
# ═══════════════════════════════════════════════════════════════════════

# ── Max retry limit for the scenario fix-and-rerun loop ────────────────
MAX_SCENARIO_UPDATE_ITERATIONS = 5


async def scenario_fix(state: Ai_test_State):
    """Fix failed scenario steps and loop back to re-run.

    Follows the same pattern as ``case_update``: increments
    ``scenario_update_count`` on each iteration, terminates after
    ``MAX_SCENARIO_UPDATE_ITERATIONS`` and moves to ``scenario_report``.
    """
    from src.agents.agents import create_agent
    scenario_results = state.get("scenario_results", {})
    scenario_update_count = int(state.get("scenario_update_count", 0))

    # Extract failed steps
    step_results = scenario_results.get("step_results", [])
    failed_steps = [s for s in step_results if not s.get("success", False)]
    failed_count = len(failed_steps)

    logger.info(
        "Scenario fix — failed_steps=%d, iteration=%d",
        failed_count, scenario_update_count,
    )

    # ── Guard: too many retries ───────────────────────────────────────
    if scenario_update_count >= MAX_SCENARIO_UPDATE_ITERATIONS:
        logger.info(
            "Max scenario update iterations (%d) reached, moving to report",
            MAX_SCENARIO_UPDATE_ITERATIONS,
        )
        return Command(
            update={
                "messages": [AIMessage(
                    content=f"已达到最大修复次数（{MAX_SCENARIO_UPDATE_ITERATIONS}次），生成场景报告",
                    name="scenario_fix",
                )],
            },
            goto="scenario_report",
        )

    # ── Guard: no failures ───────────────────────────────────────────
    if not failed_steps:
        logger.info("All scenario steps passed!")
        return Command(
            update={
                "messages": [AIMessage(
                    content="所有场景步骤执行成功！",
                    name="scenario_fix",
                )],
            },
            goto="scenario_report",
        )

    # ── Fix failures ─────────────────────────────────────────────────
    agent = await create_agent(
        agent_type="scenario_fix",
        agent_name="scenario_fix",
        prompt_template="scenario_fix",
        post_model_hook=post_model_hook,
        tools=[search_tool, update_test_tool],
    )

    fix_list_lines = []
    for s in failed_steps:
        case_id = s.get("case_id", "")
        api_name = s.get("api_name", "")
        error = s.get("error_detail", "")
        fix_list_lines.append(
            f"case_id={case_id}, api_name={api_name}, 失败详情: {error}"
        )
    fix_list = "\n".join(fix_list_lines)

    agent_input = {
        "messages": [HumanMessage(
            content=f"以下场景步骤执行失败，请逐个查询并修复：\n\n{fix_list}"
        )],
    }

    try:
        result = await agent.ainvoke(agent_input)
        new_count = scenario_update_count + 1
        logger.info(
            "Scenario fix complete, re-running (iteration %d → %d)",
            scenario_update_count, new_count,
        )

        return Command(
            update={
                "messages": [AIMessage(
                    content=result["messages"][-1].content,
                    name="scenario_fix",
                )],
                "scenario_update_count": new_count,
            },
            goto="scenario_run",
        )
    except Exception as e:
        logger.error("scenario_fix error: %s", e, exc_info=True)
        return Command(
            update={
                "messages": [AIMessage(
                    content=f"修复场景用例时发生错误：{e}",
                    name="scenario_fix",
                )],
            },
            goto=END,
        )


# ═══════════════════════════════════════════════════════════════════════
# Node: scenario_report
# ═══════════════════════════════════════════════════════════════════════

async def scenario_report(state: Ai_test_State):
    """Generate a detailed scenario test report in Markdown format."""
    scenario_results = state.get("scenario_results", {})
    scenario_plan = state.get("scenario_plan", {})
    scenario_steps = state.get("scenario_steps", [])
    scenario_update_count = int(state.get("scenario_update_count", 0))

    logger.info("Generating scenario report (fix iterations=%d)", scenario_update_count)

    llm = get_llm_by_type(AGENT_LLM_MAP.get("basic", "basic"))

    report_prompt = f"""请根据以下场景测试结果生成详细的场景测试报告：

from src.llms.llm import get_llm_by_type; from src.config.agents import AGENT_LLM_MAP
场景名称：{scenario_plan.get('scenario_name', '未命名场景')}
场景描述：{scenario_plan.get('scenario_description', '')}
修复重试次数：{scenario_update_count}
场景步骤：{json.dumps([{'step': s.get('step_order'), 'api_name': s.get('api_name'), 'description': s.get('description')} for s in scenario_steps], ensure_ascii=False)}

执行结果：
{json.dumps(scenario_results, ensure_ascii=False, indent=2)}

请用中文输出场景测试报告（Markdown格式），包含：
1. 场景概览（名称、总步骤数、通过/失败数、修复次数、整体结论）
2. 数据流追踪（展示步骤间的数据传递关系和实际传递的数据）
3. 各步骤详情（每个步骤的执行结果、HTTP状态码、响应摘要）
4. 失败分析（如果有失败步骤，详细说明失败原因和修复建议）
5. 修复记录（如有修复，说明修复了哪些步骤、修改了什么参数）
6. 总结与建议"""

    try:
        response = await llm.ainvoke([HumanMessage(content=report_prompt)])
        report_text = response.content

        return Command(
            update={
                "messages": [AIMessage(content=report_text, name="scenario_report")],
                "scenario_report_text": report_text,
                "final_report": report_text,
            },
            goto=END,
        )
    except Exception as e:
        logger.error("scenario_report error: %s", e)
        return Command(
            update={
                "messages": [AIMessage(content=f"生成场景报告时出错：{e}", name="scenario_report")],
            },
            goto=END,
        )


# ═══════════════════════════════════════════════════════════════════════
# Node: general_response
# ═══════════════════════════════════════════════════════════════════════

