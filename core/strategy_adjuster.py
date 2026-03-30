"""
策略调整器 - 根据反馈自动优化生成策略

V1.0版本
创建日期: 2026-03-26

功能:
- 根据用户反馈优化生成策略
- 根据评分趋势调整权重
- 更新Prompt模板
- 记录调整历史

使用示例:
    from core.strategy_adjuster import StrategyAdjuster
    
    adjuster = StrategyAdjuster()
    
    # 根据反馈调整
    adjuster.adjust_from_feedback(feedback)
    
    # 根据评分趋势调整
    adjuster.adjust_from_score_trend(trend)
"""

import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
import json

logger = logging.getLogger(__name__)


@dataclass
class StrategyAdjustment:
    """策略调整记录"""
    id: Optional[int] = None
    adjustment_type: str = ""  # prompt / weight / template / knowledge_recall
    trigger: str = ""  # feedback / score_trend / manual
    reason: str = ""
    before_value: Dict[str, Any] = None
    after_value: Dict[str, Any] = None
    timestamp: str = ""
    
    def __post_init__(self):
        if self.before_value is None:
            self.before_value = {}
        if self.after_value is None:
            self.after_value = {}
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class StrategyAdjuster:
    """
    策略调整器
    
    功能:
    - 根据反馈优化生成策略
    - 调整评分权重
    - 更新Prompt模板
    - 记录调整历史
    """
    
    # 默认权重配置（V1.7版本 - 8维度）
    DEFAULT_WEIGHTS = {
        "字数": 0.08,
        "知识点引用": 0.08,
        "大纲": 0.13,
        "风格": 0.19,
        "人设": 0.19,
        "世界观": 0.12,
        "逆向反馈": 0.11,
        "自然度": 0.10
    }
    
    # 权重调整限制
    WEIGHT_ADJUSTMENT_LIMIT = 0.10  # 单次调整上限10%
    WEIGHT_MIN = 0.05  # 单个维度最低5%
    WEIGHT_MAX = 0.30  # 单个维度最高30%
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        初始化策略调整器
        
        Args:
            db_path: 数据库路径（默认为 data/strategy_adjustments.db）
        """
        if db_path is None:
            db_path = Path("data/strategy_adjustments.db")
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载当前权重配置
        self.current_weights = self._load_weights()
        
        self._init_database()
        logger.info(f"StrategyAdjuster initialized with db: {self.db_path}")
    
    def _init_database(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 创建调整记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_adjustments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    adjustment_type TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    before_value TEXT,
                    after_value TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_adjustment_type ON strategy_adjustments(adjustment_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON strategy_adjustments(timestamp)
            """)
            
            conn.commit()
    
    def _load_weights(self) -> Dict[str, float]:
        """加载权重配置"""
        # 尝试从文件加载
        weights_file = Path("config/weights.json")
        if weights_file.exists():
            try:
                with open(weights_file, 'r', encoding='utf-8') as f:
                    weights = json.load(f)
                    logger.info(f"Loaded weights from {weights_file}")
                    return weights
            except Exception as e:
                logger.warning(f"Failed to load weights: {e}")
        
        # 返回默认权重
        return self.DEFAULT_WEIGHTS.copy()
    
    def _save_weights(self):
        """保存权重配置"""
        weights_file = Path("config/weights.json")
        weights_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(weights_file, 'w', encoding='utf-8') as f:
            json.dump(self.current_weights, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved weights to {weights_file}")
    
    def adjust_from_feedback(self, feedback_type: str, feedback_text: str,
                            extracted_knowledge: Optional[Dict] = None) -> StrategyAdjustment:
        """
        根据用户反馈调整策略
        
        Args:
            feedback_type: 反馈类型（content/style/ai_feeling/other）
            feedback_text: 反馈文本
            extracted_knowledge: 提取的知识点
        
        Returns:
            调整记录
        """
        adjustment = StrategyAdjustment(
            adjustment_type="prompt",
            trigger="feedback",
            reason=f"用户反馈：{feedback_text[:50]}..."
        )
        
        if feedback_type == "style":
            # 风格问题：优化Prompt约束
            adjustment.before_value = {"prompt_constraints": []}
            adjustment.after_value = {
                "prompt_constraints": [
                    "对话要自然，符合人物性格，避免书面化表达",
                    "增加细节描写，形成画面感"
                ]
            }
            adjustment.reason = "风格反馈：优化对话和描写约束"
        
        elif feedback_type == "ai_feeling":
            # AI感问题：更新AI痕迹词库
            adjustment.adjustment_type = "template"
            adjustment.before_value = {"ai_feeling_words": []}
            adjustment.after_value = {
                "ai_feeling_words": ["仿佛", "似乎", "宛如", "如同"]
            }
            adjustment.reason = "AI感反馈：更新AI痕迹词库"
        
        elif feedback_type == "content":
            # 内容问题：增加知识召回
            adjustment.adjustment_type = "knowledge_recall"
            adjustment.before_value = {"recall_tags": []}
            adjustment.after_value = {
                "recall_tags": extracted_knowledge.get("tags", []) if extracted_knowledge else []
            }
            adjustment.reason = "内容反馈：增加相关知识召回"
        
        # 保存调整记录
        self._save_adjustment(adjustment)
        
        logger.info(f"Adjusted strategy from feedback: {adjustment.adjustment_type}")
        return adjustment
    
    def adjust_from_score_trend(self, dimension_scores: Dict[str, float],
                                threshold: float = 0.75) -> List[StrategyAdjustment]:
        """
        根据评分趋势调整权重
        
        Args:
            dimension_scores: 各维度平均分
            threshold: 低分阈值
        
        Returns:
            调整记录列表
        """
        adjustments = []
        
        # 识别薄弱维度
        weak_dims = [dim for dim, score in dimension_scores.items() if score < threshold]
        
        for dim in weak_dims:
            # 调整权重（+5%）
            before_weight = self.current_weights.get(dim, 0.1)
            after_weight = min(before_weight + 0.05, self.WEIGHT_MAX)
            
            # 确保总和为1.0
            other_dims = [d for d in self.current_weights if d != dim]
            other_total = sum(self.current_weights[d] for d in other_dims)
            
            adjustment = StrategyAdjustment(
                adjustment_type="weight",
                trigger="score_trend",
                reason=f"{dim}维度平均分{dimension_scores[dim]:.2f}低于阈值{threshold}",
                before_value={dim: before_weight},
                after_value={dim: after_weight}
            )
            
            # 更新权重
            self.current_weights[dim] = after_weight
            
            # 归一化其他维度
            if other_total > 0:
                scale = (1.0 - after_weight) / other_total
                for d in other_dims:
                    self.current_weights[d] = max(
                        self.current_weights[d] * scale,
                        self.WEIGHT_MIN
                    )
            
            # 保存调整记录
            self._save_adjustment(adjustment)
            adjustments.append(adjustment)
        
        # 保存权重配置
        if adjustments:
            self._save_weights()
        
        logger.info(f"Adjusted weights from score trend: {len(adjustments)} dimensions")
        return adjustments
    
    def get_optimized_prompt(self, base_prompt: str, 
                            knowledge_points: List[Dict] = None,
                            user_preferences: List[str] = None) -> str:
        """
        获取优化后的Prompt
        
        Args:
            base_prompt: 基础Prompt
            knowledge_points: 知识点列表
            user_preferences: 用户偏好列表
        
        Returns:
            优化后的Prompt
        """
        optimized = base_prompt
        
        # 添加知识约束
        if knowledge_points:
            constraints = []
            for kp in knowledge_points[:5]:  # 最多5个知识点
                constraints.append(f"- {kp.get('content', '')}")
            
            if constraints:
                optimized += "\n\n【写作要求】\n" + "\n".join(constraints)
        
        # 添加用户偏好
        if user_preferences:
            preferences = [f"- {pref}" for pref in user_preferences[:5]]
            if preferences:
                optimized += "\n\n【用户偏好】\n" + "\n".join(preferences)
        
        # 添加AI痕迹规避
        ai_words = ["仿佛", "似乎", "宛如", "如同", "不禁", "不由得", "忍不住"]
        if ai_words:
            optimized += "\n\n【避免使用】\n" + ", ".join(ai_words)
        
        return optimized
    
    def _save_adjustment(self, adjustment: StrategyAdjustment):
        """保存调整记录"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO strategy_adjustments 
                (adjustment_type, trigger, reason, before_value, after_value, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                adjustment.adjustment_type,
                adjustment.trigger,
                adjustment.reason,
                json.dumps(adjustment.before_value, ensure_ascii=False),
                json.dumps(adjustment.after_value, ensure_ascii=False),
                adjustment.timestamp
            ))
            
            adjustment.id = cursor.lastrowid
            conn.commit()
    
    def get_adjustment_history(self, limit: int = 20) -> List[StrategyAdjustment]:
        """获取调整历史"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM strategy_adjustments 
                ORDER BY timestamp DESC LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            
            adjustments = []
            for row in rows:
                adjustment = StrategyAdjustment(
                    id=row[0],
                    adjustment_type=row[1],
                    trigger=row[2],
                    reason=row[3],
                    before_value=json.loads(row[4]) if row[4] else {},
                    after_value=json.loads(row[5]) if row[5] else {},
                    timestamp=row[6]
                )
                adjustments.append(adjustment)
            
            return adjustments


# 全局单例
_strategy_adjuster_instance: Optional[StrategyAdjuster] = None


def get_strategy_adjuster(db_path: Optional[Path] = None) -> StrategyAdjuster:
    """获取策略调整器单例"""
    global _strategy_adjuster_instance
    if _strategy_adjuster_instance is None:
        _strategy_adjuster_instance = StrategyAdjuster(db_path)
    return _strategy_adjuster_instance
