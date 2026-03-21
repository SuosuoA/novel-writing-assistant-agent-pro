"""
优化启动器 - 主启动流程管理

V1.0版本
创建日期：2026-03-21

特性：
- 隐藏窗口启动
- 异步加载模块
- 加载完成后显示窗口
- 启动时间优化（<1秒）
"""

import threading
import time
import logging
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass

from .launcher import LazyLoader, LoadPriority

logger = logging.getLogger(__name__)


@dataclass
class StartupConfig:
    """启动配置"""
    show_splash: bool = False           # 是否显示启动画面
    min_show_time: float = 0.0          # 最小显示时间（秒）
    async_load: bool = True             # 是否异步加载
    hide_window_on_start: bool = True   # 启动时隐藏窗口
    target_startup_time: float = 1.0    # 目标启动时间（秒）


class OptimizedLauncher:
    """优化启动器"""
    
    _instance: Optional['OptimizedLauncher'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'OptimizedLauncher':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._lazy_loader = LazyLoader()
        self._config = StartupConfig()
        self._startup_time = 0.0
        self._is_started = False
        self._start_callbacks: List[Callable[[], None]] = []
        self._complete_callbacks: List[Callable[[float], None]] = []
        self._root_window: Optional[Any] = None
        self._initialized = True
        logger.info("OptimizedLauncher initialized")
    
    def configure(self, **kwargs) -> None:
        """
        配置启动参数
        
        Args:
            **kwargs: StartupConfig的字段
        """
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
                logger.debug(f"Startup config: {key} = {value}")
    
    def register_module(
        self,
        name: str,
        loader: Callable[[], Any],
        priority: LoadPriority = LoadPriority.CORE,
        dependencies: Optional[List[str]] = None
    ) -> None:
        """
        注册模块
        
        Args:
            name: 模块名称
            loader: 加载函数
            priority: 加载优先级
            dependencies: 依赖模块列表
        """
        self._lazy_loader.register(name, loader, priority, dependencies)
    
    def register_start_callback(self, callback: Callable[[], None]) -> None:
        """
        注册启动开始回调
        
        Args:
            callback: 回调函数
        """
        self._start_callbacks.append(callback)
    
    def register_complete_callback(self, callback: Callable[[float], None]) -> None:
        """
        注册启动完成回调
        
        Args:
            callback: 回调函数，参数为启动时间
        """
        self._complete_callbacks.append(callback)
    
    def _init_core_modules(self) -> None:
        """初始化核心模块"""
        # 配置管理器
        def load_config():
            from .config_manager import get_config_manager
            return get_config_manager()
        
        self.register_module(
            "config_manager",
            load_config,
            LoadPriority.CORE,
            []
        )
        
        # 日志系统
        def load_logger():
            from infrastructure.logger import get_logger
            return get_logger("NovelAssistant")
        
        self.register_module(
            "logger",
            load_logger,
            LoadPriority.CORE,
            []
        )
        
        # 事件总线
        def load_event_bus():
            from .event_bus import get_event_bus
            return get_event_bus()
        
        self.register_module(
            "event_bus",
            load_event_bus,
            LoadPriority.CORE,
            ["config_manager"]
        )
        
        # 服务定位器
        def load_service_locator():
            from .service_locator import get_service_locator
            return get_service_locator()
        
        self.register_module(
            "service_locator",
            load_service_locator,
            LoadPriority.CORE,
            ["config_manager", "event_bus"]
        )
    
    def _init_plugin_modules(self) -> None:
        """初始化插件层模块"""
        # 插件注册表
        def load_plugin_registry():
            from .plugin_registry import get_plugin_registry
            return get_plugin_registry()
        
        self.register_module(
            "plugin_registry",
            load_plugin_registry,
            LoadPriority.PLUGIN,
            ["service_locator", "event_bus"]
        )
        
        # 插件加载器
        def load_plugin_loader():
            from .plugin_loader import get_plugin_loader
            return get_plugin_loader()
        
        self.register_module(
            "plugin_loader",
            load_plugin_loader,
            LoadPriority.PLUGIN,
            ["plugin_registry", "config_manager"]
        )
    
    def _init_agent_modules(self) -> None:
        """初始化Agent层模块"""
        # MasterAgent（延迟到有event_bus时加载）
        def load_master_agent():
            from .event_bus import get_event_bus
            from agents.master_agent import MasterAgent
            event_bus = get_event_bus()
            return MasterAgent(event_bus)
        
        self.register_module(
            "master_agent",
            load_master_agent,
            LoadPriority.AGENT,
            ["event_bus"]
        )
        
        # 异步处理器
        def load_async_handler():
            from .async_handler import get_async_handler
            return get_async_handler()
        
        self.register_module(
            "async_handler",
            load_async_handler,
            LoadPriority.AGENT,
            ["event_bus"]
        )
    
    def _init_ui_modules(self) -> None:
        """初始化UI层模块"""
        # UI API（延迟到有root_window时加载）
        def load_ui_api():
            from .ui_api import CoreServiceManager
            # 返回管理器实例，不需要tk_root
            return CoreServiceManager.__new__(CoreServiceManager)
        
        self.register_module(
            "ui_api",
            load_ui_api,
            LoadPriority.UI,
            ["service_locator", "event_bus"]
        )
        
        # 数据库
        def load_database():
            from .database import get_database
            return get_database()
        
        self.register_module(
            "database",
            load_database,
            LoadPriority.UI,
            ["config_manager"]
        )
    
    def _register_all_modules(self) -> None:
        """注册所有模块"""
        self._init_core_modules()
        self._init_plugin_modules()
        self._init_agent_modules()
        self._init_ui_modules()
        logger.info(f"Registered {len(self._lazy_loader._modules)} modules")
    
    def start(
        self,
        root_window: Optional[Any] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> float:
        """
        启动应用
        
        Args:
            root_window: Tk根窗口（用于异步调度）
            on_progress: 进度回调
            
        Returns:
            启动时间（秒）
        """
        if self._is_started:
            logger.warning("Application already started")
            return self._startup_time
        
        self._is_started = True
        self._root_window = root_window
        start_time = time.time()
        
        # 调用启动回调
        for callback in self._start_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Start callback error: {e}")
        
        # 注册所有模块
        self._register_all_modules()
        
        # 加载核心层（同步，确保基础功能可用）
        logger.info("Loading CORE layer...")
        core_results = self._lazy_loader.load_up_to(LoadPriority.CORE)
        core_success = all(core_results.values())
        
        if not core_success:
            logger.error("Failed to load core modules")
            failed = [k for k, v in core_results.items() if not v]
            raise RuntimeError(f"Core modules failed to load: {failed}")
        
        # 异步加载其他层
        if self._config.async_load:
            logger.info("Loading remaining layers asynchronously...")
            
            def on_async_complete(results: Dict[str, bool]):
                self._startup_time = time.time() - start_time
                logger.info(f"Async load complete in {self._startup_time:.3f}s")
                
                # 调用完成回调
                for callback in self._complete_callbacks:
                    try:
                        callback(self._startup_time)
                    except Exception as e:
                        logger.error(f"Complete callback error: {e}")
            
            def async_load_module(name: str, success: bool):
                logger.debug(f"Module '{name}' loaded: {success}")
            
            self._lazy_loader.load_async(
                on_complete=on_async_complete,
                load_callback=async_load_module,
                progress_callback=on_progress
            )
        else:
            # 同步加载
            logger.info("Loading all layers synchronously...")
            results = self._lazy_loader.load_all(progress_callback=on_progress)
            self._startup_time = time.time() - start_time
            
            # 调用完成回调
            for callback in self._complete_callbacks:
                try:
                    callback(self._startup_time)
                except Exception as e:
                    logger.error(f"Complete callback error: {e}")
        
        # 核心层加载完成后的启动时间
        core_startup_time = time.time() - start_time
        logger.info(f"Core startup in {core_startup_time:.3f}s")
        
        return core_startup_time
    
    def show_window(self) -> None:
        """显示主窗口"""
        if self._root_window:
            # 使用 after 确保在主线程中执行
            try:
                self._root_window.deiconify()
                logger.info("Window shown")
            except Exception as e:
                logger.error(f"Failed to show window: {e}")
    
    def hide_window(self) -> None:
        """隐藏主窗口"""
        if self._root_window:
            try:
                self._root_window.withdraw()
                logger.info("Window hidden")
            except Exception as e:
                logger.error(f"Failed to hide window: {e}")
    
    def get_startup_time(self) -> float:
        """获取启动时间"""
        return self._startup_time
    
    def get_stats(self) -> Dict[str, Any]:
        """获取启动统计信息"""
        return self._lazy_loader.get_load_stats()
    
    def is_started(self) -> bool:
        """是否已启动"""
        return self._is_started
    
    def get_module(self, name: str) -> Optional[Any]:
        """
        获取已加载的模块实例
        
        Args:
            name: 模块名称
            
        Returns:
            模块实例或None
        """
        return self._lazy_loader.get_module(name)
    
    def shutdown(self) -> None:
        """关闭启动器"""
        self._lazy_loader.shutdown()
        logger.info("OptimizedLauncher shutdown")


def get_optimized_launcher() -> OptimizedLauncher:
    """获取OptimizedLauncher单例"""
    return OptimizedLauncher()
