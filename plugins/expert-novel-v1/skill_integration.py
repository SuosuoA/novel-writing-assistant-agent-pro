"""
专家插件技能集成模块

版本: 1.2.0
创建日期: 2026-04-04
更新日期: 2026-04-04

功能:
1. 统一管理外部技能的加载和调用
2. 为专家插件提供可扩展的技能接口
3. 支持技能的热插拔和降级

支持的技能（已激活）:
- humanizer: 去AI感能力，检测18种AI写作模式 → 集成到 AI感 评分维度
- fiction-writing: 创意写作增强，5+2维度小说质量评估 → 集成到 写作技巧 评分维度

V1.2.0 更新（当前版本）:
【核心增强】FictionWritingSkill从"通用模板检测"升级为"项目数据驱动精准评估":

1. 数据提取层（新增3个方法）:
   - _extract_characters(): 标准化人物数据，兼容中英文key、嵌套结构
   - _extract_worldview(): 提取世界观元素/规则/设定关键词
   - _extract_style(): 提取风格特征关键词

2. 增强评估方法（新增4个方法）:
   - _evaluate_character_depth_v2(): 四层次人物深度分析（使用真实人设数据）
   - _evaluate_worldbuilding_v2(): 世界观构建精准匹配（使用真实世界观数据）
   - _evaluate_outline_alignment(): 大纲契合度评估（新增维度）
   - _evaluate_style_match(): 风格匹配度评估（新增维度）

3. 增强建议生成:
   - _generate_suggestions_v2(): 基于真实数据的针对性建议
   - 当有人物数据时：指名道姓给出改进建议
   - 当有世界观数据时：指出缺失的设定元素

4. 完整降级链:
   V2评估 → 有fallback时降级到旧版 → 无数据时返回默认值

设计原则:
- 技能可选：技能加载失败不影响核心功能
- 延迟加载：按需初始化技能
- 降级可用：技能不可用时使用内置实现
"""

import os
import sys
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field
import re

logger = logging.getLogger(__name__)


@dataclass
class SkillConfig:
    """技能配置"""
    name: str
    enabled: bool = True
    priority: int = 10
    fallback_enabled: bool = True
    
    # 技能特定的配置
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HumanizerResult:
    """Humanizer技能结果"""
    ai_score: float  # AI感评分 0.0-1.0，越高越像AI
    naturalness: float  # 自然度评分 0.0-1.0，越高越自然
    detected_patterns: List[str]  # 检测到的AI模式
    suggestions: List[str]  # 优化建议
    pattern_counts: Dict[str, int]  # 各模式出现次数


class HumanizerSkill:
    """
    Humanizer技能集成
    
    功能：检测和评估文本中的AI写作痕迹
    
    基于Wikipedia的"Signs of AI writing"指南，检测以下模式：
    1. 内容模式：过度强调重要性、模糊引用、大纲式结构
    2. 语言模式：AI词汇、避免使用"是"、负面对仗
    3. 风格模式：破折号滥用、粗体滥用、表情符号
    4. 沟通模式：协作痕迹、知识截止声明、谄媚语气
    """
    
    def __init__(self, config: Optional[SkillConfig] = None):
        self.config = config or SkillConfig(name="humanizer")
        self._init_patterns()
        logger.info("Humanizer技能初始化完成")
    
    def _init_patterns(self):
        """初始化AI写作模式检测规则"""
        
        # === 内容模式 ===
        
        # 1. 过度强调重要性和意义
        self.significance_patterns = [
            r"作为.*的重要.*",
            r"是.*的见证",
            r"是.*的证明",
            r"具有.*的重要意义",
            r"扮演着.*的关键角色",
            r"标志着.*的转折点",
            r"反映了.*的更广泛的?",
            r"象征着.*的持续",
            r"为.*做出了.*贡献",
            r"为.*奠定了基础",
            r"代表了.*的转变",
            r"关键转折点",
            r"不断演变的.*格局",
            r"焦点所在",
            r"不可磨灭的印记",
            r"深深植根于"
        ]
        
        # 2. 过度强调知名度和媒体覆盖
        self.notability_patterns = [
            r"独立报道",
            r"本地媒体.*报道",
            r"全国性媒体",
            r"由.*专家撰写",
            r"活跃的社交媒体",
            r"粉丝超过.*万"
        ]
        
        # 3. 带有-ing结尾的浅层分析
        self.ing_analysis_patterns = [
            r"，突出了.*",
            r"，强调了.*",
            r"，反映了.*",
            r"，象征着.*",
            r"，有助于.*",
            r"，促进了.*",
            r"，展示了.*",
            r"，包含了.*"
        ]
        
        # 4. 推销式语言
        self.promotional_patterns = [
            r"拥有.*的",
            r"充满活力的",
            r"丰富的.*遗产",
            r"深厚的.*",
            r"增强了.*",
            r"展示了.*",
            r"体现了.*承诺",
            r"自然美景",
            r"坐落于.*中心",
            r"突破性的",
            r"著名的",
            r"令人惊叹的",
            r"必去之地",
            r"绝美的"
        ]
        
        # 5. 模糊引用
        self.vague_attribution_patterns = [
            r"行业报告显示",
            r"观察家指出",
            r"专家认为",
            r"一些批评者认为",
            r"多个来源",
            r"多家媒体报道"
        ]
        
        # 6. 大纲式"挑战与展望"结构
        self.challenge_patterns = [
            r"尽管面临.*挑战",
            r"尽管存在.*问题",
            r"挑战与.*展望",
            r"未来展望",
            r"尽管如此.*仍"
        ]
        
        # === 语言模式 ===
        
        # 7. AI高频词汇
        self.ai_vocabulary = [
            "此外", "另外", "与之对齐", "关键的", "深入探讨",
            "持久的", "增强", "促进", "获得", "突出",
            "相互作用", "复杂的", "关键", "格局", "关键的",
            "展示", "织锦", "见证", "强调", "有价值的",
            "充满活力的", "至关重要", "不可或缺"
        ]
        
        # 8. 避免使用"是"（系词回避）
        self.copula_avoidance_patterns = [
            r"作为.*存在",
            r"标志着.*",
            r"代表了.*",
            r"拥有.*",
            r"提供.*",
            r"具有.*特点"
        ]
        
        # 9. 负面对仗
        self.negative_parallelism_patterns = [
            r"不仅.*而且.*",
            r"不只是.*而是.*",
            r"并非.*而是.*",
            r"不但.*而且.*"
        ]
        
        # 10. 三段式规则滥用
        self.rule_of_three_patterns = [
            r"[，。].*、.*和.*[，。",
            r"[，。].*、.*、.*[，。",
        ]
        
        # === 风格模式 ===
        
        # 11. 破折号滥用
        self.em_dash_pattern = r"—{2,}"
        
        # 12. 粗体滥用
        self.bold_pattern = r"\*\*[^*]+\*\*"
        
        # 13. 表情符号
        self.emoji_pattern = r"[🚀💡✅🎯📊🔥💪🌟⭐📌🔔💎🎨🏆🌈🚨📝📌]"
        
        # === 沟通模式 ===
        
        # 14. 协作沟通痕迹
        self.collaborative_patterns = [
            r"希望这.*有帮助",
            r"当然！",
            r"您说得对！",
            r"您想了解.*吗",
            r"让我知道",
            r"这是一个.*概述"
        ]
        
        # 15. 知识截止声明
        self.cutoff_patterns = [
            r"截至.*日期",
            r"根据我.*的训练",
            r"具体细节有限",
            r"根据现有信息"
        ]
        
        # 16. 谄媚语气
        self.sycophantic_patterns = [
            r"好问题！",
            r"您说得对",
            r"您提出了.*观点",
            r"这是一个.*问题"
        ]
        
        # === 填充和模糊 ===
        
        # 17. 填充词
        self.filler_patterns = [
            (r"为了达到.*目的", "为了"),
            (r"由于.*的事实", "因为"),
            (r"在此时", "现在"),
            (r"在.*的情况下", "如果"),
            (r"具有.*的能力", "能"),
            (r"需要注意的是", "")
        ]
        
        # 18. 过度模糊
        self.hedging_patterns = [
            r"可能也许",
            r"或许可能",
            r"某种程度上",
            r"在某种程度上"
        ]
        
        # 19. 通用积极结论
        self.generic_conclusion_patterns = [
            r"前景光明",
            r"激动人心的.*即将到来",
            r"迈向卓越",
            r"正确的方向迈出的.*一步"
        ]
    
    def analyze(self, text: str) -> HumanizerResult:
        """
        分析文本中的AI写作痕迹
        
        Args:
            text: 要分析的文本
            
        Returns:
            HumanizerResult: 分析结果
        """
        if not text or len(text.strip()) == 0:
            return HumanizerResult(
                ai_score=0.5,
                naturalness=0.5,
                detected_patterns=[],
                suggestions=[],
                pattern_counts={}
            )
        
        detected = []
        counts = {}
        total_penalties = 0.0
        
        # === 内容模式检测 ===
        
        # 1. 重要性强调
        sig_matches, sig_count = self._count_patterns(text, self.significance_patterns)
        if sig_matches:
            detected.extend(sig_matches)
            counts["significance"] = sig_count
            total_penalties += sig_count * 0.08
        
        # 2. 知名度强调
        notability_matches, notability_count = self._count_patterns(text, self.notability_patterns)
        if notability_matches:
            detected.extend(notability_matches)
            counts["notability"] = notability_count
            total_penalties += notability_count * 0.07
        
        # 3. -ing浅层分析
        ing_matches, ing_count = self._count_patterns(text, self.ing_analysis_patterns)
        if ing_matches:
            detected.extend(ing_matches)
            counts["ing_analysis"] = ing_count
            total_penalties += ing_count * 0.06
        
        # 4. 推销式语言
        promo_matches, promo_count = self._count_patterns(text, self.promotional_patterns)
        if promo_matches:
            detected.extend(promo_matches)
            counts["promotional"] = promo_count
            total_penalties += promo_count * 0.05
        
        # 5. 模糊引用
        vague_matches, vague_count = self._count_patterns(text, self.vague_attribution_patterns)
        if vague_matches:
            detected.extend(vague_matches)
            counts["vague_attribution"] = vague_count
            total_penalties += vague_count * 0.08
        
        # 6. 大纲式结构
        challenge_matches, challenge_count = self._count_patterns(text, self.challenge_patterns)
        if challenge_matches:
            detected.extend(challenge_matches)
            counts["challenge_section"] = challenge_count
            total_penalties += challenge_count * 0.06
        
        # === 语言模式检测 ===
        
        # 7. AI高频词汇
        ai_vocab_count = sum(1 for word in self.ai_vocabulary if word in text)
        if ai_vocab_count > 0:
            counts["ai_vocabulary"] = ai_vocab_count
            total_penalties += ai_vocab_count * 0.03
        
        # 8. 系词回避
        copula_matches, copula_count = self._count_patterns(text, self.copula_avoidance_patterns)
        if copula_matches:
            detected.extend(copula_matches)
            counts["copula_avoidance"] = copula_count
            total_penalties += copula_count * 0.05
        
        # 9. 负面对仗
        parallel_matches, parallel_count = self._count_patterns(text, self.negative_parallelism_patterns)
        if parallel_matches:
            detected.extend(parallel_matches)
            counts["negative_parallelism"] = parallel_count
            total_penalties += parallel_count * 0.06
        
        # === 风格模式检测 ===
        
        # 10. 破折号滥用
        em_dash_count = len(re.findall(self.em_dash_pattern, text))
        normal_dash_count = text.count("—")
        if normal_dash_count > 3:
            counts["em_dash_overuse"] = normal_dash_count
            total_penalties += (normal_dash_count - 3) * 0.02
        
        # 11. 粗体滥用
        bold_count = len(re.findall(self.bold_pattern, text))
        if bold_count > 2:
            counts["bold_overuse"] = bold_count
            total_penalties += (bold_count - 2) * 0.03
        
        # 12. 表情符号
        emoji_count = len(re.findall(self.emoji_pattern, text))
        if emoji_count > 0:
            counts["emoji"] = emoji_count
            total_penalties += emoji_count * 0.05
        
        # === 沟通模式检测 ===
        
        # 13. 协作痕迹
        collab_matches, collab_count = self._count_patterns(text, self.collaborative_patterns)
        if collab_matches:
            detected.extend(collab_matches)
            counts["collaborative"] = collab_count
            total_penalties += collab_count * 0.07
        
        # 14. 知识截止声明
        cutoff_matches, cutoff_count = self._count_patterns(text, self.cutoff_patterns)
        if cutoff_matches:
            detected.extend(cutoff_matches)
            counts["cutoff_disclaimer"] = cutoff_count
            total_penalties += cutoff_count * 0.04
        
        # 15. 谄媚语气
        sycoph_matches, sycoph_count = self._count_patterns(text, self.sycophantic_patterns)
        if sycoph_matches:
            detected.extend(sycoph_matches)
            counts["sycophantic"] = sycoph_count
            total_penalties += sycoph_count * 0.06
        
        # === 填充和模糊检测 ===
        
        # 16. 填充词
        filler_count = 0
        for pattern, _ in self.filler_patterns:
            if re.search(pattern, text):
                filler_count += 1
        if filler_count > 0:
            counts["filler"] = filler_count
            total_penalties += filler_count * 0.02
        
        # 17. 过度模糊
        hedging_matches, hedging_count = self._count_patterns(text, self.hedging_patterns)
        if hedging_matches:
            detected.extend(hedging_matches)
            counts["hedging"] = hedging_count
            total_penalties += hedging_count * 0.03
        
        # 18. 通用结论
        conclusion_matches, conclusion_count = self._count_patterns(text, self.generic_conclusion_patterns)
        if conclusion_matches:
            detected.extend(conclusion_matches)
            counts["generic_conclusion"] = conclusion_count
            total_penalties += conclusion_count * 0.05
        
        # === 计算最终得分 ===
        
        # AI感评分：0.0-1.0，越高越像AI
        ai_score = min(1.0, total_penalties / 2.0)  # 标准化
        
        # 自然度评分：1.0 - ai_score（越高越自然）
        naturalness = 1.0 - ai_score
        
        # 生成建议
        suggestions = self._generate_suggestions(counts, detected)
        
        return HumanizerResult(
            ai_score=round(ai_score, 4),
            naturalness=round(naturalness, 4),
            detected_patterns=list(set(detected))[:10],  # 去重，最多10个
            suggestions=suggestions,
            pattern_counts=counts
        )
    
    def _count_patterns(self, text: str, patterns: List) -> Tuple[List[str], int]:
        """统计匹配的模式"""
        matches = []
        count = 0
        
        for pattern in patterns:
            found = re.findall(pattern, text)
            if found:
                matches.extend(found if isinstance(found, list) else [found])
                count += len(found)
        
        return matches, count
    
    def _generate_suggestions(self, counts: Dict[str, int], detected: List[str]) -> List[str]:
        """生成优化建议"""
        suggestions = []
        
        if counts.get("significance", 0) > 2:
            suggestions.append("减少对【重要性】和【意义】的强调，用具体事实代替空洞表述")
        
        if counts.get("promotional", 0) > 2:
            suggestions.append("避免使用推销式语言，保持中性客观的叙述风格")
        
        if counts.get("vague_attribution", 0) > 0:
            suggestions.append("将模糊引用（如【专家认为】）替换为具体来源")
        
        if counts.get("ai_vocabulary", 0) > 3:
            suggestions.append("减少AI高频词汇的使用，尝试更多样化的表达")
        
        if counts.get("negative_parallelism", 0) > 0:
            suggestions.append("避免【不仅...而且】式的负面对仗，使用更直接的表达")
        
        if counts.get("collaborative", 0) > 0:
            suggestions.append("删除协作沟通痕迹（如【希望这有帮助】）")
        
        if counts.get("sycophantic", 0) > 0:
            suggestions.append("去除谄媚语气，保持平等客观的叙述")
        
        if counts.get("emoji", 0) > 0:
            suggestions.append("移除表情符号，使用文字表达情感")
        
        if not suggestions:
            suggestions.append("文本整体自然，可进一步增加个性化表达")
        
        return suggestions[:5]  # 最多5条建议
    
    def humanize_text(self, text: str) -> Tuple[str, List[str]]:
        """
        人性化文本（简化版）
        
        Args:
            text: 原始文本
            
        Returns:
            (修改后的文本, 修改说明列表)
        """
        changes = []
        result = text
        
        # 1. 替换填充词
        for pattern, replacement in self.filler_patterns:
            if re.search(pattern, result):
                result = re.sub(pattern, replacement, result)
                changes.append(f"简化了填充词表达")
        
        # 2. 移除表情符号
        if re.search(self.emoji_pattern, result):
            result = re.sub(self.emoji_pattern, "", result)
            changes.append("移除了表情符号")
        
        # 3. 简化负面对仗
        for pattern in self.negative_parallelism_patterns:
            if re.search(pattern, result):
                # 简化为更直接的表达
                result = re.sub(r"不仅(.*)而且(.*)", r"\1，也\2", result)
                changes.append("简化了负面对仗结构")
        
        return result, changes


# 全局技能管理器实例
_skill_manager: Optional["SkillManager"] = None


def get_skill_manager() -> "SkillManager":
    """获取全局技能管理器实例"""
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager()
    return _skill_manager


# === 创意写作技能集成 ===

@dataclass
class FictionWritingResult:
    """创意写作技能结果"""
    structure_score: float  # 结构评分
    character_depth: float  # 人物深度
    show_vs_tell: float  # 展示vs告知
    pacing: float  # 节奏
    world_building: float  # 世界观构建
    suggestions: List[str]  # 优化建议


class FictionWritingSkill:
    """
    创意写作技能集成
    
    基于grey-haven-creative-writing技能的专业小说写作指导
    
    核心功能：
    1. 故事结构分析
    2. 人物发展评估
    3. 展示vs告知检测
    4. 节奏分析
    5. 世界观构建检查
    """
    
    def __init__(self, config: Optional[SkillConfig] = None):
        self.config = config or SkillConfig(name="fiction-writing")
        self._init_guidelines()
        logger.info("FictionWriting技能初始化完成")
    
    def _init_guidelines(self):
        """初始化写作指南"""
        
        # === 展示vs告知 ===
        self.tell_patterns = [
            r"他感到.*",
            r"她觉得.*",
            r"他是.*的人",
            r"她是一个.*",
            r"很.*",
            r"非常.*",
            r"十分.*",
            r"极其.*"
        ]
        
        # === 节奏控制 ===
        # 快节奏：短句、动作
        # 慢节奏：长句、描写
        
        # === 人物塑造 ===
        self.character_depth_indicators = {
            "surface": ["外貌", "穿着", "身材", "长相"],
            "social": ["身份", "职业", "地位", "关系"],
            "private": ["害怕", "渴望", "秘密", "内心"],
            "core": ["信念", "创伤", "价值观"]
        }
        
        # === 世界观构建 ===
        self.worldbuilding_elements = [
            "地理", "气候", "社会", "权力", "阶级",
            "魔法", "科技", "经济", "资源", "历史"
        ]
        
        # === 常见问题 ===
        self.common_pitfalls = {
            "info_dump": {
                "patterns": [r".{200,}的介绍", r"原来.*是.*"],
                "suggestion": "将信息融入动作和对话中展示"
            },
            "purple_prose": {
                "patterns": [r"(\S{4,}的){3,}"],
                "suggestion": "减少50%的形容词和副词"
            },
            "passive_protagonist": {
                "patterns": [r"被迫", r"不得不", r"只能"],
                "suggestion": "给主角更多主动选择和行动"
            },
            "floating_heads": {
                "patterns": [r"\"[^\"]+\"[^。]{0,20}\"[^\"]+\""],
                "suggestion": "为对话添加环境描写和动作"
            }
        }
    
    # ========== V1.4.0 新增：数据提取与增强评估 ==========
    
    def _extract_characters(self, raw_characters: List) -> List[Dict]:
        """
        从原始人物数据中提取结构化人物信息
        
        兼容多种数据格式：
        - 格式A: {"name": "...", "personality": "...", "speaking_style": "..."}
        - 格式B: {"姓名": "...", "性格": "...", "说话风格": "..."}
        - 格式C: 嵌套在character_data中的结构
        
        Args:
            raw_characters: 原始人物列表
            
        Returns:
            List[Dict]: 标准化的 [{"name":..., "personality":..., "speaking_style":...}, ...]
        """
        if not raw_characters:
            return []
        
        extracted = []
        for char in raw_characters:
            if not isinstance(char, dict):
                continue
            
            # 标准化字段名（兼容中英文key）
            name = char.get("name") or char.get("姓名") or char.get("名字") or ""
            personality = (
                char.get("personality") or char.get("性格") 
                or char.get("personality_traits") or ""
            )
            speaking_style = (
                char.get("speaking_style") or char.get("speakingStyle")
                or char.get("说话风格") or char.get("dialogue_style") or ""
            )
            
            # 提取层次信息
            layers = char.get("layers") or char.get("层次") or {}
            core_belief = (
                char.get("core_belief") or char.get("核心信念")
                or (layers.get("core") if isinstance(layers, dict) else None)
                or ""
            )
            
            # 只保留有名字的有效人物
            if name:
                extracted.append({
                    "name": name,
                    "personality": personality,
                    "speaking_style": speaking_style,
                    "core_belief": core_belief,
                    "_raw": char  # 保留原始引用以便扩展
                })
        
        return extracted
    
    def _extract_worldview(self, raw_worldview: Dict) -> Dict:
        """
        从原始世界观数据中提取关键元素
        
        兼容多种格式：
        - 格式A: {"elements": [...], "rules": [...]}
        - 格式B: 直接包含设定键值对
        
        Args:
            raw_worldview: 原始世界观数据
            
        Returns:
            Dict: 标准化的世界观数据
        """
        if not raw_worldview or not isinstance(raw_worldview, dict):
            return {}
        
        extracted = {}
        
        # 元素列表
        elements = raw_worldview.get("elements") or []
        if isinstance(elements, list):
            extracted["elements"] = [e.get("name", str(e)) if isinstance(e, dict) else str(e) 
                                      for e in elements]
        elif isinstance(elements, str):
            extracted["elements"] = [elements]
        
        # 规则列表
        rules = raw_worldview.get("rules") or []
        if isinstance(rules, list):
            extracted["rules"] = [r.get("description", str(r)) if isinstance(r, dict) else str(r)
                                for r in rules]
        elif isinstance(rules, str):
            extracted["rules"] = [rules]
        
        # 设定关键词（从顶层key提取）
        setting_keywords = []
        for key in ["magic_system", "geography", "social_structure", 
                     "魔法体系", "地理设定", "社会制度", "power_system"]:
            val = raw_worldview.get(key)
            if val and isinstance(val, str):
                setting_keywords.append(val)
            elif val and isinstance(val, list):
                setting_keywords.extend(str(v) for v in val)
        extracted["setting_keywords"] = setting_keywords
        
        # 保留原始数据作为备用
        extracted["_raw"] = raw_worldview
        
        return extracted
    
    def _extract_style(self, raw_style: Dict) -> List[str]:
        """
        从风格数据中提取特征关键词
        
        Args:
            raw_style: 风格数据
            
        Returns:
            List[str]: 风格特征词列表
        """
        if not raw_style or not isinstance(raw_style, dict):
            return []
        
        keywords = raw_style.get("keywords") or raw_style.get("特征词") or []
        if isinstance(keywords, str):
            keywords = keywords.split("、") if "、" in keywords else [keywords]
        
        return keywords if isinstance(keywords, list) else []
    
    def _evaluate_character_depth_v2(self, content: str, characters: List[Dict], 
                                       fallback: List = None) -> float:
        """
        V1.4.0 增强版人物深度评估
        
        使用真实项目人物数据进行四层次分析：
        - Surface层：外表/举止描述
        - Social层：社会角色/关系提及
        - Private层：内心/恐惧/渴望展示
        - Core层：核心信念/价值观体现
        
        Args:
            content: 章节文本
            characters: 已标准化的角色列表（_extract_characters输出）
            fallback: 原始fallback数据
            
        Returns:
            float: 深度评分 0.0-1.0
        """
        if not characters and fallback:
            # 降级到旧版逻辑
            return self._evaluate_character_depth_fallback(content, fallback)
        
        if not characters:
            return 0.7
        
        total_scores = []
        
        for char in characters:
            name = char["name"]
            
            # 如果人物不在本章中出现，跳过
            if name not in content:
                continue
            
            depth_score = 0.0
            found_layers = 0
            
            # 1. Surface层检测（外表/动作）
            surface_indicators = ["眼睛", "头发", "脸", "手", "身", "穿", "站", "走", "看"]
            has_surface = any(ind in content for ind in surface_indicators[:5])
            if has_surface:
                depth_score += 0.10
                found_layers += 1
            
            # 2. Social层检测（身份/关系）
            social_data = char.get("speaking_style", "")
            if social_data and any(word in content for word in social_data.split("、")[:3]):
                depth_score += 0.15
                found_layers += 1
            
            # 3. Private层检测（内心活动）— 关键区分点
            personality_text = char.get("personality", "")
            if personality_text:
                # 将性格描述拆分为关键词并检查
                p_keywords = re.split(r'[，,、；;]|是|的', personality_text)
                inner_matches = sum(1 for kw in p_keywords 
                                  if len(kw) >= 2 and kw.strip() in content)
                if inner_matches > 0:
                    depth_score += min(0.25, inner_matches * 0.08)
                    found_layers += 1
                
                # 内心独白模式检测
                inner_patterns = [f"{name}心里", f"{name}想", f"{name}觉得", 
                                 f"{name}暗自", "心中", "心想", "默默"]
                if any(p in content for p in inner_patterns):
                    depth_score += 0.10
                    found_layers += 1
            
            # 4. Core层检测（核心信念/价值观）
            core_belief = char.get("core_belief", "")
            if core_belief and core_belief in content:
                depth_score += 0.20
                found_layers += 1
            elif any(p in content for p in ["相信", "坚持", "绝不", "必须", "无论如何"]):
                # 通用核心层表达
                depth_score += 0.05
                found_layers += 1
            
            # 存在性基础分 + 层次加分
            base_score = 0.30  # 人物出现即给基础分
            final_score = base_score + depth_score
            total_scores.append(min(1.0, final_score))
        
        return sum(total_scores) / len(total_scores) if total_scores else 0.7
    
    def _evaluate_character_depth_fallback(self, content: str, characters: List) -> float:
        """降级版人物深度评估（兼容旧版逻辑）"""
        if not characters:
            return 0.7
        
        depth_layers = {
            "surface": 0, "social": 0, "private": 0, "core": 0
        }
        
        for layer, indicators in self.character_depth_indicators.items():
            for indicator in indicators:
                if indicator in content:
                    depth_layers[layer] += 1
        
        weights = {"surface": 0.1, "social": 0.2, "private": 0.3, "core": 0.4}
        total_score = 0.0
        for layer, count in depth_layers.items():
            if count > 0:
                total_score += weights[layer] * min(1.0, count / 3)
        
        return min(1.0, total_score + 0.3)
    
    def _evaluate_worldbuilding_v2(self, content: str, worldview: Dict, 
                                     fallback: Dict = None) -> float:
        """
        V1.4.0 增强版世界观构建评估
        
        使用真实项目世界观数据进行精准匹配：
        - 世界观元素关键词匹配
        - 设定细节融入度检测
        - 规则一致性验证
        
        Args:
            content: 章节文本
            worldview: 已标准化的世界观数据（_extract_worldview输出）
            fallback: 原始fallback数据
            
        Returns:
            float: 构建评分 0.0-1.0
        """
        if not worldview and fallback:
            return self._evaluate_worldbuilding_fallback(content, fallback)
        
        if not worldview:
            return 0.7
        
        score = 0.40  # V1.4.0：提高基础分（有数据时）
        
        # 1. 元素融入度
        elements = worldview.get("elements", [])
        if elements:
            matched = sum(1 for elem in elements if elem and len(elem) >= 2 and elem in content)
            element_ratio = matched / max(1, len(elements))
            score += element_ratio * 0.30
        
        # 2. 设定关键词融入度
        setting_keywords = worldview.get("setting_keywords", [])
        if setting_keywords:
            kw_matched = sum(1 for kw in setting_keys 
                            if len(str(kw)) >= 2 and str(kw) in content 
                            for kw in setting_keywords[:5])
            score += min(0.20, kw_matched * 0.04)
        
        # 3. 规则体现（不违反规则加分）
        rules = worldview.get("rules", [])
        if rules:
            # 不做违规扣分（因为很难精确检测），只检查是否有规则相关内容
            rule_related = sum(1 for rule in rules 
                             if len(rule) >= 4 and any(w in content for w in rule[:4]))
            if rule_related > 0:
                score += 0.10
        
        return min(1.0, score)
    
    def _evaluate_worldbuilding_fallback(self, content: str, worldview: Dict) -> float:
        """降级版世界观评估（兼容旧版逻辑）"""
        if not worldview:
            return 0.7
        
        score = 0.5
        elements_found = 0
        for element in self.worldbuilding_elements:
            if element in content:
                elements_found += 1
        
        element_ratio = elements_found / len(self.worldbuilding_elements)
        score += element_ratio * 0.3
        
        return min(1.0, score)
    
    def _evaluate_outline_alignment(self, content: str, outline: Dict) -> float:
        """
        V1.4.0 新增：大纲契合度评估
        
        检查生成内容是否覆盖大纲中的关键情节节点
        """
        if not outline:
            return 0.7
        
        key_events = outline.get("key_events") or outline.get("events") or []
        if not key_events:
            return 0.7
        
        matched = sum(1 for event in key_events if event and event in content)
        ratio = matched / len(key_events)
        
        return max(0.5, min(1.0, 0.5 + ratio * 0.5))
    
    def _evaluate_style_match(self, content: str, style_keywords: List[str]) -> float:
        """
        V1.4.0 新增：风格匹配度评估
        
        检查生成内容是否使用了风格样本中的特征表达
        """
        if not style_keywords:
            return 0.7
        
        matched = sum(1 for kw in style_keywords if kw and len(kw) >= 2 and kw in content)
        ratio = matched / len(style_keywords)
        
        return max(0.5, min(1.0, 0.5 + ratio * 0.5))
    
    def _generate_suggestions_v2(self, structure, character, show_tell, pacing, world,
                                  content, characters_data=None, worldview_data=None,
                                  outline_data=None, has_real_data=False) -> List[str]:
        """
        V1.4.0 增强版建议生成
        
        当有真实项目数据时，生成更有针对性的建议
        """
        suggestions = []
        
        # 基础建议（保留原有逻辑）
        if structure < 0.6:
            suggestions.append("场景结构不完整。建议：明确角色目标、添加冲突、给出结局")
        
        if show_tell < 0.6:
            suggestions.append("\"告知\"过多。建议：用具体动作和感官细节替代抽象描述")
        
        if pacing < 0.6:
            suggestions.append("节奏单一。建议：变化句长、穿插动作与描写、控制段落长度")
        
        if world < 0.6:
            suggestions.append("世界观体现不足。建议：通过角色互动展示环境细节")
        
        # V1.4.0 增强建议（基于真实数据）
        if has_real_data and character < 0.7 and characters_data:
            # 找出表现最弱的人物
            weak_chars = [c["name"] for c in characters_data 
                        if c["name"] and c["name"] in content]
            if weak_chars:
                char_names = "、".join(weak_chars[:2])
                suggestions.append(
                    f"「{char_names}」的人物刻画可加深：尝试添加内心独白或展示其核心动机"
                )
        
        if has_real_data and world < 0.7 and worldview_data:
            elements = worldview_data.get("elements", [])[:3]
            if elements:
                missing = [e for e in elements if e and e not in content]
                if missing:
                    suggestions.append(
                        f"可融入更多世界观元素：{missing[0]}等设定的自然展现能增强沉浸感"
                    )
        
        # 检测常见问题（保留原有逻辑）
        for pitfall_name, pitfall_info in self.common_pitfalls.items():
            for pattern in pitfall_info["patterns"]:
                if re.search(pattern, content):
                    suggestions.append(f"检测到{pitfall_name}：{pitfall_info['suggestion']}")
                    break
        
        return suggestions[:6]  # V1.4.0：最多6条（增加2条数据驱动建议）
    
    def analyze(self, content: str, context: Optional[Dict] = None) -> FictionWritingResult:
        """
        分析小说内容质量
        
        V1.4.0 增强：
        现在能够充分利用完整项目数据（世界观/人设/大纲/风格/前文），
        从"通用模板检测"升级为"基于项目设定精准评估"。
        
        Args:
            content: 小说文本
            context: 上下文信息（V1.4.0 支持完整数据）
                - characters: List[Dict] 人物数据（姓名/性格/说话风格/层次信息）
                - worldview: Dict 世界观数据（元素列表/规则/设定细节）
                - outline: Dict 大纲数据（关键事件/情节节点）
                - style_profile: Dict 风格数据（关键词/句式特征）
                - previous_chapters: List[str] 前文内容（用于衔接分析）
                
        Returns:
            FictionWritingResult: 分析结果
        """
        context = context or {}
        
        # V1.4.0：提取结构化数据
        characters_data = self._extract_characters(context.get("characters", []))
        worldview_data = self._extract_worldview(context.get("worldview", {}))
        style_keywords = self._extract_style(context.get("style_profile", {}))
        
        # 1. 结构评分
        structure_score = self._evaluate_structure(content)
        
        # 2. 人物深度（V1.4.0：使用真实人物数据）
        character_depth = self._evaluate_character_depth_v2(
            content, 
            characters_data,
            fallback=context.get("characters", [])
        )
        
        # 3. 展示vs告知
        show_vs_tell = self._evaluate_show_vs_tell(content)
        
        # 4. 节奏
        pacing = self._evaluate_pacing(content)
        
        # 5. 世界观构建（V1.4.0：使用真实世界观数据）
        world_building = self._evaluate_worldbuilding_v2(
            content, 
            worldview_data,
            fallback=context.get("worldview", {})
        )
        
        # V1.4.0 新增：基于大纲和风格的辅助评分
        outline_alignment = self._evaluate_outline_alignment(content, context.get("outline", {}))
        style_match = self._evaluate_style_match(content, style_keywords)
        
        # 生成建议（V1.4.0：融入项目数据建议）
        suggestions = self._generate_suggestions_v2(
            structure_score, character_depth, show_vs_tell, 
            pacing, world_building, content,
            characters_data=characters_data,
            worldview_data=worldview_data,
            outline_data=context.get("outline", {}),
            has_real_data=bool(characters_data or worldview_data)
        )
        
        return FictionWritingResult(
            structure_score=structure_score,
            character_depth=character_depth,
            show_vs_tell=show_vs_tell,
            pacing=pacing,
            world_building=world_building,
            suggestions=suggestions
        )
    
    def _evaluate_structure(self, content: str) -> float:
        """
        评估故事结构
        
        检查：
        - 场景是否有明确目标
        - 是否有冲突
        - 是否有结局
        """
        score = 0.5
        
        # 检查场景结构元素
        has_goal = bool(re.search(r"想|要|希望|目标|目的", content))
        has_conflict = bool(re.search(r"但|却|然而|冲突|争|斗", content))
        has_outcome = bool(re.search(r"终于|最后|结果|结局|成功|失败", content))
        
        if has_goal:
            score += 0.15
        if has_conflict:
            score += 0.20
        if has_outcome:
            score += 0.15
        
        return min(1.0, score)
    
    def _evaluate_character_depth(self, content: str, characters: List) -> float:
        """
        评估人物塑造深度
        
        检查四个层次：
        - Surface: 外表、举止
        - Social: 角色、关系
        - Private: 恐惧、渴望
        - Core: 信念、创伤
        """
        if not characters:
            return 0.7
        
        depth_layers = {
            "surface": 0,
            "social": 0,
            "private": 0,
            "core": 0
        }
        
        for layer, indicators in self.character_depth_indicators.items():
            for indicator in indicators:
                if indicator in content:
                    depth_layers[layer] += 1
        
        # 计算深度分数
        # Core > Private > Social > Surface
        weights = {"surface": 0.1, "social": 0.2, "private": 0.3, "core": 0.4}
        
        total_score = 0.0
        for layer, count in depth_layers.items():
            if count > 0:
                total_score += weights[layer] * min(1.0, count / 3)
        
        return min(1.0, total_score + 0.3)  # 基础分0.3
    
    def _evaluate_show_vs_tell(self, content: str) -> float:
        """
        评估展示vs告知
        
        检测"告知"模式，越少越好
        """
        tell_count = 0
        
        for pattern in self.tell_patterns:
            matches = re.findall(pattern, content)
            tell_count += len(matches)
        
        # 计算每千字的告知次数
        thousand_chars = len(content) / 1000
        tell_per_thousand = tell_count / max(1, thousand_chars)
        
        # 评分：每千字少于2次为优秀，多于10次为差
        if tell_per_thousand < 2:
            return 1.0
        elif tell_per_thousand < 5:
            return 0.8
        elif tell_per_thousand < 10:
            return 0.6
        else:
            return max(0.3, 1.0 - tell_per_thousand * 0.05)
    
    def _evaluate_pacing(self, content: str) -> float:
        """
        评估节奏
        
        分析：
        - 句长变化
        - 段落长度
        - 动作vs描写比例
        """
        sentences = re.split(r'[。！？]', content)
        sentences = [s for s in sentences if s.strip()]
        
        if not sentences:
            return 0.5
        
        # 句长变化
        lengths = [len(s) for s in sentences]
        avg_length = sum(lengths) / len(lengths)
        variance = max(lengths) - min(lengths) if lengths else 0
        
        # 评分
        score = 0.5
        
        # 平均句长15-30字为佳
        if 15 <= avg_length <= 30:
            score += 0.2
        
        # 句长变化大表示节奏丰富
        if variance > 30:
            score += 0.2
        elif variance > 15:
            score += 0.1
        
        return min(1.0, score)
    
    def _evaluate_worldbuilding(self, content: str, worldview: Dict) -> float:
        """
        评估世界观构建
        
        检查：
        - 世界观元素是否体现
        - 是否自然融入
        """
        if not worldview:
            return 0.7
        
        score = 0.5
        
        # 检查世界观元素
        elements_found = 0
        for element in self.worldbuilding_elements:
            if element in content:
                elements_found += 1
        
        # 评分
        element_ratio = elements_found / len(self.worldbuilding_elements)
        score += element_ratio * 0.3
        
        return min(1.0, score)
    
    def _generate_suggestions(self, structure, character, show_tell, pacing, world, content) -> List[str]:
        """生成优化建议"""
        suggestions = []
        
        if structure < 0.6:
            suggestions.append("场景结构不完整。建议：明确角色目标、添加冲突、给出结局")
        
        if character < 0.6:
            suggestions.append("人物塑造较浅。建议：添加内心独白、展示核心信念、揭示隐藏动机")
        
        if show_tell < 0.6:
            suggestions.append("\"告知\"过多。建议：用具体动作和感官细节替代抽象描述")
        
        if pacing < 0.6:
            suggestions.append("节奏单一。建议：变化句长、穿插动作与描写、控制段落长度")
        
        if world < 0.6:
            suggestions.append("世界观体现不足。建议：通过角色互动展示环境细节")
        
        # 检查常见问题
        for pitfall_name, pitfall_info in self.common_pitfalls.items():
            for pattern in pitfall_info["patterns"]:
                if re.search(pattern, content):
                    suggestions.append(f"检测到{pitfall_name}：{pitfall_info['suggestion']}")
                    break
        
        return suggestions[:5]
    
    def get_fiction_guidelines(self) -> Dict[str, Any]:
        """
        获取小说写作指南
        
        Returns:
            Dict: 包含结构、人物、视角等写作指南
        """
        return {
            "structure": {
                "three_act": "第一幕(25%)建置 → 第二幕(50%)对抗 → 第三幕(25%)解决",
                "scene_pattern": "目标 → 冲突 → 结局",
                "sequel_pattern": "反应 → 困境 → 决定"
            },
            "character": {
                "layers": ["表面(外表举止)", "社会(角色关系)", "私人(恐惧渴望)", "核心(信念创伤)"],
                "arc_types": ["正向弧(成长)", "负向弧(堕落)", "平坦弧(改变世界)"]
            },
            "dialogue": {
                "principles": [
                    "每个角色有独特声音",
                    "潜台词比明说更有力",
                    "对话推进情节或揭示人物",
                    "用动作节拍代替对话标签"
                ]
            },
            "show_vs_tell": {
                "show": "情感时刻、关键动作、感官体验",
                "tell": "过渡、简短背景、时间流逝"
            },
            "pacing": {
                "fast": "短句、动作、紧张",
                "slow": "长句、反思、描写"
            },
            "pitfalls": {
                "info_dump": "信息倾倒 → 融入动作对话",
                "purple_prose": "华丽辞藻 → 减少50%修饰词",
                "passive_protagonist": "被动主角 → 增加主动选择",
                "floating_heads": "漂浮的头 → 为对话添加环境"
            }
        }


# === 扩展SkillManager ===

class SkillManager:
    """
    技能管理器（扩展版）
    
    统一管理所有外部技能的加载、初始化和调用
    
    支持的技能：
    - humanizer: 去AI感检测
    - fiction-writing: 创意写作指导
    """
    
    def __init__(self):
        self._skills: Dict[str, Any] = {}
        self._configs: Dict[str, SkillConfig] = {}
        
        # 注册默认技能
        self._register_default_skills()
        
        logger.info("技能管理器初始化完成")
    
    def _register_default_skills(self):
        """注册默认技能"""
        # 注册humanizer技能
        self._configs["humanizer"] = SkillConfig(
            name="humanizer",
            enabled=True,
            priority=10,
            options={
                "detect_ai_patterns": True,
                "generate_suggestions": True
            }
        )
        
        # 注册fiction-writing技能
        self._configs["fiction-writing"] = SkillConfig(
            name="fiction-writing",
            enabled=True,
            priority=8,
            options={
                "analyze_structure": True,
                "analyze_character": True
            }
        )
    
    def get_skill(self, skill_name: str) -> Optional[Any]:
        """
        获取技能实例
        
        Args:
            skill_name: 技能名称
            
        Returns:
            技能实例，如果不存在则返回None
        """
        # 检查配置
        config = self._configs.get(skill_name)
        if not config or not config.enabled:
            return None
        
        # 延迟加载
        if skill_name not in self._skills:
            self._skills[skill_name] = self._load_skill(skill_name, config)
        
        return self._skills.get(skill_name)
    
    def _load_skill(self, skill_name: str, config: SkillConfig) -> Optional[Any]:
        """
        加载技能
        
        Args:
            skill_name: 技能名称
            config: 技能配置
            
        Returns:
            技能实例
        """
        try:
            if skill_name == "humanizer":
                return HumanizerSkill(config)
            
            if skill_name == "fiction-writing":
                return FictionWritingSkill(config)
            
            logger.warning(f"未知技能: {skill_name}")
            return None
            
        except Exception as e:
            logger.error(f"加载技能 {skill_name} 失败: {e}")
            return None
    
    def analyze_ai_content(self, text: str) -> HumanizerResult:
        """
        使用humanizer技能分析AI内容
        
        Args:
            text: 要分析的文本
            
        Returns:
            HumanizerResult: 分析结果
        """
        skill = self.get_skill("humanizer")
        
        if skill:
            return skill.analyze(text)
        else:
            # 降级：返回默认结果
            return HumanizerResult(
                ai_score=0.5,
                naturalness=0.5,
                detected_patterns=[],
                suggestions=["技能不可用"],
                pattern_counts={}
            )
    
    def analyze_fiction_writing(self, text: str, context: Optional[Dict] = None) -> FictionWritingResult:
        """
        使用fiction-writing技能分析小说写作
        
        Args:
            text: 要分析的文本
            context: 上下文信息
            
        Returns:
            FictionWritingResult: 分析结果
        """
        skill = self.get_skill("fiction-writing")
        
        if skill:
            return skill.analyze(text, context)
        else:
            # 降级：返回默认结果
            return FictionWritingResult(
                structure_score=0.5,
                character_depth=0.5,
                show_vs_tell=0.5,
                pacing=0.5,
                world_building=0.5,
                suggestions=["技能不可用"]
            )
    
    def is_skill_available(self, skill_name: str) -> bool:
        """检查技能是否可用"""
        return skill_name in self._configs and self._configs[skill_name].enabled
    
    def get_available_skills(self) -> List[str]:
        """获取可用技能列表"""
        return [name for name, config in self._configs.items() if config.enabled]
    
    # === technique-monitor 技能扩展（V1.5.0）===
    
    def analyze_techniques(self, content: str, context: Optional[Dict] = None) -> 'TechniqueMonitorResult':
        """
        使用技巧监测技能分析文本中的高级写作技巧应用
        
        Args:
            content: 要分析的文本内容
            context: 可选上下文（包含世界观/人设/大纲等）
            
        Returns:
            TechniqueMonitorResult: 技巧监测结果（含评分/检测列表/指导文本）
        """
        try:
            skill = TechniqueMonitorSkill()
            return skill.analyze(content, context or {})
        except Exception as e:
            logger.error(f"技巧监测分析失败: {e}")
            return TechniqueMonitorResult(
                overall_score=0.0, category_scores={}, detected_techniques=[],
                missing_techniques=[], technique_count=0, total_available=0,
                guidance_text="", suggestions=[f"技巧监测异常: {str(e)}"]
            )
    
    def get_technique_guidance(self, content: str, context: Optional[Dict] = None) -> str:
        """
        获取用于生成环的写作技巧指导文本
        
        这是核心注入方法：将检测结果转化为LLM可理解的写作指令。
        
        Args:
            content: 当前已生成的内容（可为空字符串表示首次生成）
            context: 可选上下文
            
        Returns:
            str: 格式化的技巧指导文本（可直接追加到prompt末尾）
        """
        result = self.analyze_techniques(content, context)
        return result.guidance_text
    
    def get_technique_summary(self, content: str) -> str:
        """获取技巧检测摘要文本（用于UI显示）"""
        result = self.analyze_techniques(content)
        try:
            skill = TechniqueMonitorSkill()
            return skill.get_active_techniques_summary(result)
        except Exception:
            if result.detected_techniques:
                top = result.detected_techniques[:3]
                names = [d["name"] for d in top]
                return f"检测到{result.technique_count}个技巧: {', '.join(names)}"
            return "未检测到高级写作技巧"


# ========== 技巧监测技能集成（V1.5.0 新增）==========

@dataclass
class TechniqueMonitorResult:
    """技巧监测技能结果"""
    overall_score: float  # 总体技巧应用评分 0.0-1.0
    category_scores: Dict[str, float]  # 各分类评分
    detected_techniques: List[Dict]  # 检测到的技巧（含名称/分类/置信度/证据）
    missing_techniques: List[str]  # 未检测到的技巧名列表
    technique_count: int  # 检测到的技巧数量
    total_available: int  # 知识库总技巧数
    guidance_text: str  # 生成环指导文本
    suggestions: List[str]  # 优化建议


class TechniqueMonitorSkill:
    """
    技巧监测技能（V1.5.0 核心新增）
    
    基于知识库真实数据的高级写作技巧深度监测与生成指导系统。
    
    核心能力：
    1. 六大分类58个技巧的深度检测（超越简单关键词匹配）
    2. 生成环注入：将选定技巧转化为LLM可理解的写作指令
    3. 专项强化：针对每个技巧提供结构级/语言级/修辞级的多层检测
    
    知识库6大分类（58个技巧）：
    - advanced (20): 不可靠叙述/拼图式叙事/脚注叙事/负空间叙事/侵入式叙述者等
    - narrative (7): 叙事时间与时长/视角与聚焦/空间与场景/声音与距离等
    - structure (3): 叙事弧线/多线叙事/虫洞句
    - rhetoric (10): 反讽悖论/隐喻转喻/通感置换/排比层递等
    - description (13): 感官通感/心理意识流/陌生化/羽毛句/涟漪句等
    - special_sentence (5): 顿呼法/自由间接引语/顿悟/否定句/托心句
    
    设计原则：
    - 零外部依赖：完全基于知识库本地JSON数据
    - 延迟加载：首次使用时才加载知识库
    - 降级安全：知识库不可用时自动降级为内置检测
    """
    
    # 分类定义（与knowledge_base文件对应）
    CATEGORIES = ["advanced", "narrative", "structure", "rhetoric", "description", "special_sentence"]
    
    # 分类中文显示名
    CATEGORY_LABELS = {
        "advanced": "高级叙事",
        "narrative": "叙事学",
        "structure": "结构",
        "rhetoric": "修辞",
        "description": "描写",
        "special_sentence": "特殊句式"
    }
    
    def __init__(self, config: Optional[SkillConfig] = None):
        self.config = config or SkillConfig(name="technique-monitor")
        self._kb_data: Optional[Dict[str, List[Dict]]] = None
        self._kb_loaded = False
        self._init_advanced_patterns()
        logger.info("TechniqueMonitor技能初始化完成")
    
    def _get_kb_path(self) -> Path:
        """获取知识库路径"""
        return Path(__file__).parent.parent.parent / "data" / "knowledge" / "writing_technique"
    
    def _load_kb_data(self) -> Dict[str, List[Dict]]:
        """
        加载知识库写作技巧数据（延迟加载，带缓存）
        
        Returns:
            Dict: {category_name: [knowledge_point_dict, ...]}
        """
        if self._kb_loaded and self._kb_data is not None:
            return self._kb_data
        
        kb_path = self._get_kb_path()
        data = {}
        
        try:
            for cat in self.CATEGORIES:
                fpath = kb_path / f"{cat}.json"
                if fpath.exists():
                    with open(fpath, 'r', encoding='utf-8') as f:
                        raw = json.load(f)
                    pts = raw.get("knowledge_points", [])
                    if pts:
                        data[cat] = pts
            
            if data:
                total = sum(len(v) for v in data.values())
                logger.info(f"知识库加载成功：{len(data)}个分类/{total}个技巧")
            
            self._kb_data = data
            self._kb_loaded = True
            
        except Exception as e:
            logger.warning(f"知识库加载失败: {e}，将使用内置检测")
            self._kb_data = {}
            self._kb_loaded = True
        
        return self._kb_data
    
    def _init_advanced_patterns(self):
        """
        初始化高级技巧的结构化检测模式
        
        超越关键词匹配，检测技巧的"结构性特征"
        例如：不可靠叙述需要检测叙述者矛盾/信息隐瞒等模式
              脚注叙事需要检测文本中的注释性插入
              自由间接引语需要检测人称混用模式
        """
        # === advanced 分类：结构性检测 ===
        self.advanced_patterns = {
            "不可靠叙述": {
                "signals": [
                    r"我(?!.*?确实|.*?其实).*?(?:以为|以为|觉得|记得).*?但",  # 记忆偏差
                    r"(?:现在想来|事后才意识到|后来才知道)",  # 后知后觉
                    r"(?:也许|可能|大概).*?(?:是这样吧|没错)",  # 不确定表达
                    r"(?:他们都说|大家都说).*?但我(?!完全相信)",  # 与众不同
                ],
                "anti_signals": [],  # 反信号暂留
                "weight": 1.0,
            },
            "拼图式叙事（非线性拼贴）": {
                "signals": [
                    r"(?:三年前|那时|当初|多年后|就在那一刻)",
                    r"(?:话说|再说|回到|与此同时).{0,10}(?:另一边|别处)",
                    r"——.{0,30}——",  # 破折号片段拼接
                ],
                "weight": 1.0,
            },
            "自由间接引语": {
                "signals": [
                    r"(?:他想|她想|他觉?得|她觉得)(?!说|道|：)",  # 第三人称内心
                    r"(?:为什么|怎么|难道)(?:不|非|何)[^。，]{0,15}[？？]",  # 内心疑问
                    r"[^“\"]{0,20}(?:心想|暗自|心中一紧)[^。]{0,30}",  # 内心活动
                ],
                "weight": 1.0,
            },
            "感官过载式描写": {
                "signals": [
                    r"(?:同时|一下子|瞬间).{0,8}(?:看到|听到|闻到|感到)",
                    r".{0,10}(?:视觉|听觉|嗅觉|触觉).{0,5}(?:同时|一股脑)",
                    r"(?:铺天盖地|蜂拥而至|扑面而来| overwhelming)",
                ],
                "weight": 0.9,
            },
            "负空间叙事": {
                "signals": [
                    r"(?:没有|不曾|从未).{0,15}(?:说话|出现|提及|回应)",
                    r"(?:沉默|安静|寂静).{0,20}(?:代替|胜过|比.*更)",
                    r"(?:省略|略过|跳过).{0,15}(?:不言而喻|不必多说)",
                    r"\.{4,}",  # 省略号暗示留白
                ],
                "weight": 1.0,
            },
            "嵌套叙事的元结构": {
                "signals": [
                    r"(?:据说|传闻|传说|故事是这样的)",
                    r"(?:让我从头说起|事情要从.*说起)",
                    r"「[^」]{20,}」",  # 长引用（可能是内嵌故事）
                    r"(?:正如.*所说|就像.*讲的)",
                ],
                "weight": 0.9,
            },
            "潜文本对话": {
                "signals": [
                    r"「[^」]*」[^。「」]{0,30}(?:他|她)(?:没说|没回答|沉默了|欲言又止)",
                    r"「[^」]{2,}?」\s*(?:——|但|然而|其实)",
                    r"(?:话到嘴边|咽了回去|忍住没说|没说出口)",
                    r"「[^」]*?」\s*[^「」]*(?:对视|交换眼神|意味深长地)",
                ],
                "weight": 1.0,
            },
            "回声结构": {
                "signals": [],
                "weight": 0.8,  # 需要跨段落分析，简化版仅做标记
            },
            "侵入式叙述者": {
                "signals": [
                    r"(?:读者朋友|各位|亲爱的 reader|你可能会问)",
                    r"(?:这里需要说明|让我们先暂停|插一句)",
                    r"(?:不得不说|坦率地说|说实话)",
                ],
                "weight": 0.9,
            },
            "第二人称强制代入": {
                "signals": [
                    r"\b你\b.{0,10}(?:走|看|想|感觉|知道|明白)",
                    r"^(?:你|想象一下|假如你是)",
                ],
                "weight": 1.0,
            },
            "伪文献叙事": {
                "signals": [
                    r"(?:据.*记载|史料显示|档案编号|日记摘录)",
                    r"(?:——摘自|——节选|——整理)",
                    r"(?:信件|电报|病历|审讯记录)",
                ],
                "weight": 1.0,
            },
            "脚注叙事": {
                "signals": [
                    r"[①②③④⑤⑥⑦⑧⑨⑩]",  # 圈码脚注
                    r"\[\d+\]",  # 方括号数字
                    r"(?:注|详见|参考).{0,10}(?:第.*页|附录)",
                ],
                "weight": 0.95,
            },
            "集体视角叙事": {
                "signals": [
                    r"\b我们\b.{0,15}(?:都知道|都认为|一起)",
                    r"(?:大家|所有人|人们).{0,10}(?:记得|见证)",
                ],
                "weight": 0.9,
            },
            "物件视角叙事": {
                "signals": [
                    r"(?:从.*的角度|在.*眼中|以.*的视角)",
                    r"(?:它|这东西|此物).(?:看到了|感知到|经历)",
                ],
                "weight": 0.9,
            },
            "神话原型置换": {
                "signals": [
                    r"(?:英雄之旅|启程|考验|归来|重生|牺牲|救赎)",
                    r"(?:如同.*传说中的|仿佛.*史诗般)",
                    r"(?:宿命|预言|命运之轮|轮回)",
                ],
                "weight": 0.85,
            },
            "清单体叙事": {
                "signals": [
                    r"(?:其一|其二|其三|第一|第二|第三)",
                    r"(?:一是|二是|三是|一曰|二曰)",
                    r"(?m)^.{0,10}、.{0,10}、.{0,10}$",  # 排列清单行
                ],
                "weight": 0.9,
            },
            "超因果叙事": {
                "signals": [
                    r"(?:毫无理由|不知为何|莫名其妙|无缘无故)",
                    r"(?:因果断裂|逻辑跳跃|荒诞)",
                    r"(?:就这样|不知怎么).{0,5}(?:发生了|出现了)",
                ],
                "weight": 0.85,
            },
            "跨页断裂": {
                "signals": [
                    r"(?:正当|就在这时|突然)$",  # 段尾悬念
                ],
                "weight": 0.7,  # 需要章节边界检测，简化处理
            },
            "叙事迷宫": {
                "signals": [
                    r"(?:循环|重复|回到原点|似曾相识)",
                    r"(?:分岔路口|平行世界|另一个版本)",
                    r"(?:迷宫|迷途|迷失)",
                ],
                "weight": 0.85,
            },
            "时间畸变与多重视角嵌套": {
                "signals": [
                    r"(?:时间|岁月|光阴)(?:凝固|倒流|折叠|扭曲)",
                    r"(?:同一时刻|此时此地).{0,10}(?:不同的人|另一个人)",
                    r"(?:过去与现在|记忆与现实).{0,5}(?:交织|重叠|交错)",
                ],
                "weight": 0.85,
            },
        }
        
        # === description 分类：散文质量检测 ===
        self.description_patterns = {
            "羽毛句": {
                "signals": [
                    r"(?:轻|柔|飘|浮|微|细|淡|浅).{0,4}(?:羽毛|绒毛|飞絮|雪花|花瓣|光点|尘埃)",
                    r"(?:像.*羽毛|如.*絮|似.*烟|宛.*雾)",
                    r"(?:缓缓|轻轻|悠悠|飘飘).{0,6}(?:落下|飘落|散开|弥漫)",
                    r"(?:一瞬间|刹那间|须臾).{0,15}(?:感知|捕捉|察觉)",
                ],
                "weight": 1.0,
            },
            "涟漪句": {
                "signals": [
                    r"(?:一圈圈|层层|阵阵|一波波|涟漪|扩散)",
                    r"(?:从.*向外|由近及远|蔓延开来)",
                    r"(?:影响|波及|触动|震撼).{0,8}(?:周围|四周|整个)",
                ],
                "weight": 1.0,
            },
            "叠影句": {
                "signals": [
                    r"(?:重叠|叠加|交织|交错|重影|双重)",
                    r"(?:过去与现在|现实与回忆|梦境与清醒).{0,5}(?:重叠|交融)",
                    r"(?:两个.*影子|多重|双层)",
                ],
                "weight": 1.0,
            },
            "感官描写与通感": {
                "signals": [
                    r"(?:冰凉|滚烫|刺骨|温润|粗糙|细腻|柔软|坚硬).{0,4}(?:触碰到|摸起来)",
                    r"(?:听见|看到).{0,6}(?:颜色|温度|味道)",
                    r"(?:空气中弥漫着|鼻尖萦绕着|舌尖残留着)",
                    r"(?:通感|联觉|跨界|感官交融)",
                ],
                "weight": 0.9,
            },
            "心理描写与意识流": {
                "signals": [
                    r"(?:思绪|念头|想法|意识).{0,6}(?:飘过|闪过|涌上|浮现|流淌)",
                    r"(?:碎片般|断断续续|杂乱无章).{0,6}(?:记忆|画面|声音)",
                    r"(?:内心独白|意识流|心理活动|精神世界)",
                ],
                "weight": 0.9,
            },
            "陌生化与感知刷新": {
                "signals": [
                    r"(?:仿佛第一次|好像从未|重新发现|突然看清)",
                    r"(?:习以为常|司空见惯|理所当然).{0,8}(?:变得|显得|竟然后)",
                    r"(?:陌生|新奇|不同寻常).{0,6}(?:眼光|角度|方式)",
                ],
                "weight": 0.9,
            },
            "白描与工笔": {
                "signals": [
                    r"(?:寥寥数笔|简练|朴素|不加修饰|素白)",
                    r"(?:工笔细描|精雕细琢|浓墨重彩|细致入微)",
                    r"(?:勾勒|描摹|刻画).{0,6}(?:轮廓|线条|神韵)",
                ],
                "weight": 0.85,
            },
            "意象叠加与蒙太奇": {
                "signals": [
                    r"(?:画面|镜头|影像|场景).{0,6}(?:切换|跳跃|剪辑|闪回|并置)",
                    r"(?:一个.*接着一个|一幅幅|一组组).{0,10}(?:画面|图景|景象)",
                    r"(?:蒙太奇|剪接|拼贴)",
                ],
                "weight": 0.9,
            },
            "具身认知与动作描写": {
                "signals": [
                    r"(?:肌肉|骨骼|血液|神经|指尖|掌心).{0,6}(?:绷紧|发烫|冰冷|颤抖)",
                    r"(?:身体|躯干|四肢).{0,8}(#:本能地|下意识地|不由自主)",
                    r"(?:生理反应|身体反应|本能驱使)",
                ],
                "weight": 0.9,
            },
            "氛围营造与情绪渲染": {
                "signals": [
                    r"(?:压抑|沉闷|紧张|诡异|温馨|凄清|肃杀).{0,6}(?:气氛|氛围|空气|气息)",
                    r"(?:情绪|情感|心情).{0,6}(?:弥漫|笼罩|渗透|充盈)",
                    r"(?:令人窒息|让人不安|使人心悸|动人心弦)",
                ],
                "weight": 0.85,
            },
            "动态描写与静态描写": {
                "signals": [
                    r"(?:动静结合|一张一弛|刚柔并济)",
                    r"(?:定格|凝固|静止).{0,6}(?:瞬间|刹那|片刻)",
                    r"(?:流动|奔涌|翻滚|摇曳).{0,6}(?:静止|不动|凝固)",
                ],
                "weight": 0.8,
            },
            "细节描写与具象化": {
                "signals": [
                    r"(?:细节之处|细微之处|具体而言|确切地说)",
                    r"(?:每一个|每一点|每一处).{0,10}(?:都|全|皆)",
                    r"(?:纹理|纹路|质感|光泽|色泽|形状)",
                ],
                "weight": 0.85,
            },
            "间接描写与侧面烘托": {
                "signals": [
                    r"(?:侧面|间接|借他人|通过.*的反应)",
                    r"(?:未见其人|先闻其声|未见.*先.*)",
                    r"(?:衬托|对比|反衬|烘托)",
                ],
                "weight": 0.85,
            },
        }
        
        # === special_sentence 分类 ===
        self.special_sentence_patterns = {
            "自由间接引语": {  # 与advanced中重复但检测侧重点不同（此处侧重句式特征）
                "signals": [
                    r"(?:他难道|她怎能|他怎能不|她怎会不)",
                    r"(?:真是|简直是|何等|多么).{0,10}(?:啊|呀|呢|吧)",
                    r"(?:难道说|莫非是|岂不是)",
                ],
                "weight": 1.0,
            },
            "托心句": {
                "signals": [
                    r"(?:心似|心如|意如|情若).{0,6}(?:止水|乱麻|刀绞|火焚|冰冻)",
                    r"(?:恰似|宛如|好比|犹如).{0,10}(?:……般)",
                    r"(?:只道|谁知|哪料|不料).{0,8}",
                ],
                "weight": 1.0,
            },
            "顿悟（神启时刻）": {
                "signals": [
                    r"(?:突然|猛然|霎那|顷刻间).{0,8}(?:明白了|懂了|领悟|醒悟)",
                    r"(?:一道闪电|灵光一现|豁然开朗|茅塞顿开)",
                    r"(?:原来如此|竟是如此|竟然是)",
                ],
                "weight": 1.0,
            },
            "顿呼法": {
                "signals": [
                    r"(?:啊！|哦！|天哪！|天啊！|上帝！|老天！)",
                    r"(?:你这|你为何|你怎么|难道你)",
                    r"(?:吧！|呀！|呐！|呵！)\s*$",
                ],
                "weight": 0.9,
            },
            "否定句": {
                "signals": [
                    r"(?:并非|并非是|绝不是|决不是|绝非|从不|永不)",
                    r"(?:不.*?而.*?不|既不.*?也不)",
                    r"(?:没有什么|没什么|无*所谓|无关紧要)",
                ],
                "weight": 0.85,
            },
        }
        
        # === rhetoric 分类 ===
        self.rhetoric_patterns = {
            "反讽与悖论": {
                "signals": [
                    r"(?:所谓的|号称|美其名曰|自诩)",
                    r"(?:讽刺的是|可笑的是|荒谬的是|矛盾的是)",
                    r"(?:一方面.*另一方面|既是.*又是|既是.*又不是)",
                ],
                "weight": 0.9,
            },
            "隐喻与转喻": {
                "signals": [
                    r"(?:是|成了|变成|犹如|如同|好似|仿佛|宛如).{0,15}(?:一般|一样|般)",
                    r"(?:这一|此|该).{0,5}(?:隐喻|象征|代表|意味着)",
                ],
                "weight": 0.85,
            },
            "通感置换": {
                "signals": [
                    r"(?:甜腻|苦涩|冰冷|火热|刺耳|柔和).{0,6}(?:声音|旋律|乐章|噪音)",
                    r"(?:听到|听见了?).{0,6}(?:颜色|光芒|温度|气味)",
                    r"(?:看见|看见了?).{0,6}(?:声响|旋律|节奏)",
                ],
                "weight": 1.0,
            },
            "排比、对偶": {
                "signals": [
                    r"(?:有的.*?有的.*?有的|有的.*?有的)",
                    r"(?:是.*?是.*?是|不是.*?不是.*?不是)",
                    r".{0,10}，.{0,10}(?:，|；).{0,10}，.{0,10}(？|！|。)",
                ],
                "weight": 0.85,
            },
            "夸张、低调陈述": {
                "signals": [
                    r"(?:简直|几乎|差不多|差一点|差点)",
                    r"(?:成千上万|不计其数|无数|无穷无尽|漫天遍地)",
                    r"(?:还算|勉强|不过|仅仅|只不过|只是有点)",
                ],
                "weight": 0.8,
            },
            "象征与寓言": {
                "signals": [
                    r"(?:象征着|寓意着|代表着|暗示着|预示着)",
                    r"(?:这个.*?那个.*?|前者.*?后者)",
                    r"(?:寓言|童话|神话|传说|典故)",
                ],
                "weight": 0.85,
            },
            "解剖句": {
                "signals": [
                    r"(?m)^[^，。，！？]{2,12}$",  # 极短并列句
                    r"(?:一个.*?又一个.*?再一个|一步.*?两步.*?三步)",
                ],
                "weight": 0.9,
            },
            "幽灵句": {
                "signals": [
                    r"^(?:雨|风|雪|光|夜| silence |黑暗|寂静).{0,20}$",  # 无主语句
                    r"(?:没有人|什么也|一切).{0,10}(?:没有|不|未)",
                ],
                "weight": 0.9,
            },
            "排比与层递": {
                "signals": [
                    r"(?:一层层|一步步|一次次|一遍遍|一轮轮)",
                    r"(?:越来越.*?越来越|愈来愈.*?愈来愈)",
                ],
                "weight": 0.85,
            },
            "提喻与转喻": {
                "signals": [
                    r"(?:双手|手掌|脚下|头顶|眉宇|唇边|指尖).{0,8}(?:代指|代表|象征)",
                    r"(?:一把|一瓶|一碗|一滴|一片|一朵).{0,6}",
                ],
                "weight": 0.8,
            },
        }
        
        # === narrative 分类 ===
        self.narrative_patterns = {
            "叙事时间与时长": {
                "signals": [
                    r"(?:多年前|三年前|那时候|当年|昔日|往昔)",
                    r"(?:多年以后|后来|此后|从此|之后)",
                    r"(?:回想起来|记忆回到|思绪飘回)",
                    r"(?:时光飞逝|岁月如梭|转眼间|弹指一挥间)",
                    r"(?:十年过去了|三天后|次日清晨)",
                ],
                "weight": 0.9,
            },
            "螺旋句": {
                "signals": [
                    r"(?:绕了一圈|兜了一圈|转了一圈).{0,10}(?:回来|回到原地)",
                    r"(?:一圈又一圈|一次又一次|一遍又一遍)",
                    r"(?:循环|轮回|重复|回归)",
                ],
                "weight": 0.9,
            },
            "反高潮句": {
                "signals": [
                    r"(?:并没有|却什么也没|什么也没发生|一切如常)",
                    r"(?:平淡无奇|普普通通|平平常常)",
                    r"(?:期待.*?落空|希望.*?破灭)",
                ],
                "weight": 0.85,
            },
            "叙事视角与聚焦": {
                "signals": [
                    r"(?:透过.*的眼睛|从.*的角度|以.*的视野)",
                    r"(?:他注意到|她观察到|他发现|她察觉)",
                    r"(?:聚焦于|视线落在|目光投向)",
                ],
                "weight": 0.85,
            },
            "叙事声音与叙事距离": {
                "signals": [
                    r"(?:笔者|作者|本书记述|此处叙述)",
                    r"(?:读者诸君|诸位|列位看官)",
                    r"(?:拉开距离|拉近视角|推远镜头|推进镜头)",
                ],
                "weight": 0.8,
            },
            "叙事空间与场景": {
                "signals": [
                    r"(?:场景转换|画面切至|镜头转向|视线转移)",
                    r"(?:此处|彼时|那边|这里).{0,8}(?:空间|位置|地点)",
                ],
                "weight": 0.8,
            },
            "叙事节奏与叙事张力": {
                "signals": [
                    r"(?:节奏加快|速度放慢|时间拉长|瞬间缩短)",
                    r"(?:紧张|松弛|急促|舒缓|凝滞)",
                    r"(?:心跳加速|呼吸停滞|屏息凝神|松了一口气)",
                ],
                "weight": 0.85,
            },
        }
        
        # === structure 分类 ===
        self.structure_patterns = {
            "叙事弧线与三幕剧结构": {
                "signals": [
                    r"(?:起初|最初|一开始|开端)",
                    r"(?:转折|变化|突变|危机|冲突升级)",
                    r"(?:最终|最后|结局|落幕|收束)",
                ],
                "weight": 0.7,  # 结构类通常需要全文分析
            },
            "多线叙事与网状结构": {
                "signals": [
                    r"(?:与此同时|另一边|别处|与此同时)",
                    r"(?:另一条线索|另一条线|平行的)",
                    r"(?:交汇|汇合|交织|交叉点)",
                ],
                "weight": 0.85,
            },
            "虫洞句": {
                "signals": [
                    r"(?:时空跳跃|穿越|瞬移|断层|裂缝)",
                    r"(?:从一个世界|从一处到另一处|跨越)",
                    r"(?:——.{0,20}——.{0,20}——)",  # 多重跳跃分隔
                ],
                "weight": 0.9,
            },
        }
    
    def analyze(self, content: str, context: Optional[Dict] = None) -> TechniqueMonitorResult:
        """
        分析文本中的高级写作技巧应用情况
        
        V1.5.0 核心方法：
        基于知识库58个真实技巧进行深度检测，
        输出检测结果和生成指导。
        
        Args:
            content: 待分析的文本
            context: 可选上下文（含techniques知识库数据）
            
        Returns:
            TechniqueMonitorResult: 完整的分析结果
        """
        if not content or len(content.strip()) < 50:
            return TechniqueMonitorResult(
                overall_score=0.3,
                category_scores={},
                detected_techniques=[],
                missing_techniques=[],
                technique_count=0,
                total_available=0,
                guidance_text="",
                suggestions=["文本过短，无法进行有效检测"]
            )
        
        context = context or {}
        
        # 加载知识库
        kb_data = self._load_kb_data()
        techniques_from_context = context.get("techniques", {})
        
        # 合并数据源：优先context中的数据，补充本地KB
        all_techniques = dict(kb_data)
        for cat, items in techniques_from_context.items():
            if cat not in all_techniques or not all_techniques[cat]:
                if isinstance(items, list) and items:
                    all_techniques[cat] = items
        
        # ===== 各分类深度检测 =====
        category_results = {}
        all_detected = []
        all_titles = set()
        total_available = 0
        
        for cat in self.CATEGORIES:
            cat_kb = all_techniques.get(cat, [])
            if cat_kb:
                # 提取所有技巧标题
                titles_in_cat = []
                for item in cat_kb:
                    pts = item.get("knowledge_points", item) if isinstance(item, dict) else item
                    if isinstance(pts, list):
                        for p in pts:
                            title = p.get("title", "") if isinstance(p, dict) else ""
                            if title:
                                titles_in_cat.append(title)
                                all_titles.add(title)
                    elif isinstance(pts, dict):
                        title = pts.get("title", "")
                        if title:
                            titles_in_cat.append(title)
                            all_titles.add(title)
                
                total_available += len(titles_in_cat)
                
                # 对每个技巧执行检测
                detected_in_cat = self._detect_category(content, cat, titles_in_cat)
                category_results[cat] = detected_in_cat
                all_detected.extend(detected_in_cat)
        
        # ===== 生成指导文本 =====
        guidance = self._generate_guidance(all_detected, all_titles, content)
        
        # ===== 生成建议 =====
        suggestions = self._generate_suggestions(category_results, content)
        
        # ===== 计算总体评分 =====
        overall = self._calculate_overall(category_results, total_available)
        
        # ===== 计算各分类评分（从检测列表中提取平均置信度）=====
        cat_scores = {}
        for cat, detected_list in category_results.items():
            if detected_list:
                avg_conf = sum(d.get("confidence", 0) for d in detected_list) / len(detected_list)
                cat_scores[cat] = round(avg_conf, 4)
            else:
                cat_scores[cat] = 0.0
        
        # ===== 缺失技巧列表 =====
        detected_names = {d["name"] for d in all_detected}
        missing = sorted(list(all_titles - detected_names))[:15]  # 最多列出15个
        
        return TechniqueMonitorResult(
            overall_score=round(overall, 4),
            category_scores=cat_scores,
            detected_techniques=all_detected,
            missing_techniques=missing,
            technique_count=len(all_detected),
            total_available=total_available,
            guidance_text=guidance,
            suggestions=suggestions
        )
    
    def _detect_category(self, content: str, category: str, 
                          available_titles: List[str]) -> List[Dict]:
        """
        对指定分类的所有技巧进行深度检测
        
        检测策略（按优先级）：
        1. 结构化模式检测（预定义的正则/规则）
        2. 知识库关键词匹配（来自真实KB数据）
        3. 标题直接提及（AI有意识地使用该技巧）
        """
        # 选择对应的模式库
        pattern_map = {
            "advanced": self.advanced_patterns,
            "description": self.description_patterns,
            "special_sentence": self.special_sentence_patterns,
            "rhetoric": self.rhetoric_patterns,
            "narrative": self.narrative_patterns,
            "structure": self.structure_patterns,
        }
        
        patterns = pattern_map.get(category, {})
        detected = []
        
        for title in available_titles:
            confidence = 0.0
            evidences = []
            
            # 策略1：结构化模式检测
            if title in patterns:
                pat_info = patterns[title]
                pat_signals = pat_info.get("signals", [])
                weight = pat_info.get("weight", 0.8)
                
                match_count = 0
                for pat in pat_signals:
                    matches = re.findall(pat, content, re.MULTILINE)
                    if matches:
                        match_count += len(matches)
                        # 收集证据（取第一个匹配的前20字符作为示例）
                        sample_match = matches[0]
                        if isinstance(sample_match, tuple):
                            sample_match = str(sample_match[0])
                        evidence_preview = sample_match[:25].replace('\n', ' ') if len(sample_match) > 3 else ""
                        if evidence_preview and len(evidences) < 3:
                            evidences.append(evidence_preview)
                
                if match_count > 0:
                    # 置信度计算：基础分 + 匹配加权 + 技巧权重
                    base_confidence = min(0.6, 0.2 + match_count * 0.1)
                    confidence = min(0.95, base_confidence * weight)
            
            # 策略2：标题直接提及（最高权重证据）
            if title in content:
                confidence = max(confidence, 0.80)
                if f"【{title}】" not in evidences:
                    evidences.insert(0, f"直接提及「{title}」")
            
            # 策略3：从知识库提取关键词匹配（辅助验证）
            if confidence > 0 or title in content:
                # 尝试从已加载的KB数据获取关键词
                kb = self._kb_data or {}
                cat_kb = kb.get(category, [])
                keywords_for_title = []
                for item in cat_kb:
                    pts = item.get("knowledge_points", [item]) if isinstance(item, dict) else [item]
                    for p in pts:
                        p_title = p.get("title", "") if isinstance(p, dict) else ""
                        if p_title == title:
                            kws = p.get("keywords", []) if isinstance(p, dict) else []
                            keywords_for_title = kws
                            break
                    if keywords_for_title:
                        break
                
                # 关键词匹配加分
                if keywords_for_title:
                    kw_matches = sum(1 for kw in keywords_for_title[:8] 
                                   if kw and len(kw) >= 2 and kw in content)
                    if kw_matches >= 2:
                        confidence = min(0.98, confidence + 0.05 * min(kw_matches, 4))
                    elif kw_matches == 1:
                        confidence = max(confidence, 0.35)
            
            # 记录检测到的技巧（置信度>0.3视为有效检出）
            if confidence > 0.3:
                detected.append({
                    "name": title,
                    "category": category,
                    "confidence": round(confidence, 3),
                    "evidence": evidences[:3],  # 最多3条证据
                })
        
        # 按置信度排序
        detected.sort(key=lambda x: x["confidence"], reverse=True)
        return detected
    
    def _calculate_overall(self, category_results: Dict[str, List[Dict]], 
                           total_available: int) -> float:
        """
        计算总体技巧应用评分
        
        评分逻辑：
        - 基础分0.3
        - 各分类按检测率加权
        - 至少检测到3种不同技巧给额外加分
        """
        if total_available == 0:
            return 0.5
        
        score = 0.30  # 基础分
        total_detected = sum(len(d) for d in category_results.values())
        
        # 检测率加分
        if total_available > 0:
            detection_ratio = total_detected / min(total_available, 40)  # 上限40避免稀释
            score += detection_ratio * 0.45
        
        # 高置信度技巧加分（>=0.7的才算高质量应用）
        high_confidence = sum(
            1 for results in category_results.values() 
            for d in results if d["confidence"] >= 0.70
        )
        score += min(0.20, high_confidence * 0.03)
        
        # 分类覆盖加分（多个分类都有检出到）
        cats_with_detection = sum(1 for v in category_results.values() if v)
        if cats_with_detection >= 4:
            score += 0.05
        elif cats_with_detection >= 2:
            score += 0.02
        
        return min(1.0, score)
    
    def _generate_guidance(self, detected: List[Dict], 
                             all_titles: set, content: str) -> str:
        """
        生成用于生成环的技巧指导文本
        
        将检测结果转化为可注入prompt的写作指令。
        即使当前文本未使用某些技巧，也可以推荐使用。
        """
        if not detected and not all_titles:
            return ""
        
        lines = ["【高级写作技巧应用要求】"]
        
        # 已检测到的技巧 → 强化继续使用
        high_conf = [d for d in detected if d["confidence"] >= 0.65]
        if high_conf:
            lines.append("\n已成功运用的技巧（请继续保持和深化）：")
            for d in sorted(high_conf, key=lambda x: -x["confidence"])[:8]:
                cat_label = self.CATEGORY_LABELS.get(d["category"], d["category"])
                lines.append(f"- 【{d['name']}】({cat_label}) 置信度:{d['confidence']:.0%}")
        
        # 推荐使用的技巧（基于内容类型智能推荐）
        recommended = self._recommend_techniques(content, detected, all_titles)
        if recommended:
            lines.append("\n推荐在本章节尝试运用以下技巧：")
            for rec_name, rec_reason in recommended[:6]:
                lines.append(f"- 【{rec_name}】：{rec_reason}")
        
        # 具体的写作技法提醒
        tips = self._get_writing_tips(detected, content)
        if tips:
            lines.append("\n写作技法提醒：")
            for tip in tips[:5]:
                lines.append(f"* {tip}")
        
        return "\n".join(lines)
    
    def _recommend_techniques(self, content: str, detected: List[Dict], 
                               all_titles: set) -> List[Tuple[str, str]]:
        """
        基于当前内容特征智能推荐适合的技巧
        
        分析文本特征，推荐最匹配的未使用技巧
        """
        used_names = {d["name"] for d in detected}
        recommendations = []
        
        content_len = len(content)
        has_dialogue = '"' in content or '"' in content or "\u201c" in content
        has_inner_thought = any(w in content for w in ["心里", "想着", "觉得", "暗自", "心想"])
        has_action = any(w in content for w in ["握", "转身", "迈步", "抬头", "低头", "伸手"])
        has_sensory = any(w in content for w in ["冷", "热", "痛", "香", "响", "亮", "暗"])
        
        # 基于内容特征的推荐规则
        if has_dialogue and "潜文本对话" not in used_names:
            recommendations.append(("潜文本对话", "对话较多时，让角色'言外有意'，增加对话张力"))
        
        if has_inner_thought and "自由间接引语" not in used_names:
            recommendations.append(("自由间接引语", "存在内心活动，可用第三人称+第一人称混合增强代入感"))
        
        if has_action and "羽毛句" not in used_names and content_len > 2000:
            recommendations.append(("羽毛句", "动作描写密集时，穿插轻盈的感知瞬间增加节奏变化"))
        
        if has_sensory and "通感置换" not in used_names:
            recommendations.append(("通感置换", "已有感官描写，进一步打破感官边界创造新鲜感"))
        
        if content_len > 3000 and "负空间叙事" not in used_names:
            recommendations.append(("负空间叙事", "篇幅较长时适当留白，用'不说'来'说'更有力量"))
        
        if "展示vs告知" not in str(used_names) and "陌生人化与感知刷新" not in used_names:
            recommendations.append(("陌生化与感知刷新", "将日常事物写得'陌生'，刷新读者的感知经验"))
        
        # 如果没有任何推荐，随机选几个高价值技巧
        if not recommendations:
            priority_rec = [
                ("不可靠叙述", "通过叙述者的认知局限或主观偏见制造阅读张力"),
                ("潜文本对话", "让角色的话中有话，增加戏剧张力"),
                ("自由间接引语", "融合叙述者和角色的声音，增强沉浸感"),
                ("羽毛句", "用轻盈的意象捕捉瞬间的感知体验"),
                ("顿悟（神启时刻）", "在关键时刻安排人物突然领悟的瞬间"),
            ]
            for name, reason in priority_rec:
                if name in all_titles and name not in used_names:
                    recommendations.append((name, reason))
                    if len(recommendations) >= 3:
                        break
        
        return recommendations
    
    def _get_writing_tips(self, detected: List[Dict], content: str) -> List[str]:
        """基于检测结果给出具体的写作技法提示"""
        tips = []
        detected_cats = {d["category"] for d in detected}
        detected_names = {d["name"] for d in detected}
        
        # 基于缺失的分类给提示
        if "advanced" not in detected_cats:
            tips.append("考虑运用一种高级叙事技巧（如不可靠叙述/自由间接引语/潜文本对话）来提升文本层次")
        
        if "description" not in detected_cats and len(content) > 1500:
            tips.append("可加入羽毛句或涟漪句等特殊描写句式，增强文字的画面感和音乐性")
        
        if "rhetoric" not in detected_cats:
            tips.append("适当使用通感置换或反讽等修辞手法，丰富语言表现力")
        
        # 基于已有的检测给深化建议
        if "不可靠叙述" in detected_names:
            tips.append("不可靠叙述正在生效，注意保持叙述者与隐含作者之间的'差距'")
        
        if any(n in detected_names for n in ["羽毛句", "涟漪句", "叠影句"]):
            tips.append("特殊句式运用良好，注意不要过度集中使用，与其他句式交替更自然")
        
        # 通用质量提醒
        weak_verbs = content.count(" 是 ") + content.count(" 有 ") + content.count(" 在 ")
        if weak_verbs > len(content) // 200:
            tips.append("弱动词（是/有/在）密度偏高，尝试替换为更具象的动词")
        
        return tips
    
    def _generate_suggestions(self, category_results: Dict[str, List[Dict]], 
                                content: str) -> List[str]:
        """基于检测结果生成优化建议"""
        suggestions = []
        
        total_detected = sum(len(d) for d in category_results.values())
        
        if total_detected == 0:
            suggestions.append("未检测到任何知识库高级写作技巧的应用。建议在创作时有意识地运用1-2种技巧（如自由间接引语、潜文本对话、羽毛句等）")
            return suggestions
        
        if total_detected <= 2:
            suggestions.append(f"仅检测到{total_detected}种技巧应用，建议增加技巧多样性，丰富文本层次")
        
        # 低置信度技巧提示
        low_conf = [d for d in sum(category_results.values(), []) if d["confidence"] < 0.50]
        if len(low_conf) > total_detected // 2:
            suggestions.append("部分技巧的应用置信度较低，可能仅为表面提及而非深入运用，建议加深应用程度")
        
        # 分类覆盖不足
        active_cats = [c for c, v in category_results.items() if v]
        if len(active_cats) <= 2:
            missing_cats = [self.CATEGORY_LABELS.get(c, c) 
                         for c in self.CATEGORIES if c not in active_cats]
            suggestions.append(f"技巧应用集中在{len(active_cats)}个分类，建议拓展至{missing_cats[:2]}等领域")
        
        return suggestions[:5]
    
    def get_active_techniques_summary(self, result: TechniqueMonitorResult) -> str:
        """生成技巧应用的摘要文本（用于UI显示）"""
        if not result.detected_techniques:
            return "未检测到高级写作技巧应用"
        
        top_detected = result.detected_techniques[:5]
        parts = []
        for d in top_detected:
            cat = self.CATEGORY_LABELS.get(d["category"], d["category"])
            parts.append(f"{d['name']}({cat},{d['confidence']:.0%})")
        
        summary = f"检测到{result.technique_count}/{result.total_available}个技巧: {'; '.join(parts)}"
        if result.technique_count > 5:
            summary += f" 等"
        return summary


# === 模块导出 ===
__all__ = [
    # 基础配置
    "SkillConfig",
    # 技能管理器（扩展版，含technique-monitor）
    "SkillManager",
    "get_skill_manager",
    # 技能结果类
    "HumanizerResult",
    "FictionWritingResult",
    "TechniqueMonitorResult",
    # 技能实例（按需导入）
    "HumanizerSkill",
    "FictionWritingSkill", 
    "TechniqueMonitorSkill",
]


