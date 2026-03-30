"""
本地模型辅助 - 语义相似度和AI特征检测

版本: 1.0.0
创建日期: 2026-03-29

核心功能:
1. 语义相似度计算
2. AI生成特征检测
3. 降级方案（Jaccard相似度）

设计原则:
- 延迟加载：首次使用时初始化模型
- 降级可用：模型加载失败时使用字符串匹配
- 轻量高效：最小化计算开销
"""

import re
import logging
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class LocalModelAssistant:
    """
    本地模型辅助评分
    
    核心功能:
    1. 语义相似度计算（使用sentence_transformers）
    2. AI生成特征检测
    3. 降级方案（Jaccard相似度）
    
    设计原则:
    - 延迟加载：首次使用时初始化模型
    - 降级可用：模型加载失败时使用字符串匹配
    - 轻量高效：最小化计算开销
    """
    
    def __init__(self, model_cache_path: Optional[str] = None):
        """
        初始化本地模型辅助
        
        Args:
            model_cache_path: 模型缓存路径
        """
        # 模型缓存路径
        if model_cache_path:
            self.model_cache_path = Path(model_cache_path)
        else:
            self.model_cache_path = Path(__file__).parent.parent.parent / "sentence_transformers_cache"
        
        # 模型实例（延迟加载）
        self.model = None
        self._initialized = False
        self._init_error = None
    
    def initialize(self) -> bool:
        """
        延迟初始化模型
        
        Returns:
            bool: 初始化是否成功
        """
        if self._initialized:
            return self.model is not None
        
        try:
            # 尝试加载sentence_transformers
            from sentence_transformers import SentenceTransformer
            
            # 设置离线模式
            import os
            os.environ['HF_HUB_OFFLINE'] = '1'
            
            # 从缓存加载模型
            model_name = 'paraphrase-multilingual-MiniLM-L12-v2'
            
            if self.model_cache_path.exists():
                self.model = SentenceTransformer(
                    model_name,
                    cache_folder=str(self.model_cache_path)
                )
                logger.info("本地模型加载成功")
            else:
                logger.warning(f"模型缓存目录不存在: {self.model_cache_path}")
                self.model = None
            
            self._initialized = True
            return self.model is not None
            
        except ImportError as e:
            self._init_error = f"sentence_transformers未安装: {e}"
            logger.warning(self._init_error)
            self._initialized = True
            return False
            
        except Exception as e:
            self._init_error = f"本地模型加载失败: {e}"
            logger.warning(self._init_error)
            self._initialized = True
            return False
    
    def calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """
        计算语义相似度
        
        用途:
        1. 检查内容与世界观设定的相似度
        2. 检查人物对话与性格的一致性
        3. 检查风格匹配度
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            float: 相似度（0.0-1.0）
        """
        # 确保初始化
        if not self._initialized:
            self.initialize()
        
        # 如果模型可用，使用模型计算
        if self.model:
            try:
                return self._model_similarity(text1, text2)
            except Exception as e:
                logger.warning(f"模型相似度计算失败: {e}")
        
        # 降级方案：使用简单字符串匹配
        return self._simple_similarity(text1, text2)
    
    def _model_similarity(self, text1: str, text2: str) -> float:
        """使用模型计算相似度"""
        if not text1 or not text2:
            return 0.0
        
        try:
            import numpy as np
            from sklearn.metrics.pairwise import cosine_similarity
            
            # 生成嵌入向量
            embeddings = self.model.encode([text1, text2])
            
            # 计算余弦相似度
            similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
            
            return float(similarity)
        except Exception as e:
            logger.warning(f"模型计算失败: {e}")
            return self._simple_similarity(text1, text2)
    
    def _simple_similarity(self, text1: str, text2: str) -> float:
        """
        简单的字符串相似度（降级方案）
        
        使用Jaccard相似度
        """
        if not text1 or not text2:
            return 0.0
        
        # 分词（简单按字符分割）
        set1 = set(text1)
        set2 = set(text2)
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def detect_ai_patterns(self, content: str) -> float:
        """
        检测AI生成模式
        
        返回：0.0 (完全自然) - 1.0 (明显AI痕迹)
        
        检测规则:
        1. AI常见句式（首先...其次...最后）
        2. 模板化表达（总的来说、综上所述）
        3. 过度结构化（一方面...另一方面）
        
        Args:
            content: 待检测内容
            
        Returns:
            float: AI特征分数（越高表示AI痕迹越明显）
        """
        if not content:
            return 0.5
        
        ai_score = 0.0
        
        # AI常见模式列表
        ai_patterns = [
            # 结构化表达
            (r"首先.*其次.*最后", 0.2),
            (r"一方面.*另一方面", 0.15),
            (r"第一.*第二.*第三", 0.15),
            
            # 总结性表达
            (r"总的来说", 0.1),
            (r"综上所述", 0.1),
            (r"总而言之", 0.1),
            
            # 过度解释
            (r"值得注意的是", 0.1),
            (r"不可否认", 0.1),
            (r"由此可见", 0.1),
            (r"显而易见", 0.1),
            
            # 模板化表达
            (r"让我们.*吧", 0.1),
            (r"作为一个AI", 0.3),  # 明显AI痕迹
            (r"我必须说明", 0.1),
            
            # 过度使用引号
            (r'"[^"]{20,}"[^"]{20,}"[^"]{20,}"', 0.1),
            
            # 重复结构
            (r"(.{10,})\1{2,}", 0.2)
        ]
        
        # 检测每个模式
        for pattern, weight in ai_patterns:
            if re.search(pattern, content):
                ai_score += weight
        
        # 检测句式重复
        sentences = re.split(r'[。！？\n]', content)
        if len(sentences) > 3:
            # 检查句式相似度
            sentence_starts = [s[:10] for s in sentences if s.strip()]
            if len(sentence_starts) > 3:
                unique_starts = set(sentence_starts)
                if len(unique_starts) < len(sentence_starts) * 0.5:
                    ai_score += 0.1
        
        # 检测词汇丰富度
        words = re.findall(r'[\u4e00-\u9fa5]+', content)
        if len(words) > 50:
            unique_words = set(words)
            richness = len(unique_words) / len(words)
            if richness < 0.3:  # 词汇重复度高
                ai_score += 0.1
        
        return min(1.0, ai_score)
    
    def calculate_naturalness(self, content: str) -> float:
        """
        计算文本自然度
        
        返回：0.0 (明显AI) - 1.0 (完全自然)
        
        Args:
            content: 待检测内容
            
        Returns:
            float: 自然度分数（越高越好）
        """
        ai_score = self.detect_ai_patterns(content)
        return 1.0 - ai_score
    
    def batch_similarity(self, text: str, references: List[str]) -> float:
        """
        批量计算相似度
        
        计算文本与多个参考文本的平均相似度
        
        Args:
            text: 目标文本
            references: 参考文本列表
            
        Returns:
            float: 平均相似度
        """
        if not references:
            return 0.5
        
        similarities = [
            self.calculate_semantic_similarity(text, ref)
            for ref in references
        ]
        
        return sum(similarities) / len(similarities)
    
    def get_model_status(self) -> dict:
        """
        获取模型状态
        
        Returns:
            dict: 模型状态信息
        """
        return {
            "initialized": self._initialized,
            "model_available": self.model is not None,
            "cache_path": str(self.model_cache_path),
            "cache_exists": self.model_cache_path.exists(),
            "error": self._init_error
        }
    
    def cleanup(self):
        """清理资源"""
        if self.model:
            del self.model
            self.model = None
        
        self._initialized = False
        logger.info("本地模型资源已清理")


# 导出
__all__ = ['LocalModelAssistant']
