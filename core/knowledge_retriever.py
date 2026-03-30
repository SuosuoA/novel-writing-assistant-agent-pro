"""
知识库检索接口 - OpenClaw 向量召回

V1.0版本
创建日期：2026-03-25

特性：
- 向量检索召回top-10相关知识（OpenClaw memory_search）
- 支持题材过滤（科幻/玄幻/历史/通用）
- 支持领域过滤（物理/化学/生物/宗教/神话等）
- 混合检索：向量检索 + 关键词检索
- 召回准确率≥80%
- 检索延迟P99 <100ms
- EventBus集成

设计参考：
- OpenClaw memory_search工具
- 升级方案 10.升级方案✅️.md
- 知识库Schema 10.6 知识库Schema设计✅️.md
- ADR-003: 知识库双层设计

使用示例：
    # 创建检索器
    retriever = KnowledgeRetriever(workspace_root=Path("E:/project"))
    
    # 向量检索（召回top-10）
    results = retriever.recall_knowledge(
        query="飞船接近光速会发生什么",
        category="scifi",
        top_k=10
    )
    
    # 混合检索（向量+关键词）
    results = retriever.hybrid_search(
        query="时间膨胀效应",
        category="scifi",
        domain="physics",
        top_k=10
    )
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Pydantic数据模型
# ============================================================================


class RetrievalRequest(BaseModel):
    """检索请求"""
    
    model_config = ConfigDict(frozen=False)
    
    query: str = Field(description="查询文本")
    category: Optional[str] = Field(default=None, description="题材过滤（scifi/xuanhuan/history/general）")
    domain: Optional[str] = Field(default=None, description="领域过滤（physics/chemistry/religion等）")
    top_k: int = Field(default=10, description="返回数量")
    min_score: float = Field(default=0.5, description="最小相似度阈值")
    use_vector: bool = Field(default=True, description="是否使用向量检索")
    use_keyword: bool = Field(default=True, description="是否使用关键词检索")


class RetrievalResult(BaseModel):
    """检索结果"""
    
    model_config = ConfigDict(frozen=False)
    
    knowledge_id: str = Field(description="知识点ID")
    title: str = Field(description="知识点标题")
    content: str = Field(description="知识点内容")
    category: str = Field(description="分类")
    domain: str = Field(description="领域")
    keywords: List[str] = Field(default_factory=list, description="关键词")
    score: float = Field(description="综合相似度分数（0-1）")
    vector_score: float = Field(default=0.0, description="向量相似度分数")
    keyword_score: float = Field(default=0.0, description="关键词相似度分数")
    references: Optional[List[str]] = Field(default=None, description="参考来源")


class RetrievalStats(BaseModel):
    """检索统计"""
    
    model_config = ConfigDict(frozen=False)
    
    query: str = Field(description="查询文本")
    total_results: int = Field(description="结果总数")
    vector_results: int = Field(default=0, description="向量检索结果数")
    keyword_results: int = Field(default=0, description="关键词检索结果数")
    latency_ms: float = Field(description="检索耗时（毫秒）")
    category_filter: Optional[str] = Field(default=None, description="题材过滤")
    domain_filter: Optional[str] = Field(default=None, description="领域过滤")


# ============================================================================
# 知识库检索器
# ============================================================================


class KnowledgeRetriever:
    """
    知识库检索器 - OpenClaw向量召回
    
    功能：
    - 向量检索召回top-10相关知识
    - 支持题材过滤（科幻/玄幻/历史/通用）
    - 支持领域过滤（物理/化学/生物/宗教/神话等）
    - 混合检索（向量+关键词）
    - 召回准确率≥80%
    - 检索延迟P99 <100ms
    
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
    
    def __init__(
        self,
        workspace_root: Path,
        vector_store=None,
        knowledge_manager=None
    ):
        """
        初始化检索器
        
        Args:
            workspace_root: 工作区根目录
            vector_store: 向量存储实例（可选）
            knowledge_manager: 知识库管理器实例（可选）
        """
        # 避免重复初始化
        if hasattr(self, "_initialized") and self._initialized:
            return
        
        self.workspace_root = Path(workspace_root)
        
        # 向量存储（延迟导入）
        self._vector_store = vector_store
        self._vector_store_instance = None
        
        # 知识库管理器（延迟导入）
        self._knowledge_manager = knowledge_manager
        self._knowledge_manager_instance = None
        
        # EventBus（延迟导入）
        self._event_bus = None
        
        # 检索统计
        self._stats = {
            "total_queries": 0,
            "total_latency_ms": 0.0,
            "avg_latency_ms": 0.0,
            "vector_queries": 0,
            "keyword_queries": 0,
            "hybrid_queries": 0
        }
        self._stats_lock = threading.RLock()
        
        # 缓存（LRU策略）
        self._cache: Dict[str, List[RetrievalResult]] = {}
        self._cache_lock = threading.RLock()
        self._cache_max_size = 100
        
        self._initialized = True
    
    def _get_vector_store(self):
        """延迟获取向量存储"""
        if self._vector_store_instance is None:
            if self._vector_store is not None:
                self._vector_store_instance = self._vector_store
            else:
                try:
                    from infrastructure.vector_store import get_vector_store
                    self._vector_store_instance = get_vector_store()
                except Exception as e:
                    print(f"[KnowledgeRetriever] 初始化向量存储失败: {e}")
        return self._vector_store_instance
    
    def _get_knowledge_manager(self):
        """延迟获取知识库管理器"""
        if self._knowledge_manager_instance is None:
            if self._knowledge_manager is not None:
                self._knowledge_manager_instance = self._knowledge_manager
            else:
                try:
                    from core.knowledge_manager import get_knowledge_manager
                    self._knowledge_manager_instance = get_knowledge_manager(self.workspace_root)
                except Exception as e:
                    print(f"[KnowledgeRetriever] 初始化知识库管理器失败: {e}")
        return self._knowledge_manager_instance
    
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
    # 向量检索（OpenClaw memory_search）
    # ========================================================================
    
    def recall_knowledge(
        self,
        query: str,
        category: Optional[str] = None,
        domain: Optional[str] = None,
        top_k: int = 10,
        min_score: float = 0.5
    ) -> List[RetrievalResult]:
        """
        向量检索召回top-10相关知识（OpenClaw memory_search）
        
        Args:
            query: 查询文本
            category: 题材过滤（scifi/xuanhuan/history/general）
            domain: 领域过滤（physics/chemistry/religion等）
            top_k: 返回数量
            min_score: 最小相似度阈值
        
        Returns:
            List[RetrievalResult]: 检索结果列表
        
        性能指标：
        - 召回准确率: ≥80%
        - 检索延迟: P99 <100ms
        """
        start_time = time.time()
        
        # 检查缓存
        cache_key = self._build_cache_key(query, category, domain, top_k)
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            self._publish_event("knowledge.retrieval.cache_hit", {
                "query": query,
                "category": category,
                "domain": domain
            })
            return cached_result
        
        results = []
        
        # 1. 向量检索
        vector_store = self._get_vector_store()
        if vector_store:
            try:
                vector_results = vector_store.recall_knowledge(
                    query=query,
                    category=category,
                    domain=domain,
                    top_k=top_k * 2  # 多召回一些，后续过滤
                )
                
                for vr in vector_results:
                    if vr.score >= min_score:
                        results.append(RetrievalResult(
                            knowledge_id=vr.id,
                            title=vr.metadata.get("title", "未知标题"),
                            content=vr.content,
                            category=vr.metadata.get("category", "general"),
                            domain=vr.metadata.get("domain", "general"),
                            keywords=vr.metadata.get("keywords", []),
                            score=vr.score,
                            vector_score=vr.score,
                            keyword_score=0.0,
                            references=vr.metadata.get("references")
                        ))
            except Exception as e:
                print(f"[KnowledgeRetriever] 向量检索失败: {e}")
        
        # 2. 如果向量检索结果不足，降级为关键词检索
        if len(results) < top_k:
            keyword_results = self._keyword_search(
                query=query,
                category=category,
                domain=domain,
                top_k=top_k - len(results)
            )
            results.extend(keyword_results)
        
        # 去重
        results = self._deduplicate(results)
        
        # 按分数排序
        results.sort(key=lambda x: x.score, reverse=True)
        
        # 截断到top_k
        results = results[:top_k]
        
        # 缓存结果
        self._save_to_cache(cache_key, results)
        
        # 更新统计
        latency_ms = (time.time() - start_time) * 1000
        self._update_stats(latency_ms, "vector")
        
        # 发布事件
        self._publish_event("knowledge.retrieval.completed", {
            "query": query,
            "category": category,
            "domain": domain,
            "result_count": len(results),
            "latency_ms": latency_ms
        })
        
        return results
    
    def _keyword_search(
        self,
        query: str,
        category: Optional[str] = None,
        domain: Optional[str] = None,
        top_k: int = 10
    ) -> List[RetrievalResult]:
        """
        关键词检索（降级方案）
        
        Args:
            query: 查询文本
            category: 题材过滤
            domain: 领域过滤
            top_k: 返回数量
        
        Returns:
            List[RetrievalResult]: 检索结果
        """
        results = []
        
        knowledge_manager = self._get_knowledge_manager()
        if not knowledge_manager:
            return results
        
        try:
            # 调用知识库管理器的关键词检索
            search_results = knowledge_manager.search_knowledge(
                query=query,
                category=category,
                domain=domain,
                top_k=top_k
            )
            
            for sr in search_results:
                results.append(RetrievalResult(
                    knowledge_id=sr.knowledge_id,
                    title=sr.title,
                    content=sr.content,
                    category=sr.category,
                    domain=sr.domain,
                    keywords=sr.keywords,
                    score=sr.score,
                    vector_score=0.0,
                    keyword_score=sr.score,
                    references=None
                ))
        except Exception as e:
            print(f"[KnowledgeRetriever] 关键词检索失败: {e}")
        
        return results
    
    # ========================================================================
    # 混合检索（向量+关键词）
    # ========================================================================
    
    def hybrid_search(
        self,
        query: str,
        category: Optional[str] = None,
        domain: Optional[str] = None,
        top_k: int = 10,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3
    ) -> List[RetrievalResult]:
        """
        混合检索（向量+关键词）
        
        Args:
            query: 查询文本
            category: 题材过滤
            domain: 领域过滤
            top_k: 返回数量
            vector_weight: 向量检索权重
            keyword_weight: 关键词检索权重
        
        Returns:
            List[RetrievalResult]: 混合检索结果
        
        混合策略：
        - 向量检索召回语义相似知识点
        - 关键词检索召回精确匹配知识点
        - 加权融合分数：final_score = vector_score * 0.7 + keyword_score * 0.3
        """
        start_time = time.time()
        
        # 检查缓存
        cache_key = self._build_cache_key(f"hybrid:{query}", category, domain, top_k)
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        # 1. 向量检索
        vector_results = self.recall_knowledge(
            query=query,
            category=category,
            domain=domain,
            top_k=top_k * 2
        )
        
        # 2. 关键词检索
        keyword_results = self._keyword_search(
            query=query,
            category=category,
            domain=domain,
            top_k=top_k * 2
        )
        
        # 3. 合并结果
        merged = {}
        
        # 添加向量检索结果
        for r in vector_results:
            merged[r.knowledge_id] = RetrievalResult(
                knowledge_id=r.knowledge_id,
                title=r.title,
                content=r.content,
                category=r.category,
                domain=r.domain,
                keywords=r.keywords,
                score=r.vector_score * vector_weight,
                vector_score=r.vector_score,
                keyword_score=0.0,
                references=r.references
            )
        
        # 合并关键词检索结果
        for r in keyword_results:
            if r.knowledge_id in merged:
                # 已存在，更新分数
                existing = merged[r.knowledge_id]
                existing.keyword_score = r.keyword_score
                existing.score = existing.vector_score * vector_weight + r.keyword_score * keyword_weight
            else:
                # 不存在，添加
                merged[r.knowledge_id] = RetrievalResult(
                    knowledge_id=r.knowledge_id,
                    title=r.title,
                    content=r.content,
                    category=r.category,
                    domain=r.domain,
                    keywords=r.keywords,
                    score=r.keyword_score * keyword_weight,
                    vector_score=0.0,
                    keyword_score=r.keyword_score,
                    references=r.references
                )
        
        # 转换为列表并排序
        results = list(merged.values())
        results.sort(key=lambda x: x.score, reverse=True)
        
        # 截断到top_k
        results = results[:top_k]
        
        # 缓存结果
        self._save_to_cache(cache_key, results)
        
        # 更新统计
        latency_ms = (time.time() - start_time) * 1000
        self._update_stats(latency_ms, "hybrid")
        
        # 发布事件
        self._publish_event("knowledge.retrieval.hybrid_completed", {
            "query": query,
            "category": category,
            "domain": domain,
            "result_count": len(results),
            "latency_ms": latency_ms
        })
        
        return results
    
    # ========================================================================
    # 批量检索
    # ========================================================================
    
    def batch_recall(
        self,
        queries: List[str],
        category: Optional[str] = None,
        top_k: int = 10
    ) -> Dict[str, List[RetrievalResult]]:
        """
        批量检索
        
        Args:
            queries: 查询文本列表
            category: 题材过滤
            top_k: 每个查询的返回数量
        
        Returns:
            Dict[str, List[RetrievalResult]]: 查询 -> 结果列表
        """
        results = {}
        
        for query in queries:
            results[query] = self.recall_knowledge(
                query=query,
                category=category,
                top_k=top_k
            )
        
        return results
    
    # ========================================================================
    # 上下文召回（OpenClaw memory_search变体）
    # ========================================================================
    
    def recall_for_context(
        self,
        context: str,
        category: Optional[str] = None,
        top_k: int = 5
    ) -> str:
        """
        为上下文召回相关知识（用于提示词构建）
        
        Args:
            context: 上下文文本（如章节大纲、世界观设定等）
            category: 题材过滤
            top_k: 返回数量
        
        Returns:
            str: 召回知识的文本摘要（用于注入到提示词）
        """
        results = self.recall_knowledge(
            query=context,
            category=category,
            top_k=top_k
        )
        
        if not results:
            return ""
        
        # 构建摘要
        summary_parts = []
        for i, r in enumerate(results, 1):
            summary_parts.append(
                f"{i}. 【{r.title}】{r.content[:200]}..."
            )
        
        return "\n".join(summary_parts)
    
    # ========================================================================
    # 辅助方法
    # ========================================================================
    
    def _deduplicate(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
        """去重（按knowledge_id）"""
        seen = set()
        unique = []
        
        for r in results:
            if r.knowledge_id not in seen:
                seen.add(r.knowledge_id)
                unique.append(r)
        
        return unique
    
    def _build_cache_key(
        self,
        query: str,
        category: Optional[str],
        domain: Optional[str],
        top_k: int
    ) -> str:
        """构建缓存键"""
        return f"{query}|{category}|{domain}|{top_k}"
    
    def _get_from_cache(self, key: str) -> Optional[List[RetrievalResult]]:
        """从缓存获取"""
        with self._cache_lock:
            return self._cache.get(key)
    
    def _save_to_cache(self, key: str, results: List[RetrievalResult]):
        """保存到缓存（LRU策略）"""
        with self._cache_lock:
            # 检查容量
            if len(self._cache) >= self._cache_max_size:
                # 删除最旧的条目（简化LRU）
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            
            self._cache[key] = results
    
    def _update_stats(self, latency_ms: float, mode: str):
        """更新统计信息"""
        with self._stats_lock:
            self._stats["total_queries"] += 1
            self._stats["total_latency_ms"] += latency_ms
            self._stats["avg_latency_ms"] = (
                self._stats["total_latency_ms"] / self._stats["total_queries"]
            )
            
            if mode == "vector":
                self._stats["vector_queries"] += 1
            elif mode == "keyword":
                self._stats["keyword_queries"] += 1
            elif mode == "hybrid":
                self._stats["hybrid_queries"] += 1
    
    def _publish_event(self, event_type: str, data: Dict[str, Any]):
        """发布事件"""
        event_bus = self._get_event_bus()
        if event_bus:
            try:
                event_bus.publish(
                    event_type=event_type,
                    data=data,
                    source="KnowledgeRetriever"
                )
            except Exception:
                pass
    
    # ========================================================================
    # 统计接口
    # ========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取检索统计信息"""
        with self._stats_lock:
            return self._stats.copy()
    
    def clear_cache(self):
        """清空缓存"""
        with self._cache_lock:
            self._cache.clear()
    
    def get_retrieval_stats(
        self,
        query: str,
        category: Optional[str] = None,
        domain: Optional[str] = None
    ) -> RetrievalStats:
        """
        获取检索统计信息（带详细数据）
        
        Args:
            query: 查询文本
            category: 题材过滤
            domain: 领域过滤
        
        Returns:
            RetrievalStats: 检索统计对象
        """
        start_time = time.time()
        
        results = self.recall_knowledge(
            query=query,
            category=category,
            domain=domain,
            top_k=10
        )
        
        latency_ms = (time.time() - start_time) * 1000
        
        # 统计向量检索和关键词检索结果
        vector_count = sum(1 for r in results if r.vector_score > 0)
        keyword_count = sum(1 for r in results if r.keyword_score > 0)
        
        return RetrievalStats(
            query=query,
            total_results=len(results),
            vector_results=vector_count,
            keyword_results=keyword_count,
            latency_ms=latency_ms,
            category_filter=category,
            domain_filter=domain
        )


# ============================================================================
# 单例访问
# ============================================================================


_retriever_instance: Optional[KnowledgeRetriever] = None
_retriever_lock = threading.RLock()


def get_knowledge_retriever(
    workspace_root: Optional[Path] = None,
    vector_store=None,
    knowledge_manager=None
) -> KnowledgeRetriever:
    """获取知识库检索器单例"""
    global _retriever_instance
    
    if _retriever_instance is None:
        with _retriever_lock:
            if _retriever_instance is None:
                if workspace_root is None:
                    # 尝试从环境变量或当前目录推断
                    import os
                    workspace_root = Path(os.getcwd())
                
                _retriever_instance = KnowledgeRetriever(
                    workspace_root=workspace_root,
                    vector_store=vector_store,
                    knowledge_manager=knowledge_manager
                )
    
    return _retriever_instance


def reset_knowledge_retriever():
    """重置知识库检索器（用于测试）"""
    global _retriever_instance
    
    with _retriever_lock:
        _retriever_instance = None


# ============================================================================
# 测试代码
# ============================================================================


if __name__ == "__main__":
    import sys
    import io
    
    # 设置 stdout 编码为 UTF-8
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("=" * 60)
    print("Knowledge Retriever Test")
    print("=" * 60)
    
    # 获取工作区根目录
    workspace_root = Path(__file__).parent.parent
    
    # 创建检索器实例
    retriever = KnowledgeRetriever(workspace_root)
    
    # 测试1: 向量检索
    print("\n[Test 1] Vector Recall...")
    results = retriever.recall_knowledge(
        query="飞船接近光速会发生什么",
        category="scifi",
        top_k=5
    )
    print(f"  Found: {len(results)} results")
    for r in results[:3]:
        print(f"    - {r.title} (score: {r.score:.2f})")
    
    # 测试2: 混合检索
    print("\n[Test 2] Hybrid Search...")
    results = retriever.hybrid_search(
        query="时间膨胀效应",
        category="scifi",
        domain="physics",
        top_k=5
    )
    print(f"  Found: {len(results)} results")
    for r in results[:3]:
        print(f"    - {r.title} (score: {r.score:.2f}, vector: {r.vector_score:.2f}, keyword: {r.keyword_score:.2f})")
    
    # 测试3: 上下文召回
    print("\n[Test 3] Context Recall...")
    context = retriever.recall_for_context(
        context="星际战争爆发，人类舰队需要穿越虫洞前往外星系",
        category="scifi",
        top_k=3
    )
    print(f"  Context:\n{context[:200]}...")
    
    # 测试4: 统计信息
    print("\n[Test 4] Get Statistics...")
    stats = retriever.get_stats()
    print(f"  Total queries: {stats['total_queries']}")
    print(f"  Avg latency: {stats['avg_latency_ms']:.2f}ms")
    print(f"  Vector queries: {stats['vector_queries']}")
    print(f"  Hybrid queries: {stats['hybrid_queries']}")
    
    print("\n[OK] Test Completed")
