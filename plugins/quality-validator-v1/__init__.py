"""
质量验证器插件 V1.0

版本: 1.0.0
创建日期: 2026-03-23
迁移来源: V5 scripts/enhanced_weighted_validator.py

功能:
- 6维度加权评分系统
- 字数符合性评分 (10%)
- 大纲符合性评分 (15%)
- 风格一致性评分 (25%)
- 人设一致性评分 (25%)
- 世界观一致性评分 (20%，一票否决)
- 自然度评分 (5%)

核心规则（强制保护）:
1. 章节结束必须添加【本章完】标记
2. 评分阈值 >= 0.8 才能输出
3. 迭代上限 5 次
4. 6维度评分权重固定
5. 世界观严重违背一票否决

参考文档:
- 《项目总体架构设计说明书V1.2》第四章
- 《插件接口定义V2.1》
"""

from .plugin import QualityValidatorPlugin, get_plugin_class, register_plugin

__all__ = ['QualityValidatorPlugin', 'get_plugin_class', 'register_plugin']
__version__ = '1.0.0'
