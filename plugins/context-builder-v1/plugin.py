#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上下文构建器插件 V1 - 智能上下文构建器

基于RAG和智能检索，只发送最相关的内容。

优化策略：
1. 大纲关键词提取 → 检索相关世界观/人物/风格片段
2. 优先级排序 → 核心信息优先发送
3. 压缩格式 → 结构化简写减少Token
4. 上下文记忆 → 避免重复发送已知信息

===============================================================================
🔴 【评分反馈，循环优化生成流程】核心模块 - 强制保护区域
===============================================================================
⚠️ 本文件是【评分反馈，循环优化生成流程】的上下文构建模块
⚠️ 受 V5 最全经验文档 中的强制保护机制约束
⚠️ 未经用户明确授权，禁止以下操作：
   - ❌ 移除或弱化【本章完】强制要求
   - ❌ 修改 build_optimized_prompt() 的核心执行流程
   - ❌ 简化世界观/人物/风格检索逻辑
⚠️ 核心流程必须保持不变：
   1. 构建包含世界观、人物、风格、大纲、上下文记忆的提示词
   2. 强制要求章节结束必须添加【本章完】标记
   3. 保持优先级排序（核心信息优先）
   4. 保持压缩格式减少Token消耗
===============================================================================

迁移说明：
- 源文件：Novel Writing Assistant-V5/scripts/context_builder.py
- 目标：plugins/context-builder-v1 (GeneratorPlugin)
- 迁移日期：2026-03-23
- 迁移人：数据工程师
"""

import re
import logging
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict
from dataclasses import dataclass

# 导入核心接口
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.plugin_interface import GeneratorPlugin, PluginMetadata, PluginType, PluginContext
from core.models import GenerationRequest, GenerationResult, ValidationScores


class ContextBuilderPlugin(GeneratorPlugin):
    """
    上下文构建器插件 - GeneratorPlugin实现
    
    智能上下文构建器，基于RAG和智能检索构建优化的提示词。
    
    核心功能：
    1. 构建优化的提示词（基于七要素提示词工程框架）
    2. 智能检索相关世界观片段
    3. 智能检索相关人物
    4. 压缩风格描述
    5. 构建前情提要
    6. 提取冲突钩子
    """
    
    def __init__(self):
        """初始化上下文构建器插件"""
        metadata = PluginMetadata(
            id="context-builder-v1",
            name="上下文构建器 V1",
            version="1.0.0",
            description="智能上下文构建器，基于RAG和智能检索构建优化的提示词",
            author="项目组",
            plugin_type=PluginType.GENERATOR
        )
        super().__init__(metadata)
        
        # 上下文记忆，避免重复发送
        self.context_memory: Dict[str, Any] = {}
        # 实体缓存
        self.entity_cache: Dict[str, Any] = {}
        # 日志器
        self._logger: Optional[logging.Logger] = None
    
    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据"""
        return PluginMetadata(
            id="context-builder-v1",
            name="上下文构建器 V1",
            version="1.0.0",
            description="智能上下文构建器，基于RAG和智能检索构建优化的提示词",
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
            
            self._logger.info("[ContextBuilder] 插件初始化成功")
            return True
            
        except Exception as e:
            if self._logger:
                self._logger.error(f"[ContextBuilder] 初始化失败: {e}")
            return False
    
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """
        生成内容 - 构建优化的提示词
        
        Args:
            request: 生成请求
            
        Returns:
            生成结果（包含构建的提示词）
        """
        try:
            # 从request中提取参数
            chapter_title = request.title
            chapter_outline = request.outline
            
            # 从额外参数中获取世界观、风格、人物等
            extra = request.model_dump() if hasattr(request, 'model_dump') else {}
            world_view = extra.get('world_view', '')
            style = extra.get('style', '')
            characters = extra.get('characters', [])
            previous_chapters = extra.get('previous_chapters', None)
            max_worldview_tokens = extra.get('max_worldview_tokens', 2000)
            max_style_tokens = extra.get('max_style_tokens', 1500)
            target_word_count = extra.get('target_word_count', request.word_count)
            
            # 构建优化的提示词
            prompt = self.build_optimized_prompt(
                chapter_title=chapter_title,
                chapter_outline=chapter_outline,
                world_view=world_view,
                style=style,
                characters=characters,
                previous_chapters=previous_chapters,
                max_worldview_tokens=max_worldview_tokens,
                max_style_tokens=max_style_tokens,
                target_word_count=target_word_count
            )
            
            return GenerationResult(
                request_id=request.request_id,
                content=prompt,
                word_count=len(prompt),
                iteration_count=0,
                validation_scores=None
            )
            
        except Exception as e:
            if self._logger:
                self._logger.error(f"[ContextBuilder] 生成失败: {e}")
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
        if request.word_count < 500 or request.word_count > 10000:
            errors.append(f"字数范围应为500-10000，当前为{request.word_count}")
            
        return len(errors) == 0, errors
    
    def get_generation_options(self) -> Dict[str, Any]:
        """
        获取生成选项定义
        
        Returns:
            选项定义字典
        """
        return {
            "max_worldview_tokens": {
                "type": "integer",
                "default": 2000,
                "min": 500,
                "max": 5000,
                "description": "世界观最大Token数"
            },
            "max_style_tokens": {
                "type": "integer",
                "default": 1500,
                "min": 500,
                "max": 3000,
                "description": "风格最大Token数"
            }
        }
    
    # ========== 核心功能方法（从V5迁移）==========
    
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
        构建优化的提示词（基于七要素提示词工程框架）

        改进点：
        1. 明确角色与语气
        2. 增强输出要求的可见性（使用emoji和分隔线）
        3. 添加叙事目标
        4. 提供创作检查清单
        5. 优化冲突钩子提取

        Args:
            chapter_title: 章节标题
            chapter_outline: 章节大纲
            world_view: 世界观设定
            style: 写作风格
            characters: 人物列表
            previous_chapters: 前几章内容（用于上下文）
            max_worldview_tokens: 世界观最大Token数
            max_style_tokens: 风格最大Token数
            target_word_count: 目标字数

        Returns:
            优化后的提示词
        """
        prompt_parts = []

        # ========== 第零部分：🔴 核心创作原则(最高优先级) ==========
        prompt_parts.append("=" * 60)
        prompt_parts.append("🔴 核心创作原则(最高优先级,违反将导致创作失败)")
        prompt_parts.append("=" * 60)
        prompt_parts.append("在开始创作前,你必须:")
        prompt_parts.append("  1. **严格**按照提供的人物设定塑造角色")
        prompt_parts.append("  2. **严格**遵守世界观的所有设定")
        prompt_parts.append("  3. **严格**遵循写作风格指导")
        prompt_parts.append("  4. **完整**执行章节大纲的所有要点")
        prompt_parts.append("")
        prompt_parts.append("【重要警告】")
        prompt_parts.append("⚠️ 擅自修改设定将导致评分不及格,需要重新生成")
        prompt_parts.append("⚠️ 偏离人物设定将导致评分不及格")
        prompt_parts.append("⚠️ 违背世界观将导致评分不及格")
        prompt_parts.append("")

        # ========== 第一部分：角色与语气 ==========
        prompt_parts.append("=" * 60)
        prompt_parts.append("创作任务")
        prompt_parts.append("=" * 60)
        prompt_parts.append(f"请创作小说章节：{chapter_title}")
        prompt_parts.append("")

        # ========== 第三部分：⚠️ 核心输出要求（最突出的部分）==========
        prompt_parts.append("=" * 60)
        prompt_parts.append("⚠️ 核心输出要求（违反将导致生成失败）⚠️")
        prompt_parts.append("=" * 60)
        prompt_parts.append(f"1. 【最重要】章节内容**必须**以【本章完】结尾，这是章节完成的唯一标志！")
        # V5.8 字数控制强化
        tolerance_low = int(target_word_count * 0.9)
        tolerance_high = int(target_word_count * 1.1)
        prompt_parts.append(f"2. 【字数硬性要求】目标字数：{target_word_count}字")
        prompt_parts.append(f"   - 合理范围：{tolerance_low}-{tolerance_high}字（±10%）")
        prompt_parts.append(f"   - ⚠️ 超过{tolerance_high}字将触发扣分，超标50%以上直接判定失败！")
        prompt_parts.append(f"   - ⚠️ 请严格控制篇幅，宁可精简也不要冗余！")
        prompt_parts.append(f"3. 【一票否决】如果没有【本章完】标记，评分将为0，需要重新生成！")
        prompt_parts.append(f"4. 【本章完】必须是完整标记，不能缺少任何字符！")
        prompt_parts.append(f"5. 不要在【本章完】之后再添加任何其他内容！")
        prompt_parts.append(f"6. 在每次反馈迭代中，如果没有【本章完】标记，请务必在改进时添加！")
        prompt_parts.append(f"7. 字数超标比字数不足更严重，超标过多将直接停止迭代！")
        prompt_parts.append("")
        prompt_parts.append("✅ 正确示例：")
        prompt_parts.append(f"（章节正文...，约{target_word_count}字）")
        prompt_parts.append(f"【本章完】")
        prompt_parts.append("")
        prompt_parts.append("❌ 错误示例：")
        prompt_parts.append("（章节正文...，但没有【本章完】标记）")
        prompt_parts.append("")
        prompt_parts.append("⚠️ 请确保：")
        prompt_parts.append(f"  - ✅ 最终内容末尾有【本章完】标记")
        prompt_parts.append(f"  - ✅ 字数接近{target_word_count}字")
        prompt_parts.append(f"  - ❌ 不要缺少【本章完】")
        prompt_parts.append(f"  - ❌ 不要在【本章完】后添加其他内容")
        prompt_parts.append("")

        # ========== 第四部分：叙事目标 ==========
        prompt_parts.append("=" * 60)
        prompt_parts.append("叙事目标")
        prompt_parts.append("=" * 60)
        prompt_parts.append("本章的创作目标是：")
        prompt_parts.append("  1. 推进情节发展，展现关键冲突")
        prompt_parts.append("  2. 深化角色刻画，展现人物成长")
        prompt_parts.append("  3. 营造恰当氛围，引发读者情感共鸣")
        prompt_parts.append("  4. 保持叙事连贯，与前后章自然衔接")
        prompt_parts.append("")

        # ========== 第五部分：章节大纲 ==========
        if chapter_outline:
            prompt_parts.append("=" * 60)
            prompt_parts.append("章节大纲")
            prompt_parts.append("=" * 60)
            prompt_parts.append(chapter_outline)

            # 提取冲突钩子
            conflict_hooks = self._extract_conflict_hooks(chapter_outline)
            if conflict_hooks:
                prompt_parts.append("")
                prompt_parts.append("🎯 核心冲突与张力：")
                for hook in conflict_hooks:
                    prompt_parts.append(f"  • {hook}")
            prompt_parts.append("")

        # ========== 第六部分：人物设定 ==========
        relevant_characters = self._retrieve_relevant_characters(
            chapter_outline, characters
        )
        if relevant_characters:
            prompt_parts.append("=" * 60)
            prompt_parts.append("人物设定")
            prompt_parts.append("=" * 60)
            prompt_parts.append("（本章涉及的主要人物）")
            for char_desc in relevant_characters:
                prompt_parts.append(f"\n{char_desc}")
            prompt_parts.append("")

        # ========== 第七部分：世界观背景 ==========
        if world_view:
            relevant_worldview = self._retrieve_relevant_worldview(
                chapter_outline, world_view, max_worldview_tokens
            )
            if relevant_worldview:
                prompt_parts.append("=" * 60)
                prompt_parts.append("世界观背景")
                prompt_parts.append("=" * 60)
                prompt_parts.append(relevant_worldview)
                prompt_parts.append("")

        # ========== 第八部分：写作风格 ==========
        if style:
            compressed_style = self._compress_style(style, max_style_tokens)
            if compressed_style:
                prompt_parts.append("=" * 60)
                prompt_parts.append("写作风格")
                prompt_parts.append("=" * 60)
                prompt_parts.append(compressed_style)
                prompt_parts.append("")

        # ========== 第九部分：前情提要 ==========
        if previous_chapters:
            context_summary = self._build_context_summary(previous_chapters)
            if context_summary:
                prompt_parts.append("=" * 60)
                prompt_parts.append("前情提要")
                prompt_parts.append("=" * 60)
                prompt_parts.append(context_summary)
                prompt_parts.append("")

        # ========== 第十部分：创作检查清单 ==========
        prompt_parts.append("=" * 60)
        prompt_parts.append("创作检查清单")
        prompt_parts.append("=" * 60)
        prompt_parts.append("在创作前请确认：")
        prompt_parts.append(f"  [ ] 已理解章节大纲的核心要点")
        prompt_parts.append(f"  [ ] 已明确本章要展现的核心冲突")
        prompt_parts.append(f"  [ ] 已熟悉本章涉及的人物特征")
        prompt_parts.append(f"  [ ] 已了解相关的世界观设定")
        prompt_parts.append(f"  [ ] 已确定写作风格和叙述语气")
        prompt_parts.append(f"  [ ] 已记住【本章完】标记和字数要求")
        prompt_parts.append("")
        prompt_parts.append("=" * 60)
        prompt_parts.append("现在请开始创作，确保符合以上所有要求。")
        prompt_parts.append("=" * 60)

        return "\n".join(prompt_parts)
    
    def _retrieve_relevant_worldview(
        self,
        chapter_outline: str,
        world_view: str,
        max_tokens: int
    ) -> str:
        """
        智能检索相关世界观片段

        策略：
        1. 从大纲提取关键词（地点、势力、物品等）
        2. 在世界观中检索相关段落
        3. 优先保留核心设定（法则、地理、社会结构）
        """
        if not world_view:
            return ""

        # 1. 提取关键词
        keywords = self._extract_keywords(chapter_outline)

        # 2. 分割世界观为段落
        paragraphs = [p.strip() for p in world_view.split('\n\n') if p.strip()]

        # 3. 评分每个段落的相关性
        scored_paragraphs = []
        for para in paragraphs:
            score = self._calculate_relevance(para, keywords)
            scored_paragraphs.append((score, para))

        # 4. 排序并选取最相关的段落
        scored_paragraphs.sort(key=lambda x: x[0], reverse=True)

        # 5. 优先级调整：核心设定（法则、地理等）给予加分
        core_sections = ['法则', '地理', '历史', '势力', '社会结构', '世界观']
        for idx, (score, para) in enumerate(scored_paragraphs):
            for section in core_sections:
                if section in para:
                    scored_paragraphs[idx] = (score + 0.3, para)
                    break

        # 6. 重新排序
        scored_paragraphs.sort(key=lambda x: x[0], reverse=True)

        # 7. 选取最相关的段落，直到达到Token限制
        selected_parts = []
        current_length = 0
        for score, para in scored_paragraphs:
            if current_length + len(para) <= max_tokens:
                selected_parts.append(para)
                current_length += len(para)
            else:
                # 尝试截断最后一个段落
                remaining = max_tokens - current_length
                if remaining > 100:  # 至少100字符才有意义
                    selected_parts.append(para[:remaining] + '...')
                break

        return '\n\n'.join(selected_parts)

    def _retrieve_relevant_characters(
        self,
        chapter_outline: str,
        characters: List[Dict]
    ) -> List[str]:
        """
        智能检索相关人物（只保留大纲中涉及的人物）

        Returns:
            压缩格式的人物描述列表
        """
        if not characters:
            return []

        # 1. 从大纲提取人物名
        mentioned_names = self._extract_character_names(chapter_outline)

        # 2. 筛选相关人物（提到的 + 最多3个主要人物）
        relevant_chars = []
        for char in characters:
            basic_info = char.get('basic_info', {})
            name = basic_info.get('name', '')
            if not name:
                continue

            # 判断是否相关
            is_relevant = (
                name in mentioned_names or
                basic_info.get('role', '') in ['主角', '主要角色', '核心人物'] or
                len(relevant_chars) < 3
            )

            if is_relevant:
                # 压缩格式
                compressed = self._compress_character(char)
                relevant_chars.append(compressed)

        return relevant_chars

    def _compress_style(self, style: str, max_tokens: int) -> str:
        """
        压缩风格描述

        策略：
        1. 保留核心风格标签（叙事视角、语言风格、节奏）
        2. 使用简写格式
        3. 去除冗余描述
        """
        if not style:
            return ""

        # 提取关键信息
        compressed_lines = []

        # 1. 叙事视角
        if '第一人称' in style or '第三人称' in style:
            perspective = '第一人称' if '第一人称' in style else '第三人称'
            compressed_lines.append(f"视角: {perspective}")

        # 2. 语言风格
        style_keywords = {
            '文白': '半文半白',
            '文雅': '文雅优美',
            '通俗': '通俗平实',
            '幽默': '幽默风趣',
            '简洁': '简洁有力',
            '华丽': '华丽辞藻'
        }
        for key, value in style_keywords.items():
            if key in style:
                compressed_lines.append(f"语言: {value}")
                break

        # 3. 节奏
        if '快节奏' in style or '慢节奏' in style:
            pace = '快节奏' if '快节奏' in style else '慢节奏'
            compressed_lines.append(f"节奏: {pace}")

        # 4. 保留核心段落（如果压缩后太短）
        if len(compressed_lines) < 3:
            paragraphs = style.split('\n\n')
            # 保留前2个最重要的段落
            for para in paragraphs[:2]:
                if len(para) < max_tokens:
                    compressed_lines.append(para)

        result = '\n'.join(compressed_lines)

        # 确保不超过最大Token数
        if len(result) > max_tokens:
            result = result[:max_tokens] + '...'

        return result

    def _compress_character(self, char: Dict) -> str:
        """
        构建完整的人物档案卡片（优化版）

        🔴 核心改进：发送完整的人物设定，而不是过度压缩

        格式:
        【人物名称】
        基础信息: ...
        性格特征: ...
        外貌特征: ...
        背景故事: ...
        人物关系: ...
        行为模式: ...
        语言风格: ...
        """
        basic_info = char.get('basic_info', {})
        name = basic_info.get('name', '')
        if not name:
            return ""

        lines = []
        lines.append(f"\n【{name}】")

        # 1. 基础信息（完整保留）
        basic_parts = []
        role = basic_info.get('role', '')
        if role:
            basic_parts.append(f"角色:{role}")

        age = basic_info.get('age', '')
        if age and age != '未知':
            basic_parts.append(f"年龄:{age}岁")

        gender = basic_info.get('gender', '')
        if gender and gender != '未知':
            basic_parts.append(f"性别:{gender}")

        mbti = basic_info.get('mbti', '')
        if mbti:
            basic_parts.append(f"MBTI:{mbti}")

        if basic_parts:
            lines.append("基础信息: " + " | ".join(basic_parts))

        # 2. 性格特征（完整保留，不截断）
        personality = basic_info.get('personality', '')
        if personality:
            lines.append(f"性格特征: {personality}")

        # 3. 外貌特征（完整保留）
        appearance = basic_info.get('appearance', '')
        if appearance:
            lines.append(f"外貌特征: {appearance}")

        # 4. 背景故事（关键经历，不超过200字）
        background = basic_info.get('background', '')
        if background:
            # 如果超过200字，保留最关键的部分
            if len(background) > 200:
                # 尝试提取关键经历
                key_sentences = []
                sentences = background.replace('。', '。\n').split('\n')
                for sentence in sentences:
                    if any(keyword in sentence for keyword in ['经历', '过去', '曾经', '后来', '因为', '所以']):
                        key_sentences.append(sentence.strip())
                if key_sentences:
                    background = ''.join(key_sentences[:3])  # 最多3个关键句子
                else:
                    background = background[:200] + '...'
            lines.append(f"背景故事: {background}")

        # 5. 目标动机（完整保留）
        goals = basic_info.get('goals', '')
        if goals:
            lines.append(f"目标动机: {goals}")

        # 6. 人物关系（从设定中提取）
        relationships = char.get('relationships', [])
        if relationships:
            rel_desc = []
            for rel in relationships[:3]:  # 最多3个关键关系
                target = rel.get('target', '')
                rel_type = rel.get('type', '')
                if target and rel_type:
                    rel_desc.append(f"{target}({rel_type})")
            if rel_desc:
                lines.append(f"人物关系: {', '.join(rel_desc)}")

        # 7. 行为模式（从设定中提取）
        behavior_patterns = char.get('behavior_patterns', {})
        if behavior_patterns:
            behavior_desc = []
            # 决策方式
            decision = behavior_patterns.get('decision_style', '')
            if decision:
                behavior_desc.append(f"决策:{decision}")
            # 典型行为
            typical = behavior_patterns.get('typical_behaviors', [])
            if typical:
                behavior_desc.append(f"典型行为:{','.join(typical[:3])}")
            if behavior_desc:
                lines.append(f"行为模式: {' | '.join(behavior_desc)}")

        # 8. 语言风格（从设定中提取）
        speech_style = char.get('speech_style', {})
        if speech_style:
            speech_desc = []
            # 说话特点
            features = speech_style.get('features', '')
            if features:
                speech_desc.append(features)
            # 常用词汇
            vocabulary = speech_style.get('vocabulary', [])
            if vocabulary:
                speech_desc.append(f"常用词:{','.join(vocabulary[:5])}")
            if speech_desc:
                lines.append(f"语言风格: {' | '.join(speech_desc)}")

        # 9. 喜好厌恶（如果有）
        preferences = char.get('preferences', {})
        if preferences:
            pref_desc = []
            likes = preferences.get('likes', [])
            if likes:
                pref_desc.append(f"喜欢:{','.join(likes[:3])}")
            dislikes = preferences.get('dislikes', [])
            if dislikes:
                pref_desc.append(f"讨厌:{','.join(dislikes[:3])}")
            if pref_desc:
                lines.append(f"喜好厌恶: {' | '.join(pref_desc)}")

        return '\n'.join(lines)

    def _extract_keywords(self, text: str) -> Set[str]:
        """从文本中提取关键词（地点、势力、物品等）"""
        keywords = set()

        # 常见关键词模式
        patterns = [
            r'([\u4e00-\u9fa5]{2,4})(城|山|河|岛|森林|宫殿|府|阁)',
            r'([\u4e00-\u9fa5]{2,4})(派|门|宗|教|国|朝|军)',
            r'([\u4e00-\u9fa5]{2,4})(剑|刀|法|术|功|诀)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                keywords.add(match[0])

        return keywords

    def _extract_character_names(self, text: str) -> Set[str]:
        """从文本中提取人物名（2-3个中文字符）"""
        # 简单提取：2-3个连续的中文字符
        names = re.findall(r'([\u4e00-\u9fa5]{2,3})', text)

        # 过滤常见非人名词
        stop_words = {'世界', '中国', '大陆', '森林', '山脉', '河流', '宫殿',
                     '国家', '军队', '人民', '百姓', '江湖', '武林', '修仙'}

        return set(name for name in names if name not in stop_words)

    def _calculate_relevance(self, paragraph: str, keywords: Set[str]) -> float:
        """计算段落与关键词的相关性评分"""
        if not keywords:
            return 0.5  # 无关键词时给予中等分数

        score = 0.0
        for keyword in keywords:
            if keyword in paragraph:
                score += 1.0

        # 归一化
        return score / len(keywords)

    def _build_context_summary(self, previous_chapters: List[str]) -> str:
        """
        构建前情提要摘要

        策略：
        1. 只保留最近2章
        2. 提取关键事件和人物状态
        """
        if not previous_chapters:
            return ""

        # 只取最近2章
        recent = previous_chapters[-2:]

        # 简单摘要：每章取前200字
        summaries = []
        for i, chapter in enumerate(recent, 1):
            summary = chapter[:200] + ('...' if len(chapter) > 200 else '')
            summaries.append(f"第{i}段: {summary}")

        return '\n'.join(summaries)

    def _extract_conflict_hooks(self, chapter_outline: str) -> List[str]:
        """
        从章节大纲中提取冲突钩子

        冲突类型：
        1. 人与人之间的矛盾
        2. 人与环境/命运的对抗
        3. 内心矛盾和成长
        4. 悬念和未知

        Returns:
            冲突钩子列表
        """
        conflict_hooks = []

        # 冲突关键词模式
        conflict_patterns = {
            '人与人矛盾': ['对峙', '冲突', '对抗', '争论', '争斗', '竞争', '敌对', '仇恨', '复仇'],
            '人物与命运': ['困境', '危机', '挑战', '遭遇', '面对', '逃脱', '生存', '考验', '磨难'],
            '内心矛盾': ['矛盾', '挣扎', '犹豫', '抉择', '困惑', '觉醒', '成长', '改变', '决心'],
            '悬念未知': ['发现', '揭露', '秘密', '真相', '谜团', '意外', '转折', '突变', '震惊']
        }

        # 扫描大纲，提取冲突点
        for conflict_type, keywords in conflict_patterns.items():
            for keyword in keywords:
                if keyword in chapter_outline:
                    # 找到包含关键词的句子
                    sentences = chapter_outline.split('。')
                    for sentence in sentences:
                        if keyword in sentence:
                            # 提取核心冲突描述（限制在50字以内）
                            hook = sentence.strip()[:50]
                            if hook and hook not in conflict_hooks:
                                conflict_hooks.append(hook)

        # 如果没有找到明确冲突，添加通用冲突提示
        if not conflict_hooks:
            conflict_hooks.append("展现本章情节中的核心冲突和矛盾")
            conflict_hooks.append("构建必要的张力和悬念")

        # 最多返回3个冲突钩子
        return conflict_hooks[:3]


# ============================================================================
# 模块级函数（供插件加载器使用）
# ============================================================================

    def clear_cache(self):
        """清理缓存"""
        if hasattr(self, 'context_memory'):
            self.context_memory.clear()
        if hasattr(self, 'entity_cache'):
            self.entity_cache.clear()
        if self._logger:
            self._logger.info("[ContextBuilder] 已清理缓存")
    
    def shutdown(self) -> bool:
        """优雅关闭插件
        
        清理资源：
        1. 清理上下文记忆
        2. 清理实体缓存
        3. 调用父类shutdown
        """
        try:
            self.clear_cache()
            
            if self._logger:
                self._logger.info("[ContextBuilder] 插件已关闭")
            
            return super().shutdown()
            
        except Exception as e:
            if self._logger:
                self._logger.error(f"[ContextBuilder] 关闭失败: {e}")
            return False


def get_plugin_class():
    """获取插件类（供插件加载器调用）
    
    Returns:
        插件类
    """
    return ContextBuilderPlugin


def register_plugin():
    """注册插件（供插件加载器调用）
    
    Returns:
        插件类
    """
    return ContextBuilderPlugin
