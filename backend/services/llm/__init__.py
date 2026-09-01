"""backend.services.llm — LLM model router 包.

隐式命名空间包补显式 ``__init__.py`` (存量 bug 清扫 C1: 与 ai_hub/dsh/triggers
保持一致, 避免显式列包的打包方式漏掉本包)。当前仅 model_router.py 一个模块,
消费者直接 ``from backend.services.llm.model_router import ...``。
"""
