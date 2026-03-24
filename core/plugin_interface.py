"""
插件接口定义

V2.0最终版
创建日期：2026-03-21

特性：
- BasePlugin基础接口（符合架构设计说明书V1.2）
- PluginMetadata/PluginContext数据类
- 专用插件接口（Analyzer/Generator/Validator/AI/Storage/Tool/Protocol）
- 生命周期管理（initialize/shutdown/cleanup）
- V5核心模块保护机制

参考文档：
- 《项目总体架构设计说明书V1.2》第四章
- 《项目协作指南V1.1》
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from uuid import uuid4

from .models import (
    GenerationRequest, 
    GenerationResult, 
    ValidationScores,
    ContinuationRequest,
    ContinuationResult,
    ContinuationDirection,
    QuickCreationRequest,
    QuickCreationResult,
    QuickCreationTarget,
    WorldviewResult,
    OutlineResult,
    CharacterResult,
    PlotResult,
)

if TYPE_CHECKING:
    from .config_manager import ConfigManager
    from .event_bus import EventBus
    from .plugin_registry import PluginRegistry
    from .service_locator import ServiceLocator


class PluginType(Enum):
    """插件类型枚举"""

    PROTOCOL = "protocol"
    AI = "ai"
    STORAGE = "storage"
    ANALYZER = "analyzer"
    GENERATOR = "generator"
    VALIDATOR = "validator"
    TOOL = "tool"


class PluginState(Enum):
    """插件状态枚举 - 与架构文档V1.2一致"""

    UNLOADED = "unloaded"  # 未加载（初始状态）
    LOADED = "loaded"  # 已加载（初始化完成）
    ACTIVE = "active"  # 已激活（可执行）
    ERROR = "error"  # 错误状态
    UNLOADING = "unloading"  # 卸载中


@dataclass
class PluginMetadata:
    """插件元数据

    与架构设计说明书V1.2 4.2.1节一致
    """

    id: str  # 唯一标识符（如：outline-parser-v3）
    name: str  # 显示名称
    version: str  # 版本号（语义化版本）
    description: str  # 描述
    author: str  # 作者
    plugin_type: PluginType  # 插件类型
    api_version: str = "1.0"  # API版本
    priority: int = 100  # 加载优先级（越小越先）
    enabled: bool = True  # 是否启用
    dependencies: List[str] = field(default_factory=list)  # 依赖插件ID列表
    conflicts: List[str] = field(default_factory=list)  # 冲突插件ID列表
    permissions: List[str] = field(default_factory=list)  # 所需权限
    min_platform_version: str = "6.0.0"  # 最低平台版本
    entry_class: str = ""  # 入口类名（plugin.json使用）

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "plugin_type": self.plugin_type.value,
            "api_version": self.api_version,
            "priority": self.priority,
            "enabled": self.enabled,
            "dependencies": self.dependencies,
            "conflicts": self.conflicts,
            "permissions": self.permissions,
            "min_platform_version": self.min_platform_version,
            "entry_class": self.entry_class,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginMetadata":
        """从字典创建"""
        plugin_type = data.get("plugin_type", "tool")
        if isinstance(plugin_type, str):
            plugin_type = PluginType(plugin_type.lower())

        return cls(
            id=data["id"],
            name=data["name"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            plugin_type=plugin_type,
            api_version=data.get("api_version", "1.0"),
            priority=data.get("priority", 100),
            enabled=data.get("enabled", True),
            dependencies=data.get("dependencies", []),
            conflicts=data.get("conflicts", []),
            permissions=data.get("permissions", []),
            min_platform_version=data.get("min_platform_version", "6.0.0"),
            entry_class=data.get("entry_class", ""),
        )


@dataclass
class PluginContext:
    """插件上下文

    与架构设计说明书V1.2 4.2.1节一致
    """

    event_bus: "EventBus"
    service_locator: "ServiceLocator"
    config_manager: "ConfigManager"
    plugin_registry: "PluginRegistry"
    logger: Optional[Any] = None  # StructuredLogger

    # V5核心模块保护引用
    v5_modules: Dict[str, Any] = field(default_factory=dict)


class BasePlugin(ABC):
    """插件基类

    所有插件必须继承此类并实现必要的方法。

    与架构设计说明书V1.2 4.2.1节一致：
    - 不包含execute()方法，使用专用接口
    - 支持initialize/shutdown/cleanup生命周期
    """

    def __init__(self, metadata: PluginMetadata):
        """初始化插件

        Args:
            metadata: 插件元数据
        """
        self.metadata = metadata
        self._context: Optional[PluginContext] = None
        self._cleanup_done = False
        self._state: PluginState = PluginState.LOADED

    @classmethod
    @abstractmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据（类方法）

        子类必须实现此方法返回插件元数据。

        Returns:
            插件元数据对象
        """
        pass

    def initialize(self, context: PluginContext) -> bool:
        """初始化插件

        Args:
            context: 插件上下文（包含EventBus、ConfigManager等）

        Returns:
            是否初始化成功
        """
        self._context = context
        self._state = PluginState.LOADED
        return True

    def shutdown(self) -> bool:
        """关闭插件 - 优雅关闭，释放资源

        Returns:
            是否关闭成功
        """
        return True

    def cleanup(self) -> bool:
        """强制资源回收 - 与shutdown区分

        Returns:
            是否清理成功
        """
        self._cleanup_done = True
        return True

    @property
    def state(self) -> PluginState:
        """获取插件状态（只读）"""
        return self._state

    def _set_state(self, value: PluginState):
        """设置插件状态（内部方法，仅PluginRegistry调用）"""
        self._state = value

    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._context is not None

    @property
    def context(self) -> Optional[PluginContext]:
        """获取插件上下文"""
        return self._context


# ============================================================================
# 专用插件接口
# ============================================================================


class AnalyzerPlugin(BasePlugin):
    """分析器插件接口

    用于大纲解析、风格学习、人物管理、世界观解析等。

    与架构设计说明书V1.2 4.2.3节一致。
    """

    @abstractmethod
    def analyze(
        self, content: str, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """分析内容并返回结果

        Args:
            content: 待分析内容
            options: 分析选项

        Returns:
            分析结果字典
        """
        pass

    @abstractmethod
    def get_supported_formats(self) -> List[str]:
        """获取支持的输入格式

        Returns:
            格式列表（如：["txt", "json", "yaml"]）
        """
        pass

    @abstractmethod
    def get_analysis_types(self) -> List[str]:
        """获取支持的分析类型

        Returns:
            分析类型列表（如：["outline", "style", "character"]）
        """
        pass


class GeneratorPlugin(BasePlugin):
    """生成器插件接口

    用于上下文构建、小说生成等。

    与架构设计说明书V1.2 4.2.3节一致。
    """

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """生成内容

        Args:
            request: 生成请求（Pydantic模型）

        Returns:
            生成结果
        """
        pass

    @abstractmethod
    def validate_request(self, request: GenerationRequest) -> tuple[bool, List[str]]:
        """验证请求是否有效

        Args:
            request: 生成请求

        Returns:
            (是否有效, 错误消息列表)
        """
        pass

    @abstractmethod
    def get_generation_options(self) -> Dict[str, Any]:
        """获取生成选项定义

        Returns:
            选项定义字典
        """
        pass

    def cancel(self, request_id: str) -> bool:
        """取消生成（可选实现）

        Args:
            request_id: 请求ID

        Returns:
            是否取消成功
        """
        return False


class ContinuationPlugin(GeneratorPlugin):
    """续写插件接口

    用于基于现有文本进行智能续写，支持自然续写和特定方向续写。
    
    继承自 GeneratorPlugin，扩展了专门的续写能力。
    
    核心方法：
        - generate_continuation: 续写核心方法
        - get_continuation_options: 获取续写选项
        - estimate_continuation: 预估续写效果
    
    设计原则：
        - 起始文本 + 字数 + 方向 + 上下文 → 续写结果
        - 支持多种续写方向（自然/特定/情感/动作/对话）
        - 上下文包含大纲、人设、世界观、风格、前文
        - 返回结果包含文本和元数据（模型、耗时等）
    """

    @abstractmethod
    def generate_continuation(
        self, 
        request: ContinuationRequest
    ) -> ContinuationResult:
        """执行续写

        核心方法：基于起始文本和上下文，生成续写内容。

        Args:
            request: 续写请求参数，包含：
                - starting_text: 起始文本（续写起点）
                - word_count: 目标字数（100-5000）
                - direction: 续写方向（natural/specific/emotion/action/dialogue）
                - direction_hint: 方向提示（特定方向时使用）
                - outline: 章节大纲
                - characters: 人物设定列表
                - worldview: 世界观设定
                - style_profile: 风格档案
                - previous_chapters: 前文章节文本
                - temperature: 生成温度
                - preserve_ending: 是否保留自然结尾

        Returns:
            ContinuationResult: 续写结果，包含：
                - text: 续写文本
                - word_count: 实际字数
                - metadata: 元数据（模型、耗时、token等）
                - success: 是否成功
                - error: 错误信息（如有）
                - suggestions: 后续建议（可选）
        """
        pass

    def get_continuation_options(self) -> Dict[str, Any]:
        """获取续写选项定义

        返回支持的续写配置选项，供UI层使用。

        Returns:
            选项定义字典，包含：
            {
                "directions": {
                    "natural": "自然续写",
                    "specific": "特定方向",
                    "emotion": "情感导向",
                    "action": "动作导向",
                    "dialogue": "对话导向"
                },
                "word_count_range": {"min": 100, "max": 5000, "default": 500},
                "temperature_range": {"min": 0.0, "max": 2.0, "default": 0.8},
                "supported_contexts": ["outline", "characters", "worldview", "style_profile", "previous_chapters"]
            }
        """
        return {
            "directions": {
                ContinuationDirection.NATURAL.value: "自然续写 - 按大纲和上下文自然发展",
                ContinuationDirection.SPECIFIC.value: "特定方向 - 用户指定情节走向",
                ContinuationDirection.EMOTION.value: "情感导向 - 侧重情感描写",
                ContinuationDirection.ACTION.value: "动作导向 - 侧重场景和动作",
                ContinuationDirection.DIALOGUE.value: "对话导向 - 侧重人物对话"
            },
            "word_count_range": {"min": 100, "max": 5000, "default": 500},
            "temperature_range": {"min": 0.0, "max": 2.0, "default": 0.8},
            "supported_contexts": [
                "outline", 
                "characters", 
                "worldview", 
                "style_profile", 
                "previous_chapters"
            ]
        }

    def estimate_continuation(
        self, 
        request: ContinuationRequest
    ) -> Dict[str, Any]:
        """预估续写效果（可选实现）

        在实际生成前，预估续写的大致效果和资源消耗。
        用于UI预览和资源规划。

        Args:
            request: 续写请求参数

        Returns:
            预估信息字典，包含：
            {
                "estimated_tokens": int,  # 预估token消耗
                "estimated_time": float,  # 预估耗时（秒）
                "context_completeness": float,  # 上下文完整度（0-1）
                "suggestions": List[str]  # 优化建议
            }
        """
        # 默认实现：简单预估
        word_count = request.word_count or 500
        return {
            "estimated_tokens": int(word_count * 1.5),  # 中文约1.5 token/字
            "estimated_time": word_count * 0.1,  # 约100字/秒
            "context_completeness": self._evaluate_context_completeness(request),
            "suggestions": self._generate_context_suggestions(request)
        }

    def _evaluate_context_completeness(self, request: ContinuationRequest) -> float:
        """评估上下文完整度（内部方法）"""
        score = 0.0
        if request.outline:
            score += 0.25
        if request.characters:
            score += 0.25
        if request.worldview:
            score += 0.2
        if request.style_profile:
            score += 0.2
        if request.previous_chapters:
            score += 0.1
        return score

    def _generate_context_suggestions(self, request: ContinuationRequest) -> List[str]:
        """生成上下文优化建议（内部方法）"""
        suggestions = []
        if not request.outline:
            suggestions.append("建议提供章节大纲以获得更好的情节连贯性")
        if not request.characters:
            suggestions.append("建议提供人物设定以保持角色一致性")
        if not request.style_profile:
            suggestions.append("建议提供风格档案以匹配写作风格")
        return suggestions

    # 实现父类GeneratorPlugin的抽象方法（委托给续写方法）
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """实现父类generate方法（适配GenerationRequest）

        将GenerationRequest转换为ContinuationRequest并调用generate_continuation。

        Args:
            request: 生成请求

        Returns:
            生成结果
        """
        # 转换请求参数
        continuation_request = ContinuationRequest(
            starting_text=request.title,  # 使用标题作为起始文本
            word_count=request.word_count,
            direction=ContinuationDirection.NATURAL.value,
            outline=request.outline,
            characters=request.character_profiles.get("characters") if request.character_profiles else None,
            worldview=request.worldview_config.get("worldview") if request.worldview_config else None,
            style_profile=request.style_profile,
            request_id=request.request_id
        )
        
        # 调用续写方法
        result = self.generate_continuation(continuation_request)
        
        # 转换结果
        from datetime import datetime
        return GenerationResult(
            request_id=request.request_id,
            content=result.text,
            word_count=result.word_count,
            iteration_count=result.metadata.iterations,
            error=result.error,
            timestamp=datetime.now()
        )

    def validate_request(self, request: GenerationRequest) -> tuple[bool, List[str]]:
        """验证请求是否有效"""
        errors = []
        
        if not request.title:
            errors.append("起始文本不能为空")
        if request.word_count < 100 or request.word_count > 5000:
            errors.append(f"字数范围应为100-5000，当前为{request.word_count}")
            
        return len(errors) == 0, errors

    def get_generation_options(self) -> Dict[str, Any]:
        """获取生成选项定义（委托给续写选项）"""
        return self.get_continuation_options()


class ValidatorPlugin(BasePlugin):
    """验证器插件接口

    用于内容质量评分验证。

    与架构设计说明书V1.2 4.2.3节一致。
    """

    @abstractmethod
    def validate(
        self, content: str, context: Optional[Dict[str, Any]] = None
    ) -> ValidationScores:
        """验证内容并返回评分

        Args:
            content: 待验证内容
            context: 验证上下文

        Returns:
            验证评分（ValidationScores Pydantic模型）
        """
        pass

    @abstractmethod
    def get_validation_dimensions(self) -> List[str]:
        """获取验证维度

        Returns:
            维度列表（如：["word_count", "style", "character"]）
        """
        pass


class StoragePlugin(BasePlugin):
    """存储插件接口

    用于数据持久化。
    """

    @abstractmethod
    def save(
        self, key: str, data: Any, metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """保存数据

        Args:
            key: 数据键
            data: 数据内容
            metadata: 元数据

        Returns:
            是否保存成功
        """
        pass

    @abstractmethod
    def load(self, key: str) -> Optional[Any]:
        """加载数据

        Args:
            key: 数据键

        Returns:
            数据内容
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除数据

        Args:
            key: 数据键

        Returns:
            是否删除成功
        """
        pass

    @abstractmethod
    def list_keys(self, prefix: str = "") -> List[str]:
        """列出所有键

        Args:
            prefix: 键前缀

        Returns:
            键列表
        """
        pass


class AIPlugin(BasePlugin):
    """AI插件接口

    用于LLM调用封装。
    """

    @abstractmethod
    def call(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        """调用AI模型

        Args:
            prompt: 提示词
            context: 调用上下文

        Returns:
            AI响应
        """
        pass

    @abstractmethod
    def stream_call(self, prompt: str, context: Optional[Dict[str, Any]] = None):
        """流式调用AI模型

        Args:
            prompt: 提示词
            context: 调用上下文

        Yields:
            AI响应片段
        """
        pass


class ToolPlugin(BasePlugin):
    """工具插件接口

    用于通用工具功能（如热榜功能）。
    """

    @abstractmethod
    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具操作

        Args:
            action: 操作名称
            params: 操作参数

        Returns:
            执行结果
        """
        pass


class QuickCreationPlugin(ToolPlugin):
    """快捷创作插件接口

    用于快速生成小说创作所需的各项设定（世界观、大纲、人物、情节）。
    
    继承自 ToolPlugin，提供专门的快捷创作能力。
    
    核心方法：
        - generate_worldview: 生成世界观设定
        - generate_outline: 生成大纲设定
        - generate_characters: 生成人物设定
        - generate_plot: 生成情节设定
        - generate_all: 生成全部设定
    
    设计原则：
        - 关键词 + 参考文本 + 生成目标 → 设定结果
        - 支持单项生成和全部生成
        - 各设定之间保持一致性和关联性
        - 返回结构化数据，便于后续使用和编辑
    """

    @abstractmethod
    def generate_worldview(
        self, 
        request: QuickCreationRequest
    ) -> WorldviewResult:
        """生成世界观设定

        核心方法：基于关键词生成完整的世界观设定。

        Args:
            request: 快捷创作请求参数，包含：
                - keywords: 创作关键词（必需）
                - reference_text: 参考文本（可选）
                - genre: 题材类型（可选）
                - detailed_level: 详细程度（brief/medium/detailed）

        Returns:
            WorldviewResult: 世界观设定结果，包含：
                - setting_name: 世界观名称
                - era: 时代背景
                - world_structure: 世界结构
                - power_system: 力量体系
                - geography: 地理环境
                - social_structure: 社会结构
                - major_forces: 主要势力
                - rules_and_laws: 规则与法则
                - special_elements: 特殊元素
                - background_story: 背景故事
        """
        pass

    @abstractmethod
    def generate_outline(
        self, 
        request: QuickCreationRequest,
        worldview: Optional[WorldviewResult] = None
    ) -> OutlineResult:
        """生成大纲设定

        核心方法：基于关键词和世界观生成大纲设定。

        Args:
            request: 快捷创作请求参数，包含：
                - keywords: 创作关键词（必需）
                - reference_text: 参考文本（可选）
                - chapter_count: 章节数量
                - word_count_per_chapter: 每章字数
            worldview: 世界观设定（用于保持一致性，可选）

        Returns:
            OutlineResult: 大纲设定结果，包含：
                - title: 作品标题
                - theme: 主题
                - synopsis: 故事梗概
                - chapters: 章节列表
                - main_plot: 主线剧情
                - sub_plots: 支线剧情
                - climax_points: 高潮节点
                - ending_direction: 结局走向
        """
        pass

    @abstractmethod
    def generate_characters(
        self, 
        request: QuickCreationRequest,
        outline: Optional[OutlineResult] = None,
        worldview: Optional[WorldviewResult] = None
    ) -> List[CharacterResult]:
        """生成人物设定

        核心方法：基于关键词、大纲和世界观生成人物设定。

        Args:
            request: 快捷创作请求参数，包含：
                - keywords: 创作关键词（必需）
                - reference_text: 参考文本（可选）
                - character_count: 人物数量
                - include_relationships: 是否包含人物关系
            outline: 大纲设定（用于保持角色与剧情一致，可选）
            worldview: 世界观设定（用于保持角色与世界一致，可选）

        Returns:
            List[CharacterResult]: 人物设定列表，每个包含：
                - name: 人物名称
                - role: 角色定位（主角/配角/反派）
                - appearance: 外貌描述
                - personality: 性格特点
                - background: 背景故事
                - abilities: 能力/技能
                - goals: 目标/动机
                - weaknesses: 弱点/缺陷
                - relationships: 人物关系
                - speech_pattern: 说话风格
                - character_arc: 人物弧线
        """
        pass

    @abstractmethod
    def generate_plot(
        self, 
        request: QuickCreationRequest,
        outline: Optional[OutlineResult] = None,
        characters: Optional[List[CharacterResult]] = None,
        worldview: Optional[WorldviewResult] = None
    ) -> PlotResult:
        """生成情节设定

        核心方法：基于关键词、大纲、人物和世界观生成情节设定。

        Args:
            request: 快捷创作请求参数，包含：
                - keywords: 创作关键词（必需）
                - reference_text: 参考文本（可选）
            outline: 大纲设定（用于情节与主线一致）
            characters: 人物设定（用于角色行为一致）
            worldview: 世界观设定（用于场景一致）

        Returns:
            PlotResult: 情节设定结果，包含：
                - plot_name: 情节名称
                - plot_type: 情节类型
                - participants: 参与角色
                - setting: 场景设定
                - beginning: 开端
                - development: 发展
                - climax: 高潮
                - resolution: 结局
                - conflicts: 冲突点
                - turning_points: 转折点
                - foreshadowing: 伏笔
        """
        pass

    def generate_all(
        self, 
        request: QuickCreationRequest
    ) -> QuickCreationResult:
        """生成全部设定

        统一方法：按顺序生成世界观、大纲、人物、情节，确保一致性。

        Args:
            request: 快捷创作请求参数

        Returns:
            QuickCreationResult: 完整的创作设定结果，包含：
                - worldview: 世界观设定
                - outline: 大纲设定
                - characters: 人物设定列表
                - plot: 情节设定
                - metadata: 生成元数据
        """
        result = QuickCreationResult(
            request_id=request.request_id or f"qc-{uuid4().hex[:8]}",
            keywords=request.keywords,
            target=QuickCreationTarget.ALL.value
        )
        
        try:
            # 1. 生成世界观
            result.worldview = self.generate_worldview(request)
            result.metadata.targets_generated.append("worldview")
            
            # 2. 生成大纲（基于世界观）
            result.outline = self.generate_outline(request, result.worldview)
            result.metadata.targets_generated.append("outline")
            
            # 3. 生成人物（基于世界观和大纲）
            result.characters = self.generate_characters(
                request, result.outline, result.worldview
            )
            result.metadata.targets_generated.append("characters")
            
            # 4. 生成情节（基于全部设定）
            result.plot = self.generate_plot(
                request, result.outline, result.characters, result.worldview
            )
            result.metadata.targets_generated.append("plot")
            
            result.success = True
            
        except Exception as e:
            result.success = False
            result.error = str(e)
        
        return result

    def get_creation_options(self) -> Dict[str, Any]:
        """获取快捷创作选项定义

        返回支持的创作配置选项，供UI层使用。

        Returns:
            选项定义字典
        """
        return {
            "targets": {
                QuickCreationTarget.WORLDVIEW.value: "世界观设定 - 世界结构、力量体系、社会背景",
                QuickCreationTarget.OUTLINE.value: "大纲设定 - 章节规划、剧情走向、高潮节点",
                QuickCreationTarget.CHARACTERS.value: "人物设定 - 角色形象、性格特点、人物关系",
                QuickCreationTarget.PLOT.value: "情节设定 - 场景设计、冲突转折、伏笔布局",
                QuickCreationTarget.ALL.value: "全部生成 - 一键生成所有设定"
            },
            "genres": [
                "玄幻", "仙侠", "都市", "言情", "科幻", 
                "历史", "军事", "悬疑", "奇幻", "武侠"
            ],
            "styles": [
                "轻松", "严肃", "热血", "治愈", "暗黑",
                "幽默", "温馨", "刺激", "唯美"
            ],
            "tones": [
                "爽文", "虐文", "喜剧", "悲剧", "正剧",
                "轻小说", "史诗", "日常"
            ],
            "detailed_levels": {
                "brief": "简略 - 核心要素，快速生成",
                "medium": "中等 - 标准详细度，平衡质量与速度",
                "detailed": "详细 - 全面设定，深度刻画"
            },
            "character_count_range": {"min": 1, "max": 10, "default": 3},
            "chapter_count_range": {"min": 1, "max": 100, "default": 10},
            "word_count_per_chapter_range": {"min": 500, "max": 10000, "default": 2000}
        }

    def estimate_creation(
        self, 
        request: QuickCreationRequest
    ) -> Dict[str, Any]:
        """预估创作效果（可选实现）

        在实际生成前，预估创作的大致效果和资源消耗。
        用于UI预览和资源规划。

        Args:
            request: 快捷创作请求参数

        Returns:
            预估信息字典
        """
        # 根据目标计算预估
        target = request.target or QuickCreationTarget.ALL.value
        
        base_tokens = {
            QuickCreationTarget.WORLDVIEW.value: 800,
            QuickCreationTarget.OUTLINE.value: 1500,
            QuickCreationTarget.CHARACTERS.value: 600 * request.character_count,
            QuickCreationTarget.PLOT.value: 1000,
        }
        
        if target == QuickCreationTarget.ALL.value:
            estimated_tokens = sum(base_tokens.values())
        else:
            estimated_tokens = base_tokens.get(target, 1000)
        
        # 考虑详细程度
        detail_multiplier = {
            "brief": 0.6,
            "medium": 1.0,
            "detailed": 1.5
        }
        estimated_tokens = int(
            estimated_tokens * detail_multiplier.get(request.detailed_level, 1.0)
        )
        
        return {
            "estimated_tokens": estimated_tokens,
            "estimated_time": estimated_tokens * 0.05,  # 约20 token/秒
            "targets_to_generate": self._get_targets_for_request(request),
            "suggestions": self._generate_keyword_suggestions(request)
        }

    def _get_targets_for_request(self, request: QuickCreationRequest) -> List[str]:
        """获取请求将要生成的目标列表"""
        target = request.target or QuickCreationTarget.ALL.value
        if target == QuickCreationTarget.ALL.value:
            return [
                QuickCreationTarget.WORLDVIEW.value,
                QuickCreationTarget.OUTLINE.value,
                QuickCreationTarget.CHARACTERS.value,
                QuickCreationTarget.PLOT.value
            ]
        return [target]

    def _generate_keyword_suggestions(self, request: QuickCreationRequest) -> List[str]:
        """生成关键词优化建议"""
        suggestions = []
        keywords = request.keywords
        
        if len(keywords) < 3:
            suggestions.append("建议提供更多关键词以获得更精准的设定")
        if not request.genre:
            suggestions.append("建议指定题材类型以获得更符合类型的设定")
        if not request.style:
            suggestions.append("建议指定写作风格以保持风格一致性")
        
        return suggestions

    # 实现父类ToolPlugin的execute方法
    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具操作（适配ToolPlugin接口）

        Args:
            action: 操作名称（worldview/outline/characters/plot/all）
            params: 操作参数（QuickCreationRequest字段）

        Returns:
            执行结果字典
        """
        # 构建请求
        request = QuickCreationRequest(
            keywords=params.get("keywords", ""),
            target=action,
            reference_text=params.get("reference_text"),
            reference_type=params.get("reference_type"),
            genre=params.get("genre"),
            style=params.get("style"),
            tone=params.get("tone"),
            character_count=params.get("character_count", 3),
            chapter_count=params.get("chapter_count", 10),
            word_count_per_chapter=params.get("word_count_per_chapter", 2000),
            detailed_level=params.get("detailed_level", "medium"),
            include_relationships=params.get("include_relationships", True),
            include_timeline=params.get("include_timeline", True),
            request_id=params.get("request_id")
        )
        
        # 根据action调用对应方法
        if action == QuickCreationTarget.WORLDVIEW.value:
            result = self.generate_worldview(request)
            return {"worldview": result.get_full_text(), "data": result.to_dict() if hasattr(result, 'to_dict') else result.model_dump()}
        
        elif action == QuickCreationTarget.OUTLINE.value:
            result = self.generate_outline(request)
            return {"outline": result.get_full_text(), "data": result.model_dump()}
        
        elif action == QuickCreationTarget.CHARACTERS.value:
            results = self.generate_characters(request)
            return {
                "characters": [r.get_full_text() for r in results],
                "data": [r.model_dump() for r in results]
            }
        
        elif action == QuickCreationTarget.PLOT.value:
            result = self.generate_plot(request)
            return {"plot": result.get_full_text(), "data": result.model_dump()}
        
        elif action == QuickCreationTarget.ALL.value:
            result = self.generate_all(request)
            return {
                "success": result.success,
                "texts": result.get_all_text(),
                "data": result.model_dump()
            }
        
        else:
            return {"error": f"未知操作: {action}"}


class ProtocolPlugin(BasePlugin):
    """协议插件接口

    用于导入导出格式转换。
    """

    @abstractmethod
    def import_data(self, source: str, format: str) -> Dict[str, Any]:
        """导入数据

        Args:
            source: 数据源
            format: 数据格式

        Returns:
            解析后的数据
        """
        pass

    @abstractmethod
    def export_data(self, data: Dict[str, Any], format: str) -> str:
        """导出数据

        Args:
            data: 数据内容
            format: 目标格式

        Returns:
            导出后的数据
        """
        pass


# ============================================================================
# 逆向反馈功能数据模型（V1.4新增）
# ============================================================================


class ConsistencyIssueType(Enum):
    """冲突类型枚举"""

    OUTLINE = "outline"  # 大纲冲突
    CHARACTER = "character"  # 人物设定冲突
    WORLDVIEW = "worldview"  # 世界观冲突


class ConsistencySeverity(Enum):
    """冲突严重程度枚举"""

    LOW = "low"  # 轻微冲突，不影响整体逻辑
    MEDIUM = "medium"  # 中等冲突，需要注意
    HIGH = "high"  # 严重冲突，必须修正


@dataclass
class ConsistencyIssue:
    """章节内容与设定的冲突项

    用于逆向反馈功能，记录检测到的冲突详情。

    Attributes:
        issue_id: 冲突项唯一标识
        issue_type: 冲突类型（outline/character/worldview）
        severity: 严重程度（low/medium/high）
        description: 冲突描述
        suggested_fix: 建议修正方案
        original_content: 原始设定内容
        chapter_reference: 引发冲突的章节ID或标题
        detected_at: 检测时间戳
        element_name: 冲突涉及的元素名称（如角色名、地点名）
        confidence: 检测置信度（0.0-1.0）
    """

    issue_id: str = field(default_factory=lambda: f"issue-{uuid4().hex[:8]}")
    issue_type: ConsistencyIssueType = ConsistencyIssueType.OUTLINE
    severity: ConsistencySeverity = ConsistencySeverity.MEDIUM
    description: str = ""
    suggested_fix: str = ""
    original_content: str = ""
    chapter_reference: str = ""
    detected_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    element_name: str = ""
    confidence: float = 0.8

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type.value,
            "severity": self.severity.value,
            "description": self.description,
            "suggested_fix": self.suggested_fix,
            "original_content": self.original_content,
            "chapter_reference": self.chapter_reference,
            "detected_at": self.detected_at,
            "element_name": self.element_name,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConsistencyIssue":
        """从字典创建"""
        issue_type = data.get("issue_type", "outline")
        if isinstance(issue_type, str):
            issue_type = ConsistencyIssueType(issue_type)

        severity = data.get("severity", "medium")
        if isinstance(severity, str):
            severity = ConsistencySeverity(severity)

        return cls(
            issue_id=data.get("issue_id", f"issue-{uuid4().hex[:8]}"),
            issue_type=issue_type,
            severity=severity,
            description=data.get("description", ""),
            suggested_fix=data.get("suggested_fix", ""),
            original_content=data.get("original_content", ""),
            chapter_reference=data.get("chapter_reference", ""),
            detected_at=data.get("detected_at", datetime.now(timezone.utc).timestamp()),
            element_name=data.get("element_name", ""),
            confidence=data.get("confidence", 0.8),
        )


@dataclass
class ConsistencyReport:
    """一致性分析报告

    包含多个冲突项和分析摘要。

    Attributes:
        report_id: 报告唯一标识
        project_name: 项目名称
        chapters_analyzed: 分析的章节数量
        issues: 冲突项列表
        summary: 分析摘要
        analyzed_at: 分析时间戳
        high_priority_count: 高优先级冲突数量
        medium_priority_count: 中等优先级冲突数量
        low_priority_count: 低优先级冲突数量
    """

    report_id: str = field(default_factory=lambda: f"report-{uuid4().hex[:8]}")
    project_name: str = ""
    chapters_analyzed: int = 0
    issues: List[ConsistencyIssue] = field(default_factory=list)
    summary: str = ""
    analyzed_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    high_priority_count: int = 0
    medium_priority_count: int = 0
    low_priority_count: int = 0

    def add_issue(self, issue: ConsistencyIssue):
        """添加冲突项并更新统计"""
        self.issues.append(issue)
        if issue.severity == ConsistencySeverity.HIGH:
            self.high_priority_count += 1
        elif issue.severity == ConsistencySeverity.MEDIUM:
            self.medium_priority_count += 1
        else:
            self.low_priority_count += 1

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "report_id": self.report_id,
            "project_name": self.project_name,
            "chapters_analyzed": self.chapters_analyzed,
            "issues": [issue.to_dict() for issue in self.issues],
            "summary": self.summary,
            "analyzed_at": self.analyzed_at,
            "high_priority_count": self.high_priority_count,
            "medium_priority_count": self.medium_priority_count,
            "low_priority_count": self.low_priority_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConsistencyReport":
        """从字典创建"""
        report = cls(
            report_id=data.get("report_id", f"report-{uuid4().hex[:8]}"),
            project_name=data.get("project_name", ""),
            chapters_analyzed=data.get("chapters_analyzed", 0),
            summary=data.get("summary", ""),
            analyzed_at=data.get("analyzed_at", datetime.now(timezone.utc).timestamp()),
            high_priority_count=data.get("high_priority_count", 0),
            medium_priority_count=data.get("medium_priority_count", 0),
            low_priority_count=data.get("low_priority_count", 0),
        )
        for issue_data in data.get("issues", []):
            report.issues.append(ConsistencyIssue.from_dict(issue_data))
        return report


class ReverseFeedbackPlugin(AnalyzerPlugin):
    """逆向反馈分析插件接口

    用于分析已生成章节与项目设定（大纲、人物、世界观）的一致性，
    检测冲突并生成修正建议。

    继承自 AnalyzerPlugin，扩展了专门的逆向分析方法。
    """

    @abstractmethod
    def analyze_chapter_vs_settings(
        self,
        chapter_text: str,
        current_settings: Dict[str, Any],
        chapter_id: str = "",
    ) -> ConsistencyReport:
        """分析章节内容与当前设定的冲突

        核心方法：对比章节中提取的信息与项目设定，发现不一致之处。

        Args:
            chapter_text: 章节文本内容
            current_settings: 当前项目设定，应包含：
                - outline: 大纲文本
                - characters: 人物设定列表
                - worldview: 世界观设定文本
            chapter_id: 章节ID或标题（用于引用）

        Returns:
            ConsistencyReport: 包含冲突列表和分析摘要的报告
        """
        pass

    @abstractmethod
    def analyze_project(
        self,
        project_data: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
    ) -> ConsistencyReport:
        """分析整个项目的一致性

        遍历所有章节，检测与设定的冲突。

        Args:
            project_data: 完整项目数据，应包含：
                - project_name: 项目名称
                - chapters: 章节列表（每个包含id, title, content）
                - outline: 大纲文本
                - characters: 人物设定列表
                - worldview: 世界观设定文本
            options: 分析选项（可选）

        Returns:
            ConsistencyReport: 综合分析报告
        """
        pass

    @abstractmethod
    def generate_corrections(
        self,
        report: ConsistencyReport,
        current_settings: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """根据冲突报告生成修正后的设定

        Args:
            report: 一致性分析报告
            current_settings: 当前项目设定
            options: 修正选项（可选），可包含：
                - auto_fix_low: 是否自动修正低优先级冲突
                - preserve_original: 是否保留原始设定作为备份

        Returns:
            包含修正后设定的字典：
            {
                "updated_outline": str,
                "updated_characters": List[Dict],
                "updated_worldview": str,
                "suggestions": List[str],
                "backup": Optional[Dict]  # 原始设定备份
            }
        """
        pass

    def get_supported_formats(self) -> List[str]:
        """支持的输入格式"""
        return ["txt", "md", "json"]

    def get_analysis_types(self) -> List[str]:
        """支持的分析类型"""
        return [
            "consistency_check",
            "conflict_detection",
            "setting_validation",
            "character_consistency",
            "worldview_consistency",
        ]


# ============================================================================
# V5核心模块保护机制
# ============================================================================

# V5核心模块ID列表（不可变更）
# 与架构文档V1.3 第18章 V5强制保护机制一致
V5_PROTECTED_MODULES = frozenset(
    [
        # 四大核心板块
        "outline-parser-v3",  # 大纲解析
        "style-learner-v2",  # 风格学习
        "character-manager",  # 人物管理
        "worldview-parser",  # 世界观解析
        # 评分反馈循环优化生成流程
        "context-builder",  # 上下文构建
        "iterative-generator-v2",  # 迭代生成
        "weighted-validator",  # 加权验证
        "optimized-generator-v2",  # 生成入口
        # 热榜功能
        "hot-ranking",  # 热榜功能
    ]
)


def is_v5_protected_module(plugin_id: str) -> bool:
    """检查是否为V5保护模块

    Args:
        plugin_id: 插件ID

    Returns:
        是否为保护模块
    """
    return plugin_id in V5_PROTECTED_MODULES
