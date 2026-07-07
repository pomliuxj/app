
from langchain_core.runnables import RunnableLambda
import uuid
import logging
from langchain_core.messages import AIMessage


def function_validator(model_output):
    """
    修正模型输出中的tool_call_id为空的，解决ToolNode的 _validate_tool_call检验异常
    """
    try:
        logging.info(f"model_output {model_output}")

        if isinstance(model_output, dict) and model_output.get("messages"):
            # 判断最后一条消息是否为AIMessage
            if isinstance(model_output.get("messages")[-1], AIMessage):
                # 修正tool_call_id为none
                tool_calls = model_output.get("messages")[-1].tool_calls
                for tool_call in tool_calls:
                    if  not tool_call.get('id'):
                        tool_call["id"] = f'call_{uuid.uuid4().hex}'
                        logging.info(f"model tool_call_id is none,fix call_id {tool_call['id']}. ")
        return model_output
    except Exception as e:
        logging.error(f"Error detail: {e}")
        return model_output


# 使用示例
post_model_hook = RunnableLambda(function_validator)
