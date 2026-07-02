"""
微调积累器 - Claw化"越用越聪明"积累组件

V1.0版本
创建日期: 2026-04-08
最后更新: 2026-04-08

核心功能:
1. 积累每次生成的评分修正经验（哪些维度需调整策略）
2. 记录Prompt优化历史（优化前后的评分对比）
3. 维度级策略权重自适应调整
4. 生成微调摘要报告

设计参考:
- 经验文档/11.4Claw化实际运行说明✅️.md
- core/score_history_analyzer.py（评分趋势分析）
- core/prompt_optimizer.py（Prompt优化）

使用示例:
    from core.fine_tuning_accumulator import FineTuningAccumulator
    
    accumulator = FineTuningAccumulator(workspace_root=Path("E:/project"))
    
    # 记录一次评分结果
    accumulator.record_scores(
        chapter_id="ch01",
        dimension_scores={"style": 0.85, "character": 0.72, "worldview": 0.60},
        weighted_total=0.75,
        passed=False
    )
    
    # 记录Prompt优化效果
    accumulator.record_prompt_optimization(
        dimension="worldview",
        old_score=0.60,
        new_score=0.78,
        optimization_desc="增强世界观关键词匹配权重"
    )
    
    # 获取维度策略建议
    suggestions = accumulator.get_dimension_suggestions()
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)


@dataclass
class ScoreRecord:
    """评分记录"""
    id: Optional[int] = None
    chapter_id: str = ""
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    weighted_total: float = 0.0
    passed: bool = False
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class PromptOptimizationRecord:
    """Prompt优化记录"""
    id: Optional[int] = None
    dimension: str = ""
    old_score: float = 0.0
    new_score: float = 0.0
    score_delta: float = 0.0
    optimization_desc: str = ""
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        self.score_delta = self.new_score - self.old_score


@dataclass
class DimensionStrategy:
    """维度策略"""
    dimension: str = ""
    adjustment_factor: float = 1.0  # 调整因子（>1加强，<1减弱）
    priority_boost: float = 0.0     # 优先级提升
    success_count: int = 0          # 优化成功次数
    fail_count: int = 0             # 优化失败次数
    last_adjusted: str = ""


class FineTuningAccumulator:
    """
    微调积累器
    
    从评分历史和Prompt优化效果中积累经验：
    1. 记录每次评分结果（维度分数、总分、是否达标）
    2. 记录Prompt优化效果（优化前后评分对比）
    3. 基于历史数据调整维度策略权重
    4. 生成微调摘要报告
    """
    
    # 九维度标准定义（与quality-validator-v1对齐）
    DIMENSIONS = [
        'worldview', 'character', 'outline', 'style',
        'knowledge', 'writing_technique', 'word_count',
        'context_coherence', 'ai_feeling'
    ]
    
    # 维度中文映射
    DIMENSION_LABELS = {
        'worldview': '世界观', 'character': '人设', 'outline': '大纲',
        'style': '风格', 'knowledge': '知识库', 'writing_technique': '写作技巧',
        'word_count': '字数', 'context_coherence': '上下文衔接', 'ai_feeling': 'AI感',
    }
    
    # 维度默认权重（与quality-validator-v1对齐）
    DEFAULT_WEIGHTS = {
        'worldview': 0.12, 'character': 0.19, 'outline': 0.13,
        'style': 0.19, 'knowledge': 0.08, 'writing_technique': 0.08,
        'word_count': 0.08, 'context_coherence': 0.08, 'ai_feeling': 0.05,
    }
    
    def __init__(self, workspace_root: Optional[Path] = None):
        """
        初始化微调积累器
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(".")
        self.db_path = self.workspace_root / "data" / "fine_tuning.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._lock = threading.Lock()
        self._strategies: Dict[str, DimensionStrategy] = {}
        
        self._init_database()
        self._load_strategies()
        
        logger.info(f"FineTuningAccumulator initialized with db: {self.db_path}")
    
    def _init_database(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 评分记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS score_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter_id TEXT NOT NULL,
                    dimension_scores TEXT NOT NULL,
                    weighted_total REAL NOT NULL,
                    passed INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            # Prompt优化记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prompt_optimization_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dimension TEXT NOT NULL,
                    old_score REAL NOT NULL,
                    new_score REAL NOT NULL,
                    score_delta REAL NOT NULL,
                    optimization_desc TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                )
            """)
            
            # 维度策略表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dimension_strategies (
                    dimension TEXT PRIMARY KEY,
                    adjustment_factor REAL DEFAULT 1.0,
                    priority_boost REAL DEFAULT 0.0,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    last_adjusted TEXT DEFAULT ''
                )
            """)
            
            conn.commit()
    
    def _load_strategies(self):
        """从数据库加载维度策略"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT dimension, adjustment_factor, priority_boost, success_count, fail_count, last_adjusted FROM dimension_strategies")
            for row in cursor.fetchall():
                self._strategies[row[0]] = DimensionStrategy(
                    dimension=row[0],
                    adjustment_factor=row[1],
                    priority_boost=row[2],
                    success_count=row[3],
                    fail_count=row[4],
                    last_adjusted=row[5],
                )
        
        # 确保所有维度都有策略
        for dim in self.DIMENSIONS:
            if dim not in self._strategies:
                self._strategies[dim] = DimensionStrategy(dimension=dim)
    
    # ===== 公共接口 =====
    
    def record_scores(self, chapter_id: str, dimension_scores: Dict[str, float],
                      weighted_total: float, passed: bool) -> ScoreRecord:
        """
        记录一次评分结果
        
        Args:
            chapter_id: 章节ID
            dimension_scores: 各维度分数
            weighted_total: 加权总分
            passed: 是否达标
            
        Returns:
            评分记录
        """
        record = ScoreRecord(
            chapter_id=chapter_id,
            dimension_scores=dimension_scores,
            weighted_total=weighted_total,
            passed=passed,
        )
        
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO score_records (chapter_id, dimension_scores, weighted_total, passed, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    record.chapter_id,
                    json.dumps(record.dimension_scores, ensure_ascii=False),
                    record.weighted_total,
                    1 if record.passed else 0,
                    record.timestamp,
                ))
                record.id = cursor.lastrowid
                conn.commit()
        
        # 自动调整策略
        self._auto_adjust_strategies(dimension_scores, passed)
        
        logger.info(f"Recorded scores for {chapter_id}: total={weighted_total:.2f}, passed={passed}")
        return record
    
    def record_prompt_optimization(self, dimension: str, old_score: float,
                                   new_score: float, optimization_desc: str = "") -> PromptOptimizationRecord:
        """
        记录Prompt优化效果
        
        Args:
            dimension: 维度名
            old_score: 优化前评分
            new_score: 优化后评分
            optimization_desc: 优化描述
            
        Returns:
            优化记录
        """
        record = PromptOptimizationRecord(
            dimension=dimension,
            old_score=old_score,
            new_score=new_score,
            optimization_desc=optimization_desc,
        )
        
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO prompt_optimization_records (dimension, old_score, new_score, score_delta, optimization_desc, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    record.dimension,
                    record.old_score,
                    record.new_score,
                    record.score_delta,
                    record.optimization_desc,
                    record.timestamp,
                ))
                record.id = cursor.lastrowid
                conn.commit()
        
        # 更新维度策略
        self._update_strategy_from_optimization(dimension, record.score_delta)
        
        logger.info(f"Recorded optimization for {dimension}: {old_score:.2f} -> {new_score:.2f} (delta={record.score_delta:+.2f})")
        return record
    
    def get_dimension_suggestions(self, threshold: float = 0.75) -> List[Dict[str, Any]]:
        """
        获取维度策略建议
        
        Args:
            threshold: 薄弱维度阈值
            
        Returns:
            建议列表，按优先级排序
        """
        suggestions = []
        recent_scores = self._get_recent_dimension_averages(last_n=20)
        
        for dim in self.DIMENSIONS:
            avg_score = recent_scores.get(dim, 0.5)
            strategy = self._strategies.get(dim, DimensionStrategy(dimension=dim))
            label = self.DIMENSION_LABELS.get(dim, dim)
            
            if avg_score < threshold:
                # 薄弱维度：建议加强
                suggestions.append({
                    'dimension': dim,
                    'label': label,
                    'current_avg': round(avg_score, 3),
                    'adjustment_factor': strategy.adjustment_factor,
                    'priority_boost': strategy.priority_boost,
                    'suggestion': f"{label}维度平均分{avg_score:.2f}低于阈值{threshold}，建议增加Prompt权重（调整因子{strategy.adjustment_factor:.2f}）",
                    'severity': 'high' if avg_score < 0.6 else 'medium',
                })
            elif avg_score > 0.9:
                # 优势维度：可适当释放资源
                suggestions.append({
                    'dimension': dim,
                    'label': label,
                    'current_avg': round(avg_score, 3),
                    'adjustment_factor': strategy.adjustment_factor,
                    'priority_boost': strategy.priority_boost,
                    'suggestion': f"{label}维度平均分{avg_score:.2f}优秀，可适当降低Prompt关注度，将资源分配给薄弱维度",
                    'severity': 'low',
                })
        
        # 按严重程度排序
        severity_order = {'high': 0, 'medium': 1, 'low': 2}
        suggestions.sort(key=lambda x: (severity_order.get(x['severity'], 3), x['current_avg']))
        
        return suggestions
    
    def get_adjusted_weights(self) -> Dict[str, float]:
        """
        获取调整后的维度权重
        
        基于历史评分趋势和优化效果，对默认权重进行微调。
        调整幅度限制在默认权重的±30%范围内。
        
        Returns:
            调整后的权重字典（总和=1.0）
        """
        adjusted = {}
        for dim in self.DIMENSIONS:
            default_w = self.DEFAULT_WEIGHTS.get(dim, 0.08)
            strategy = self._strategies.get(dim, DimensionStrategy(dimension=dim))
            # 调整因子限制在0.7-1.3范围内（±30%）
            factor = max(0.7, min(1.3, strategy.adjustment_factor))
            adjusted[dim] = default_w * factor
        
        # 归一化使总和=1.0
        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: round(v / total, 4) for k, v in adjusted.items()}
        
        return adjusted
    
    def get_optimization_history(self, dimension: Optional[str] = None,
                                 limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取Prompt优化历史
        
        Args:
            dimension: 指定维度（None=全部）
            limit: 最大记录数
            
        Returns:
            优化历史列表
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if dimension:
                cursor.execute("""
                    SELECT dimension, old_score, new_score, score_delta, optimization_desc, timestamp
                    FROM prompt_optimization_records
                    WHERE dimension = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (dimension, limit))
            else:
                cursor.execute("""
                    SELECT dimension, old_score, new_score, score_delta, optimization_desc, timestamp
                    FROM prompt_optimization_records
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'dimension': row[0],
                    'label': self.DIMENSION_LABELS.get(row[0], row[0]),
                    'old_score': row[1],
                    'new_score': row[2],
                    'score_delta': row[3],
                    'optimization_desc': row[4],
                    'timestamp': row[5],
                })
            return results
    
    def generate_report(self, last_n: int = 30) -> Dict[str, Any]:
        """
        生成微调摘要报告
        
        Args:
            last_n: 分析最近N条记录
            
        Returns:
            报告字典
        """
        # 1. 评分趋势
        recent_averages = self._get_recent_dimension_averages(last_n)
        
        # 2. 达标率
        pass_rate = self._get_pass_rate(last_n)
        
        # 3. 优化效果统计
        optimization_stats = self._get_optimization_stats()
        
        # 4. 维度策略
        strategies = {}
        for dim in self.DIMENSIONS:
            s = self._strategies.get(dim, DimensionStrategy(dimension=dim))
            strategies[dim] = {
                'label': self.DIMENSION_LABELS.get(dim, dim),
                'adjustment_factor': round(s.adjustment_factor, 3),
                'priority_boost': round(s.priority_boost, 3),
                'success_count': s.success_count,
                'fail_count': s.fail_count,
                'success_rate': round(s.success_count / max(s.success_count + s.fail_count, 1), 3),
            }
        
        # 5. 调整后权重
        adjusted_weights = self.get_adjusted_weights()
        
        # 6. 建议
        suggestions = self.get_dimension_suggestions()
        
        return {
            'report_time': datetime.now().isoformat(),
            'analysis_range': f'最近{last_n}条记录',
            'pass_rate': round(pass_rate, 3),
            'dimension_averages': {self.DIMENSION_LABELS.get(k, k): round(v, 3) for k, v in recent_averages.items()},
            'optimization_stats': optimization_stats,
            'strategies': strategies,
            'adjusted_weights': {self.DIMENSION_LABELS.get(k, k): round(v, 4) for k, v in adjusted_weights.items()},
            'suggestions': suggestions,
        }
    
    # ===== 内部方法 =====
    
    def _auto_adjust_strategies(self, dimension_scores: Dict[str, float], passed: bool):
        """
        基于评分结果自动调整维度策略
        
        规则:
        - 达标：轻微降低弱维度优先级提升
        - 未达标：增强低分维度的调整因子和优先级
        """
        with self._lock:
            for dim, score in dimension_scores.items():
                if dim not in self._strategies:
                    self._strategies[dim] = DimensionStrategy(dimension=dim)
                
                strategy = self._strategies[dim]
                
                if not passed and score < 0.7:
                    # 低分维度：增强调整因子
                    strategy.adjustment_factor = min(1.3, strategy.adjustment_factor + 0.02)
                    strategy.priority_boost = min(0.5, strategy.priority_boost + 0.05)
                    strategy.fail_count += 1
                elif score >= 0.8:
                    # 高分维度：轻微回调
                    strategy.adjustment_factor = max(0.85, strategy.adjustment_factor - 0.01)
                    strategy.priority_boost = max(0.0, strategy.priority_boost - 0.02)
                    strategy.success_count += 1
                
                strategy.last_adjusted = datetime.now().isoformat()
            
            # 持久化策略
            self._save_strategies()
    
    def _update_strategy_from_optimization(self, dimension: str, score_delta: float):
        """从Prompt优化结果更新策略"""
        with self._lock:
            if dimension not in self._strategies:
                self._strategies[dimension] = DimensionStrategy(dimension=dimension)
            
            strategy = self._strategies[dimension]
            
            if score_delta > 0.05:
                # 优化有效：进一步增大调整因子
                strategy.adjustment_factor = min(1.3, strategy.adjustment_factor + 0.03)
                strategy.success_count += 1
            elif score_delta < -0.05:
                # 优化反效果：回退调整因子
                strategy.adjustment_factor = max(0.7, strategy.adjustment_factor - 0.05)
                strategy.fail_count += 1
            
            strategy.last_adjusted = datetime.now().isoformat()
            self._save_strategies()
    
    def _save_strategies(self):
        """持久化策略到数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for dim, strategy in self._strategies.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO dimension_strategies 
                    (dimension, adjustment_factor, priority_boost, success_count, fail_count, last_adjusted)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    strategy.dimension,
                    strategy.adjustment_factor,
                    strategy.priority_boost,
                    strategy.success_count,
                    strategy.fail_count,
                    strategy.last_adjusted,
                ))
            conn.commit()
    
    def _get_recent_dimension_averages(self, last_n: int = 20) -> Dict[str, float]:
        """获取最近N条记录的维度平均分"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT dimension_scores FROM score_records
                ORDER BY timestamp DESC
                LIMIT ?
            """, (last_n,))
            
            dimension_totals: Dict[str, float] = {}
            dimension_counts: Dict[str, int] = {}
            
            for row in cursor.fetchall():
                try:
                    scores = json.loads(row[0])
                except (json.JSONDecodeError, TypeError):
                    continue
                
                for dim, val in scores.items():
                    dimension_totals[dim] = dimension_totals.get(dim, 0.0) + val
                    dimension_counts[dim] = dimension_counts.get(dim, 0) + 1
            
            return {dim: dimension_totals.get(dim, 0) / max(dimension_counts.get(dim, 1), 1)
                    for dim in self.DIMENSIONS}
    
    def _get_pass_rate(self, last_n: int = 30) -> float:
        """获取最近N条记录的达标率"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT passed FROM score_records
                ORDER BY timestamp DESC
                LIMIT ?
            """, (last_n,))
            
            rows = cursor.fetchall()
            if not rows:
                return 0.0
            
            passed = sum(1 for r in rows if r[0])
            return passed / len(rows)
    
    def _get_optimization_stats(self) -> Dict[str, Any]:
        """获取优化效果统计"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*), AVG(score_delta) FROM prompt_optimization_records")
            row = cursor.fetchone()
            total_optimizations = row[0] or 0
            avg_delta = row[1] or 0.0
            
            cursor.execute("SELECT COUNT(*) FROM prompt_optimization_records WHERE score_delta > 0")
            positive_count = cursor.fetchone()[0] or 0
            
            cursor.execute("""
                SELECT dimension, AVG(score_delta) 
                FROM prompt_optimization_records 
                GROUP BY dimension
            """)
            dim_deltas = {row[0]: round(row[1], 3) for row in cursor.fetchall()}
        
        return {
            'total_optimizations': total_optimizations,
            'avg_score_delta': round(avg_delta, 3),
            'positive_rate': round(positive_count / max(total_optimizations, 1), 3),
            'dimension_deltas': {self.DIMENSION_LABELS.get(k, k): v for k, v in dim_deltas.items()},
        }
