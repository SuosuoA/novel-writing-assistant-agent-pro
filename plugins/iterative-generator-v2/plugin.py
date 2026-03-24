#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迭代生成器插件 V2 - 迭代优化的章节生成器

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

# 导入核心接口
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.plugin_interface import GeneratorPlugin, PluginMetadata, PluginType, PluginContext
from core.models import GenerationRequest, GenerationResult, ValidationScores


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
        self._logger: Optional[logging.Logger] = None
    
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
            self._logger = context.logger or logging.getLogger(__name__)
            
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
                    # 尝试获取AI服务
                    ai_service = context.service_locator.get("ai_service")
                    if ai_service:
                        self._api_client = ai_service
                        self._logger.info("[IterativeGenerator] 从服务定位器获取AI服务成功")
                except Exception as e:
                    self._logger.warning(f"[IterativeGenerator] 无法从服务定位器获取AI服务: {e}")
            
            self._logger.info(f"[IterativeGenerator] 迭代生成器初始化完成")
            self._logger.info(f"[IterativeGenerator] 目标字数: {self.target_word_count}, 质量阈值: {self.quality_threshold}, 最大迭代: {self.max_iterations}")
            
            return True
            
        except Exception as e:
            if self._logger:
                self._logger.error(f"[IterativeGenerator] 初始化失败: {e}")
            return False
    
    def set_api_client(self, api_client: Any):
        """
        设置API客户端
        
        Args:
            api_client: API客户端实例
        """
        self._api_client = api_client
        if self._logger:
            self._logger.info("[IterativeGenerator] API客户端已设置")
    
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
        
        if self._logger:
            self._logger.info(f"[IterativeGenerator] 配置已更新 - 模型: {model_name}, 字数: {target_word_count}, 阈值: {quality_threshold}, 迭代: {max_iterations}")
    
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
            if self._logger:
                self._logger.error(f"[IterativeGenerator] 生成失败: {e}")
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
        if self._logger:
            self._logger.info("[V2] ========== 开始迭代生成流程 ==========")
        else:
            logging.info("[V2] ========== 开始迭代生成流程 ==========")
        if self._logger:
            self._logger.info(f"[V2] 质量阈值: {self.quality_threshold}, 最大迭代: {self.max_iterations}")

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
            if self._logger:
                self._logger.info(f"[V2] 第 {iteration + 1} 轮迭代开始")

            # === 步骤1: 整理打包请求内容 ===
            current_prompt = self._build_request_prompt(prompt, iteration, best_result)

            # === 步骤2: 向大模型发送请求 ===
            if self._logger:
                self._logger.info(f"[V2] 正在发送API请求...")

            try:
                generated_content = self._send_request_to_model(current_prompt, strategy)
            except Exception as e:
                if self._logger:
                    self._logger.error(f"[V2] API请求失败: {e}")
                if iteration == 0:
                    # 第一轮就失败，抛出异常
                    raise
                # 后续轮次失败，使用上次最佳结果
                if self._logger:
                    self._logger.warning(f"[V2] 第{iteration + 1}轮生成失败，使用上一轮结果")
                break

            # === 步骤3: 接受返回文章 ===
            if self._logger:
                self._logger.info(f"[V2] 接收到返回内容，长度: {len(generated_content)} 字符")

            # === 步骤4: 从多维度评分 ===
            total_score, dimension_scores, suggestions = self._evaluate_content(
                generated_content, validation_fn
            )

            # 检查【本章完】标记
            has_chapter_end = '【本章完】' in generated_content
            if self._logger:
                self._logger.info(f"[V2] 【本章完】检查: {'有' if has_chapter_end else '没有'}, 总评分: {total_score:.3f}")

            # 打印各维度评分
            for dim_name, dim_score in dimension_scores.items():
                if self._logger:
                    self._logger.debug(f"[V2] {dim_name}: {dim_score.score:.3f} - {dim_score.details}")

            # 记录结果
            iteration_result = IterationResult(
                iteration=iteration + 1,
                content=generated_content,
                total_score=total_score,
                dimension_scores=dimension_scores,
                has_chapter_end=has_chapter_end,
                feedback=self._build_feedback_text(total_score, dimension_scores, has_chapter_end),
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
            # 检查字数偏差（超过50%强制继续迭代）
            word_count_score = dimension_scores.get('字数')
            word_count_deviation = 0
            if word_count_score and isinstance(word_count_score, DimensionScore):
                word_count_deviation = 1 - word_count_score.score  # 评分越低，偏差越大
            
            # 必须同时满足：评分 >= 0.8、有【本章完】标记、字数偏差不超过50%
            word_count_acceptable = word_count_score is None or (isinstance(word_count_score, DimensionScore) and word_count_score.score >= 0.3)
            
            if total_score >= self.quality_threshold and has_chapter_end and word_count_acceptable:
                if self._logger:
                    self._logger.info(f"[V2][SUCCESS] ========== 迭代完成！满足条件 ==========")
                    self._logger.info(f"[V2][SUCCESS] 总评分: {total_score:.3f} >= {self.quality_threshold}")
                    self._logger.info(f"[V2][SUCCESS] 包含【本章完】标记")
                    if word_count_score and isinstance(word_count_score, DimensionScore):
                        self._logger.info(f"[V2][SUCCESS] 字数评分: {word_count_score.score:.3f} >= 0.3")
                    self._logger.info(f"[V2] 迭代完成！满足条件，评分: {total_score:.3f}")

                best_result = iteration_result
                best_score = total_score
                break

            # === 不满足条件，构建反馈，准备下一轮 ===
            if self._logger:
                self._logger.info(f"[V2][CONTINUE] 未满足条件，准备第 {iteration + 2} 轮迭代")
                self._logger.info(f"[V2][CONTINUE] 原因: ")
                if total_score < self.quality_threshold:
                    self._logger.info(f"[V2][CONTINUE]   - 评分 {total_score:.3f} < 阈值 {self.quality_threshold}")
                if not has_chapter_end:
                    self._logger.info(f"[V2][CONTINUE]   - 缺少【本章完】标记")
                if not word_count_acceptable:
                    self._logger.info(f"[V2][CONTINUE]   - 字数偏差过大（评分 {word_count_score.score:.3f} < 0.3，偏差超过50%）")

                # 打印反馈内容
                self._logger.info(f"[V2][FEEDBACK] 反馈内容:")
                self._logger.debug(iteration_result.feedback)

            # 如果是最佳结果，保存
            if total_score > best_score:
                best_result = iteration_result
                best_score = total_score

        # 迭代结束（达到最大次数或满足条件）
        if self._logger:
            self._logger.info(f"[V2][FINAL] ========== 迭代结束 ==========")
            self._logger.info(f"[V2][FINAL] 总迭代次数: {stats['iterations']}")
            self._logger.info(f"[V2][FINAL] 最佳评分: {best_score:.3f}")

        # 输出保存
        final_content = best_result.content if best_result else ""
        if self._logger:
            self._logger.info(f"[V2][SAVE] 最终内容长度: {len(final_content)} 字符")
            self._logger.info(f"[V2][SAVE] 最终内容包含【本章完】: {'是' if '【本章完】' in final_content else '否'}")

        # === 步骤6: 输出保存 ===
        if self._logger:
            self._logger.info(f"[V2] 迭代结束，返回最终内容")
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

        if self._logger:
            self._logger.debug(f"[V2][PROMPT] 第一轮提示词（前200字符）: {prompt[:200]}...")
            return prompt

        # 后续轮次：基础提示词 + 反馈 + 改进要求
        if self._logger:
            self._logger.info(f"[V2][PROMPT] 构建第{iteration + 1}轮提示词...")

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
        if self._logger:
            self._logger.debug(f"[V2][PROMPT] 提示词长度: {len(final_prompt)} 字符")

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
        if not self._api_client:
            raise RuntimeError("API客户端未设置，请调用set_api_client()或通过服务定位器获取")
        
        # 计算max_tokens - V5.7修复：确保AI有足够token生成完整章节
        # 中文约1.5字符/token，目标字数对应约 target/1.5 tokens
        # V5.7修复：给AI留出足够空间写【本章完】（至少+20%空间）
        base_tokens = int(self.target_word_count / 1.5)  # 基础token数
        max_tokens = int(base_tokens * 1.5)  # 允许50%浮动，确保有空间写【本章完】
        max_tokens = max(max_tokens, 1000)  # 最小1000 tokens（V5.7提高下限）
        max_tokens = min(max_tokens, 4096)  # 最大4096 tokens

        # 根据策略设置温度
        temperature_map = {
            GenerationStrategy.CREATIVE: 0.9,
            GenerationStrategy.BALANCED: 0.7,
            GenerationStrategy.PRECISE: 0.5
        }
        temperature = temperature_map.get(strategy, 0.7)

        if self._logger:
            self._logger.debug(f"[V2] API请求 - max_tokens: {max_tokens}, temperature: {temperature}")

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

        # 调用API客户端(使用OpenAI标准接口)
        try:
            response = self._api_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=120  # 120秒超时
            )

            # 提取生成内容
            content = response.choices[0].message.content

            if self._logger:
                self._logger.info(f"[V2][API] API响应成功，内容长度: {len(content)} 字符")

            return content

        except Exception as e:
            if self._logger:
                self._logger.error(f"[V2][ERROR] API调用失败: {e}")
            raise

    def _evaluate_content(
        self,
        content: str,
        validation_fn: Optional[Callable]
    ) -> Tuple[float, Dict[str, DimensionScore], List[str]]:
        """
        步骤4: 从多维度评分

        维度：
        - 世界观
        - 大纲
        - 风格
        - 人设
        - Ai感
        - 字数
        - 上下文契合度

        没有【本章完】视作未完成（会在外部处理，这里只返回评分）
        """
        # 如果没有验证函数，返回默认评分
        if validation_fn is None:
            default_scores = {
                '世界观': DimensionScore('世界观', 0.5, '无验证函数', []),
                '大纲': DimensionScore('大纲', 0.5, '无验证函数', []),
                '风格': DimensionScore('风格', 0.5, '无验证函数', []),
                '人设': DimensionScore('人设', 0.5, '无验证函数', []),
                'AI感': DimensionScore('AI感', 0.5, '无验证函数', []),
                '字数': DimensionScore('字数', self._score_word_count(content), f'目标:{self.target_word_count} 实际:{len(content)}', []),
                '上下文契合度': DimensionScore('上下文契合度', 0.5, '无验证函数', [])
            }
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
                if self._logger:
                    self._logger.debug(f"[V2] 处理维度: {dim_name}, 类型: {type(dim_data)}, 值: {dim_data}")
                
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
                else:
                    # 未知类型，使用默认值
                    if self._logger:
                        self._logger.warning(f"[V2][WARNING] 未知维度数据类型: {type(dim_data)}")
                    dimension_scores[dim_name] = DimensionScore(
                        dimension_name=dim_name,
                        score=0.5,
                        details=f'数据类型错误: {type(dim_data)}',
                        issues=[]
                    )

            if self._logger:
                self._logger.info(f"[V2][SCORE] 评分完成 - 总分: {total_score:.3f}, 维度数: {len(dimension_scores)}")

            return total_score, dimension_scores, suggestions

        except Exception as e:
            if self._logger:
                self._logger.error(f"[V2][ERROR] 评分过程出错: {e}")

            # 返回默认评分
            default_scores = {
                '世界观': DimensionScore('世界观', 0.5, f'评分失败: {str(e)}', []),
                '大纲': DimensionScore('大纲', 0.5, '评分失败', []),
                '风格': DimensionScore('风格', 0.5, '评分失败', []),
                '人设': DimensionScore('人设', 0.5, '评分失败', []),
                'AI感': DimensionScore('AI感', 0.5, '评分失败', []),
                '字数': DimensionScore('字数', 0.5, '评分失败', []),
                '上下文契合度': DimensionScore('上下文契合度', 0.5, '评分失败', [])
            }

            return 0.5, default_scores, [f'评分过程出错: {str(e)}']
    
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
        has_chapter_end: bool
    ) -> str:
        """
        步骤5: 构建反馈文本（增强版 - 针对性改进建议）

        格式：总评分 + 各维度评分 + 问题描述(优先显示设定偏离问题) + 具体改进建议
        """
        feedback_parts = [
            f"【总评分】: {total_score:.3f} / 1.0",
            ""
        ]

        # 🔴 优先级1:检查设定偏离(人设、世界观、风格)
        priority_dims = ['人设', '世界观', '风格']
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
            
            # 记录字数问题
            if dim_name == '字数' and dim_score.score < 0.3:
                word_count_issue = dim_score
            
            # 记录大纲问题
            if dim_name == '大纲' and dim_score.score < 0.7:
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

        if setting_issues:
            feedback_parts.append(f"❌ 未达标 - 存在设定偏离问题（{', '.join([d[0] for d in setting_issues])}）")
            feedback_parts.append("   请立即修正设定偏离,然后重新生成内容。")
        elif word_count_issue:
            feedback_parts.append(f"❌ 未达标 - 字数偏差过大（评分 {word_count_issue.score:.3f} < 0.3）")
            feedback_parts.append("   请严格控制字数，重新生成内容。")
        elif total_score >= self.quality_threshold and has_chapter_end:
            feedback_parts.extend([
                "✅ 优秀！内容质量达标且包含结束标记",
                "   设定符合、大纲完整、风格一致。"
            ])
        elif total_score < self.quality_threshold:
            feedback_parts.append(f"⚠️ 未达标（评分 {total_score:.3f} < {self.quality_threshold}）")
        elif not has_chapter_end:
            feedback_parts.append("⚠️ 未达标（缺少【本章完】标记）")

        return "\n".join(feedback_parts)


# ============================================================================
# 模块级函数（供插件加载器使用）
# ============================================================================

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
                if self._logger:
                    self._logger.info("[IterativeGenerator] 已清理生成历史记录")
            
            # 清理API客户端引用
            if hasattr(self, '_api_client'):
                self._api_client = None
            
            if self._logger:
                self._logger.info("[IterativeGenerator] 插件已关闭")
            
            return super().shutdown()
            
        except Exception as e:
            if self._logger:
                self._logger.error(f"[IterativeGenerator] 关闭失败: {e}")
            return False


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
