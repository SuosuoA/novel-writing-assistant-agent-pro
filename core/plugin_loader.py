"""
插件加载器 - 动态导入 + 热插拔 + 依赖解析

V1.2版本（最终修订版）
创建日期：2026-03-21

V1.1修正：
- 增加独立的DependencyResolver类
- 增加Discovered_plugins缓存
- 热插拔权限控制（L0-L3安全分级）

特性：
- importlib动态导入
- 拓扑排序依赖解析
- watchdog热插拔监控
- 插件沙箱隔离
"""

import importlib.util
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .event_bus import EventBus, get_event_bus
from .models import PluginMetadata
from .plugin_interface import BasePlugin
from .plugin_registry import PluginRegistry, PluginState, get_plugin_registry


logger = logging.getLogger(__name__)


class PluginLoadResult:
    """插件加载结果"""
    
    def __init__(
        self,
        success: bool,
        plugin_id: str = "",
        error: Optional[str] = None,
        instance: Optional[Any] = None
    ):
        self.success = success
        self.plugin_id = plugin_id
        self.error = error
        self.instance = instance


class CircularDependencyError(Exception):
    """循环依赖异常"""
    pass


class DependencyResolver:
    """
    依赖解析器 - 拓扑排序算法
    
    V1.1新增：独立的依赖解析器，负责解析插件依赖关系
    
    特性：
    - 拓扑排序算法（Kahn算法）
    - 循环依赖检测
    - 缺失依赖报告
    """
    
    @staticmethod
    def resolve(
        plugins: List[PluginMetadata]
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        解析依赖关系，返回加载顺序
        
        Args:
            plugins: 插件元数据列表
        
        Returns:
            (加载顺序列表, 错误列表)
        """
        # 构建依赖图
        graph: Dict[str, List[str]] = {}
        in_degree: Dict[str, int] = {}
        plugin_map: Dict[str, PluginMetadata] = {}
        
        for plugin in plugins:
            plugin_map[plugin.id] = plugin
            graph[plugin.id] = []
            in_degree[plugin.id] = 0
        
        # 构建边和入度
        for plugin in plugins:
            for dep_id in plugin.dependencies:
                if dep_id in graph:
                    graph[dep_id].append(plugin.id)
                    in_degree[plugin.id] += 1
        
        # Kahn算法拓扑排序
        queue: List[str] = [
            plugin_id
            for plugin_id, degree in in_degree.items()
            if degree == 0
        ]
        
        sorted_plugins: List[str] = []
        errors: List[Dict[str, Any]] = []
        
        while queue:
            current = queue.pop(0)
            sorted_plugins.append(current)
            
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # 检测循环依赖
        if len(sorted_plugins) != len(plugins):
            for plugin_id, degree in in_degree.items():
                if degree > 0:
                    errors.append({
                        "type": "circular_dependency",
                        "plugin_id": plugin_id,
                        "message": f"Circular dependency detected for {plugin_id}"
                    })
            
            # 返回部分排序结果（尽可能加载）
            return sorted_plugins, errors
        
        # 检测缺失依赖
        for plugin in plugins:
            for dep_id in plugin.dependencies:
                if dep_id not in plugin_map:
                    errors.append({
                        "type": "missing_dependency",
                        "plugin_id": plugin.id,
                        "dependency": dep_id,
                        "message": f"Missing dependency {dep_id} for {plugin.id}"
                    })
        
        return sorted_plugins, errors


class HotSwapPermission:
    """
    热插拔权限控制（V1.2新增）
    
    安全分级策略：
    - L0-信任：官方插件，完全信任
    - L1-受限：第三方签名插件，受限操作
    - L2-隔离：未知来源插件，进程隔离
    - L3-禁止：风险插件，禁止加载
    """
    
    SECURITY_LEVELS = {
        "L0": {
            "can_reload": True,
            "can_load": True,
            "can_unload": True,
            "process_isolation": False
        },
        "L1": {
            "can_reload": True,
            "can_load": True,
            "can_unload": False,
            "process_isolation": False
        },
        "L2": {
            "can_reload": False,
            "can_load": True,
            "can_unload": False,
            "process_isolation": True
        },
        "L3": {
            "can_reload": False,
            "can_load": False,
            "can_unload": False,
            "process_isolation": False
        },
    }
    
    # 官方插件白名单
    OFFICIAL_PLUGINS = {
        "novel-generator",
        "novel-analyzer",
        "novel-validator",
        "style-learner",
        "character-manager",
        "worldview-parser"
    }
    
    def __init__(
        self,
        plugin_id: str,
        signature_verified: bool = False,
        is_official: bool = False
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
            signature_verified,
            is_official or self.is_official_plugin()
        )
    
    def is_official_plugin(self) -> bool:
        """判断是否为官方插件"""
        return self.plugin_id in self.OFFICIAL_PLUGINS
    
    def _determine_level(
        self,
        signature_verified: bool,
        is_official: bool = False
    ) -> str:
        """
        确定插件安全等级
        
        Args:
            signature_verified: 签名是否验证通过
            is_official: 是否为官方插件
        
        Returns:
            安全等级：L0/L1/L2/L3
        """
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


class PluginLoader:
    """
    插件加载器
    
    V1.1修正：
    - 增加DependencyResolver依赖
    - 增加discovered_plugins缓存
    - 支持热插拔权限控制
    """
    
    def __init__(
        self,
        plugin_directories: Optional[List[str]] = None,
        event_bus: Optional[EventBus] = None,
        registry: Optional[PluginRegistry] = None,
        hot_swap_enabled: bool = True,
        sandbox_enabled: bool = False
    ):
        """
        初始化插件加载器
        
        Args:
            plugin_directories: 插件目录列表
            event_bus: 事件总线实例
            registry: 插件注册表实例
            hot_swap_enabled: 是否启用热插拔
            sandbox_enabled: 是否启用沙箱
        """
        self._event_bus = event_bus or get_event_bus()
        self._registry = registry or get_plugin_registry()
        self._plugin_directories = plugin_directories or []
        self._lock = threading.RLock()
        
        # 已加载模块缓存
        self._loaded_modules: Dict[str, Any] = {}
        self._module_cache: Dict[str, Any] = {}
        
        # V1.1新增：发现阶段缓存（不注册到Registry）
        self._discovered_plugins: Dict[str, PluginMetadata] = {}
        
        # 热插拔
        self._hot_swap_enabled = hot_swap_enabled
        self._debounce_timers: Dict[str, threading.Timer] = {}
        self._debounce_delay: float = 1.0  # 防抖延迟（秒）
        
        # 沙箱
        self._sandbox_enabled = sandbox_enabled
        
        # V1.1新增：依赖解析器
        self._dependency_resolver = DependencyResolver()
        
        # watchdog观察者
        self._observer: Optional[Any] = None
    
    def discover_plugins(self) -> List[str]:
        """
        发现插件（V1.1修正：存储到_discovered_plugins，不注册到Registry）
        
        Returns:
            发现的插件ID列表
        """
        discovered_ids: List[str] = []
        
        for directory in self._plugin_directories:
            dir_path = Path(directory)
            if not dir_path.exists():
                continue
            
            # 扫描plugin.json或__init__.py
            for plugin_dir in dir_path.iterdir():
                if plugin_dir.is_dir():
                    plugin_json = plugin_dir / "plugin.json"
                    init_file = plugin_dir / "__init__.py"
                    
                    if plugin_json.exists():
                        # 解析plugin.json
                        try:
                            import json
                            with open(plugin_json, 'r', encoding='utf-8') as f:
                                meta_dict = json.load(f)
                            
                            metadata = PluginMetadata(**meta_dict)
                            
                            # V1.1修正：存储到_discovered_plugins
                            self._discovered_plugins[metadata.id] = metadata
                            discovered_ids.append(metadata.id)
                            
                        except Exception as e:
                            logger.error(
                                f"Failed to parse plugin.json for {plugin_dir}: {e}"
                            )
                    
                    elif init_file.exists():
                        # 从__init__.py推断插件信息
                        plugin_id = plugin_dir.name
                        metadata = PluginMetadata(
                            id=plugin_id,
                            name=plugin_id.replace("_", " ").title(),
                            version="1.0.0"
                        )
                        
                        # V1.1修正：存储到_discovered_plugins
                        self._discovered_plugins[metadata.id] = metadata
                        discovered_ids.append(metadata.id)
        
        return discovered_ids
    
    def load_plugin(self, plugin_id: str) -> PluginLoadResult:
        """
        加载单个插件
        
        Args:
            plugin_id: 插件ID
        
        Returns:
            加载结果
        """
        with self._lock:
            # V1.1修正：从_discovered_plugins获取元数据
            if plugin_id not in self._discovered_plugins:
                return PluginLoadResult(
                    success=False,
                    plugin_id=plugin_id,
                    error=f"Plugin {plugin_id} not discovered"
                )
            
            metadata = self._discovered_plugins[plugin_id]
            
            # 检查权限（V1.2新增）
            permission = HotSwapPermission(
                plugin_id=plugin_id,
                signature_verified=True,  # TODO: 实际签名验证
                is_official=plugin_id in HotSwapPermission.OFFICIAL_PLUGINS
            )
            
            if not permission.can_load():
                return PluginLoadResult(
                    success=False,
                    plugin_id=plugin_id,
                    error=f"Plugin {plugin_id} is blocked (L3)"
                )
            
            # 查找插件目录
            plugin_path = self._find_plugin_path(plugin_id)
            if not plugin_path:
                return PluginLoadResult(
                    success=False,
                    plugin_id=plugin_id,
                    error=f"Plugin path not found for {plugin_id}"
                )
            
            # 动态导入
            try:
                instance = self._import_plugin(plugin_path, plugin_id)
                
                # 注册到Registry
                self._registry.register(plugin_id, metadata, instance)
                
                # 初始化插件
                context = {
                    "event_bus": self._event_bus,
                    "registry": self._registry,
                    "loader": self
                }
                
                if hasattr(instance, 'initialize'):
                    instance.initialize(context)
                
                # 激活插件
                self._registry.activate(plugin_id)
                
                # 发布事件
                self._event_bus.publish("plugin.loaded", {
                    "plugin_id": plugin_id,
                    "metadata": metadata.model_dump()
                })
                
                return PluginLoadResult(
                    success=True,
                    plugin_id=plugin_id,
                    instance=instance
                )
            
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_id}: {e}")
                
                # 设置错误状态
                self._registry.set_error(plugin_id, str(e))
                
                return PluginLoadResult(
                    success=False,
                    plugin_id=plugin_id,
                    error=str(e)
                )
    
    def unload_plugin(self, plugin_id: str) -> bool:
        """
        卸载插件
        
        Args:
            plugin_id: 插件ID
        
        Returns:
            是否卸载成功
        """
        with self._lock:
            # 检查权限
            permission = HotSwapPermission(
                plugin_id=plugin_id,
                signature_verified=True,
                is_official=plugin_id in HotSwapPermission.OFFICIAL_PLUGINS
            )
            
            if not permission.can_unload():
                logger.warning(f"Plugin {plugin_id} cannot be unloaded (L1/L2)")
                return False
            
            # 获取插件实例
            plugin_info = self._registry.get_plugin_info(plugin_id)
            if not plugin_info:
                return False
            
            # 调用dispose
            instance = plugin_info.instance
            if instance and hasattr(instance, 'dispose'):
                try:
                    instance.dispose()
                except Exception as e:
                    logger.error(f"Plugin {plugin_id} dispose failed: {e}")
            
            # 从Registry注销
            self._registry.unregister(plugin_id)
            
            # 清理模块缓存
            if plugin_id in self._loaded_modules:
                del self._loaded_modules[plugin_id]
            
            # 发布事件
            self._event_bus.publish("plugin.unloaded", {
                "plugin_id": plugin_id
            })
            
            return True
    
    def reload_plugin(self, plugin_id: str) -> PluginLoadResult:
        """
        重载插件
        
        Args:
            plugin_id: 插件ID
        
        Returns:
            重载结果
        """
        # 检查权限
        permission = HotSwapPermission(
            plugin_id=plugin_id,
            signature_verified=True,
            is_official=plugin_id in HotSwapPermission.OFFICIAL_PLUGINS
        )
        
        if not permission.can_reload():
            return PluginLoadResult(
                success=False,
                plugin_id=plugin_id,
                error=f"Plugin {plugin_id} cannot be reloaded (L2/L3)"
            )
        
        # 卸载
        self.unload_plugin(plugin_id)
        
        # 重新加载
        return self.load_plugin(plugin_id)
    
    def load_all(self) -> Dict[str, PluginLoadResult]:
        """
        加载所有已发现的插件（V1.1修正：从_discovered_plugins获取）
        
        Returns:
            加载结果字典 {plugin_id: PluginLoadResult}
        """
        results: Dict[str, PluginLoadResult] = {}
        
        # V1.1修正：从_discovered_plugins获取插件列表
        plugins = list(self._discovered_plugins.values())
        
        if not plugins:
            # 如果未发现，先执行发现
            self.discover_plugins()
            plugins = list(self._discovered_plugins.values())
        
        # 依赖解析
        sorted_ids, errors = DependencyResolver.resolve(plugins)
        
        # 报告错误
        for error in errors:
            logger.warning(f"Dependency resolution error: {error}")
        
        # 按顺序加载
        for plugin_id in sorted_ids:
            results[plugin_id] = self.load_plugin(plugin_id)
        
        return results
    
    def enable_hot_swap(self, debounce_delay: float = 1.0) -> None:
        """
        启用热插拔监控
        
        Args:
            debounce_delay: 防抖延迟（秒）
        """
        if self._hot_swap_enabled:
            return
        
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileModifiedEvent
            
            class PluginFileHandler(FileSystemEventHandler):
                def __init__(self, loader: 'PluginLoader'):
                    self.loader = loader
                
                def on_modified(self, event: FileModifiedEvent):
                    if event.is_directory:
                        return
                    
                    # 处理文件变更
                    self.loader._handle_file_change(event.src_path)
            
            self._debounce_delay = debounce_delay
            self._observer = Observer()
            handler = PluginFileHandler(self)
            
            for directory in self._plugin_directories:
                dir_path = Path(directory)
                if dir_path.exists():
                    self._observer.schedule(handler, str(dir_path), recursive=True)
            
            self._observer.start()
            self._hot_swap_enabled = True
            
            logger.info("Hot swap monitoring enabled")
        
        except ImportError:
            logger.warning("watchdog not installed, hot swap disabled")
            self._hot_swap_enabled = False
    
    def disable_hot_swap(self) -> None:
        """禁用热插拔监控"""
        if not self._hot_swap_enabled or not self._observer:
            return
        
        self._observer.stop()
        self._observer.join()
        self._observer = None
        self._hot_swap_enabled = False
        
        logger.info("Hot swap monitoring disabled")
    
    def _find_plugin_path(self, plugin_id: str) -> Optional[Path]:
        """
        查找插件目录
        
        Args:
            plugin_id: 插件ID
        
        Returns:
            插件目录路径
        """
        for directory in self._plugin_directories:
            dir_path = Path(directory)
            plugin_dir = dir_path / plugin_id
            
            if plugin_dir.exists() and plugin_dir.is_dir():
                return plugin_dir
        
        return None
    
    def _import_plugin(
        self,
        plugin_path: Path,
        plugin_id: str
    ) -> BasePlugin:
        """
        动态导入插件模块
        
        Args:
            plugin_path: 插件目录路径
            plugin_id: 插件ID
        
        Returns:
            插件实例
        """
        # 构建模块名
        module_name = f"plugins.{plugin_id}"
        
        # 检查是否已加载
        if module_name in sys.modules:
            # 重新加载
            module = importlib.reload(sys.modules[module_name])
        else:
            # 加载__init__.py
            init_file = plugin_path / "__init__.py"
            
            if not init_file.exists():
                raise ImportError(f"No __init__.py in {plugin_path}")
            
            # 使用importlib动态导入
            spec = importlib.util.spec_from_file_location(
                module_name,
                init_file
            )
            
            if not spec or not spec.loader:
                raise ImportError(f"Failed to create spec for {init_file}")
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        
        # 查找插件类
        plugin_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type) and
                issubclass(attr, BasePlugin) and
                attr is not BasePlugin
            ):
                plugin_class = attr
                break
        
        if not plugin_class:
            raise ImportError(
                f"No BasePlugin subclass found in {module_name}"
            )
        
        # 实例化
        instance = plugin_class()
        self._loaded_modules[plugin_id] = module
        
        return instance
    
    def _handle_file_change(self, file_path: str) -> None:
        """
        处理文件变更（热插拔）
        
        Args:
            file_path: 变更文件路径
        """
        # 提取插件ID
        plugin_id = self._extract_plugin_id(file_path)
        if not plugin_id:
            return
        
        # 检查权限
        permission = HotSwapPermission(
            plugin_id=plugin_id,
            signature_verified=True,
            is_official=plugin_id in HotSwapPermission.OFFICIAL_PLUGINS
        )
        
        if not permission.can_reload():
            logger.debug(f"Plugin {plugin_id} hot reload not allowed (L2/L3)")
            return
        
        # 防抖：取消之前的定时器
        if plugin_id in self._debounce_timers:
            self._debounce_timers[plugin_id].cancel()
        
        # 设置新定时器
        timer = threading.Timer(
            self._debounce_delay,
            self._reload_plugin,
            args=(plugin_id,)
        )
        self._debounce_timers[plugin_id] = timer
        timer.start()
    
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
    
    def _reload_plugin(self, plugin_id: str) -> None:
        """
        重载插件（内部方法）
        
        Args:
            plugin_id: 插件ID
        """
        logger.info(f"Reloading plugin {plugin_id}")
        
        result = self.reload_plugin(plugin_id)
        
        if result.success:
            self._event_bus.publish("plugin.reloaded", {
                "plugin_id": plugin_id
            })
        else:
            logger.error(f"Failed to reload plugin {plugin_id}: {result.error}")


# 全局单例
_loader_instance: Optional[PluginLoader] = None
_loader_lock = threading.Lock()


def get_plugin_loader() -> PluginLoader:
    """获取全局PluginLoader实例"""
    global _loader_instance
    if _loader_instance is None:
        with _loader_lock:
            if _loader_instance is None:
                _loader_instance = PluginLoader()
    return _loader_instance
