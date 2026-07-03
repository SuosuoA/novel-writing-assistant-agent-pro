"""
质量验证器插件 V2.0

版本: 2.0.0
创建日期: 2026-03-23
最后更新: 2026-04-08
迁移来源: V5 scripts/enhanced_weighted_validator.py

功能（V2.0版本 - 9维度评分体系）:
- 世界观一致性评分 (12%)
- 人设一致性评分 (19%)
- 大纲符合性评分 (13%)
- 风格一致性评分 (19%)
- 知识库引用评分 (8%)
- 写作技巧评分 (8%) - V2.0新增
- 字数符合性评分 (8%)
- 上下文衔接评分 (8%) - V2.0新增
- AI感检测评分 (5%) - V2.0新增

V2.0 变更:
- 升级为9维度评分体系（与expert-novel-v1/validator.py统一）
- 新增写作技巧评分维度（writing_technique_score）
- 新增上下文衔接评分维度（context_coherence_score，替代reverse_feedback）
- 新增AI感检测评分维度（ai_feeling_score，替代naturalness）
- 保持向后兼容（旧字段映射到新维度）

核心规则（强制保护）:
1. 章节结束必须添加【本章完】标记
2. 评分阈值 >= 0.8 才能输出
3. 迭代上限 5 次
4. 9维度评分权重可通过配置文件调整
5. 世界观严重违背一票否决

参考文档:
- 《项目总体架构设计说明书V1.5》第四章
- 《插件接口定义V2.1》
- 《12.95开始创作修复方案.md》
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

    实现 ValidatorPlugin 接口，提供8维度加权评分验证（V1.7版本）。

    验证维度:
    - word_count: 字数符合性 (8%)
    - knowledge_reference: 知识点引用 (8%) - V1.7新增
    - outline: 大纲符合性 (13%)
    - style: 风格一致性 (19%)
    - character: 人设一致性 (19%)
    - worldview: 世界观一致性 (12%)
    - reverse_feedback: 逆向反馈 (11%) - V1.7新增
    - naturalness: 自然度 (10%)
    """

    # 类常量
    PLUGIN_ID = "quality-validator-v1"
    PLUGIN_NAME = "质量验证器 V1"
    PLUGIN_VERSION = "2.0.0"

    # 评分权重配置（V2.0版本 - 9维度）
    # 实际权重从config/validator_weights.yaml动态加载
    # 与expert-novel-v1/validator.py维度统一
    DEFAULT_WEIGHTS = {
        'worldview': 0.12,         # 世界观一致性
        'character': 0.19,         # 人设一致性
        'outline': 0.13,           # 大纲符合性
        'style': 0.19,             # 风格一致性
        'knowledge': 0.08,         # 知识库引用
        'writing_technique': 0.08, # 写作技巧
        'word_count': 0.08,        # 字数符合性
        'context_coherence': 0.08, # 上下文衔接
        'ai_feeling': 0.05,        # AI感检测
    }

    def __init__(self):
        """初始化插件"""
        metadata = PluginMetadata(
            id=self.PLUGIN_ID,
            name=self.PLUGIN_NAME,
            version=self.PLUGIN_VERSION,
            description="9维度加权评分验证器（V2.0）",
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

        # 动态权重验证器引用（在initialize中设置）
        self._weight_validator = None

        # 逆向反馈分析器引用（在initialize中设置）
        self._reverse_feedback_analyzer = None

        # 知识检索器引用（在initialize中设置）
        self._knowledge_retriever = None

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
            description="9维度加权评分验证器（V2.0）",
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

    @classmethod
    def get_dimension_display_map(cls) -> Dict[str, str]:
        """获取维度英文→中文映射（唯一真值来源）
        
        V3.0修订：GUI层通过此方法获取维度映射，避免硬编码。
        当维度增删时只需修改此处和DEFAULT_WEIGHTS。
        """
        return {
            'worldview': '世界观',
            'character': '人设',
            'outline': '大纲',
            'style': '风格',
            'knowledge': '知识库',
            'writing_technique': '写作技巧',
            'word_count': '字数',
            'context_coherence': '上下文衔接',
            'ai_feeling': 'AI感',
        }

    @classmethod
    def get_dimension_attr_map(cls) -> Dict[str, str]:
        """获取ValidationScores属性名→维度名的映射（唯一真值来源）
        
        V3.0修订：与get_dimension_display_map()对称，
        GUI层通过此方法获取属性映射，避免硬编码。
        当ValidationScores字段增删时只需修改此处。
        """
        return {
            'worldview_score': 'worldview',
            'character_score': 'character',
            'outline_score': 'outline',
            'style_score': 'style',
            'knowledge_reference_score': 'knowledge',
            'writing_technique_score': 'writing_technique',
            'word_count_score': 'word_count',
            'context_coherence_score': 'context_coherence',
            'ai_feeling_score': 'ai_feeling',
        }

    def initialize(self, context: PluginContext) -> bool:
        """初始化插件"""
        if not super().initialize(context):
            return False

        # 初始化动态权重验证器
        try:
            from scripts.enhanced_weighted_validator import get_validator_instance
            self._weight_validator = get_validator_instance()
            self._logger.info(f"[{self.PLUGIN_ID}] 成功初始化动态权重验证器")
        except Exception as e:
            self._logger.warning(f"[{self.PLUGIN_ID}] 初始化动态权重验证器失败，使用默认配置: {e}")
            self._weight_validator = None

        # 获取逆向反馈分析器插件引用
        # V2.1修复：quality-validator 按字母序先于 reverse-feedback-analyzer 加载，
        # 初始化时查找必然失败 → 上下文一致性检查永远跳过。
        # 改为：保存 registry 引用，初始化时查一次，使用时惰性重查（见 _get_reverse_analyzer）。
        self._reverse_feedback_analyzer = None
        self._plugin_registry_ref = getattr(context, 'plugin_registry', None)
        try:
            if self._plugin_registry_ref:
                self._reverse_feedback_analyzer = self._plugin_registry_ref.get_plugin("reverse-feedback-analyzer")
                if self._reverse_feedback_analyzer:
                    self._logger.info("[质量验证器] 成功获取逆向反馈分析器插件引用")
                else:
                    self._logger.info("[质量验证器] 逆向反馈分析器尚未加载，将在使用时惰性获取")
        except Exception as e:
            self._logger.warning(f"[质量验证器] 获取逆向反馈分析器插件失败: {e}")

        # 初始化知识检索器引用
        self._knowledge_retriever = None
        try:
            from core.knowledge_retriever import get_knowledge_retriever
            from pathlib import Path
            workspace_root = Path(__file__).parent.parent.parent
            self._knowledge_retriever = get_knowledge_retriever(workspace_root)
            if self._knowledge_retriever:
                self._logger.info("[质量验证器] 成功初始化知识检索器")
        except Exception as e:
            self._logger.warning(f"[质量验证器] 初始化知识检索器失败: {e}")

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

        # 获取动态权重配置
        weights = self._get_current_weights()
        self._logger.info(f"当前权重配置: {weights}")

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

        # 1. 世界观一致性评分（一票否决）
        if world_view:
            worldview_consistency, worldview_violation = self._score_worldview_consistency(content, world_view)
        else:
            worldview_consistency = 0.7
            worldview_violation = False

        # 2. 人设一致性评分
        if character_profiles:
            character_consistency = self._score_character_consistency(content, character_profiles)
        else:
            character_consistency = 0.7

        # 3. 大纲符合性评分
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

        # 4. 风格一致性评分
        style_consistency = self._score_style_consistency(content, style_profile)

        # 5. 知识库引用评分（V2.0维度 - 从原knowledge_reference维度升级）
        knowledge_score, recalled_knowledge = self._score_knowledge(content, context)

        # 6. 写作技巧评分（V2.0新增维度）
        writing_technique_score = self._score_writing_technique(content, context)

        # 7. 字数符合性评分
        word_count_score = self._score_word_count(content, target_word_count)

        # 8. 上下文衔接评分（V2.0新增维度 - 替代原reverse_feedback维度）
        context_coherence_score, coherence_issues = self._score_context_coherence(content, context)

        # 9. AI感检测评分（V2.0新增维度 - 从原naturalness维度升级）
        ai_feeling_score, ai_issues = self._score_ai_feeling(content)

        # 检查严重违背世界观（一票否决）
        if worldview_violation:
            self._logger.warning("检测到严重违背世界观，一票否决")
            total_score = 0.0
            passed = False
        else:
            # 计算加权总分（V2.0版本 - 9维度）
            total_score = (
                worldview_consistency * weights['worldview'] +
                character_consistency * weights['character'] +
                outline_compliance.score * weights['outline'] +
                style_consistency * weights['style'] +
                knowledge_score * weights['knowledge'] +
                writing_technique_score * weights['writing_technique'] +
                word_count_score.score * weights['word_count'] +
                context_coherence_score * weights['context_coherence'] +
                ai_feeling_score * weights['ai_feeling']
            )

            # 必须同时满足：总分达标 + 包含结束标记
            passed = (total_score >= 0.8 and has_ending_marker)

        # 创建ValidationScores对象（V2.0版本 - 9维度）
        scores = ValidationScores(
            word_count_score=word_count_score.score,
            outline_score=outline_compliance.score,
            style_score=style_consistency,
            character_score=character_consistency,
            worldview_score=worldview_consistency,
            naturalness_score=ai_feeling_score,  # AI感检测映射到naturalness
            knowledge_reference_score=knowledge_score,  # 兼容旧字段
            reverse_feedback_score=context_coherence_score,  # 兼容旧字段
            # V2.0新增维度字段
            writing_technique_score=writing_technique_score,
            context_coherence_score=context_coherence_score,
            ai_feeling_score=ai_feeling_score,
            total_score=total_score,
            has_chapter_end=has_ending_marker,
            passed=passed  # V2.1：达标判断归属插件层（ADR-010），供Agent/GUI直接读取
        )
        # 设置上下文衔接问题
        if coherence_issues:
            scores.reverse_feedback_issues = [
                {"description": issue, "severity": "medium"}
                for issue in coherence_issues
            ]
        # 设置召回的知识点
        if recalled_knowledge:
            scores.recalled_knowledge = recalled_knowledge

        scores.calculate_total()

        self._logger.info(f"验证完成: 总分={total_score:.2f}, 通过={passed}, 上下文衔接={context_coherence_score:.2f}, AI感={ai_feeling_score:.2f}")
        return scores

    def validate_with_weights(
        self,
        text: str,
        target_word_count: int,
        chapter_outline: str = None,
        style_profile: Dict[str, Any] = None,
        character_profiles: List[Dict] = None,
        world_view: str = None,
        knowledge_categories: List[str] = None
    ) -> WeightedValidationResult:
        """完整验证并返回详细结果（兼容V5接口）

        此方法保留V5原有接口，提供更详细的验证结果。

        V2.13（《无极》九维审计）：新增可选 knowledge_categories——此前
        context 不带 genre，知识维度恒以'通用'空查召回 0 条 → 恒 0.6。
        """
        context = {
            'target_word_count': target_word_count,
            'chapter_outline': chapter_outline,
            'style_profile': style_profile,
            'character_profiles': character_profiles,
            'world_view': world_view
        }
        if knowledge_categories:
            context['genre'] = knowledge_categories[0]
            context['knowledge_categories'] = list(knowledge_categories)

        # 执行验证
        validation_scores = self.validate(text, context)

        # 构建详细结果
        has_ending_marker = "【本章完】" in text

        # V2.16：句子完整性判罚——标记盖在截断悬句上视为未真正完结
        # （《无极》第4章'…长老由归'+【本章完】实证：残缺曾被标记掩盖、
        # 评分满分放行）。检测标记前正文是否以终止标点收束。
        _terminal_punct = ('。', '！', '？', '…', '”', '』', '】', '"', '）', ')')
        ending_truncated = False
        if has_ending_marker:
            _inner = text.rstrip()
            _inner = _inner[:_inner.rfind('【本章完】')].rstrip()
            ending_truncated = bool(_inner) and not _inner.endswith(_terminal_punct)

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
            # V2.16：截断悬句不放行（完整性是达标的前置条件）
            passed = (total_score >= 0.8 and has_ending_marker
                      and not ending_truncated)

        # 构建反馈（V3.0版本 - 9维度，使用英文key作为唯一真值来源）
        # V6.0关键修复：feedback必须使用与get_dimension_display_map()一致的英文key，
        # 否则GUI层的dim_display.get(key)查找失败，导致维度名无法正确显示！
        feedback = {
            'chapter_end': {
                # V2.16：截断悬句+标记=0.3判罚（真实完结才给满分）
                'score': 0.3 if ending_truncated else (1.0 if has_ending_marker else 0.0),
                'details': ('✗ 末句在句中截断，【本章完】盖在残句上（需真实补完结尾）'
                            if ending_truncated else
                            ('✓ 包含【本章完】' if has_ending_marker else '✗ 缺少【本章完】'))
            },
            'worldview': {
                'score': validation_scores.worldview_score,
                'details': '是否符合世界观设定' + ('（一票否决）' if worldview_violation else '')
            },
            'character': {
                'score': validation_scores.character_score,
                'details': '人物行为是否符合设定'
            },
            'outline': {
                'score': validation_scores.outline_score,
                'details': f"匹配{outline_compliance.matched_plot_points}/{outline_compliance.total_plot_points}个情节点"
            },
            'style': {
                'score': validation_scores.style_score,
                'details': '与学习风格的匹配度'
            },
            'knowledge': {
                'score': validation_scores.knowledge_reference_score,
                'details': '知识库知识点引用情况'
            },
            'writing_technique': {
                'score': validation_scores.writing_technique_score,
                'details': '描写手法、叙事技巧运用程度'
            },
            'word_count': {
                'score': validation_scores.word_count_score,
                'details': f"目标{target_word_count}字，实际{word_count_score.actual_words}字"
            },
            'context_coherence': {
                'score': validation_scores.context_coherence_score,
                'details': '与前文的衔接连贯性'
            },
            'ai_feeling': {
                'score': validation_scores.ai_feeling_score,
                'details': f"AI痕迹检测（越低越明显）"
            }
        }

        # 生成改进建议（V2.0版本 - 9维度）
        suggestions = self._generate_suggestions_v2(
            word_count_score, outline_compliance, validation_scores
        )

        if not has_ending_marker:
            suggestions.insert(0, "缺少【本章完】结束标记，请在章节末尾添加【本章完】")
        if ending_truncated:
            suggestions.insert(0, "章节末句在句中截断（【本章完】盖在残句上），"
                                  "请将结尾场景真实写完后再收束")

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
        """获取验证维度（V2.0版本 - 9维度）"""
        return [
            "worldview",          # 世界观（12%）
            "character",          # 人设（19%）
            "outline",            # 大纲（13%）
            "style",              # 风格（19%）
            "knowledge",          # 知识库（8%）
            "writing_technique",  # 写作技巧（8%）- V2.0新增
            "word_count",         # 字数（8%）
            "context_coherence",  # 上下文衔接（8%）- V2.0新增
            "ai_feeling",         # AI感（5%）- V2.0新增
        ]
    
    def _get_current_weights(self) -> Dict[str, float]:
        """获取当前权重配置（支持动态配置和热更新）
        
        Returns:
            权重配置字典
        """
        # 如果动态权重验证器可用，使用动态配置
        if self._weight_validator:
            # 检查配置文件是否修改
            self._weight_validator.check_and_reload_if_modified()
            weights = self._weight_validator.weights
            # V2.1修复：enhanced_weighted_validator 输出的是旧8维键名
            # （knowledge_reference/reverse_feedback/naturalness，且无 writing_technique），
            # 而本插件九维加权用新键名 → KeyError: 'knowledge' → 普通模式评分整体崩溃降级。
            # 仅当动态配置包含全部九维新键时才使用；否则回落锁定的九维默认权重
            # （九维度权重为锁定资产，遗留8维配置不应改变它）。
            if isinstance(weights, dict) and all(k in weights for k in self.DEFAULT_WEIGHTS):
                return weights
            self._logger.debug("[权重] 动态配置为遗留8维键名，使用锁定的九维默认权重")
            return self.DEFAULT_WEIGHTS

        # 否则使用默认配置（V2.0版本 - 9维度）
        return self.DEFAULT_WEIGHTS
    
    def update_weights(self, new_weights: Dict[str, float], updated_by: str = "api") -> bool:
        """热更新权重配置
        
        Args:
            new_weights: 新的权重配置字典
            updated_by: 更新来源标识
        
        Returns:
            是否更新成功
        """
        if not self._weight_validator:
            self._logger.warning("动态权重验证器未初始化，无法热更新")
            return False
        
        return self._weight_validator.update_weights(new_weights, updated_by)
    
    def get_weight_config_info(self) -> Dict[str, Any]:
        """获取权重配置信息
        
        Returns:
            配置信息字典
        """
        if not self._weight_validator:
            return {
                'config_path': None,
                'config_version': 'default',
                'last_updated': 'N/A',
                'updated_by': 'system',
                'weights': self._get_current_weights(),
                'total_weight': sum(self._get_current_weights().values()),
            }
        
        return self._weight_validator.get_config_info()

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
            # V2.16修复量纲倒挂：人名命中（用了配置人设）的地板不得低于
            # 无人物可查的中性兜底0.7——旧地板0.5使"名字命中但性格词零匹配"
            # 得0.6，反而比完全没配置人物（0.7）更低，惩罚了正确行为。
            total_score = min(1.0, base_score + keyword_score + behavior_score + dialog_score)
            total_score = max(0.7, total_score)

            consistency_scores.append(total_score)

        # V2.17：配置了人物但正文一个名字都没命中 = 人设约束被整体忽略
        # （或prompt人物块断裂）——给0.5判罚并区分于中性0.7，让此类静默
        # 失效在评分上可见（V2.13的"魏央顶替林越"曾因两种情况同为0.7而隐身）。
        if not consistency_scores:
            _cfg_names = [
                (c.get('name') or (c.get('basic_info') or {}).get('name', ''))
                for c in character_profiles if isinstance(c, dict)]
            _cfg_names = [n for n in _cfg_names if n][:5]
            self._logger.warning(
                "[质量验证器] 人设维度：配置人物名（%s）均未出现在正文，判罚0.5",
                "、".join(_cfg_names) if _cfg_names else "?")
            return 0.5
        return sum(consistency_scores) / len(consistency_scores)

    def _score_worldview_consistency(self, text: str, world_view: str) -> Tuple[float, bool]:
        """世界观一致性评分（一票否决 + 核心词命中率）

        V2.18修复（九维法证审计C4）：原实现除一票否决分支外恒返回1.0
        ——喂赛博朋克设定给仙侠正文照样满分，维度是存根。移植V2.7
        核心词Top-30命中率算法（与novel-generator内联版同源）：取设定
        高频核心词（专有名词倾向），按正文命中率打分。
        """
        if not world_view:
            return 0.7, False

        # 检查严重违背（一票否决，保留）
        if '现实' in world_view:
            fantasy_keywords = ['魔法', '法术', '异能', '修仙', '仙术']
            if any(kw in text for kw in fantasy_keywords):
                self._logger.warning("检测到现实题材中出现魔法元素，严重违背世界观")
                return 0.0, True

        from collections import Counter
        _stop = {'一个', '可以', '通过', '进行', '以及', '或者', '但是',
                 '如果', '这个', '那个', '成为', '开始', '出现', '存在',
                 '所有', '任何', '之间', '不同', '各种', '之后', '其中'}
        _words = [w for w in re.findall(r'[一-龥]{2,4}', str(world_view))
                  if w not in _stop]
        _core = [w for w, _cnt in Counter(_words).most_common(30)]
        if not _core:
            return 0.7, False
        hit = sum(1 for w in _core if w in text)
        hit_rate = hit / len(_core)
        # 校准：单章只覆盖世界观子集，命中30%核心词即视为充分贴合（1.0）；
        # 零命中=脱设定（0.45底）。比线性0.45+rate*0.9区分度更陡。
        return min(1.0, 0.45 + min(1.0, hit_rate / 0.3) * 0.55), False

    def _score_reverse_feedback(
        self,
        text: str,
        context: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """逆向反馈评分（V1.7新增维度 - 上下文衔接一致性）

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
        # V2.1修复：惰性重查（初始化时因加载顺序拿不到，此时应已加载）
        if not self._reverse_feedback_analyzer and getattr(self, '_plugin_registry_ref', None):
            try:
                self._reverse_feedback_analyzer = self._plugin_registry_ref.get_plugin("reverse-feedback-analyzer")
                if self._reverse_feedback_analyzer:
                    self._logger.info("[质量验证器] 惰性获取逆向反馈分析器成功")
            except Exception:
                pass

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

    def _score_knowledge_reference(
        self,
        text: str,
        context: Dict[str, Any]
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """知识点引用评分（V1.7新增维度 - 知识库功能）

        验证生成内容是否正确引用知识库知识点。

        评分逻辑：
        - 基础分：0.5（默认分）
        - 成功召回知识点：+0.2
        - 知识点在文本中被引用：+0.3
        - 最高分：1.0

        Args:
            text: 章节文本内容
            context: 验证上下文，需包含：
                - genre: 题材类型（科幻/玄幻/都市等）
                - knowledge_retriever: 知识检索器实例（可选）

        Returns:
            Tuple[float, List[Dict]]: (评分, 召回的知识点列表)
        """
        recalled_knowledge = []

        # 尝试获取知识检索器（优先使用实例变量，其次从context获取）
        knowledge_retriever = self._knowledge_retriever or context.get('knowledge_retriever')
        genre = context.get('genre', '通用')

        if not knowledge_retriever:
            self._logger.debug("知识检索器不可用，返回默认知识点引用评分")
            return 0.7, []

        try:
            # 从文本中提取关键词
            keywords = self._extract_keywords(text)[:10]

            if not keywords:
                return 0.6, []

            # 调用知识检索器召回知识点（方法名：recall_knowledge）
            self._logger.info(f"调用知识检索器召回知识点，题材: {genre}, 关键词: {keywords[:5]}")
            results = knowledge_retriever.recall_knowledge(
                query=" ".join(keywords),
                category=genre,
                top_k=5
            )

            if not results:
                return 0.6, []

            # 计算评分
            base_score = 0.5
            recall_bonus = min(0.2, len(results) * 0.05)  # 每个召回的知识点加0.05

            # 检查知识点是否在文本中被引用
            reference_bonus = 0.0
            for result in results:
                knowledge_text = result.content if hasattr(result, 'content') else result.get('content', '')
                # 简单匹配：检查知识点关键词是否出现在文本中
                knowledge_keywords = self._extract_keywords(knowledge_text)[:3]
                if any(kw in text for kw in knowledge_keywords):
                    reference_bonus += 0.1
                    recalled_knowledge.append({
                        "id": result.knowledge_id if hasattr(result, 'knowledge_id') else result.get('id', ''),
                        "content": knowledge_text[:100],
                        "referenced": True
                    })
                else:
                    recalled_knowledge.append({
                        "id": result.knowledge_id if hasattr(result, 'knowledge_id') else result.get('id', ''),
                        "content": knowledge_text[:100],
                        "referenced": False
                    })

            reference_bonus = min(0.3, reference_bonus)
            score = min(1.0, base_score + recall_bonus + reference_bonus)

            self._logger.info(f"知识点引用评分: {score:.2f}, 召回{len(results)}个知识点, 引用{len([k for k in recalled_knowledge if k['referenced']])}个")

            return score, recalled_knowledge

        except Exception as e:
            self._logger.error(f"知识点引用评分失败: {e}")
            return 0.6, []

    def _score_knowledge(self, text: str, context: Dict[str, Any]) -> Tuple[float, List[Dict[str, Any]]]:
        """知识库引用评分（V2.0版本 - 包装原_score_knowledge_reference）

        维度说明：验证生成内容是否正确引用知识库知识点。
        权重：8%

        Returns:
            Tuple[float, List[Dict]]: (评分, 召回的知识点列表)
        """
        return self._score_knowledge_reference(text, context)

    def _score_writing_technique(self, text: str, context: Dict[str, Any]) -> float:
        """写作技巧评分（V2.0新增维度）

        维度说明：评估文本中写作技巧的运用程度，包括描写手法、
        叙事技巧、修辞运用等。权重：8%

        评分逻辑：
        - 对话比例（0-0.25）：合理对话占比增加评分
        - 描写密度（0-0.25）：感官描写（视觉/听觉/触觉等）
        - 修辞运用（0-0.25）：比喻/拟人/排比等
        - 节奏变化（0-0.25）：长短句交替、段落变化

        Returns:
            float: 0.4-1.0
        """
        if not text or len(text) < 100:
            return 0.5

        scores = []

        # 1. 对话比例评分（合理对话占比30%-50%为佳）
        dialog_markers = ['"', '"', '「', '」', '『', '』']
        dialog_chars = sum(1 for c in text if c in dialog_markers)
        dialog_ratio = dialog_chars / len(text) if len(text) > 0 else 0
        if 0.03 <= dialog_ratio <= 0.15:
            scores.append(1.0)
        elif 0.01 <= dialog_ratio <= 0.25:
            scores.append(0.8)
        elif dialog_ratio > 0:
            scores.append(0.6)
        else:
            scores.append(0.4)

        # 2. 感官描写密度
        sensory_keywords = [
            '看', '望', '瞧', '见',  # 视觉
            '听', '闻', '响',  # 听觉
            '摸', '触', '冷', '热', '温暖', '冰凉',  # 触觉
            '香', '臭', '味',  # 嗅觉
            '甜', '苦', '咸', '辣',  # 味觉
        ]
        sensory_count = sum(1 for kw in sensory_keywords if kw in text)
        ideal_count = max(1, len(text) / 800)
        if sensory_count >= ideal_count * 2:
            scores.append(1.0)
        elif sensory_count >= ideal_count:
            scores.append(0.8)
        elif sensory_count > 0:
            scores.append(0.6)
        else:
            scores.append(0.4)

        # 3. 修辞运用
        rhetoric_patterns = [
            r'像[^。？！]{2,15}一样',  # 明喻
            r'仿佛[^。？！]{2,15}般',  # 暗喻
            r'是[^。？！]{2,10}的[^。？！]{2,10}',  # 判断式
        ]
        rhetoric_count = sum(len(re.findall(p, text)) for p in rhetoric_patterns)
        if rhetoric_count >= 3:
            scores.append(1.0)
        elif rhetoric_count >= 1:
            scores.append(0.8)
        else:
            scores.append(0.5)

        # 4. 节奏变化（长短句交替）
        sentences = self._split_sentences(text)
        if len(sentences) >= 4:
            lengths = [len(s) for s in sentences]
            avg_len = sum(lengths) / len(lengths)
            variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
            std_dev = variance ** 0.5
            variation_coefficient = std_dev / avg_len if avg_len > 0 else 0

            if 0.3 <= variation_coefficient <= 0.8:
                scores.append(1.0)
            elif 0.1 <= variation_coefficient <= 1.2:
                scores.append(0.7)
            else:
                scores.append(0.5)
        else:
            scores.append(0.5)

        # 加权平均
        weights = [0.25, 0.25, 0.25, 0.25]
        final_score = sum(s * w for s, w in zip(scores, weights))
        return max(0.4, min(1.0, final_score))

    def _score_context_coherence(self, text: str, context: Dict[str, Any]) -> Tuple[float, List[str]]:
        """上下文衔接评分（V2.0新增维度）

        维度说明：评估当前章节与前文的衔接连贯性。权重：8%

        评分逻辑：
        - 优先调用逆向反馈分析器（如果可用）
        - 降级为本地衔接标记检测

        Returns:
            Tuple[float, List[str]]: (评分, 问题列表)
        """
        issues = []

        # 策略1：调用逆向反馈分析器（复用已有能力）
        if self._reverse_feedback_analyzer:
            try:
                reverse_score, reverse_issues = self._score_reverse_feedback(text, context)
                return reverse_score, reverse_issues
            except Exception:
                pass

        # 策略2：本地衔接标记检测
        coherence_score = 0.7  # 基础分

        # 检测章节开头衔接词
        opening_text = text[:200] if len(text) > 200 else text
        has_opening_hook = any(
            marker in opening_text
            for marker in ['却', '而', '然而', '不过', '但是', '原来', '此时', '这时', '随后', '接着']
        )
        if has_opening_hook:
            coherence_score += 0.1

        # 检测人物承接（开头是否出现前文人物名）
        character_profiles = context.get('character_profiles', [])
        if character_profiles:
            for char_profile in character_profiles[:3]:
                char_name = char_profile.get('name', '') or char_profile.get('basic_info', {}).get('name', '')
                if char_name and char_name in opening_text:
                    coherence_score += 0.05
                    break

        # 检测时间/空间连贯性标记
        time_markers = ['次日', '翌日', '三天后', '一周后', '月余', '半年后', '此时']
        space_markers = ['回到', '来到', '走进', '离开', '抵达']
        has_continuity = any(m in opening_text for m in time_markers + space_markers)
        if has_continuity:
            coherence_score += 0.05

        # 检测突兀转折（无铺垫的重大变化）
        abrupt_markers = ['突然之间', '毫无征兆', '就在这一刻', '谁也没想到']
        abrupt_count = sum(1 for m in abrupt_markers if m in text)
        if abrupt_count > 2:
            coherence_score -= 0.1
            issues.append(f"存在{abrupt_count}处突兀转折，缺乏铺垫")

        coherence_score = max(0.4, min(1.0, coherence_score))

        if coherence_score < 0.6:
            issues.append("上下文衔接度较低，建议增加过渡段落")

        return coherence_score, issues

    def _score_ai_feeling(self, text: str) -> Tuple[float, List[str]]:
        """AI感检测评分（V2.0新增维度）

        维度说明：检测文本中AI生成的痕迹，分数越高表示越自然。
        权重：5%（最低权重，因为该维度不确定性较高）

        评分逻辑：
        - 复用已有naturalness评分的核心逻辑
        - 返回评分和检测到的AI痕迹问题

        Returns:
            Tuple[float, List[str]]: (评分0.4-1.0, 问题列表)
        """
        issues = []

        # V2.18修复（九维法证审计C7）：原实现只用本地naturalness启发式，
        # 从未接入 core/ai_feeling_detector 真检测器——纯AI腔文本（夜幕降临/
        # 难以言喻/命运的齿轮…）反而得1.0。改为主用真检测器（与反AI指导
        # 共享AI_COMMON_WORDS词表），本地启发式仅作检测器不可用时的降级。
        try:
            from core.ai_feeling_detector import detect_ai_feeling
            report = detect_ai_feeling(text)
            score = float(report.naturalness_score)
            for it in (getattr(report, 'issues', None) or [])[:8]:
                issues.append(str(getattr(it, 'description', None) or it))
            return max(0.4, min(1.0, score)), issues
        except Exception as e:
            self._logger.warning(f"[质量验证器] AI感真检测器不可用，降级本地启发式: {e}")

        # 降级路径：本地naturalness启发式 + 额外规则
        naturalness = self._score_naturalness(text)

        # 额外检测：过度正式
        formal_phrases = ['值得注意的是', '综上所述', '总而言之', '不言而喻', '毋庸置疑']
        formal_count = sum(1 for p in formal_phrases if p in text)
        if formal_count >= 2:
            issues.append(f"存在{formal_count}处过度正式表达")

        # 额外检测：三段式结构
        if re.search(r'首先[^。]+。其次[^。]+。最后[^。]+。', text):
            issues.append("检测到典型的三段式AI结构")

        # 额外检测：过度排比
        parallel_count = len(re.findall(r'[^。？！]{4,12}，[^。？！]{4,12}，[^。？！]{4,12}[。？！]', text))
        if parallel_count >= 3:
            issues.append(f"排比结构过多({parallel_count}处)")

        score = naturalness.score
        # 每个额外问题扣0.05
        score = max(0.4, score - len(issues) * 0.05)

        return score, issues

    def _score_naturalness(self, text: str) -> NaturalnessScore:
        """自然度评分（V2.0独立方法 - 被validate_with_weights和_score_ai_feeling共同调用）

        检测文本中的AI生成痕迹，返回NaturalnessScore对象。
        V6.0修复：从_score_ai_feeling内部错误缩进中提取为独立方法。

        Args:
            text: 待检测的文本

        Returns:
            NaturalnessScore: 包含评分、AI概率、公式化程度等详细信息
        """
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
        issues_found = []
        if ai_probability > 0.4:
            issues_found.append(f"AI生成概率较高: {ai_probability:.1%}")
        if formulaic_score > 0.6:
            issues_found.append("公式化程度较高")
        if cliche_score > 0.05:
            issues_found.append("陈词滥调较多")

        return NaturalnessScore(
            score=score,
            ai_probability=ai_probability,
            formulaic_score=formulaic_score,
            cliche_score=cliche_score,
            issues_found=issues_found
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

    def _generate_suggestions_v2(
        self,
        word_count_score: WordCountScore,
        outline_compliance: OutlineComplianceScore,
        scores: ValidationScores
    ) -> List[str]:
        """生成改进建议（V2.0版本 - 9维度）"""
        suggestions = []

        # 世界观问题
        if scores.worldview_score < 0.7:
            suggestions.append(f"世界观不一致(评分{scores.worldview_score:.2f}): 请检查世界观设定是否准确")

        # 人设问题
        if scores.character_score < 0.7:
            suggestions.append(f"人设不符合(评分{scores.character_score:.2f}): 请检查人物对话是否符合性格特征")

        # 风格问题
        if scores.style_score < 0.7:
            suggestions.append(f"风格不一致(评分{scores.style_score:.2f}): 请调整语言表达与风格档案保持一致")

        # 大纲符合性
        if outline_compliance.score < 0.8 and outline_compliance.missing_plot_points:
            suggestions.append(f"大纲符合度低: 缺失情节: {'、'.join(outline_compliance.missing_plot_points[:3])}")

        # 知识库引用
        if scores.knowledge_reference_score < 0.6:
            suggestions.append(f"知识库引用不足(评分{scores.knowledge_reference_score:.2f}): 建议增加专业知识细节")

        # 写作技巧
        if scores.writing_technique_score < 0.6:
            suggestions.append(f"写作技巧不足(评分{scores.writing_technique_score:.2f}): 建议增加对话、感官描写和修辞手法")

        # 字数问题
        if word_count_score.score < 0.8:
            if word_count_score.difference > 0:
                suggestions.append(f"字数超标(超出{word_count_score.difference}字): 请精简内容")
            else:
                suggestions.append(f"字数不足(缺少{abs(word_count_score.difference)}字): 请增加细节描写")

        # 上下文衔接
        if scores.context_coherence_score < 0.6:
            suggestions.append(f"上下文衔接不足(评分{scores.context_coherence_score:.2f}): 建议增加过渡段落")

        # AI感
        if scores.ai_feeling_score < 0.6:
            suggestions.append("AI痕迹明显: 建议增加口语化表达和个性化细节")

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
