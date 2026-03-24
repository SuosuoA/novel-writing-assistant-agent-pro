"""
小说生成器插件 V3

整合上下文构建、迭代生成、加权验证的完整流程。
"""

from .plugin import NovelGeneratorPlugin, GenerationStrategy, get_plugin_class, register_plugin

__all__ = ["NovelGeneratorPlugin", "GenerationStrategy", "get_plugin_class", "register_plugin"]
