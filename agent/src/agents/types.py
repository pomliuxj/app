# src/agents/types.py

from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class FeedbackType(str, Enum):
    """反馈类型枚举"""
    LIKE = "like"
    DISLIKE = "dislike"
    NONE = "none"  # 无反馈状态


class ExecutionStatus(str, Enum):
    """智能体执行状态枚举"""
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    RUNNING = "running"
    PENDING = "pending"


class AgentExecutionRecord(BaseModel):
    """智能体执行记录"""
    agent_name: str
    title: str = ""
    ent_id: str
    user_id: str
    user_role: Optional[str] = None
    thread_id: str
    task_id: str
    feedback_type: FeedbackType = FeedbackType.NONE
    status: ExecutionStatus = ExecutionStatus.RUNNING
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    tags: Optional[dict] = None
    execution_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_first_task: bool = False
