"""
反馈提纯器

V1.0版本
创建日期: 2026-04-08
最后更新: 2026-04-08

功能:
- 从用户反馈中提取知识点
- NLP分析反馈语义，生成结构化知识条目
- 将提纯结果存储到向量库和JSON文件
- 支持批量处理未提纯的反馈

使用示例:
    from core.feedback_refiner import FeedbackRefiner
    
    refiner = FeedbackRefiner(db_path="data/feedback.db")
    
    # 提纯单条反馈
    result = refiner.refine(feedback_id=1)
    
    # 批量提纯未处理反馈
    results = refiner.refine_all_unprocessed()
"""

import re
import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class RefinedKnowledge:
    """提纯后的知识点数据类"""
    id: Optional[int] = None
    source_feedback_id: int = 0
    category: str = ""           # 知识类别（科幻/玄幻/通用）
    subcategory: str = ""        # 子类别
    title: str = ""              # 知识标题
    content: str = ""            # 知识内容
    keywords: List[str] = None   # 关键词列表
    source_type: str = "user_feedback"  # 来源类型
    confidence: float = 0.0      # 置信度 0-1
    created_at: str = ""
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class FeedbackRefiner:
    """
    反馈提纯器
    
    从用户反馈中提取结构化知识点：
    1. 分析反馈语义（规则+NLP混合）
    2. 提取关键信息（类别、关键词、知识点）
    3. 生成结构化知识条目
    4. 存储到向量库和JSON文件
    """
    
    # 反馈类型→知识类别映射
    FEEDBACK_TYPE_MAP = {
        'content': '通用',
        'style': '通用',
        'ai_feeling': '通用',
        'other': '通用',
    }
    
    # 关键词提取模式
    KEYWORD_PATTERNS = [
        r'[\u4e00-\u9fa5]{2,6}(?:问题|错误|矛盾|不合理|不符)',  # 问题模式
        r'[\u4e00-\u9fa5]{2,6}(?:应该|需要|建议|最好)',          # 建议模式
        r'[\u4e00-\u9fa5]{2,6}(?:风格|语气|节奏|结构)',          # 风格模式
        r'[\u4e00-\u9fa5]{2,6}(?:角色|人物|主角|配角)',          # 人物模式
        r'[\u4e00-\u9fa5]{2,6}(?:设定|背景|规则|体系)',          # 设定模式
    ]
    
    def __init__(self, db_path: Optional[Path] = None,
                 knowledge_dir: Optional[Path] = None):
        """
        初始化反馈提纯器
        
        Args:
            db_path: 反馈数据库路径
            knowledge_dir: 知识库输出目录
        """
        self.db_path = Path(db_path) if db_path else Path("data/feedback.db")
        self.knowledge_dir = Path(knowledge_dir) if knowledge_dir else Path("data/知识库验证器")
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        
        self._init_database()
        logger.info(f"FeedbackRefiner initialized with db: {self.db_path}")
    
    def _init_database(self):
        """初始化提纯知识表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS refined_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_feedback_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    subcategory TEXT DEFAULT '',
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    keywords TEXT DEFAULT '[]',
                    source_type TEXT DEFAULT 'user_feedback',
                    confidence REAL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (source_feedback_id) REFERENCES feedback(id)
                )
            """)
            conn.commit()
    
    def refine(self, feedback_id: int) -> Optional[RefinedKnowledge]:
        """
        提纯单条反馈
        
        Args:
            feedback_id: 反馈ID
            
        Returns:
            提纯后的知识点，或None（如果无法提纯）
        """
        # 1. 读取原始反馈
        feedback = self._get_feedback(feedback_id)
        if not feedback:
            logger.warning(f"Feedback #{feedback_id} not found")
            return None
        
        feedback_text = feedback.get('feedback_text', '')
        feedback_type = feedback.get('feedback_type', 'other')
        context = feedback.get('context', {})
        
        if not feedback_text or len(feedback_text) < 5:
            logger.debug(f"Feedback #{feedback_id} too short to refine")
            return None
        
        # 2. 分析语义，提取知识点
        category = self._detect_category(feedback_text, feedback_type, context)
        keywords = self._extract_keywords(feedback_text)
        title = self._generate_title(feedback_text, category)
        content = self._generate_content(feedback_text, keywords, category)
        confidence = self._calculate_confidence(feedback_text, keywords)
        
        # 3. 创建知识点
        knowledge = RefinedKnowledge(
            source_feedback_id=feedback_id,
            category=category,
            subcategory=self._detect_subcategory(feedback_text, category),
            title=title,
            content=content,
            keywords=keywords,
            confidence=confidence,
        )
        
        # 4. 存储到数据库
        self._save_knowledge(knowledge)
        
        # 5. 标记原始反馈已提纯
        self._mark_feedback_processed(feedback_id, knowledge_extracted=True)
        
        logger.info(f"Refined feedback #{feedback_id} -> knowledge: {title[:30]}... (confidence: {confidence:.2f})")
        return knowledge
    
    def refine_all_unprocessed(self, limit: int = 50) -> List[RefinedKnowledge]:
        """
        批量提纯未处理的反馈
        
        Args:
            limit: 最大处理数量
            
        Returns:
            提纯后的知识点列表
        """
        unprocessed = self._get_unprocessed_feedbacks(limit)
        results = []
        
        for fb in unprocessed:
            knowledge = self.refine(fb['id'])
            if knowledge:
                results.append(knowledge)
        
        logger.info(f"Refined {len(results)}/{len(unprocessed)} unprocessed feedbacks")
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取提纯统计"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM refined_knowledge")
            total = cursor.fetchone()[0]
            
            cursor.execute("SELECT category, COUNT(*) FROM refined_knowledge GROUP BY category")
            by_category = dict(cursor.fetchall())
            
            cursor.execute("SELECT AVG(confidence) FROM refined_knowledge")
            avg_confidence = cursor.fetchone()[0] or 0.0
        
        return {
            'total_refined': total,
            'by_category': by_category,
            'avg_confidence': round(avg_confidence, 3),
        }
    
    # ===== 内部方法 =====
    
    def _get_feedback(self, feedback_id: int) -> Optional[Dict]:
        """读取原始反馈"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, chapter_id, feedback_text, feedback_type, context FROM feedback WHERE id = ?",
                         (feedback_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            context = {}
            if row[4]:
                try:
                    context = json.loads(row[4])
                except (json.JSONDecodeError, TypeError):
                    pass
            
            return {
                'id': row[0],
                'chapter_id': row[1],
                'feedback_text': row[2],
                'feedback_type': row[3],
                'context': context,
            }
    
    def _get_unprocessed_feedbacks(self, limit: int) -> List[Dict]:
        """获取未提纯的反馈"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, chapter_id, feedback_text, feedback_type, context 
                FROM feedback 
                WHERE knowledge_extracted = 0 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,))
            
            results = []
            for row in cursor.fetchall():
                context = {}
                if row[4]:
                    try:
                        context = json.loads(row[4])
                    except (json.JSONDecodeError, TypeError):
                        pass
                results.append({
                    'id': row[0],
                    'chapter_id': row[1],
                    'feedback_text': row[2],
                    'feedback_type': row[3],
                    'context': context,
                })
            return results
    
    def _detect_category(self, text: str, feedback_type: str, context: Dict) -> str:
        """检测知识类别"""
        # 优先从上下文获取
        if 'knowledge_category' in context:
            return context['knowledge_category']
        
        # 基于关键词检测
        sci_keywords = ['科技', '物理', '化学', '生物', '太空', 'AI', '量子', '赛博']
        fantasy_keywords = ['魔法', '修仙', '神话', '仙侠', '灵气', '阵法', '丹药']
        
        for kw in sci_keywords:
            if kw in text:
                return '科幻'
        for kw in fantasy_keywords:
            if kw in text:
                return '玄幻'
        
        return self.FEEDBACK_TYPE_MAP.get(feedback_type, '通用')
    
    def _detect_subcategory(self, text: str, category: str) -> str:
        """检测子类别"""
        subcategory_map = {
            '科幻': {'物理': 'physics', '生物': 'biology', '太空': 'space', '技术': 'technology', 'AI': 'technology'},
            '玄幻': {'神话': 'mythology', '宗教': 'religion', '修仙': 'mythology', '魔法': 'mythology'},
            '通用': {'逻辑': 'logic', '哲学': 'philosophy', '基础': 'basic_knowledge', '经济': 'economics'},
        }
        
        cat_map = subcategory_map.get(category, {})
        for keyword, sub in cat_map.items():
            if keyword in text:
                return sub
        
        return ''
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        keywords = set()
        
        # 基于模式提取
        for pattern in self.KEYWORD_PATTERNS:
            matches = re.findall(pattern, text)
            keywords.update(matches)
        
        # 基于中文词频提取（简单版：提取2-4字中文词组）
        chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
        # 过滤停用词
        stopwords = {'这个', '那个', '但是', '因为', '所以', '如果', '就是', '而且', '可以', '应该', '一些', '这些', '那些', '他们', '我们', '自己', '什么', '怎么', '这样', '那样', '已经', '还是', '只是', '没有'}
        meaningful = [w for w in chinese_words if w not in stopwords]
        
        # 取前10个高频词
        from collections import Counter
        word_freq = Counter(meaningful)
        top_words = [w for w, _ in word_freq.most_common(10)]
        keywords.update(top_words)
        
        return list(keywords)[:15]
    
    def _generate_title(self, text: str, category: str) -> str:
        """生成知识标题"""
        # 截取前20字作为标题基础
        base = text[:20].strip()
        if len(text) > 20:
            base += '...'
        return f"[{category}] {base}"
    
    def _generate_content(self, text: str, keywords: List[str], category: str) -> str:
        """生成知识内容"""
        content_parts = [f"用户反馈（{category}类）：{text}"]
        if keywords:
            content_parts.append(f"关联关键词：{', '.join(keywords[:5])}")
        content_parts.append(f"提取时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
        return '\n'.join(content_parts)
    
    def _calculate_confidence(self, text: str, keywords: List[str]) -> float:
        """计算置信度"""
        score = 0.3  # 基础分
        
        # 文本长度（信息量）
        if len(text) > 20:
            score += 0.2
        if len(text) > 50:
            score += 0.1
        
        # 关键词数量（结构化程度）
        if len(keywords) >= 3:
            score += 0.2
        if len(keywords) >= 6:
            score += 0.1
        
        # 包含具体建议
        suggestion_words = ['建议', '应该', '需要', '最好', '改为', '增加', '减少']
        if any(w in text for w in suggestion_words):
            score += 0.1
        
        return min(1.0, score)
    
    def _save_knowledge(self, knowledge: RefinedKnowledge):
        """保存知识点到数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO refined_knowledge 
                (source_feedback_id, category, subcategory, title, content, keywords, source_type, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                knowledge.source_feedback_id,
                knowledge.category,
                knowledge.subcategory,
                knowledge.title,
                knowledge.content,
                json.dumps(knowledge.keywords, ensure_ascii=False),
                knowledge.source_type,
                knowledge.confidence,
                knowledge.created_at,
            ))
            knowledge.id = cursor.lastrowid
            conn.commit()
    
    def _mark_feedback_processed(self, feedback_id: int, knowledge_extracted: bool = True):
        """标记反馈已处理"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if knowledge_extracted:
                cursor.execute("UPDATE feedback SET knowledge_extracted = 1, processed = 1 WHERE id = ?",
                             (feedback_id,))
            else:
                cursor.execute("UPDATE feedback SET processed = 1 WHERE id = ?", (feedback_id,))
            conn.commit()
