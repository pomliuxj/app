"""Multi-API scenario test generation sub-agent.

Graph topology::

    START → select_apis [interrupt] → scenario_design [interrupt]
          → scenario_generate → scenario_run → scenario_fix (retry≤5)
          → scenario_report → END
"""

import logging

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from src.framework.state import Ai_test_State
from src.shared.nodes import select_apis as _select_apis
from src.agents.scenario_gen.nodes import (
    scenario_design,
    scenario_generate,
    scenario_run,
    scenario_fix,
    scenario_report,
)
from src.framework import register_sub_agent, SubAgentDefinition

logger = logging.getLogger(__name__)


async def _select_apis_scenario(state: Ai_test_State) -> Command:
    """Wrapper: force routing to scenario_design within this sub-graph."""
    state["intent_type"] = "scenario_test_generation"
    result = await _select_apis(state)
    if hasattr(result, "goto") and result.goto not in (END, "scenario_design"):
        logger.warning("select_apis tried '%s' → forcing 'scenario_design'", result.goto)
        return Command(update=result.update, goto="scenario_design")
    return result


def build_graph() -> StateGraph:
    builder = StateGraph(Ai_test_State)
    builder.add_node("select_apis", _select_apis_scenario)
    builder.add_node("scenario_design", scenario_design)
    builder.add_node("scenario_generate", scenario_generate)
    builder.add_node("scenario_run", scenario_run)
    builder.add_node("scenario_fix", scenario_fix)
    builder.add_node("scenario_report", scenario_report)
    builder.add_edge(START, "select_apis")
    return builder.compile()


def register():
    register_sub_agent(SubAgentDefinition(
        agent_id="scenario_gen",
        name="场景用例生成",
        description="为多个关联API设计业务场景流程，自动生成步骤间参数关联的测试用例，支持场景执行与修复",
        graph=build_graph(),
        intent_keywords=["场景用例","场景测试","业务流程","端到端","链路测试","场景生成","多接口","scenario","end-to-end","flow test"],
        icon="el-icon-connection",
        node_labels={
            "select_apis":"选取接口","scenario_design":"设计场景",
            "scenario_generate":"生成场景用例","scenario_run":"执行场景",
            "scenario_fix":"修复场景","scenario_report":"场景报告",
        },
    ))
    logger.info("ScenarioAgent registered")

register()
