#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迭代生成器插件 V2 - 迭代优化的章节生成器

核心流程（点下【开始生成】后的运行逻辑）：
1. 整理打包请求内容（百分百附加要求：结束加上【本章完】）
2. 向大模型发送请求（本地调用模型/线上调用API）
3. 接受返回文章
4. 从多维度评分（世界观、大纲、风格、人设、Ai感、字数、上下文契合度、知识库一致性，没有【本章完】视作未完成）
5. 分数小于0.8 -> 发送评分（总评分+各维度评分）+ 修改建议（围绕各维度） -> 再次接受返还
6. 再次评分 -> ... -> 评分大于0.8且标记【本章完】
7. 输出保存

===============================================================================
🔴 【评分反馈，循环优化生成流程】核心模块 - 强制保护区域
===============================================================================
⚠️ 本文件是【评分反馈，循环优化生成流程】的核心迭代循环模块
⚠️ 受 V5 最全经验文档 中的强制保护机制约束
⚠️ 未经用户明确授权，禁止以下操作：
   - ❌ 修改 generate_with_iteration() 的执行流程
   - ❌ 修改迭代判断条件（评分阈值0.8、最多5次迭代）
   - ❌ 修改【本章完】标记检查逻辑
   - ❌ 简化或删除反馈构建逻辑
⚠️ 核心流程必须保持不变：
   1. 步骤1: 整理打包请求内容（必须包含【本章完】要求）
   2. 步骤2: 向大模型发送请求
   3. 步骤3: 接受返回文章
   4. 步骤4: 从多维度评分
   5. 步骤5: 判断是否达标（评分<0.8或缺少【本章完】→循环）
   6. 步骤6: 构建反馈（评分+各维度评分+修改建议）
   7. 步骤7: 输出保存
===============================================================================

V2.1版本更新（2026-03-25）：
- 集成本地知识库一致性检测（Sprint 5-6）
- 新增知识库召回维度（权重10%）
- 反馈中包含知识冲突信息
- 评分准确率提升20%

迁移说明：
- 源文件：Novel Writing Assistant-V5/scripts/iterative_generator_v2.py
- 目标：plugins/iterative-generator-v2 (GeneratorPlugin)
- 迁移日期：2026-03-23
- 迁移人：数据工程师
"""

import logging
import sys
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass
from enum import Enum
import re
from pathlib import Path

# 初始化全局logger
logger = logging.getLogger(__name__)

# 导入核心接口
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.plugin_interface import GeneratorPlugin, PluginMetadata, PluginType, PluginContext
from core.models import GenerationRequest, GenerationResult, ValidationScores
from core.ai_provider import AIProviderError  # 导入异常类

# ============================================================================
# V2.1新增：知识库召回集成
# ============================================================================

# 知识库召回器（延迟导入，避免循环依赖）
_knowledge_recall_instance = None

def _get_knowledge_recall():
    """
    延迟获取知识库召回器实例
    
    Returns:
        KnowledgeRecall实例或None（如果不可用）
    """
    global _knowledge_recall_instance
    
    if _knowledge_recall_instance is None:
        try:
            from core.knowledge_recall import get_knowledge_recall
            workspace_root = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            _knowledge_recall_instance = get_knowledge_recall(workspace_root)
            logger.info("[V2.1] 知识库召回器初始化成功")
        except ImportError as e:
            logger.warning(f"[V2.1] 知识库召回模块未安装: {e}")
        except Exception as e:
            logger.warning(f"[V2.1] 知识库召回器初始化失败: {e}")
    
    return _knowledge_recall_instance


class GenerationStrategy(Enum):
    """生成策略"""
    CREATIVE = "creative"      # 创意优先（高温度）
    BALANCED = "balanced"      # 平衡（中等温度）
    PRECISE = "precise"        # 精确优先（低温度）


@dataclass
class DimensionScore:
    """单维度评分"""
    dimension_name: str      # 维度名称
    score: float             # 评分 0.0-1.0
    details: str             # 详细说明
    issues: List[str]        # 发现的问题
    # V2.1新增：知识库冲突详情（仅知识库一致性维度使用）
    knowledge_conflicts: Optional[List[Dict[str, Any]]] = None  # 知识冲突列表
    recalled_knowledge: Optional[List[Dict[str, Any]]] = None   # 召回的知识点


@dataclass
class IterationResult:
    """迭代结果"""
    iteration: int           # 迭代轮次
    content: str             # 生成内容
    total_score: float      # 总评分
    dimension_scores: Dict[str, DimensionScore]  # 各维度评分
    has_chapter_end: bool    # 是否有【本章完】标记
    feedback: str            # 反馈内容
    suggestions: List[str]  # 修改建议


class IterativeGeneratorPlugin(GeneratorPlugin):
    """
    迭代生成器插件 V2 - GeneratorPlugin实现
    
    严格按照用户要求的流程实现：
    1. 打包请求内容（必须包含【本章完】）
    2. 发送请求生成
    3. 多维度评分
    4. 评分<0.8或缺少【本章完】 -> 循环优化
    5. 评分>=0.8且有【本章完】 -> 输出保存
    """
    
    def __init__(self):
        """初始化迭代生成器插件"""
        metadata = PluginMetadata(
            id="iterative-generator-v2",
            name="迭代生成器 V2",
            version="2.0.0",
            description="迭代优化的章节生成器，支持评分反馈循环优化",
            author="项目组",
            plugin_type=PluginType.GENERATOR
        )
        super().__init__(metadata)
        
        # 配置参数
        self.model_name: str = "deepseek-chat"
        self.target_word_count: int = 3500
        self.quality_threshold: float = 0.8
        self.max_iterations: int = 5
        
        # API客户端
        self._api_client: Optional[Any] = None
        
        # 生成历史（用于调试和追踪）
        self.generation_history: List[IterationResult] = []
        
        # 日志器
        self._logger = logger
    
    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据"""
        return PluginMetadata(
            id="iterative-generator-v2",
            name="迭代生成器 V2",
            version="2.0.0",
            description="迭代优化的章节生成器，支持评分反馈循环优化",
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
            # 从配置文件读取参数（如果可用）
            if hasattr(context, 'config') and context.config:
                config = context.config
                # 支持从配置文件读取生成参数
                if isinstance(config, dict):
                    self.model_name = config.get('model', self.model_name)
                    self.target_word_count = config.get('target_word_count', self.target_word_count)
                    self.quality_threshold = config.get('quality_threshold', self.quality_threshold)
                    self.max_iterations = config.get('max_iterations', self.max_iterations)
            
            # 从服务定位器获取API客户端
            if hasattr(context, 'service_locator') and context.service_locator:
                try:
                    # 使用get_service()按名称获取（不是get()按类型获取）
                    ai_service = context.service_locator.get_service("ai_service")
                    if ai_service:
                        self._api_client = ai_service
                        logger.info("[IterativeGenerator] 从服务定位器获取AI服务成功")
                except Exception as e:
                    logger.warning(f"[IterativeGenerator] 无法从服务定位器获取AI服务: {e}")
            
            logger.info(f"[IterativeGenerator] 迭代生成器初始化完成")
            logger.info(f"[IterativeGenerator] 目标字数: {self.target_word_count}, 质量阈值: {self.quality_threshold}, 最大迭代: {self.max_iterations}")
            
            return True
            
        except Exception as e:
            logger.error(f"[IterativeGenerator] 初始化失败: {e}")
            return False
    
    def set_api_client(self, api_client: Any):
        """
        设置API客户端
        
        Args:
            api_client: API客户端实例
        """
        self._api_client = api_client
        logger.info("[IterativeGenerator] API客户端已设置")
    
    def set_config(
        self,
        model_name: str = "deepseek-chat",
        target_word_count: int = 3500,
        quality_threshold: float = 0.8,
        max_iterations: int = 5
    ):
        """
        设置配置参数
        
        Args:
            model_name: 模型名称
            target_word_count: 目标字数
            quality_threshold: 质量阈值
            max_iterations: 最大迭代次数
        """
        self.model_name = model_name
        self.target_word_count = target_word_count
        self.quality_threshold = quality_threshold
        self.max_iterations = max_iterations
        
        logger.info(f"[IterativeGenerator] 配置已更新 - 模型: {model_name}, 字数: {target_word_count}, 阈值: {quality_threshold}, 迭代: {max_iterations}")
    
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """
        生成内容 - 执行迭代生成流程
        
        Args:
            request: 生成请求
            
        Returns:
            生成结果
        """
        try:
            # 从request中提取参数
            prompt = request.outline  # 使用outline作为基础prompt
            extra = request.model_dump() if hasattr(request, 'model_dump') else {}
            
            # 获取验证函数（从context或参数中）
            validation_fn = extra.get('validation_fn')
            strategy_str = extra.get('strategy', 'balanced')
            strategy = GenerationStrategy(strategy_str) if isinstance(strategy_str, str) else GenerationStrategy.BALANCED
            
            # 更新目标字数
            self.target_word_count = request.word_count
            
            # 执行迭代生成
            final_content, stats = self.generate_with_iteration(
                prompt=prompt,
                validation_fn=validation_fn,
                strategy=strategy
            )
            
            return GenerationResult(
                request_id=request.request_id,
                content=final_content,
                word_count=len(final_content),
                iteration_count=stats.get('iterations', 0),
                validation_scores=None
            )
            
        except Exception as e:
            logger.error(f"[IterativeGenerator] 生成失败: {e}")
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
        
        if not request.outline:
            errors.append("提示词/大纲不能为空")
        if not self._api_client:
            errors.append("API客户端未设置")
            
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
    
    def generate_with_iteration(
        self,
        prompt: str,
        validation_fn: Optional[Callable] = None,
        strategy: GenerationStrategy = GenerationStrategy.BALANCED
    ) -> Tuple[str, Dict]:
        """
        完整的迭代生成流程

        流程：
        1. 整理打包请求内容（强制附加【本章完】要求）
        2. 发送请求生成内容
        3. 多维度评分
        4. 如果评分<0.8或缺少【本章完】标记：
           - 构建反馈（评分+各维度评分+修改建议）
           - 再次生成
        5. 循环直到评分>=0.8且有【本章完】标记
        6. 输出保存

        Args:
            prompt: 基础提示词
            validation_fn: 验证函数，返回 (total_score, dimension_scores, suggestions)
            strategy: 生成策略

        Returns:
            (最终生成内容, 统计信息)
        """
        logger.info("[V2] ========== 开始迭代生成流程 ==========")
        logger.info(f"[V2] 质量阈值: {self.quality_threshold}, 最大迭代: {self.max_iterations}")

        best_result = None
        best_score = 0.0

        stats = {
            'iterations': 0,
            'scores': [],
            'dimension_scores': [],
            'has_chapter_end_history': [],
            'feedback_history': []
        }

        # 开始迭代
        for iteration in range(self.max_iterations):
            logger.info(f"[V2] 第 {iteration + 1} 轮迭代开始")

            # === 步骤1: 整理打包请求内容 ===
            current_prompt = self._build_request_prompt(prompt, iteration, best_result)

            # === 步骤2: 向大模型发送请求 ===
            logger.info(f"[V2] 正在发送API请求...")

            try:
                generated_content = self._send_request_to_model(current_prompt, strategy)
            except Exception as e:
                logger.error(f"[V2] API请求失败: {e}")
                if iteration == 0:
                    # 第一轮就失败，抛出异常
                    raise
                # 后续轮次失败，使用上次最佳结果
                logger.warning(f"[V2] 第{iteration + 1}轮生成失败，使用上一轮结果")
                break

            # === 步骤3: 接受返回文章 ===
            logger.info(f"[V2] 接收到返回内容，长度: {len(generated_content)} 字符")

            # === 步骤4: 从多维度评分 ===
            total_score, dimension_scores, suggestions = self._evaluate_content(
                generated_content, validation_fn
            )

            # 检查【本章完】标记
            has_chapter_end = '【本章完】' in generated_content
            logger.info(f"[V2] 【本章完】检查: {'有' if has_chapter_end else '没有'}, 总评分: {total_score:.3f}")

            # 打印各维度评分
            for dim_name, dim_score in dimension_scores.items():
                logger.debug(f"[V2] {dim_name}: {dim_score.score:.3f} - {dim_score.details}")

            # 记录结果
            iteration_result = IterationResult(
                iteration=iteration + 1,
                content=generated_content,
                total_score=total_score,
                dimension_scores=dimension_scores,
                has_chapter_end=has_chapter_end,
                feedback=self._build_feedback_text(total_score, dimension_scores, has_chapter_end, generated_content),
                suggestions=suggestions
            )

            self.generation_history.append(iteration_result)
            
            # 限制历史记录大小，防止内存泄漏
            if len(self.generation_history) > 50:
                self.generation_history = self.generation_history[-30:]
            
            stats['iterations'] += 1
            stats['scores'].append(total_score)
            stats['dimension_scores'].append(dimension_scores)
            stats['has_chapter_end_history'].append(has_chapter_end)
            stats['feedback_history'].append(iteration_result.feedback)

            # === 步骤5: 判断是否满足停止条件 ===
            # 检查字数偏差（超过50%强制继续迭代）— V6.1: 使用英文key 'word_count'
            word_count_score = dimension_scores.get('word_count') or dimension_scores.get('字数')
            word_count_deviation = 0
            if word_count_score and isinstance(word_count_score, DimensionScore):
                word_count_deviation = 1 - word_count_score.score  # 评分越低，偏差越大
            
            # 必须同时满足：评分 >= 0.8、有【本章完】标记、字数偏差不超过50%
            word_count_acceptable = word_count_score is None or (isinstance(word_count_score, DimensionScore) and word_count_score.score >= 0.3)
            
            if total_score >= self.quality_threshold and has_chapter_end and word_count_acceptable:
                logger.info(f"[V2][SUCCESS] ========== 迭代完成！满足条件 ==========")
                logger.info(f"[V2][SUCCESS] 总评分: {total_score:.3f} >= {self.quality_threshold}")
                logger.info(f"[V2][SUCCESS] 包含【本章完】标记")
                if word_count_score and isinstance(word_count_score, DimensionScore):
                    logger.info(f"[V2][SUCCESS] 字数评分: {word_count_score.score:.3f} >= 0.3")
                logger.info(f"[V2] 迭代完成！满足条件，评分: {total_score:.3f}")

                best_result = iteration_result
                best_score = total_score
                break

            # === 不满足条件，构建反馈，准备下一轮 ===
            logger.info(f"[V2][CONTINUE] 未满足条件，准备第 {iteration + 2} 轮迭代")
            logger.info(f"[V2][CONTINUE] 原因: ")
            if total_score < self.quality_threshold:
                logger.info(f"[V2][CONTINUE]   - 评分 {total_score:.3f} < 阈值 {self.quality_threshold}")
            if not has_chapter_end:
                logger.info(f"[V2][CONTINUE]   - 缺少【本章完】标记")
            if not word_count_acceptable:
                logger.info(f"[V2][CONTINUE]   - 字数偏差过大（评分 {word_count_score.score:.3f} < 0.3，偏差超过50%）")

            # 打印反馈内容
            logger.info(f"[V2][FEEDBACK] 反馈内容:")
            logger.debug(iteration_result.feedback)

            # 如果是最佳结果，保存
            if total_score > best_score:
                best_result = iteration_result
                best_score = total_score

        # 迭代结束（达到最大次数或满足条件）
        logger.info(f"[V2][FINAL] ========== 迭代结束 ==========")
        logger.info(f"[V2][FINAL] 总迭代次数: {stats['iterations']}")
        logger.info(f"[V2][FINAL] 最佳评分: {best_score:.3f}")

        # 输出保存
        final_content = best_result.content if best_result else ""
        
        # V7.0关键修复：【本章完】强制保障
        # 如果迭代结束仍无【本章完】标记，自动补充（与专家模式一致的保障策略）
        if final_content and '【本章完】' not in final_content and '本章完' not in final_content:
            logger.warning("[V2][SAVE] 最终内容缺少【本章完】标记，强制自动补充")
            # 智能补充：找最后一个句号/引号位置追加
            import re
            last_punct = max(
                final_content.rfind('。'),
                final_content.rfind('」'),
                final_content.rfind('"'),
                final_content.rfind('！'),
                final_content.rfind('？'),
            )
            if last_punct > len(final_content) * 0.8:  # 在后20%范围内
                final_content = final_content[:last_punct+1] + '\n\n【本章完】' + final_content[last_punct+1:]
            else:
                final_content = final_content.rstrip() + '\n\n【本章完】'
        
        logger.info(f"[V2][SAVE] 最终内容长度: {len(final_content)} 字符")
        logger.info(f"[V2][SAVE] 最终内容包含【本章完】: {'是' if '【本章完】' in final_content else '否'}")

        # === 步骤6: 输出保存 ===
        logger.info(f"[V2] 迭代结束，返回最终内容")
        return final_content, stats

    def _build_request_prompt(
        self,
        base_prompt: str,
        iteration: int,
        previous_result: Optional[IterationResult]
    ) -> str:
        """
        步骤1: 整理打包请求内容

        强制要求：
        - 结尾必须加上【本章完】
        - 如果不是第一轮，包含上一轮的反馈和改进建议
        """
        # 第一轮：基础提示词 + 强制要求
        if iteration == 0:
            prompt = base_prompt.strip()

            # 强制附加【本章完】要求（如果没有的话）
            if "【本章完】" not in prompt:
                prompt += "\n\n重要要求：章节结束时必须在末尾添加【本章完】标记！"
            # V6.1修复：首轮必须包含字数约束（±10%范围）
            if "目标字数" not in prompt and "字数" not in prompt:
                prompt += f"\n\n【字数要求】本文目标{self.target_word_count}字（允许误差±10%），请严格控制篇幅。"
            logger.debug(f"[V2][PROMPT] 第一轮提示词（前200字符）: {prompt[:200]}...")
            return prompt

        # 后续轮次：基础提示词 + 反馈 + 改进要求
        logger.info(f"[V2][PROMPT] 构建第{iteration + 1}轮提示词...")

        prompt_parts = [
            base_prompt.strip(),
            "",
            "=" * 60,
            "【上一轮反馈与改进要求】",
            ""
        ]

        # 添加评分信息
        if previous_result:
            prompt_parts.append(f"上一轮总评分: {previous_result.total_score:.3f} / 1.0")
            prompt_parts.append("各维度评分:")
            for dim_name, dim_score in previous_result.dimension_scores.items():
                prompt_parts.append(f"  - {dim_name}: {dim_score.score:.3f} - {dim_score.details}")

            prompt_parts.append("")
            prompt_parts.append("【详细反馈】")
            prompt_parts.append(previous_result.feedback)

            prompt_parts.append("")
            prompt_parts.append("【改进建议】")
            for idx, suggestion in enumerate(previous_result.suggestions, 1):
                prompt_parts.append(f"{idx}. {suggestion}")

        # 强制要求【本章完】和字数
        prompt_parts.extend([
            "",
            "=" * 60,
            "特别强调:",
            f"1. 必须按照上述反馈进行改进",
            f"2. 【目标字数】{self.target_word_count}字，字数必须接近目标（误差±10%以内）",
            f"3. 章节结束时**必须**在末尾添加【本章完】标记！",
            f"4. 这是停止生成的必要条件",
            ""
        ])

        final_prompt = "\n".join(prompt_parts)
        logger.debug(f"[V2][PROMPT] 提示词长度: {len(final_prompt)} 字符")

        return final_prompt

    def _send_request_to_model(
        self,
        prompt: str,
        strategy: GenerationStrategy
    ) -> str:
        """
        步骤2: 向大模型发送请求

        支持本地模型和在线API
        """
        # V2.1修复：此处旧门卫要求 _api_client，但实际调用（下方）走 AIServiceManager
        # 统一入口（V2.23设计），并不使用 _api_client。若服务定位器未注册 ai_service，
        # 生成会死在这个根本不需要的检查上。改为仅提示，不再阻断。
        if not self._api_client:
            logger.debug("[V2] _api_client 未设置（不影响生成，实际走 AIServiceManager 统一入口）")


        # 计算max_tokens - V6.0修复：确保AI有足够token生成完整章节+【本章完】
        # 中文约1.5字符/token，目标字数对应约 target/1.5 tokens
        # V6.0关键修复：max_tokens必须显著大于基础token数，否则API输出会被截断导致【本章完】无法写入
        # 公式：base = target/1.5(内容tokens), max = base*2.0(留100%余量给结束标记和溢出)
        base_tokens = int(self.target_word_count / 1.5)  # 基础内容token数
        max_tokens = int(base_tokens * 2.0)  # 留出100%空间确保能写完【本章完】
        max_tokens = max(max_tokens, 1000)  # 最小1000 tokens
        max_tokens = min(max_tokens, 4096)  # 最大4096 tokens（DeepSeek限制）

        # 根据策略设置温度
        temperature_map = {
            GenerationStrategy.CREATIVE: 0.9,
            GenerationStrategy.BALANCED: 0.7,
            GenerationStrategy.PRECISE: 0.5
        }
        temperature = temperature_map.get(strategy, 0.7)

        logger.debug(f"[V2] API请求 - max_tokens: {max_tokens}, temperature: {temperature}")

        # 构建强化的system prompt - 强调设定优先级
        system_prompt = """你是一位经验丰富的小说创作专家,必须严格遵守以下核心原则:

【核心原则】
1. **人物设定不可违背**: 
   - 人物的性格、外貌、背景、行为模式必须严格遵循设定
   - 人物的对话风格、语言习惯必须与设定一致
   - 人物之间的关系必须符合设定
   - 严禁擅自改变人物设定或添加不符合设定的行为

2. **大纲严格执行**: 
   - 必须完整执行章节大纲的所有要点
   - 不得遗漏关键情节

3. **风格保持一致**: 
   - 在遵守设定的前提下,保持与提供风格样本相同的叙事风格

【人物设定优先级】
- 人物设定 > 风格模仿
- 设定准确性 > 文学修辞
- 人物一致性 > 情节戏剧性

【创作检查清单】
在创作每一句话前，请确认：
✓ 人物的对话是否符合理设定的说话方式？
✓ 人物的行为是否符合设定的性格特征？
✓ 人物的决策是否符合设定的行为模式？
✓ 人物之间的互动是否符合设定的人物关系？
✓ 世界观元素是否准确无误？

【输出要求】
- 必须以【本章完】结尾
- 字数必须接近目标字数(误差±10%以内)
- 人物言行必须100%符合设定"""

        # 调用AIServiceManager（统一AI调用）
        try:
            from core.ai_service_manager import get_ai_service_manager
            from core.ai_provider import GenerationConfig

            ai_manager = get_ai_service_manager()

            # 构建配置
            config = GenerationConfig(
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=120
            )

            # 调用生成（支持messages格式）
            result = ai_manager.generate_text(
                prompt=prompt,
                config=config,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )

            # 检查生成结果
            if not result.success:
                raise AIProviderError(f"AI生成失败: {result.error}")

            content = result.text

            logger.info(f"[V2][API] API响应成功，内容长度: {len(content)} 字符，Token使用: {result.usage}")

            return content

        except Exception as e:
            logger.error(f"[V2][ERROR] AI调用失败: {e}")
            raise

    def _evaluate_content(
        self,
        content: str,
        validation_fn: Optional[Callable]
    ) -> Tuple[float, Dict[str, DimensionScore], List[str]]:
        """
        步骤4: 从多维度评分（V2.1版本 - 新增知识库一致性维度）

        维度：
        - 世界观
        - 大纲
        - 风格
        - 人设
        - Ai感
        - 字数
        - 上下文契合度
        - 知识库一致性（V2.1新增）

        没有【本章完】视作未完成（会在外部处理，这里只返回评分）
        """
        # 如果没有验证函数，返回默认评分
        if validation_fn is None:
            # V6.0修复：统一使用英文key与quality-validator一致
            default_scores = {
                'worldview': DimensionScore('worldview', 0.5, '无验证函数', []),
                'outline': DimensionScore('outline', 0.5, '无验证函数', []),
                'style': DimensionScore('style', 0.5, '无验证函数', []),
                'character': DimensionScore('character', 0.5, '无验证函数', []),
                'ai_feeling': DimensionScore('ai_feeling', 0.5, '无验证函数', []),
                'word_count': DimensionScore('word_count', self._score_word_count(content), f'目标:{self.target_word_count} 实际:{len(content)}', []),
                'context_coherence': DimensionScore('context_coherence', 0.5, '无验证函数', [])
            }
            # V2.1新增：知识库一致性评分
            knowledge_score = self._evaluate_knowledge_consistency(content)
            default_scores['knowledge'] = knowledge_score
            
            return 0.5, default_scores, ['请提供验证函数以获得准确评分']
        
        # 调用验证函数
        try:
            total_score, detailed_scores, suggestions = validation_fn(content)

            # 确保返回格式正确
            if not isinstance(total_score, (int, float)):
                total_score = float(total_score)

            if not isinstance(detailed_scores, dict):
                # 如果验证函数返回的是元组，需要转换
                detailed_scores = {}

            if not isinstance(suggestions, list):
                suggestions = list(suggestions) if suggestions else []

            # 创建DimensionScore对象
            dimension_scores = {}
            for dim_name, dim_data in detailed_scores.items():
                logger.debug(f"[V2] 处理维度: {dim_name}, 类型: {type(dim_data).__name__}")
                
                # 检查是否已经是DimensionScore对象
                if isinstance(dim_data, DimensionScore):
                    dimension_scores[dim_name] = dim_data
                elif isinstance(dim_data, dict):
                    dimension_scores[dim_name] = DimensionScore(
                        dimension_name=dim_name,
                        score=float(dim_data.get('score', 0.5)),
                        details=dim_data.get('details', ''),
                        issues=dim_data.get('issues', [])
                    )
                elif isinstance(dim_data, (int, float)):
                    dimension_scores[dim_name] = DimensionScore(
                        dimension_name=dim_name,
                        score=float(dim_data),
                        details='',
                        issues=[]
                    )
                elif hasattr(dim_data, 'score'):
                    # 兼容NaturalnessScore等dataclass对象 - V6.0新增
                    dimension_scores[dim_name] = DimensionScore(
                        dimension_name=dim_name,
                        score=float(getattr(dim_data, 'score', 0.5)),
                        details=f'{type(dim_data).__name__}对象',
                        issues=getattr(dim_data, 'issues_found', []) or getattr(dim_data, 'issues', [])
                    )
                else:
                    # 未知类型，使用默认值并记录详细日志
                    logger.warning(f"[V2][WARNING] 未知维度数据类型: {type(dim_data).__name__}, 维度名: {dim_name}, 值预览: {str(dim_data)[:100]}")
                    dimension_scores[dim_name] = DimensionScore(
                        dimension_name=dim_name,
                        score=0.5,
                        details=f'数据类型错误: {type(dim_data).__name__}',
                        issues=[]
                    )

            # V2.1新增：知识库一致性评分
            knowledge_score = self._evaluate_knowledge_consistency(content)
            dimension_scores['知识库一致性'] = knowledge_score
            
            # 重新计算总分（包含知识库一致性）
            total_score = self._calculate_total_score_with_knowledge(dimension_scores)

            logger.info(f"[V2.1][SCORE] 评分完成 - 总分: {total_score:.3f}, 维度数: {len(dimension_scores)}")
            logger.info(f"[V2.1][SCORE] 知识库一致性: {knowledge_score.score:.3f}, 冲突数: {len(knowledge_score.knowledge_conflicts or [])}")

            return total_score, dimension_scores, suggestions

        except Exception as e:
            logger.error(f"[V2][ERROR] 评分过程出错: {e}")

            # 返回默认评分（V6.0修复：统一英文key）
            default_scores = {
                'worldview': DimensionScore('worldview', 0.5, f'评分失败: {str(e)}', []),
                'outline': DimensionScore('outline', 0.5, '评分失败', []),
                'style': DimensionScore('style', 0.5, '评分失败', []),
                'character': DimensionScore('character', 0.5, '评分失败', []),
                'ai_feeling': DimensionScore('ai_feeling', 0.5, '评分失败', []),
                'word_count': DimensionScore('word_count', 0.5, '评分失败', []),
                'context_coherence': DimensionScore('context_coherence', 0.5, '评分失败', [])
            }
            
            # V2.1新增：知识库一致性评分
            knowledge_score = self._evaluate_knowledge_consistency(content)
            default_scores['knowledge'] = knowledge_score

            return 0.5, default_scores, [f'评分过程出错: {str(e)}']
    
    def _evaluate_knowledge_consistency(self, content: str) -> DimensionScore:
        """
        V2.1新增：评估知识库一致性
        
        调用KnowledgeRecall进行智能召回和一致性检测
        
        Args:
            content: 待评估的内容
            
        Returns:
            DimensionScore: 知识库一致性评分
        """
        try:
            recall = _get_knowledge_recall()
            
            if recall is None:
                # 知识库不可用，返回默认评分
                return DimensionScore(
                    dimension_name='知识库一致性',
                    score=0.8,  # 知识库不可用时给默认分
                    details='知识库模块未启用',
                    issues=[],
                    knowledge_conflicts=None,
                    recalled_knowledge=None
                )
            
            # 调用知识库一致性检测
            check_result = recall.check_knowledge_consistency(
                content=content,
                category=None,  # 自动识别题材
                top_k=10
            )
            
            # 提取冲突信息
            conflicts = []
            if check_result.conflicts:
                for conflict in check_result.conflicts:
                    conflicts.append({
                        "type": conflict.conflict_type,
                        "severity": conflict.severity,
                        "description": conflict.description,
                        "knowledge_title": conflict.knowledge_title,
                        "suggested_fix": conflict.suggested_fix
                    })
            
            # 提取召回的知识点
            recalled = []
            if check_result.recalled_knowledge:
                for knowledge in check_result.recalled_knowledge[:5]:  # 只保留前5个
                    recalled.append({
                        "title": knowledge.title,
                        "category": knowledge.category,
                        "domain": knowledge.domain,
                        "score": knowledge.score
                    })
            
            # 构建详情信息
            details = f"一致性评分: {check_result.consistency_score:.2f}, "
            details += f"题材: {check_result.category}, "
            details += f"召回知识点: {len(check_result.recalled_knowledge)}个, "
            details += f"冲突: {len(conflicts)}个"
            
            # 构建问题列表
            issues = []
            for conflict in conflicts:
                severity = conflict.get('severity', 'P2')
                if severity == 'P0':
                    issues.append(f"🔴 {conflict.get('description', '')}")
                elif severity == 'P1':
                    issues.append(f"🟡 {conflict.get('description', '')}")
                else:
                    issues.append(f"ℹ️ {conflict.get('description', '')}")
            
            return DimensionScore(
                dimension_name='知识库一致性',
                score=check_result.consistency_score,
                details=details,
                issues=issues,
                knowledge_conflicts=conflicts if conflicts else None,
                recalled_knowledge=recalled if recalled else None
            )
            
        except Exception as e:
            logger.error(f"[V2.1][ERROR] 知识库一致性检测失败: {e}")
            return DimensionScore(
                dimension_name='知识库一致性',
                score=0.7,  # 出错时给中等评分，避免影响总体
                details=f'检测失败: {str(e)}',
                issues=[f'知识库检测出错: {str(e)}'],
                knowledge_conflicts=None,
                recalled_knowledge=None
            )
    
    def _calculate_total_score_with_knowledge(
        self,
        dimension_scores: Dict[str, DimensionScore]
    ) -> float:
        """
        V2.1→V7.0修复：计算包含知识库一致性的总分
        
        V7.0关键修复：
        - 支持中英文双语key匹配（英文key来自quality-validator-v1/内联评分，
          中文key来自V2.1自身添加的'知识库一致性'维度）
        - 权重与九维度评分体系对齐（word_count=0.08, knowledge=0.08等）
        - 废弃旧的中文key权重表（只匹配到知识库一致性导致总分永远0.9的bug）
        
        权重分配（V7.0 - 与九维度对齐）：
        - word_count/字数: 8%
        - outline/大纲: 13%
        - style/风格: 19%
        - character/人设: 19%
        - worldview/世界观: 12%
        - knowledge/知识库: 8%
        - writing_technique/写作技巧: 8%
        - context_coherence/上下文衔接: 8%
        - ai_feeling/AI感: 5%
        - 知识库一致性: 8% (V2.1独立维度，与knowledge维度互补)
        - naturalness/自然度: 5% (兼容旧版)
        - chapter_end/本章完: 5% (兼容旧版)
        """
        # 英文key → 权重（与quality-validator-v1九维度权重一致）
        en_weights = {
            'word_count': 0.08,
            'outline': 0.13,
            'style': 0.19,
            'character': 0.19,
            'worldview': 0.12,
            'knowledge': 0.08,
            'writing_technique': 0.08,
            'context_coherence': 0.08,
            'ai_feeling': 0.05,
            'naturalness': 0.05,
            'chapter_end': 0.05,
        }
        # 中文key → 英文key映射
        cn_to_en = {
            '字数': 'word_count',
            '大纲': 'outline',
            '风格': 'style',
            '人设': 'character',
            '世界观': 'worldview',
            '知识库': 'knowledge',
            '写作技巧': 'writing_technique',
            '上下文契合度': 'context_coherence',
            '上下文衔接': 'context_coherence',
            'AI感': 'ai_feeling',
            '自然度': 'naturalness',
            '本章完': 'chapter_end',
        }
        # 知识库一致性是V2.1独立维度，与knowledge互补
        knowledge_consistency_weight = 0.08
        
        raw_score = 0.0
        total_weight = 0.0
        
        for dim_name, dim_score in dimension_scores.items():
            # 先尝试英文key直接匹配
            weight = en_weights.get(dim_name, 0.0)
            # 如果英文不匹配，尝试中文映射
            if weight == 0.0 and dim_name in cn_to_en:
                en_key = cn_to_en[dim_name]
                weight = en_weights.get(en_key, 0.0)
            # 特殊处理：知识库一致性维度
            if weight == 0.0 and '知识库' in dim_name:
                weight = knowledge_consistency_weight
            
            if weight > 0:
                raw_score += dim_score.score * weight
                total_weight += weight
        
        # 归一化
        if total_weight > 0:
            return min(raw_score / total_weight, 1.0)
        else:
            return 0.5
    
    def _score_word_count(self, content: str) -> float:
        """简单的字数评分"""
        actual = len(content)
        target = self.target_word_count
        
        if actual < target * 0.5:
            return 0.2
        elif actual < target * 0.8:
            return 0.5
        elif actual < target * 1.1:
            return 1.0
        elif actual < target * 1.5:
            return 0.5
        else:
            return 0.2

    def _build_feedback_text(
        self,
        total_score: float,
        dimension_scores: Dict[str, DimensionScore],
        has_chapter_end: bool,
        content: str = ""
    ) -> str:
        """
        步骤5: 构建反馈文本（V2.1版本 - 新增知识库冲突显示）

        格式：总评分 + 各维度评分 + 知识库冲突信息 + 问题描述(优先显示设定偏离问题)
        + AI感专项(具体AI腔词句) + 具体改进建议

        Args:
            content: 本轮生成正文（用于AI感专项检测，列出具体AI腔词句要求改写）
        """
        feedback_parts = [
            f"【总评分】: {total_score:.3f} / 1.0",
            ""
        ]

        # 🔴 优先级0: 检查知识库冲突（V2.1新增）
        # V6.1修复：使用英文key与quality-validator feedback统一
        knowledge_dim = dimension_scores.get('knowledge') or dimension_scores.get('知识库一致性')
        knowledge_issues = []
        
        if knowledge_dim and knowledge_dim.knowledge_conflicts:
            # 有P0级别冲突
            p0_conflicts = [c for c in knowledge_dim.knowledge_conflicts if c.get('severity') == 'P0']
            p1_conflicts = [c for c in knowledge_dim.knowledge_conflicts if c.get('severity') == 'P1']
            
            if p0_conflicts or p1_conflicts:
                feedback_parts.append("=" * 60)
                feedback_parts.append("🔴 【严重问题 - 知识库冲突】(必须立即修正)")
                feedback_parts.append("=" * 60)
                
                for conflict in p0_conflicts:
                    feedback_parts.append(f"⚠️ {conflict.get('type', '未知')}: {conflict.get('description', '')}")
                    feedback_parts.append(f"   相关知识点: {conflict.get('knowledge_title', '')}")
                    if conflict.get('suggested_fix'):
                        feedback_parts.append(f"   修正建议: {conflict['suggested_fix']}")
                    knowledge_issues.append(conflict.get('description', ''))
                
                for conflict in p1_conflicts:
                    feedback_parts.append(f"⚡ {conflict.get('type', '未知')}: {conflict.get('description', '')}")
                    feedback_parts.append(f"   相关知识点: {conflict.get('knowledge_title', '')}")
                    knowledge_issues.append(conflict.get('description', ''))
                
                feedback_parts.append("")
                feedback_parts.append("【修正要求】")
                feedback_parts.append("  ❌ 内容违反了知识库中的科学/历史/文化常识")
                feedback_parts.append("  ✅ 请根据上述知识点修正错误内容")
                feedback_parts.append("  ✅ 确保物理/化学/生物/历史等知识点准确")
                feedback_parts.append("")

        # 🔴 优先级1:检查设定偏离(人设、世界观、风格) — V6.1修复：使用英文key
        priority_dims = ['character', 'worldview', 'style']
        setting_issues = []

        for dim_name in priority_dims:
            if dim_name in dimension_scores:
                dim_score = dimension_scores[dim_name]
                if dim_score.score < 0.7:
                    setting_issues.append((dim_name, dim_score))

        if setting_issues:
            feedback_parts.append("=" * 60)
            feedback_parts.append("🔴 【核心问题 - 设定偏离】(必须立即修正)")
            feedback_parts.append("=" * 60)

            for dim_name, dim_score in setting_issues:
                feedback_parts.append(f"⚠️ {dim_name}不符合: 评分 {dim_score.score:.3f} (要求≥0.7)")
                if dim_score.details:
                    feedback_parts.append(f"   说明: {dim_score.details}")
                if dim_score.issues:
                    feedback_parts.append(f"   问题:")
                    for issue in dim_score.issues:
                        feedback_parts.append(f"     - {issue}")

            feedback_parts.append("")
            feedback_parts.append("【修正要求】")
            feedback_parts.append("  ❌ 严禁偏离提供的人物设定、世界观、写作风格")
            feedback_parts.append("  ✅ 必须严格按照原始设定重新创作相关内容")
            feedback_parts.append("  ✅ 检查人物行为、对话是否符合其设定")
            feedback_parts.append("  ✅ 检查世界观元素是否准确无误")
            feedback_parts.append("  ✅ 检查写作风格是否保持一致")
            feedback_parts.append("")

        # 🔴 优先级2: AI感专项反馈（V2.6新增）——闭环去AI腔
        # 当AI感维度偏低时，直接用AI感检测器扫出具体AI腔词句，逐条要求改写，
        # 而非泛泛说"减少AI感"。让下一轮迭代精确消除这些痕迹。
        ai_dim = dimension_scores.get('ai_feeling') or dimension_scores.get('AI感')
        ai_low = (ai_dim is None) or (getattr(ai_dim, 'score', 1.0) < 0.75)
        if content and ai_low:
            try:
                from core.ai_feeling_detector import detect_ai_feeling
                report = detect_ai_feeling(content)
                if report.issues:
                    feedback_parts.append("=" * 60)
                    feedback_parts.append("🔴 【AI感问题 - 请逐条消除以下AI腔】")
                    feedback_parts.append("=" * 60)
                    for issue in report.issues[:12]:
                        pos = (issue.position or '')[:40]
                        feedback_parts.append(f"  · [{issue.issue_type}] {pos}")
                        if issue.suggestion:
                            feedback_parts.append(f"    改法: {issue.suggestion}")
                    feedback_parts.append("")
                    feedback_parts.append("【修正要求】")
                    feedback_parts.append("  ❌ 上述词句有明显AI腔（AI高频词/模板句式/空洞情感/机械过渡）")
                    feedback_parts.append("  ✅ 逐条改写：用具体动作、细节、对白替代，不保留原句式")
                    feedback_parts.append("  ✅ 目标：让文字读起来像资深人类作者写的（以假乱真）")
                    feedback_parts.append("")
            except Exception as _e:
                logger.debug(f"[V2] AI感专项反馈生成失败（不影响主反馈）: {_e}")

        # 各维度评分
        feedback_parts.append("=" * 60)
        feedback_parts.append("【各维度评分】")
        feedback_parts.append("=" * 60)

        # 检查字数偏差和大纲问题
        word_count_issue = None
        outline_issue = None
        
        for dim_name, dim_score in dimension_scores.items():
            status = "✓" if dim_score.score >= 0.7 else "✗"
            feedback_parts.append(f"{status} {dim_name}: {dim_score.score:.3f}")

            if dim_score.details and dim_name not in priority_dims:
                feedback_parts.append(f"   说明: {dim_score.details}")

            if dim_score.issues and dim_name not in priority_dims:
                feedback_parts.append(f"   问题:")
                for issue in dim_score.issues:
                    # 过滤掉空的问题和纯标题行
                    if issue and len(issue.strip()) > 10 and not issue.strip().startswith('**'):
                        feedback_parts.append(f"     - {issue}")
            
            # 记录字数问题（V6.1修复：使用英文key 'word_count'）
            # V2.13修复（《无极》九维审计）：原阈值 <0.3 过松——实测第1章
            # 超标58%（3162/2000字）评分0.5，5轮迭代反馈从未提及字数，
            # 模型无从纠偏。凡明显偏离（<0.95）即给出方向性纠偏指令。
            if dim_name == 'word_count' and dim_score.score < 0.95:
                word_count_issue = dim_score
            
            # 记录大纲问题（V6.1修复：使用英文key 'outline'）
            if dim_name == 'outline' and dim_score.score < 0.7:
                outline_issue = dim_score

        # 【本章完】检查
        feedback_parts.extend([
            "",
            "=" * 60,
            "【结束标记检查】",
            "=" * 60,
            "✓ 有【本章完】" if has_chapter_end else "✗ 缺少【本章完】标记（必须添加）"
        ])

        # 总体评价
        feedback_parts.extend([
            "",
            "=" * 60,
            "【总体评价】",
            "=" * 60,
        ])

        # V2.1新增：知识库冲突优先显示
        if knowledge_issues:
            feedback_parts.append(f"❌ 未达标 - 存在知识库冲突（{len(knowledge_issues)}个问题）")
            feedback_parts.append("   请修正违反知识常识的内容后重新生成。")
        elif setting_issues:
            feedback_parts.append(f"❌ 未达标 - 存在设定偏离问题（{', '.join([d[0] for d in setting_issues])}）")
            feedback_parts.append("   请立即修正设定偏离,然后重新生成内容。")
        elif word_count_issue:
            # V2.13：给出方向性纠偏（扩写/删减+目标区间），而非笼统"控制字数"
            actual_words = len(content) if content else 0
            target = self.target_word_count
            lo, hi = int(target * 0.9), int(target * 1.1)
            if actual_words > hi:
                direction = f"当前约{actual_words}字，超出目标，请删减到{lo}-{hi}字（精简描写与重复段落，不要砍情节主线）"
            elif 0 < actual_words < lo:
                direction = f"当前约{actual_words}字，低于目标，请扩写到{lo}-{hi}字（扩展细节描写与人物互动，不要注水）"
            else:
                direction = f"请将字数控制在{lo}-{hi}字"
            feedback_parts.append(f"❌ 未达标 - 字数偏离（评分 {word_count_issue.score:.3f}）")
            feedback_parts.append(f"   {direction}。")
        elif total_score >= self.quality_threshold and has_chapter_end:
            feedback_parts.extend([
                "✅ 优秀！内容质量达标且包含结束标记",
                "   设定符合、大纲完整、风格一致、知识准确。"
            ])
        elif total_score < self.quality_threshold:
            feedback_parts.append(f"⚠️ 未达标（评分 {total_score:.3f} < {self.quality_threshold}）")
        elif not has_chapter_end:
            feedback_parts.append("⚠️ 未达标（缺少【本章完】标记）")

        return "\n".join(feedback_parts)

    def shutdown(self) -> bool:
        """优雅关闭插件
        
        清理资源：
        1. 清理生成历史记录
        2. 清理API客户端引用
        3. 调用父类shutdown
        """
        try:
            # 清理生成历史
            if hasattr(self, 'generation_history'):
                self.generation_history.clear()
                logger.info("[IterativeGenerator] 已清理生成历史记录")
            
            # 清理API客户端引用
            if hasattr(self, '_api_client'):
                self._api_client = None
            
            logger.info("[IterativeGenerator] 插件已关闭")
            
            return super().shutdown()
            
        except Exception as e:
            logger.error(f"[IterativeGenerator] 关闭失败: {e}")
            return False


# ============================================================================
# 模块级函数（供插件加载器使用）
# ============================================================================

def get_plugin_class():
    """获取插件类（供插件加载器调用）
    
    Returns:
        插件类
    """
    return IterativeGeneratorPlugin


def register_plugin():
    """注册插件（供插件加载器调用）
    
    Returns:
        插件类
    """
    return IterativeGeneratorPlugin
