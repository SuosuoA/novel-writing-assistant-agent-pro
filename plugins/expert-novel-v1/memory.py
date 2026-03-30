"""
专家记忆模块 - Claw记忆集成

版本: 1.0.0
创建日期: 2026-03-29

核心功能:
1. L1热记忆：SessionState（当前会话快速访问）
2. L2温记忆：VectorStore（语义检索）
3. 用户反馈学习
4. 记忆优化策略

设计原则:
- 越用越聪明：从历史中学习
- 异常安全：失败不影响主流程
- 轻量高效：最小化存储开销
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass

try:
    from .models import ExpertEvaluation, OptimizationSuggestion, UserFeedback
except ImportError:
    from models import ExpertEvaluation, OptimizationSuggestion, UserFeedback

logger = logging.getLogger(__name__)


class ExpertMemory:
    """
    专家记忆系统
    
    记忆层级:
    - L1热记忆: 内存缓存（当前会话快速访问）
    - L2温记忆: VectorStore（语义检索）
    - L3冷记忆: 文件存储（持久化）
    
    核心功能:
    1. 存储评分结果
    2. 存储优化建议
    3. 存储用户反馈
    4. 检索相似问题
    5. 学习优化策略
    """
    
    def __init__(self, memory_path: Optional[str] = None):
        """
        初始化记忆系统
        
        Args:
            memory_path: 记忆存储路径
        """
        # L1热记忆（内存缓存）
        self._hot_memory: Dict[str, Any] = {}
        
        # 记忆命名空间
        self.namespace = "expert_memory"
        
        # 记忆路径
        if memory_path:
            self.memory_path = Path(memory_path)
        else:
            self.memory_path = Path(__file__).parent.parent.parent / "data" / "expert_memory"
        
        # 确保目录存在
        self.memory_path.mkdir(parents=True, exist_ok=True)
        
        # VectorStore引用（延迟加载）
        self._vector_store = None
        
        # TTL配置
        self.l1_ttl = 3600  # 1小时
    
    def store_evaluation(self, evaluation: ExpertEvaluation, chapter_id: str):
        """
        存储评分结果到记忆系统
        
        L1: 存入内存缓存（当前会话快速访问）
        L2: 存入文件系统（持久化）
        
        Args:
            evaluation: 评估结果
            chapter_id: 章节ID
        """
        # L1 热记忆
        cache_key = f"evaluation_{chapter_id}"
        self._hot_memory[cache_key] = {
            "data": evaluation.to_dict(),
            "timestamp": datetime.now().isoformat(),
            "ttl": self.l1_ttl
        }
        
        # L2 持久化存储
        try:
            file_path = self.memory_path / f"evaluation_{chapter_id}.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(evaluation.to_dict(), f, ensure_ascii=False, indent=2)
            
            logger.debug(f"评分结果已存储: {chapter_id}")
        except Exception as e:
            logger.warning(f"存储评分结果失败: {e}")
    
    def store_optimization(self, suggestion: OptimizationSuggestion, chapter_id: str):
        """
        存储优化建议到记忆系统
        
        Args:
            suggestion: 优化建议
            chapter_id: 章节ID
        """
        # L1 热记忆
        cache_key = f"optimization_{chapter_id}"
        self._hot_memory[cache_key] = {
            "data": suggestion.to_dict(),
            "timestamp": datetime.now().isoformat(),
            "ttl": self.l1_ttl
        }
        
        # L2 持久化存储
        try:
            file_path = self.memory_path / f"optimization_{chapter_id}.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(suggestion.to_dict(), f, ensure_ascii=False, indent=2)
            
            logger.debug(f"优化建议已存储: {chapter_id}")
        except Exception as e:
            logger.warning(f"存储优化建议失败: {e}")
    
    def store_feedback(self, feedback: UserFeedback):
        """
        存储用户反馈
        
        用户采纳了哪些建议？拒绝了哪些建议？
        这些反馈将优化未来的建议生成
        
        Args:
            feedback: 用户反馈
        """
        # L1 热记忆
        cache_key = f"feedback_{feedback.chapter_id}"
        self._hot_memory[cache_key] = {
            "data": feedback.to_dict(),
            "timestamp": datetime.now().isoformat(),
            "ttl": self.l1_ttl
        }
        
        # L2 持久化存储
        try:
            # 追加到反馈历史文件
            feedback_file = self.memory_path / "feedback_history.json"
            
            history = []
            if feedback_file.exists():
                with open(feedback_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            
            history.append(feedback.to_dict())
            
            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"用户反馈已存储: {feedback.chapter_id}")
            
            # 触发记忆优化事件
            self._analyze_feedback_patterns(history)
        except Exception as e:
            logger.warning(f"存储用户反馈失败: {e}")
    
    def retrieve_evaluation(self, chapter_id: str) -> Optional[ExpertEvaluation]:
        """
        检索评分结果
        
        Args:
            chapter_id: 章节ID
            
        Returns:
            ExpertEvaluation: 评估结果，不存在返回None
        """
        # 先查L1热记忆
        cache_key = f"evaluation_{chapter_id}"
        if cache_key in self._hot_memory:
            cached = self._hot_memory[cache_key]
            return ExpertEvaluation.from_dict(cached["data"])
        
        # 查L2持久化存储
        try:
            file_path = self.memory_path / f"evaluation_{chapter_id}.json"
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return ExpertEvaluation.from_dict(data)
        except Exception as e:
            logger.warning(f"检索评分结果失败: {e}")
        
        return None
    
    def retrieve_similar_issues(self, issue_description: str, top_k: int = 5) -> List[Dict]:
        """
        检索相似问题及解决方案
        
        从记忆中检索历史上遇到的类似问题
        
        Args:
            issue_description: 问题描述
            top_k: 返回数量
            
        Returns:
            List[Dict]: 相似问题列表
        """
        results = []
        
        try:
            # 遍历所有存储的优化记录
            for file_path in self.memory_path.glob("optimization_*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 简单匹配：检查关键词重叠
                    suggestions = data.get("dimension_suggestions", {})
                    overlap = self._calculate_overlap(issue_description, str(suggestions))
                    
                    if overlap > 0.3:  # 30%以上重叠
                        results.append({
                            "file": str(file_path),
                            "data": data,
                            "overlap": overlap
                        })
                except Exception:
                    continue
            
            # 按重叠度排序
            results.sort(key=lambda x: x["overlap"], reverse=True)
            
            return results[:top_k]
        except Exception as e:
            logger.warning(f"检索相似问题失败: {e}")
            return []
    
    def _calculate_overlap(self, text1: str, text2: str) -> float:
        """计算文本重叠度"""
        if not text1 or not text2:
            return 0.0
        
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union) if union else 0.0
    
    def learn_from_feedback(self, feedback: UserFeedback) -> Dict[str, Any]:
        """
        从用户反馈中学习
        
        分析用户采纳了哪些建议，拒绝了哪些建议
        返回优化策略
        
        Args:
            feedback: 用户反馈
            
        Returns:
            Dict: 学习结果和优化策略
        """
        learning_result = {
            "chapter_id": feedback.chapter_id,
            "accepted_count": len(feedback.accepted_suggestions),
            "rejected_count": len(feedback.rejected_suggestions),
            "rating": feedback.user_rating,
            "patterns": []
        }
        
        # 分析模式
        if feedback.user_rating >= 4.0:
            # 高分案例：记录成功模式
            learning_result["patterns"].append({
                "type": "success",
                "suggestion": "当前优化策略有效"
            })
        elif feedback.user_rating < 3.0:
            # 低分案例：记录失败模式
            learning_result["patterns"].append({
                "type": "failure",
                "suggestion": "优化策略需要调整"
            })
        
        # 存储学习结果
        self.store_feedback(feedback)
        
        return learning_result
    
    def _analyze_feedback_patterns(self, history: List[Dict]):
        """
        分析反馈模式
        
        识别哪些类型的建议更受欢迎
        
        Args:
            history: 反馈历史
        """
        if len(history) < 5:
            return
        
        try:
            # 统计各维度的接受率
            dimension_stats = {}
            
            for record in history:
                accepted = record.get("accepted_suggestions", [])
                rejected = record.get("rejected_suggestions", [])
                
                for item in accepted:
                    # 提取维度
                    for dim in ["世界观", "人设", "大纲", "风格", "知识库", 
                               "写作技巧", "字数", "上下文衔接", "AI感"]:
                        if dim in item:
                            if dim not in dimension_stats:
                                dimension_stats[dim] = {"accepted": 0, "rejected": 0}
                            dimension_stats[dim]["accepted"] += 1
                
                for item in rejected:
                    for dim in ["世界观", "人设", "大纲", "风格", "知识库",
                               "写作技巧", "字数", "上下文衔接", "AI感"]:
                        if dim in item:
                            if dim not in dimension_stats:
                                dimension_stats[dim] = {"accepted": 0, "rejected": 0}
                            dimension_stats[dim]["rejected"] += 1
            
            # 计算接受率
            for dim, stats in dimension_stats.items():
                total = stats["accepted"] + stats["rejected"]
                if total > 0:
                    acceptance_rate = stats["accepted"] / total
                    logger.debug(f"维度 {dim} 建议接受率: {acceptance_rate:.2%}")
        except Exception as e:
            logger.warning(f"分析反馈模式失败: {e}")
    
    def get_optimization_history(self, limit: int = 10) -> List[Dict]:
        """
        获取优化历史
        
        Args:
            limit: 返回数量
            
        Returns:
            List[Dict]: 历史记录
        """
        history = []
        
        try:
            files = sorted(
                self.memory_path.glob("optimization_*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            
            for file_path in files[:limit]:
                with open(file_path, 'r', encoding='utf-8') as f:
                    history.append(json.load(f))
        except Exception as e:
            logger.warning(f"获取优化历史失败: {e}")
        
        return history
    
    def clear_cache(self):
        """清除L1热记忆缓存"""
        self._hot_memory.clear()
        logger.info("L1热记忆缓存已清除")
    
    def cleanup(self):
        """清理资源"""
        self.clear_cache()
        logger.info("专家记忆系统资源已清理")


# 导出
__all__ = ['ExpertMemory']
