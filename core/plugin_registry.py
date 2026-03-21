"""
插件注册表 - 状态管理

V1.2版本（最终修订版）
创建日期：2026-03-21

V1.1修正：
- 状态机从6状态改为4状态模型（LOADED/ACTIVE/ERROR/UNLOADING）
- 移除DISCOVERED和UNLOADED状态
- 补充ERROR状态恢复路径

特性：
- 线程安全（RLock）
- 状态机验证
- 插槽绑定
"""

import threading
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from .models import PluginMetadata, PluginInfo


class PluginState(str, Enum):
    """
    插件状态枚举
    
    V1.1修正：4状态模型
    - LOADED: 插件已加载（初始化完成），但未激活
    - ACTIVE: 插件已激活，可执行
    - ERROR: 插件处于错误状态，需要重置
    - UNLOADING: 插件正在卸载中
    
    移除的状态：
    - DISCOVERED: 由PluginLoader单独管理
    - UNLOADED: 等同于"不存在于Registry中"
    """
    LOADED = "LOADED"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"
    UNLOADING = "UNLOADING"


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
    
    V1.1修正：
    - register()方法：插件注册时直接进入LOADED状态
    - unregister()方法：设置UNLOADING状态后从注册表移除
    - load()方法：调整状态转换逻辑，支持ERROR状态重置
    - 状态机：补充ERROR→LOADED恢复路径
    """
    
    # 允许的状态转换（V1.1修正）
    _ALLOWED_TRANSITIONS: Dict[PluginState, Set[PluginState]] = {
        PluginState.LOADED: {PluginState.ACTIVE, PluginState.ERROR, PluginState.UNLOADING},
        PluginState.ACTIVE: {PluginState.LOADED, PluginState.UNLOADING},
        PluginState.ERROR: {PluginState.LOADED, PluginState.UNLOADING},  # V1.1新增：ERROR可恢复
        PluginState.UNLOADING: set(),  # UNLOADING是终态，从注册表移除
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
        metadata: PluginMetadata,
        instance: Optional[Any] = None
    ) -> bool:
        """
        注册插件（V1.1修正：直接进入LOADED状态）
        
        Args:
            plugin_id: 插件ID
            metadata: 插件元数据
            instance: 插件实例
        
        Returns:
            是否注册成功
        """
        with self._lock:
            if plugin_id in self._plugins:
                return False
            
            plugin_info = PluginInfo(
                metadata=metadata,
                state=PluginState.LOADED.value,  # V1.1修正：直接进入LOADED状态
                instance=instance,
                load_time=datetime.now(),
                load_count=1,
                error_count=0
            )
            
            self._plugins[plugin_id] = plugin_info
            self._notify_observers(plugin_id, None, PluginState.LOADED.value)
            return True
    
    def unregister(self, plugin_id: str) -> bool:
        """
        注销插件（V1.1修正：设置UNLOADING状态后移除）
        
        Args:
            plugin_id: 插件ID
        
        Returns:
            是否注销成功
        """
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
    
    def load(
        self,
        plugin_id: str,
        instance: Optional[Any] = None
    ) -> bool:
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
            self._notify_observers(plugin_id, PluginState.ERROR.value, PluginState.LOADED.value)
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
        self,
        plugin_id: str,
        old_state: Optional[str],
        new_state: str
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
