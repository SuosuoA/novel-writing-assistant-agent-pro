"""
上下文构建器插件 V1

智能上下文构建器，基于RAG和智能检索构建优化的提示词。
"""

from .plugin import ContextBuilderPlugin, get_plugin_class, register_plugin

__all__ = ["ContextBuilderPlugin", "get_plugin_class", "register_plugin"]
