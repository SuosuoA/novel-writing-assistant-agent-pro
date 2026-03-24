"""
大纲解析器插件包 V3

基于LangChain和LLM的智能大纲解析。
"""

from .plugin import OutlineParserPlugin, get_plugin_class, register_plugin

__all__ = ["OutlineParserPlugin", "get_plugin_class", "register_plugin"]

# 插件版本
__version__ = "3.0.0"
