#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说生成器插件 V3 - 整合上下文构建、迭代生成、加权验证的完整流程

核心流程（点下【开始生成】后的运行逻辑）：
1. 整理打包请求内容（百分百附加要求：结束加上【本章完】）
2. 向大模型发送请求（本地调用模型/线上调用API）
3. 接受返回文章
4. 从多维度评分（世界观、大纲、风格、人设、Ai感、字数、上下文契合度，没有【本章完】视作未完成）
5. 分数小于0.8 -> 发送评分（总评分+各维度评分）+ 修改建议（围绕各维度） -> 再次接受返还
6. 再次评分 -> ... -> 评分大于0.8且标记【本章完】
7. 输出保存

===============================================================================
🔴 【评分反馈，循环优化生成流程】核心模块 - 强制保护区域
===============================================================================
⚠️ 本文件是【评分反馈，循环优化生成流程】的核心协调模块
⚠️ 受 V5 最全经验文档 中的强制保护机制约束
⚠️ 未经用户明确授权，禁止以下操作：
   - ❌ 修改 generate_chapter() 的执行流程
   - ❌ 修改验证函数 validation_fn 的调用逻辑
   - ❌ 修改上下文记忆更新逻辑
⚠️ 核心流程必须保持不变：
   1. SmartContextBuilder 构建提示词
   2. IterativeGeneratorV2 执行迭代生成
   3. EnhancedWeightedValidator 进行多维度评分
   4. 评分<0.8或缺少【本章完】→ 循环优化
   5. 评分≥0.8且有【本章完】→ 输出保存
   6. 保持前5章上下文记忆
===============================================================================

迁移说明：
- 源文件：Novel Writing Assistant-V5/scripts/optimized_generator_v2.py
- 目标：plugins/novel-generator-v3 (GeneratorPlugin)
- 迁移日期：2026-03-23
- 迁移人：数据工程师
"""

import logging
import sys
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import re
import os

# 导入核心接口
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.plugin_interface import GeneratorPlugin, PluginMetadata, PluginType, PluginContext
from core.models import GenerationRequest, GenerationResult, ValidationScores

# 导入其他插件
try:
    from plugins.context_builder_v1.plugin import ContextBuilderPlugin
    from plugins.iterative_generator_v2.plugin import IterativeGeneratorPlugin, GenerationStrategy, DimensionScore
except ImportError:
    ContextBuilderPlugin = None
    IterativeGeneratorPlugin = None
    GenerationStrategy = None
    DimensionScore = None


class NovelGeneratorPlugin(GeneratorPlugin):
    """
    小说生成器插件 V3 - GeneratorPlugin实现
    
    整合上下文构建、迭代生成、加权验证的完整流程。
    
    核心功能：
    1. 构建优化的提示词（调用 context-builder-v1）
    2. 执行迭代生成（调用 iterative-generator-v2）
    3. 多维度评分验证
    4. 上下文记忆管理（保持前5章）
    """
    
    def __init__(self):
        """初始化小说生成器插件"""
        metadata = PluginMetadata(
            id="novel-generator-v3",
            name="小说生成器 V3",
            version="3.0.0",
            description="小说章节生成器V3，整合上下文构建、迭代生成、加权验证的完整流程",
            author="项目组",
            plugin_type=PluginType.GENERATOR
        )
        super().__init__(metadata)
        
        # 配置参数
        self.model_name: str = "deepseek-chat"
        self.quality_threshold: float = 0.8
        self.max_iterations: int = 5
        self.target_word_count: int = 3500
        
        # 子插件引用
        self._context_builder: Optional[ContextBuilderPlugin] = None
        self._iterative_generator: Optional[IterativeGeneratorPlugin] = None
        
        # 上下文记忆（保持前5章）
        self.previous_chapters: List[Dict[str, Any]] = []
        
        # 日志器
        self._logger: Optional[logging.Logger] = None
    
    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据"""
        return PluginMetadata(
            id="novel-generator-v3",
            name="小说生成器 V3",
            version="3.0.0",
            description="小说章节生成器V3，整合上下文构建、迭代生成、加权验证的完整流程",
            author="项目组",
            plugin_type=PluginType.GENERATOR
        )
    
    def initialize(self, context: PluginContext) -> bool:
        """
        初始化插件
        
        Args:
            context: 插件上下文
            
        Returns:
            是否初始化成功
        """
        try:
            self._context = context
            self._logger = context.logger or logging.getLogger(__name__)
            
            # 从服务定位器获取依赖插件
            if hasattr(context, 'service_locator') and context.service_locator:
                try:
                    # 获取上下文构建器
                    self._context_builder = context.service_locator.get("context-builder-v1")
                    self._logger.info("[NovelGenerator] 从服务定位器获取上下文构建器成功")
                except Exception as e:
                    self._logger.error(f"[NovelGenerator] 无法从服务定位器获取上下文构建器: {e}")
                
                try:
                    # 获取迭代生成器
                    self._iterative_generator = context.service_locator.get("iterative-generator-v2")
                    self._logger.info("[NovelGenerator] 从服务定位器获取迭代生成器成功")
                except Exception as e:
                    self._logger.error(f"[NovelGenerator] 无法从服务定位器获取迭代生成器: {e}")
            
            # 如果没有获取到依赖，创建本地实例
            if not self._context_builder and ContextBuilderPlugin:
                self._context_builder = ContextBuilderPlugin()
                self._context_builder.initialize(context)
                self._logger.info("[NovelGenerator] 创建本地ContextBuilderPlugin实例")
            elif not self._context_builder:
                self._logger.warning("[NovelGenerator] ContextBuilderPlugin不可用，将使用简化版提示词")
            
            if not self._iterative_generator and IterativeGeneratorPlugin:
                self._iterative_generator = IterativeGeneratorPlugin()
                self._iterative_generator.initialize(context)
                self._logger.info("[NovelGenerator] 创建本地IterativeGeneratorPlugin实例")
            elif not self._iterative_generator:
                self._logger.error("[NovelGenerator] IterativeGeneratorPlugin不可用，生成功能将受限")
            
            # 检查核心依赖是否可用
            if not self._iterative_generator:
                self._logger.error("[NovelGenerator] 核心依赖不可用，插件可能无法正常工作")
                return False
            
            self._logger.info(f"[NovelGenerator] 小说生成器初始化完成")
            self._logger.info(f"[NovelGenerator] 目标字数: {self.target_word_count}, 质量阈值: {self.quality_threshold}, 最大迭代: {self.max_iterations}")
            
            return True
            
        except Exception as e:
            if self._logger:
                self._logger.error(f"[NovelGenerator] 初始化失败: {e}")
            return False
    
    def set_api_client(self, api_client: Any):
        """
        设置API客户端
        
        Args:
            api_client: API客户端实例
        """
        # 传递给迭代生成器
        if self._iterative_generator:
            self._iterative_generator.set_api_client(api_client)
        if self._logger:
            self._logger.info("[NovelGenerator] API客户端已设置")
    
    def set_config(
        self,
        model_name: str = "deepseek-chat",
        quality_threshold: float = 0.8,
        max_iterations: int = 5,
        target_word_count: int = 3500
    ):
        """
        设置配置参数
        
        Args:
            model_name: 模型名称
            quality_threshold: 质量阈值
            max_iterations: 最大迭代次数
            target_word_count: 目标字数
        """
        self.model_name = model_name
        self.quality_threshold = quality_threshold
        self.max_iterations = max_iterations
        self.target_word_count = target_word_count
        
        # 传递给迭代生成器
        if self._iterative_generator:
            self._iterative_generator.set_config(
                model_name=model_name,
                target_word_count=target_word_count,
                quality_threshold=quality_threshold,
                max_iterations=max_iterations
            )
        
        if self._logger:
            self._logger.info(f"[NovelGenerator] 配置已更新 - 模型: {model_name}, 阈值: {quality_threshold}, 迭代: {max_iterations}, 字数: {target_word_count}")
    
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """
        生成内容 - 执行完整的章节生成流程
        
        Args:
            request: 生成请求
            
        Returns:
            生成结果
        """
        try:
            # 从request中提取参数
            extra = request.model_dump() if hasattr(request, 'model_dump') else {}
            
            chapter_title = request.title
            chapter_outline = request.outline
            world_view = extra.get('world_view', '')
            style = extra.get('style', '')
            characters = extra.get('characters', [])
            target_word_count = request.word_count or self.target_word_count
            strategy_str = extra.get('strategy', 'balanced')
            strategy = GenerationStrategy(strategy_str) if GenerationStrategy and isinstance(strategy_str, str) else None
            use_context_memory = extra.get('use_context_memory', True)
            style_profile = extra.get('style_profile')
            
            # 执行章节生成
            final_content, stats = self.generate_chapter(
                chapter_title=chapter_title,
                chapter_outline=chapter_outline,
                world_view=world_view,
                style=style,
                characters=characters,
                target_word_count=target_word_count,
                strategy=strategy,
                use_context_memory=use_context_memory,
                style_profile=style_profile
            )
            
            return GenerationResult(
                request_id=request.request_id,
                content=final_content,
                word_count=len(final_content),
                iteration_count=stats.get('total_iterations', 0),
                validation_scores=None
            )
            
        except Exception as e:
            if self._logger:
                self._logger.error(f"[NovelGenerator] 生成失败: {e}")
            return GenerationResult(
                request_id=request.request_id if hasattr(request, 'request_id') else '',
                content='',
                word_count=0,
                iteration_count=0,
                validation_scores=None,
                error=str(e)
            )
    
    def validate_request(self, request: GenerationRequest) -> Tuple[bool, List[str]]:
        """
        验证请求是否有效
        
        Args:
            request: 生成请求
            
        Returns:
            (是否有效, 错误消息列表)
        """
        errors = []
        
        if not request.title:
            errors.append("章节标题不能为空")
        if not request.outline:
            errors.append("章节大纲不能为空")
        if not self._iterative_generator:
            errors.append("迭代生成器未初始化")
            
        return len(errors) == 0, errors
    
    def get_generation_options(self) -> Dict[str, Any]:
        """
        获取生成选项定义
        
        Returns:
            选项定义字典
        """
        return {
            "strategy": {
                "type": "enum",
                "values": ["creative", "balanced", "precise"],
                "default": "balanced",
                "description": "生成策略"
            },
            "use_context_memory": {
                "type": "boolean",
                "default": True,
                "description": "是否使用上下文记忆"
            },
            "quality_threshold": {
                "type": "float",
                "default": 0.8,
                "min": 0.5,
                "max": 1.0,
                "description": "质量阈值"
            },
            "max_iterations": {
                "type": "integer",
                "default": 5,
                "min": 1,
                "max": 10,
                "description": "最大迭代次数"
            }
        }
    
    # ========== 核心功能方法（从V5迁移）==========
    
    def generate_chapter(
        self,
        chapter_title: str,
        chapter_outline: str,
        world_view: str,
        style: str,
        characters: List[Dict],
        target_word_count: int = 3500,
        strategy: Optional[Any] = None,
        use_context_memory: bool = True,
        style_profile: Optional[Dict] = None
    ) -> Tuple[str, Dict]:
        """
        生成章节内容 - 完整流程

        按照用户要求的流程：
        1. 整理打包请求内容（百分百附加要求：结束加上【本章完】）
        2. 向大模型发送请求
        3. 接受返回文章
        4. 从多维度评分
        5. 分数小于0.8 → 发送评分+修改建议 → 再次生成
        6. 评分大于0.8且标记【本章完】 → 输出保存

        Args:
            chapter_title: 章节标题
            chapter_outline: 章节大纲
            world_view: 世界观设定
            style: 写作风格
            characters: 人物列表
            target_word_count: 目标字数
            strategy: 生成策略
            use_context_memory: 是否使用上下文记忆
            style_profile: 风格档案

        Returns:
            (生成的内容, 统计信息)
        """
        if self._logger:
            self._logger.info(f"[V3] 开始生成章节: {chapter_title}, 目标字数: {target_word_count}")

        # === 步骤1: 整理打包请求内容（强制要求【本章完】）===
        if self._logger:
            self._logger.info("[V3] 步骤1: 构建提示词")

        # 更新目标字数
        self.target_word_count = target_word_count
        if self._iterative_generator:
            self._iterative_generator.target_word_count = target_word_count

        # 1. 构建优化的提示词（使用ContextBuilderPlugin）
        if self._context_builder:
            context = [ch.get('content', '') for ch in self.previous_chapters] if use_context_memory else None
            base_prompt = self._context_builder.build_optimized_prompt(
                chapter_title=chapter_title,
                chapter_outline=chapter_outline,
                world_view=world_view,
                style=style,
                characters=characters,
                previous_chapters=context,
                max_worldview_tokens=2000,
                max_style_tokens=1500,
                target_word_count=target_word_count
            )
        else:
            # 简化版提示词
            base_prompt = self._build_simple_prompt(
                chapter_title, chapter_outline, world_view, style, characters
            )

        # 强制附加【本章完】要求（百分百保证）
        base_prompt = self._ensure_chapter_end_marker(base_prompt)

        if self._logger:
            self._logger.info(f"[V3] 基础提示词长度: {len(base_prompt)} 字符")

        # === 步骤2-6: 调用迭代生成器（内部完成剩余步骤）===
        if self._logger:
            self._logger.info("[V3] 步骤2-6: 调用迭代生成器进行循环优化")

        # 定义验证函数
        def validation_fn(content: str):
            """验证内容质量"""
            return self._validate_content(
                content=content,
                target_word_count=target_word_count,
                chapter_outline=chapter_outline,
                style_profile=style_profile,
                characters=characters,
                world_view=world_view
            )

        # 调用迭代生成器
        if self._iterative_generator:
            final_content, stats = self._iterative_generator.generate_with_iteration(
                prompt=base_prompt,
                validation_fn=validation_fn,
                strategy=strategy or (GenerationStrategy.BALANCED if GenerationStrategy else None)
            )
        else:
            # 直接返回基础结果
            final_content = "【生成器未初始化】"
            stats = {'iterations': 0, 'scores': []}

        # === 步骤7: 输出保存 ===
        if self._logger:
            self._logger.info(f"[V3] 生成完成，最终内容长度: {len(final_content)} 字符")

        # 更新上下文记忆
        if use_context_memory:
            self.previous_chapters.append({
                'title': chapter_title,
                'content': final_content,
                'word_count': len(final_content)
            })
            # 保持最多5章上下文
            if len(self.previous_chapters) > 5:
                self.previous_chapters = self.previous_chapters[-5:]

        # 构建统计信息
        scores = stats.get('scores', [])
        final_stats = {
            'final_score': scores[-1] if scores else 0.0,
            'total_iterations': stats.get('iterations', 0),
            'all_scores': scores,
            'has_chapter_end': '【本章完】' in final_content,
            'word_count': len(final_content),
            'target_word_count': target_word_count
        }

        if self._logger:
            self._logger.info(f"[V3] 生成完成 - 评分: {final_stats['final_score']:.3f}, 迭代: {final_stats['total_iterations']}, 字数: {final_stats['word_count']}, 包含【本章完】: {final_stats['has_chapter_end']}")

        return final_content, final_stats

    def _build_simple_prompt(
        self,
        chapter_title: str,
        chapter_outline: str,
        world_view: str,
        style: str,
        characters: List[Dict]
    ) -> str:
        """构建简化的提示词（当ContextBuilder不可用时）"""
        parts = [
            f"请创作小说章节：{chapter_title}",
            "",
            f"章节大纲：\n{chapter_outline}",
            ""
        ]
        
        if world_view:
            parts.append(f"世界观：\n{world_view[:500]}...")
            parts.append("")
        
        if style:
            parts.append(f"写作风格：\n{style[:300]}...")
            parts.append("")
        
        if characters:
            parts.append("人物：")
            for char in characters[:3]:
                name = char.get('basic_info', {}).get('name', '未知')
                role = char.get('basic_info', {}).get('role', '未知')
                parts.append(f"  - {name}（{role}）")
            parts.append("")
        
        parts.extend([
            "【重要要求】",
            f"1. 目标字数：{self.target_word_count}字",
            "2. 必须在末尾添加【本章完】标记",
            "3. 严格遵守人物设定和世界观设定"
        ])
        
        return "\n".join(parts)
    
    def _ensure_chapter_end_marker(self, prompt: str) -> str:
        """
        确保提示词中包含【本章完】要求

        这是百分百必须的附加要求
        """
        if "【本章完】" in prompt:
            # 已经包含，强化说明
            if "必须" not in prompt or "强制" not in prompt:
                prompt += "\n\n【重要提醒】章节结束时必须在末尾添加【本章完】标记！"
        else:
            # 不包含，强制添加
            prompt += "\n\n【重要要求】章节结束时必须在末尾添加【本章完】标记！\n这是章节完成的必要条件，请务必遵守。"

        return prompt
    
    def _validate_content(
        self,
        content: str,
        target_word_count: int,
        chapter_outline: str,
        style_profile: Optional[Dict],
        characters: List[Dict],
        world_view: str
    ) -> Tuple[float, Dict, List]:
        """
        验证内容质量（简化版）
        
        返回：(total_score, dimension_scores, suggestions)
        """
        # 计算各维度评分
        scores = {}
        suggestions = []
        
        # 1. 字数评分
        actual_words = len(content)
        if actual_words < target_word_count * 0.5:
            word_score = 0.2
            suggestions.append(f"字数严重不足：目标{target_word_count}字，实际{actual_words}字")
        elif actual_words < target_word_count * 0.8:
            word_score = 0.5
            suggestions.append(f"字数不足：目标{target_word_count}字，实际{actual_words}字")
        elif actual_words <= target_word_count * 1.1:
            word_score = 1.0
        elif actual_words <= target_word_count * 1.5:
            word_score = 0.5
            suggestions.append(f"字数偏多：目标{target_word_count}字，实际{actual_words}字")
        else:
            word_score = 0.2
            suggestions.append(f"字数严重超标：目标{target_word_count}字，实际{actual_words}字")
        
        scores['字数'] = word_score
        
        # 2. 大纲评分
        if chapter_outline:
            outline_keywords = set(re.findall(r'[\u4e00-\u9fa5]{2,4}', chapter_outline))
            content_keywords = set(re.findall(r'[\u4e00-\u9fa5]{2,4}', content))
            overlap = len(outline_keywords & content_keywords) / max(len(outline_keywords), 1)
            scores['大纲'] = min(1.0, overlap + 0.3)
        else:
            scores['大纲'] = 0.7
        
        # 3. 风格评分
        scores['风格'] = 0.7  # 默认值
        
        # 4. 人设评分
        if characters:
            scores['人设'] = 0.7
        else:
            scores['人设'] = 0.8
        
        # 5. 世界观评分
        if world_view:
            scores['世界观'] = 0.7
        else:
            scores['世界观'] = 0.8
        
        # 6. AI感评分
        ai_patterns = ['首先', '其次', '最后', '总之', '综上所述', '值得注意的是']
        ai_count = sum(1 for p in ai_patterns if p in content)
        scores['AI感'] = max(0.3, 1.0 - ai_count * 0.1)
        
        # 7. 上下文契合度
        scores['上下文契合度'] = 0.8
        
        # 计算总分（加权平均）
        weights = {
            '字数': 0.10,
            '大纲': 0.15,
            '风格': 0.25,
            '人设': 0.25,
            '世界观': 0.20,
            'AI感': 0.05,
            '上下文契合度': 0.05  # 新增维度
        }
        
        total_score = sum(scores.get(k, 0.5) * w for k, w in weights.items())
        
        # 创建DimensionScore对象
        if DimensionScore:
            dimension_scores = {
                k: DimensionScore(k, v, '', []) for k, v in scores.items()
            }
        else:
            dimension_scores = scores
        
        return total_score, dimension_scores, suggestions
    
    def _score_context_fit(self, content: str, previous_chapters: List[str]) -> float:
        """
        上下文契合度评分（V5.3新增）
        
        分析当前章节与前面章节的一致性：
        1. 人物名称一致性
        2. 关键事件延续性  
        3. 时间线连贯性
        """
        if not previous_chapters:
            return 0.8
        
        scores = []
        
        previous_text = '\n'.join(previous_chapters)
        
        # 1. 人物名称一致性
        prev_names = set(re.findall(r'[\u4e00-\u9fa5]{2,4}', previous_text))
        curr_names = set(re.findall(r'[\u4e00-\u9fa5]{2,4}', content))
        
        stop_words = {'世界', '中国', '大陆', '森林', '山脉', '河流', '宫殿', '国家', '军队', '人民', '百姓', '江湖', '武林', '修仙'}
        prev_names = prev_names - stop_words
        curr_names = curr_names - stop_words
        
        if prev_names:
            name_overlap = len(prev_names & curr_names) / len(prev_names)
            scores.append(min(1.0, name_overlap + 0.2))
        else:
            scores.append(0.8)
        
        # 2. 关键事件延续性
        action_patterns = ['说', '走', '看', '想', '做', '去', '来', '到', '发现', '决定', '明白', '意识到']
        prev_actions = set(a for a in action_patterns if a in previous_text)
        curr_actions = set(a for a in action_patterns if a in content)
        
        if prev_actions:
            action_overlap = len(prev_actions & curr_actions) / len(prev_actions)
            scores.append(min(1.0, action_overlap + 0.2))
        else:
            scores.append(0.8)
        
        # 3. 时间线连贯性
        time_words = ['之后', '然后', '接着', '后来', '第二天', '今天', '昨天', '明天']
        prev_time = sum(1 for w in time_words if w in previous_text)
        curr_time = sum(1 for w in time_words if w in content)
        
        if prev_time > 0 and curr_time > 0:
            scores.append(0.9)
        else:
            scores.append(0.7)
        
        # 加权平均
        weights = [0.4, 0.35, 0.25]
        final_score = sum(s * w for s, w in zip(scores, weights))
        
        return final_score


# ============================================================================
# 模块级函数（供插件加载器使用）
# ============================================================================

    def shutdown(self) -> bool:
        """优雅关闭插件
        
        清理资源：
        1. 清理上下文记忆
        2. 清理子插件引用
        3. 调用父类shutdown
        """
        try:
            # 清理上下文记忆
            if hasattr(self, 'previous_chapters'):
                self.previous_chapters.clear()
                if self._logger:
                    self._logger.info("[NovelGenerator] 已清理上下文记忆")
            
            # 清理子插件引用（不调用其shutdown，由插件系统统一管理）
            if hasattr(self, '_context_builder'):
                self._context_builder = None
            if hasattr(self, '_iterative_generator'):
                self._iterative_generator = None
            
            if self._logger:
                self._logger.info("[NovelGenerator] 插件已关闭")
            
            return super().shutdown()
            
        except Exception as e:
            if self._logger:
                self._logger.error(f"[NovelGenerator] 关闭失败: {e}")
            return False


def get_plugin_class():
    """获取插件类（供插件加载器调用）
    
    Returns:
        插件类
    """
    return NovelGeneratorPlugin


def register_plugin():
    """注册插件（供插件加载器调用）
    
    Returns:
        插件类
    """
    return NovelGeneratorPlugin
