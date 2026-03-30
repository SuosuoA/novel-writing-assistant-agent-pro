"""
专家验证器 - 九维度智能评分

版本: 1.0.0
创建日期: 2026-03-29

核心功能:
1. 强制检查【本章完】标记（一票否决）
2. 九维度评分：
   - 世界观(12%): 世界观一致性
   - 人设(19%): 人物性格一致性
   - 大纲(13%): 情节符合大纲
   - 风格(19%): 写作风格匹配
   - 知识库(8%): 知识点引用
   - 写作技巧(8%): 技巧应用
   - 字数(8%): 字数达标率
   - 上下文衔接(8%): 前文衔接
   - AI感(5%): 文本自然度
"""

import re
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass

try:
    from .models import ExpertEvaluation, ExpertConfig
except ImportError:
    from models import ExpertEvaluation, ExpertConfig

logger = logging.getLogger(__name__)


class ExpertValidator:
    """
    专家验证器
    
    九维度智能评分系统:
    - 继承EnhancedWeightedValidator的V1.1版本8维度评分
    - 扩展为9维度评分（新增知识库、写作技巧、AI感）
    - 强制检查【本章完】标记（一票否决）
    
    设计原则:
    1. 继承不破坏 - 可调用父类评分方法
    2. 扩展不冲突 - 新增维度不影响现有维度
    3. 降级可用 - 失败时使用基础评分
    """
    
    def __init__(self, config: Optional[ExpertConfig] = None):
        """
        初始化专家验证器
        
        Args:
            config: 专家配置
        """
        self.config = config or ExpertConfig()
        
        # 九维度权重配置
        self.expert_weights = {
            "世界观": 0.12,
            "人设": 0.19,
            "大纲": 0.13,
            "风格": 0.19,
            "知识库": 0.08,
            "写作技巧": 0.08,
            "字数": 0.08,
            "上下文衔接": 0.08,
            "AI感": 0.05
        }
        
        # 本地模型辅助（延迟初始化）
        self._local_model = None
        
        # 初始化建议数据库
        self._init_suggestions_db()
    
    def _init_suggestions_db(self):
        """初始化建议数据库"""
        self.suggestions_db = {
            "世界观": {
                "low": "世界观设定不明确。建议：\n1) 明确当前场景的魔法体系规则\n2) 添加环境描写体现世界特色\n3) 确保人物行为符合世界观设定",
                "medium": "世界观体现不足。建议增加场景细节描写，如建筑风格、魔法元素等，让世界观更生动。"
            },
            "人设": {
                "low": "人物形象模糊。建议：\n1) 为对话添加动作描写（如'她皱眉道'）\n2) 增加人物内心独白\n3) 确保对话风格符合人物性格",
                "medium": "人物塑造可加强。建议增加细节描写，如习惯性动作、独特口头禅等，让人物更立体。"
            },
            "大纲": {
                "low": "情节推进偏离大纲。建议：\n1) 回顾大纲当前节点\n2) 确保主要情节要点完整呈现\n3) 控制节奏，避免过快或过慢",
                "medium": "情节推进可优化。建议增加过渡情节，让故事节奏更自然。"
            },
            "风格": {
                "low": "写作风格不统一。建议：\n1) 检查句式是否多样\n2) 注意用词是否准确\n3) 保持叙述视角一致",
                "medium": "风格可进一步统一。建议增加个人风格的标志性表达。"
            },
            "知识库": {
                "low": "知识库引用不足。建议：\n1) 引用魔法体系的规则\n2) 使用设定中的专有名词\n3) 融入背景设定元素",
                "medium": "可增加知识库引用。建议适度融入世界观设定细节。"
            },
            "写作技巧": {
                "low": "写作技巧应用不足。建议：\n1) 使用'展示而非告知'技巧\n2) 增加感官描写\n3) 运用对比和衬托",
                "medium": "写作技巧可进一步提升。建议学习高级叙述技巧。"
            },
            "字数": {
                "low": "字数未达标。建议：\n1) 扩展场景描写\n2) 增加对话细节\n3) 补充人物心理活动",
                "medium": "字数接近达标。可适当扩展细节描写。"
            },
            "上下文衔接": {
                "low": "与前文衔接不自然。建议：\n1) 回顾前文关键情节\n2) 建立情节呼应\n3) 保持时间线连续",
                "medium": "衔接可更自然。建议增加过渡句。"
            },
            "AI感": {
                "low": "AI痕迹明显。建议：\n1) 减少模板化表达\n2) 增加口语化表达\n3) 使用更自然的句式变化",
                "medium": "文本略显生硬。建议增加个人化表达。"
            }
        }
    
    def evaluate(self, content: str, context: Dict[str, Any]) -> ExpertEvaluation:
        """
        九维度评分（含强制检查）
        
        Args:
            content: 生成的内容
            context: 上下文信息
                {
                    "worldview": 世界观数据,
                    "characters": 人物数据,
                    "outline": 大纲数据,
                    "style_profile": 风格数据,
                    "knowledge_base": 知识库数据,
                    "techniques": 写作技巧数据,
                    "previous_chapters": 前文数据,
                    "target_words": 目标字数
                }
            
        Returns:
            ExpertEvaluation: 评估结果
        """
        scores = {}
        analysis = {}
        
        # ===== 第零步：强制检查【本章完】标记 =====
        if not self._check_chapter_end_marker(content):
            logger.error("【本章完】标记缺失，强制返回失败评分")
            return self._create_failed_evaluation("章节缺少【本章完】标记")
        
        try:
            # ===== 第一步：基础维度评分 =====
            
            # 世界观评分
            scores["世界观"] = self._evaluate_worldview(
                content, 
                context.get("worldview", {})
            )
            
            # 人设评分
            scores["人设"] = self._evaluate_character(
                content, 
                context.get("characters", [])
            )
            
            # 大纲评分
            scores["大纲"] = self._evaluate_outline(
                content, 
                context.get("outline", {})
            )
            
            # 风格评分
            scores["风格"] = self._evaluate_style(
                content, 
                context.get("style_profile", {})
            )
            
            # 字数评分
            scores["字数"] = self._evaluate_word_count(
                content, 
                context.get("target_words", 3500)
            )
            
            # ===== 第二步：扩展维度评分 =====
            
            # 知识库评分
            scores["知识库"] = self._evaluate_knowledge_base(
                content,
                context.get("knowledge_base", {})
            )
            
            # 写作技巧评分
            scores["写作技巧"] = self._evaluate_writing_technique(
                content,
                context.get("techniques", {})
            )
            
            # 上下文衔接评分
            scores["上下文衔接"] = self._evaluate_context_continuation(
                content,
                context.get("previous_chapters", [])
            )
            
            # AI感评分
            scores["AI感"] = self._evaluate_ai_sense(content)
            
            # ===== 第三步：生成分析 =====
            analysis = self._generate_analysis(scores, content, context)
            
        except Exception as e:
            # 降级方案：使用基础评分
            logger.error(f"专家评分失败，降级为基础评分: {e}")
            scores = self._fallback_scores()
            analysis = {"error": f"评分异常: {str(e)}"}
        
        # ===== 第四步：计算总分 =====
        total_score = sum(
            scores.get(k, 0.5) * self.expert_weights.get(k, 0.1) 
            for k in self.expert_weights.keys()
        )
        
        # ===== 第五步：识别问题和优势 =====
        issues = self._identify_issues(scores, analysis)
        strengths = self._identify_strengths(scores, analysis)
        
        return ExpertEvaluation(
            total_score=round(total_score, 4),
            dimension_scores=scores,
            analysis=analysis,
            issues=issues,
            strengths=strengths
        )
    
    def _check_chapter_end_marker(self, content: str) -> bool:
        """
        强制检查章节结尾的【本章完】标记
        
        检查规则：
        1. 检查章节最后100个字符
        2. 匹配模式：【本章完】、[本章完]、（本章完）等
        3. 缺失即返回False，触发重新生成
        
        Args:
            content: 生成的章节内容
            
        Returns:
            bool: True表示标记存在，False表示缺失
        """
        if not content or len(content.strip()) == 0:
            return False
        
        # 获取最后100个字符
        check_range = self.config.chapter_end_marker_range
        last_chars = content.strip()[-check_range:] if len(content) >= check_range else content.strip()
        
        # 匹配模式列表
        patterns = self.config.chapter_end_marker_patterns
        
        # 检查是否包含任一标记
        has_marker = any(pattern in last_chars for pattern in patterns)
        
        if not has_marker:
            logger.warning(f"章节结尾未找到【本章完】标记")
        
        return has_marker
    
    def _create_failed_evaluation(self, reason: str) -> ExpertEvaluation:
        """
        创建失败评分（用于强制检查失败时）
        
        Args:
            reason: 失败原因
            
        Returns:
            ExpertEvaluation: 总分为0的评估结果
        """
        return ExpertEvaluation(
            total_score=0.0,
            dimension_scores={
                "世界观": 0.0,
                "人设": 0.0,
                "大纲": 0.0,
                "风格": 0.0,
                "知识库": 0.0,
                "写作技巧": 0.0,
                "字数": 0.0,
                "上下文衔接": 0.0,
                "AI感": 0.0
            },
            analysis={"error": reason},
            issues=[reason, "必须添加【本章完】标记在章节结尾"],
            strengths=[]
        )
    
    # ========== 维度评分方法 ==========
    
    def _evaluate_worldview(self, content: str, worldview_data: Dict) -> float:
        """
        世界观一致性评分
        
        检查点:
        1. 世界观设定是否体现
        2. 设定元素是否一致
        3. 规则是否违反
        """
        if not worldview_data:
            return 0.7  # 无数据时返回默认分
        
        score = 0.5
        
        # 提取世界观元素
        elements = worldview_data.get("elements", [])
        rules = worldview_data.get("rules", [])
        
        if elements:
            # 检查元素在内容中的体现
            matched = sum(1 for e in elements if e.get("name", "") in content)
            element_score = matched / len(elements) if elements else 0.5
            score = max(score, element_score)
        
        # 检查规则违反
        for rule in rules:
            if self._check_rule_violation(content, rule):
                score -= 0.1
        
        return max(0.0, min(1.0, score))
    
    def _check_rule_violation(self, content: str, rule: Dict) -> bool:
        """检查规则违反"""
        # 简化实现：检查是否有违反关键词
        violation_keywords = rule.get("violation_keywords", [])
        return any(kw in content for kw in violation_keywords)
    
    def _evaluate_character(self, content: str, characters_data: List) -> float:
        """
        人设一致性评分
        
        检查点:
        1. 人物性格是否一致
        2. 对话风格是否符合人设
        3. 行为动机是否合理
        """
        if not characters_data:
            return 0.7
        
        scores = []
        
        for character in characters_data:
            char_name = character.get("name", "")
            personality = character.get("personality", "")
            speaking_style = character.get("speaking_style", "")
            
            if char_name and char_name in content:
                # 人物存在，检查性格体现
                char_score = 0.5
                
                # 检查性格关键词
                if personality:
                    personality_keywords = personality.split("、")
                    matched = sum(1 for kw in personality_keywords if kw in content)
                    char_score += matched * 0.1
                
                # 检查对话风格
                if speaking_style and speaking_style in content:
                    char_score += 0.2
                
                scores.append(min(1.0, char_score))
        
        return sum(scores) / len(scores) if scores else 0.7
    
    def _evaluate_outline(self, content: str, outline_data: Dict) -> float:
        """
        大纲符合度评分
        
        检查点:
        1. 情节节点是否呈现
        2. 关键事件是否包含
        """
        if not outline_data:
            return 0.7
        
        score = 0.5
        
        # 提取关键节点
        key_events = outline_data.get("key_events", [])
        if key_events:
            matched = sum(1 for event in key_events if event in content)
            score = matched / len(key_events)
        
        return max(0.5, min(1.0, score))
    
    def _evaluate_style(self, content: str, style_data: Dict) -> float:
        """
        风格匹配度评分
        
        检查点:
        1. 句式风格
        2. 用词习惯
        3. 叙述节奏
        """
        if not style_data:
            return 0.7
        
        score = 0.5
        
        # 检查风格特征词
        style_keywords = style_data.get("keywords", [])
        if style_keywords:
            matched = sum(1 for kw in style_keywords if kw in content)
            score = matched / len(style_keywords)
        
        # 检查句式多样性
        sentences = re.split(r'[。！？]', content)
        if len(sentences) > 5:
            lengths = [len(s) for s in sentences if s.strip()]
            if lengths:
                variance = max(lengths) - min(lengths) if lengths else 0
                if variance > 20:
                    score += 0.2
        
        return min(1.0, score)
    
    def _evaluate_word_count(self, content: str, target_words: int) -> float:
        """
        字数达标率评分
        
        计算方式：实际字数/目标字数
        """
        actual_words = len(content.replace("\n", "").replace(" ", ""))
        
        if target_words <= 0:
            return 0.5
        
        ratio = actual_words / target_words
        
        if ratio >= 0.95:
            return 1.0
        elif ratio >= 0.8:
            return 0.8
        elif ratio >= 0.6:
            return 0.6
        else:
            return max(0.3, ratio)
    
    def _evaluate_knowledge_base(self, content: str, knowledge_data: Dict) -> float:
        """
        知识库引用质量评分
        
        检查点:
        1. 知识点引用数量
        2. 引用是否恰当
        """
        if not knowledge_data:
            return 0.7
        
        score = 0.5
        
        # 检查各领域知识引用
        total_items = 0
        matched_items = 0
        
        for category, items in knowledge_data.items():
            if isinstance(items, list):
                total_items += len(items)
                for item in items:
                    if isinstance(item, dict):
                        keywords = item.get("keywords", [])
                        if any(kw in content for kw in keywords):
                            matched_items += 1
        
        if total_items > 0:
            score = matched_items / total_items
        
        return max(0.5, min(1.0, score))
    
    def _evaluate_writing_technique(self, content: str, techniques: Dict) -> float:
        """
        写作技巧应用评分
        
        检查点:
        1. 技巧应用数量
        2. 应用是否恰当
        """
        if not techniques:
            return 0.7
        
        score = 0.5
        
        # 技巧检测模式
        technique_patterns = {
            "sensory": ["看到", "听到", "闻到", "摸到", "尝到"],
            "metaphor": ["像", "如同", "仿佛", "宛如"],
            "dialogue": ["：'", "' '", "\""],
            "action": ["走", "跑", "站", "坐", "看", "想"],
            "psychology": ["心里", "想着", "觉得", "感觉"]
        }
        
        detected = 0
        for pattern_name, keywords in technique_patterns.items():
            if any(kw in content for kw in keywords):
                detected += 1
        
        score = detected / len(technique_patterns)
        
        return max(0.5, min(1.0, score))
    
    def _evaluate_context_continuation(self, content: str, previous_chapters: List) -> float:
        """
        上下文衔接评分
        
        检查点:
        1. 时间线连续性
        2. 情节呼应
        """
        if not previous_chapters:
            return 0.7
        
        score = 0.5
        
        # 检查前文关键元素是否延续
        last_chapter = previous_chapters[-1] if previous_chapters else ""
        
        # 提取前文关键词
        keywords = re.findall(r'[\u4e00-\u9fa5]{2,4}', last_chapter)
        unique_keywords = set(keywords[:20])  # 取前20个关键词
        
        if unique_keywords:
            matched = sum(1 for kw in unique_keywords if kw in content)
            score = matched / len(unique_keywords)
        
        return max(0.5, min(1.0, score))
    
    def _evaluate_ai_sense(self, content: str) -> float:
        """
        AI感评分（越低越好，但返回值越高表示越自然）
        
        检查点:
        1. AI常见句式
        2. 模板化表达
        """
        ai_patterns = [
            r"首先.*其次.*最后",
            r"一方面.*另一方面",
            r"总的来说",
            r"综上所述",
            r"值得注意的是",
            r"不可否认",
            r"由此可见",
            r"总而言之"
        ]
        
        ai_score = 0.0
        
        for pattern in ai_patterns:
            if re.search(pattern, content):
                ai_score += 0.15
        
        # AI感越高，自然度越低
        naturalness = 1.0 - min(1.0, ai_score)
        
        return naturalness
    
    # ========== 辅助方法 ==========
    
    def _generate_analysis(self, scores: Dict, content: str, context: Dict) -> Dict:
        """生成分析"""
        analysis = {}
        
        for dimension, score in scores.items():
            if score >= 0.8:
                analysis[dimension] = f"{dimension}表现出色（{score:.2%}）"
            elif score >= 0.6:
                analysis[dimension] = f"{dimension}表现良好（{score:.2%}）"
            else:
                analysis[dimension] = f"{dimension}需要改进（{score:.2%}）"
        
        return analysis
    
    def _identify_issues(self, scores: Dict, analysis: Dict) -> List[str]:
        """识别问题"""
        issues = []
        
        for dimension, score in scores.items():
            if score < 0.6:
                issues.append(f"{dimension}评分较低（{score:.2%}）")
        
        return issues
    
    def _identify_strengths(self, scores: Dict, analysis: Dict) -> List[str]:
        """识别优势"""
        strengths = []
        
        for dimension, score in scores.items():
            if score >= 0.8:
                strengths.append(f"{dimension}表现出色（{score:.2%}）")
        
        return strengths
    
    def _fallback_scores(self) -> Dict[str, float]:
        """降级评分"""
        return {
            "世界观": 0.5,
            "人设": 0.5,
            "大纲": 0.5,
            "风格": 0.5,
            "知识库": 0.5,
            "写作技巧": 0.5,
            "字数": 0.5,
            "上下文衔接": 0.5,
            "AI感": 0.5
        }
    
    def get_weights(self) -> Dict[str, float]:
        """
        获取九维度权重配置
        
        Returns:
            Dict[str, float]: 维度名称到权重的映射
        """
        return self.expert_weights.copy()


# 导出
__all__ = ['ExpertValidator']
