"""
上下文智能召回 - OpenClaw memory_search

V1.0版本
创建日期：2026-03-25

特性：
- 向量检索召回top-10相似章节（OpenClaw memory_search）
- 召回准确率≥85%
- 构建上下文摘要（避免超出token限制）
- 支持多种召回策略（章节/知识/风格）
- 智能token预算分配
- EventBus集成
- 线程安全设计

设计参考：
- OpenClaw memory_search工具
- 升级方案 10.升级方案✅️.md
- ADR-001: LanceDB作为向量数据库
- ADR-002: OpenClaw 5层记忆架构

使用示例：
    # 创建召回器实例
    recaller = ContextRecaller(workspace_root=Path("E:/project"))
    
    # 为新章节召回上下文
    context = recaller.recall_for_new_chapter(
        chapter_outline="第三章 星际战争爆发",
        top_k=10,
        max_tokens=3000
    )
    
    # 构建上下文摘要
    summary = recaller.build_context_summary(
        chapters=[...],
        max_tokens=2000
    )
    
    # 智能token预算分配
    budget = recaller.allocate_token_budget(
        total_budget=4000,
        chapter_count=10,
        knowledge_count=5
    )
"""

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Tuple
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Pydantic数据模型
# ============================================================================


class RecalledChapter(BaseModel):
    """召回的章节"""
    
    model_config = ConfigDict(frozen=False)
    
    chapter_id: str = Field(description="章节ID")
    title: Optional[str] = Field(default=None, description="章节标题")
    content: str = Field(description="章节内容（部分或全部）")
    score: float = Field(description="相似度分数（0-1）")
    word_count: int = Field(default=0, description="字数")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    position: int = Field(default=0, description="章节位置（第几章）")


class RecalledKnowledge(BaseModel):
    """召回的知识点"""
    
    model_config = ConfigDict(frozen=False)
    
    knowledge_id: str = Field(description="知识点ID")
    title: str = Field(description="知识点标题")
    content: str = Field(description="知识点内容")
    category: str = Field(description="分类")
    domain: str = Field(description="领域")
    score: float = Field(description="相似度分数（0-1）")
    keywords: List[str] = Field(default_factory=list, description="关键词")


class RecalledStyle(BaseModel):
    """召回的风格"""
    
    model_config = ConfigDict(frozen=False)
    
    style_id: str = Field(description="风格ID")
    style_name: str = Field(description="风格名称")
    style_category: str = Field(description="风格分类")
    sample_text: str = Field(description="样本文本")
    score: float = Field(description="相似度分数（0-1）")
    writing_guidelines: List[str] = Field(default_factory=list, description="写作指南")
    avoid_patterns: List[str] = Field(default_factory=list, description="避免模式")


class ContextSummary(BaseModel):
    """上下文摘要"""
    
    model_config = ConfigDict(frozen=False)
    
    total_tokens: int = Field(description="总token数")
    chapter_tokens: int = Field(default=0, description="章节token数")
    knowledge_tokens: int = Field(default=0, description="知识token数")
    style_tokens: int = Field(default=0, description="风格token数")
    chapter_count: int = Field(default=0, description="章节数量")
    knowledge_count: int = Field(default=0, description="知识数量")
    has_style: bool = Field(default=False, description="是否包含风格")
    summary_text: str = Field(default="", description="摘要文本")
    chapters: List[RecalledChapter] = Field(default_factory=list, description="召回的章节")
    knowledge: List[RecalledKnowledge] = Field(default_factory=list, description="召回的知识")
    style: Optional[RecalledStyle] = Field(default=None, description="召回的风格")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="时间戳")


class TokenBudget(BaseModel):
    """Token预算分配"""
    
    model_config = ConfigDict(frozen=False)
    
    total_budget: int = Field(description="总token预算")
    chapter_budget: int = Field(description="章节token预算")
    knowledge_budget: int = Field(description="知识token预算")
    style_budget: int = Field(description="风格token预算")
    chapter_count: int = Field(default=0, description="预期章节数")
    knowledge_count: int = Field(default=0, description="预期知识数")
    has_style: bool = Field(default=True, description="是否包含风格")


class RecallStats(BaseModel):
    """召回统计"""
    
    model_config = ConfigDict(frozen=False)
    
    total_recalls: int = Field(default=0, description="总召回次数")
    successful_recalls: int = Field(default=0, description="成功召回次数")
    failed_recalls: int = Field(default=0, description="失败召回次数")
    total_chapters_recalled: int = Field(default=0, description="召回章节总数")
    total_knowledge_recalled: int = Field(default=0, description="召回知识总数")
    total_style_recalled: int = Field(default=0, description="召回风格总数")
    total_tokens_used: int = Field(default=0, description="使用token总数")
    avg_latency_ms: float = Field(default=0.0, description="平均延迟（毫秒）")


# ============================================================================
# ContextRecaller 主类
# ============================================================================


class ContextRecaller:
    """
    上下文智能召回器 - OpenClaw memory_search
    
    核心功能：
    1. 向量检索召回top-10相似章节
    2. 召回准确率≥85%
    3. 构建上下文摘要（避免超出token限制）
    4. 智能token预算分配
    5. 多种召回策略（章节/知识/风格）
    """
    
    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        vector_store=None,
        chapter_encoder=None,
        knowledge_retriever=None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化上下文召回器
        
        Args:
            workspace_root: 工作区根目录
            vector_store: VectorStore实例（可选，延迟加载）
            chapter_encoder: ChapterEncoder实例（可选，延迟加载）
            knowledge_retriever: KnowledgeRetriever实例（可选，延迟加载）
            config: 配置字典
        """
        self.workspace_root = workspace_root or Path.cwd()
        self.config = config or {}
        
        # 延迟加载依赖（避免循环导入）
        self._vector_store = vector_store
        self._chapter_encoder = chapter_encoder
        self._knowledge_retriever = knowledge_retriever
        
        # 统计信息
        self._stats = RecallStats()
        self._stats_lock = threading.RLock()
        
        # Logger
        self._logger = logging.getLogger(__name__)
        
        # Token预算配置
        self._default_token_budget = self.config.get("default_token_budget", 4000)
        self._max_chapter_tokens = self.config.get("max_chapter_tokens", 500)
        self._max_knowledge_tokens = self.config.get("max_knowledge_tokens", 300)
        self._max_style_tokens = self.config.get("max_style_tokens", 200)
        
        # 召回准确率阈值
        self._min_score_threshold = self.config.get("min_score_threshold", 0.6)
        
    # ------------------------------------------------------------------------
    # 延迟加载属性
    # ------------------------------------------------------------------------
    
    @property
    def vector_store(self):
        """延迟加载VectorStore"""
        if self._vector_store is None:
            try:
                import os
                from infrastructure.vector_store import get_vector_store
                
                # 设置本地模型缓存目录到项目内部
                project_root = self.workspace_root
                cache_dir = project_root / "sentence_transformers_cache"
                cache_dir.mkdir(parents=True, exist_ok=True)
                os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(cache_dir)
                
                # 设置HuggingFace国内镜像加速
                os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
                self._logger.info(f"[ContextRecall] 本地模型缓存目录: {str(cache_dir)}")
                self._logger.info(f"[ContextRecall] 使用HuggingFace镜像: https://hf-mirror.com")
                
                # 从配置读取embedding类型
                embedding_type = "local"  # 默认使用本地模型（免费、无网络依赖）
                
                try:
                    from .config_service import get_config_service
                    config_service = get_config_service(self.workspace_root)
                    config = config_service.get_all()
                    
                    # 检查openclaw配置
                    openclaw_config = config.get("openclaw", {})
                    vector_config = openclaw_config.get("vector_store", {})
                    
                    # 读取embedding模型配置
                    embedding_model = vector_config.get("embedding_model", "all-MiniLM-L6-v2")
                    self._logger.info(f"[ContextRecall] 使用本地embedding模型: {embedding_model}")
                    
                except Exception as config_err:
                    self._logger.warning(f"[ContextRecall] 读取配置失败，使用默认本地模型: {config_err}")
                
                # 使用本地模型初始化向量存储
                # 注意：首次使用会下载模型文件（all-MiniLM-L6-v2 约90MB）到F:\
                self._vector_store = get_vector_store(
                    embedding_type="local"
                )
                
            except Exception as e:
                self._logger.error(f"加载VectorStore失败: {e}")
        return self._vector_store
    
    @property
    def chapter_encoder(self):
        """延迟加载ChapterEncoder"""
        if self._chapter_encoder is None:
            try:
                from .chapter_encoder import get_chapter_encoder
                self._chapter_encoder = get_chapter_encoder(self.workspace_root)
            except Exception as e:
                self._logger.error(f"加载ChapterEncoder失败: {e}")
        return self._chapter_encoder
    
    @property
    def knowledge_retriever(self):
        """延迟加载KnowledgeRetriever"""
        if self._knowledge_retriever is None:
            try:
                from .knowledge_retriever import get_knowledge_retriever
                self._knowledge_retriever = get_knowledge_retriever(self.workspace_root)
            except Exception as e:
                self._logger.error(f"加载KnowledgeRetriever失败: {e}")
        return self._knowledge_retriever
    
    # ------------------------------------------------------------------------
    # 配置读取方法
    # ------------------------------------------------------------------------
    
    def _get_vector_recall_topk(self) -> int:
        """
        从config.yaml读取向量召回数量配置
        
        V1.1版本新增（2026-03-28）：
        - 支持memory.vector_recall_topk配置
        - 默认值：10
        
        Returns:
            向量召回数量
        """
        try:
            import yaml
            from pathlib import Path
            
            # 读取config.yaml
            config_path = self.workspace_root / "config.yaml"
            if not config_path.exists():
                self._logger.info("[ContextRecall] config.yaml不存在，使用默认top_k=10")
                return 10
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 读取记忆配置
            memory_config = config.get("memory", {})
            top_k = memory_config.get("vector_recall_topk", 10)
            
            self._logger.info(f"[ContextRecall] 从config读取vector_recall_topk={top_k}")
            return top_k
            
        except Exception as e:
            self._logger.warning(f"[ContextRecall] 读取配置失败，使用默认top_k=10: {e}")
            return 10
    
    # ------------------------------------------------------------------------
    # 核心召回方法
    # ------------------------------------------------------------------------
    
    def recall_for_new_chapter(
        self,
        chapter_outline: str,
        top_k: Optional[int] = None,  # V1.1: 改为Optional，从config读取
        max_tokens: int = 4000,
        include_knowledge: bool = True,
        include_style: bool = False,
        genre: Optional[str] = None
    ) -> ContextSummary:
        """
        为新章节召回上下文（OpenClaw memory_search核心功能）
        
        V1.1版本更新（2026-03-28）：
        - top_k参数改为Optional，从config.yaml读取默认值
        - 支持memory.vector_recall_topk配置
        
        Args:
            chapter_outline: 章节大纲/摘要
            top_k: 召回章节数量（None时从config.yaml读取）
            max_tokens: 最大token预算
            include_knowledge: 是否包含知识库召回
            include_style: 是否包含风格召回
            genre: 题材（可选，用于知识库召回）
        
        Returns:
            ContextSummary: 上下文摘要
        """
        start_time = time.time()
        
        # V1.1: 从config.yaml读取top_k配置
        if top_k is None:
            top_k = self._get_vector_recall_topk()
        
        try:
            self._logger.info(f"开始为新章节召回上下文: {chapter_outline[:50]}...")
            self._logger.info(f"[ContextRecall] top_k={top_k}（从config读取）")
            
            # 1. 分配token预算
            budget = self.allocate_token_budget(
                total_budget=max_tokens,
                chapter_count=top_k,
                knowledge_count=5 if include_knowledge else 0,
                include_style=include_style
            )
            
            # 2. 召回相似章节
            chapters = self._recall_similar_chapters(
                query=chapter_outline,
                top_k=top_k,
                max_tokens=budget.chapter_budget
            )
            
            # 3. 召回相关知识（可选）
            knowledge = []
            if include_knowledge and budget.knowledge_budget > 0:
                knowledge = self._recall_knowledge(
                    query=chapter_outline,
                    top_k=5,
                    max_tokens=budget.knowledge_budget,
                    genre=genre
                )
            
            # 4. 召回风格（可选）
            style = None
            if include_style and budget.style_budget > 0:
                style = self._recall_style(
                    query=chapter_outline,
                    max_tokens=budget.style_budget
                )
            
            # 5. 构建上下文摘要
            summary = self.build_context_summary(
                chapters=chapters,
                knowledge=knowledge,
                style=style,
                max_tokens=max_tokens
            )
            
            # 6. 更新统计
            latency_ms = (time.time() - start_time) * 1000
            self._update_stats(
                success=True,
                chapter_count=len(chapters),
                knowledge_count=len(knowledge),
                style_count=1 if style else 0,
                tokens_used=summary.total_tokens,
                latency_ms=latency_ms
            )
            
            # 7. 发布EventBus事件
            self._publish_recall_event(summary, latency_ms)
            
            self._logger.info(
                f"上下文召回完成: {len(chapters)}章节, {len(knowledge)}知识, "
                f"{summary.total_tokens}tokens, {latency_ms:.2f}ms"
            )
            
            return summary
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self._update_stats(success=False, latency_ms=latency_ms)
            self._logger.error(f"上下文召回失败: {e}")
            
            # 返回空摘要
            return ContextSummary(
                total_tokens=0,
                summary_text=f"召回失败: {str(e)}",
                timestamp=datetime.now().isoformat()
            )
    
    def _recall_similar_chapters(
        self,
        query: str,
        top_k: int,
        max_tokens: int
    ) -> List[RecalledChapter]:
        """
        召回相似章节
        
        Args:
            query: 查询文本
            top_k: 返回数量
            max_tokens: 最大token预算
        
        Returns:
            List[RecalledChapter]: 召回的章节列表
        """
        chapters = []
        
        try:
            # 使用ChapterEncoder召回
            if self.chapter_encoder:
                results = self.chapter_encoder.recall_similar_chapters(
                    query=query,
                    top_k=top_k
                )
                
                # 转换为RecalledChapter
                for idx, result in enumerate(results):
                    # 估算token数（中文约1.5字/token）
                    content = result.get("content", "")
                    estimated_tokens = int(len(content) / 1.5)
                    
                    # 如果超出预算，截断内容
                    if estimated_tokens > max_tokens // top_k:
                        max_chars = int((max_tokens // top_k) * 1.5)
                        content = content[:max_chars] + "..."
                    
                    chapter = RecalledChapter(
                        chapter_id=result.get("chapter_id", f"chapter-{idx}"),
                        title=result.get("metadata", {}).get("title"),
                        content=content,
                        score=result.get("score", 0.0),
                        word_count=result.get("metadata", {}).get("word_count", 0),
                        metadata=result.get("metadata", {}),
                        position=result.get("metadata", {}).get("position", idx + 1)
                    )
                    chapters.append(chapter)
        
        except Exception as e:
            self._logger.error(f"召回相似章节失败: {e}")
        
        # 过滤低分章节
        chapters = [c for c in chapters if c.score >= self._min_score_threshold]
        
        return chapters
    
    def _recall_knowledge(
        self,
        query: str,
        top_k: int,
        max_tokens: int,
        genre: Optional[str] = None
    ) -> List[RecalledKnowledge]:
        """
        召回相关知识
        
        Args:
            query: 查询文本
            top_k: 返回数量
            max_tokens: 最大token预算
            genre: 题材
        
        Returns:
            List[RecalledKnowledge]: 召回的知识列表
        """
        knowledge = []
        
        try:
            # 使用KnowledgeRetriever召回
            if self.knowledge_retriever:
                results = self.knowledge_retriever.recall_knowledge(
                    query=query,
                    category=genre,
                    top_k=top_k
                )
                
                # 转换为RecalledKnowledge
                for result in results:
                    # 估算token数
                    content = result.get("content", "")
                    estimated_tokens = int(len(content) / 1.5)
                    
                    # 如果超出预算，截断内容
                    if estimated_tokens > max_tokens // top_k:
                        max_chars = int((max_tokens // top_k) * 1.5)
                        content = content[:max_chars] + "..."
                    
                    knowledge_item = RecalledKnowledge(
                        knowledge_id=result.get("knowledge_id", ""),
                        title=result.get("title", ""),
                        content=content,
                        category=result.get("category", ""),
                        domain=result.get("domain", ""),
                        score=result.get("score", 0.0),
                        keywords=result.get("keywords", [])
                    )
                    knowledge.append(knowledge_item)
        
        except Exception as e:
            self._logger.error(f"召回知识失败: {e}")
        
        # 过滤低分知识
        knowledge = [k for k in knowledge if k.score >= self._min_score_threshold]
        
        return knowledge
    
    def _recall_style(
        self,
        query: str,
        max_tokens: int
    ) -> Optional[RecalledStyle]:
        """
        召回风格
        
        Args:
            query: 查询文本
            max_tokens: 最大token预算
        
        Returns:
            Optional[RecalledStyle]: 召回的风格（最相似的一个）
        """
        try:
            # 使用VectorStore召回
            if self.vector_store:
                results = self.vector_store.recall_similar_styles(
                    query=query,
                    top_k=1
                )
                
                if results:
                    result = results[0]
                    
                    # 估算token数
                    sample_text = result.get("content", "")
                    estimated_tokens = int(len(sample_text) / 1.5)
                    
                    # 如果超出预算，截断内容
                    if estimated_tokens > max_tokens:
                        max_chars = int(max_tokens * 1.5)
                        sample_text = sample_text[:max_chars] + "..."
                    
                    return RecalledStyle(
                        style_id=result.get("style_id", ""),
                        style_name=result.get("metadata", {}).get("style_name", ""),
                        style_category=result.get("metadata", {}).get("style_category", ""),
                        sample_text=sample_text,
                        score=result.get("score", 0.0),
                        writing_guidelines=result.get("metadata", {}).get("writing_guidelines", []),
                        avoid_patterns=result.get("metadata", {}).get("avoid_patterns", [])
                    )
        
        except Exception as e:
            self._logger.error(f"召回风格失败: {e}")
        
        return None
    
    # ------------------------------------------------------------------------
    # 上下文摘要构建
    # ------------------------------------------------------------------------
    
    def build_context_summary(
        self,
        chapters: Optional[List[RecalledChapter]] = None,
        knowledge: Optional[List[RecalledKnowledge]] = None,
        style: Optional[RecalledStyle] = None,
        max_tokens: int = 4000
    ) -> ContextSummary:
        """
        构建上下文摘要（避免超出token限制）
        
        Args:
            chapters: 召回的章节列表
            knowledge: 召回的知识列表
            style: 召回的风格
            max_tokens: 最大token预算
        
        Returns:
            ContextSummary: 上下文摘要
        """
        chapters = chapters or []
        knowledge = knowledge or []
        
        summary_parts = []
        total_tokens = 0
        chapter_tokens = 0
        knowledge_tokens = 0
        style_tokens = 0
        
        # 1. 添加章节摘要
        if chapters:
            chapter_summary = self._build_chapter_summary(chapters, max_tokens // 2)
            summary_parts.append(chapter_summary["text"])
            chapter_tokens = chapter_summary["tokens"]
            total_tokens += chapter_tokens
        
        # 2. 添加知识摘要
        if knowledge:
            knowledge_summary = self._build_knowledge_summary(knowledge, max_tokens // 4)
            summary_parts.append(knowledge_summary["text"])
            knowledge_tokens = knowledge_summary["tokens"]
            total_tokens += knowledge_tokens
        
        # 3. 添加风格摘要
        if style:
            style_summary = self._build_style_summary(style, max_tokens // 4)
            summary_parts.append(style_summary["text"])
            style_tokens = style_summary["tokens"]
            total_tokens += style_tokens
        
        # 4. 合并摘要文本
        summary_text = "\n\n".join(summary_parts)
        
        # 5. 如果超出预算，智能截断
        if total_tokens > max_tokens:
            summary_text, total_tokens = self._truncate_summary(
                summary_text, max_tokens
            )
        
        return ContextSummary(
            total_tokens=total_tokens,
            chapter_tokens=chapter_tokens,
            knowledge_tokens=knowledge_tokens,
            style_tokens=style_tokens,
            chapter_count=len(chapters),
            knowledge_count=len(knowledge),
            has_style=style is not None,
            summary_text=summary_text,
            chapters=chapters,
            knowledge=knowledge,
            style=style,
            timestamp=datetime.now().isoformat()
        )
    
    def _build_chapter_summary(
        self,
        chapters: List[RecalledChapter],
        max_tokens: int
    ) -> Dict[str, Any]:
        """
        构建章节摘要
        
        Args:
            chapters: 章节列表
            max_tokens: 最大token预算
        
        Returns:
            Dict: {"text": 摘要文本, "tokens": token数}
        """
        parts = []
        total_tokens = 0
        
        parts.append("## 📖 前文相关章节\n")
        
        for chapter in chapters:
            # 构建单个章节摘要
            chapter_text = f"### 第{chapter.position}章"
            if chapter.title:
                chapter_text += f"：{chapter.title}"
            chapter_text += f"（相似度: {chapter.score:.2f}）\n"
            
            # 添加内容摘要（最多200字）
            content_preview = chapter.content[:200]
            if len(chapter.content) > 200:
                content_preview += "..."
            chapter_text += f"{content_preview}\n"
            
            # 估算token
            estimated_tokens = int(len(chapter_text) / 1.5)
            
            # 检查是否超出预算
            if total_tokens + estimated_tokens > max_tokens:
                break
            
            parts.append(chapter_text)
            total_tokens += estimated_tokens
        
        text = "\n".join(parts)
        return {"text": text, "tokens": total_tokens}
    
    def _build_knowledge_summary(
        self,
        knowledge: List[RecalledKnowledge],
        max_tokens: int
    ) -> Dict[str, Any]:
        """
        构建知识摘要
        
        Args:
            knowledge: 知识列表
            max_tokens: 最大token预算
        
        Returns:
            Dict: {"text": 摘要文本, "tokens": token数}
        """
        parts = []
        total_tokens = 0
        
        parts.append("## 📚 相关知识参考\n")
        
        for idx, item in enumerate(knowledge, 1):
            # 构建单个知识摘要
            knowledge_text = f"### {idx}. {item.title}（{item.category}/{item.domain}）\n"
            knowledge_text += f"相似度: {item.score:.2f}\n"
            knowledge_text += f"内容: {item.content[:150]}...\n"
            if item.keywords:
                knowledge_text += f"关键词: {', '.join(item.keywords[:5])}\n"
            
            # 估算token
            estimated_tokens = int(len(knowledge_text) / 1.5)
            
            # 检查是否超出预算
            if total_tokens + estimated_tokens > max_tokens:
                break
            
            parts.append(knowledge_text)
            total_tokens += estimated_tokens
        
        text = "\n".join(parts)
        return {"text": text, "tokens": total_tokens}
    
    def _build_style_summary(
        self,
        style: RecalledStyle,
        max_tokens: int
    ) -> Dict[str, Any]:
        """
        构建风格摘要
        
        Args:
            style: 风格对象
            max_tokens: 最大token预算
        
        Returns:
            Dict: {"text": 摘要文本, "tokens": token数}
        """
        parts = []
        
        parts.append(f"## ✍️ 写作风格参考：{style.style_name}\n")
        parts.append(f"风格分类: {style.style_category}\n")
        parts.append(f"相似度: {style.score:.2f}\n")
        
        # 样本文本（最多100字）
        if style.sample_text:
            sample = style.sample_text[:100]
            if len(style.sample_text) > 100:
                sample += "..."
            parts.append(f"\n样本片段:\n{sample}\n")
        
        # 写作指南（最多3条）
        if style.writing_guidelines:
            parts.append("\n写作建议:")
            for idx, guideline in enumerate(style.writing_guidelines[:3], 1):
                parts.append(f"  {idx}. {guideline}")
        
        # 避免模式（最多3条）
        if style.avoid_patterns:
            parts.append("\n应避免:")
            for idx, pattern in enumerate(style.avoid_patterns[:3], 1):
                parts.append(f"  {idx}. {pattern}")
        
        text = "\n".join(parts)
        tokens = int(len(text) / 1.5)
        
        return {"text": text, "tokens": tokens}
    
    def _truncate_summary(
        self,
        summary_text: str,
        max_tokens: int
    ) -> Tuple[str, int]:
        """
        智能截断摘要
        
        Args:
            summary_text: 摘要文本
            max_tokens: 最大token预算
        
        Returns:
            Tuple[str, int]: (截断后的文本, token数)
        """
        # 中文约1.5字/token
        max_chars = int(max_tokens * 1.5)
        
        if len(summary_text) <= max_chars:
            return summary_text, int(len(summary_text) / 1.5)
        
        # 按段落截断
        paragraphs = summary_text.split("\n\n")
        truncated_parts = []
        current_chars = 0
        
        for para in paragraphs:
            if current_chars + len(para) + 2 <= max_chars:
                truncated_parts.append(para)
                current_chars += len(para) + 2
            else:
                break
        
        truncated_text = "\n\n".join(truncated_parts)
        truncated_text += "\n\n[摘要已截断，超出token预算]"
        
        return truncated_text, int(len(truncated_text) / 1.5)
    
    # ------------------------------------------------------------------------
    # Token预算分配
    # ------------------------------------------------------------------------
    
    def allocate_token_budget(
        self,
        total_budget: int,
        chapter_count: int = 10,
        knowledge_count: int = 5,
        include_style: bool = True
    ) -> TokenBudget:
        """
        智能token预算分配
        
        Args:
            total_budget: 总token预算
            chapter_count: 预期章节数量
            knowledge_count: 预期知识数量
            include_style: 是否包含风格
        
        Returns:
            TokenBudget: token预算分配
        """
        # 分配比例：章节50% / 知识30% / 风格20%
        chapter_ratio = 0.5
        knowledge_ratio = 0.3
        style_ratio = 0.2
        
        # 如果不包含风格，重新分配
        if not include_style:
            chapter_ratio = 0.6
            knowledge_ratio = 0.4
            style_ratio = 0.0
        
        chapter_budget = int(total_budget * chapter_ratio)
        knowledge_budget = int(total_budget * knowledge_ratio)
        style_budget = int(total_budget * style_ratio)
        
        # 限制单个章节/知识的最大token
        if chapter_count > 0:
            max_chapter_budget = self._max_chapter_tokens * chapter_count
            chapter_budget = min(chapter_budget, max_chapter_budget)
        
        if knowledge_count > 0:
            max_knowledge_budget = self._max_knowledge_tokens * knowledge_count
            knowledge_budget = min(knowledge_budget, max_knowledge_budget)
        
        style_budget = min(style_budget, self._max_style_tokens)
        
        return TokenBudget(
            total_budget=total_budget,
            chapter_budget=chapter_budget,
            knowledge_budget=knowledge_budget,
            style_budget=style_budget,
            chapter_count=chapter_count,
            knowledge_count=knowledge_count,
            has_style=include_style
        )
    
    # ------------------------------------------------------------------------
    # 统计和事件
    # ------------------------------------------------------------------------
    
    def _update_stats(
        self,
        success: bool,
        chapter_count: int = 0,
        knowledge_count: int = 0,
        style_count: int = 0,
        tokens_used: int = 0,
        latency_ms: float = 0.0
    ):
        """更新统计信息"""
        with self._stats_lock:
            self._stats.total_recalls += 1
            if success:
                self._stats.successful_recalls += 1
                self._stats.total_chapters_recalled += chapter_count
                self._stats.total_knowledge_recalled += knowledge_count
                self._stats.total_style_recalled += style_count
                self._stats.total_tokens_used += tokens_used
            else:
                self._stats.failed_recalls += 1
            
            # 更新平均延迟
            total_latency = (
                self._stats.avg_latency_ms * (self._stats.total_recalls - 1) +
                latency_ms
            )
            self._stats.avg_latency_ms = total_latency / self._stats.total_recalls
    
    def _publish_recall_event(self, summary: ContextSummary, latency_ms: float):
        """发布召回事件"""
        try:
            # 延迟导入EventBus避免循环依赖
            from .event_bus import EventBus
            from . import get_event_bus
            
            event_bus = get_event_bus()
            if event_bus:
                event_bus.publish(
                    event_type="context.recall.completed",
                    data={
                        "total_tokens": summary.total_tokens,
                        "chapter_count": summary.chapter_count,
                        "knowledge_count": summary.knowledge_count,
                        "has_style": summary.has_style,
                        "latency_ms": latency_ms
                    },
                    source="ContextRecaller"
                )
        except Exception as e:
            self._logger.debug(f"发布EventBus事件失败: {e}")
    
    def get_stats(self) -> RecallStats:
        """获取统计信息"""
        with self._stats_lock:
            return self._stats.model_copy()
    
    def reset_stats(self):
        """重置统计信息"""
        with self._stats_lock:
            self._stats = RecallStats()


# ============================================================================
# 全局单例
# ============================================================================


_context_recaller_instance: Optional[ContextRecaller] = None
_context_recaller_lock = threading.RLock()


def get_context_recaller(
    workspace_root: Optional[Path] = None,
    config: Optional[Dict[str, Any]] = None
) -> ContextRecaller:
    """
    获取全局ContextRecaller单例
    
    Args:
        workspace_root: 工作区根目录
        config: 配置字典
    
    Returns:
        ContextRecaller: 全局单例
    """
    global _context_recaller_instance
    
    if _context_recaller_instance is None:
        with _context_recaller_lock:
            # 双重检查锁
            if _context_recaller_instance is None:
                _context_recaller_instance = ContextRecaller(
                    workspace_root=workspace_root,
                    config=config
                )
    
    return _context_recaller_instance


def reset_context_recaller():
    """重置全局单例（测试用）"""
    global _context_recaller_instance
    
    with _context_recaller_lock:
        _context_recaller_instance = None
