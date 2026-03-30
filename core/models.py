"""
数据模型定义 - Pydantic v2模型

V1.3版本（最终修订版）
创建日期：2026-03-21
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class Event(BaseModel):
    """事件模型"""

    model_config = ConfigDict(frozen=False)

    type: str = Field(..., description="事件类型")
    data: Any = Field(None, description="事件数据")
    source: Optional[str] = Field(None, description="事件来源")
    timestamp: Optional[float] = Field(None, description="事件时间戳")
    event_id: Optional[str] = Field(None, description="事件ID")


class HandlerInfo(BaseModel):
    """处理器信息"""

    model_config = ConfigDict(frozen=False)

    id: str = Field(..., description="处理器ID")
    handler: Any = Field(..., description="处理器函数")
    priority: int = Field(20, description="优先级（数值越小越高）")
    is_async: bool = Field(False, description="是否异步执行")
    timeout: float = Field(30.0, description="超时时间（秒）")


class PluginMetadata(BaseModel):
    """插件元数据 - Pydantic版本

    注意：此模型用于PluginInfo和JSON序列化
    字段与plugin_interface.py中的dataclass版本保持一致
    """

    model_config = ConfigDict(frozen=False)

    id: str = Field(..., description="插件ID")
    name: str = Field(..., description="插件名称")
    version: str = Field("1.0.0", description="版本号")
    description: str = Field("", description="描述")
    author: str = Field("", description="作者")
    plugin_type: str = Field("tool", description="插件类型")
    api_version: str = Field("1.0", description="API版本")
    priority: int = Field(100, description="优先级")
    enabled: bool = Field(True, description="是否启用")
    dependencies: List[str] = Field(default_factory=list, description="依赖")
    conflicts: List[str] = Field(default_factory=list, description="冲突")
    permissions: List[str] = Field(default_factory=list, description="权限")
    min_platform_version: str = Field("6.0.0", description="最低平台版本")
    entry_class: str = Field("", description="入口类名")


class PluginInfo(BaseModel):
    """插件信息"""

    model_config = ConfigDict(frozen=False)

    metadata: PluginMetadata = Field(..., description="插件元数据")
    state: str = Field(
        "loaded", description="插件状态"
    )  # 使用小写，与PluginState枚举值一致
    instance: Optional[Any] = Field(None, description="插件实例")
    slot: Optional[str] = Field(None, description="插槽ID")
    error_message: Optional[str] = Field(None, description="错误信息")
    load_time: Optional[datetime] = Field(None, description="加载时间")
    load_count: int = Field(0, description="加载次数")
    error_count: int = Field(0, description="错误次数")


class ValidationScores(BaseModel):
    """验证评分（V1.7版本 - 8维度评分体系）

    权重分配（V1.7版本）：
    - 字数: 8%
    - 知识点引用: 8%
    - 大纲: 13%
    - 风格: 19%
    - 人设: 19%
    - 世界观: 12%
    - 逆向反馈: 11%
    - 自然度: 10%
    总计: 100%

    新增维度说明：
    - knowledge_reference_score: 知识点引用评分（从知识库召回知识点并在生成中引用）
    - reverse_feedback_score: 逆向反馈评分（章节与已设定内容的一致性检查）
    """

    model_config = ConfigDict(frozen=False)

    word_count_score: float = Field(0.0, ge=0, le=1, description="字数评分")
    outline_score: float = Field(0.0, ge=0, le=1, description="大纲评分")
    style_score: float = Field(0.0, ge=0, le=1, description="风格评分")
    character_score: float = Field(0.0, ge=0, le=1, description="人设评分")
    worldview_score: float = Field(0.0, ge=0, le=1, description="世界观评分")
    naturalness_score: float = Field(0.0, ge=0, le=1, description="自然度评分")

    # V1.7新增：知识点引用评分（知识库功能）
    knowledge_reference_score: float = Field(
        0.0, ge=0, le=1, description="知识点引用评分（V1.7新增，知识库召回和引用）"
    )

    # V1.7新增：逆向反馈评分（上下文衔接一致性）
    reverse_feedback_score: float = Field(
        0.0, ge=0, le=1, description="逆向反馈评分（V1.7新增，章节与设定一致性）"
    )

    # 保留旧字段用于向后兼容（已弃用，映射到knowledge_reference_score）
    knowledge_consistency_score: float = Field(
        0.0, ge=0, le=1, description="知识库一致性评分（已弃用，使用knowledge_reference_score）"
    )

    total_score: float = Field(0.0, ge=0, le=1, description="总分")
    has_chapter_end: bool = Field(False, description="是否包含章节结束标记")

    # 知识库验证详情
    knowledge_conflicts: Optional[List[Dict[str, Any]]] = Field(
        None, description="检测到的知识冲突列表"
    )
    recalled_knowledge: Optional[List[Dict[str, Any]]] = Field(
        None, description="召回的相关知识列表"
    )

    # V1.7新增：逆向反馈详情
    reverse_feedback_issues: Optional[List[Dict[str, Any]]] = Field(
        None, description="逆向反馈检测到的问题列表"
    )

    def calculate_total(self) -> float:
        """计算总分（8维度加权）

        权重分配（V1.7版本）：
        - 字数: 8%
        - 知识点引用: 8%
        - 大纲: 13%
        - 风格: 19%
        - 人设: 19%
        - 世界观: 12%
        - 逆向反馈: 11%
        - 自然度: 10%

        总权重: 100%
        """
        raw_score = (
            self.word_count_score * 0.08
            + self.knowledge_reference_score * 0.08
            + self.outline_score * 0.13
            + self.style_score * 0.19
            + self.character_score * 0.19
            + self.worldview_score * 0.12
            + self.reverse_feedback_score * 0.11
            + self.naturalness_score * 0.10
        )

        self.total_score = min(raw_score, 1.0)
        return self.total_score

    def get_score_breakdown(self) -> Dict[str, float]:
        """获取评分明细（包含各维度得分和权重）"""
        return {
            "字数": {
                "score": self.word_count_score,
                "weight": 0.08,
                "weighted_score": self.word_count_score * 0.08,
            },
            "知识点引用": {
                "score": self.knowledge_reference_score,
                "weight": 0.08,
                "weighted_score": self.knowledge_reference_score * 0.08,
            },
            "大纲": {
                "score": self.outline_score,
                "weight": 0.13,
                "weighted_score": self.outline_score * 0.13,
            },
            "风格": {
                "score": self.style_score,
                "weight": 0.19,
                "weighted_score": self.style_score * 0.19,
            },
            "人设": {
                "score": self.character_score,
                "weight": 0.19,
                "weighted_score": self.character_score * 0.19,
            },
            "世界观": {
                "score": self.worldview_score,
                "weight": 0.12,
                "weighted_score": self.worldview_score * 0.12,
            },
            "逆向反馈": {
                "score": self.reverse_feedback_score,
                "weight": 0.11,
                "weighted_score": self.reverse_feedback_score * 0.11,
            },
            "自然度": {
                "score": self.naturalness_score,
                "weight": 0.10,
                "weighted_score": self.naturalness_score * 0.10,
            },
            "总分": {"score": self.total_score, "weight": 1.0, "weighted_score": self.total_score},
        }


class GenerationRequest(BaseModel):
    """生成请求"""

    model_config = ConfigDict(frozen=False)

    request_id: str = Field(..., description="请求ID")
    title: str = Field(..., description="章节标题")
    outline: str = Field(..., description="章节大纲")
    word_count: int = Field(2000, ge=500, le=10000, description="目标字数")
    max_iterations: int = Field(5, ge=1, le=10, description="最大迭代次数")
    context_chapters: int = Field(5, ge=0, le=10, description="上下文章节数")
    style_profile: Optional[Dict[str, Any]] = Field(None, description="风格配置")
    character_profiles: Optional[Dict[str, Any]] = Field(None, description="人物配置")
    worldview_config: Optional[Dict[str, Any]] = Field(None, description="世界观配置")


class GenerationResult(BaseModel):
    """生成结果"""

    model_config = ConfigDict(frozen=False)

    request_id: str = Field(..., description="请求ID")
    content: str = Field(..., description="生成内容")
    word_count: int = Field(0, description="实际字数")
    iteration_count: int = Field(0, description="迭代次数")
    validation_scores: Optional[ValidationScores] = Field(None, description="验证评分")
    error: Optional[str] = Field(None, description="错误信息")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")


class PluginEvent(BaseModel):
    """插件事件"""

    model_config = ConfigDict(frozen=False)

    event_type: str = Field(..., description="事件类型")
    plugin_id: str = Field(..., description="插件ID")
    data: Dict[str, Any] = Field(default_factory=dict, description="事件数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")


# ============================================================================
# 续写功能数据模型（V1.4新增）
# ============================================================================


from enum import Enum


class ContinuationDirection(str, Enum):
    """续写方向枚举"""
    
    NATURAL = "natural"  # 自然续写（按大纲和上下文自然发展）
    SPECIFIC = "specific"  # 特定方向（用户指定情节走向）
    EMOTION = "emotion"  # 情感导向（侧重情感描写）
    ACTION = "action"  # 动作导向（侧重场景和动作）
    DIALOGUE = "dialogue"  # 对话导向（侧重人物对话）


class ContinuationRequest(BaseModel):
    """续写请求参数
    
    续写功能核心参数结构，用于 generate_continuation 方法。
    """
    
    model_config = ConfigDict(frozen=False)
    
    # 必需参数
    starting_text: str = Field(
        ..., 
        description="起始文本（续写的起点，通常为上一段文本的末尾部分）"
    )
    word_count: int = Field(
        500, 
        ge=100, 
        le=5000, 
        description="目标字数（100-5000字）"
    )
    
    # 续写方向
    direction: str = Field(
        "natural", 
        description="续写方向：natural(自然)/specific(特定)/emotion(情感)/action(动作)/dialogue(对话)"
    )
    direction_hint: Optional[str] = Field(
        None, 
        description="方向提示（当direction=specific时，描述具体情节走向）"
    )
    
    # 上下文配置
    outline: Optional[str] = Field(
        None, 
        description="章节大纲（续写需要遵循的情节大纲）"
    )
    characters: Optional[List[Dict[str, Any]]] = Field(
        None, 
        description="人物设定列表（当前场景涉及的角色）"
    )
    worldview: Optional[str] = Field(
        None, 
        description="世界观设定（场景相关的世界观背景）"
    )
    style_profile: Optional[Dict[str, Any]] = Field(
        None, 
        description="风格档案（写作风格特征）"
    )
    previous_chapters: Optional[List[str]] = Field(
        None, 
        description="前文章节文本（用于保持上下文连贯性）"
    )
    
    # 高级选项
    temperature: float = Field(
        0.8, 
        ge=0.0, 
        le=2.0, 
        description="生成温度（0.0-2.0，越高越随机）"
    )
    preserve_ending: bool = Field(
        True, 
        description="是否保留自然结尾（避免断句）"
    )
    request_id: Optional[str] = Field(
        None, 
        description="请求ID（用于追踪和取消）"
    )


class ContinuationMetadata(BaseModel):
    """续写元数据
    
    包含生成过程中的统计信息和诊断数据。
    """
    
    model_config = ConfigDict(frozen=False)
    
    # 模型信息
    model_name: str = Field("", description="使用的模型名称")
    provider: str = Field("", description="模型提供商")
    
    # 性能指标
    generation_time: float = Field(0.0, description="生成耗时（秒）")
    tokens_used: int = Field(0, description="消耗的token数")
    iterations: int = Field(1, description="迭代次数（如有重试）")
    
    # 质量指标
    coherence_score: float = Field(0.0, ge=0, le=1, description="连贯性评分")
    style_match_score: float = Field(0.0, ge=0, le=1, description="风格匹配度")
    
    # 上下文信息
    context_length: int = Field(0, description="上下文长度（字符数）")
    starting_text_length: int = Field(0, description="起始文本长度")
    
    # 时间戳
    timestamp: datetime = Field(default_factory=datetime.now, description="生成时间")


class ContinuationResult(BaseModel):
    """续写结果
    
    续写功能的返回结果结构。
    """
    
    model_config = ConfigDict(frozen=False)
    
    # 核心结果
    text: str = Field(..., description="续写生成的文本内容")
    word_count: int = Field(0, description="实际生成字数")
    
    # 元数据
    metadata: ContinuationMetadata = Field(
        default_factory=ContinuationMetadata, 
        description="生成元数据"
    )
    
    # 状态
    success: bool = Field(True, description="是否成功")
    error: Optional[str] = Field(None, description="错误信息")
    
    # 建议（可选）
    suggestions: Optional[List[str]] = Field(
        None, 
        description="后续续写建议（如可能的情节发展）"
    )
    
    def get_full_text(self, starting_text: str) -> str:
        """获取完整文本（起始文本 + 续写内容）
        
        Args:
            starting_text: 原始起始文本
            
        Returns:
            拼接后的完整文本
        """
        return starting_text + self.text


# ============================================================================
# 快捷创作功能数据模型（V1.4新增）
# ============================================================================


class QuickCreationTarget(str, Enum):
    """快捷创作生成目标枚举"""
    
    WORLDVIEW = "worldview"      # 世界观设定
    OUTLINE = "outline"          # 大纲设定
    CHARACTERS = "characters"    # 人物设定
    PLOT = "plot"               # 情节设定
    ALL = "all"                 # 全部生成


class QuickCreationRequest(BaseModel):
    """快捷创作请求参数
    
    快捷创作功能核心参数结构，用于 QuickCreationPlugin 的各生成方法。
    """
    
    model_config = ConfigDict(frozen=False)
    
    # 必需参数
    keywords: str = Field(
        ..., 
        description="创作关键词（核心创意点，如：玄幻、穿越、复仇、系统）"
    )
    
    # 生成目标
    target: str = Field(
        "all", 
        description="生成目标：worldview(世界观)/outline(大纲)/characters(人物)/plot(情节)/all(全部)"
    )
    
    # 参考文本（可选）
    reference_text: Optional[str] = Field(
        None, 
        description="参考文本（已有的设定或风格参考）"
    )
    reference_type: Optional[str] = Field(
        None, 
        description="参考类型：novel(小说)/outline(大纲)/character(人物)/worldview(世界观)"
    )
    
    # 风格选项
    genre: Optional[str] = Field(
        None, 
        description="题材类型（如：玄幻、都市、言情、科幻）"
    )
    style: Optional[str] = Field(
        None, 
        description="写作风格（如：轻松、严肃、热血、治愈）"
    )
    tone: Optional[str] = Field(
        None, 
        description="基调（如：爽文、虐文、喜剧、悲剧）"
    )
    
    # 数量配置
    character_count: int = Field(
        3, 
        ge=1, 
        le=10, 
        description="人物数量（1-10人）"
    )
    chapter_count: int = Field(
        10, 
        ge=1, 
        le=100, 
        description="章节数量（1-100章）"
    )
    word_count_per_chapter: int = Field(
        2000, 
        ge=500, 
        le=10000, 
        description="每章字数（500-10000字）"
    )
    
    # 高级选项
    detailed_level: str = Field(
        "medium", 
        description="详细程度：brief(简略)/medium(中等)/detailed(详细)"
    )
    include_relationships: bool = Field(
        True, 
        description="是否包含人物关系图"
    )
    include_timeline: bool = Field(
        True, 
        description="是否包含时间线"
    )
    
    # 请求标识
    request_id: Optional[str] = Field(
        None, 
        description="请求ID（用于追踪和取消）"
    )


class WorldviewResult(BaseModel):
    """世界观设定结果"""
    
    model_config = ConfigDict(frozen=False)
    
    # 核心内容
    setting_name: str = Field("", description="世界观名称")
    era: str = Field("", description="时代背景")
    world_structure: str = Field("", description="世界结构（如：三界、平行世界）")
    power_system: str = Field("", description="力量体系（如：修仙等级、异能体系）")
    geography: str = Field("", description="地理环境")
    social_structure: str = Field("", description="社会结构")
    major_forces: List[str] = Field(default_factory=list, description="主要势力")
    rules_and_laws: List[str] = Field(default_factory=list, description="规则与法则")
    special_elements: List[str] = Field(default_factory=list, description="特殊元素")
    background_story: str = Field("", description="背景故事")
    
    # 元数据
    word_count: int = Field(0, description="字数")
    
    def get_full_text(self) -> str:
        """获取完整世界观文本"""
        parts = []
        if self.setting_name:
            parts.append(f"# {self.setting_name}")
        if self.era:
            parts.append(f"\n## 时代背景\n{self.era}")
        if self.world_structure:
            parts.append(f"\n## 世界结构\n{self.world_structure}")
        if self.power_system:
            parts.append(f"\n## 力量体系\n{self.power_system}")
        if self.geography:
            parts.append(f"\n## 地理环境\n{self.geography}")
        if self.social_structure:
            parts.append(f"\n## 社会结构\n{self.social_structure}")
        if self.major_forces:
            parts.append(f"\n## 主要势力\n" + "\n".join(f"- {f}" for f in self.major_forces))
        if self.rules_and_laws:
            parts.append(f"\n## 规则与法则\n" + "\n".join(f"- {r}" for r in self.rules_and_laws))
        if self.special_elements:
            parts.append(f"\n## 特殊元素\n" + "\n".join(f"- {e}" for e in self.special_elements))
        if self.background_story:
            parts.append(f"\n## 背景故事\n{self.background_story}")
        return "\n".join(parts)


class OutlineResult(BaseModel):
    """大纲设定结果"""
    
    model_config = ConfigDict(frozen=False)
    
    # 核心内容
    title: str = Field("", description="作品标题")
    theme: str = Field("", description="主题")
    synopsis: str = Field("", description="故事梗概")
    chapters: List[Dict[str, Any]] = Field(
        default_factory=list, 
        description="章节列表，每章包含：chapter_num(序号)、title(标题)、summary(摘要)、key_events(关键事件)"
    )
    main_plot: str = Field("", description="主线剧情")
    sub_plots: List[str] = Field(default_factory=list, description="支线剧情")
    climax_points: List[str] = Field(default_factory=list, description="高潮节点")
    ending_direction: str = Field("", description="结局走向")
    
    # 元数据
    total_chapters: int = Field(0, description="总章节数")
    estimated_word_count: int = Field(0, description="预估总字数")
    
    def get_full_text(self) -> str:
        """获取完整大纲文本"""
        parts = []
        if self.title:
            parts.append(f"# {self.title}")
        if self.theme:
            parts.append(f"\n## 主题\n{self.theme}")
        if self.synopsis:
            parts.append(f"\n## 故事梗概\n{self.synopsis}")
        if self.main_plot:
            parts.append(f"\n## 主线剧情\n{self.main_plot}")
        if self.sub_plots:
            parts.append(f"\n## 支线剧情\n" + "\n".join(f"- {p}" for p in self.sub_plots))
        if self.chapters:
            parts.append(f"\n## 章节大纲\n")
            for ch in self.chapters:
                parts.append(f"第{ch.get('chapter_num', '?')}章：{ch.get('title', '待定')}")
                if ch.get('summary'):
                    parts.append(f"  摘要：{ch['summary']}")
                if ch.get('key_events'):
                    parts.append(f"  关键事件：{', '.join(ch['key_events'])}")
                parts.append("")
        if self.climax_points:
            parts.append(f"\n## 高潮节点\n" + "\n".join(f"- {c}" for c in self.climax_points))
        if self.ending_direction:
            parts.append(f"\n## 结局走向\n{self.ending_direction}")
        return "\n".join(parts)


class CharacterResult(BaseModel):
    """人物设定结果"""
    
    model_config = ConfigDict(frozen=False)
    
    # 核心内容
    name: str = Field("", description="人物名称")
    role: str = Field("", description="角色定位（主角/配角/反派）")
    age: str = Field("", description="年龄")
    gender: str = Field("", description="性别")
    appearance: str = Field("", description="外貌描述")
    personality: str = Field("", description="性格特点")
    background: str = Field("", description="背景故事")
    abilities: List[str] = Field(default_factory=list, description="能力/技能")
    goals: List[str] = Field(default_factory=list, description="目标/动机")
    weaknesses: List[str] = Field(default_factory=list, description="弱点/缺陷")
    relationships: Dict[str, str] = Field(
        default_factory=dict, 
        description="人物关系：{人物名: 关系描述}"
    )
    speech_pattern: str = Field("", description="说话风格")
    character_arc: str = Field("", description="人物弧线")
    
    # 元数据
    word_count: int = Field(0, description="字数")
    
    def get_full_text(self) -> str:
        """获取完整人物设定文本"""
        parts = []
        parts.append(f"# {self.name or '未命名角色'}")
        parts.append(f"\n## 基本信息")
        parts.append(f"- 角色定位：{self.role}")
        parts.append(f"- 年龄：{self.age}")
        parts.append(f"- 性别：{self.gender}")
        if self.appearance:
            parts.append(f"\n## 外貌描述\n{self.appearance}")
        if self.personality:
            parts.append(f"\n## 性格特点\n{self.personality}")
        if self.background:
            parts.append(f"\n## 背景故事\n{self.background}")
        if self.abilities:
            parts.append(f"\n## 能力技能\n" + "\n".join(f"- {a}" for a in self.abilities))
        if self.goals:
            parts.append(f"\n## 目标动机\n" + "\n".join(f"- {g}" for g in self.goals))
        if self.weaknesses:
            parts.append(f"\n## 弱点缺陷\n" + "\n".join(f"- {w}" for w in self.weaknesses))
        if self.relationships:
            parts.append(f"\n## 人物关系")
            for name, rel in self.relationships.items():
                parts.append(f"- {name}：{rel}")
        if self.speech_pattern:
            parts.append(f"\n## 说话风格\n{self.speech_pattern}")
        if self.character_arc:
            parts.append(f"\n## 人物弧线\n{self.character_arc}")
        return "\n".join(parts)


class PlotResult(BaseModel):
    """情节设定结果"""
    
    model_config = ConfigDict(frozen=False)
    
    # 核心内容
    plot_name: str = Field("", description="情节名称")
    plot_type: str = Field("", description="情节类型（主线/支线/感情线等）")
    participants: List[str] = Field(default_factory=list, description="参与角色")
    setting: str = Field("", description="场景设定")
    beginning: str = Field("", description="开端")
    development: str = Field("", description="发展")
    climax: str = Field("", description="高潮")
    resolution: str = Field("", description="结局")
    conflicts: List[str] = Field(default_factory=list, description="冲突点")
    turning_points: List[str] = Field(default_factory=list, description="转折点")
    foreshadowing: List[str] = Field(default_factory=list, description="伏笔")
    
    # 元数据
    word_count: int = Field(0, description="字数")
    involved_chapters: List[int] = Field(default_factory=list, description="涉及章节")
    
    def get_full_text(self) -> str:
        """获取完整情节设定文本"""
        parts = []
        parts.append(f"# {self.plot_name or '未命名情节'}")
        parts.append(f"\n## 情节类型\n{self.plot_type}")
        if self.participants:
            parts.append(f"\n## 参与角色\n" + ", ".join(self.participants))
        if self.setting:
            parts.append(f"\n## 场景设定\n{self.setting}")
        parts.append(f"\n## 情节发展")
        if self.beginning:
            parts.append(f"\n### 开端\n{self.beginning}")
        if self.development:
            parts.append(f"\n### 发展\n{self.development}")
        if self.climax:
            parts.append(f"\n### 高潮\n{self.climax}")
        if self.resolution:
            parts.append(f"\n### 结局\n{self.resolution}")
        if self.conflicts:
            parts.append(f"\n## 冲突点\n" + "\n".join(f"- {c}" for c in self.conflicts))
        if self.turning_points:
            parts.append(f"\n## 转折点\n" + "\n".join(f"- {t}" for t in self.turning_points))
        if self.foreshadowing:
            parts.append(f"\n## 伏笔\n" + "\n".join(f"- {f}" for f in self.foreshadowing))
        return "\n".join(parts)


class QuickCreationMetadata(BaseModel):
    """快捷创作元数据
    
    包含生成过程中的统计信息和诊断数据。
    """
    
    model_config = ConfigDict(frozen=False)
    
    # 模型信息
    model_name: str = Field("", description="使用的模型名称")
    provider: str = Field("", description="模型提供商")
    
    # 性能指标
    generation_time: float = Field(0.0, description="生成耗时（秒）")
    tokens_used: int = Field(0, description="消耗的token数")
    
    # 生成统计
    targets_generated: List[str] = Field(
        default_factory=list, 
        description="已生成的目标列表"
    )
    
    # 时间戳
    timestamp: datetime = Field(default_factory=datetime.now, description="生成时间")


class QuickCreationResult(BaseModel):
    """快捷创作结果
    
    快捷创作功能的返回结果结构，支持单项或全部生成。
    """
    
    model_config = ConfigDict(frozen=False)
    
    # 请求信息
    request_id: str = Field("", description="请求ID")
    keywords: str = Field("", description="输入关键词")
    target: str = Field("all", description="生成目标")
    
    # 各项生成结果（按需填充）
    worldview: Optional[WorldviewResult] = Field(None, description="世界观设定")
    outline: Optional[OutlineResult] = Field(None, description="大纲设定")
    characters: Optional[List[CharacterResult]] = Field(None, description="人物设定列表")
    plot: Optional[PlotResult] = Field(None, description="情节设定")
    
    # 元数据
    metadata: QuickCreationMetadata = Field(
        default_factory=QuickCreationMetadata, 
        description="生成元数据"
    )
    
    # 状态
    success: bool = Field(True, description="是否成功")
    error: Optional[str] = Field(None, description="错误信息")
    
    # 建议（可选）
    suggestions: Optional[List[str]] = Field(
        None, 
        description="后续创作建议"
    )
    
    def get_generated_items(self) -> Dict[str, Any]:
        """获取已生成的项目字典"""
        items = {}
        if self.worldview:
            items["worldview"] = self.worldview
        if self.outline:
            items["outline"] = self.outline
        if self.characters:
            items["characters"] = self.characters
        if self.plot:
            items["plot"] = self.plot
        return items
    
    def get_all_text(self) -> Dict[str, str]:
        """获取所有生成的文本内容"""
        texts = {}
        if self.worldview:
            texts["worldview"] = self.worldview.get_full_text()
        if self.outline:
            texts["outline"] = self.outline.get_full_text()
        if self.characters:
            texts["characters"] = "\n\n---\n\n".join(
                ch.get_full_text() for ch in self.characters
            )
        if self.plot:
            texts["plot"] = self.plot.get_full_text()
        return texts
