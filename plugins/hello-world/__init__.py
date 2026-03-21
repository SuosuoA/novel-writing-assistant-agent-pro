"""
Hello World插件包

示例ToolPlugin实现，用于验证插件系统流程。
"""

from .plugin import HelloWorldPlugin, get_plugin_class, register_plugin

__all__ = [
    "HelloWorldPlugin",
    "get_plugin_class",
    "register_plugin"
]

# 插件版本
__version__ = "1.0.0"
