"""
风格学习器插件包 V5

深度风格分析，提供词汇特征、句式模式、修辞手法、情感色彩、语言风格等全方位分析。
"""

from .plugin import StyleLearnerPlugin, get_plugin_class, register_plugin

__all__ = ["StyleLearnerPlugin", "get_plugin_class", "register_plugin"]

# 插件版本
__version__ = "5.0.0"
