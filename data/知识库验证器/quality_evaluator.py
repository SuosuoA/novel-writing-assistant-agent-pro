#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
质量评估器 - 五维度质量标准

评估维度：
1. 内容长度（25%） - 目标2000-3000字
2. 关键词数量（20%） - 目标8-12个
3. 参考作品数量（20%） - 目标≥3个
4. 内容相关性（20%） - 标题/内容/关键词一致
5. 语言质量（15%） - 清晰、无语法错误
"""

import logging
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class QualityScore(BaseModel):
    """质量评分结果"""
    
    overall_score: float = Field(..., description="总分（0-10分）")
    dimension_scores: Dict[str, float] = Field(default_factory=dict, description="各维度得分")
    issues: List[str] = Field(default_factory=list, description="发现的问题")
    passed: bool = Field(..., description="是否通过（≥threshold）")


class QualityEvaluator:
    """质量评估器 - 多维度质量标准"""
    
    def __init__(self, 
                 quality_threshold: Optional[float] = None,
                 auto_delete_threshold: Optional[float] = None):
        """初始化质量评估器
        
        P3优化：支持配置化阈值
        
        Args:
            quality_threshold: 质量评分阈值（可选，默认从配置读取）
            auto_delete_threshold: 自动删除阈值（可选，默认从配置读取）
        """
        # P3优化：从配置文件读取阈值
        try:
            from .config_loader import get_quality_threshold, get_auto_delete_threshold, get_quality_weights
            self.quality_threshold = quality_threshold or get_quality_threshold()
            self.auto_delete_threshold = auto_delete_threshold or get_auto_delete_threshold()
            self.weights = get_quality_weights()
        except ImportError:
            # 降级使用默认值
            self.quality_threshold = quality_threshold or 6.0
            self.auto_delete_threshold = auto_delete_threshold or 4.0
            self.weights = {
                "content_length": 0.25,
                "keyword_count": 0.20,
                "reference_count": 0.20,
                "content_relevance": 0.20,
                "language_quality": 0.15
            }
        
        logger.info(f"[QUALITY_EVALUATOR] 初始化完成, 阈值={self.quality_threshold}")
    
    def evaluate_all(self, 
                    knowledge_list: List[Dict]) -> Dict[str, QualityScore]:
        """
        批量评估知识点质量
        
        Args:
            knowledge_list: 知识点列表
        
        Returns:
            {"kp_id": QualityScore(...)}
        """
        results = {}
        
        for kp in knowledge_list:
            kp_id = kp.get('knowledge_id', '')
            score = self.evaluate_single(kp)
            results[kp_id] = score
        
        return results
    
    def evaluate_single(self, kp: Dict) -> QualityScore:
        """
        评估单个知识点质量
        
        Args:
            kp: 知识点字典
        
        Returns:
            QualityScore(...)
        """
        # 评估各维度
        dimension_scores = {
            "content_length": self._check_content_length(kp),
            "keyword_count": self._check_keyword_count(kp),
            "reference_count": self._check_reference_count(kp),
            "content_relevance": self._check_content_relevance(kp),
            "language_quality": self._check_language_quality(kp)
        }
        
        # 计算总体评分
        overall_score = self._calculate_overall_score(dimension_scores)
        
        # 判断是否通过
        passed = overall_score >= self.quality_threshold
        
        # 提取问题
        issues = []
        if not passed:
            if dimension_scores['content_length'] < 4.0:
                issues.append("content_too_short")
            if dimension_scores['keyword_count'] < 4.0:
                issues.append("keywords_too_few")
            if dimension_scores['reference_count'] < 4.0:
                issues.append("references_too_few")
        
        return QualityScore(
            overall_score=overall_score,
            dimension_scores=dimension_scores,
            issues=issues,
            passed=passed
        )
    
    def _check_content_length(self, kp: Dict) -> float:
        """
        检查内容长度（目标：3000字左右）
        
        评分标准:
        - ≥2500字: 9-10分
        - 2000-2499字: 7-8分
        - 1000-1999字: 5-6分
        - 500-999字: 3-4分
        - <500字: 0-2分（低质量）
        
        Args:
            kp: 知识点字典
        
        Returns:
            评分 (0-10)
        """
        content_len = len(kp.get('content', ''))
        
        if content_len >= 2500:
            return 9.0 + min(1.0, (content_len - 2500) / 5000)
        elif content_len >= 2000:
            return 7.0 + (content_len - 2000) / 500
        elif content_len >= 1000:
            return 5.0 + (content_len - 1000) / 1000
        elif content_len >= 500:
            return 3.0 + (content_len - 500) / 500
        elif content_len >= 200:
            return 2.0 + (content_len - 200) / 300
        else:
            return max(0.0, content_len / 200 * 2.0)
    
    def _check_keyword_count(self, kp: Dict) -> float:
        """
        检查关键词数量（目标：10个左右）
        
        评分标准:
        - ≥8个: 9-10分
        - 5-7个: 7-8分
        - 3-4个: 5-6分
        - <3个: 0-4分（低质量）
        
        Args:
            kp: 知识点字典
        
        Returns:
            评分 (0-10)
        """
        keyword_count = len(kp.get('keywords', []))
        
        if keyword_count >= 8:
            return 9.0 + min(1.0, (keyword_count - 8) / 10)
        elif keyword_count >= 5:
            return 7.0 + (keyword_count - 5) / 2
        elif keyword_count >= 3:
            return 5.0 + (keyword_count - 3)
        else:
            return max(0.0, keyword_count / 3 * 4.0)
    
    def _check_reference_count(self, kp: Dict) -> float:
        """
        检查参考作品数量（目标：3个以上）
        
        评分标准:
        - ≥3个: 9-10分
        - 2个: 7-8分
        - 1个: 5-6分
        - 0个: 0-4分（低质量）
        
        Args:
            kp: 知识点字典
        
        Returns:
            评分 (0-10)
        """
        ref_count = len(kp.get('references', []))
        
        if ref_count >= 3:
            return 9.0 + min(1.0, (ref_count - 3) / 5)
        elif ref_count >= 2:
            return 7.0 + (ref_count - 2)
        elif ref_count >= 1:
            return 5.0
        else:
            return 4.0  # 无参考作品时给4分（警告但不删除）
    
    def _check_content_relevance(self, kp: Dict) -> float:
        """
        检查内容相关性（是否与标题、关键词一致）
        
        使用规则检测：
        - 标题是否出现在内容中
        - 关键词是否出现在内容中
        
        Args:
            kp: 知识点字典
        
        Returns:
            评分 (0-10)
        """
        title = kp.get('title', '').lower()
        content = kp.get('content', '').lower()
        keywords = [kw.lower() for kw in kp.get('keywords', [])]
        
        score = 5.0  # 基础分
        
        # 检查标题是否出现在内容中
        if title and title in content:
            score += 2.0
        
        # 检查关键词是否出现在内容中
        if keywords:
            keyword_matches = sum(1 for kw in keywords if kw in content)
            match_ratio = keyword_matches / len(keywords)
            
            if match_ratio >= 0.7:  # 至少70%关键词出现
                score += 3.0
            elif match_ratio >= 0.5:  # 至少50%关键词出现
                score += 2.0
            elif match_ratio >= 0.3:  # 至少30%关键词出现
                score += 1.0
        
        return min(10.0, score)
    
    def _check_language_quality(self, kp: Dict) -> float:
        """
        检查语言质量（是否清晰、无语法错误）
        
        使用规则检测：
        - 内容长度是否合理
        - 是否包含明显的乱码
        - 是否包含过短的句子
        
        Args:
            kp: 知识点字典
        
        Returns:
            评分 (0-10)
        """
        content = kp.get('content', '')
        
        score = 5.0  # 基础分
        
        # 检查内容长度
        if len(content) >= 1000:
            score += 2.0
        elif len(content) >= 500:
            score += 1.0
        
        # 检查是否包含乱码（简单检测）
        if '???' not in content and '...' * 10 not in content:
            score += 1.5
        
        # 检查句子结构（简单检测句号）
        sentence_count = content.count('。') + content.count('！') + content.count('？')
        if sentence_count >= 5:
            score += 1.5
        elif sentence_count >= 3:
            score += 1.0
        
        return min(10.0, score)
    
    def _calculate_overall_score(self, dimension_scores: Dict[str, float]) -> float:
        """
        计算总体质量评分
        
        P3优化：使用配置化权重
        
        加权求和
        
        Args:
            dimension_scores: 各维度得分
        
        Returns:
            总分 (0-10)
        """
        # 使用配置化的权重
        overall_score = sum(
            dimension_scores.get(dim, 0) * self.weights.get(dim, 0)
            for dim in self.weights.keys()
        )
        
        return overall_score
    
    def should_auto_delete(self, score: QualityScore) -> bool:
        """
        判断是否应该自动删除
        
        Args:
            score: 质量评分
        
        Returns:
            是否应该自动删除
        """
        # 评分过低
        if score.overall_score < self.auto_delete_threshold:
            return True
        
        # 内容过短 + 关键词过少 + 无参考作品
        if (score.dimension_scores.get('content_length', 10) < 3.0 and
            score.dimension_scores.get('keyword_count', 10) < 3.0 and
            score.dimension_scores.get('reference_count', 10) < 4.0):
            return True
        
        return False
