"""Single-API test case generation sub-agent.

Graph topology::

    START → select_apis [interrupt] → case_generate → case_run
              → case_update (retry≤5) → final_report → END
"""

import logging

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from src.framework.state import Ai_test_State
from src.shared.nodes import select_apis as _select_apis
from src.agents.case_gen.nodes import (
    case_generate,
    case_run,
    case_update,
    final_report,
)
from src.framework import register_sub_agent, SubAgentDefinition

logger = logging.getLogger(__name__)


async def _select_apis_case(state: Ai_test_State) -> Command:
    """Wrapper: force routing to case_generate within this sub-graph."""
    state["intent_type"] = "test_case_generation"
    result = await _select_apis(state)
    if hasattr(result, "goto") and result.goto not in (END, "case_generate"):
        logger.warning("select_apis tried '%s' → forcing 'case_generate'", result.goto)
        return Command(update=result.update, goto="case_generate")
    return result


def build_graph() -> StateGraph:
    builder = StateGraph(Ai_test_State)
    builder.add_node("select_apis", _select_apis_case)
    builder.add_node("case_generate", case_generate)
    builder.add_node("case_run", case_run)
    builder.add_node("case_update", case_update)
    builder.add_node("final_report", final_report)
    builder.add_edge(START, "select_apis")
    return builder.compile()


def register():
    register_sub_agent(SubAgentDefinition(
        agent_id="case_gen",
        name="接口用例生成",
        description="为选中的API自动生成测试用例，覆盖功能、参数校验、边界值、异常等维度，并自动执行与修复",
        graph=build_graph(),
        intent_keywords=["用例生成", "测试用例", "生成用例", "接口测试", "API测试", "api测试", "test case", "testcase"],
        icon="el-icon-document",
        node_labels={
            "select_apis": "选取接口", "case_generate": "生成用例",
            "case_run": "执行测试", "case_update": "修复用例", "final_report": "生成报告",
        },
    ))
    logger.info("CaseGenAgent registered")

register()
