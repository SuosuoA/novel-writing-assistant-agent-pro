"""
V5模块适配器

V2.0版本
创建日期: 2026-03-21

将V5核心模块包装为Agent能力:
- OutlineParserAdapter: 大纲解析器
- StyleLearnerAdapter: 风格学习器
- CharacterManagerAdapter: 人物管理器
- WorldviewParserAdapter: 世界观解析器
- ContextBuilderAdapter: 上下文构建器
- IterativeGeneratorAdapter: 迭代生成器
- WeightedValidatorAdapter: 加权验证器
"""

from .outline_adapter import OutlineParserAdapter
from .style_adapter import StyleLearnerAdapter
from .character_adapter import CharacterManagerAdapter
from .worldview_adapter import WorldviewParserAdapter
from .context_adapter import ContextBuilderAdapter
from .generator_adapter import IterativeGeneratorAdapter
from .validator_adapter import WeightedValidatorAdapter

__all__ = [
    "OutlineParserAdapter",
    "StyleLearnerAdapter",
    "CharacterManagerAdapter",
    "WorldviewParserAdapter",
    "ContextBuilderAdapter",
    "IterativeGeneratorAdapter",
    "WeightedValidatorAdapter",
]
