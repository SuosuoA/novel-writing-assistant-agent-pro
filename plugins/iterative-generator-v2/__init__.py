"""
迭代生成器插件 V2

迭代优化的章节生成器，支持评分反馈循环优化。
"""

from .plugin import IterativeGeneratorPlugin, get_plugin_class, register_plugin

__all__ = ["IterativeGeneratorPlugin", "get_plugin_class", "register_plugin"]
