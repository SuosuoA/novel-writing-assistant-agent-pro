"""
服务模块

V2.0版本
创建日期: 2026-03-21

包含:
- LLM客户端容错服务
- Prompt模板管理
- 上下文管理
"""

from .llm_client_with_resilience import LLMClientWithResilience, LLMProvider

__all__ = [
    "LLMClientWithResilience",
    "LLMProvider",
]
