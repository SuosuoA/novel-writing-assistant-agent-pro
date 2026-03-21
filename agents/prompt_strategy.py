"""
Prompt策略模块

V2.0版本
创建日期: 2026-03-21

支持5种推理策略:
- Zero-shot: 无需示例
- Few-shot: 提供示例
- CoT: 链式思考
- ToT: 树状思考
- ReAct: 推理+行动
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


class PromptStrategy(Enum):
    """Prompt策略枚举"""

    ZERO_SHOT = "zero_shot"
    FEW_SHOT = "few_shot"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    TREE_OF_THOUGHT = "tree_of_thought"
    REACT = "react"


@dataclass
class PromptTemplate:
    """
    Prompt模板

    定义Agent的提示词模板
    """

    name: str
    system_prompt: str
    user_template: str
    strategy: PromptStrategy = PromptStrategy.CHAIN_OF_THOUGHT
    constraints: List[str] = None
    examples: List[Dict[str, str]] = None

    def __post_init__(self):
        if self.constraints is None:
            self.constraints = []
        if self.examples is None:
            self.examples = []

    def render(self, user_input: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """
        渲染Prompt

        Args:
            user_input: 用户输入
            context: 上下文信息

        Returns:
            渲染后的Prompt
        """
        # 渲染用户模板
        user_prompt = self.user_template.format(**user_input)

        # 添加示例（Few-shot）
        if self.strategy == PromptStrategy.FEW_SHOT and self.examples:
            examples_text = "\n\n".join(
                [
                    f"示例:\n输入: {ex['input']}\n输出: {ex['output']}"
                    for ex in self.examples
                ]
            )
            user_prompt = f"{examples_text}\n\n{user_prompt}"

        # 添加CoT提示
        if self.strategy == PromptStrategy.CHAIN_OF_THOUGHT:
            user_prompt = f"{user_prompt}\n\n请逐步思考并展示推理过程。"

        # 添加约束
        if self.constraints:
            constraints_text = "\n".join([f"- {c}" for c in self.constraints])
            user_prompt = f"{user_prompt}\n\n约束条件:\n{constraints_text}"

        # 添加上下文
        if context:
            context_text = "\n".join([f"{k}: {v}" for k, v in context.items()])
            user_prompt = f"上下文信息:\n{context_text}\n\n{user_prompt}"

        return user_prompt


# 预定义的Agent Prompt模板

PLANNER_PROMPT = PromptTemplate(
    name="planner",
    system_prompt="""你是一个专业的小说创作规划师，擅长将复杂任务分解为可执行的子任务。

核心职责:
1. 分析用户需求，识别任务目标
2. 分解任务为多个子任务
3. 识别任务依赖关系
4. 制定执行顺序

输出格式:
- JSON格式的任务计划
- 包含子任务列表、依赖关系、优先级""",
    user_template="""任务描述: {task_description}
目标章节: {chapter_title}
大纲内容: {chapter_outline}
目标字数: {word_count}字

请制定详细的生成计划。""",
    strategy=PromptStrategy.CHAIN_OF_THOUGHT,
    constraints=["必须保持任务逻辑连贯性", "子任务必须可独立验证", "依赖关系必须明确"],
)

THINKER_PROMPT = PromptTemplate(
    name="thinker",
    system_prompt="""你是一个深度思考的AI推理引擎，擅长复杂问题的分析和推理。

核心能力:
1. 链式推理: 逐步分析问题，展示推理过程
2. 多角度思考: 从不同角度审视问题
3. 逻辑验证: 检查推理过程的逻辑性

思考模式:
- 问题分解
- 假设提出
- 证据收集
- 逻辑推理
- 结论验证""",
    user_template="""待思考问题: {question}
上下文信息:
{context}

请深入思考并给出你的分析。""",
    strategy=PromptStrategy.CHAIN_OF_THOUGHT,
    constraints=[
        "必须展示完整的推理过程",
        "推理步骤必须有逻辑依据",
        "结论必须有证据支撑",
    ],
)

OPTIMIZER_PROMPT = PromptTemplate(
    name="optimizer",
    system_prompt="""你是一个迭代优化专家，擅长根据反馈不断改进输出质量。

优化原则:
1. 精准定位问题: 根据反馈识别具体问题
2. 制定改进方案: 针对问题提出可执行的改进措施
3. 验证改进效果: 确保改进解决了问题

优化流程:
- 分析反馈 → 识别问题 → 制定方案 → 执行改进 → 验证效果""",
    user_template="""当前输出: {current_output}
反馈意见: {feedback}
评分结果: {scores}
迭代轮次: {iteration}/5

请根据反馈优化输出。""",
    strategy=PromptStrategy.CHAIN_OF_THOUGHT,
    constraints=[
        "必须针对性地解决反馈中的问题",
        "保持已有优点，不要全盘推翻",
        "每次迭代都应有明显改进",
    ],
)

VALIDATOR_PROMPT = PromptTemplate(
    name="validator",
    system_prompt="""你是一个质量验证专家，负责多维度评估输出质量。

验证维度:
1. 字数符合性: 是否达到目标字数
2. 大纲符合性: 是否覆盖关键情节
3. 风格一致性: 是否符合目标风格
4. 人设一致性: 角色行为是否符合设定
5. 世界观一致性: 是否违背世界观设定
6. 自然度: 文学性和流畅度

评分标准:
- 1.0: 完美符合
- 0.8-0.9: 基本符合，有小瑕疵
- 0.6-0.7: 部分符合，有明显问题
- 0.4-0.5: 不符合，需要大幅改进
- 0.0-0.3: 严重不符合

权重配置:
- 字数: 10%
- 大纲: 15%
- 风格: 25%
- 人设: 25%
- 世界观: 20%
- 自然度: 5%""",
    user_template="""待验证内容: {content}
大纲要求: {outline}
风格档案: {style_profile}
人物设定: {characters}
世界观设定: {worldview}
目标字数: {target_words}字

请进行多维度评分。""",
    strategy=PromptStrategy.FEW_SHOT,
    constraints=[
        "评分必须客观公正",
        "必须给出具体的评分理由",
        "对于低分项必须提供改进建议",
    ],
)
