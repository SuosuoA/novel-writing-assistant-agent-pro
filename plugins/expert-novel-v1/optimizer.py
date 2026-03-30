"""
专家优化器 - 优化建议生成

版本: 1.0.0
创建日期: 2026-03-29

核心功能:
1. 基于评分结果生成优化建议
2. 提供切实可执行的修改方案
3. 生成具体修改示例

设计原则:
- 切实可执行：不说空话，直接告诉怎么改
- 具体明确：给出具体方法或示例
- 有针对性：基于实际分析结果
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

try:
    from .models import ExpertEvaluation, OptimizationSuggestion
except ImportError:
    from models import ExpertEvaluation, OptimizationSuggestion

logger = logging.getLogger(__name__)


class ExpertOptimizer:
    """
    专家优化器
    
    核心功能:
    1. 基于评估结果生成优化建议
    2. 提供切实可执行的修改方案
    3. 生成具体修改示例
    
    设计原则:
    - 切实可执行：不说空话，直接告诉怎么改
    - 具体明确：给出具体方法或示例
    - 有针对性：基于实际分析结果
    """
    
    def __init__(self):
        """初始化优化器"""
        
        # 建议模板库
        self._init_templates()
    
    def _init_templates(self):
        """初始化建议模板"""
        
        self.dimension_templates = {
            "世界观": {
                "high": "世界观设定优秀，继续保持",
                "medium": """世界观表现可增强：
1) 增加环境描写，体现世界特色（如建筑风格、地理特征）
2) 在对话中自然融入设定元素
3) 确保场景描述与世界观一致""",
                "low": """世界观设定严重不足，建议：
1) 明确当前场景的魔法体系规则，如："根据光明教会的教义，魔法师在使用火系魔法时需要消耗精神力"
2) 添加环境描写体现世界特色，如："街道两旁的石砌建筑散发着淡淡的魔法波动"
3) 确保人物行为符合世界观设定，避免出现违背设定的情况"""
            },
            "人设": {
                "high": "人物塑造出色，性格鲜明",
                "medium": """人设表现可优化：
1) 增加人物标志性动作描写
2) 对话中体现人物性格特点
3) 补充内心独白，展现人物思想""",
                "low": """人物形象模糊，建议：
1) 为对话添加动作描写，如"她皱了皱眉，眼神中闪过一丝不安"而非简单的"她说"
2) 增加人物内心独白，展现思想变化
3) 确保对话风格符合人物性格，如活泼角色用语应轻快"""
            },
            "大纲": {
                "high": "情节推进符合大纲，节奏把控得当",
                "medium": """情节推进可优化：
1) 增加过渡情节，让节奏更自然
2) 强化关键情节的戏剧性
3) 注意伏笔的埋设""",
                "low": """情节推进偏离大纲，建议：
1) 回顾大纲当前节点的核心任务
2) 确保主要情节要点完整呈现
3) 控制节奏，避免过快推进或过于拖沓"""
            },
            "风格": {
                "high": "写作风格统一，富有个人特色",
                "medium": """风格可进一步统一：
1) 保持句式多样性
2) 注意用词的准确性
3) 增加个人风格的标志性表达""",
                "low": """写作风格不统一，建议：
1) 检查句式是否多样，避免连续使用相同句型
2) 注意用词是否准确，替换口语化表达
3) 保持叙述视角一致，避免突然切换"""
            },
            "知识库": {
                "high": "知识库引用恰当，增强了内容深度",
                "medium": """知识库引用可增加：
1) 适度融入设定细节
2) 引用时注意自然过渡
3) 避免生硬堆砌""",
                "low": """知识库引用不足，建议：
1) 引用魔法体系的规则，如"根据光明教会的教义..."
2) 使用设定中的专有名词，如地名、组织名等
3) 融入背景设定元素，增强世界观的实感"""
            },
            "写作技巧": {
                "high": "写作技巧运用娴熟，增强了表现力",
                "medium": """写作技巧可提升：
1) 增加感官描写
2) 运用对比衬托
3) 注意节奏变化""",
                "low": """写作技巧应用不足，建议：
1) 使用"展示而非告知"技巧，用具体细节代替抽象描述
2) 增加感官描写（视觉、听觉、嗅觉、触觉）
3) 运用对比和衬托，突出人物或情节特点"""
            },
            "字数": {
                "high": "字数达标，内容充实",
                "medium": """字数接近达标：
1) 可适当扩展场景描写
2) 增加对话细节
3) 补充人物心理活动""",
                "low": """字数未达标，建议：
1) 扩展场景描写，增加环境细节
2) 增加对话细节，展现人物性格
3) 补充人物心理活动描写
4) 添加过渡情节，丰富故事层次"""
            },
            "上下文衔接": {
                "high": "与前文衔接自然，情节连贯",
                "medium": """衔接可更自然：
1) 增加过渡句
2) 回应前文伏笔
3) 注意时间线""",
                "low": """与前文衔接不自然，建议：
1) 回顾前文关键情节，确保时间线连续
2) 建立情节呼应，如"正如之前所说..."
3) 添加过渡句，如"几天后的一个清晨"或"转眼间，时间来到了..."
4) 注意人物状态的连贯性"""
            },
            "AI感": {
                "high": "文本自然，无明显AI痕迹",
                "medium": """文本略显生硬：
1) 增加口语化表达
2) 变化句式结构
3) 减少模板化用语""",
                "low": """AI痕迹明显，建议：
1) 减少模板化表达，如"首先...其次...最后..."
2) 增加口语化表达，让对话更自然
3) 使用更多变的句式，避免千篇一律的句型
4) 增加个人化表达，如特定的比喻或用词习惯"""
            }
        }
        
        # 修改示例库
        self.example_templates = {
            "人设": [
                {
                    "原文": "她说：'我不会去的。'",
                    "建议": "她皱了皱眉，眼神中闪过一丝不安：'我不会去的。'"
                },
                {
                    "原文": "他回答道。",
                    "建议": "他沉默了片刻，缓缓开口。"
                }
            ],
            "世界观": [
                {
                    "原文": "他施展了魔法。",
                    "建议": "他低声吟唱咒语，空气中的魔法元素开始凝聚，一道淡蓝色的光芒在指尖浮现。"
                },
                {
                    "原文": "这里是一座城市。",
                    "建议": "眼前是一座被魔法屏障笼罩的古老城市，高耸的石砌城墙在阳光下泛着微光。"
                }
            ],
            "写作技巧": [
                {
                    "原文": "她很害怕。",
                    "建议": "她的手指不自觉地攥紧了衣角，呼吸也变得急促起来。"
                },
                {
                    "原文": "天很热。",
                    "建议": "烈日当空，空气中弥漫着燥热的气息，连树上的蝉鸣都变得有气无力。"
                }
            ]
        }
    
    def generate_suggestions(self, evaluation: ExpertEvaluation) -> OptimizationSuggestion:
        """
        生成优化建议
        
        Args:
            evaluation: 评估结果
            
        Returns:
            OptimizationSuggestion: 切实可执行的优化建议
        """
        suggestions = {}
        examples = []
        
        # 针对每个低分维度生成建议
        for dimension, score in evaluation.dimension_scores.items():
            if score < 0.8:
                suggestion = self._generate_dimension_suggestion(
                    dimension,
                    score,
                    evaluation.analysis.get(dimension, "")
                )
                suggestions[dimension] = suggestion
                
                # 生成具体修改示例
                example = self._generate_modification_example(dimension)
                if example:
                    examples.append(example)
        
        # 确定优先级
        priority = self._determine_priority(evaluation.total_score)
        
        # 生成总体建议
        overall = self._generate_overall_suggestion(evaluation)
        
        return OptimizationSuggestion(
            overall_suggestion=overall,
            dimension_suggestions=suggestions,
            examples=examples,
            priority=priority
        )
    
    def _generate_dimension_suggestion(self, dimension: str, score: float, 
                                        analysis: str) -> str:
        """
        生成特定维度的优化建议
        
        Args:
            dimension: 维度名称
            score: 维度分数
            analysis: 分析结果
            
        Returns:
            str: 优化建议
        """
        # 根据分数选择建议级别
        if score < 0.5:
            level = "low"
        elif score < 0.7:
            level = "medium"
        else:
            level = "high"
        
        # 获取建议模板
        templates = self.dimension_templates.get(dimension, {})
        suggestion = templates.get(level, "需要改进")
        
        return suggestion
    
    def _generate_modification_example(self, dimension: str) -> Optional[Dict[str, str]]:
        """
        生成具体修改示例
        
        Args:
            dimension: 维度名称
            
        Returns:
            Dict: 修改示例 {"原文": "...", "建议": "..."}
        """
        examples = self.example_templates.get(dimension, [])
        
        if examples:
            return examples[0]
        
        return None
    
    def _determine_priority(self, total_score: float) -> str:
        """
        确定优先级
        
        Args:
            total_score: 总分
            
        Returns:
            str: "high" / "medium" / "low"
        """
        if total_score < 0.5:
            return "high"
        elif total_score < 0.7:
            return "medium"
        else:
            return "low"
    
    def _generate_overall_suggestion(self, evaluation: ExpertEvaluation) -> str:
        """
        生成总体建议
        
        Args:
            evaluation: 评估结果
            
        Returns:
            str: 总体建议
        """
        total_score = evaluation.total_score
        weak_dims = evaluation.get_weak_dimensions()
        strong_dims = evaluation.get_strong_dimensions()
        
        parts = []
        
        # 总体评价
        if total_score >= 0.8:
            parts.append("整体质量优秀，")
        elif total_score >= 0.6:
            parts.append("整体质量良好，")
        else:
            parts.append("整体质量需要改进，")
        
        # 优势说明
        if strong_dims:
            parts.append(f"在{', '.join(strong_dims[:3])}方面表现出色。")
        
        # 问题说明
        if weak_dims:
            parts.append(f"主要问题集中在{', '.join(weak_dims[:3])}方面，")
            parts.append("建议针对性优化。")
        
        return "".join(parts)
    
    def optimize_with_history(self, evaluation: ExpertEvaluation,
                               history: List[Dict]) -> OptimizationSuggestion:
        """
        使用历史经验优化建议
        
        越用越聪明的关键：
        1. 检索历史上的相似问题
        2. 参考成功的优化案例
        3. 避免重复失败的方案
        
        Args:
            evaluation: 评估结果
            history: 历史优化记录
            
        Returns:
            OptimizationSuggestion: 融合历史经验的优化建议
        """
        # 基础建议
        base_suggestion = self.generate_suggestions(evaluation)
        
        if not history:
            return base_suggestion
        
        # 分析历史成功案例
        successful_cases = [
            case for case in history
            if case.get("user_rating", 0) >= 4.0
        ]
        
        if successful_cases:
            # 融合历史成功经验
            enhanced_suggestions = {}
            
            for dimension, suggestion in base_suggestion.dimension_suggestions.items():
                # 检查历史中是否有该维度的成功建议
                matching_cases = [
                    case for case in successful_cases
                    if dimension in case.get("dimension_suggestions", {})
                ]
                
                if matching_cases:
                    # 融合历史经验
                    history_tip = matching_cases[0].get("dimension_suggestions", {}).get(dimension, "")
                    enhanced_suggestions[dimension] = f"{suggestion}\n\n历史成功经验：{history_tip}"
                else:
                    enhanced_suggestions[dimension] = suggestion
            
            return OptimizationSuggestion(
                overall_suggestion=base_suggestion.overall_suggestion,
                dimension_suggestions=enhanced_suggestions,
                examples=base_suggestion.examples,
                priority=base_suggestion.priority
            )
        
        return base_suggestion


# 导出
__all__ = ['ExpertOptimizer']
