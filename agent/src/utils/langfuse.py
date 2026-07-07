import os
import logging

logger = logging.getLogger(__name__)

langfuse_client = None
callback_handler = []

try:
    from langfuse import get_client
    from langfuse.langchain import CallbackHandler
except ImportError:
    get_client = None
    CallbackHandler = None
    logger.warning("Langfuse not available — tracing disabled")

if os.getenv("LANGFUSE_TRACING", False):
    if CallbackHandler is not None:
        callback_handler = [CallbackHandler()]
    else:
        logger.warning("LANGFUSE_TRACING enabled but langfuse.langchain.CallbackHandler not available")
if os.getenv("LANGFUSE_PUBLIC_KEY", None) and get_client is not None:
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_client = get_client(public_key=public_key)
