"""
反馈提纯器 - 从用户反馈中提取可执行知识

V1.0版本
创建日期: 2026-03-26

功能:
- NLP分析用户反馈
- 提取知识点、风格偏好、AI痕迹
- 结构化存储
- 自动去重合并

使用示例:
    from core.feedback_purifier import FeedbackPurifier
    
    purifier = FeedbackPurifier()
    knowledge_points = purifier.purify(
        feedback_text="这个对话太生硬了，不像角色会说的话",
        feedback_type="style"
    )
"""

import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import jieba
import jieba.analyse

logger = logging.getLogger(__name__)


@dataclass
class KnowledgePoint:
    """知识点数据类"""
    category: str  # style / ai_feeling / content / conflict
    content: str
    tags: List[str]
    source: str  # "用户反馈"
    weight: float  # 0.0-1.0
    context: Dict[str, Any]
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class FeedbackPurifier:
    """
    反馈提纯器
    
    功能:
    - NLP分析反馈文本
    - 提取知识点
    - 结构化存储
    """
    
    # AI痕迹词库
    AI_FEELING_WORDS = [
        "仿佛", "似乎", "宛如", "如同",
        "不禁", "不由得", "忍不住",
        "一股", "一种", "一阵",
        "微微", "轻声", "缓缓",
        "淡淡的", "莫名的", "说不出的"
    ]
    
    # 风格问题关键词
    STYLE_KEYWORDS = {
        "对话": ["对话", "台词", "说话"],
        "描写": ["描写", "叙述", "文笔"],
        "节奏": ["节奏", "拖沓", "紧凑"],
        "情感": ["情感", "感情", "情绪"]
    }
    
    def __init__(self):
        """初始化反馈提纯器"""
        # 加载自定义词典
        self._load_custom_dict()
        logger.info("FeedbackPurifier initialized")
    
    def _load_custom_dict(self):
        """加载自定义词典"""
        # 添加AI痕迹词到词典
        for word in self.AI_FEELING_WORDS:
            jieba.add_word(word)
    
    def purify(self, feedback_text: str, feedback_type: str,
               context: Optional[Dict[str, Any]] = None) -> List[KnowledgePoint]:
        """
        提纯反馈，提取知识点
        
        Args:
            feedback_text: 反馈文本
            feedback_type: 反馈类型
            context: 上下文信息
        
        Returns:
            提取的知识点列表
        """
        knowledge_points = []
        
        # 1. NLP分析
        analysis = self._analyze_feedback(feedback_text)
        
        # 2. 根据类型提取知识点
        if feedback_type == "style":
            kp = self._extract_style_knowledge(feedback_text, analysis)
            if kp:
                knowledge_points.append(kp)
        
        elif feedback_type == "ai_feeling":
            kp = self._extract_ai_feeling_knowledge(feedback_text, analysis)
            if kp:
                knowledge_points.append(kp)
        
        elif feedback_type == "content":
            kp = self._extract_content_knowledge(feedback_text, analysis)
            if kp:
                knowledge_points.append(kp)
        
        # 3. 去重
        knowledge_points = self._deduplicate(knowledge_points)
        
        logger.info(f"Purified feedback: {feedback_type} -> {len(knowledge_points)} knowledge points")
        return knowledge_points
    
    def _analyze_feedback(self, feedback_text: str) -> Dict[str, Any]:
        """
        NLP分析反馈文本
        
        Returns:
            分析结果字典
        """
        # 分词
        words = list(jieba.cut(feedback_text))
        
        # 关键词提取
        keywords = jieba.analyse.extract_tags(feedback_text, topK=10)
        
        # 情感分析（简化版）
        sentiment = self._analyze_sentiment(feedback_text)
        
        return {
            "words": words,
            "keywords": keywords,
            "sentiment": sentiment
        }
    
    def _analyze_sentiment(self, text: str) -> str:
        """情感分析（简化版）"""
        negative_words = ["不好", "太", "生硬", "空洞", "拖沓", "不自然"]
        positive_words = ["好", "喜欢", "不错", "自然", "流畅"]
        
        neg_count = sum(1 for w in negative_words if w in text)
        pos_count = sum(1 for w in positive_words if w in text)
        
        if neg_count > pos_count:
            return "negative"
        elif pos_count > neg_count:
            return "positive"
        else:
            return "neutral"
    
    def _extract_style_knowledge(self, text: str, analysis: Dict) -> Optional[KnowledgePoint]:
        """提取风格知识点"""
        # 检测风格类型
        style_type = None
        for key, keywords in self.STYLE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                style_type = key
                break
        
        if not style_type:
            return None
        
        # 构建知识点
        content = self._build_style_content(text, style_type)
        
        return KnowledgePoint(
            category="style",
            content=content,
            tags=[style_type, "风格"],
            source="用户反馈",
            weight=0.9,
            context={
                "original_feedback": text,
                "style_type": style_type,
                "keywords": analysis["keywords"]
            }
        )
    
    def _extract_ai_feeling_knowledge(self, text: str, analysis: Dict) -> Optional[KnowledgePoint]:
        """提取AI痕迹知识点"""
        # 检测AI痕迹词
        detected_words = [w for w in self.AI_FEELING_WORDS if w in text]
        
        if not detected_words:
            return None
        
        # 构建知识点
        content = f"避免使用{','.join(detected_words)}等AI痕迹表达"
        
        return KnowledgePoint(
            category="ai_feeling",
            content=content,
            tags=["AI痕迹", "自然度"],
            source="用户反馈",
            weight=0.95,
            context={
                "original_feedback": text,
                "ai_words": detected_words
            }
        )
    
    def _extract_content_knowledge(self, text: str, analysis: Dict) -> Optional[KnowledgePoint]:
        """提取内容知识点"""
        # 简化实现：直接提取关键词作为知识点
        keywords = analysis["keywords"][:3]  # 最多3个关键词
        
        if not keywords:
            return None
        
        content = f"注意{','.join(keywords)}相关问题"
        
        return KnowledgePoint(
            category="content",
            content=content,
            tags=keywords,
            source="用户反馈",
            weight=0.85,
            context={
                "original_feedback": text,
                "keywords": keywords
            }
        )
    
    def _build_style_content(self, text: str, style_type: str) -> str:
        """构建风格知识点内容"""
        if style_type == "对话":
            return "对话要自然，符合人物性格，避免书面化表达"
        elif style_type == "描写":
            return "描写要有细节感，形成画面感，避免空洞"
        elif style_type == "节奏":
            return "节奏要紧凑，避免拖沓，推动剧情发展"
        elif style_type == "情感":
            return "情感描写要真实，避免刻意煽情"
        else:
            return f"改进{style_type}相关问题"
    
    def _deduplicate(self, knowledge_points: List[KnowledgePoint]) -> List[KnowledgePoint]:
        """去重"""
        seen = set()
        unique = []
        
        for kp in knowledge_points:
            key = (kp.category, kp.content)
            if key not in seen:
                seen.add(key)
                unique.append(kp)
        
        return unique


# 全局单例
_feedback_purifier_instance: Optional[FeedbackPurifier] = None


def get_feedback_purifier() -> FeedbackPurifier:
    """获取反馈提纯器单例"""
    global _feedback_purifier_instance
    if _feedback_purifier_instance is None:
        _feedback_purifier_instance = FeedbackPurifier()
    return _feedback_purifier_instance
