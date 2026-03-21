"""
插件注册表 - 状态管理

V2.1版本（5状态模型优化版）
创建日期：2026-03-21

V2.1修订：
- 状态机升级为5状态模型（UNLOADED/LOADED/ACTIVE/ERROR/UNLOADING）
- 枚举值统一为小写（与PluginInfo.state默认值一致）
- 状态机转换注释完善

V1.3新增：
- V5核心模块保护机制（运行时检查）
- 禁止卸载/禁用/覆盖保护模块

特性：
- 线程安全（RLock）
- 状态机验证
- 插槽绑定
- V5保护模块运行时检查
"""

import threading
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from .models import PluginMetadata as PydanticPluginMetadata, PluginInfo

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


class PluginProtectionError(Exception):
    """插件保护异常 - 尝试操作受保护模块时抛出"""

    pass


class PluginState(str, Enum):
    """
    插件状态枚举 - 与plugin_interface.py保持一致

    V2.1修订：5状态模型（与架构文档V1.3一致）
    - UNLOADED: 插件未加载（初始状态）
    - LOADED: 插件已加载（初始化完成），但未激活
    - ACTIVE: 插件已激活，可执行
    - ERROR: 插件处于错误状态，需要重置
    - UNLOADING: 插件正在卸载中

    状态转换规则：
    - UNLOADED → LOADED: register()成功
    - LOADED → ACTIVE: activate()成功
    - ACTIVE → LOADED: deactivate()成功
    - LOADED/ACTIVE → ERROR: initialize/execute异常
    - ERROR → LOADED: recover()成功
    - LOADED/ACTIVE → UNLOADING: 卸载请求
    - UNLOADING → UNLOADED: shutdown+cleanup完成
    """

    UNLOADED = "unloaded"  # 未加载（初始状态）
    LOADED = "loaded"  # 已加载
    ACTIVE = "active"  # 已激活
    ERROR = "error"  # 错误状态
    UNLOADING = "unloading"  # 卸载中


class PluginType(str, Enum):
    """插件类型枚举"""

    PROTOCOL = "PROTOCOL"
    AI = "AI"
    STORAGE = "STORAGE"
    ANALYZER = "ANALYZER"
    GENERATOR = "GENERATOR"
    VALIDATOR = "VALIDATOR"
    TOOL = "TOOL"


class PluginRegistry:
    """
    插件注册表 - 管理插件注册、状态转换、插槽绑定

    V2.0修订（与plugin_interface.py PluginState对齐）：
    - 新增UNLOADED状态（插件未加载/初始状态）
    - register()方法：插件注册时进入LOADED状态（从UNLOADED转换）
    - unregister()方法：设置UNLOADING状态后从注册表移除（变为UNLOADED）
    - load()方法：调整状态转换逻辑，支持ERROR状态重置
    - 状态机：完整5状态模型（UNLOADED→LOADED→ACTIVE→UNLOADING→UNLOADED）
    """

    # 允许的状态转换（V2.1修订：5状态模型）
    # 与plugin_interface.py PluginState保持一致
    # 状态转换规则详见PluginState枚举注释
    _ALLOWED_TRANSITIONS: Dict[PluginState, Set[PluginState]] = {
        PluginState.UNLOADED: {PluginState.LOADED},  # 加载：插件注册成功
        PluginState.LOADED: {
            PluginState.ACTIVE,
            PluginState.ERROR,
            PluginState.UNLOADING,
        },  # 激活/错误/卸载
        PluginState.ACTIVE: {
            PluginState.LOADED,
            PluginState.ERROR,
            PluginState.UNLOADING,
        },  # 停用/错误/卸载
        PluginState.ERROR: {
            PluginState.LOADED,
            PluginState.UNLOADING,
        },  # 可恢复到LOADED或卸载
        PluginState.UNLOADING: set(),  # 终态：从注册表移除后变为UNLOADED
    }

    def __init__(self):
        """初始化插件注册表"""
        self._plugins: Dict[str, PluginInfo] = {}
        self._slots: Dict[str, Optional[str]] = {}  # slot_id -> plugin_id
        self._lock = threading.RLock()
        self._observers: List[Callable[[str, str, str], None]] = []  # 状态变更观察者

    def register(
        self,
        plugin_id: str,
        metadata: Union[PydanticPluginMetadata, Any],  # 支持Pydantic和dataclass两种类型
        instance: Optional[Any] = None,
    ) -> bool:
        """
        注册插件（V1.1修正：直接进入LOADED状态）

        V1.4修正：支持两种PluginMetadata类型
        - Pydantic版本（models.PydananticPluginMetadata）
        - dataclass版本（plugin_interface.PluginMetadata）

        Args:
            plugin_id: 插件ID
            metadata: 插件元数据（支持Pydantic或dataclass版本）
            instance: 插件实例

        Returns:
            是否注册成功
        """
        with self._lock:
            if plugin_id in self._plugins:
                return False

            # V1.4新增：处理不同类型的metadata
            if isinstance(metadata, PydanticPluginMetadata):
                # 已经是Pydantic版本，直接使用
                pydantic_metadata = metadata
            elif hasattr(metadata, "to_dict"):
                # dataclass版本，转换为Pydantic
                data = metadata.to_dict()
                pydantic_metadata = PydanticPluginMetadata(**data)
            elif isinstance(metadata, dict):
                # 字典类型，直接创建
                pydantic_metadata = PydanticPluginMetadata(**metadata)
            else:
                # 尝试从对象属性创建
                try:
                    pydantic_metadata = PydanticPluginMetadata(
                        id=getattr(metadata, "id", plugin_id),
                        name=getattr(metadata, "name", plugin_id),
                        version=getattr(metadata, "version", "1.0.0"),
                        description=getattr(metadata, "description", ""),
                        author=getattr(metadata, "author", ""),
                        plugin_type=getattr(metadata, "plugin_type", "tool"),
                        api_version=getattr(metadata, "api_version", "1.0"),
                        priority=getattr(metadata, "priority", 100),
                        enabled=getattr(metadata, "enabled", True),
                        dependencies=getattr(metadata, "dependencies", []),
                        conflicts=getattr(metadata, "conflicts", []),
                        permissions=getattr(metadata, "permissions", []),
                        min_platform_version=getattr(
                            metadata, "min_platform_version", "6.0.0"
                        ),
                        entry_class=getattr(metadata, "entry_class", ""),
                    )
                except Exception:
                    return False

            plugin_info = PluginInfo(
                metadata=pydantic_metadata,
                state=PluginState.LOADED.value,  # V1.1修正：直接进入LOADED状态
                instance=instance,
                load_time=datetime.now(),
                load_count=1,
                error_count=0,
            )

            self._plugins[plugin_id] = plugin_info
            self._notify_observers(plugin_id, None, PluginState.LOADED.value)
            return True

    def unregister(self, plugin_id: str) -> bool:
        """
        注销插件（V1.3增强：V5保护模块检查）

        Args:
            plugin_id: 插件ID

        Returns:
            是否注销成功

        Raises:
            PluginProtectionError: 尝试卸载保护模块时抛出
        """
        # V1.3新增：V5保护模块检查
        if plugin_id in V5_PROTECTED_MODULES:
            raise PluginProtectionError(f"禁止卸载V5保护模块: {plugin_id}")

        with self._lock:
            if plugin_id not in self._plugins:
                return False

            plugin_info = self._plugins[plugin_id]
            old_state = plugin_info.state

            # 设置UNLOADING状态
            if not self._validate_transition(old_state, PluginState.UNLOADING.value):
                return False

            plugin_info.state = PluginState.UNLOADING.value
            self._notify_observers(plugin_id, old_state, PluginState.UNLOADING.value)

            # 从注册表移除
            del self._plugins[plugin_id]

            # 清理插槽绑定
            for slot_id, bound_plugin_id in list(self._slots.items()):
                if bound_plugin_id == plugin_id:
                    self._slots[slot_id] = None

            return True

    def load(self, plugin_id: str, instance: Optional[Any] = None) -> bool:
        """
        加载插件（V1.1修正：支持ERROR状态重置）

        Args:
            plugin_id: 插件ID
            instance: 插件实例

        Returns:
            是否加载成功
        """
        with self._lock:
            if plugin_id not in self._plugins:
                return False

            plugin_info = self._plugins[plugin_id]
            old_state = plugin_info.state

            # V1.1修正：支持ERROR→LOADED恢复
            if old_state == PluginState.ERROR.value:
                plugin_info.state = PluginState.LOADED.value
                plugin_info.error_message = None
                plugin_info.error_count = 0
                self._notify_observers(plugin_id, old_state, PluginState.LOADED.value)
                return True

            if not self._validate_transition(old_state, PluginState.LOADED.value):
                return False

            plugin_info.state = PluginState.LOADED.value
            plugin_info.instance = instance
            plugin_info.load_count += 1
            self._notify_observers(plugin_id, old_state, PluginState.LOADED.value)
            return True

    def activate(self, plugin_id: str) -> bool:
        """
        激活插件

        Args:
            plugin_id: 插件ID

        Returns:
            是否激活成功
        """
        with self._lock:
            if plugin_id not in self._plugins:
                return False

            plugin_info = self._plugins[plugin_id]
            old_state = plugin_info.state

            if not self._validate_transition(old_state, PluginState.ACTIVE.value):
                return False

            plugin_info.state = PluginState.ACTIVE.value
            self._notify_observers(plugin_id, old_state, PluginState.ACTIVE.value)
            return True

    def deactivate(self, plugin_id: str) -> bool:
        """
        停用插件

        Args:
            plugin_id: 插件ID

        Returns:
            是否停用成功
        """
        with self._lock:
            if plugin_id not in self._plugins:
                return False

            plugin_info = self._plugins[plugin_id]
            old_state = plugin_info.state

            if not self._validate_transition(old_state, PluginState.LOADED.value):
                return False

            plugin_info.state = PluginState.LOADED.value
            self._notify_observers(plugin_id, old_state, PluginState.LOADED.value)
            return True

    def set_error(self, plugin_id: str, error: str) -> bool:
        """
        设置插件错误状态

        Args:
            plugin_id: 插件ID
            error: 错误信息

        Returns:
            是否设置成功
        """
        with self._lock:
            if plugin_id not in self._plugins:
                return False

            plugin_info = self._plugins[plugin_id]
            old_state = plugin_info.state

            if not self._validate_transition(old_state, PluginState.ERROR.value):
                return False

            plugin_info.state = PluginState.ERROR.value
            plugin_info.error_message = error
            plugin_info.error_count += 1
            self._notify_observers(plugin_id, old_state, PluginState.ERROR.value)
            return True

    def reset_error(self, plugin_id: str) -> bool:
        """
        重置插件错误状态（V1.1新增）

        Args:
            plugin_id: 插件ID

        Returns:
            是否重置成功
        """
        with self._lock:
            if plugin_id not in self._plugins:
                return False

            plugin_info = self._plugins[plugin_id]

            if plugin_info.state != PluginState.ERROR.value:
                return False

            plugin_info.state = PluginState.LOADED.value
            plugin_info.error_message = None
            self._notify_observers(
                plugin_id, PluginState.ERROR.value, PluginState.LOADED.value
            )
            return True

    def get_plugin(self, plugin_id: str) -> Optional[Any]:
        """
        获取插件实例

        Args:
            plugin_id: 插件ID

        Returns:
            插件实例（不存在或未激活返回None）
        """
        with self._lock:
            plugin_info = self._plugins.get(plugin_id)
            if plugin_info and plugin_info.state == PluginState.ACTIVE.value:
                return plugin_info.instance
        return None

    def get_plugin_info(self, plugin_id: str) -> Optional[PluginInfo]:
        """
        获取插件信息

        Args:
            plugin_id: 插件ID

        Returns:
            插件信息对象
        """
        with self._lock:
            return self._plugins.get(plugin_id)

    def get_state(self, plugin_id: str) -> Optional[str]:
        """
        获取插件状态

        Args:
            plugin_id: 插件ID

        Returns:
            插件状态
        """
        with self._lock:
            plugin_info = self._plugins.get(plugin_id)
            return plugin_info.state if plugin_info else None

    def get_plugins_by_type(self, plugin_type: PluginType) -> List[Any]:
        """
        获取指定类型的所有插件实例

        Args:
            plugin_type: 插件类型

        Returns:
            插件实例列表
        """
        with self._lock:
            return [
                info.instance
                for info in self._plugins.values()
                if info.metadata.plugin_type == plugin_type.value
                and info.state == PluginState.ACTIVE.value
            ]

    def get_active_plugins(self) -> List[Any]:
        """
        获取所有激活状态的插件实例

        Returns:
            插件实例列表
        """
        with self._lock:
            return [
                info.instance
                for info in self._plugins.values()
                if info.state == PluginState.ACTIVE.value
            ]

    def bind_slot(self, slot_id: str, plugin_id: str) -> bool:
        """
        绑定插件到插槽

        Args:
            slot_id: 插槽ID
            plugin_id: 插件ID

        Returns:
            是否绑定成功
        """
        with self._lock:
            if plugin_id not in self._plugins:
                return False

            plugin_info = self._plugins[plugin_id]
            if plugin_info.state != PluginState.ACTIVE.value:
                return False

            # 解绑旧插件
            if slot_id in self._slots and self._slots[slot_id]:
                old_plugin_id = self._slots[slot_id]
                if old_plugin_id in self._plugins:
                    self._plugins[old_plugin_id].slot = None

            # 绑定新插件
            self._slots[slot_id] = plugin_id
            plugin_info.slot = slot_id
            return True

    def get_slot_plugin(self, slot_id: str) -> Optional[Any]:
        """
        获取插槽绑定的插件实例

        Args:
            slot_id: 插槽ID

        Returns:
            插件实例
        """
        with self._lock:
            plugin_id = self._slots.get(slot_id)
            if plugin_id:
                return self.get_plugin(plugin_id)
        return None

    def add_observer(self, observer: Callable[[str, str, str], None]) -> None:
        """
        添加状态变更观察者

        Args:
            observer: 观察者函数 (plugin_id, old_state, new_state) -> None
        """
        with self._lock:
            self._observers.append(observer)

    def _validate_transition(self, from_state: str, to_state: str) -> bool:
        """
        验证状态转换是否合法（V1.1补充）

        Args:
            from_state: 当前状态
            to_state: 目标状态

        Returns:
            是否合法转换
        """
        try:
            from_enum = PluginState(from_state)
            to_enum = PluginState(to_state)
            return to_enum in self._ALLOWED_TRANSITIONS.get(from_enum, set())
        except ValueError:
            return False

    def _notify_observers(
        self, plugin_id: str, old_state: Optional[str], new_state: str
    ) -> None:
        """
        通知观察者状态变更

        Args:
            plugin_id: 插件ID
            old_state: 旧状态
            new_state: 新状态
        """
        for observer in self._observers:
            try:
                observer(plugin_id, old_state, new_state)
            except Exception:
                pass  # 观察者异常不影响主流程

    # ========================================================================
    # V5保护模块相关方法（V1.3新增）
    # ========================================================================

    def is_protected(self, plugin_id: str) -> bool:
        """
        检查插件是否为V5保护模块

        Args:
            plugin_id: 插件ID

        Returns:
            是否为保护模块
        """
        return plugin_id in V5_PROTECTED_MODULES

    def get_protected_modules(self) -> List[str]:
        """
        获取所有V5保护模块ID列表

        Returns:
            保护模块ID列表
        """
        return list(V5_PROTECTED_MODULES)

    def disable(self, plugin_id: str) -> bool:
        """
        禁用插件（V1.3新增：V5保护模块检查）

        Args:
            plugin_id: 插件ID

        Returns:
            是否禁用成功

        Raises:
            PluginProtectionError: 尝试禁用保护模块时抛出
        """
        # V1.3新增：V5保护模块检查
        if plugin_id in V5_PROTECTED_MODULES:
            raise PluginProtectionError(f"禁止禁用V5保护模块: {plugin_id}")

        return self.deactivate(plugin_id)

    # ========================================================================
    # 运行时加载/卸载接口（V2.0新增：集成PluginLoader）
    # ========================================================================

    def load_plugin_runtime(
        self, plugin_id: str, loader: Optional[Any] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        运行时加载插件

        Args:
            plugin_id: 插件ID
            loader: 插件加载器实例（可选）

        Returns:
            (是否成功, 错误信息)
        """
        from .plugin_loader import get_plugin_loader

        _loader = loader or get_plugin_loader()
        result = _loader.load_plugin(plugin_id)

        if result.success:
            return True, None
        return False, result.error

    def unload_plugin_runtime(
        self, plugin_id: str, loader: Optional[Any] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        运行时卸载插件

        Args:
            plugin_id: 插件ID
            loader: 插件加载器实例（可选）

        Returns:
            (是否成功, 错误信息)
        """
        from .plugin_loader import get_plugin_loader

        # V5保护模块检查
        if plugin_id in V5_PROTECTED_MODULES:
            return False, f"禁止卸载V5保护模块: {plugin_id}"

        _loader = loader or get_plugin_loader()
        success = _loader.unload_plugin(plugin_id)

        if success:
            return True, None
        return False, "卸载失败"

    def reload_plugin_runtime(
        self, plugin_id: str, loader: Optional[Any] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        运行时重载插件

        Args:
            plugin_id: 插件ID
            loader: 插件加载器实例（可选）

        Returns:
            (是否成功, 错误信息)
        """
        from .plugin_loader import get_plugin_loader

        # V5保护模块检查
        if plugin_id in V5_PROTECTED_MODULES:
            return False, f"禁止重载V5保护模块: {plugin_id}"

        _loader = loader or get_plugin_loader()
        result = _loader.reload_plugin(plugin_id)

        if result.success:
            return True, None
        return False, result.error


# 全局单例
_registry_instance: Optional[PluginRegistry] = None
_registry_lock = threading.Lock()


def get_plugin_registry() -> PluginRegistry:
    """获取全局PluginRegistry实例"""
    global _registry_instance
    if _registry_instance is None:
        with _registry_lock:
            if _registry_instance is None:
                _registry_instance = PluginRegistry()
    return _registry_instance
