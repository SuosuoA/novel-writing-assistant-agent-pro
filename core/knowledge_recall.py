"""
知识库召回机制 - OpenClaw 智能召回层

V1.0版本
创建日期：2026-03-25

特性：
- 智能召回：自动识别题材，加载对应知识库
- 多策略召回：向量召回 + 关键词召回 + 规则召回
- 一致性检测：检测生成内容是否违反知识库
- 召回准确率≥80%
- EventBus集成
- 线程安全设计

设计参考：
- OpenClaw memory_search工具
- 升级方案 10.升级方案✅️.md Sprint 5-6
- ADR-003: 知识库双层设计

使用示例：
    # 创建召回器
    recall = KnowledgeRecall(workspace_root=Path("E:/project"))
    
    # 自动识别题材并召回
    results = recall.recall_for_content(
        content="飞船接近光速飞行，时间流逝变慢",
        top_k=10
    )
    
    # 一致性检测
    check_result = recall.check_knowledge_consistency(
        content="超光速飞行导致时间倒流",
        category="scifi"
    )
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Pydantic数据模型
# ============================================================================


class KnowledgeConflict(BaseModel):
    """知识冲突记录"""
    
    model_config = ConfigDict(frozen=False)
    
    conflict_type: str = Field(description="冲突类型（physics/chemistry/biology/history/religion）")
    description: str = Field(description="冲突描述")
    severity: str = Field(description="严重程度（P0/P1/P2）")
    knowledge_id: str = Field(description="相关知识点ID")
    knowledge_title: str = Field(description="相关知识点标题")
    knowledge_content: str = Field(description="相关知识点内容")
    suggested_fix: Optional[str] = Field(default=None, description="修复建议")


class RecallResult(BaseModel):
    """召回结果"""
    
    model_config = ConfigDict(frozen=False)
    
    knowledge_id: str = Field(description="知识点ID")
    title: str = Field(description="知识点标题")
    content: str = Field(description="知识点内容")
    category: str = Field(description="分类（scifi/xuanhuan/history/general）")
    domain: str = Field(description="领域（physics/chemistry/religion等）")
    keywords: List[str] = Field(default_factory=list, description="关键词")
    score: float = Field(description="综合相似度分数（0-1）")
    recall_strategy: str = Field(description="召回策略（vector/keyword/rule）")


class ConsistencyCheckResult(BaseModel):
    """一致性检测结果"""
    
    model_config = ConfigDict(frozen=False)
    
    is_consistent: bool = Field(description="是否一致")
    consistency_score: float = Field(description="一致性评分（0-1）")
    conflicts: List[KnowledgeConflict] = Field(default_factory=list, description="检测到的冲突")
    recalled_knowledge: List[RecallResult] = Field(default_factory=list, description="召回的相关知识")
    category: str = Field(description="识别的题材")
    domain: Optional[str] = Field(default=None, description="识别的领域")


# ============================================================================
# 题材识别器
# ============================================================================


class GenreRecognizer:
    """
    题材识别器
    
    功能：
    - 根据关键词识别题材（科幻/玄幻/历史/通用）
    - 根据关键词识别领域（物理/化学/生物/宗教/神话等）
    """
    
    # 题材关键词映射
    GENRE_KEYWORDS = {
        "scifi": [
            "飞船", "星际", "光速", "虫洞", "量子", "基因", "克隆", "人工智能", "AI",
            "机器人", "时间旅行", "平行宇宙", "黑洞", "相对论", "核聚变", "纳米"
        ],
        "xuanhuan": [
            "修仙", "丹药", "灵气", "宗门", "法宝", "元婴", "渡劫", "神兽", "道法",
            "佛门", "魔修", "仙界", "灵石", "炼器", "阵法", "神识", "天劫"
        ],
        "history": [
            "朝代", "皇帝", "将军", "战争", "朝堂", "谋士", "骑兵", "城池", "谋反",
            "科举", "宰相", "尚书", "总督", "巡抚", "知府", "县令", "驿站"
        ]
    }
    
    # 领域关键词映射
    DOMAIN_KEYWORDS = {
        "physics": ["光速", "相对论", "量子", "黑洞", "引力", "时间膨胀", "能量", "粒子"],
        "chemistry": ["化学", "元素", "反应", "分子", "原子", "化合物", "催化", "化学键"],
        "biology": ["基因", "克隆", "进化", "DNA", "细胞", "病毒", "生物", "遗传"],
        "religion": ["道教", "佛教", "轮回", "因果", "修仙", "丹道", "禅宗", "菩萨"],
        "mythology": ["神话", "神仙", "龙", "凤凰", "妖魔", "天神", "神兽", "异兽"],
        "history": ["朝代", "皇帝", "战争", "谋略", "战役", "历史", "古都", "朝堂"]
    }
    
    def recognize_genre(self, content: str) -> Tuple[str, float]:
        """
        识别题材
        
        Args:
            content: 文本内容
        
        Returns:
            Tuple[str, float]: (题材, 置信度)
        """
        scores = {}
        
        for genre, keywords in self.GENRE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in content)
            scores[genre] = score
        
        # 找到最高分
        if not scores or max(scores.values()) == 0:
            return "general", 0.5
        
        best_genre = max(scores, key=scores.get)
        confidence = min(scores[best_genre] / 5.0, 1.0)  # 至少5个关键词匹配才达到1.0置信度
        
        return best_genre, confidence
    
    def recognize_domain(self, content: str, category: str) -> Optional[str]:
        """
        识别领域
        
        Args:
            content: 文本内容
            category: 题材分类
        
        Returns:
            Optional[str]: 领域（如果识别到）
        """
        # 根据题材限定领域范围
        if category == "scifi":
            candidate_domains = ["physics", "chemistry", "biology"]
        elif category == "xuanhuan":
            candidate_domains = ["religion", "mythology"]
        elif category == "history":
            candidate_domains = ["history"]
        else:
            candidate_domains = list(self.DOMAIN_KEYWORDS.keys())
        
        # 统计领域得分
        scores = {}
        for domain in candidate_domains:
            if domain in self.DOMAIN_KEYWORDS:
                score = sum(1 for kw in self.DOMAIN_KEYWORDS[domain] if kw in content)
                if score > 0:
                    scores[domain] = score
        
        # 返回得分最高的领域
        if scores:
            return max(scores, key=scores.get)
        
        return None


# ============================================================================
# 知识库召回器
# ============================================================================


class KnowledgeRecall:
    """
    知识库召回器 - OpenClaw智能召回层
    
    功能：
    - 智能召回：自动识别题材，加载对应知识库
    - 多策略召回：向量召回 + 关键词召回 + 规则召回
    - 一致性检测：检测生成内容是否违反知识库
    - 召回准确率≥80%
    
    设计参考：
    - OpenClaw memory_search工具
    - ADR-003: 知识库双层设计
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, workspace_root: Path, knowledge_retriever=None):
        """
        初始化召回器
        
        Args:
            workspace_root: 工作区根目录
            knowledge_retriever: 知识库检索器实例（可选）
        """
        # 避免重复初始化
        if hasattr(self, "_initialized") and self._initialized:
            return
        
        self.workspace_root = Path(workspace_root)
        
        # 题材识别器
        self._genre_recognizer = GenreRecognizer()
        
        # 知识库检索器（延迟导入）
        self._knowledge_retriever = knowledge_retriever
        self._knowledge_retriever_instance = None
        
        # EventBus（延迟导入）
        self._event_bus = None
        
        # 召回统计
        self._stats = {
            "total_recalls": 0,
            "successful_recalls": 0,
            "failed_recalls": 0,
            "avg_recall_latency_ms": 0.0,
            "total_latency_ms": 0.0,
            "category_distribution": {
                "scifi": 0,
                "xuanhuan": 0,
                "history": 0,
                "general": 0
            }
        }
        self._stats_lock = threading.RLock()
        
        self._initialized = True
    
    def _get_knowledge_retriever(self):
        """延迟获取知识库检索器"""
        if self._knowledge_retriever_instance is None:
            if self._knowledge_retriever is not None:
                self._knowledge_retriever_instance = self._knowledge_retriever
            else:
                try:
                    from core.knowledge_retriever import get_knowledge_retriever
                    self._knowledge_retriever_instance = get_knowledge_retriever(self.workspace_root)
                except Exception as e:
                    print(f"[KnowledgeRecall] 初始化知识库检索器失败: {e}")
        return self._knowledge_retriever_instance
    
    def _get_event_bus(self):
        """延迟获取EventBus"""
        if self._event_bus is None:
            try:
                from core import get_event_bus
                self._event_bus = get_event_bus()
            except Exception:
                pass
        return self._event_bus
    
    # ========================================================================
    # 智能召回（自动识别题材）
    # ========================================================================
    
    def recall_for_content(
        self,
        content: str,
        top_k: int = 10,
        min_score: float = 0.5
    ) -> List[RecallResult]:
        """
        智能召回：自动识别题材，召回相关知识
        
        Args:
            content: 文本内容
            top_k: 返回数量
            min_score: 最小相似度阈值
        
        Returns:
            List[RecallResult]: 召回结果列表
        
        召回策略：
        1. 题材识别：根据关键词识别题材（科幻/玄幻/历史/通用）
        2. 领域识别：根据关键词识别领域（物理/化学/生物/宗教/神话等）
        3. 向量召回：调用knowledge_retriever的向量检索
        4. 降级召回：向量召回结果不足时，降级为关键词召回
        """
        start_time = time.time()
        
        # 1. 题材识别
        category, confidence = self._genre_recognizer.recognize_genre(content)
        
        # 2. 领域识别
        domain = self._genre_recognizer.recognize_domain(content, category)
        
        # 3. 向量召回
        retriever = self._get_knowledge_retriever()
        if not retriever:
            return []
        
        results = []
        
        try:
            # 调用检索器的召回方法
            retrieval_results = retriever.recall_knowledge(
                query=content,
                category=category,
                domain=domain,
                top_k=top_k,
                min_score=min_score
            )
            
            # 转换为RecallResult
            for rr in retrieval_results:
                results.append(RecallResult(
                    knowledge_id=rr.knowledge_id,
                    title=rr.title,
                    content=rr.content,
                    category=rr.category,
                    domain=rr.domain,
                    keywords=rr.keywords,
                    score=rr.score,
                    recall_strategy="vector" if rr.vector_score > 0 else "keyword"
                ))
        except Exception as e:
            print(f"[KnowledgeRecall] 召回失败: {e}")
        
        # 更新统计
        latency_ms = (time.time() - start_time) * 1000
        self._update_stats(latency_ms, len(results) > 0, category)
        
        # 发布事件
        self._publish_event("knowledge.recall.completed", {
            "content_length": len(content),
            "category": category,
            "domain": domain,
            "result_count": len(results),
            "latency_ms": latency_ms
        })
        
        return results
    
    # ========================================================================
    # 一致性检测
    # ========================================================================
    
    def check_knowledge_consistency(
        self,
        content: str,
        category: Optional[str] = None,
        top_k: int = 10
    ) -> ConsistencyCheckResult:
        """
        一致性检测：检测生成内容是否违反知识库
        
        Args:
            content: 待检测内容
            category: 题材分类（如果未提供，自动识别）
            top_k: 召回知识点数量
        
        Returns:
            ConsistencyCheckResult: 一致性检测结果
        
        检测流程：
        1. 题材识别：自动识别题材（如果未提供）
        2. 知识召回：召回相关知识（top_k个）
        3. 冲突检测：检测内容是否与知识点冲突
        4. 评分计算：根据冲突数量和严重程度计算一致性评分
        """
        start_time = time.time()
        
        # 1. 题材识别
        if category is None:
            category, confidence = self._genre_recognizer.recognize_genre(content)
        else:
            confidence = 1.0
        
        # 2. 领域识别
        domain = self._genre_recognizer.recognize_domain(content, category)
        
        # 3. 知识召回
        recalled = self.recall_for_content(
            content=content,
            top_k=top_k
        )
        
        # 4. 冲突检测
        conflicts = self._detect_conflicts(content, recalled)
        
        # 5. 计算一致性评分
        consistency_score = self._calculate_consistency_score(conflicts, recalled)
        
        # 发布事件
        latency_ms = (time.time() - start_time) * 1000
        self._publish_event("knowledge.consistency.checked", {
            "content_length": len(content),
            "category": category,
            "is_consistent": len(conflicts) == 0,
            "conflict_count": len(conflicts),
            "consistency_score": consistency_score,
            "latency_ms": latency_ms
        })
        
        return ConsistencyCheckResult(
            is_consistent=len(conflicts) == 0,
            consistency_score=consistency_score,
            conflicts=conflicts,
            recalled_knowledge=recalled,
            category=category,
            domain=domain
        )
    
    def _detect_conflicts(
        self,
        content: str,
        recalled: List[RecallResult]
    ) -> List[KnowledgeConflict]:
        """
        检测知识冲突
        
        Args:
            content: 待检测内容
            recalled: 召回的知识点列表
        
        Returns:
            List[KnowledgeConflict]: 检测到的冲突列表
        
        检测逻辑（简化版，后续可接入LLM增强）：
        - 物理冲突：检测是否违反基本物理定律
        - 化学冲突：检测是否违反化学反应规则
        - 生物冲突：检测是否违反生物学原理
        - 历史冲突：检测是否与历史事实矛盾
        - 宗教冲突：检测是否与宗教体系矛盾
        """
        conflicts = []
        
        # 简化冲突检测规则（示例）
        # P0级别冲突：明显违反知识库
        
        # 物理冲突示例
        physics_keywords = {
            "超光速": "超光速违反相对论，质量会无限增大",
            "时间倒流": "时间倒流违反因果律，可能导致悖论"
        }
        
        for keyword, violation in physics_keywords.items():
            if keyword in content:
                # 查找相关知识点
                for r in recalled:
                    if r.domain == "physics" and keyword in r.content:
                        conflicts.append(KnowledgeConflict(
                            conflict_type="physics",
                            description=f"内容包含'{keyword}'，{violation}",
                            severity="P0",
                            knowledge_id=r.knowledge_id,
                            knowledge_title=r.title,
                            knowledge_content=r.content[:200],
                            suggested_fix=f"建议修改为符合物理定律的表达"
                        ))
                        break
        
        # P1级别冲突：可能存在问题
        
        # 历史冲突示例（简化）
        history_keywords = {
            "明朝使用火药": "明朝确实使用火药，但技术程度需核实"
        }
        
        for keyword, warning in history_keywords.items():
            if keyword in content:
                # 查找相关知识点
                for r in recalled:
                    if r.domain == "history" and ("明朝" in r.content or "火药" in r.content):
                        conflicts.append(KnowledgeConflict(
                            conflict_type="history",
                            description=f"内容包含'{keyword}'，{warning}",
                            severity="P1",
                            knowledge_id=r.knowledge_id,
                            knowledge_title=r.title,
                            knowledge_content=r.content[:200],
                            suggested_fix=f"建议查阅历史资料核实细节"
                        ))
                        break
        
        return conflicts
    
    def _calculate_consistency_score(
        self,
        conflicts: List[KnowledgeConflict],
        recalled: List[RecallResult]
    ) -> float:
        """
        计算一致性评分
        
        Args:
            conflicts: 检测到的冲突列表
            recalled: 召回的知识点列表
        
        Returns:
            float: 一致性评分（0-1）
        
        评分逻辑：
        - 基础分：1.0（完全一致）
        - P0冲突：每个扣0.3分
        - P1冲突：每个扣0.1分
        - P2冲突：每个扣0.05分
        - 最低分：0.0
        """
        score = 1.0
        
        for conflict in conflicts:
            if conflict.severity == "P0":
                score -= 0.3
            elif conflict.severity == "P1":
                score -= 0.1
            elif conflict.severity == "P2":
                score -= 0.05
        
        # 如果召回知识点不足，降低基础分
        if len(recalled) < 3:
            score *= 0.9  # 召回知识点不足，评分降低10%
        
        return max(score, 0.0)
    
    # ========================================================================
    # 统计接口
    # ========================================================================
    
    def _update_stats(self, latency_ms: float, success: bool, category: str):
        """更新统计信息"""
        with self._stats_lock:
            self._stats["total_recalls"] += 1
            self._stats["total_latency_ms"] += latency_ms
            self._stats["avg_recall_latency_ms"] = (
                self._stats["total_latency_ms"] / self._stats["total_recalls"]
            )
            
            if success:
                self._stats["successful_recalls"] += 1
            else:
                self._stats["failed_recalls"] += 1
            
            # 题材分布统计
            if category in self._stats["category_distribution"]:
                self._stats["category_distribution"][category] += 1
    
    def _publish_event(self, event_type: str, data: Dict[str, Any]):
        """发布事件"""
        event_bus = self._get_event_bus()
        if event_bus:
            try:
                event_bus.publish(
                    event_type=event_type,
                    data=data,
                    source="KnowledgeRecall"
                )
            except Exception:
                pass
    
    def get_stats(self) -> Dict[str, Any]:
        """获取召回统计信息"""
        with self._stats_lock:
            return self._stats.copy()
    
    def get_recall_accuracy(self) -> float:
        """
        获取召回准确率
        
        Returns:
            float: 召回准确率（0-1）
        
        计算方法：
        - 成功率 = 成功召回次数 / 总召回次数
        """
        with self._stats_lock:
            total = self._stats["total_recalls"]
            if total == 0:
                return 0.0
            
            successful = self._stats["successful_recalls"]
            return successful / total


# ============================================================================
# 单例访问
# ============================================================================


_recall_instance: Optional[KnowledgeRecall] = None
_recall_lock = threading.RLock()


def get_knowledge_recall(workspace_root: Optional[Path] = None) -> KnowledgeRecall:
    """获取知识库召回器单例"""
    global _recall_instance
    
    if _recall_instance is None:
        with _recall_lock:
            if _recall_instance is None:
                if workspace_root is None:
                    # 尝试从环境变量或当前目录推断
                    import os
                    workspace_root = Path(os.getcwd())
                
                _recall_instance = KnowledgeRecall(workspace_root=workspace_root)
    
    return _recall_instance


def reset_knowledge_recall():
    """重置知识库召回器（用于测试）"""
    global _recall_instance
    
    with _recall_lock:
        _recall_instance = None


# ============================================================================
# 测试代码
# ============================================================================


if __name__ == "__main__":
    import sys
    import io
    
    # 设置 stdout 编码为 UTF-8
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("=" * 60)
    print("Knowledge Recall Test")
    print("=" * 60)
    
    # 获取工作区根目录
    workspace_root = Path(__file__).parent.parent
    
    # 创建召回器实例
    recall = KnowledgeRecall(workspace_root)
    
    # 测试1: 智能召回
    print("\n[Test 1] Smart Recall...")
    content = "飞船接近光速飞行，时间流逝变慢，船员发现外面的世界已经过去了数百年"
    results = recall.recall_for_content(content=content, top_k=5)
    print(f"  Content: {content[:50]}...")
    print(f"  Found: {len(results)} results")
    for r in results[:3]:
        print(f"    - {r.title} (category: {r.category}, domain: {r.domain}, score: {r.score:.2f})")
    
    # 测试2: 一致性检测
    print("\n[Test 2] Consistency Check...")
    content_with_conflict = "超光速飞船瞬间到达目的地，时间倒流回出发前"
    check_result = recall.check_knowledge_consistency(content=content_with_conflict, category="scifi")
    print(f"  Content: {content_with_conflict[:50]}...")
    print(f"  Is consistent: {check_result.is_consistent}")
    print(f"  Consistency score: {check_result.consistency_score:.2f}")
    print(f"  Conflicts: {len(check_result.conflicts)}")
    for conflict in check_result.conflicts:
        print(f"    - [{conflict.severity}] {conflict.description}")
    
    # 测试3: 题材识别
    print("\n[Test 3] Genre Recognition...")
    recognizer = GenreRecognizer()
    
    test_cases = [
        "修仙者在仙界炼制丹药，突破元婴期",
        "星际舰队穿越虫洞，探索平行宇宙",
        "明朝末年，农民起义军攻入京城"
    ]
    
    for tc in test_cases:
        genre, confidence = recognizer.recognize_genre(tc)
        domain = recognizer.recognize_domain(tc, genre)
        print(f"  '{tc[:30]}...'")
        print(f"    -> Genre: {genre} (confidence: {confidence:.2f}), Domain: {domain}")
    
    # 测试4: 统计信息
    print("\n[Test 4] Statistics...")
    stats = recall.get_stats()
    print(f"  Total recalls: {stats['total_recalls']}")
    print(f"  Successful: {stats['successful_recalls']}")
    print(f"  Failed: {stats['failed_recalls']}")
    print(f"  Avg latency: {stats['avg_recall_latency_ms']:.2f}ms")
    print(f"  Recall accuracy: {recall.get_recall_accuracy():.2%}")
    print(f"  Category distribution: {stats['category_distribution']}")
    
    print("\n[OK] Test Completed")
