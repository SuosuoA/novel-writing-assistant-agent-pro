"""
Fine-tuning数据积累器 - 收集高质量训练数据

V1.0版本
创建日期: 2026-03-26

功能:
- 收集高质量生成数据（评分≥0.85）
- 积累Fine-tuning训练数据
- 导出JSONL格式训练集
- 支持用户修改版本

使用示例:
    from core.finetuning_data_accumulator import FinetuningDataAccumulator
    
    accumulator = FinetuningDataAccumulator()
    
    # 收集数据
    accumulator.collect(chapter, user_feedback)
    
    # 导出训练集
    accumulator.export_dataset("training_data.jsonl", min_samples=100)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
import sqlite3

logger = logging.getLogger(__name__)


@dataclass
class TrainingData:
    """训练数据"""
    id: Optional[int] = None
    instruction: str = ""
    input: str = ""
    output: str = ""
    score: float = 0.0
    iterations: int = 0
    user_modified: bool = False
    chapter_id: str = ""
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class FinetuningDataAccumulator:
    """
    Fine-tuning数据积累器
    
    功能:
    - 收集高质量生成数据
    - 积累训练数据
    - 导出JSONL格式
    """
    
    # 质量阈值
    MIN_SCORE = 0.85  # 最低评分
    MAX_ITERATIONS = 3  # 最大迭代次数
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        初始化Fine-tuning数据积累器
        
        Args:
            db_path: 数据库路径（默认为 data/finetuning_data.db）
        """
        if db_path is None:
            db_path = Path("data/finetuning_data.db")
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_database()
        logger.info(f"FinetuningDataAccumulator initialized with db: {self.db_path}")
    
    def _init_database(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 创建训练数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS training_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    instruction TEXT NOT NULL,
                    input TEXT NOT NULL,
                    output TEXT NOT NULL,
                    score REAL NOT NULL,
                    iterations INTEGER NOT NULL,
                    user_modified BOOLEAN DEFAULT 0,
                    chapter_id TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_score ON training_data(score)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chapter_id ON training_data(chapter_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON training_data(timestamp)
            """)
            
            conn.commit()
    
    def collect(self, outline: str, content: str, 
                score: float, iterations: int,
                chapter_id: str = "",
                user_feedback: Optional[Dict] = None) -> Optional[TrainingData]:
        """
        收集训练数据
        
        Args:
            outline: 大纲内容
            content: 生成内容
            score: 总评分
            iterations: 迭代次数
            chapter_id: 章节ID
            user_feedback: 用户反馈（可选）
        
        Returns:
            训练数据对象（如果符合质量要求）
        """
        # 检查质量
        if score < self.MIN_SCORE:
            logger.info(f"Data quality too low: score={score:.2f} < {self.MIN_SCORE}")
            return None
        
        if iterations > self.MAX_ITERATIONS:
            logger.info(f"Iterations too many: {iterations} > {self.MAX_ITERATIONS}")
            return None
        
        # 创建训练数据
        data = TrainingData(
            instruction="根据大纲生成小说章节",
            input=outline,
            output=content,
            score=score,
            iterations=iterations,
            chapter_id=chapter_id,
            user_modified=False
        )
        
        # 如果有用户修改，使用修改后的内容
        if user_feedback and "corrected_content" in user_feedback:
            data.output = user_feedback["corrected_content"]
            data.user_modified = True
        
        # 保存到数据库
        self._save_data(data)
        
        logger.info(f"Collected training data: score={score:.2f}, iterations={iterations}")
        return data
    
    def _save_data(self, data: TrainingData):
        """保存训练数据"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO training_data 
                (instruction, input, output, score, iterations, user_modified, chapter_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.instruction,
                data.input,
                data.output,
                data.score,
                data.iterations,
                data.user_modified,
                data.chapter_id,
                data.timestamp
            ))
            
            data.id = cursor.lastrowid
            conn.commit()
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取数据统计"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 总数
            cursor.execute("SELECT COUNT(*) FROM training_data")
            total = cursor.fetchone()[0]
            
            # 平均评分
            cursor.execute("SELECT AVG(score) FROM training_data")
            avg_score = cursor.fetchone()[0] or 0
            
            # 用户修改比例
            cursor.execute("SELECT COUNT(*) FROM training_data WHERE user_modified = 1")
            user_modified = cursor.fetchone()[0]
            
            # 按评分分布
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN score >= 0.95 THEN '0.95+'
                        WHEN score >= 0.90 THEN '0.90-0.95'
                        WHEN score >= 0.85 THEN '0.85-0.90'
                        ELSE '<0.85'
                    END as score_range,
                    COUNT(*) as count
                FROM training_data
                GROUP BY score_range
            """)
            score_distribution = {row[0]: row[1] for row in cursor.fetchall()}
            
            return {
                "total": total,
                "avg_score": avg_score,
                "user_modified_ratio": user_modified / total if total > 0 else 0,
                "score_distribution": score_distribution
            }
    
    def export_dataset(self, output_path: str, min_samples: int = 100,
                      min_score: float = 0.85,
                      max_iterations: int = 3) -> int:
        """
        导出训练数据集
        
        Args:
            output_path: 输出文件路径
            min_samples: 最少样本数
            min_score: 最低评分
            max_iterations: 最大迭代次数
        
        Returns:
            导出的样本数
        """
        # 加载符合条件的数据
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT instruction, input, output, score, iterations
                FROM training_data
                WHERE score >= ? AND iterations <= ?
                ORDER BY score DESC, iterations ASC
            """, (min_score, max_iterations))
            
            rows = cursor.fetchall()
        
        # 检查数据量
        if len(rows) < min_samples:
            logger.warning(f"Insufficient data: {len(rows)} < {min_samples}")
            return 0
        
        # 转换为训练格式
        dataset = []
        for row in rows:
            dataset.append({
                "instruction": row[0],
                "input": row[1],
                "output": row[2],
                "score": row[3],
                "iterations": row[4]
            })
        
        # 保存为JSONL
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for item in dataset:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        logger.info(f"Exported {len(dataset)} samples to {output_file}")
        return len(dataset)
    
    def get_recent_data(self, limit: int = 20) -> List[TrainingData]:
        """获取最近的训练数据"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM training_data 
                ORDER BY timestamp DESC LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            
            data_list = []
            for row in rows:
                data = TrainingData(
                    id=row[0],
                    instruction=row[1],
                    input=row[2],
                    output=row[3],
                    score=row[4],
                    iterations=row[5],
                    user_modified=bool(row[6]),
                    chapter_id=row[7],
                    timestamp=row[8]
                )
                data_list.append(data)
            
            return data_list
    
    def clear_low_quality_data(self, threshold: float = 0.85):
        """清理低质量数据"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM training_data WHERE score < ?", (threshold,))
            deleted = cursor.rowcount
            conn.commit()
        
        logger.info(f"Cleared {deleted} low quality data (score < {threshold})")
        return deleted


# 全局单例
_finetuning_data_accumulator_instance: Optional[FinetuningDataAccumulator] = None


def get_finetuning_data_accumulator(db_path: Optional[Path] = None) -> FinetuningDataAccumulator:
    """获取Fine-tuning数据积累器单例"""
    global _finetuning_data_accumulator_instance
    if _finetuning_data_accumulator_instance is None:
        _finetuning_data_accumulator_instance = FinetuningDataAccumulator(db_path)
    return _finetuning_data_accumulator_instance
