"""
Agent插件模块

包含4个可被MasterAgent调度的Agent：
- OutlineAnalysisAgent: 大纲分析Agent，调用 outline-parser-v3 插件
- StyleLearningAgent: 风格学习Agent，调用 style-learner-v5 插件
- NovelGenerationAgent: 小说生成Agent，调用 novel-generator-v3 插件
- QualityValidationAgent: 质量验证Agent，调用 quality-validator-v1 插件

每个Agent实现Analyzer/Generator/Validator能力。
"""

from .outline_analysis_agent import OutlineAnalysisAgent
from .style_learning_agent import StyleLearningAgent
from .novel_generation_agent import NovelGenerationAgent
from .quality_validation_agent import QualityValidationAgent

__all__ = [
    "OutlineAnalysisAgent",
    "StyleLearningAgent", 
    "NovelGenerationAgent",
    "QualityValidationAgent",
]
