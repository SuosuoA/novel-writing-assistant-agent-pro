"""
续写生成器插件 V1.2

智能小说续写功能，支持多种续写方向和上下文智能感知。

V1.1新增：
- ProjectContextManager: 项目上下文管理器
- 自动读取项目设定（大纲/人设/世界观）
- 章节选择时自动加载前文概要，避免重复

V1.2新增：
- LLM调用超时保护机制（concurrent.futures强制超时）
- 自定义异常类型（LLMError/TimeoutError/AuthError/ConnectionError）
- 缓存持久化机制（save_to_disk/load_from_disk）
- 增强人物设定解析（支持JSON/YAML格式）
- 智能章节概要生成（关键词提取+句子选择）
- 魔法数字提取为类常量
"""

from .plugin import (
    ContinuationGeneratorPlugin,
    ProjectContextManager,
    ProjectContext,
    LLMError,
    LLMTimeoutError,
    LLMAuthenticationError,
    LLMConnectionError,
    LLMRateLimitError,
    get_plugin_class,
    register_plugin
)

__all__ = [
    "ContinuationGeneratorPlugin",
    "ProjectContextManager",
    "ProjectContext",
    "LLMError",
    "LLMTimeoutError",
    "LLMAuthenticationError",
    "LLMConnectionError",
    "LLMRateLimitError",
    "get_plugin_class",
    "register_plugin",
]
