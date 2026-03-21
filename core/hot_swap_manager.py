"""
热插拔管理器 - 文件监控 + 防抖 + 状态管理

V1.0版本
创建日期：2026-03-21

特性：
- watchdog文件系统监控
- 防抖机制（避免频繁重载）
- 状态管理（加载/卸载/重载状态跟踪）
- 安全权限控制（L0-L3分级）
- 事件发布（热插拔事件）
"""

import hashlib
import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set

# P2-2: watchdog依赖检测和优雅降级
_WATCHDOG_AVAILABLE = False
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    _WATCHDOG_AVAILABLE = True
except ImportError:
    Observer = None
    FileSystemEventHandler = None

if TYPE_CHECKING:
    from .event_bus import EventBus
    from .plugin_loader import PluginLoader
    from .plugin_registry import PluginRegistry

# P2-3: 统一使用结构化日志器
try:
    from infrastructure.logger import get_logger
    logger = get_logger("core.hot_swap_manager")
except ImportError:
    logger = logging.getLogger(__name__)


class HotSwapAction(Enum):
    """热插拔操作类型"""

    LOAD = "load"
    UNLOAD = "unload"
    RELOAD = "reload"


class HotSwapState(Enum):
    """热插拔状态"""

    IDLE = "idle"  # 空闲
    PENDING = "pending"  # 待处理（防抖中）
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


@dataclass
class HotSwapEvent:
    """热插拔事件"""

    plugin_id: str
    action: HotSwapAction
    state: HotSwapState
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None
    retry_count: int = 0
    file_path: Optional[str] = None


@dataclass
class PluginStateInfo:
    """插件状态信息"""

    plugin_id: str
    state: HotSwapState = HotSwapState.IDLE
    last_action: Optional[HotSwapAction] = None
    last_success: Optional[datetime] = None
    last_error: Optional[str] = None
    error_count: int = 0
    reload_count: int = 0
    debounce_timer: Optional[threading.Timer] = None
    pending_files: Set[str] = field(default_factory=set)


class HotSwapPermission:
    """
    热插拔权限控制

    安全分级策略：
    - L0-信任：官方插件，完全信任（可热重载/卸载）
    - L1-受限：第三方签名插件（可热重载，不可卸载）
    - L2-隔离：未知来源插件（禁止热重载和卸载）
    - L3-禁止：风险插件（禁止加载）

    V5核心模块：无论签名如何，均禁止热重载和卸载
    """

    SECURITY_LEVELS = {
        "L0": {
            "can_reload": True,
            "can_load": True,
            "can_unload": True,
            "process_isolation": False,
        },
        "L1": {
            "can_reload": True,
            "can_load": True,
            "can_unload": False,
            "process_isolation": False,
        },
        "L2": {
            "can_reload": False,
            "can_load": True,
            "can_unload": False,
            "process_isolation": True,
        },
        "L3": {
            "can_reload": False,
            "can_load": False,
            "can_unload": False,
            "process_isolation": False,
        },
    }

    # 官方插件白名单
    OFFICIAL_PLUGINS = {
        "novel-generator",
        "novel-analyzer",
        "novel-validator",
        "style-learner",
        "character-manager",
        "worldview-parser",
    }

    # V5核心保护模块（禁止热插拔）
    V5_PROTECTED_MODULES = frozenset(
        [
            "outline-parser-v3",
            "style-learner-v2",
            "character-manager",
            "worldview-parser",
            "context-builder",
            "iterative-generator-v2",
            "weighted-validator",
            "optimized-generator-v2",
            "hot-ranking",
        ]
    )

    def __init__(
        self,
        plugin_id: str,
        signature_verified: bool = False,
        is_official: bool = False,
    ):
        """
        初始化权限控制

        Args:
            plugin_id: 插件ID
            signature_verified: 签名是否验证通过
            is_official: 是否为官方插件
        """
        self.plugin_id = plugin_id
        self._security_level = self._determine_level(
            plugin_id, signature_verified, is_official or self.is_official_plugin()
        )

    def is_official_plugin(self) -> bool:
        """判断是否为官方插件"""
        return self.plugin_id in self.OFFICIAL_PLUGINS

    def is_v5_protected(self) -> bool:
        """判断是否为V5保护模块"""
        return self.plugin_id in self.V5_PROTECTED_MODULES

    def _determine_level(
        self, plugin_id: str, signature_verified: bool, is_official: bool = False
    ) -> str:
        """
        确定插件安全等级

        Args:
            plugin_id: 插件ID
            signature_verified: 签名是否验证通过
            is_official: 是否为官方插件

        Returns:
            安全等级：L0/L1/L2/L3
        """
        # V5保护模块禁止热插拔
        if plugin_id in self.V5_PROTECTED_MODULES:
            return "L2"  # 允许加载，但禁止热重载和卸载

        # 未签名插件禁止加载
        if not signature_verified:
            return "L3"

        # 官方插件获得最高信任级别
        if is_official:
            return "L0"

        # 第三方签名插件为受限级别
        return "L1"

    def can_reload(self) -> bool:
        """是否允许热重载"""
        return self.SECURITY_LEVELS[self._security_level]["can_reload"]

    def can_load(self) -> bool:
        """是否允许加载"""
        return self.SECURITY_LEVELS[self._security_level]["can_load"]

    def can_unload(self) -> bool:
        """是否允许卸载"""
        return self.SECURITY_LEVELS[self._security_level]["can_unload"]

    def requires_isolation(self) -> bool:
        """是否需要进程隔离"""
        return self.SECURITY_LEVELS[self._security_level]["process_isolation"]

    @property
    def security_level(self) -> str:
        """获取安全等级"""
        return self._security_level


class HotSwapManager:
    """
    热插拔管理器

    功能：
    1. 文件系统监控（watchdog）
    2. 防抖机制（可配置延迟）
    3. 状态管理（插件热插拔状态跟踪）
    4. 事件发布（热插拔开始/完成/失败）
    5. 重试机制（失败自动重试）
    """

    DEFAULT_DEBOUNCE_DELAY = 1.0  # 默认防抖延迟（秒）
    MAX_RETRY_COUNT = 3  # 最大重试次数
    RETRY_DELAY = 2.0  # 重试延迟（秒）

    def __init__(
        self,
        plugin_loader: "PluginLoader",
        event_bus: Optional["EventBus"] = None,
        registry: Optional["PluginRegistry"] = None,
        debounce_delay: float = DEFAULT_DEBOUNCE_DELAY,
        max_retry: int = MAX_RETRY_COUNT,
    ):
        """
        初始化热插拔管理器

        Args:
            plugin_loader: 插件加载器实例
            event_bus: 事件总线实例
            registry: 插件注册表实例
            debounce_delay: 防抖延迟（秒）
            max_retry: 最大重试次数
        """
        self._plugin_loader = plugin_loader
        self._event_bus = event_bus
        self._registry = registry
        self._debounce_delay = debounce_delay
        self._max_retry = max_retry

        # 状态管理
        self._plugin_states: Dict[str, PluginStateInfo] = {}
        self._lock = threading.RLock()

        # 事件监听器
        self._listeners: List[Callable[[HotSwapEvent], None]] = []

        # watchdog观察者
        self._observer: Optional[Any] = None
        self._watch_paths: Set[str] = set()
        self._enabled = False

        # 统计信息
        self._stats = defaultdict(int)

    def start_watch(self, plugin_directories: List[str]) -> bool:
        """
        启动文件监控

        Args:
            plugin_directories: 插件目录列表

        Returns:
            是否启动成功
        """
        if self._enabled:
            logger.warning("Hot swap watch already started")
            return True

        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent

            class PluginFileHandler(FileSystemEventHandler):
                def __init__(self, manager: "HotSwapManager"):
                    self.manager = manager

                def on_modified(self, event):
                    if event.is_directory:
                        return
                    self.manager._handle_file_change(
                        event.src_path, "modified"
                    )

                def on_created(self, event):
                    if event.is_directory:
                        return
                    self.manager._handle_file_change(
                        event.src_path, "created"
                    )

                def on_deleted(self, event):
                    if event.is_directory:
                        return
                    self.manager._handle_file_change(
                        event.src_path, "deleted"
                    )

            self._observer = Observer()
            handler = PluginFileHandler(self)

            for directory in plugin_directories:
                dir_path = Path(directory)
                if dir_path.exists() and dir_path.is_dir():
                    self._observer.schedule(handler, str(dir_path), recursive=True)
                    self._watch_paths.add(str(dir_path))

            self._observer.start()
            self._enabled = True

            logger.info(
                f"Hot swap watch started, monitoring {len(self._watch_paths)} directories"
            )
            return True

        except ImportError:
            logger.warning("watchdog not installed, hot swap disabled")
            return False
        except Exception as e:
            logger.error(f"Failed to start hot swap watch: {e}")
            return False

    def stop_watch(self) -> None:
        """停止文件监控"""
        if not self._enabled or not self._observer:
            return

        # 取消所有待处理的防抖定时器
        with self._lock:
            for state_info in self._plugin_states.values():
                if state_info.debounce_timer:
                    state_info.debounce_timer.cancel()
                    state_info.debounce_timer = None

        self._observer.stop()
        self._observer.join(timeout=5.0)
        self._observer = None
        self._enabled = False
        self._watch_paths.clear()

        logger.info("Hot swap watch stopped")

    def is_enabled(self) -> bool:
        """检查热插拔是否启用"""
        return self._enabled

    def _handle_file_change(self, file_path: str, change_type: str) -> None:
        """
        处理文件变更（防抖）

        Args:
            file_path: 变更文件路径
            change_type: 变更类型（modified/created/deleted）
        """
        # 提取插件ID
        plugin_id = self._extract_plugin_id(file_path)
        if not plugin_id:
            return

        # 检查是否为Python文件或插件配置文件
        path = Path(file_path)
        if path.suffix not in (".py", ".json", ".yaml", ".yml"):
            return

        # 检查权限
        permission = HotSwapPermission(
            plugin_id=plugin_id,
            signature_verified=True,  # TODO: 实际签名验证
            is_official=plugin_id in HotSwapPermission.OFFICIAL_PLUGINS,
        )

        if not permission.can_reload():
            logger.debug(f"Plugin {plugin_id} hot reload not allowed (security level: {permission.security_level})")
            return

        # 更新状态
        with self._lock:
            if plugin_id not in self._plugin_states:
                self._plugin_states[plugin_id] = PluginStateInfo(plugin_id=plugin_id)

            state_info = self._plugin_states[plugin_id]

            # 记录待处理文件
            state_info.pending_files.add(file_path)

            # 取消之前的防抖定时器
            if state_info.debounce_timer:
                state_info.debounce_timer.cancel()

            # 设置状态为待处理
            state_info.state = HotSwapState.PENDING

            # 设置新的防抖定时器
            timer = threading.Timer(
                self._debounce_delay,
                self._execute_hot_swap,
                args=(plugin_id, change_type),
            )
            state_info.debounce_timer = timer
            timer.start()

            logger.debug(
                f"File change detected for {plugin_id}: {file_path} ({change_type}), debounce scheduled"
            )

    def _execute_hot_swap(self, plugin_id: str, change_type: str) -> None:
        """
        执行热插拔操作

        Args:
            plugin_id: 插件ID
            change_type: 变更类型
        """
        with self._lock:
            if plugin_id not in self._plugin_states:
                return

            state_info = self._plugin_states[plugin_id]
            state_info.debounce_timer = None
            state_info.state = HotSwapState.PROCESSING

            # 清空待处理文件
            state_info.pending_files.clear()

        # 发布事件
        event = HotSwapEvent(
            plugin_id=plugin_id,
            action=HotSwapAction.RELOAD,
            state=HotSwapState.PROCESSING,
        )
        self._notify_listeners(event)

        # 执行重载
        try:
            result = self._plugin_loader.reload_plugin(plugin_id)

            if result.success:
                with self._lock:
                    state_info.state = HotSwapState.COMPLETED
                    state_info.last_action = HotSwapAction.RELOAD
                    state_info.last_success = datetime.now()
                    state_info.reload_count += 1
                    state_info.error_count = 0

                event = HotSwapEvent(
                    plugin_id=plugin_id,
                    action=HotSwapAction.RELOAD,
                    state=HotSwapState.COMPLETED,
                )
                self._stats["reload_success"] += 1

                logger.info(f"Plugin {plugin_id} reloaded successfully")

            else:
                raise Exception(result.error or "Unknown error")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to reload plugin {plugin_id}: {error_msg}")

            with self._lock:
                state_info.state = HotSwapState.FAILED
                state_info.last_error = error_msg
                state_info.error_count += 1

                # 检查是否需要重试
                if state_info.error_count < self._max_retry:
                    # 延迟重试
                    timer = threading.Timer(
                        self.RETRY_DELAY,
                        self._retry_hot_swap,
                        args=(plugin_id, state_info.error_count),
                    )
                    state_info.debounce_timer = timer
                    timer.start()
                    logger.info(
                        f"Retry scheduled for {plugin_id} (attempt {state_info.error_count + 1}/{self._max_retry})"
                    )
                else:
                    logger.error(
                        f"Max retry count reached for {plugin_id}, giving up"
                    )

            event = HotSwapEvent(
                plugin_id=plugin_id,
                action=HotSwapAction.RELOAD,
                state=HotSwapState.FAILED,
                error=error_msg,
                retry_count=state_info.error_count,
            )
            self._stats["reload_failed"] += 1

        self._notify_listeners(event)

    def _retry_hot_swap(self, plugin_id: str, retry_count: int) -> None:
        """
        重试热插拔

        Args:
            plugin_id: 插件ID
            retry_count: 当前重试次数
        """
        with self._lock:
            if plugin_id not in self._plugin_states:
                return

            state_info = self._plugin_states[plugin_id]
            state_info.debounce_timer = None

        logger.info(f"Retrying hot swap for {plugin_id} (attempt {retry_count + 1})")
        self._execute_hot_swap(plugin_id, "retry")

    def _extract_plugin_id(self, file_path: str) -> Optional[str]:
        """
        从文件路径提取插件ID

        Args:
            file_path: 文件路径

        Returns:
            插件ID
        """
        path = Path(file_path)

        # 查找plugins目录
        parts = path.parts
        if "plugins" in parts:
            idx = parts.index("plugins")
            if idx + 1 < len(parts):
                return parts[idx + 1]

        return None

    def _notify_listeners(self, event: HotSwapEvent) -> None:
        """
        通知监听器

        Args:
            event: 热插拔事件
        """
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Hot swap listener error: {e}")

        # 发布到EventBus
        if self._event_bus:
            try:
                self._event_bus.publish(
                    f"plugin.hot_swap.{event.state.value}",
                    {
                        "plugin_id": event.plugin_id,
                        "action": event.action.value,
                        "state": event.state.value,
                        "error": event.error,
                        "retry_count": event.retry_count,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to publish hot swap event: {e}")

    def add_listener(self, listener: Callable[[HotSwapEvent], None]) -> None:
        """
        添加热插拔事件监听器

        Args:
            listener: 监听器函数
        """
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[HotSwapEvent], None]) -> None:
        """
        移除热插拔事件监听器

        Args:
            listener: 监听器函数
        """
        if listener in self._listeners:
            self._listeners.remove(listener)

    def get_plugin_state(self, plugin_id: str) -> Optional[HotSwapState]:
        """
        获取插件热插拔状态

        Args:
            plugin_id: 插件ID

        Returns:
            热插拔状态
        """
        with self._lock:
            if plugin_id in self._plugin_states:
                return self._plugin_states[plugin_id].state
        return None

    def get_state_info(self, plugin_id: str) -> Optional[PluginStateInfo]:
        """
        获取插件状态信息

        Args:
            plugin_id: 插件ID

        Returns:
            状态信息
        """
        with self._lock:
            return self._plugin_states.get(plugin_id)

    def get_all_states(self) -> Dict[str, PluginStateInfo]:
        """
        获取所有插件状态

        Returns:
            插件状态字典
        """
        with self._lock:
            return dict(self._plugin_states)

    def get_stats(self) -> Dict[str, int]:
        """
        获取统计信息

        Returns:
            统计字典
        """
        return dict(self._stats)

    def force_reload(self, plugin_id: str) -> bool:
        """
        强制重载插件（跳过防抖）

        Args:
            plugin_id: 插件ID

        Returns:
            是否成功
        """
        # 检查权限
        permission = HotSwapPermission(
            plugin_id=plugin_id,
            signature_verified=True,
            is_official=plugin_id in HotSwapPermission.OFFICIAL_PLUGINS,
        )

        if not permission.can_reload():
            logger.warning(f"Force reload denied for {plugin_id} (security level: {permission.security_level})")
            return False

        # 取消防抖定时器
        with self._lock:
            if plugin_id in self._plugin_states:
                state_info = self._plugin_states[plugin_id]
                if state_info.debounce_timer:
                    state_info.debounce_timer.cancel()
                    state_info.debounce_timer = None

        # 直接执行重载
        self._execute_hot_swap(plugin_id, "force")

        # 检查结果
        with self._lock:
            if plugin_id in self._plugin_states:
                return self._plugin_states[plugin_id].state == HotSwapState.COMPLETED
        return False

    def cancel_pending(self, plugin_id: str) -> bool:
        """
        取消待处理的热插拔操作

        Args:
            plugin_id: 插件ID

        Returns:
            是否成功取消
        """
        with self._lock:
            if plugin_id not in self._plugin_states:
                return False

            state_info = self._plugin_states[plugin_id]
            if state_info.debounce_timer:
                state_info.debounce_timer.cancel()
                state_info.debounce_timer = None
                state_info.state = HotSwapState.IDLE
                state_info.pending_files.clear()
                return True

        return False


# 全局单例
_hot_swap_manager: Optional[HotSwapManager] = None
_hot_swap_lock = threading.Lock()


def get_hot_swap_manager() -> HotSwapManager:
    """获取全局HotSwapManager实例"""
    global _hot_swap_manager
    if _hot_swap_manager is None:
        with _hot_swap_lock:
            if _hot_swap_manager is None:
                from .plugin_loader import get_plugin_loader

                _hot_swap_manager = HotSwapManager(plugin_loader=get_plugin_loader())
    return _hot_swap_manager
