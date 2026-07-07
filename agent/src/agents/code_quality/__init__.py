"""Code quality analysis sub-agent — demonstrates the extensibility of the framework.

Graph topology::

    START
      │
      ▼
    analyze_code  — LLM analyses provided code / repo for quality issues
      │
      ▼
    generate_report  — structured quality report with suggestions
      │
      ▼
    END
"""

import logging

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langchain_core.messages import HumanMessage, AIMessage

from src.framework import register_sub_agent, SubAgentDefinition

logger = logging.getLogger(__name__)


# ── Nodes ──────────────────────────────────────────────────────────────────
async def _analyze_code(state: dict) -> Command:
    """Analyse the provided code for quality issues."""
    from src.llms.llm import get_llm_by_type
    from src.config.agents import AGENT_LLM_MAP

    messages = state.get("messages", [])
    user_input = ""
    if messages:
        last = messages[-1]
        user_input = last.content if hasattr(last, "content") else str(last)

    llm = get_llm_by_type(AGENT_LLM_MAP.get("basic", "basic"))

    prompt = f"""你是一个代码质量分析专家。请分析以下代码的质量问题。

分析维度：
1. 代码规范（命名、格式、注释）
2. 潜在 Bug（空指针、边界条件、异常处理）
3. 性能问题（算法复杂度、资源泄露、重复计算）
4. 安全风险（注入攻击、敏感信息泄露、权限校验）
5. 可维护性（函数长度、耦合度、测试覆盖建议）

代码内容：
{user_input}

请以结构化 JSON 格式输出分析结果，包含：
- summary: 总体评价（1-2 句话）
- issues: 问题列表（每条包含 severity: high/medium/low, category, description, suggestion）
- score: 质量评分（0-100）"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        analysis = response.content
    except Exception:
        analysis = "代码分析失败，请稍后重试。"

    return Command(
        update={
            "messages": [AIMessage(content=analysis, name="analyze_code")],
            "code_analysis": analysis,
        },
        goto="generate_report",
    )


async def _generate_report(state: dict) -> Command:
    """Generate a final quality report."""
    from src.llms.llm import get_llm_by_type
    from src.config.agents import AGENT_LLM_MAP

    analysis = state.get("code_analysis", "无分析结果")

    llm = get_llm_by_type(AGENT_LLM_MAP.get("basic", "basic"))

    prompt = f"""基于以下分析结果，生成一份简洁的代码质量报告（中文，Markdown 格式）。

{analysis}

报告结构：
1. 总体评分
2. 主要问题
3. 改进建议
4. 下一步行动"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        report = response.content
    except Exception:
        report = "报告生成失败。"

    return Command(
        update={
            "messages": [AIMessage(content=report, name="generate_report")],
        },
        goto=END,
    )


# ── Build ──────────────────────────────────────────────────────────────────
def build_graph() -> StateGraph:
    """Build the compiled code quality analysis graph."""
    builder = StateGraph(dict)

    builder.add_node("analyze_code", _analyze_code)
    builder.add_node("generate_report", _generate_report)

    builder.add_edge(START, "analyze_code")
    builder.add_edge("generate_report", END)

    return builder.compile()


# ── Register ───────────────────────────────────────────────────────────────
def register():
    """Register this sub-agent with the framework."""
    register_sub_agent(
        SubAgentDefinition(
            agent_id="code_quality",
            name="代码质量分析",
            description="分析代码质量，检测 Bug、性能问题、安全风险，生成改进建议报告",
            graph=build_graph(),
            intent_keywords=[
                "代码质量", "代码分析", "代码审查", "code review",
                "代码检查", "质量分析", "代码规范",
                "code quality", "static analysis",
            ],
            icon="el-icon-monitor",
            node_labels={
                "analyze_code": "分析代码",
                "generate_report": "生成报告",
            },
        )
    )
    logger.info("CodeQualityAgent registered")


# Auto-register on import
register()
