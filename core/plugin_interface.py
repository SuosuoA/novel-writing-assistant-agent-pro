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

from .models import GenerationRequest, GenerationResult, ValidationScores

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

    @abstractmethod
    def initialize(self, context: PluginContext) -> bool:
        """初始化插件

        Args:
            context: 插件上下文（包含EventBus、ConfigManager等）

        Returns:
            是否初始化成功
        """
        self._context = context
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
