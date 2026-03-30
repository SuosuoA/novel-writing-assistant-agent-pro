"""
插件加载器 - 动态导入 + 依赖解析

V1.3版本（热插拔解耦版）
创建日期：2026-03-21

V1.3修订：
- 热插拔逻辑独立到 hot_swap_manager.py
- 集成 HotSwapManager
- 简化接口

V1.2特性：
- importlib动态导入
- 拓扑排序依赖解析
- 依赖检查
- 权限控制
"""

import hashlib
import importlib.util
import json
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
from .hot_swap_manager import HotSwapManager, HotSwapPermission

# 尝试导入结构化日志器
try:
    from infrastructure.logger import get_logger
    logger = get_logger("plugin_loader")
except ImportError:
    logger = logging.getLogger(__name__)


class PluginSignatureVerifier:
    """插件签名验证器
    
    使用SHA256哈希验证插件完整性。
    支持在plugin.json中配置signature字段。
    """
    
    @staticmethod
    def verify_plugin_signature(plugin_path: Path, plugin_id: str, plugin_json: Optional[Dict] = None) -> Tuple[bool, Optional[str]]:
        """验证插件签名
        
        Args:
            plugin_path: 插件目录路径
            plugin_id: 插件ID
            plugin_json: plugin.json内容（如果已解析）
        
        Returns:
            (验证是否通过, 错误信息)
        """
        # 读取plugin.json
        if plugin_json is None:
            plugin_json_path = plugin_path / "plugin.json"
            if not plugin_json_path.exists():
                # 没有plugin.json，视为未签名（L2级别）
                return False, None
            
            try:
                with open(plugin_json_path, "r", encoding="utf-8") as f:
                    plugin_json = json.load(f)
            except Exception as e:
                return False, f"Failed to read plugin.json: {e}"
        
        # 检查签名字段
        if "signature" not in plugin_json:
            # 没有签名字段，视为未签名（L2级别）
            return False, "No signature field in plugin.json"
        
        stored_signature = plugin_json.get("signature")
        if not stored_signature or not isinstance(stored_signature, str):
            return False, "Invalid signature format in plugin.json"
        
        # 计算实际哈希
        actual_signature = PluginSignatureVerifier._calculate_directory_hash(plugin_path)
        
        # 比较签名
        if actual_signature != stored_signature:
            return False, f"Signature mismatch for plugin {plugin_id}"
        
        return True, None
    
    # P1-3修复：最大遍历深度
    MAX_TRAVERSAL_DEPTH = 20
    
    @classmethod
    def _calculate_directory_hash(cls, directory: Path) -> str:
        """计算目录的SHA256哈希
        
        用于验证插件完整性。
        忽略__pycache__等缓存目录。
        
        P1-3修复：
        - 添加符号链接检测，避免无限循环
        - 添加遍历深度限制
        - 添加文件大小限制
        
        Args:
            directory: 插件目录路径
        
        Returns:
            SHA256哈希值
        """
        hasher = hashlib.sha256()
        file_count = 0
        total_size = 0
        max_file_size = 10 * 1024 * 1024  # 10MB
        max_total_size = 100 * 1024 * 1024  # 100MB
        
        # P1-3修复：使用安全的遍历方法
        def safe_walk(current_dir: Path, depth: int = 0):
            """安全遍历目录，带深度和符号链接检测"""
            nonlocal file_count, total_size
            
            if depth > cls.MAX_TRAVERSAL_DEPTH:
                logger.warning(f"Max traversal depth reached: {current_dir}")
                return
            
            try:
                for item in current_dir.iterdir():
                    # 跳过__pycache__目录
                    if item.name == "__pycache__":
                        continue
                    
                    # P1-3修复：检测符号链接，避免无限循环
                    try:
                        if item.is_symlink():
                            logger.debug(f"Skipping symlink: {item}")
                            continue
                        
                        # 检测是否为目录外链接
                        if item.is_dir():
                            # 确保解析后的路径仍在原目录内
                            resolved = item.resolve()
                            try:
                                resolved.relative_to(directory.resolve())
                            except ValueError:
                                logger.warning(f"Skipping external path: {item}")
                                continue
                            safe_walk(item, depth + 1)
                        elif item.is_file():
                            # 跳过.pyc文件
                            if item.suffix == ".pyc":
                                continue
                            
                            # P1-3修复：文件大小检查
                            file_size = item.stat().st_size
                            if file_size > max_file_size:
                                logger.warning(f"Skipping large file: {item} ({file_size} bytes)")
                                continue
                            
                            total_size += file_size
                            if total_size > max_total_size:
                                logger.warning(f"Total size limit reached, stopping traversal")
                                return
                            
                            try:
                                with open(item, "rb") as f:
                                    hasher.update(f.read())
                                    file_count += 1
                            except Exception as e:
                                logger.debug(f"Failed to read file {item}: {e}")
                                continue
                    except OSError as e:
                        logger.debug(f"Cannot access {item}: {e}")
                        continue
            except PermissionError as e:
                logger.debug(f"Permission denied: {current_dir}: {e}")
            except Exception as e:
                logger.debug(f"Error traversing {current_dir}: {e}")
        
        safe_walk(directory)
        
        if file_count == 0:
            logger.warning(f"No files hashed in {directory}")
        
        return hasher.hexdigest()


class PluginLoadResult:
    """插件加载结果"""

    def __init__(
        self,
        success: bool,
        plugin_id: str = "",
        error: Optional[str] = None,
        instance: Optional[Any] = None,
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
    - 版本冲突检查
    """

    @staticmethod
    def resolve(
        plugins: List[PluginMetadata],
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
            plugin_id for plugin_id, degree in in_degree.items() if degree == 0
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
                    errors.append(
                        {
                            "type": "circular_dependency",
                            "plugin_id": plugin_id,
                            "message": f"Circular dependency detected for {plugin_id}",
                        }
                    )

            # 返回部分排序结果（尽可能加载）
            return sorted_plugins, errors

        # 检测缺失依赖
        for plugin in plugins:
            for dep_id in plugin.dependencies:
                if dep_id not in plugin_map:
                    errors.append(
                        {
                            "type": "missing_dependency",
                            "plugin_id": plugin.id,
                            "dependency": dep_id,
                            "message": f"Missing dependency {dep_id} for {plugin.id}",
                        }
                    )

        return sorted_plugins, errors

    @staticmethod
    def check_conflicts(
        plugins: List[PluginMetadata],
    ) -> List[Dict[str, Any]]:
        """
        检查插件冲突

        Args:
            plugins: 插件元数据列表

        Returns:
            冲突列表
        """
        conflicts: List[Dict[str, Any]] = []
        plugin_ids = {p.id for p in plugins}

        for plugin in plugins:
            for conflict_id in plugin.conflicts:
                if conflict_id in plugin_ids:
                    conflicts.append(
                        {
                            "type": "conflict",
                            "plugin_id": plugin.id,
                            "conflicts_with": conflict_id,
                            "message": f"Plugin {plugin.id} conflicts with {conflict_id}",
                        }
                    )

        return conflicts


class PluginLoader:
    """
    插件加载器

    V1.3修订：
    - 集成 HotSwapManager（热插拔委托）
    - 简化接口

    V1.2特性：
    - 动态导入
    - 依赖解析
    - 权限控制
    """

    def __init__(
        self,
        plugin_directories: Optional[List[str]] = None,
        event_bus: Optional[EventBus] = None,
        registry: Optional[PluginRegistry] = None,
        hot_swap_enabled: bool = True,
        sandbox_enabled: bool = False,
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

        # 发现阶段缓存（不注册到Registry）
        self._discovered_plugins: Dict[str, PluginMetadata] = {}

        # 热插拔管理器（V1.3新增）
        self._hot_swap_manager: Optional[HotSwapManager] = None
        self._hot_swap_enabled = hot_swap_enabled

        # 沙箱
        self._sandbox_enabled = sandbox_enabled

        # 依赖解析器
        self._dependency_resolver = DependencyResolver()

    def discover_plugins(self) -> List[str]:
        """
        发现插件

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

                            with open(plugin_json, "r", encoding="utf-8") as f:
                                meta_dict = json.load(f)

                            metadata = PluginMetadata(**meta_dict)
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
                            version="1.0.0",
                        )
                        self._discovered_plugins[metadata.id] = metadata
                        discovered_ids.append(metadata.id)

        return discovered_ids

    def load_plugin(self, plugin_id: str) -> PluginLoadResult:
        """
        加载单个插件（带签名验证）

        Args:
            plugin_id: 插件ID

        Returns:
            加载结果
        """
        with self._lock:
            # 从_discovered_plugins获取元数据
            if plugin_id not in self._discovered_plugins:
                return PluginLoadResult(
                    success=False,
                    plugin_id=plugin_id,
                    error=f"Plugin {plugin_id} not discovered",
                )

            metadata = self._discovered_plugins[plugin_id]

            # 查找插件目录（必须在签名验证之前）
            plugin_path = self._find_plugin_path(plugin_id)
            if not plugin_path:
                return PluginLoadResult(
                    success=False,
                    plugin_id=plugin_id,
                    error=f"Plugin path not found for {plugin_id}",
                )

            # 签名验证
            is_official = plugin_id in HotSwapPermission.OFFICIAL_PLUGINS
            sig_verified, sig_error = PluginSignatureVerifier.verify_plugin_signature(
                plugin_path, plugin_id
            )

            # 记录签名验证结果
            if sig_verified:
                logger.info(f"Plugin {plugin_id} signature verified")
            else:
                logger.warning(
                    f"Plugin {plugin_id} signature verification failed: {sig_error}"
                )

            # 官方插件必须签名验证通过
            if is_official and not sig_verified:
                return PluginLoadResult(
                    success=False,
                    plugin_id=plugin_id,
                    error=f"Official plugin {plugin_id} signature verification failed: {sig_error}",
                )

            # 检查权限（基于签名验证结果）
            permission = HotSwapPermission(
                plugin_id=plugin_id,
                signature_verified=sig_verified,
                is_official=is_official,
            )

            if not permission.can_load():
                return PluginLoadResult(
                    success=False,
                    plugin_id=plugin_id,
                    error=f"Plugin {plugin_id} is blocked (L3) - signature verification failed",
                )

            # 动态导入
            try:
                instance = self._import_plugin(plugin_path, plugin_id)

                # 注册到Registry
                self._registry.register(plugin_id, metadata, instance)

                # 初始化插件
                # 创建PluginContext对象
                from .plugin_interface import PluginContext
                from .config_manager import get_config_manager
                from .service_locator import get_service_locator
                
                context = PluginContext(
                    event_bus=self._event_bus,
                    service_locator=get_service_locator(),
                    config_manager=get_config_manager(),
                    plugin_registry=self._registry,
                )

                if hasattr(instance, "initialize"):
                    instance.initialize(context)

                # 激活插件
                self._registry.activate(plugin_id)

                # 发布事件
                self._event_bus.publish(
                    "plugin.loaded",
                    {"plugin_id": plugin_id, "metadata": metadata.model_dump()},
                )

                return PluginLoadResult(
                    success=True, plugin_id=plugin_id, instance=instance
                )

            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_id}: {e}")

                # 设置错误状态
                self._registry.set_error(plugin_id, str(e))

                return PluginLoadResult(
                    success=False, plugin_id=plugin_id, error=str(e)
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
                is_official=plugin_id in HotSwapPermission.OFFICIAL_PLUGINS,
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
            if instance and hasattr(instance, "dispose"):
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
            self._event_bus.publish("plugin.unloaded", {"plugin_id": plugin_id})

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
            is_official=plugin_id in HotSwapPermission.OFFICIAL_PLUGINS,
        )

        if not permission.can_reload():
            return PluginLoadResult(
                success=False,
                plugin_id=plugin_id,
                error=f"Plugin {plugin_id} cannot be reloaded (L2/L3)",
            )

        # 卸载
        self.unload_plugin(plugin_id)

        # 重新加载
        return self.load_plugin(plugin_id)

    def load_all(self) -> Dict[str, PluginLoadResult]:
        """
        加载所有已发现的插件

        Returns:
            加载结果字典 {plugin_id: PluginLoadResult}
        """
        results: Dict[str, PluginLoadResult] = {}

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

        # 检查冲突
        conflicts = DependencyResolver.check_conflicts(plugins)
        for conflict in conflicts:
            logger.error(f"Plugin conflict: {conflict}")

        # 按顺序加载
        for plugin_id in sorted_ids:
            results[plugin_id] = self.load_plugin(plugin_id)

        return results

    def enable_hot_swap(self, debounce_delay: float = 1.0) -> bool:
        """
        启用热插拔监控（V1.3修订：委托给HotSwapManager）

        Args:
            debounce_delay: 防抖延迟（秒）

        Returns:
            是否启用成功
        """
        if not self._hot_swap_enabled:
            return False

        if self._hot_swap_manager is None:
            self._hot_swap_manager = HotSwapManager(
                plugin_loader=self,
                event_bus=self._event_bus,
                registry=self._registry,
                debounce_delay=debounce_delay,
            )

        success = self._hot_swap_manager.start_watch(self._plugin_directories)

        if success:
            logger.info("Hot swap monitoring enabled via HotSwapManager")

        return success

    def disable_hot_swap(self) -> None:
        """禁用热插拔监控"""
        if self._hot_swap_manager:
            self._hot_swap_manager.stop_watch()
            logger.info("Hot swap monitoring disabled")

    @property
    def hot_swap_manager(self) -> Optional[HotSwapManager]:
        """获取热插拔管理器"""
        return self._hot_swap_manager

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

    def _import_plugin(self, plugin_path: Path, plugin_id: str) -> BasePlugin:
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
            spec = importlib.util.spec_from_file_location(module_name, init_file)

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
                isinstance(attr, type)
                and issubclass(attr, BasePlugin)
                and attr is not BasePlugin
            ):
                plugin_class = attr
                break

        if not plugin_class:
            raise ImportError(f"No BasePlugin subclass found in {module_name}")

        # 实例化
        instance = plugin_class()
        self._loaded_modules[plugin_id] = module

        return instance

    def get_discovered_plugins(self) -> Dict[str, PluginMetadata]:
        """获取已发现的插件"""
        return dict(self._discovered_plugins)

    def get_loaded_modules(self) -> Dict[str, Any]:
        """获取已加载的模块"""
        return dict(self._loaded_modules)


# 导出HotSwapPermission供外部使用（兼容性）
__all__ = [
    "PluginLoader",
    "PluginLoadResult",
    "DependencyResolver",
    "HotSwapPermission",
    "CircularDependencyError",
    "get_plugin_loader",
]

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
