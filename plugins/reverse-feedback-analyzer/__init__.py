"""
逆向反馈分析插件包

V1.1版本
更新日期: 2026-03-24

分析已生成章节与项目设定（大纲、人物、世界观）的一致性，
利用AI进行深度语义比对，检测冲突并生成修正建议。

架构说明：
- plugin.py: 插件入口包装器（ReverseFeedbackAnalyzerPlugin）
- reverse_feedback_analyzer.py: 核心实现（ReverseFeedbackAnalyzer）
- settings_corrector.py: 设定修正生成器
"""

# 主入口类（插件包装器）
from .plugin import ReverseFeedbackAnalyzerPlugin

# 核心实现类（可供外部直接使用）
from .reverse_feedback_analyzer import (
    ReverseFeedbackAnalyzer,
    AnalysisCache,
    LLMAnalyzer,
)

# 修正生成器
from .settings_corrector import (
    SettingsCorrector,
    LLMCorrector,
    CorrectionResult,
    CorrectionReport,
    correct_single_issue,
    correct_batch_issues,
    settings_corrector,
)

__all__ = [
    # 插件入口（主要使用）
    "ReverseFeedbackAnalyzerPlugin",
    # 核心实现（可选直接使用）
    "ReverseFeedbackAnalyzer",
    "AnalysisCache",
    "LLMAnalyzer",
    # 修正器
    "SettingsCorrector",
    "LLMCorrector",
    "CorrectionResult",
    "CorrectionReport",
    "correct_single_issue",
    "correct_batch_issues",
    "settings_corrector",
]

# 插件版本（统一版本号）
__version__ = "1.1.0"
