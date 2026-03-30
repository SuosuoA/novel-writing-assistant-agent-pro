#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Novel Writing Assistant - Agent Pro
GUI模块包

该包包含所有UI面板和组件的独立实现，从gui_main.py外迁而来
以提高代码可维护性和降低主文件规模。

模块列表：
- hot_ranking_panel: 热榜面板
- knowledge_panel: 知识库面板
- generation_workbench: 生成工作台
- settings_panel: 设置面板
- progress_monitor: 进度监控
- feedback_panel: 反馈页面
- expert_selector: 专家选择器
- expert_evaluation: 专家评估对话框
"""

__version__ = "2.19"
__author__ = "Novel Writing Assistant Team"

# 延迟导入，避免循环依赖
__all__ = [
    'HotRankingPanel',
    'KnowledgePanel',
    'GenerationWorkbench',
    'SettingsPanel',
    'ProgressMonitor',
    'FeedbackPanel',
    'ExpertSelectorWidget',
    'ExpertEvaluationDialog',
]
