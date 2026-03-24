"""
质量验证器插件 V1.1

版本: 1.1.0
创建日期: 2026-03-23
最后更新: 2026-03-24
迁移来源: V5 scripts/enhanced_weighted_validator.py

功能:
- 6维度加权评分系统
- 字数符合性评分 (10%)
- 大纲符合性评分 (15%)
- 风格一致性评分 (25%)
- 人设一致性评分 (25%)
- 世界观一致性评分 (20%，一票否决)
- 自然度评分 (5%)

V1.1 新增功能:
- 集成逆向反馈分析器，实现"上下文不违背"维度评分
- 调用逆向反馈分析器检查章节与设定的一致性
- 将冲突数量/严重程度转化为评分（0-1）
- 支持高/中/低优先级冲突的差异化扣分

核心规则（强制保护）:
1. 章节结束必须添加【本章完】标记
2. 评分阈值 >= 0.8 才能输出
3. 迭代上限 5 次
4. 6维度评分权重固定
5. 世界观严重违背一票否决

参考文档:
- 《项目总体架构设计说明书V1.2》第四章
- 《插件接口定义V2.1》
- 《逆向反馈分析器插件实现说明》
"""

import re
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from collections import Counter
import sys
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.plugin_interface import ValidatorPlugin, PluginMetadata, PluginType, PluginContext
from core.models import ValidationScores

# 可选依赖检测
try:
    import jieba
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False


@dataclass
class WordCountScore:
    """字数符合性评分"""
    target_words: int
    actual_words: int
    difference: int
    accuracy_percentage: float
    score: float  # 0.4-1.0


@dataclass
class OutlineComplianceScore:
    """大纲符合性评分"""
    score: float  # 0.4-1.0
    matched_plot_points: int
    total_plot_points: int
    matched_keywords: List[str]
    missing_plot_points: List[str]


@dataclass
class NaturalnessScore:
    """自然度评分（AI痕迹检测）"""
    score: float  # 0.4-1.0
    ai_probability: float
    formulaic_score: float
    cliche_score: float
    issues_found: List[str]


@dataclass
class WeightedValidationResult:
    """加权评分验证结果"""
    word_count_score: WordCountScore
    outline_compliance: OutlineComplianceScore
    style_consistency: float
    character_consistency: float
    worldview_consistency: float
    naturalness: NaturalnessScore
    total_weighted_score: float
    passed: bool
    feedback: Dict[str, Any]
    suggestions: List[str]


class QualityValidatorPlugin(ValidatorPlugin):
    """质量验证器插件 - V5核心模块迁移

    实现 ValidatorPlugin 接口，提供6维度加权评分验证。

    验证维度:
    - word_count: 字数符合性 (10%)
    - outline: 大纲符合性 (15%)
    - style: 风格一致性 (25%)
    - character: 人设一致性 (25%)
    - worldview: 世界观一致性 (20%)
    - naturalness: 自然度 (5%)
    """

    # 类常量
    PLUGIN_ID = "quality-validator-v1"
    PLUGIN_NAME = "质量验证器 V1"
    PLUGIN_VERSION = "1.1.0"

    # 评分权重配置（强制保护 - 不可变更）
    WEIGHTS = {
        'word_count': 0.10,
        'outline': 0.15,
        'style': 0.25,
        'character': 0.25,
        'worldview': 0.20,
        'naturalness': 0.05
    }

    def __init__(self):
        """初始化插件"""
        metadata = PluginMetadata(
            id=self.PLUGIN_ID,
            name=self.PLUGIN_NAME,
            version=self.PLUGIN_VERSION,
            description="6维度加权评分验证器",
            author="项目组",
            plugin_type=PluginType.VALIDATOR,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=["quality-validator-v2"],
            permissions=["file.read"],
            min_platform_version="6.0.0",
            entry_class="QualityValidatorPlugin",
        )
        super().__init__(metadata)

        self._logger = logging.getLogger(__name__)

        # 逆向反馈分析器引用（在initialize中设置）
        self._reverse_feedback_analyzer = None

        # AI痕迹检测模式
        self.ai_patterns = {
            "formulaic_beginnings": [
                r'在[\u4e00-\u9fff]{2,6}的[\u4e00-\u9fff]{2,6}，',
                r'这是一个关于[\u4e00-\u9fff]{2,10}的故事',
                r'让我们把目光投向[\u4e00-\u9fff]{2,10}',
            ],
            "over_explanation": [
                r'换句话说，',
                r'也就是说，',
                r'具体来说，',
                r'简而言之，'
            ],
            "repetitive_structures": [
                r'一方面，[\u4e00-\u9fff]+。另一方面，[\u4e00-\u9fff]+。',
                r'首先，[\u4e00-\u9fff]+。其次，[\u4e00-\u9fff]+。最后，[\u4e00-\u9fff]+。',
            ],
            "unnatural_transitions": [
                r'突然，',
                r'就在这时，',
                r'没想到，',
            ],
            "ai_cliches": [
                r'在.*的背景下',
                r'从.*的角度来看',
                r'值得注意的是',
            ]
        }

        # 陈词滥调词汇
        self.cliches = [
            '美丽', '漂亮', '高大', '细小', '明亮', '黑暗',
            '重要', '关键', '核心', '基本', '主要', '必要',
            '显然', '明显', '清楚', '明白', '明确', '确定',
            '非常', '极其', '十分', '特别', '相当', '颇为',
        ]

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据"""
        return PluginMetadata(
            id=cls.PLUGIN_ID,
            name=cls.PLUGIN_NAME,
            version=cls.PLUGIN_VERSION,
            description="6维度加权评分验证器",
            author="项目组",
            plugin_type=PluginType.VALIDATOR,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=["quality-validator-v2"],
            permissions=["file.read"],
            min_platform_version="6.0.0",
            entry_class="QualityValidatorPlugin",
        )

    def initialize(self, context: PluginContext) -> bool:
        """初始化插件"""
        if not super().initialize(context):
            return False

        # 获取逆向反馈分析器插件引用
        self._reverse_feedback_analyzer = None
        try:
            if hasattr(context, 'plugin_registry') and context.plugin_registry:
                self._reverse_feedback_analyzer = context.plugin_registry.get_plugin("reverse-feedback-analyzer")
                if self._reverse_feedback_analyzer:
                    self._logger.info("[质量验证器] 成功获取逆向反馈分析器插件引用")
                else:
                    self._logger.warning("[质量验证器] 逆向反馈分析器插件未找到，上下文一致性检查将跳过")
        except Exception as e:
            self._logger.warning(f"[质量验证器] 获取逆向反馈分析器插件失败: {e}")

        self._logger.info(f"[{self.PLUGIN_ID}] 插件初始化成功")
        return True

    def validate(self, content: str, context: Optional[Dict[str, Any]] = None) -> ValidationScores:
        """验证内容并返回评分

        Args:
            content: 待验证内容
            context: 验证上下文
                - target_word_count: 目标字数
                - chapter_outline: 章节大纲
                - style_profile: 风格配置
                - character_profiles: 人物设定列表
                - world_view: 世界观设定
                - chapter_id: 章节ID（用于逆向反馈分析）
                - project_name: 项目名称
                - chapter_title: 章节标题

        Returns:
            ValidationScores 评分对象
        """
        context = context or {}
        self._logger.info("开始加权评分验证...")

        # 检查章节结束标记
        has_ending_marker = "【本章完】" in content
        if not has_ending_marker:
            self._logger.warning("缺少【本章完】结束标记")

        # 获取上下文参数
        target_word_count = context.get('target_word_count', 2000)
        chapter_outline = context.get('chapter_outline')
        style_profile = context.get('style_profile')
        character_profiles = context.get('character_profiles')
        world_view = context.get('world_view')

        # 1. 字数符合性评分
        word_count_score = self._score_word_count(content, target_word_count)

        # 2. 大纲符合性评分
        if chapter_outline:
            outline_compliance = self._score_outline_compliance(content, chapter_outline)
        else:
            outline_compliance = OutlineComplianceScore(
                score=0.7,
                matched_plot_points=0,
                total_plot_points=0,
                matched_keywords=[],
                missing_plot_points=[]
            )

        # 3. 风格一致性评分
        style_consistency = self._score_style_consistency(content, style_profile)

        # 4. 人设一致性评分
        if character_profiles:
            character_consistency = self._score_character_consistency(content, character_profiles)
        else:
            character_consistency = 0.7

        # 5. 世界观一致性评分（一票否决）
        if world_view:
            worldview_consistency, worldview_violation = self._score_worldview_consistency(content, world_view)
        else:
            worldview_consistency = 0.7
            worldview_violation = False

        # 6. 自然度评分
        naturalness = self._score_naturalness(content)

        # 7. 上下文一致性评分（集成逆向反馈分析器）
        context_consistency, context_issues = self._score_context_consistency(content, context)

        # 如果存在高优先级冲突，记录警告
        if context_consistency < 0.6:
            self._logger.warning(f"上下文一致性评分较低: {context_consistency:.2f}")
            for issue in context_issues:
                self._logger.warning(f"  - {issue}")

        # 检查严重违背世界观（一票否决）
        if worldview_violation:
            self._logger.warning("检测到严重违背世界观，一票否决")
            total_score = 0.0
            passed = False
        else:
            # 计算加权总分
            total_score = (
                word_count_score.score * self.WEIGHTS['word_count'] +
                outline_compliance.score * self.WEIGHTS['outline'] +
                style_consistency * self.WEIGHTS['style'] +
                character_consistency * self.WEIGHTS['character'] +
                worldview_consistency * self.WEIGHTS['worldview'] +
                naturalness.score * self.WEIGHTS['naturalness']
            )

            # 上下文一致性作为额外加权因子（影响总分但不参与权重计算）
            # 如果上下文一致性评分较低，会降低总分
            if context_consistency < 0.7:
                # 应用惩罚因子：每低于0.1扣减5%的总分
                penalty_factor = max(0.7, context_consistency)
                total_score = total_score * penalty_factor
                self._logger.info(f"上下文一致性惩罚因子: {penalty_factor:.2f}")

            # 必须同时满足：总分达标 + 包含结束标记
            passed = (total_score >= 0.8 and has_ending_marker)

        # 创建ValidationScores对象
        scores = ValidationScores(
            word_count_score=word_count_score.score,
            outline_score=outline_compliance.score,
            style_score=style_consistency,
            character_score=character_consistency,
            worldview_score=worldview_consistency,
            naturalness_score=naturalness.score,
            total_score=total_score,
            has_chapter_end=has_ending_marker
        )
        scores.calculate_total()

        self._logger.info(f"验证完成: 总分={total_score:.2f}, 通过={passed}, 上下文一致性={context_consistency:.2f}")
        return scores

    def validate_with_weights(
        self,
        text: str,
        target_word_count: int,
        chapter_outline: str = None,
        style_profile: Dict[str, Any] = None,
        character_profiles: List[Dict] = None,
        world_view: str = None
    ) -> WeightedValidationResult:
        """完整验证并返回详细结果（兼容V5接口）

        此方法保留V5原有接口，提供更详细的验证结果。
        """
        context = {
            'target_word_count': target_word_count,
            'chapter_outline': chapter_outline,
            'style_profile': style_profile,
            'character_profiles': character_profiles,
            'world_view': world_view
        }

        # 执行验证
        validation_scores = self.validate(text, context)

        # 构建详细结果
        has_ending_marker = "【本章完】" in text

        word_count_score = self._score_word_count(text, target_word_count)

        if chapter_outline:
            outline_compliance = self._score_outline_compliance(text, chapter_outline)
        else:
            outline_compliance = OutlineComplianceScore(
                score=0.7, matched_plot_points=0, total_plot_points=0,
                matched_keywords=[], missing_plot_points=[]
            )

        style_consistency = self._score_style_consistency(text, style_profile)

        if character_profiles:
            character_consistency = self._score_character_consistency(text, character_profiles)
        else:
            character_consistency = 0.7

        if world_view:
            worldview_consistency, worldview_violation = self._score_worldview_consistency(text, world_view)
        else:
            worldview_consistency = 0.7
            worldview_violation = False

        naturalness = self._score_naturalness(text)

        if worldview_violation:
            total_score = 0.0
            passed = False
        else:
            total_score = validation_scores.total_score
            passed = validation_scores.passed

        # 构建反馈
        feedback = {
            '章节结束标记': {
                'score': 1.0 if has_ending_marker else 0.0,
                'details': '✓ 包含【本章完】' if has_ending_marker else '✗ 缺少【本章完】'
            },
            '字数符合性': {
                'score': word_count_score.score,
                'details': f"目标{target_word_count}字，实际{word_count_score.actual_words}字"
            },
            '大纲符合性': {
                'score': outline_compliance.score,
                'details': f"匹配{outline_compliance.matched_plot_points}/{outline_compliance.total_plot_points}个情节点"
            },
            '风格一致性': {
                'score': style_consistency,
                'details': '与学习风格的匹配度'
            },
            '人设一致性': {
                'score': character_consistency,
                'details': '人物行为是否符合设定'
            },
            '世界观一致性': {
                'score': worldview_consistency,
                'details': '是否符合世界观设定' + ('（一票否决）' if worldview_violation else '')
            },
            '自然度': {
                'score': naturalness.score,
                'details': f"AI痕迹概率: {naturalness.ai_probability:.1%}"
            }
        }

        # 生成改进建议
        suggestions = self._generate_suggestions(
            word_count_score, outline_compliance, style_consistency,
            character_consistency, worldview_consistency, naturalness
        )

        if not has_ending_marker:
            suggestions.insert(0, "缺少【本章完】结束标记，请在章节末尾添加【本章完】")

        return WeightedValidationResult(
            word_count_score=word_count_score,
            outline_compliance=outline_compliance,
            style_consistency=style_consistency,
            character_consistency=character_consistency,
            worldview_consistency=worldview_consistency,
            naturalness=naturalness,
            total_weighted_score=total_score,
            passed=passed,
            feedback=feedback,
            suggestions=suggestions
        )

    def get_validation_dimensions(self) -> List[str]:
        """获取验证维度"""
        return [
            "word_count",      # 字数（10%）
            "outline",         # 大纲（15%）
            "style",           # 风格（25%）
            "character",       # 人设（25%）
            "worldview",       # 世界观（20%）
            "naturalness"      # 自然度（5%）
        ]

    # ===== 内部评分方法 =====

    def _score_word_count(self, text: str, target_words: int) -> WordCountScore:
        """字数符合性评分"""
        has_ending_marker = "【本章完】" in text

        # 统计字数（排除【本章完】这4个字）
        actual_words = self._count_words_excluding_marker(text)
        difference = actual_words - target_words
        accuracy_percentage = (actual_words / target_words * 100) if target_words > 0 else 100.0

        # 评分逻辑
        tolerance_10 = target_words * 0.10
        tolerance_20 = target_words * 0.20
        tolerance_30 = target_words * 0.30
        over_ratio = actual_words / target_words if target_words > 0 else 1.0

        if difference < 0:  # 字数不足
            if abs(difference) <= tolerance_10:
                score = 1.0
            elif abs(difference) <= tolerance_20:
                score = 0.8
            elif abs(difference) <= tolerance_30:
                score = 0.6
            else:
                score = 0.5
        else:  # 字数超标
            if difference <= tolerance_10:
                score = 1.0
            elif difference <= tolerance_20:
                score = 0.75
            elif difference <= tolerance_30:
                score = 0.5
            elif over_ratio <= 1.5:
                score = 0.3
            elif over_ratio <= 2.0:
                score = 0.2
            else:
                score = 0.1

        return WordCountScore(
            target_words=target_words,
            actual_words=actual_words,
            difference=difference,
            accuracy_percentage=accuracy_percentage,
            score=score
        )

    def _score_outline_compliance(self, text: str, chapter_outline: str) -> OutlineComplianceScore:
        """大纲符合性评分"""
        plot_points = self._extract_plot_points(chapter_outline)
        total_plot_points = len(plot_points)

        if total_plot_points == 0:
            return OutlineComplianceScore(
                score=0.7,
                matched_plot_points=0,
                total_plot_points=0,
                matched_keywords=[],
                missing_plot_points=[]
            )

        keywords = self._extract_keywords(chapter_outline)
        matched_plot_points = 0
        missing_plot_points = []
        matched_keywords = []

        for plot_point in plot_points:
            keywords_in_plot = self._extract_keywords(plot_point)
            for keyword in keywords_in_plot:
                if keyword in text:
                    matched_plot_points += 1
                    break
            else:
                missing_plot_points.append(plot_point)

        for keyword in keywords:
            if keyword in text:
                matched_keywords.append(keyword)

        if total_plot_points > 0:
            match_ratio = matched_plot_points / total_plot_points
            if match_ratio >= 0.9:
                score = 1.0
            elif match_ratio >= 0.7:
                score = 0.8
            elif match_ratio >= 0.5:
                score = 0.6
            else:
                score = 0.4
        else:
            score = 0.7

        return OutlineComplianceScore(
            score=score,
            matched_plot_points=matched_plot_points,
            total_plot_points=total_plot_points,
            matched_keywords=matched_keywords,
            missing_plot_points=missing_plot_points
        )

    def _score_style_consistency(self, text: str, style_profile: Dict[str, Any]) -> float:
        """风格一致性评分"""
        if not style_profile or not isinstance(style_profile, dict):
            return self._score_text_quality(text)

        if not HAS_JIEBA:
            return 0.7

        words = list(jieba.cut(text))
        word_counts = Counter(words)
        scores = []

        # 词汇匹配度
        style_words = []
        vocab_depth = style_profile.get('vocabulary_depth', {})
        if vocab_depth and 'high_frequency_words' in vocab_depth:
            for item in vocab_depth['high_frequency_words'][:20]:
                if isinstance(item, list) and len(item) >= 1:
                    style_words.append(item[0])
                elif isinstance(item, str):
                    style_words.append(item)

        if not style_words:
            vocab_profile = style_profile.get('vocabulary_profile', {})
            if vocab_profile and 'most_common_words' in vocab_profile:
                for item in vocab_profile['most_common_words'][:20]:
                    if isinstance(item, list) and len(item) >= 1:
                        style_words.append(item[0])

        style_words = [w for w in style_words if w and len(w) >= 2]

        if style_words:
            text_common_words = [word for word, _ in word_counts.most_common(30)]
            matched_words = set(style_words).intersection(set(text_common_words))
            vocab_match_ratio = len(matched_words) / len(style_words) if style_words else 0

            if vocab_match_ratio >= 0.3:
                scores.append(1.0)
            elif vocab_match_ratio >= 0.2:
                scores.append(0.9)
            elif vocab_match_ratio >= 0.1:
                scores.append(0.8)
            elif vocab_match_ratio >= 0.05:
                scores.append(0.7)
            else:
                scores.append(0.6)
        else:
            scores.append(self._score_text_quality(text))

        # 句式模式评分
        sentence_patterns = style_profile.get('sentence_patterns', {})
        if sentence_patterns:
            sentences = self._split_sentences(text)
            if sentences:
                avg_length = sum(len(s) for s in sentences) / len(sentences)
                target_length = sentence_patterns.get('avg_length', 30)
                if target_length > 0:
                    length_ratio = min(avg_length, target_length) / max(avg_length, target_length)
                    if length_ratio >= 0.7:
                        scores.append(1.0)
                    elif length_ratio >= 0.5:
                        scores.append(0.85)
                    else:
                        scores.append(0.7)
            else:
                scores.append(0.7)
        else:
            scores.append(0.7)

        # 文本质量评分
        scores.append(self._score_text_quality(text))

        # 加权平均
        weights = [0.4, 0.3, 0.3]
        final_score = sum(s * w for s, w in zip(scores, weights))
        final_score = max(0.6, final_score)

        return final_score

    def _score_text_quality(self, text: str) -> float:
        """文本质量评分"""
        if not HAS_JIEBA:
            return 0.7

        scores = []

        # 句式多样性
        sentences = self._split_sentences(text)
        if sentences:
            avg_length = sum(len(s) for s in sentences) / len(sentences)
            if 20 <= avg_length <= 40:
                scores.append(1.0)
            elif 15 <= avg_length <= 50:
                scores.append(0.8)
            else:
                scores.append(0.6)
        else:
            scores.append(0.5)

        # AI痕迹检测
        ai_penalty = 0.0
        ai_patterns = [
            (r'在.*的.*下', 0.05),
            (r'从.*的.*角度', 0.05),
            (r'让我们', 0.03),
            (r'值得注意的是', 0.05),
        ]

        for pattern, penalty in ai_patterns:
            if re.search(pattern, text):
                ai_penalty += penalty

        ai_score = max(0.4, 1.0 - ai_penalty)
        scores.append(ai_score)

        # 描写丰富度
        description_keywords = ['看着', '想', '感觉', '听到', '看到']
        description_count = sum(1 for kw in description_keywords if kw in text)
        ideal_count = len(text) / 500 * 3

        if description_count >= ideal_count * 0.8:
            scores.append(1.0)
        elif description_count >= ideal_count * 0.5:
            scores.append(0.8)
        elif description_count > 0:
            scores.append(0.6)
        else:
            scores.append(0.4)

        # 语言自然度
        dialog_markers = ['"', '"', '「', '」']
        has_dialog = any(marker in text for marker in dialog_markers)
        detail_patterns = [r'\d+年', r'\d+月', r'红色', r'蓝色']
        has_details = any(re.search(p, text) for p in detail_patterns)

        if has_dialog and has_details:
            scores.append(1.0)
        elif has_dialog or has_details:
            scores.append(0.8)
        else:
            scores.append(0.6)

        weights = [0.30, 0.30, 0.25, 0.15]
        return sum(s * w for s, w in zip(scores, weights))

    def _score_character_consistency(self, text: str, character_profiles: List[Dict]) -> float:
        """人设一致性评分"""
        if not character_profiles:
            return 0.7

        consistency_scores = []

        for char_profile in character_profiles:
            basic_info = char_profile.get('basic_info', {})
            char_name = char_profile.get('name', '') or basic_info.get('name', '')

            if not char_name or char_name not in text:
                continue

            # 基础分：人物存在
            base_score = 0.5

            # 提取性格关键词
            personality_keywords = []
            personality = char_profile.get('personality', '') or basic_info.get('personality', '')
            if personality:
                clean_personality = re.sub(r'\*\*[^*]+\*\*[:：]', '', personality)
                keywords = re.split(r'[,，。、；;\\n]+\s*', clean_personality)
                personality_keywords.extend([kw.strip() for kw in keywords if 2 <= len(kw.strip()) <= 10])

            traits = char_profile.get('traits', []) or basic_info.get('traits', [])
            if isinstance(traits, list):
                personality_keywords.extend([t for t in traits if t and 2 <= len(t) <= 10])

            personality_keywords = list(set(personality_keywords))[:5]

            # 关键词匹配
            keyword_score = 0.0
            matched_count = 0
            for keyword in personality_keywords:
                if keyword in text:
                    matched_count += 1

            if personality_keywords:
                match_ratio = matched_count / len(personality_keywords)
                keyword_score = match_ratio * 0.3

            # 行为描写
            action_patterns = ['说', '做', '走', '看', '想']
            action_count = sum(1 for p in action_patterns if p in text)
            behavior_score = 0.1 if action_count >= 3 else 0.0

            # 对话描写
            dialog_score = 0.1 if any(m in text for m in ['"', '"', '「', '」']) else 0.0

            # 总分
            total_score = min(1.0, base_score + keyword_score + behavior_score + dialog_score)
            total_score = max(0.5, total_score)

            consistency_scores.append(total_score)

        return sum(consistency_scores) / len(consistency_scores) if consistency_scores else 0.7

    def _score_worldview_consistency(self, text: str, world_view: str) -> Tuple[float, bool]:
        """世界观一致性评分（一票否决）"""
        if not world_view:
            return 0.7, False

        # 检查严重违背
        if '现实' in world_view:
            fantasy_keywords = ['魔法', '法术', '异能', '修仙', '仙术']
            if any(kw in text for kw in fantasy_keywords):
                self._logger.warning("检测到现实题材中出现魔法元素，严重违背世界观")
                return 0.0, True

        return 1.0, False

    def _score_context_consistency(
        self,
        text: str,
        context: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """上下文一致性评分（集成逆向反馈分析器）

        调用逆向反馈分析器检查章节与设定的一致性，将冲突数量和严重程度转化为评分。

        评分公式：
        - 基础分：1.0（无冲突）
        - 每个低优先级冲突：-0.05
        - 每个中优先级冲突：-0.10
        - 每个高优先级冲突：-0.20
        - 最低分：0.4（保底）

        Args:
            text: 章节文本内容
            context: 验证上下文，需包含：
                - chapter_id: 章节ID
                - chapter_outline: 章节大纲
                - character_profiles: 人物设定列表
                - world_view: 世界观设定
                - project_name: 项目名称

        Returns:
            Tuple[float, List[str]]: (评分, 问题列表)
        """
        # 如果逆向反馈分析器不可用，返回默认评分
        if not self._reverse_feedback_analyzer:
            self._logger.debug("逆向反馈分析器不可用，跳过上下文一致性检查")
            return 0.75, ["逆向反馈分析器未启用"]

        try:
            # 准备逆向反馈分析器所需的参数
            chapter_id = context.get('chapter_id', 'unknown')

            current_settings = {
                "project_name": context.get('project_name', ''),
                "chapter_title": context.get('chapter_title', ''),
                "outline": context.get('chapter_outline', ''),
                "characters": context.get('character_profiles', []),
                "worldview": context.get('world_view', '')
            }

            # 调用逆向反馈分析器
            self._logger.info(f"调用逆向反馈分析器检查章节一致性: {chapter_id}")
            report = self._reverse_feedback_analyzer.analyze_chapter_vs_settings(
                chapter_text=text,
                current_settings=current_settings,
                chapter_id=chapter_id
            )

            # 提取冲突信息
            issues = report.issues
            high_count = report.high_priority_count
            medium_count = report.medium_priority_count
            low_count = report.low_priority_count

            self._logger.info(
                f"逆向反馈分析完成: 共{len(issues)}个冲突 "
                f"(高:{high_count}, 中:{medium_count}, 低:{low_count})"
            )

            # 计算评分
            base_score = 1.0
            penalty = (
                high_count * 0.20 +    # 高优先级扣分
                medium_count * 0.10 +   # 中优先级扣分
                low_count * 0.05        # 低优先级扣分
            )

            score = max(0.4, base_score - penalty)

            # 生成问题列表
            problem_list = []
            for issue in issues[:5]:  # 只取前5个问题
                severity_map = {
                    "high": "【高】",
                    "medium": "【中】",
                    "low": "【低】"
                }
                severity_label = severity_map.get(issue.severity.value, "【未知】")
                problem_list.append(f"{severity_label}{issue.description}")

            return score, problem_list

        except Exception as e:
            self._logger.error(f"逆向反馈分析失败: {e}")
            return 0.7, [f"逆向反馈分析异常: {str(e)}"]

    def _score_naturalness(self, text: str) -> NaturalnessScore:
        """自然度评分"""
        detected_patterns = []
        pattern_scores = {}

        for category, patterns in self.ai_patterns.items():
            category_detections = []
            for pattern in patterns:
                try:
                    matches = re.findall(pattern, text)
                    if matches:
                        category_detections.append(f"{category}: {pattern}")
                except re.error:
                    continue

            if category_detections:
                detected_patterns.extend(category_detections)
                pattern_scores[category] = len(category_detections)

        # 陈词滥调检测
        cliche_count = 0
        if HAS_JIEBA:
            words = list(jieba.cut(text))
            for cliche in self.cliches:
                cliche_count += words.count(cliche)
            total_words = len(words)
            cliche_score = cliche_count / total_words if total_words > 0 else 0.0
        else:
            cliche_score = 0.0

        # 公式化程度
        formulaic_score = self._calculate_formulaic_score(text)

        # AI概率
        total_patterns = sum(pattern_scores.values())
        pattern_probability = min(total_patterns / 10, 1.0)
        ai_probability = (
            pattern_probability * 0.4 +
            formulaic_score * 0.4 +
            cliche_score * 0.2
        )

        # 评分
        if ai_probability <= 0.2:
            score = 1.0
        elif ai_probability <= 0.4:
            score = 0.8
        elif ai_probability <= 0.6:
            score = 0.6
        else:
            score = 0.4

        # 生成问题列表
        issues = []
        if ai_probability > 0.4:
            issues.append(f"AI生成概率较高: {ai_probability:.1%}")
        if formulaic_score > 0.6:
            issues.append("公式化程度较高")
        if cliche_score > 0.05:
            issues.append("陈词滥调较多")

        return NaturalnessScore(
            score=score,
            ai_probability=ai_probability,
            formulaic_score=formulaic_score,
            cliche_score=cliche_score,
            issues_found=issues
        )

    def _generate_suggestions(
        self,
        word_count_score: WordCountScore,
        outline_compliance: OutlineComplianceScore,
        style_consistency: float,
        character_consistency: float,
        worldview_consistency: float,
        naturalness: NaturalnessScore
    ) -> List[str]:
        """生成改进建议"""
        suggestions = []

        # 人设问题
        if character_consistency < 0.7:
            suggestions.append(f"人设不符合(评分{character_consistency:.2f}): 请检查人物对话是否符合性格特征")

        # 世界观问题
        if worldview_consistency < 0.7:
            suggestions.append(f"世界观不符合(评分{worldview_consistency:.2f}): 请检查世界观设定是否准确")

        # 风格问题
        if style_consistency < 0.7:
            suggestions.append(f"风格不一致(评分{style_consistency:.2f}): 请调整语言表达与风格档案保持一致")

        # 大纲符合性
        if outline_compliance.score < 0.8 and outline_compliance.missing_plot_points:
            suggestions.append(f"大纲符合度低: 缺失情节: {'、'.join(outline_compliance.missing_plot_points[:3])}")

        # 字数问题
        if word_count_score.score < 0.8:
            if word_count_score.difference > 0:
                suggestions.append(f"字数超标(超出{word_count_score.difference}字): 请精简内容")
            else:
                suggestions.append(f"字数不足(缺少{abs(word_count_score.difference)}字): 请增加细节描写")

        # 自然度问题
        if naturalness.score < 0.7:
            suggestions.append("AI痕迹检测: 建议增加口语化表达和个性化细节")

        return suggestions[:5]

    # ===== 辅助方法 =====

    def _count_words(self, text: str) -> int:
        """统计字数（精确版）
        
        统计规则：
        - 中文字符：每个算1字
        - 英文单词：每个算1字
        - 数字组：每组算1字
        """
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        digit_groups = len(re.findall(r'\d+', text))
        return chinese_chars + english_words + digit_groups

    def _count_words_excluding_marker(self, text: str) -> int:
        """统计字数（排除【本章完】标记）"""
        clean_text = text.replace("【本章完】", "")
        return self._count_words(clean_text)

    def _extract_plot_points(self, chapter_outline: str) -> List[str]:
        """从大纲中提取关键情节点"""
        if not chapter_outline:
            return []

        key_points = []
        lines = chapter_outline.split('\n')

        for line in lines:
            line = line.strip()
            if line.startswith('#### 第') or line.startswith('## 第'):
                continue
            if not line or len(line) < 4:
                continue
            if line.startswith('**') and line.endswith('**') and len(line) < 20:
                continue
            if any(c in line for c in ['后', '时', '了', '的', '是', '在']):
                key_points.append(line)

        return key_points[:10]

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        if not HAS_JIEBA:
            return []

        words = list(jieba.cut(text))
        stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一'}

        keywords = [w for w in words if len(w) >= 2 and w not in stopwords and w.isalpha()]
        word_freq = Counter(keywords)
        return [word for word, _ in word_freq.most_common(20)]

    def _calculate_formulaic_score(self, text: str) -> float:
        """计算公式化程度"""
        formulaic_patterns = [
            r'在.*的.*下',
            r'从.*的.*角度',
            r'通过.*的.*方式',
        ]

        formulaic_count = sum(len(re.findall(p, text)) for p in formulaic_patterns)
        sentences = self._split_sentences(text)

        return min(formulaic_count / len(sentences), 1.0) if sentences else 0.0

    def _split_sentences(self, text: str) -> List[str]:
        """分割句子"""
        sentences = []
        current_sentence = []

        for char in text:
            current_sentence.append(char)
            if char in '。！？.!?':
                sentence = ''.join(current_sentence).strip()
                if sentence:
                    sentences.append(sentence)
                current_sentence = []

        if current_sentence:
            sentence = ''.join(current_sentence).strip()
            if sentence:
                sentences.append(sentence)

        return sentences

    def shutdown(self) -> bool:
        """优雅关闭插件
        
        清理资源：
        1. 清理AI模式配置
        2. 清理陈词滥调列表
        3. 调用父类shutdown
        """
        try:
            # 清理AI模式配置
            if hasattr(self, 'ai_patterns'):
                self.ai_patterns.clear()
            
            # 清理陈词滥调列表
            if hasattr(self, 'cliches'):
                self.cliches.clear()
            
            self._logger.info(f"[{self.PLUGIN_ID}] 插件已关闭")
            return super().shutdown()
            
        except Exception as e:
            self._logger.error(f"[{self.PLUGIN_ID}] 关闭失败: {e}")
            return False


# ============================================================================
# 模块级函数
# ============================================================================

def get_plugin_class():
    """获取插件类"""
    return QualityValidatorPlugin


def register_plugin():
    """注册插件"""
    return QualityValidatorPlugin


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("质量验证器插件 V1.1 测试")
    print("=" * 60)

    plugin = QualityValidatorPlugin()
    print(f"\n1. 插件元数据:")
    print(f"   ID: {plugin.metadata.id}")
    print(f"   名称: {plugin.metadata.name}")
    print(f"   版本: {plugin.metadata.version}")
    print(f"   类型: {plugin.metadata.plugin_type.value}")

    print(f"\n2. 测试validate方法:")
    test_text = """
    小明和小红在学校的操场上相遇了。
    "你好，"小红说。
    "你好，"小明回答。
    他们决定一起躲雨。
    【本章完】
    """

    scores = plugin.validate(test_text, {'target_word_count': 100})

    print(f"   总分: {scores.total_score:.2f}")
    print(f"   通过: {scores.passed}")
    print(f"   各维度评分:")
    print(f"     - 字数: {scores.word_count_score:.2f}")
    print(f"     - 大纲: {scores.outline_score:.2f}")
    print(f"     - 风格: {scores.style_score:.2f}")
    print(f"     - 人设: {scores.character_score:.2f}")
    print(f"     - 世界观: {scores.worldview_score:.2f}")
    print(f"     - 自然度: {scores.naturalness_score:.2f}")
    print(f"     - 结束标记: {'是' if scores.has_chapter_end else '否'}")

    print(f"\n3. 验证维度: {plugin.get_validation_dimensions()}")

    print(f"\n4. 逆向反馈分析器集成:")
    print(f"   状态: {'已启用' if plugin._reverse_feedback_analyzer else '未启用（需初始化context）'}")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
