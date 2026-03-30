"""
冲突模式学习器 - Claw化"越用越聪明"学习组件

V1.0版本
创建日期：2026-03-26

核心功能：
1. 从用户修改中学习冲突模式
2. 积累常见冲突模式库
3. 预判新内容的潜在冲突
4. 提供预防性建议

设计参考：
- 经验文档/11.4Claw化实际运行说明✅️.md
- agents/consistency_checker_agent.py

使用示例：
    # 创建学习器实例
    learner = ConflictPatternLearner(workspace_root=Path("E:/project"))
    
    # 从修改中学习
    learner.learn_from_correction(
        original="张三是个开朗的男孩",
        corrected="张三是个沉稳的少年",
        conflict_type="character"
    )
    
    # 预判潜在冲突
    predictions = learner.predict_conflicts(
        content="张三笑着说，他是个内向的人..."
    )
"""

import json
import logging
import sqlite3
import threading
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Pydantic数据模型
# ============================================================================


class ConflictPattern(BaseModel):
    """冲突模式数据模型"""
    
    model_config = ConfigDict(frozen=False)
    
    pattern_id: str = Field(description="模式ID")
    conflict_type: str = Field(description="冲突类型（character/plot/worldview）")
    pattern_name: str = Field(description="模式名称")
    original_pattern: str = Field(description="原始模式（正则表达式）")
    corrected_pattern: str = Field(description="修正模式")
    description: str = Field(description="模式描述")
    occurrences: int = Field(default=1, description="出现次数")
    last_occurred: str = Field(description="最后出现时间")
    confidence: float = Field(default=0.8, description="置信度")


class PredictedConflict(BaseModel):
    """预测的冲突数据模型"""
    
    model_config = ConfigDict(frozen=False)
    
    conflict_type: str = Field(description="冲突类型")
    pattern_id: str = Field(description="匹配的模式ID")
    pattern_name: str = Field(description="模式名称")
    matched_text: str = Field(description="匹配的文本")
    position: int = Field(description="位置")
    severity: str = Field(description="严重程度（P0/P1/P2）")
    suggestion: str = Field(description="修改建议")
    confidence: float = Field(description="置信度")


# ============================================================================
# 冲突模式学习器
# ============================================================================


class ConflictPatternLearner:
    """
    冲突模式学习器
    
    负责：
    1. 从用户修改中学习冲突模式
    2. 积累常见冲突模式库
    3. 预判新内容的潜在冲突
    4. 提供预防性建议
    """
    
    # 内置冲突模式（基础规则）
    BUILTIN_PATTERNS = {
        "character_name_inconsistent": {
            "conflict_type": "character",
            "pattern_name": "人物姓名不一致",
            "description": "同一人物使用不同姓名",
            "regex": None,  # 需要动态生成
            "severity": "P1"
        },
        "character_trait_contradict": {
            "conflict_type": "character",
            "pattern_name": "人物性格矛盾",
            "description": "人物前后性格描述矛盾",
            "regex": None,
            "severity": "P1"
        },
        "timeline_error": {
            "conflict_type": "plot",
            "pattern_name": "时间线错误",
            "description": "事件发生时间顺序错误",
            "regex": None,
            "severity": "P0"
        },
        "worldview_contradict": {
            "conflict_type": "worldview",
            "pattern_name": "世界观设定矛盾",
            "description": "违反已设定的世界观规则",
            "regex": None,
            "severity": "P1"
        }
    }
    
    def __init__(self, workspace_root: Path = None):
        """
        初始化冲突模式学习器
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = workspace_root or Path.cwd()
        self.logger = logging.getLogger(__name__)
        
        # 数据库路径
        self.data_dir = self.workspace_root / "data" / "learning"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "learning_loop.db"
        
        # 初始化数据库
        self._init_database()
        
        # 线程锁
        self._lock = threading.RLock()
        
        # 模式缓存
        self._pattern_cache: Dict[str, ConflictPattern] = {}
        self._load_patterns()
        
        self.logger.info(f"ConflictPatternLearner initialized: {self.workspace_root}")
    
    def _init_database(self) -> None:
        """初始化SQLite数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 冲突模式表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conflict_patterns (
                    pattern_id TEXT PRIMARY KEY,
                    conflict_type TEXT NOT NULL,
                    pattern_name TEXT NOT NULL,
                    original_pattern TEXT,
                    corrected_pattern TEXT,
                    description TEXT,
                    occurrences INTEGER DEFAULT 1,
                    last_occurred TEXT,
                    confidence REAL
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_conflict_type 
                ON conflict_patterns(conflict_type)
            """)
            
            conn.commit()
    
    def _load_patterns(self) -> None:
        """加载已学习的模式"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM conflict_patterns")
                
                for row in cursor.fetchall():
                    pattern = ConflictPattern(
                        pattern_id=row[0],
                        conflict_type=row[1],
                        pattern_name=row[2],
                        original_pattern=row[3] or "",
                        corrected_pattern=row[4] or "",
                        description=row[5] or "",
                        occurrences=row[6],
                        last_occurred=row[7],
                        confidence=row[8] or 0.8
                    )
                    self._pattern_cache[pattern.pattern_id] = pattern
            
            self.logger.info(f"Loaded {len(self._pattern_cache)} conflict patterns")
            
        except Exception as e:
            self.logger.error(f"Failed to load patterns: {e}")
    
    def learn_from_correction(
        self,
        original: str,
        corrected: str,
        conflict_type: str,
        metadata: Dict[str, Any] = None
    ) -> Optional[str]:
        """
        从用户修改中学习冲突模式
        
        Args:
            original: 原始文本
            corrected: 修正后文本
            conflict_type: 冲突类型
            metadata: 元数据
            
        Returns:
            模式ID（如果学习成功）
        """
        try:
            # 提取修改模式
            pattern_id = self._extract_pattern(
                original, corrected, conflict_type
            )
            
            if pattern_id:
                self._update_pattern_occurrence(pattern_id)
                self.logger.info(f"Learned pattern: {pattern_id}")
                return pattern_id
            
        except Exception as e:
            self.logger.error(f"Failed to learn from correction: {e}")
        
        return None
    
    def _extract_pattern(
        self,
        original: str,
        corrected: str,
        conflict_type: str
    ) -> Optional[str]:
        """
        提取修改模式
        
        简化实现：使用diff方法提取差异
        """
        # 查找差异部分
        orig_words = list(original)
        corr_words = list(corrected)
        
        # 找到第一个差异位置
        diff_start = -1
        for i in range(min(len(orig_words), len(corr_words))):
            if orig_words[i] != corr_words[i]:
                diff_start = i
                break
        
        if diff_start == -1:
            if len(orig_words) != len(corr_words):
                diff_start = min(len(orig_words), len(corr_words))
            else:
                return None
        
        # 提取差异片段
        orig_diff = original[diff_start:diff_start+20]
        corr_diff = corrected[diff_start:diff_start+20]
        
        # 生成模式ID
        pattern_id = f"cp_{conflict_type}_{int(time.time()*1000)}"
        
        # 创建模式
        pattern = ConflictPattern(
            pattern_id=pattern_id,
            conflict_type=conflict_type,
            pattern_name=f"学习模式_{len(self._pattern_cache)+1}",
            original_pattern=orig_diff,
            corrected_pattern=corr_diff,
            description=f"从修改中学习：'{orig_diff}' -> '{corr_diff}'",
            occurrences=1,
            last_occurred=datetime.now().isoformat(),
            confidence=0.7
        )
        
        # 保存到数据库
        self._save_pattern(pattern)
        
        # 更新缓存
        self._pattern_cache[pattern_id] = pattern
        
        return pattern_id
    
    def _save_pattern(self, pattern: ConflictPattern) -> None:
        """保存模式到数据库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO conflict_patterns
                    (pattern_id, conflict_type, pattern_name, original_pattern,
                     corrected_pattern, description, occurrences, last_occurred, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pattern.pattern_id, pattern.conflict_type, pattern.pattern_name,
                    pattern.original_pattern, pattern.corrected_pattern,
                    pattern.description, pattern.occurrences, pattern.last_occurred,
                    pattern.confidence
                ))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to save pattern: {e}")
    
    def _update_pattern_occurrence(self, pattern_id: str) -> None:
        """更新模式出现次数"""
        if pattern_id in self._pattern_cache:
            pattern = self._pattern_cache[pattern_id]
            pattern.occurrences += 1
            pattern.last_occurred = datetime.now().isoformat()
            self._save_pattern(pattern)
    
    def predict_conflicts(
        self,
        content: str,
        min_confidence: float = 0.6
    ) -> List[PredictedConflict]:
        """
        预判潜在冲突
        
        Args:
            content: 待检查内容
            min_confidence: 最小置信度
            
        Returns:
            预测的冲突列表
        """
        predictions = []
        
        try:
            # 检查已学习的模式
            for pattern_id, pattern in self._pattern_cache.items():
                if pattern.confidence < min_confidence:
                    continue
                
                # 简单匹配：检查原始模式是否出现在内容中
                if pattern.original_pattern and pattern.original_pattern in content:
                    position = content.find(pattern.original_pattern)
                    
                    predictions.append(PredictedConflict(
                        conflict_type=pattern.conflict_type,
                        pattern_id=pattern_id,
                        pattern_name=pattern.pattern_name,
                        matched_text=pattern.original_pattern,
                        position=position,
                        severity=self._get_severity(pattern),
                        suggestion=f"建议修改为：{pattern.corrected_pattern}",
                        confidence=pattern.confidence
                    ))
            
            # 检查内置规则
            predictions.extend(self._check_builtin_rules(content))
            
            self.logger.info(f"Predicted {len(predictions)} potential conflicts")
            
        except Exception as e:
            self.logger.error(f"Failed to predict conflicts: {e}")
        
        return predictions
    
    def _get_severity(self, pattern: ConflictPattern) -> str:
        """根据模式类型确定严重程度"""
        if pattern.occurrences >= 5:
            return "P0"  # 频繁出现的问题
        elif pattern.occurrences >= 2:
            return "P1"
        else:
            return "P2"
    
    def _check_builtin_rules(self, content: str) -> List[PredictedConflict]:
        """检查内置规则"""
        predictions = []
        
        # 检查人物性格矛盾（简单示例）
        # 例如：开朗vs内向，勇敢vs胆小
        trait_pairs = [
            ("开朗", "内向"),
            ("勇敢", "胆小"),
            ("沉稳", "急躁"),
            ("热情", "冷漠")
        ]
        
        for pos_trait, neg_trait in trait_pairs:
            if pos_trait in content and neg_trait in content:
                # 检查是否描述同一人物
                pos_idx = content.find(pos_trait)
                neg_idx = content.find(neg_trait)
                
                if abs(pos_idx - neg_idx) < 100:  # 100字内
                    predictions.append(PredictedConflict(
                        conflict_type="character",
                        pattern_id="builtin_trait_contradict",
                        pattern_name="人物性格矛盾",
                        matched_text=f"{pos_trait}...{neg_trait}",
                        position=min(pos_idx, neg_idx),
                        severity="P1",
                        suggestion=f"检查人物性格是否一致：'{pos_trait}'和'{neg_trait}'矛盾",
                        confidence=0.85
                    ))
        
        return predictions
    
    def get_pattern_stats(self) -> Dict[str, Any]:
        """获取模式统计"""
        stats = {
            "total_patterns": len(self._pattern_cache),
            "by_type": {},
            "top_patterns": []
        }
        
        # 按类型统计
        for pattern in self._pattern_cache.values():
            conflict_type = pattern.conflict_type
            if conflict_type not in stats["by_type"]:
                stats["by_type"][conflict_type] = 0
            stats["by_type"][conflict_type] += 1
        
        # 按出现次数排序
        sorted_patterns = sorted(
            self._pattern_cache.values(),
            key=lambda p: p.occurrences,
            reverse=True
        )[:10]
        
        stats["top_patterns"] = [
            {
                "pattern_id": p.pattern_id,
                "pattern_name": p.pattern_name,
                "occurrences": p.occurrences
            }
            for p in sorted_patterns
        ]
        
        return stats


# ============================================================================
# 全局单例
# ============================================================================

_learner: Optional[ConflictPatternLearner] = None
_learner_lock = threading.Lock()


def get_conflict_pattern_learner(workspace_root: Path = None) -> ConflictPatternLearner:
    """获取冲突模式学习器单例"""
    global _learner
    
    with _learner_lock:
        if _learner is None:
            _learner = ConflictPatternLearner(workspace_root)
        return _learner
