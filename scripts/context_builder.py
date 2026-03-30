#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能上下文构建器 V2.0 - 集成向量召回机制

基于V5.5的SmartContextBuilder升级，集成OpenClaw L2温记忆向量召回。

核心改进：
1. 向量召回相似章节（实现"照相记忆"）
2. 智能token预算分配
3. 多源上下文整合（章节/知识/风格）
4. 构建时间优化（目标<500ms）

===============================================================================
🔴 【评分反馈，循环优化生成流程】核心模块 - 强制保护区域
===============================================================================
⚠️ 本文件是【评分反馈，循环优化生成流程】的上下文构建模块
⚠️ 受 V5 最全经验文档 中的强制保护机制约束
⚠️ 核心原则必须保持不变：
   1. 必须包含完整的上下文信息（世界观、人物、大纲、风格）
   2. 必须附加【本章完】强制要求
   3. 必须保持上下文记忆（前5章）
   4. 必须优化Token使用效率
===============================================================================

迁移说明：
- 源文件：Novel Writing Assistant-V5/scripts/context_builder.py
- 目标：scripts/context_builder.py (V2.0升级)
- 升级日期：2026-03-25
- 升级内容：集成向量召回机制（Sprint 7-8）
"""

import logging
import time
import threading
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

# ============================================================================
# 延迟导入：向量召回模块
# ============================================================================

_context_recall_instance = None
_context_recall_lock = threading.RLock()


def _get_context_recall(workspace_root: Path = None):
    """
    延迟获取ContextRecaller实例
    
    Args:
        workspace_root: 工作区根目录
        
    Returns:
        ContextRecaller实例或None（如果不可用）
    """
    global _context_recall_instance
    
    if _context_recall_instance is None:
        with _context_recall_lock:
            if _context_recall_instance is None:
                try:
                    from core.context_recall import get_context_recaller
                    _context_recall_instance = get_context_recaller(workspace_root)
                    logging.getLogger(__name__).info("[V2.0] 向量召回器初始化成功")
                except ImportError as e:
                    logging.getLogger(__name__).warning(f"[V2.0] 向量召回模块未安装: {e}")
                except Exception as e:
                    logging.getLogger(__name__).warning(f"[V2.0] 向量召回器初始化失败: {e}")
    
    return _context_recall_instance


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class ContextBuildResult:
    """上下文构建结果"""
    prompt: str                              # 最终构建的提示词
    total_tokens: int                        # 总token数
    sections: List[str]                      # 各部分名称
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    
    # V2.0新增：向量召回相关
    vector_recall_used: bool = False         # 是否使用向量召回
    recalled_chapters: int = 0               # 召回章节数
    recalled_knowledge: int = 0              # 召回知识数
    recall_latency_ms: float = 0.0           # 召回延迟（毫秒）


@dataclass
class TokenBudget:
    """Token预算分配"""
    total_budget: int                        # 总预算
    worldview_budget: int                    # 世界观预算
    characters_budget: int                   # 人物预算
    outline_budget: int                      # 大纲预算
    style_budget: int                        # 风格预算
    context_budget: int                      # 上下文预算（向量召回）
    knowledge_budget: int                    # 知识预算（向量召回）


# ============================================================================
# SmartContextBuilder V2.0 主类
# ============================================================================


class SmartContextBuilder:
    """
    智能上下文构建器 V2.0 - 集成向量召回
    
    核心改进：
    1. 向量召回相似章节（实现"照相记忆"）
    2. 智能token预算分配
    3. 多源上下文整合
    4. 构建时间优化（目标<500ms）
    """
    
    # Token预算默认配置
    DEFAULT_TOTAL_BUDGET = 8000
    DEFAULT_WORLDVIEW_BUDGET = 2000
    DEFAULT_CHARACTERS_BUDGET = 2000
    DEFAULT_OUTLINE_BUDGET = 1000
    DEFAULT_STYLE_BUDGET = 1500
    DEFAULT_CONTEXT_BUDGET = 2000   # 向量召回预算
    DEFAULT_KNOWLEDGE_BUDGET = 500  # 知识召回预算
    
    def __init__(
        self,
        workspace_root: Path = None,
        logger: logging.Logger = None,
        config: Dict[str, Any] = None
    ):
        """
        初始化智能上下文构建器
        
        Args:
            workspace_root: 工作区根目录
            logger: 日志记录器
            config: 配置字典
        """
        self.workspace_root = workspace_root or Path.cwd()
        self.logger = logger or logging.getLogger(__name__)
        self.config = config or {}
        
        # 上下文记忆（避免重复发送）
        self.context_memory: Dict[str, str] = {}
        
        # 实体缓存
        self.entity_cache: Dict[str, Any] = {}
        
        # V2.0新增：向量召回器
        self._context_recall = None
        
        # Token预算配置
        self._token_budget = self._init_token_budget()
        
        # 统计信息
        self._build_count = 0
        self._total_build_time = 0.0
        
    def _init_token_budget(self) -> TokenBudget:
        """初始化Token预算"""
        return TokenBudget(
            total_budget=self.config.get("total_token_budget", self.DEFAULT_TOTAL_BUDGET),
            worldview_budget=self.config.get("worldview_budget", self.DEFAULT_WORLDVIEW_BUDGET),
            characters_budget=self.config.get("characters_budget", self.DEFAULT_CHARACTERS_BUDGET),
            outline_budget=self.config.get("outline_budget", self.DEFAULT_OUTLINE_BUDGET),
            style_budget=self.config.get("style_budget", self.DEFAULT_STYLE_BUDGET),
            context_budget=self.config.get("context_budget", self.DEFAULT_CONTEXT_BUDGET),
            knowledge_budget=self.config.get("knowledge_budget", self.DEFAULT_KNOWLEDGE_BUDGET)
        )
    
    @property
    def context_recall(self):
        """延迟加载ContextRecaller"""
        if self._context_recall is None:
            self._context_recall = _get_context_recall(self.workspace_root)
        return self._context_recall
    
    # ------------------------------------------------------------------------
    # 核心构建方法
    # ------------------------------------------------------------------------
    
    def build(
        self,
        worldview: str,
        characters: List[Dict],
        outline: str,
        style_profile: Dict[str, Any],
        chapter_title: str = "",
        previous_chapters: List[str] = None,
        target_word_count: int = 3500,
        genre: str = None,
        **options
    ) -> ContextBuildResult:
        """
        构建完整的上下文提示词（V2.0 - 集成向量召回）
        
        Args:
            worldview: 世界观设定
            characters: 人物设定列表
            outline: 章节大纲
            style_profile: 风格配置
            chapter_title: 章节标题
            previous_chapters: 前文章节（可选，向量召回时可自动获取）
            target_word_count: 目标字数
            genre: 题材（用于知识库召回）
            **options: 其他选项
            
        Returns:
            ContextBuildResult: 构建结果
        """
        start_time = time.time()
        
        self.logger.info(f"[V2.0] 开始构建上下文: {chapter_title}")
        
        prompt_parts = []
        sections = []
        total_tokens = 0
        recalled_chapters = 0
        recalled_knowledge = 0
        recall_latency = 0.0
        vector_recall_used = False
        
        # 1. 核心创作原则（最高优先级）
        core_text = self._build_core_principles()
        prompt_parts.append(core_text)
        sections.append("核心创作原则")
        total_tokens += len(core_text) // 2
        
        # 2. 世界观设定
        worldview_text = self._build_worldview(worldview)
        prompt_parts.append(worldview_text)
        sections.append("世界观设定")
        total_tokens += len(worldview_text) // 2
        
        # 3. 人物设定
        characters_text = self._build_characters(characters)
        prompt_parts.append(characters_text)
        sections.append("人物设定")
        total_tokens += len(characters_text) // 2
        
        # 4. 章节大纲
        outline_text = self._build_outline(outline, chapter_title)
        prompt_parts.append(outline_text)
        sections.append("章节大纲")
        total_tokens += len(outline_text) // 2
        
        # 5. 写作风格
        style_text = self._build_style(style_profile)
        prompt_parts.append(style_text)
        sections.append("写作风格")
        total_tokens += len(style_text) // 2
        
        # 6. 上下文记忆（V2.0新增：向量召回）
        context_result = self._build_context_with_vector_recall(
            chapter_outline=outline,
            previous_chapters=previous_chapters,
            genre=genre,
            max_tokens=self._token_budget.context_budget
        )
        
        if context_result["text"]:
            prompt_parts.append(context_result["text"])
            sections.append("上下文记忆")
            total_tokens += context_result["tokens"]
            recalled_chapters = context_result.get("recalled_chapters", 0)
            recalled_knowledge = context_result.get("recalled_knowledge", 0)
            recall_latency = context_result.get("latency_ms", 0.0)
            vector_recall_used = context_result.get("vector_recall_used", False)
        
        # 7. 输出要求（必须包含【本章完】）
        output_text = self._build_output_requirements(target_word_count)
        prompt_parts.append(output_text)
        sections.append("输出要求")
        total_tokens += len(output_text) // 2
        
        # 合并最终提示词
        final_prompt = "\n\n".join(prompt_parts)
        
        # 计算总时间
        build_time = (time.time() - start_time) * 1000
        self._build_count += 1
        self._total_build_time += build_time
        
        self.logger.info(
            f"[V2.0] 上下文构建完成: {len(final_prompt)}字符, "
            f"{total_tokens}tokens, {build_time:.2f}ms"
        )
        
        if vector_recall_used:
            self.logger.info(
                f"[V2.0] 向量召回: {recalled_chapters}章节, "
                f"{recalled_knowledge}知识, {recall_latency:.2f}ms"
            )
        
        return ContextBuildResult(
            prompt=final_prompt,
            total_tokens=total_tokens,
            sections=sections,
            metadata={
                "build_time_ms": build_time,
                "target_word_count": target_word_count,
                "chapter_title": chapter_title,
                "genre": genre
            },
            vector_recall_used=vector_recall_used,
            recalled_chapters=recalled_chapters,
            recalled_knowledge=recalled_knowledge,
            recall_latency_ms=recall_latency
        )
    
    # ------------------------------------------------------------------------
    # 各部分构建方法
    # ------------------------------------------------------------------------
    
    def _build_core_principles(self) -> str:
        """构建核心创作原则"""
        parts = []
        
        parts.append("=" * 60)
        parts.append("🔴 核心创作原则(最高优先级,违反将导致创作失败)")
        parts.append("=" * 60)
        parts.append("在开始创作前,你必须:")
        parts.append("  1. **严格**按照提供的人物设定塑造角色")
        parts.append("  2. **严格**遵守世界观的所有设定")
        parts.append("  3. **严格**遵循写作风格指导")
        parts.append("  4. **完整**执行章节大纲的所有要点")
        parts.append("")
        parts.append("【重要警告】")
        parts.append("⚠️ 擅自修改设定将导致评分不及格,需要重新生成")
        parts.append("⚠️ 偏离人物设定将导致评分不及格")
        parts.append("⚠️ 违背世界观将导致评分不及格")
        parts.append("")
        
        return "\n".join(parts)
    
    def _build_worldview(self, worldview: str) -> str:
        """构建世界观设定"""
        parts = []
        
        parts.append("=" * 60)
        parts.append("🌍 世界观设定(必须严格遵守)")
        parts.append("=" * 60)
        
        if worldview:
            # 限制token预算
            max_chars = self._token_budget.worldview_budget * 2
            if len(worldview) > max_chars:
                worldview = worldview[:max_chars] + "\n...(内容已截断)"
            parts.append(worldview)
        else:
            parts.append("（未提供世界观设定）")
        
        parts.append("")
        
        return "\n".join(parts)
    
    def _build_characters(self, characters: List[Dict]) -> str:
        """构建人物设定"""
        parts = []
        
        parts.append("=" * 60)
        parts.append("👥 人物设定(必须严格遵守)")
        parts.append("=" * 60)
        
        if not characters:
            parts.append("（未提供人物设定）")
            parts.append("")
            return "\n".join(parts)
        
        # 计算每个人物的token预算
        char_budget = self._token_budget.characters_budget // max(len(characters), 1)
        
        for idx, char in enumerate(characters, 1):
            name = char.get("name", char.get("basic_info", {}).get("name", f"人物{idx}"))
            
            parts.append(f"### 人物{idx}: {name}")
            
            # 基本信息
            basic_info = char.get("basic_info", {})
            if basic_info:
                if "age" in basic_info:
                    parts.append(f"年龄: {basic_info['age']}")
                if "gender" in basic_info:
                    parts.append(f"性别: {basic_info['gender']}")
                if "identity" in basic_info:
                    parts.append(f"身份: {basic_info['identity']}")
            
            # 性格
            personality = char.get("personality", basic_info.get("personality", ""))
            if personality:
                # 清理markdown标记
                import re
                clean_personality = re.sub(r'\*\*[^*]+\*\*[:：]', '', personality)
                clean_personality = re.sub(r'\*\*', '', clean_personality)
                parts.append(f"性格: {clean_personality[:200]}")
            
            # 外貌
            appearance = char.get("appearance", basic_info.get("appearance", ""))
            if appearance:
                parts.append(f"外貌: {appearance[:150]}")
            
            # 背景
            background = char.get("background", basic_info.get("background", ""))
            if background:
                parts.append(f"背景: {background[:200]}")
            
            parts.append("")
        
        return "\n".join(parts)
    
    def _build_outline(self, outline: str, chapter_title: str) -> str:
        """构建章节大纲"""
        parts = []
        
        parts.append("=" * 60)
        parts.append("📋 章节大纲(必须完整执行)")
        parts.append("=" * 60)
        
        if chapter_title:
            parts.append(f"章节标题: {chapter_title}")
            parts.append("")
        
        if outline:
            # 限制token预算
            max_chars = self._token_budget.outline_budget * 2
            if len(outline) > max_chars:
                outline = outline[:max_chars] + "\n...(内容已截断)"
            parts.append(outline)
        else:
            parts.append("（未提供章节大纲）")
        
        parts.append("")
        
        return "\n".join(parts)
    
    def _build_style(self, style_profile: Dict[str, Any]) -> str:
        """构建写作风格"""
        parts = []
        
        parts.append("=" * 60)
        parts.append("✍️ 写作风格(必须严格遵循)")
        parts.append("=" * 60)
        
        if not style_profile:
            parts.append("（未提供风格配置，使用自然叙事风格）")
            parts.append("")
            return "\n".join(parts)
        
        # 风格名称
        style_name = style_profile.get("style_name", style_profile.get("name", "未命名风格"))
        parts.append(f"风格类型: {style_name}")
        parts.append("")
        
        # 写作指南
        writing_guidelines = style_profile.get("writing_guidelines", [])
        if writing_guidelines:
            parts.append("写作指南:")
            for idx, guideline in enumerate(writing_guidelines[:5], 1):
                parts.append(f"  {idx}. {guideline}")
            parts.append("")
        
        # 避免模式
        avoid_patterns = style_profile.get("avoid_patterns", [])
        if avoid_patterns:
            parts.append("应避免:")
            for idx, pattern in enumerate(avoid_patterns[:5], 1):
                parts.append(f"  {idx}. {pattern}")
            parts.append("")
        
        # 词汇特征
        vocab_profile = style_profile.get("vocabulary_profile", {})
        if vocab_profile:
            common_words = vocab_profile.get("most_common_words", [])
            if common_words:
                words = []
                for item in common_words[:10]:
                    if isinstance(item, list) and item:
                        words.append(item[0])
                    elif isinstance(item, str):
                        words.append(item)
                if words:
                    parts.append(f"常用词汇: {', '.join(words)}")
                    parts.append("")
        
        return "\n".join(parts)
    
    def _build_context_with_vector_recall(
        self,
        chapter_outline: str,
        previous_chapters: Optional[List[str]],
        genre: Optional[str],
        max_tokens: int
    ) -> Dict[str, Any]:
        """
        构建上下文记忆（V2.0新增：向量召回）
        
        实现OpenClaw的"照相记忆"能力：
        1. 向量检索召回top-10相似章节
        2. 召回准确率≥85%
        3. 构建上下文摘要
        
        Args:
            chapter_outline: 章节大纲
            previous_chapters: 前文章节（可选）
            genre: 题材
            max_tokens: 最大token预算
            
        Returns:
            Dict: {"text": 文本, "tokens": token数, ...}
        """
        start_time = time.time()
        
        result = {
            "text": "",
            "tokens": 0,
            "recalled_chapters": 0,
            "recalled_knowledge": 0,
            "latency_ms": 0.0,
            "vector_recall_used": False
        }
        
        try:
            # 尝试使用向量召回
            if self.context_recall:
                self.logger.info("[V2.0] 使用向量召回构建上下文...")
                
                # 调用ContextRecaller进行智能召回
                context_summary = self.context_recall.recall_for_new_chapter(
                    chapter_outline=chapter_outline,
                    top_k=10,
                    max_tokens=max_tokens,
                    include_knowledge=True,
                    include_style=False,  # 风格已单独处理
                    genre=genre
                )
                
                # 使用召回的上下文摘要
                if context_summary.summary_text:
                    result["text"] = context_summary.summary_text
                    result["tokens"] = context_summary.total_tokens
                    result["recalled_chapters"] = context_summary.chapter_count
                    result["recalled_knowledge"] = context_summary.knowledge_count
                    result["vector_recall_used"] = True
                    
                    self.logger.info(
                        f"[V2.0] 向量召回成功: {context_summary.chapter_count}章节, "
                        f"{context_summary.knowledge_count}知识"
                    )
                    
            # 如果向量召回失败或不可用，使用传统方法
            if not result["text"] and previous_chapters:
                self.logger.info("[V2.0] 使用传统方法构建上下文...")
                
                result["text"] = self._build_traditional_context(
                    previous_chapters, max_tokens
                )
                result["tokens"] = len(result["text"]) // 2
                
        except Exception as e:
            self.logger.error(f"[V2.0] 上下文构建失败: {e}")
            
            # 降级到传统方法
            if previous_chapters:
                result["text"] = self._build_traditional_context(
                    previous_chapters, max_tokens
                )
                result["tokens"] = len(result["text"]) // 2
        
        result["latency_ms"] = (time.time() - start_time) * 1000
        
        return result
    
    def _build_traditional_context(
        self,
        previous_chapters: List[str],
        max_tokens: int
    ) -> str:
        """
        构建传统上下文（前文章节直接拼接）
        
        Args:
            previous_chapters: 前文章节列表
            max_tokens: 最大token预算
            
        Returns:
            上下文文本
        """
        parts = []
        
        parts.append("=" * 60)
        parts.append("📖 前文章节摘要")
        parts.append("=" * 60)
        
        # 只保留最近5章
        recent_chapters = previous_chapters[-5:] if len(previous_chapters) > 5 else previous_chapters
        
        for idx, chapter in enumerate(recent_chapters, 1):
            # 每章最多400字符
            preview = chapter[:400]
            if len(chapter) > 400:
                preview += "..."
            
            parts.append(f"【第{idx}章】")
            parts.append(preview)
            parts.append("")
        
        return "\n".join(parts)
    
    def _build_output_requirements(self, target_word_count: int) -> str:
        """构建输出要求（必须包含【本章完】）"""
        parts = []
        
        parts.append("=" * 60)
        parts.append("📝 输出要求(必须严格遵守)")
        parts.append("=" * 60)
        parts.append(f"目标字数: {target_word_count}字（允许±10%偏差）")
        parts.append("")
        parts.append("【强制要求】")
        parts.append("⚠️ 章节结束必须添加【本章完】标记")
        parts.append("⚠️ 没有此标记将被视为未完成，需要重新生成")
        parts.append("")
        parts.append("【创作检查清单】")
        parts.append("在提交作品前，请确认:")
        parts.append("  □ 人物行为符合设定")
        parts.append("  □ 世界观设定准确")
        parts.append("  □ 风格保持一致")
        parts.append("  □ 大纲完整执行")
        parts.append("  □ 字数符合要求")
        parts.append("  □ 结尾有【本章完】标记")
        parts.append("")
        parts.append("=" * 60)
        
        return "\n".join(parts)
    
    # ------------------------------------------------------------------------
    # 兼容性方法
    # ------------------------------------------------------------------------
    
    def build_optimized_prompt(
        self,
        chapter_title: str,
        chapter_outline: str,
        world_view: str,
        style: str,
        characters: List[Dict],
        previous_chapters: Optional[List[str]] = None,
        max_worldview_tokens: int = 2000,
        max_style_tokens: int = 1500,
        target_word_count: int = 3500
    ) -> str:
        """
        构建优化的提示词（兼容V5接口）
        
        Args:
            chapter_title: 章节标题
            chapter_outline: 章节大纲
            world_view: 世界观设定
            style: 风格描述
            characters: 人物设定
            previous_chapters: 前文章节
            max_worldview_tokens: 世界观token预算
            max_style_tokens: 风格token预算
            target_word_count: 目标字数
            
        Returns:
            构建的提示词
        """
        # 转换风格格式
        style_profile = {
            "style_name": style if isinstance(style, str) else style.get("name", "默认风格"),
            "writing_guidelines": [],
            "avoid_patterns": []
        }
        if isinstance(style, dict):
            style_profile.update(style)
        
        # 调用新的build方法
        result = self.build(
            worldview=world_view,
            characters=characters,
            outline=chapter_outline,
            style_profile=style_profile,
            chapter_title=chapter_title,
            previous_chapters=previous_chapters,
            target_word_count=target_word_count
        )
        
        return result.prompt
    
    # ------------------------------------------------------------------------
    # 统计和调试方法
    # ------------------------------------------------------------------------
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        avg_build_time = (
            self._total_build_time / self._build_count
            if self._build_count > 0 else 0.0
        )
        
        return {
            "build_count": self._build_count,
            "total_build_time_ms": self._total_build_time,
            "avg_build_time_ms": avg_build_time,
            "token_budget": {
                "total": self._token_budget.total_budget,
                "worldview": self._token_budget.worldview_budget,
                "characters": self._token_budget.characters_budget,
                "outline": self._token_budget.outline_budget,
                "style": self._token_budget.style_budget,
                "context": self._token_budget.context_budget
            }
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self._build_count = 0
        self._total_build_time = 0.0


# ============================================================================
# 全局单例
# ============================================================================

_builder_instance: Optional[SmartContextBuilder] = None
_builder_lock = threading.RLock()


def get_context_builder(
    workspace_root: Path = None,
    config: Dict[str, Any] = None
) -> SmartContextBuilder:
    """
    获取全局SmartContextBuilder单例
    
    Args:
        workspace_root: 工作区根目录
        config: 配置字典
        
    Returns:
        SmartContextBuilder实例
    """
    global _builder_instance
    
    if _builder_instance is None:
        with _builder_lock:
            if _builder_instance is None:
                _builder_instance = SmartContextBuilder(
                    workspace_root=workspace_root,
                    config=config
                )
    
    return _builder_instance


def reset_context_builder():
    """重置全局单例（测试用）"""
    global _builder_instance
    
    with _builder_lock:
        _builder_instance = None


# ============================================================================
# 模块导出
# ============================================================================

__all__ = [
    "SmartContextBuilder",
    "ContextBuildResult",
    "TokenBudget",
    "get_context_builder",
    "reset_context_builder"
]
