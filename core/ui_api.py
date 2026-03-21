"""
UI层交互API规范

V1.2版本（最终修订版）
创建日期：2026-03-21

特性：
- CoreServiceManager统一入口
- ServiceProxy分层代理
- Tkinter线程安全保证
"""

import threading
from typing import Any, Callable, Dict, List, Optional

from .config_manager import ConfigManager, get_config_manager
from .event_bus import EventBus, get_event_bus
from .models import GenerationRequest, GenerationResult
from .plugin_loader import PluginLoader, get_plugin_loader
from .plugin_registry import PluginRegistry, get_plugin_registry
from .service_locator import ServiceLocator, get_service_locator


class GenerationServiceProxy:
    """
    生成服务代理
    
    为UI层提供生成相关的操作接口
    """
    
    def __init__(self, tk_root: Any):
        """
        初始化生成服务代理
        
        Args:
            tk_root: Tkinter根窗口
        """
        self._root = tk_root
        self._event_bus: Optional[EventBus] = None
        self._progress_callback: Optional[Callable] = None
        self._completion_callback: Optional[Callable] = None
    
    def set_progress_callback(
        self,
        callback: Callable[[int, str], None]
    ) -> None:
        """
        设置进度回调
        
        Args:
            callback: 回调函数 (progress: int, message: str) -> None
        """
        self._progress_callback = callback
    
    def set_completion_callback(
        self,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        设置完成回调
        
        Args:
            callback: 回调函数 (result: Dict) -> None
        """
        self._completion_callback = callback
    
    def generate_chapter(
        self,
        title: str,
        outline: str,
        word_count: int = 2000,
        max_iterations: int = 5
    ) -> Dict[str, Any]:
        """
        生成章节
        
        Args:
            title: 章节标题
            outline: 章节大纲
            word_count: 目标字数
            max_iterations: 最大迭代次数
        
        Returns:
            {"request_id": str, "status": str}
        """
        import uuid
        
        request_id = uuid.uuid4().hex
        
        # 创建生成请求
        request = GenerationRequest(
            request_id=request_id,
            title=title,
            outline=outline,
            word_count=word_count,
            max_iterations=max_iterations
        )
        
        # 发布生成请求事件
        if self._event_bus:
            self._event_bus.publish("generation.requested", {
                "request": request.model_dump()
            })
        
        return {
            "request_id": request_id,
            "status": "pending"
        }
    
    def cancel_generation(self, request_id: str) -> bool:
        """
        取消生成
        
        Args:
            request_id: 请求ID
        
        Returns:
            是否取消成功
        """
        if self._event_bus:
            self._event_bus.publish("generation.cancelled", {
                "request_id": request_id
            })
        return True
    
    def _on_progress(self, event: Any) -> None:
        """
        处理进度事件（线程安全）
        
        Args:
            event: 事件对象
        """
        if not self._progress_callback:
            return
        
        # 线程安全：调度到主线程
        def update():
            self._progress_callback(
                event.data.get("progress", 0),
                event.data.get("message", "")
            )
        
        self._root.after(0, update)
    
    def _on_complete(self, event: Any) -> None:
        """
        处理完成事件（线程安全）
        
        Args:
            event: 事件对象
        """
        if not self._completion_callback:
            return
        
        # 线程安全：调度到主线程
        def update():
            self._completion_callback(event.data)
        
        self._root.after(0, update)


class PluginServiceProxy:
    """
    插件服务代理
    
    为UI层提供插件管理操作接口
    """
    
    def __init__(self, tk_root: Any):
        """
        初始化插件服务代理
        
        Args:
            tk_root: Tkinter根窗口
        """
        self._root = tk_root
        self._registry: Optional[PluginRegistry] = None
        self._loader: Optional[PluginLoader] = None
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """
        列出所有插件
        
        Returns:
            插件信息列表
        """
        if not self._registry:
            return []
        
        # TODO: 实现插件列表获取
        return []
    
    def get_plugin(self, plugin_id: str) -> Optional[Any]:
        """
        获取插件实例
        
        Args:
            plugin_id: 插件ID
        
        Returns:
            插件实例
        """
        if self._registry:
            return self._registry.get_plugin(plugin_id)
        return None
    
    def activate_plugin(self, plugin_id: str) -> bool:
        """
        激活插件
        
        Args:
            plugin_id: 插件ID
        
        Returns:
            是否激活成功
        """
        if self._registry:
            return self._registry.activate(plugin_id)
        return False
    
    def deactivate_plugin(self, plugin_id: str) -> bool:
        """
        停用插件
        
        Args:
            plugin_id: 插件ID
        
        Returns:
            是否停用成功
        """
        if self._registry:
            return self._registry.deactivate(plugin_id)
        return False
    
    def reload_plugin(self, plugin_id: str) -> bool:
        """
        重载插件
        
        Args:
            plugin_id: 插件ID
        
        Returns:
            是否重载成功
        """
        if self._loader:
            result = self._loader.reload_plugin(plugin_id)
            return result.success
        return False


class ConfigServiceProxy:
    """
    配置服务代理
    
    为UI层提供配置管理操作接口
    """
    
    def __init__(self, tk_root: Any):
        """
        初始化配置服务代理
        
        Args:
            tk_root: Tkinter根窗口
        """
        self._root = tk_root
        self._config: Optional[ConfigManager] = None
    
    def get(
        self,
        key: str,
        default: Any = None
    ) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键
            default: 默认值
        
        Returns:
            配置值
        """
        if self._config:
            return self._config.get(key, default)
        return default
    
    def set(
        self,
        key: str,
        value: Any
    ) -> bool:
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 配置值
        
        Returns:
            是否设置成功
        """
        if self._config:
            try:
                self._config.set(key, value)
                return True
            except Exception:
                return False
        return False
    
    def get_all(self) -> Dict[str, Any]:
        """
        获取全部配置
        
        Returns:
            配置字典
        """
        if self._config:
            return self._config.get_all()
        return {}
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """
        列出配置键
        
        Args:
            prefix: 键前缀
        
        Returns:
            键列表
        """
        if self._config:
            return self._config.list_keys(prefix)
        return []
    
    def get_history(
        self,
        key: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取配置历史
        
        Args:
            key: 配置键
            limit: 最大返回数量
        
        Returns:
            历史记录列表
        """
        if self._config:
            return self._config.get_history(key, limit)
        return []


class EventServiceProxy:
    """
    事件服务代理
    
    为UI层提供事件订阅操作接口
    """
    
    def __init__(self, tk_root: Any):
        """
        初始化事件服务代理
        
        Args:
            tk_root: Tkinter根窗口
        """
        self._root = tk_root
        self._event_bus: Optional[EventBus] = None
    
    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Any], None],
        handler_id: Optional[str] = None
    ) -> str:
        """
        订阅事件
        
        Args:
            event_type: 事件类型
            handler: 处理函数
            handler_id: 处理器ID
        
        Returns:
            订阅ID
        """
        if not self._event_bus:
            return ""
        
        # 包装处理器：确保线程安全
        def safe_handler(event: Any):
            # 调度到主线程执行
            self._root.after(0, lambda: handler(event))
        
        return self._event_bus.subscribe(
            event_type,
            safe_handler,
            handler_id
        )
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        取消订阅
        
        Args:
            subscription_id: 订阅ID
        
        Returns:
            是否取消成功
        """
        if self._event_bus:
            return self._event_bus.unsubscribe(subscription_id)
        return False
    
    def publish(
        self,
        event_type: str,
        data: Any = None,
        source: Optional[str] = None
    ) -> None:
        """
        发布事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
            source: 事件来源
        """
        if self._event_bus:
            self._event_bus.publish(event_type, data, source)
    
    def get_handler_count(self, event_type: str) -> int:
        """
        获取事件处理器数量
        
        Args:
            event_type: 事件类型
        
        Returns:
            处理器数量
        """
        if self._event_bus:
            return self._event_bus.get_handler_count(event_type)
        return 0


class CoreServiceManager:
    """
    核心服务管理器
    
    为UI层提供统一的、安全的服务访问接口
    
    使用示例：
    ```python
    # gui_main.py
    class MainWindow:
        def __init__(self):
            self.root = tk.Tk()
            self._init_core_services()
        
        def _init_core_services(self):
            self.services = CoreServiceManager(self.root)
            self.services.initialize(
                get_event_bus(),
                get_plugin_registry(),
                get_service_locator(),
                get_config_manager()
            )
        
        def _on_generate_clicked(self):
            result = self.services.generation.generate_chapter(
                title="第一章",
                outline="主角出场...",
                word_count=2000
            )
    ```
    """
    
    def __init__(self, tk_root: Any):
        """
        初始化核心服务管理器
        
        Args:
            tk_root: Tkinter根窗口
        """
        self._root = tk_root
        self._initialized = False
        
        # 服务代理
        self._generation: Optional[GenerationServiceProxy] = None
        self._plugins: Optional[PluginServiceProxy] = None
        self._config: Optional[ConfigServiceProxy] = None
        self._events: Optional[EventServiceProxy] = None
        
        # 核心服务实例
        self._event_bus: Optional[EventBus] = None
        self._registry: Optional[PluginRegistry] = None
        self._locator: Optional[ServiceLocator] = None
        self._config_manager: Optional[ConfigManager] = None
    
    @property
    def generation(self) -> GenerationServiceProxy:
        """获取生成服务代理"""
        if not self._generation:
            self._generation = GenerationServiceProxy(self._root)
        return self._generation
    
    @property
    def plugins(self) -> PluginServiceProxy:
        """获取插件服务代理"""
        if not self._plugins:
            self._plugins = PluginServiceProxy(self._root)
        return self._plugins
    
    @property
    def config(self) -> ConfigServiceProxy:
        """获取配置服务代理"""
        if not self._config:
            self._config = ConfigServiceProxy(self._root)
        return self._config
    
    @property
    def events(self) -> EventServiceProxy:
        """获取事件服务代理"""
        if not self._events:
            self._events = EventServiceProxy(self._root)
        return self._events
    
    def initialize(
        self,
        event_bus: EventBus,
        registry: PluginRegistry,
        locator: ServiceLocator,
        config: ConfigManager
    ) -> None:
        """
        初始化核心服务
        
        Args:
            event_bus: 事件总线
            registry: 插件注册表
            locator: 服务定位器
            config: 配置管理器
        """
        if self._initialized:
            return
        
        self._event_bus = event_bus
        self._registry = registry
        self._locator = locator
        self._config_manager = config
        
        # 设置服务代理
        self._generation = GenerationServiceProxy(self._root)
        self._generation._event_bus = event_bus
        
        self._plugins = PluginServiceProxy(self._root)
        self._plugins._registry = registry
        self._plugins._loader = get_plugin_loader()
        
        self._config = ConfigServiceProxy(self._root)
        self._config._config = config
        
        self._events = EventServiceProxy(self._root)
        self._events._event_bus = event_bus
        
        # 订阅生成事件
        event_bus.subscribe("generation.progress", self._generation._on_progress)
        event_bus.subscribe("generation.completed", self._generation._on_complete)
        
        self._initialized = True
    
    def shutdown(self) -> None:
        """关闭核心服务"""
        if not self._initialized:
            return
        
        # 关闭事件总线
        if self._event_bus:
            self._event_bus.shutdown()
        
        # 释放服务资源
        if self._locator:
            self._locator.dispose_all()
        
        self._initialized = False
