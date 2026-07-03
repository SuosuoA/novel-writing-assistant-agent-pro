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
# V1.49.27修复：使用importlib动态导入（因为目录名包含短横线）
import importlib.util
from pathlib import Path  # V2.7修复：知识评分函数裸用 Path（原仅局部导入两处）

# V2.7修复（《无极》实战捕获）：本模块 L1204/L1219 的 except 分支引用裸 logger
# 但模块级 logger 从未定义 → 知识维度评分一抛异常，except 自身 NameError
# 顶替原始异常向上崩掉整个九维评分 → 全维度降级 0.5、迭代反馈失去区分度。
# 修 logger 后原始异常现形：知识评分里 name 'Path' is not defined（链式第二层）。
logger = logging.getLogger(__name__)


def _load_plugin_module(plugin_dir: str, module_name: str = "plugin"):
    """动态加载插件模块（处理目录名包含短横线的情况）"""
    try:
        plugin_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), plugin_dir, f"{module_name}.py")
        if os.path.exists(plugin_path):
            spec = importlib.util.spec_from_file_location(f"plugins.{plugin_dir}.{module_name}", plugin_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
    except Exception:
        pass
    return None

# 加载 ContextBuilderPlugin
_context_builder_module = _load_plugin_module("context-builder-v1")
ContextBuilderPlugin = getattr(_context_builder_module, "ContextBuilderPlugin", None) if _context_builder_module else None

# 加载 IterativeGeneratorPlugin
_iter_gen_module = _load_plugin_module("iterative-generator-v2")
IterativeGeneratorPlugin = getattr(_iter_gen_module, "IterativeGeneratorPlugin", None) if _iter_gen_module else None
GenerationStrategy = getattr(_iter_gen_module, "GenerationStrategy", None) if _iter_gen_module else None
DimensionScore = getattr(_iter_gen_module, "DimensionScore", None) if _iter_gen_module else None


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
            
            # V1.49.27修复：优先从PluginRegistry获取依赖插件
            if hasattr(context, 'plugin_registry') and context.plugin_registry:
                try:
                    # 从PluginRegistry获取上下文构建器
                    cb_info = context.plugin_registry.get_plugin_info("context-builder-v1")
                    if cb_info and hasattr(cb_info, 'instance') and cb_info.instance:
                        self._context_builder = cb_info.instance
                        self._logger.info("[NovelGenerator] 从PluginRegistry获取上下文构建器成功")
                except Exception as e:
                    self._logger.warning(f"[NovelGenerator] 从PluginRegistry获取上下文构建器失败: {e}")
                
                try:
                    # 从PluginRegistry获取迭代生成器
                    ig_info = context.plugin_registry.get_plugin_info("iterative-generator-v2")
                    if ig_info and hasattr(ig_info, 'instance') and ig_info.instance:
                        self._iterative_generator = ig_info.instance
                        self._logger.info("[NovelGenerator] 从PluginRegistry获取迭代生成器成功")
                except Exception as e:
                    self._logger.warning(f"[NovelGenerator] 从PluginRegistry获取迭代生成器失败: {e}")
            
            # 备用方案：从服务定位器获取依赖插件
            if not self._context_builder and hasattr(context, 'service_locator') and context.service_locator:
                try:
                    self._context_builder = context.service_locator.get("context-builder-v1")
                    self._logger.info("[NovelGenerator] 从服务定位器获取上下文构建器成功")
                except Exception as e:
                    self._logger.warning(f"[NovelGenerator] 无法从服务定位器获取上下文构建器: {e}")
            
            if not self._iterative_generator and hasattr(context, 'service_locator') and context.service_locator:
                try:
                    self._iterative_generator = context.service_locator.get("iterative-generator-v2")
                    self._logger.info("[NovelGenerator] 从服务定位器获取迭代生成器成功")
                except Exception as e:
                    self._logger.warning(f"[NovelGenerator] 无法从服务定位器获取迭代生成器: {e}")
            
            # 最后备用方案：创建本地实例
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
            # V2.1修复：字段映射对齐 GenerationRequest 实际字段。
            # 旧代码从 extra['world_view']/['characters'] 取数，但请求字段名是
            # worldview_config/character_profiles → 世界观/人物恒为空，生成时静默丢失设定。
            chapter_outline = getattr(request, 'chapter_outline', None) or request.outline
            world_view = extra.get('world_view', '') or getattr(request, 'worldview_config', None) or ''
            if isinstance(world_view, dict):
                import json as _json
                world_view = _json.dumps(world_view, ensure_ascii=False)
            style = extra.get('style', '')
            characters = extra.get('characters', []) or getattr(request, 'character_profiles', None) or []
            target_word_count = request.word_count or self.target_word_count
            strategy_str = extra.get('strategy', 'balanced')
            strategy = GenerationStrategy(strategy_str) if GenerationStrategy and isinstance(strategy_str, str) else None
            use_context_memory = extra.get('use_context_memory', True)
            style_profile = extra.get('style_profile') or getattr(request, 'style_profile', None)

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
                style_profile=style_profile,
                knowledge_categories=getattr(request, 'knowledge_categories', None),
                writing_techniques=getattr(request, 'writing_techniques', None),
            )

            # V2.1修复（ADR-010）：generate_chapter 已算出 weighted_total_score/passed/
            # dimension_scores，旧代码直接丢弃（validation_scores=None、无metadata），
            # 违反"评分归属插件层"合同。现随 metadata 完整返回。
            return GenerationResult(
                request_id=request.request_id,
                content=final_content,
                word_count=len(final_content),
                iteration_count=stats.get('total_iterations', 0),
                validation_scores=None,
                metadata=stats,
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

    def seed_previous_chapters(self, chapter_texts: List[str]) -> None:
        """外部种子前章上下文（V2.2新增，会话恢复场景）

        仅在内部记忆为空时生效（会话内自累计优先），保持前5章上限
        （评分反馈循环锁定规则：上下文记忆前 5 章）。

        Args:
            chapter_texts: 前章正文文本列表（按章节顺序）
        """
        if self.previous_chapters or not chapter_texts:
            return
        for text in chapter_texts[-5:]:
            if isinstance(text, str) and text.strip():
                self.previous_chapters.append({
                    'title': '',
                    'content': text,
                    'word_count': len(text),
                })
        if self._logger and self.previous_chapters:
            self._logger.info(
                f"[V3] 前章上下文已种子: {len(self.previous_chapters)} 章")

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
        style_profile: Optional[Dict] = None,
        knowledge_categories: Optional[List[str]] = None,  # V2.12新增
        knowledge_domains: Optional[List[str]] = None,     # V2.12新增
        writing_techniques: Optional[List[str]] = None,    # V2.12新增
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
            knowledge_categories: 选中的知识库分类（V2.12新增）
            knowledge_domains: 选中的知识领域（V2.12新增）
            writing_techniques: 选中的写作技巧（V2.12新增）
            use_context_memory: 是否使用上下文记忆
            style_profile: 风格档案

        Returns:
            (生成的内容, 统计信息)
        """
        if self._logger:
            self._logger.info(f"[V3] 开始生成章节: {chapter_title}, 目标字数: {target_word_count}")

        # V2.1修复：人物数据形状归一化（与专家模式V6.3同类修复）。
        # GenerationDataService 输出 {name: profile} 字典，而下游（提示词构建L588、
        # 内联评分L899、context-builder）都按 list[dict] 遍历——dict会迭代出str导致
        # 'str' object has no attribute 'get'，普通模式生成/评分整体崩溃。
        if isinstance(characters, dict):
            _char_list = []
            for _cname, _prof in characters.items():
                if isinstance(_prof, dict):
                    if not _prof.get('name') and not (
                            isinstance(_prof.get('basic_info'), dict)
                            and _prof['basic_info'].get('name')):
                        _prof = dict(_prof)
                        _prof['name'] = _cname
                    _char_list.append(_prof)
                else:
                    _char_list.append({'name': _cname})
            characters = _char_list
        elif characters is None:
            characters = []

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
            # 简化版提示词（V2.12新增：支持知识库和写作技巧）
            base_prompt = self._build_simple_prompt(
                chapter_title, chapter_outline, world_view, style, characters,
                knowledge_categories=knowledge_categories,
                writing_techniques=writing_techniques
            )

        # V2.13修复（《无极》九维审计）：知识库/写作技巧注入原来只存在于
        # 降级版提示词——主路径（ContextBuilder 可用时）从未注入，正文
        # 不可能引用知识 → knowledge 维度恒 0.6。主路径补同源注入段。
        if self._context_builder and (knowledge_categories or writing_techniques):
            extra_parts = []
            if knowledge_categories:
                knowledge_content = self._retrieve_knowledge(
                    knowledge_categories, query=chapter_outline or chapter_title)
                if knowledge_content:
                    extra_parts.append("【知识库参考】")
                    extra_parts.append("以下是相关的知识库内容，请在创作时自然化用（用修辞与情节体现，勿复述原文）：")
                    extra_parts.append(knowledge_content)
            if writing_techniques:
                techniques_content = self._retrieve_writing_techniques(writing_techniques)
                if techniques_content:
                    extra_parts.append("【写作技巧要求】")
                    extra_parts.append("以下写作技巧请在创作中严格运用：")
                    extra_parts.append(techniques_content)
            if extra_parts:
                base_prompt = base_prompt + "\n\n" + "\n".join(extra_parts)

        # 强制附加【本章完】要求（百分百保证）
        base_prompt = self._ensure_chapter_end_marker(base_prompt)

        if self._logger:
            self._logger.info(f"[V3] 基础提示词长度: {len(base_prompt)} 字符")

        # === 步骤2-6: 调用迭代生成器（内部完成剩余步骤）===
        if self._logger:
            self._logger.info("[V3] 步骤2-6: 调用迭代生成器进行循环优化")

        # 定义验证函数（V2.0修订 - 桥接quality-validator-v1九维度评分）
        def validation_fn(content: str):
            """验证内容质量（桥接插件九维度评分，降级到内联评分）"""
            plugin_result = self._validate_via_plugin(
                content=content,
                target_word_count=target_word_count,
                chapter_outline=chapter_outline,
                style_profile=style_profile,
                characters=characters,
                world_view=world_view,
                knowledge_categories=knowledge_categories,
                writing_techniques=writing_techniques,
            )
            if plugin_result is not None:
                return plugin_result
            # 降级：插件不可用时使用内联评分（也是九维度）
            return self._validate_content(
                content=content,
                target_word_count=target_word_count,
                chapter_outline=chapter_outline,
                style_profile=style_profile,
                characters=characters,
                world_view=world_view,
                knowledge_categories=knowledge_categories
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
        # V2.7修复（《无极》实战）：模型偶把"# 第N章"标题写进正文行首——
        # 污染正文、虚增字数。剥离开头的markdown/纯章节标题行。
        if final_content:
            _lines = final_content.lstrip().split('\n')
            while _lines and re.match(r'^\s*#{0,6}\s*第[\d一二三四五六七八九十百千]+章\s*$',
                                      _lines[0].strip()):
                _lines.pop(0)
            final_content = '\n'.join(_lines).lstrip('\n')

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
        dimension_scores_list = stats.get('dimension_scores', [])
        final_dimension_scores = dimension_scores_list[-1] if dimension_scores_list else {}
        
        # 将DimensionScore对象转换为可显示的字典
        display_scores = {}
        if final_dimension_scores:
            for dim_name, dim_val in final_dimension_scores.items():
                if hasattr(dim_val, 'score'):
                    display_scores[dim_name] = dim_val.score
                elif isinstance(dim_val, (int, float)):
                    display_scores[dim_name] = dim_val
        
        # 计算加权总分（V3.0修订：由插件层计算，GUI不硬编码权重）
        weights = {
            'worldview': 0.12, 'character': 0.19, 'outline': 0.13,
            'style': 0.19, 'knowledge': 0.08, 'writing_technique': 0.08,
            'word_count': 0.08, 'context_coherence': 0.08, 'ai_feeling': 0.05,
        }
        weighted_total = sum(display_scores.get(k, 0.5) * w for k, w in weights.items())
        
        # V2.13修复（《无极》九维审计）：判定分与上报分必须同源。
        # 迭代循环以 validation_fn 的加权总分对照 0.8 阈值做达标判定，
        # 而此处曾用本地权重表对维度字典事后重算——两者因维度键差异
        # （如迭代器补充的'知识库一致性'覆盖分）产生分歧，出现
        # "循环判定达标停轮、上报却<0.8"的矛盾。返回内容是最佳轮次，
        # 故上报其真实评分 max(scores)；重算仅作 scores 为空时的兜底。
        authoritative_score = max(scores) if scores else round(weighted_total, 4)
        final_stats = {
            'final_score': scores[-1] if scores else 0.0,
            'total_iterations': stats.get('iterations', 0),
            'all_scores': scores,
            'dimension_scores': display_scores,
            'weighted_total_score': round(authoritative_score, 4),
            'passed': authoritative_score >= 0.8 and '【本章完】' in final_content,
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
        characters: List[Dict],
        knowledge_categories: Optional[List[str]] = None,
        writing_techniques: Optional[List[str]] = None,
    ) -> str:
        """构建简化的提示词（当ContextBuilder不可用时）
        
        V2.12新增：支持知识库和写作技巧注入
        """
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
                if not isinstance(char, dict):
                    continue
                # V2.1修复：兼容扁平dict（name/role在顶层）与V5嵌套（basic_info.name）
                bi = char.get('basic_info') if isinstance(char.get('basic_info'), dict) else {}
                name = bi.get('name') or char.get('name', '未知')
                role = bi.get('role') or char.get('role', '未知')
                parts.append(f"  - {name}（{role}）")
            parts.append("")
        
        # V2.12新增：注入知识库内容
        if knowledge_categories:
            parts.append("【知识库参考】")
            parts.append("以下是相关的知识库内容，请在创作时参考：")
            knowledge_content = self._retrieve_knowledge(knowledge_categories)
            if knowledge_content:
                parts.append(knowledge_content)
            parts.append("")
        
        # V2.12新增：注入写作技巧
        if writing_techniques:
            parts.append("【写作技巧要求】")
            parts.append("以下是必须遵循的写作技巧，请在创作时严格遵守：")
            techniques_content = self._retrieve_writing_techniques(writing_techniques)
            if techniques_content:
                parts.append(techniques_content)
            parts.append("")
        
        # 降低AI感文风要求（V2.6：降级路径也覆盖，与主路径一致）
        try:
            from core.ai_feeling_detector import build_anti_ai_prompt_guidance
            parts.append("")
            parts.append(build_anti_ai_prompt_guidance())
        except Exception:
            pass

        parts.extend([
            "【重要要求】",
            f"1. 目标字数：{self.target_word_count}字（严格控制在±10%范围内，即{int(self.target_word_count*0.9)}-{int(self.target_word_count*1.1)}字）",
            "2. 必须在末尾添加【本章完】标记",
            "3. 严格遵守人物设定和世界观设定",
            "4. 字数不足时扩展描写细节而非压缩；超出时精简而非增加新情节"
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
    
    def _retrieve_knowledge(self, knowledge_categories: List[str],
                            query: str = "") -> str:
        """
        检索知识库内容（V2.12新增）

        V2.13重写（《无极》九维审计）：原实现调用 recall.recall_by_category
        ——该方法在全代码库从未存在，每次 AttributeError 被 except 吞成
        警告 → 知识注入恒为空（幽灵符号+吞异常反模式，与 get_llm_client 同款）。
        改用真实 API KnowledgeRetriever.recall_knowledge(query, category)，
        query 用章节大纲以获得语义相关召回。

        Args:
            knowledge_categories: 知识库分类列表（如 xuanhuan/scifi）
            query: 检索查询文本（通常传章节大纲；空则用类别名）

        Returns:
            格式化的知识库内容
        """
        try:
            from core.knowledge_retriever import get_knowledge_retriever
            from pathlib import Path as _Path

            workspace_root = _Path(__file__).parent.parent.parent
            retriever = get_knowledge_retriever(workspace_root)

            if not retriever:
                if self._logger:
                    self._logger.warning("[V3] 知识检索器不可用")
                return ""

            all_knowledge = []
            for category in knowledge_categories:
                try:
                    results = retriever.recall_knowledge(
                        query=(query or category)[:500],
                        category=category,
                        top_k=5,
                        min_score=0.3,
                    )
                    for item in results or []:
                        title = getattr(item, 'title', '') or '未知知识点'
                        content = (getattr(item, 'content', '') or '')[:200]
                        all_knowledge.append(f"- [{getattr(item, 'category', category)}] {title}: {content}")
                except Exception as e:
                    if self._logger:
                        self._logger.warning(f"[V3] 检索知识库 {category} 失败: {e}")

            if all_knowledge:
                return "\n".join(all_knowledge[:20])  # 最多20条知识点
            if self._logger:
                self._logger.info(f"[V3] 知识库召回为空: categories={knowledge_categories}")
            return ""

        except ImportError:
            if self._logger:
                self._logger.warning("[V3] 知识库检索模块未安装")
            return ""
        except Exception as e:
            if self._logger:
                self._logger.error(f"[V3] 知识库检索异常: {e}")
            return ""
    
    def _retrieve_writing_techniques(self, techniques: List[str]) -> str:
        """
        检索写作技巧内容（V2.12新增）
        
        Args:
            techniques: 写作技巧列表
            
        Returns:
            格式化的写作技巧内容
        """
        try:
            import json
            from pathlib import Path
            
            # 写作技巧库路径
            workspace_root = Path(__file__).parent.parent.parent
            technique_dir = workspace_root / "data" / "knowledge"
            
            if not technique_dir.exists():
                if self._logger:
                    self._logger.warning(f"[V3] 写作技巧库目录不存在: {technique_dir}")
                return ""
            
            # 遍历所有写作技巧领域文件
            all_techniques = []
            technique_files = [
                "writing_technique_narrative.json",
                "writing_technique_description.json",
                "writing_technique_rhetoric.json",
                "writing_technique_structure.json",
                "writing_technique_special_sentence.json",
                "writing_technique_advanced.json",
            ]
            
            for filename in technique_files:
                file_path = technique_dir / filename
                if not file_path.exists():
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 查找匹配的技巧
                    for item in data:
                        if item.get('name') in techniques:
                            # 提取AI强制遵循规则
                            rules = item.get('ai_mandatory_rules', [])
                            if rules:
                                technique_text = f"\n【{item.get('name')}】\n"
                                technique_text += "\n".join([f"  {i+1}. {rule}" for i, rule in enumerate(rules[:5])])
                                all_techniques.append(technique_text)
                                
                except Exception as e:
                    if self._logger:
                        self._logger.warning(f"[V3] 读取技巧文件失败 {filename}: {e}")
            
            if all_techniques:
                return "\n".join(all_techniques)
            else:
                return ""
                
        except Exception as e:
            if self._logger:
                self._logger.error(f"[V3] 写作技巧检索异常: {e}")
            return ""
    
    def _validate_via_plugin(self, content: str, target_word_count: int,
                             chapter_outline: str, style_profile: Optional[Dict],
                             characters: List[Dict], world_view: str,
                             knowledge_categories: Optional[List[str]] = None,
                             writing_techniques: Optional[List[str]] = None):
        """
        通过quality-validator-v1插件进行九维度评分（桥接方案）
        
        设计原则：
        - 复用插件评分逻辑，不在novel-generator-v3中重写评分
        - 如果插件不可用，返回None触发降级到内联评分
        - 返回格式与iterative-generator-v2期望的(total_score, dimension_scores, suggestions)一致
        """
        try:
            validator = self._get_quality_validator()
            if not validator:
                return None
            
            # 使用validate_with_weights方法（直接传参）
            # V2.13：透传知识库类别（旧签名validator无此参则回退不传，保持兼容）
            try:
                result = validator.validate_with_weights(
                    text=content,
                    target_word_count=target_word_count,
                    chapter_outline=chapter_outline,
                    style_profile=style_profile,
                    character_profiles=characters,
                    world_view=world_view,
                    knowledge_categories=knowledge_categories
                )
            except TypeError:
                result = validator.validate_with_weights(
                    text=content,
                    target_word_count=target_word_count,
                    chapter_outline=chapter_outline,
                    style_profile=style_profile,
                    character_profiles=characters,
                    world_view=world_view
                )
            
            if result and hasattr(result, 'total_weighted_score'):
                # WeightedValidationResult → (total_score, dimension_scores, suggestions)
                dimension_scores = {}
                if hasattr(result, 'feedback') and result.feedback:
                    for dim_name, dim_data in result.feedback.items():
                        if isinstance(dim_data, dict) and 'score' in dim_data:
                            score_val = dim_data['score']
                            details = dim_data.get('details', '')
                            if DimensionScore:
                                dimension_scores[dim_name] = DimensionScore(dim_name, score_val, details, [])
                            else:
                                dimension_scores[dim_name] = score_val
                
                suggestions = []
                if hasattr(result, 'suggestions') and result.suggestions:
                    suggestions = result.suggestions
                
                return (result.total_weighted_score, dimension_scores, suggestions)
            
            return None
            
        except Exception as e:
            if self._logger:
                self._logger.warning(f"[V3] 插件评分失败，降级到内联评分: {e}")
            return None

    def _get_quality_validator(self):
        """获取quality-validator-v1插件实例

        V2.8修复（《无极》实战评分审计）：原实现只查注册表——无头/独立进程
        注册表为空 → 恒 None → 九维评分恒降级到内联规则分（character 0.5/
        style 0.6 等低天花板，0.8阈值实际不可达，5轮迭代必然全跑满）。
        补 context-builder 同款本地实例兜底（importlib+initialize+缓存）。
        """
        # 缓存命中
        if getattr(self, '_quality_validator_cached', None) is not None:
            return self._quality_validator_cached

        validator = None
        try:
            if self._context and hasattr(self._context, 'plugin_registry'):
                registry = self._context.plugin_registry
                if registry:
                    if hasattr(registry, 'get_plugin'):
                        validator = registry.get_plugin('quality-validator-v1')
                    elif hasattr(registry, 'get_plugin_info'):
                        info = registry.get_plugin_info('quality-validator-v1')
                        if info and hasattr(info, 'instance') and info.instance:
                            validator = info.instance
        except Exception:
            validator = None

        # 本地实例兜底（与 _context_builder 同款策略）
        if validator is None or not hasattr(validator, 'validate'):
            try:
                import importlib
                _qv_mod = importlib.import_module("plugins.quality-validator-v1.plugin")
                inst = _qv_mod.QualityValidatorPlugin()
                try:
                    from core.plugin_interface import PluginContext
                    inst.initialize(PluginContext(
                        event_bus=getattr(self._context, 'event_bus', None) if self._context else None,
                        service_locator=getattr(self._context, 'service_locator', None) if self._context else None,
                        config_manager=getattr(self._context, 'config_manager', None) if self._context else None,
                        plugin_registry=getattr(self._context, 'plugin_registry', None) if self._context else None,
                    ))
                except Exception as ie:
                    logger.debug(f"[V3] 质量验证器本地初始化未完成（降级可用性）: {ie}")
                validator = inst
                logger.info("[V3] 创建本地QualityValidatorPlugin实例（九维评分归位）")
            except Exception as e:
                logger.warning(f"[V3] 质量验证器本地兜底失败，将用内联规则分: {e}")
                return None

        if validator is not None and hasattr(validator, 'validate'):
            self._quality_validator_cached = validator
            return validator
        return None

    def _validate_content(
        self,
        content: str,
        target_word_count: int,
        chapter_outline: str,
        style_profile: Optional[Dict],
        characters: List[Dict],
        world_view: str,
        knowledge_categories: Optional[List[str]] = None
    ) -> Tuple[float, Dict, List]:
        """
        验证内容质量（降级内联版 - V2.0九维度对齐）
        
        返回：(total_score, dimension_scores, suggestions)
        """
        # 计算各维度评分（V2.0修订 - 九维度对齐）
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
        
        scores['word_count'] = word_score
        
        # 2. 大纲评分
        if chapter_outline:
            outline_keywords = set(re.findall(r'[\u4e00-\u9fa5]{2,4}', chapter_outline))
            content_keywords = set(re.findall(r'[\u4e00-\u9fa5]{2,4}', content))
            overlap = len(outline_keywords & content_keywords) / max(len(outline_keywords), 1)
            scores['outline'] = min(1.0, overlap + 0.3)
        else:
            scores['outline'] = 0.7
        
        # 3. 风格评分（V3.0修订：基于风格特征词匹配率）
        if style_profile and isinstance(style_profile, dict):
            style_keywords = set()
            for key in ['常用词汇', '关键词', '词汇偏好', '风格关键词', 'frequent_words', 'keywords']:
                words = style_profile.get(key, [])
                if isinstance(words, list):
                    style_keywords.update(str(w) for w in words)
                elif isinstance(words, str):
                    style_keywords.update(w.strip() for w in words.split(',') if w.strip())
            if style_keywords:
                matches = sum(1 for kw in style_keywords if kw in content)
                match_rate = matches / max(len(style_keywords), 1)
                scores['style'] = min(1.0, 0.5 + match_rate * 0.5)
            else:
                scores['style'] = 0.7  # 有风格档案但无特征词
        else:
            scores['style'] = 0.6  # 无风格档案，稍低
        
        # 4. 人设评分
        if characters:
            # 简单检测人物名是否出现
            char_names = [c.get('basic_info', {}).get('name', '') or c.get('name', '') for c in characters]
            mentioned = sum(1 for name in char_names if name and name in content)
            if mentioned > 0:
                scores['character'] = min(1.0, 0.5 + mentioned * 0.1)
            else:
                scores['character'] = 0.5
        else:
            scores['character'] = 0.7
        
        # 5. 世界观评分（V2.7修订：核心词命中率）
        # 旧算法用设定全部词表与正文求交集比率——1500+字设定词表巨大，
        # 2000字正文数学上不可能覆盖，比率天然<0.1（《无极》实测：正文
        # 已用"混沌/无极"体系却只得0.42）。改为：取设定高频核心词Top-30
        # （专有名词倾向），按核心词命中率打分。
        if world_view:
            worldview_text = str(world_view) if not isinstance(world_view, str) else world_view
            from collections import Counter
            _stop = {'一个', '可以', '通过', '进行', '以及', '或者', '但是',
                     '如果', '这个', '那个', '成为', '开始', '出现', '存在',
                     '所有', '任何', '之间', '不同', '各种', '之后', '其中'}
            _words = [w for w in re.findall(r'[一-龥]{2,4}', worldview_text)
                      if w not in _stop]
            _core = [w for w, _cnt in Counter(_words).most_common(30)]
            if _core:
                hit = sum(1 for w in _core if w in content)
                hit_rate = hit / len(_core)
                scores['worldview'] = min(1.0, 0.45 + hit_rate * 0.9)
            else:
                scores['worldview'] = 0.6
        else:
            scores['worldview'] = 0.6  # 无世界观，稍低
        
        # 6. 知识库引用评分
        knowledge_score = self._evaluate_knowledge_reference(content, knowledge_categories or [])
        scores['knowledge'] = knowledge_score
        
        # 7. 写作技巧评分（V2.0新增维度 - 与quality-validator-v1对齐）
        scores['writing_technique'] = self._evaluate_writing_technique(content)
        
        # 8. 上下文衔接评分（V2.0新增维度 - 替代原上下文契合度）
        scores['context_coherence'] = self._evaluate_context_coherence(content)
        
        # 9. AI感评分（V2.0修订 - 权重从11%修正为5%）
        ai_patterns = ['首先', '其次', '最后', '总之', '综上所述', '值得注意的是']
        ai_count = sum(1 for p in ai_patterns if p in content)
        scores['ai_feeling'] = max(0.3, 1.0 - ai_count * 0.1)
        
        # 计算总分（加权平均 - V2.0九维度权重，与quality-validator-v1一致）
        weights = {
            'word_count': 0.08,
            'knowledge': 0.08,
            'outline': 0.13,
            'style': 0.19,
            'character': 0.19,
            'worldview': 0.12,
            'writing_technique': 0.08,  # V2.0新增
            'context_coherence': 0.08,  # V2.0修正（原10%）
            'ai_feeling': 0.05,         # V2.0修正（原11%）
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
    
    def _evaluate_writing_technique(self, content: str) -> float:
        """
        写作技巧评分（V2.0新增 - 九维度对齐）
        
        评估内容的写作技巧水平：
        1. 修辞手法使用（比喻、拟人、排比等）
        2. 句式变化（长短句交替）
        3. 描写手法（动作、心理、环境描写）
        
        返回0-1的评分
        """
        try:
            score = 0.0
            
            # 1. 修辞手法检测（占比40%）
            rhetoric_patterns = {
                '比喻': ['像', '如同', '仿佛', '宛如', '好似', '犹如'],
                '拟人': ['似乎在', '好像在', '低语', '倾诉', '微笑着'],
                '排比': None,  # 需要特殊检测
                '夸张': ['极', '无比', '难以置信', '前所未有'],
                '反问': ['难道', '岂不是', '怎能'],
            }
            rhetoric_count = 0
            for name, patterns in rhetoric_patterns.items():
                if patterns and any(p in content for p in patterns):
                    rhetoric_count += 1
            
            # 排比检测：连续3个以上相同句式
            import re as _re
            sentences = _re.split(r'[。！？；]', content)
            if len(sentences) >= 3:
                # 检测连续短句
                short_sentences = [s.strip() for s in sentences if 4 <= len(s.strip()) <= 15]
                for i in range(len(short_sentences) - 2):
                    if (short_sentences[i][-1:] == short_sentences[i+1][-1:] == short_sentences[i+2][-1:]):
                        rhetoric_count += 1
                        break
            
            rhetoric_score = min(1.0, rhetoric_count / 3.0)  # 3种修辞手法即满分
            score += rhetoric_score * 0.4
            
            # 2. 句式变化检测（占比30%）
            if sentences:
                lengths = [len(s.strip()) for s in sentences if s.strip()]
                if lengths:
                    avg_len = sum(lengths) / len(lengths)
                    variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
                    std_dev = variance ** 0.5
                    # 标准差越大，句式变化越丰富
                    variety_score = min(1.0, std_dev / 20.0)
                else:
                    variety_score = 0.5
            else:
                variety_score = 0.5
            score += variety_score * 0.3
            
            # 3. 描写手法检测（占比30%）
            description_patterns = {
                '动作描写': ['走', '跑', '抓', '推', '拉', '挥', '举', '握', '转身', '迈步'],
                '心理描写': ['心想', '觉得', '感到', '暗自', '不禁', '心中', '思忖', '意识到'],
                '环境描写': ['天空', '阳光', '风', '雨', '山', '水', '树', '花', '月光', '云'],
                '神态描写': ['微笑', '皱眉', '叹息', '目光', '眼神', '脸色', '表情'],
            }
            desc_count = sum(1 for name, pats in description_patterns.items() 
                           if any(p in content for p in pats))
            desc_score = min(1.0, desc_count / 3.0)  # 3种描写手法即满分
            score += desc_score * 0.3
            
            return max(0.3, min(1.0, score))
            
        except Exception as e:
            if self._logger:
                self._logger.warning(f"[V3] 写作技巧评分失败: {e}")
            return 0.5
    
    def _evaluate_context_coherence(self, content: str) -> float:
        """
        上下文衔接评分（V2.0新增 - 九维度对齐）
        
        评估内容与上下文的衔接连贯性：
        1. 承接词使用（然而、于是、因此等）
        2. 人物/场景延续性
        3. 时间/空间过渡
        
        返回0-1的评分
        """
        try:
            score = 0.0
            
            # 1. 承接过渡词检测（占比30%）
            transition_words = {
                '转折': ['然而', '但是', '不过', '可是', '却', '虽然'],
                '顺承': ['于是', '然后', '接着', '随后', '便', '就'],
                '因果': ['因此', '所以', '因为', '由于', '故而'],
                '递进': ['而且', '并且', '同时', '此外', '不仅'],
                '时间': ['后来', '之后', '这时', '此刻', '当天', '第二天'],
            }
            transition_count = sum(1 for name, words in transition_words.items()
                                  if any(w in content for w in words))
            transition_score = min(1.0, transition_count / 3.0)
            score += transition_score * 0.3
            
            # 2. 段落间连贯性（占比40%）
            paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
            if len(paragraphs) > 1:
                # 检测段落间是否有衔接
                coherence_count = 0
                for i in range(1, len(paragraphs)):
                    prev_last = paragraphs[i-1][-20:] if len(paragraphs[i-1]) > 20 else paragraphs[i-1]
                    curr_first = paragraphs[i][:20:] if len(paragraphs[i]) > 20 else paragraphs[i]
                    # 段落间有代词或关联词衔接
                    pronouns = ['他', '她', '它', '这', '那', '此', '其']
                    if any(p in curr_first for p in pronouns):
                        coherence_count += 1
                    # 段落间有过渡词
                    if any(w in curr_first for ws in transition_words.values() for w in ws):
                        coherence_count += 1
                
                coherence_ratio = coherence_count / max(len(paragraphs) - 1, 1)
                paragraph_score = min(1.0, coherence_ratio + 0.3)
            else:
                paragraph_score = 0.6  # 单段落，无法评估连贯性
            score += paragraph_score * 0.4
            
            # 3. 内容完整度（占比30%）- 有开头和结尾
            completeness_score = 0.5
            if len(content) > 200:
                # 有明确开头（非突然开始）
                first_50 = content[:50]
                opening_signals = ['当', '在', '那天', '一', '此', '自', '从']
                if any(s in first_50 for s in opening_signals):
                    completeness_score += 0.25
                
                # 有明确结尾
                last_50 = content[-50:]
                closing_signals = ['【本章完】', '……', '。', '！', '？', '着', '了']
                if any(s in last_50 for s in closing_signals):
                    completeness_score += 0.25
            
            score += min(1.0, completeness_score) * 0.3
            
            return max(0.3, min(1.0, score))
            
        except Exception as e:
            if self._logger:
                self._logger.warning(f"[V3] 上下文衔接评分失败: {e}")
            return 0.5

    def _evaluate_knowledge_reference(self, content: str, knowledge_categories: List[str]) -> float:
        """
        知识点引用评分（V5.3修复 - P1-1）
        
        评估内容中对知识点的引用情况：
        1. 知识点关键词匹配
        2. 知识库一致性检测
        3. 返回0-1的评分
        
        参考：plugins/iterative-generator-v2/plugin.py 第797-869行
        """
        try:
            # 如果没有选择知识库，返回默认分
            if not knowledge_categories:
                return 0.7
            
            # 尝试调用知识库一致性检测
            try:
                from core.knowledge_recall import get_knowledge_recall
                recall = get_knowledge_recall(Path(__file__).parent.parent.parent)
                
                # 调用一致性检测
                check_result = recall.check_knowledge_consistency(
                    content=content,
                    category=None,  # 自动识别题材
                    top_k=10
                )
                
                # 返回一致性评分
                return check_result.consistency_score
                
            except Exception as e:
                logger.warning(f"知识库一致性检测失败，使用简化评分: {e}")
                
                # 简化评分：检测知识点关键词
                knowledge_keywords = [
                    '物理', '化学', '生物', '数学', '历史', '地理',
                    '天文', '心理', '哲学', '经济', '技术', '文化',
                    '魔法', '神话', '宗教', '修炼', '道家', '佛家'
                ]
                
                matched = sum(1 for kw in knowledge_keywords if kw in content)
                score = min(1.0, matched / 5.0)  # 每匹配5个关键词得1分
                
                return max(0.5, score)  # 最低0.5分
                
        except Exception as e:
            logger.error(f"知识点引用评分失败: {e}")
            return 0.5  # 默认评分

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
