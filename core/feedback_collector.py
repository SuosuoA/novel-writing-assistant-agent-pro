"""
用户反馈收集器

V1.0版本
创建日期: 2026-03-26
最后更新: 2026-03-26

功能:
- 收集用户对生成内容的反馈
- 支持多种反馈类型（内容/风格/AI感/其他）
- 记录反馈上下文（章节、时间、用户操作）
- 存储到SQLite数据库

使用示例:
    from core.feedback_collector import FeedbackCollector
    
    collector = FeedbackCollector(db_path="data/feedback.db")
    
    # 收集反馈
    feedback = collector.collect(
        chapter_id="chapter_001",
        feedback_text="这个对话太生硬了",
        feedback_type="style",
        context={"dimension": "naturalness"}
    )
    
    # 查询历史反馈
    history = collector.get_history(limit=10)
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
class Feedback:
    """反馈数据类"""
    id: Optional[int] = None
    chapter_id: str = ""
    feedback_text: str = ""
    feedback_type: str = ""  # content / style / ai_feeling / other
    context: Dict[str, Any] = None
    timestamp: str = ""
    processed: bool = False
    knowledge_extracted: bool = False
    
    def __post_init__(self):
        if self.context is None:
            self.context = {}
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class FeedbackCollector:
    """
    用户反馈收集器
    
    功能:
    - 收集用户对生成内容的反馈
    - 支持多种反馈类型
    - 记录反馈上下文
    - 存储到SQLite数据库
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        初始化反馈收集器
        
        Args:
            db_path: 数据库路径（默认为 data/feedback.db）
        """
        if db_path is None:
            db_path = Path("data/feedback.db")
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_database()
        logger.info(f"FeedbackCollector initialized with db: {self.db_path}")
    
    def _init_database(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 创建反馈表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter_id TEXT NOT NULL,
                    feedback_text TEXT NOT NULL,
                    feedback_type TEXT NOT NULL,
                    context TEXT,
                    timestamp TEXT NOT NULL,
                    processed BOOLEAN DEFAULT 0,
                    knowledge_extracted BOOLEAN DEFAULT 0
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chapter_id ON feedback(chapter_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback(feedback_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON feedback(timestamp)
            """)
            
            conn.commit()
    
    def collect(self, chapter_id: str, feedback_text: str, feedback_type: str,
                context: Optional[Dict[str, Any]] = None) -> Feedback:
        """
        收集用户反馈
        
        Args:
            chapter_id: 章节ID
            feedback_text: 反馈文本
            feedback_type: 反馈类型（content/style/ai_feeling/other）
            context: 上下文信息
        
        Returns:
            反馈对象
        """
        feedback = Feedback(
            chapter_id=chapter_id,
            feedback_text=feedback_text,
            feedback_type=feedback_type,
            context=context or {}
        )
        
        # 保存到数据库
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO feedback (chapter_id, feedback_text, feedback_type, context, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                feedback.chapter_id,
                feedback.feedback_text,
                feedback.feedback_type,
                json.dumps(feedback.context, ensure_ascii=False),
                feedback.timestamp
            ))
            
            feedback.id = cursor.lastrowid
            conn.commit()
        
        logger.info(f"Collected feedback #{feedback.id}: {feedback.feedback_type} - {feedback.feedback_text[:50]}...")
        return feedback
    
    def get_history(self, limit: int = 10, feedback_type: Optional[str] = None,
                    chapter_id: Optional[str] = None) -> List[Feedback]:
        """
        查询历史反馈
        
        Args:
            limit: 返回数量
            feedback_type: 筛选反馈类型
            chapter_id: 筛选章节ID
        
        Returns:
            反馈列表
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM feedback WHERE 1=1"
            params = []
            
            if feedback_type:
                query += " AND feedback_type = ?"
                params.append(feedback_type)
            
            if chapter_id:
                query += " AND chapter_id = ?"
                params.append(chapter_id)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            feedbacks = []
            for row in rows:
                feedback = Feedback(
                    id=row[0],
                    chapter_id=row[1],
                    feedback_text=row[2],
                    feedback_type=row[3],
                    context=json.loads(row[4]) if row[4] else {},
                    timestamp=row[5],
                    processed=bool(row[6]),
                    knowledge_extracted=bool(row[7])
                )
                feedbacks.append(feedback)
            
            return feedbacks
    
    def mark_processed(self, feedback_id: int):
        """标记反馈已处理"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE feedback SET processed = 1 WHERE id = ?
            """, (feedback_id,))
            conn.commit()
        
        logger.info(f"Marked feedback #{feedback_id} as processed")
    
    def mark_knowledge_extracted(self, feedback_id: int):
        """标记反馈已提取知识点"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE feedback SET knowledge_extracted = 1 WHERE id = ?
            """, (feedback_id,))
            conn.commit()
        
        logger.info(f"Marked feedback #{feedback_id} as knowledge extracted")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取反馈统计信息
        
        Returns:
            统计信息字典
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 总数
            cursor.execute("SELECT COUNT(*) FROM feedback")
            total = cursor.fetchone()[0]
            
            # 按类型统计
            cursor.execute("""
                SELECT feedback_type, COUNT(*) as count
                FROM feedback
                GROUP BY feedback_type
            """)
            by_type = {row[0]: row[1] for row in cursor.fetchall()}
            
            # 未处理数量
            cursor.execute("SELECT COUNT(*) FROM feedback WHERE processed = 0")
            unprocessed = cursor.fetchone()[0]
            
            # 未提取知识点数量
            cursor.execute("SELECT COUNT(*) FROM feedback WHERE knowledge_extracted = 0")
            unextracted = cursor.fetchone()[0]
            
            return {
                "total": total,
                "by_type": by_type,
                "unprocessed": unprocessed,
                "unextracted": unextracted
            }
    
    def export_feedbacks(self, output_path: Path, limit: Optional[int] = None):
        """
        导出反馈数据
        
        Args:
            output_path: 输出文件路径
            limit: 导出数量限制
        """
        feedbacks = self.get_history(limit=limit or 1000)
        
        data = [asdict(f) for f in feedbacks]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Exported {len(feedbacks)} feedbacks to {output_path}")


# 全局单例
_feedback_collector_instance: Optional[FeedbackCollector] = None


def get_feedback_collector(db_path: Optional[Path] = None) -> FeedbackCollector:
    """获取反馈收集器单例"""
    global _feedback_collector_instance
    if _feedback_collector_instance is None:
        _feedback_collector_instance = FeedbackCollector(db_path)
    return _feedback_collector_instance
