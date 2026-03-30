"""
专家模式插件 - 小说创作专家

版本: 1.0.0
创建日期: 2026-03-29

核心功能:
1. 九维度智能评分
2. 切实可执行的优化建议
3. Claw记忆集成（越用越聪明）
4. 本地模型辅助评分
5. 【本章完】强制检查

设计原则:
- 轻量化可插拔：延迟加载，不增加启动负担
- 增强不替换：调用现有生成器，不破坏现有流程
- 继承不冲突：复用V5核心模块保护机制
"""

from .plugin import ExpertPlugin
from .validator import ExpertValidator
from .optimizer import ExpertOptimizer
from .memory import ExpertMemory
from .local_model import LocalModelAssistant
from .models import ExpertEvaluation, OptimizationSuggestion

__version__ = "1.0.0"
__author__ = "Agent Pro Team"

__all__ = [
    "ExpertPlugin",
    "ExpertValidator", 
    "ExpertOptimizer",
    "ExpertMemory",
    "LocalModelAssistant",
    "ExpertEvaluation",
    "OptimizationSuggestion"
]
