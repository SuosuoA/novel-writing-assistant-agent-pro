"""
评分历史分析器 - Claw化"越用越聪明"分析组件

V1.0版本
创建日期：2026-03-26

核心功能：
1. 追踪评分趋势（上升/下降/稳定）
2. 识别薄弱维度（平均分<阈值）
3. 分析评分分布（标准差/变异系数）
4. 预测评分走势（线性回归）
5. 生成可视化报告

设计参考：
- 经验文档/11.4Claw化实际运行说明✅️.md
- V5评分反馈循环（V1.7版本 - 8维度）

使用示例：
    # 创建分析器实例
    analyzer = ScoreHistoryAnalyzer(workspace_root=Path("E:/project"))
    
    # 分析评分趋势
    report = analyzer.generate_report(last_n=20)
    
    # 识别薄弱维度
    weak_dims = analyzer.identify_weak_dimensions(threshold=0.75)
    
    # 预测下个评分
    prediction = analyzer.predict_next_score("风格")
"""

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Pydantic数据模型
# ============================================================================


class DimensionStats(BaseModel):
    """维度统计数据模型"""
    
    model_config = ConfigDict(frozen=False)
    
    dimension: str = Field(description="维度名称")
    count: int = Field(description="样本数")
    mean: float = Field(description="平均值")
    std: float = Field(description="标准差")
    min_val: float = Field(description="最小值")
    max_val: float = Field(description="最大值")
    trend: str = Field(description="趋势（up/down/stable）")
    trend_slope: float = Field(description="趋势斜率")
    cv: float = Field(description="变异系数")


class ScoreReport(BaseModel):
    """评分报告数据模型"""
    
    model_config = ConfigDict(frozen=False)
    
    report_id: str = Field(description="报告ID")
    timestamp: str = Field(description="生成时间")
    total_samples: int = Field(description="总样本数")
    overall_avg: float = Field(description="总体平均分")
    dimension_stats: Dict[str, DimensionStats] = Field(default_factory=dict)
    weak_dimensions: List[str] = Field(default_factory=list)
    strong_dimensions: List[str] = Field(default_factory=list)
    predictions: Dict[str, float] = Field(default_factory=dict)
    recommendations: List[str] = Field(default_factory=list)


# ============================================================================
# 评分历史分析器
# ============================================================================


class ScoreHistoryAnalyzer:
    """
    评分历史分析器
    
    负责：
    1. 追踪评分趋势
    2. 识别薄弱维度
    3. 分析评分分布
    4. 预测评分走势
    5. 生成可视化报告
    """
    
    # 评分维度列表（V1.7版本 - 8维度）
    SCORE_DIMENSIONS = [
        "字数", "知识点引用", "大纲", "风格", 
        "人设", "世界观", "逆向反馈", "自然度"
    ]
    
    # 趋势判断阈值
    TREND_THRESHOLD = 0.05  # 5%变化
    
    def __init__(self, workspace_root: Path = None):
        """
        初始化评分历史分析器
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = workspace_root or Path.cwd()
        self.logger = logging.getLogger(__name__)
        
        # 数据库路径
        self.data_dir = self.workspace_root / "data" / "learning"
        self.db_path = self.data_dir / "learning_loop.db"
        
        # 线程锁
        self._lock = threading.RLock()
        
        self.logger.info(f"ScoreHistoryAnalyzer initialized: {self.workspace_root}")
    
    def get_dimension_scores(
        self, 
        dimension: str, 
        limit: int = 50
    ) -> List[Tuple[str, float]]:
        """
        获取某维度的评分历史
        
        Args:
            dimension: 维度名称
            limit: 最大返回数量
            
        Returns:
            [(timestamp, score), ...] 列表
        """
        scores = []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, score FROM score_history
                    WHERE dimension = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                """, (dimension, limit))
                
                scores = [(row[0], row[1]) for row in cursor.fetchall()]
                
        except Exception as e:
            self.logger.error(f"Failed to get dimension scores: {e}")
        
        return scores
    
    def calculate_dimension_stats(
        self, 
        dimension: str, 
        last_n: int = 20
    ) -> Optional[DimensionStats]:
        """
        计算维度统计数据
        
        Args:
            dimension: 维度名称
            last_n: 分析最近N条记录
            
        Returns:
            维度统计数据
        """
        try:
            scores = self.get_dimension_scores(dimension, last_n)
            
            if len(scores) < 2:
                return None
            
            # 提取分数值
            values = [s[1] for s in scores]
            n = len(values)
            
            # 计算统计量
            mean = sum(values) / n
            
            # 标准差
            variance = sum((x - mean) ** 2 for x in values) / n
            std = variance ** 0.5
            
            # 变异系数
            cv = std / mean if mean > 0 else 0
            
            # 趋势斜率（简单线性回归）
            x = list(range(n))
            y = values
            
            x_mean = sum(x) / n
            y_mean = mean
            
            numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
            denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
            
            slope = numerator / denominator if denominator != 0 else 0
            
            # 判断趋势
            if slope > self.TREND_THRESHOLD / n:
                trend = "up"
            elif slope < -self.TREND_THRESHOLD / n:
                trend = "down"
            else:
                trend = "stable"
            
            return DimensionStats(
                dimension=dimension,
                count=n,
                mean=mean,
                std=std,
                min_val=min(values),
                max_val=max(values),
                trend=trend,
                trend_slope=slope,
                cv=cv
            )
            
        except Exception as e:
            self.logger.error(f"Failed to calculate dimension stats: {e}")
            return None
    
    def identify_weak_dimensions(
        self, 
        threshold: float = 0.75,
        last_n: int = 10
    ) -> List[Tuple[str, float]]:
        """
        识别薄弱维度
        
        Args:
            threshold: 薄弱阈值
            last_n: 分析最近N条记录
            
        Returns:
            [(维度名, 平均分), ...] 按平均分升序排列
        """
        weak_dims = []
        
        for dimension in self.SCORE_DIMENSIONS:
            stats = self.calculate_dimension_stats(dimension, last_n)
            
            if stats and stats.mean < threshold:
                weak_dims.append((dimension, stats.mean))
        
        # 按平均分升序排列
        weak_dims.sort(key=lambda x: x[1])
        
        return weak_dims
    
    def identify_strong_dimensions(
        self, 
        threshold: float = 0.85,
        last_n: int = 10
    ) -> List[Tuple[str, float]]:
        """
        识别强势维度
        
        Args:
            threshold: 强势阈值
            last_n: 分析最近N条记录
            
        Returns:
            [(维度名, 平均分), ...] 按平均分降序排列
        """
        strong_dims = []
        
        for dimension in self.SCORE_DIMENSIONS:
            stats = self.calculate_dimension_stats(dimension, last_n)
            
            if stats and stats.mean >= threshold:
                strong_dims.append((dimension, stats.mean))
        
        # 按平均分降序排列
        strong_dims.sort(key=lambda x: x[1], reverse=True)
        
        return strong_dims
    
    def predict_next_score(self, dimension: str) -> Optional[float]:
        """
        预测下一个评分（简单线性回归）
        
        Args:
            dimension: 维度名称
            
        Returns:
            预测分数
        """
        try:
            scores = self.get_dimension_scores(dimension, 20)
            
            if len(scores) < 3:
                return None
            
            # 线性回归预测
            n = len(scores)
            x = list(range(n))
            y = [s[1] for s in scores]
            
            x_mean = sum(x) / n
            y_mean = sum(y) / n
            
            numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
            denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
            
            slope = numerator / denominator if denominator != 0 else 0
            intercept = y_mean - slope * x_mean
            
            # 预测下一个值
            next_x = n
            prediction = slope * next_x + intercept
            
            # 限制在0-1范围
            prediction = max(0.0, min(1.0, prediction))
            
            return prediction
            
        except Exception as e:
            self.logger.error(f"Failed to predict next score: {e}")
            return None
    
    def generate_report(self, last_n: int = 20) -> ScoreReport:
        """
        生成评分报告
        
        Args:
            last_n: 分析最近N条记录
            
        Returns:
            评分报告
        """
        report_id = f"report_{int(time.time()*1000)}"
        timestamp = datetime.now().isoformat()
        
        # 计算各维度统计
        dimension_stats = {}
        for dimension in self.SCORE_DIMENSIONS:
            stats = self.calculate_dimension_stats(dimension, last_n)
            if stats:
                dimension_stats[dimension] = stats
        
        # 计算总体平均分
        if dimension_stats:
            overall_avg = sum(s.mean for s in dimension_stats.values()) / len(dimension_stats)
        else:
            overall_avg = 0.0
        
        # 识别薄弱和强势维度
        weak_dims = self.identify_weak_dimensions(last_n=last_n)
        strong_dims = self.identify_strong_dimensions(last_n=last_n)
        
        # 预测各维度分数
        predictions = {}
        for dimension in self.SCORE_DIMENSIONS:
            pred = self.predict_next_score(dimension)
            if pred is not None:
                predictions[dimension] = pred
        
        # 生成建议
        recommendations = []
        
        for dim, score in weak_dims[:3]:
            recommendations.append(
                f"【{dim}】维度平均分{score:.2f}偏低，建议："
                f"检查相关配置或增加该维度的权重"
            )
        
        for dim, stats in dimension_stats.items():
            if stats.trend == "down":
                recommendations.append(
                    f"【{dim}】维度呈下降趋势，需关注"
                )
        
        # 统计总样本数
        total_samples = sum(s.count for s in dimension_stats.values())
        
        return ScoreReport(
            report_id=report_id,
            timestamp=timestamp,
            total_samples=total_samples,
            overall_avg=overall_avg,
            dimension_stats=dimension_stats,
            weak_dimensions=[d[0] for d in weak_dims],
            strong_dimensions=[d[0] for d in strong_dims],
            predictions=predictions,
            recommendations=recommendations
        )
    
    def export_report_markdown(self, report: ScoreReport) -> str:
        """
        导出Markdown格式报告
        
        Args:
            report: 评分报告
            
        Returns:
            Markdown文本
        """
        lines = [
            f"# 评分历史分析报告",
            "",
            f"> **生成时间**: {report.timestamp}",
            f"> **总样本数**: {report.total_samples}",
            f"> **总体平均分**: {report.overall_avg:.2%}",
            "",
            "## 各维度统计",
            "",
            "| 维度 | 平均分 | 标准差 | 趋势 | 样本数 |",
            "|------|:------:|:------:|:----:|:------:|",
        ]
        
        for dim, stats in report.dimension_stats.items():
            trend_icon = {"up": "📈", "down": "📉", "stable": "➡️"}.get(stats.trend, "➡️")
            lines.append(
                f"| {dim} | {stats.mean:.2%} | {stats.std:.2%} | "
                f"{trend_icon} {stats.trend} | {stats.count} |"
            )
        
        if report.weak_dimensions:
            lines.extend([
                "",
                "## 薄弱维度",
                "",
                "以下维度平均分低于0.75，需要重点关注：",
                "",
            ])
            for dim in report.weak_dimensions:
                lines.append(f"- **{dim}**")
        
        if report.strong_dimensions:
            lines.extend([
                "",
                "## 强势维度",
                "",
                "以下维度表现优秀：",
                "",
            ])
            for dim in report.strong_dimensions:
                lines.append(f"- **{dim}**")
        
        if report.predictions:
            lines.extend([
                "",
                "## 下次预测",
                "",
                "| 维度 | 预测分数 |",
                "|------|:--------:|",
            ])
            for dim, pred in report.predictions.items():
                lines.append(f"| {dim} | {pred:.2%} |")
        
        if report.recommendations:
            lines.extend([
                "",
                "## 改进建议",
                "",
            ])
            for rec in report.recommendations:
                lines.append(f"- {rec}")
        
        lines.append("")
        return "\n".join(lines)
    
    # 兼容性别名方法
    def record_score(self, dimension: str, score: float, chapter_id: str = None) -> None:
        """
        记录评分（兼容性别名）
        
        Args:
            dimension: 维度名称
            score: 评分
            chapter_id: 章节ID
        """
        # 此方法由LearningLoopManager.collect_generation_data()实现
        # 这里仅提供接口兼容性
        pass
    
    def get_trend(self, dimension: str) -> str:
        """
        获取维度趋势（兼容性别名）
        
        Args:
            dimension: 维度名称
            
        Returns:
            趋势字符串（up/down/stable）
        """
        stats = self.calculate_dimension_stats(dimension)
        return stats.trend if stats else "stable"
    
    def get_average_score(self, dimension: str, last_n: int = 20) -> float:
        """
        获取维度平均分（兼容性别名）
        
        Args:
            dimension: 维度名称
            last_n: 最近N条记录
            
        Returns:
            平均分
        """
        stats = self.calculate_dimension_stats(dimension, last_n)
        return stats.mean if stats else 0.0


# ============================================================================
# 全局单例
# ============================================================================

_analyzer: Optional[ScoreHistoryAnalyzer] = None
_analyzer_lock = threading.Lock()


def get_score_history_analyzer(workspace_root: Path = None) -> ScoreHistoryAnalyzer:
    """获取评分历史分析器单例"""
    global _analyzer
    
    with _analyzer_lock:
        if _analyzer is None:
            _analyzer = ScoreHistoryAnalyzer(workspace_root)
        return _analyzer
