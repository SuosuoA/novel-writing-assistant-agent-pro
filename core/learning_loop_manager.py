"""
学习闭环管理器 - 实现"越用越聪明"的核心引擎

V1.1版本 - 聚焦核心目标
创建日期：2026-03-26
更新日期：2026-03-26

核心目标（用户诉求驱动）：
1. 提升八大维度评分（字数/知识点引用/大纲/风格/人设/世界观/逆向反馈/自然度）
2. 降低AI感（减少机械感、模板化、生硬表达）
3. 知识库自动增长
4. 冲突模式积累

学习闭环：
生成内容 → 评分反馈 → AI感检测 → 知识提取 → 权重优化 → 下次生成更好

关键指标：
- 八大维度平均分：目标≥0.85
- AI感评分：目标≤0.3（越低越好，自然度维度的反向指标）
- 知识库增长率：每周+50条
- 冲突减少率：每月-20%

设计参考：
- 经验文档/11.4Claw化实际运行说明✅️.md
- OpenClaw mem9架构
- V5评分反馈循环（八大维度权重：字数8%/知识点引用8%/大纲13%/风格19%/人设19%/世界观12%/逆向反馈11%/自然度10%）

使用示例：
    # 创建管理器实例
    manager = LearningLoopManager(workspace_root=Path("E:/project"))
    
    # 收集生成数据（包含AI感评分）
    manager.collect_generation_data(
        chapter_id="chapter_001",
        content="第一章内容...",
        scores={
            "word_count": 0.85,
            "knowledge_reference": 0.75,  # 知识点引用
            "outline": 0.9,
            "style": 0.88,
            "character": 0.92,
            "worldview": 0.85,
            "reverse_feedback": 0.80,  # 逆向反馈（上下文一致性）
            "naturalness": 0.70,  # 自然度（AI感的反向）
            "ai_feeling": 0.35  # AI感评分（越低越好）
        }
    )
    
    # 分析薄弱维度
    weak_dims = manager.identify_weak_dimensions(threshold=0.75)
    
    # 获取改进建议
    suggestions = manager.get_improvement_suggestions(weak_dims)
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
from dataclasses import dataclass, field, asdict

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Pydantic数据模型
# ============================================================================


class KnowledgePoint(BaseModel):
    """知识点数据模型"""
    
    model_config = ConfigDict(frozen=False)
    
    knowledge_id: str = Field(description="知识点ID")
    title: str = Field(description="知识点标题")
    content: str = Field(description="知识点内容")
    category: str = Field(description="分类（character/worldview/style/plot）")
    domain: str = Field(default="general", description="领域")
    keywords: List[str] = Field(default_factory=list, description="关键词")
    source_chapter: str = Field(description="来源章节ID")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    confidence: float = Field(default=0.8, description="置信度（0-1）")


class ScoreRecord(BaseModel):
    """评分记录数据模型"""
    
    model_config = ConfigDict(frozen=False)
    
    record_id: str = Field(description="记录ID")
    chapter_id: str = Field(description="章节ID")
    dimension: str = Field(description="评分维度")
    score: float = Field(description="分数（0-1）")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScoreTrend(BaseModel):
    """评分趋势数据模型"""
    
    model_config = ConfigDict(frozen=False)
    
    dimension: str = Field(description="维度名称")
    avg_score: float = Field(description="平均分")
    trend: str = Field(description="趋势（up/down/stable）")
    sample_count: int = Field(description="样本数")
    last_score: float = Field(description="最近一次分数")


class WeightSuggestion(BaseModel):
    """权重调整建议数据模型"""
    
    model_config = ConfigDict(frozen=False)
    
    dimension: str = Field(description="维度名称")
    current_weight: float = Field(description="当前权重")
    suggested_weight: float = Field(description="建议权重")
    reason: str = Field(description="调整原因")


class LearningStats(BaseModel):
    """学习统计数据模型"""
    
    model_config = ConfigDict(frozen=False)
    
    total_chapters: int = Field(default=0, description="总章节数")
    total_knowledge_points: int = Field(default=0, description="总知识点数")
    avg_score: float = Field(default=0.0, description="平均评分")
    weak_dimensions: List[str] = Field(default_factory=list, description="薄弱维度")
    strong_dimensions: List[str] = Field(default_factory=list, description="强势维度")
    last_learning_time: Optional[str] = Field(default=None, description="最后学习时间")


# ============================================================================
# 学习闭环管理器
# ============================================================================


class LearningLoopManager:
    """
    学习闭环管理器
    
    负责：
    1. 收集生成数据
    2. 提取知识点
    3. 更新知识库
    4. 分析评分趋势
    5. 建议权重调整
    """
    
    # 评分维度列表（V1.7版本 - 8维度）
    SCORE_DIMENSIONS = [
        "字数", "知识点引用", "大纲", "风格", 
        "人设", "世界观", "逆向反馈", "自然度"
    ]
    
    # 默认权重配置
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
    
    # 知识点提取模式
    KNOWLEDGE_PATTERNS = {
        "character": [
            r"(.{2,10})[:,：]\s*([^。\n]{10,100})",  # 人物: 描述
            r"(.{2,10})身穿([^。\n]{5,50})",  # 人物穿着
            r'(.{2,10})说道[：:]?\s*[\"\"]([^\"\"]+)[\"\"]',  # 人物对话
        ],
        "worldview": [
            r"在(.{3,20})[,，]([^。\n]{10,100})",  # 世界设定
            r"(.{3,20})的规则是[：:]?\s*([^。\n]{10,100})",  # 规则设定
        ],
        "style": [
            r"(.*?)[,，]宛如([^。\n]{5,30})",  # 比喻
            r"(.*?)[,，]仿佛([^。\n]{5,30})",  # 明喻
        ]
    }
    
    def __init__(self, workspace_root: Path = None):
        """
        初始化学习闭环管理器
        
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
        
        # 统计数据
        self._stats = LearningStats()
        self._load_stats()
        
        self.logger.info(f"LearningLoopManager initialized: {self.workspace_root}")
    
    def _init_database(self) -> None:
        """初始化SQLite数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 评分历史表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS score_history (
                    record_id TEXT PRIMARY KEY,
                    chapter_id TEXT NOT NULL,
                    dimension TEXT NOT NULL,
                    score REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT
                )
            """)
            
            # 知识点表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_points (
                    knowledge_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    domain TEXT,
                    keywords TEXT,
                    source_chapter TEXT,
                    created_at TEXT,
                    confidence REAL
                )
            """)
            
            # 学习统计表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learning_stats (
                    stat_id TEXT PRIMARY KEY,
                    total_chapters INTEGER,
                    total_knowledge_points INTEGER,
                    avg_score REAL,
                    weak_dimensions TEXT,
                    strong_dimensions TEXT,
                    last_learning_time TEXT
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_score_chapter 
                ON score_history(chapter_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_score_dimension 
                ON score_history(dimension)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_category 
                ON knowledge_points(category)
            """)            
            conn.commit()
    
    def _load_stats(self) -> None:
        """加载统计数据"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM learning_stats LIMIT 1")
            row = cursor.fetchone()
            
            if row:
                self._stats = LearningStats(
                    total_chapters=row[1],
                    total_knowledge_points=row[2],
                    avg_score=row[3],
                    weak_dimensions=json.loads(row[4]) if row[4] else [],
                    strong_dimensions=json.loads(row[5]) if row[5] else [],
                    last_learning_time=row[6]
                )
    
    def _save_stats(self) -> None:
        """保存统计数据"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO learning_stats 
                (stat_id, total_chapters, total_knowledge_points, avg_score, 
                 weak_dimensions, strong_dimensions, last_learning_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                "main",
                self._stats.total_chapters,
                self._stats.total_knowledge_points,
                self._stats.avg_score,
                json.dumps(self._stats.weak_dimensions),
                json.dumps(self._stats.strong_dimensions),
                self._stats.last_learning_time
            ))
            conn.commit()
    
    def collect_generation_data(
        self, 
        chapter_id: str, 
        content: str, 
        scores: Dict[str, float]
    ) -> None:
        """
        收集生成数据
        
        Args:
            chapter_id: 章节ID
            content: 章节内容
            scores: 评分字典
        """
        with self._lock:
            try:
                timestamp = datetime.now().isoformat()
                
                # 保存评分记录
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    for dimension, score in scores.items():
                        record_id = f"{chapter_id}_{dimension}_{int(time.time()*1000)}"
                        cursor.execute("""
                            INSERT INTO score_history 
                            (record_id, chapter_id, dimension, score, timestamp, metadata)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            record_id, chapter_id, dimension, score, timestamp,
                            json.dumps({"chapter_length": len(content)})
                        ))
                    conn.commit()
                
                # 提取知识点
                knowledge_points = self.extract_knowledge_points(content, chapter_id)
                if knowledge_points:
                    self.update_knowledge_base(knowledge_points)
                
                # 更新统计
                self._stats.total_chapters += 1
                self._stats.last_learning_time = timestamp
                self._save_stats()
                
                self.logger.info(
                    f"Collected data for chapter {chapter_id}: "
                    f"scores={len(scores)}, knowledge_points={len(knowledge_points)}"
                )
                
            except Exception as e:
                self.logger.error(f"Failed to collect generation data: {e}")
    
    def extract_knowledge_points(
        self, 
        content: str, 
        chapter_id: str,
        min_confidence: float = 0.6
    ) -> List[KnowledgePoint]:
        """
        从内容中提取知识点
        
        Args:
            content: 章节内容
            chapter_id: 章节ID
            min_confidence: 最小置信度阈值
            
        Returns:
            提取的知识点列表
        """
        knowledge_points = []
        
        try:
            for category, patterns in self.KNOWLEDGE_PATTERNS.items():
                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        if isinstance(match, tuple):
                            title = match[0].strip()
                            content_text = match[1].strip() if len(match) > 1 else ""
                        else:
                            title = match.strip()
                            content_text = ""
                        
                        # 跳过太短或太长的内容
                        if len(title) < 2 or len(content_text) < 10:
                            continue
                        
                        # 计算置信度（简单规则）
                        confidence = min(1.0, len(content_text) / 50)
                        
                        if confidence >= min_confidence:
                            knowledge_id = f"kp_{category}_{int(time.time()*1000)}_{len(knowledge_points)}"
                            
                            kp = KnowledgePoint(
                                knowledge_id=knowledge_id,
                                title=title,
                                content=content_text,
                                category=category,
                                domain="general",
                                keywords=self._extract_keywords(title + " " + content_text),
                                source_chapter=chapter_id,
                                confidence=confidence
                            )
                            knowledge_points.append(kp)
            
            self.logger.info(
                f"Extracted {len(knowledge_points)} knowledge points from chapter {chapter_id}"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to extract knowledge points: {e}")
        
        return knowledge_points
    
    def _extract_keywords(self, text: str, max_keywords: int = 5) -> List[str]:
        """提取关键词(简单实现)"""
        # 停用词列表（简化版）
        stop_words = {"的", "了", "是", "在", "有", "和", "与", "或", "但", "这", "那"}
        
        # 分词（简单按空格和标点分割）
        words = re.findall(r"[\u4e00-\u9fa5]{2,4}", text)
        
        # 过滤停用词并返回前N个
        keywords = [w for w in words if w not in stop_words][:max_keywords]
        return keywords
    
    def update_knowledge_base(
        self, 
        knowledge_points: List[KnowledgePoint]
    ) -> int:
        """
        更新知识库
        
        Args:
            knowledge_points: 知识点列表
            
        Returns:
            成功更新的知识点数量
        """
        success_count = 0
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for kp in knowledge_points:
                    # 检查是否已存在（去重）
                    cursor.execute("""
                        SELECT knowledge_id FROM knowledge_points 
                        WHERE title = ? AND category = ?
                    """, (kp.title, kp.category))
                    
                    if cursor.fetchone():
                        continue
                    
                    # 插入新知识点
                    cursor.execute("""
                        INSERT INTO knowledge_points 
                        (knowledge_id, title, content, category, domain, 
                         keywords, source_chapter, created_at, confidence)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        kp.knowledge_id, kp.title, kp.content, kp.category,
                        kp.domain, json.dumps(kp.keywords), kp.source_chapter,
                        kp.created_at, kp.confidence
                    ))
                    success_count += 1
                
                conn.commit()
            
            # 更新统计
            self._stats.total_knowledge_points += success_count
            self._save_stats()
            
            self.logger.info(f"Updated knowledge base: {success_count} new points")
            
        except Exception as e:
            self.logger.error(f"Failed to update knowledge base: {e}")
        
        return success_count
    
    def analyze_score_trend(self, last_n: int = 10) -> Dict[str, ScoreTrend]:
        """
        分析评分趋势
        
        Args:
            last_n: 分析最近N个章节
            
        Returns:
            各维度的评分趋势
        """
        trends = {}
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for dimension in self.SCORE_DIMENSIONS:
                    # 获取最近N条记录
                    cursor.execute("""
                        SELECT score FROM score_history 
                        WHERE dimension = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (dimension, last_n))
                    
                    scores = [row[0] for row in cursor.fetchall()]
                    
                    if len(scores) < 2:
                        continue
                    
                    avg_score = sum(scores) / len(scores)
                    last_score = scores[0]
                    
                    # 判断趋势
                    if len(scores) >= 3:
                        recent_avg = sum(scores[:3]) / 3
                        older_avg = sum(scores[-3:]) / 3
                        
                        if recent_avg > older_avg + 0.05:
                            trend = "up"
                        elif recent_avg < older_avg - 0.05:
                            trend = "down"
                        else:
                            trend = "stable"
                    else:
                        trend = "stable"
                    
                    trends[dimension] = ScoreTrend(
                        dimension=dimension,
                        avg_score=avg_score,
                        trend=trend,
                        sample_count=len(scores),
                        last_score=last_score
                    )
            
            self.logger.info(f"Analyzed score trends for {len(trends)} dimensions")
            
        except Exception as e:
            self.logger.error(f"Failed to analyze score trend: {e}")
        
        return trends
    
    def suggest_weight_adjustment(
        self, 
        trends: Dict[str, ScoreTrend],
        threshold: float = 0.75
    ) -> List[WeightSuggestion]:
        """
        建议权重调整
        
        Args:
            trends: 评分趋势字典
            threshold: 薄弱维度阈值
            
        Returns:
            权重调整建议列表
        """
        suggestions = []
        
        try:
            # 识别薄弱和强势维度
            weak_dims = []
            strong_dims = []
            
            for dimension, trend in trends.items():
                if trend.avg_score < threshold:
                    weak_dims.append((dimension, trend.avg_score))
                elif trend.avg_score > 0.85:
                    strong_dims.append((dimension, trend.avg_score))
            
            # 生成调整建议
            for dim, score in weak_dims:
                current_weight = self.DEFAULT_WEIGHTS.get(dim, 0.1)
                # 薄弱维度权重+5%，最高30%
                suggested = min(0.30, current_weight + 0.05)
                
                suggestions.append(WeightSuggestion(
                    dimension=dim,
                    current_weight=current_weight,
                    suggested_weight=suggested,
                    reason=f"平均分{score:.2f}<阈值{threshold}，需要加强"
                ))
            
            # 更新统计
            self._stats.weak_dimensions = [d[0] for d in weak_dims]
            self._stats.strong_dimensions = [d[0] for d in strong_dims]
            self._save_stats()
            
            self.logger.info(f"Generated {len(suggestions)} weight suggestions")
            
        except Exception as e:
            self.logger.error(f"Failed to suggest weight adjustment: {e}")
        
        return suggestions
    
    def get_learning_stats(self) -> LearningStats:
        """获取学习统计"""
        return self._stats
    
    def get_recent_scores(self, limit: int = 20) -> List[ScoreRecord]:
        """获取最近评分记录"""
        records = []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT record_id, chapter_id, dimension, score, timestamp, metadata
                    FROM score_history
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
                
                for row in cursor.fetchall():
                    records.append(ScoreRecord(
                        record_id=row[0],
                        chapter_id=row[1],
                        dimension=row[2],
                        score=row[3],
                        timestamp=row[4],
                        metadata=json.loads(row[5]) if row[5] else {}
                    ))
        except Exception as e:
            self.logger.error(f"Failed to get recent scores: {e}")
        
        return records


# ============================================================================
# 全局单例
# ============================================================================

_learning_loop_manager: Optional[LearningLoopManager] = None
_manager_lock = threading.Lock()


def get_learning_loop_manager(workspace_root: Path = None) -> LearningLoopManager:
    """获取学习闭环管理器单例"""
    global _learning_loop_manager
    
    with _manager_lock:
        if _learning_loop_manager is None:
            _learning_loop_manager = LearningLoopManager(workspace_root)
        return _learning_loop_manager

