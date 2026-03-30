#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识库验证器模块

负责批量检查和清理低质量、重复的知识词条。

模块组成：
- KnowledgeVerifierPlugin: 插件入口（ToolPlugin接口）
- KnowledgeVerifier: 主控制器
- DeduplicationEngine: 查重引擎
- QualityEvaluator: 质量评估器
- FileCleaner: 文件清理器
- ClawOptimizer: Claw优化集成

P3优化：
- ConfigLoader: 配置加载器（支持配置化阈值）
- StatsMonitor: 统计监控器（清理统计看板）
- ScheduledCleanupManager: 定期清理调度器
"""

from .knowledge_verifier import KnowledgeVerifier
from .deduplication_engine import DeduplicationEngine
from .quality_evaluator import QualityEvaluator, QualityScore
from .file_cleaner import FileCleaner
from .claw_optimizer import ClawOptimizer

# P3优化：新增模块
from .config_loader import (
    ConfigLoader,
    get_config_loader,
    get_similarity_threshold,
    get_overlap_threshold,
    get_quality_threshold,
    get_auto_delete_threshold,
    get_quality_weights
)
from .stats_monitor import (
    StatsMonitor,
    CleanupStats,
    ScheduledCleanupManager,
    get_stats_monitor,
    get_schedule_manager
)

__all__ = [
    'KnowledgeVerifier',
    'DeduplicationEngine',
    'QualityEvaluator',
    'QualityScore',
    'FileCleaner',
    'ClawOptimizer',
    # P3优化
    'ConfigLoader',
    'get_config_loader',
    'get_similarity_threshold',
    'get_overlap_threshold',
    'get_quality_threshold',
    'get_auto_delete_threshold',
    'get_quality_weights',
    'StatsMonitor',
    'CleanupStats',
    'ScheduledCleanupManager',
    'get_stats_monitor',
    'get_schedule_manager',
]

__version__ = '1.1.0'  # P3优化版本升级
__author__ = 'Novel Writing Assistant Team'
