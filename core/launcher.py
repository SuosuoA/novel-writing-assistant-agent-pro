"""
延迟加载管理器 - 分层加载与优先级调度

V1.0版本
创建日期：2026-03-21

特性：
- 4层加载优先级（核心层 > 插件层 > Agent层 > UI层）
- 延迟加载非关键模块
- 异步初始化支持
- 加载状态跟踪
"""

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import IntEnum
from concurrent.futures import ThreadPoolExecutor, Future
import logging

logger = logging.getLogger(__name__)


class LoadPriority(IntEnum):
    """加载优先级（数值越小优先级越高）"""
    CORE = 0       # 核心层：配置、日志、事件总线、服务定位器
    PLUGIN = 10    # 插件层：插件加载器、插件注册表
    AGENT = 20     # Agent层：MasterAgent、专家Agent
    UI = 30        # UI层：GUI组件、界面渲染


@dataclass
class ModuleInfo:
    """模块信息"""
    name: str
    priority: LoadPriority
    loader: Callable[[], Any]
    dependencies: List[str] = field(default_factory=list)
    is_loaded: bool = False
    load_time: float = 0.0
    error: Optional[Exception] = None
    instance: Optional[Any] = None


class LazyLoader:
    """延迟加载管理器"""
    
    _instance: Optional['LazyLoader'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'LazyLoader':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._modules: Dict[str, ModuleInfo] = {}
        self._load_order: List[str] = []
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="loader")
        self._load_callback: Optional[Callable[[str, bool], None]] = None
        self._progress_callback: Optional[Callable[[int, int, str], None]] = None
        self._initialized = True
        self._load_start_time = 0.0
        logger.info("LazyLoader initialized")
    
    def register(
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
        if name in self._modules:
            logger.warning(f"Module '{name}' already registered, skipping")
            return
        
        self._modules[name] = ModuleInfo(
            name=name,
            priority=priority,
            loader=loader,
            dependencies=dependencies or []
        )
        
        # 重新计算加载顺序
        self._calculate_load_order()
        logger.debug(f"Registered module '{name}' with priority {priority.name}")
    
    def _calculate_load_order(self) -> None:
        """计算加载顺序（拓扑排序）"""
        # 按优先级分组
        priority_groups: Dict[LoadPriority, List[str]] = {}
        for name, info in self._modules.items():
            if info.priority not in priority_groups:
                priority_groups[info.priority] = []
            priority_groups[info.priority].append(name)
        
        # 按优先级顺序加载，同优先级内按依赖关系排序
        self._load_order = []
        loaded_set: Set[str] = set()
        
        for priority in sorted(priority_groups.keys()):
            group = priority_groups[priority]
            # 拓扑排序
            sorted_group = self._topological_sort(group, loaded_set)
            self._load_order.extend(sorted_group)
            loaded_set.update(sorted_group)
    
    def _topological_sort(
        self,
        modules: List[str],
        already_loaded: Set[str]
    ) -> List[str]:
        """拓扑排序"""
        result = []
        visited = set(already_loaded)
        temp_visited = set()
        
        def visit(name: str):
            if name in visited:
                return
            if name in temp_visited:
                logger.warning(f"Circular dependency detected involving '{name}'")
                return
            
            temp_visited.add(name)
            
            info = self._modules.get(name)
            if info:
                for dep in info.dependencies:
                    if dep in modules:  # 只处理同组内的依赖
                        visit(dep)
            
            temp_visited.remove(name)
            visited.add(name)
            result.append(name)
        
        for name in modules:
            visit(name)
        
        return result
    
    def load_module(self, name: str) -> bool:
        """
        加载单个模块
        
        Args:
            name: 模块名称
            
        Returns:
            是否加载成功
        """
        info = self._modules.get(name)
        if not info:
            logger.error(f"Module '{name}' not found")
            return False
        
        if info.is_loaded:
            logger.debug(f"Module '{name}' already loaded")
            return True
        
        try:
            start_time = time.time()
            instance = info.loader()
            load_time = time.time() - start_time
            
            info.is_loaded = True
            info.load_time = load_time
            info.instance = instance
            
            logger.info(f"Loaded module '{name}' in {load_time:.3f}s")
            
            if self._load_callback:
                self._load_callback(name, True)
            
            return True
            
        except Exception as e:
            info.error = e
            logger.error(f"Failed to load module '{name}': {e}")
            
            if self._load_callback:
                self._load_callback(name, False)
            
            return False
    
    def load_all(
        self,
        load_callback: Optional[Callable[[str, bool], None]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, bool]:
        """
        加载所有模块
        
        Args:
            load_callback: 单个模块加载完成回调
            progress_callback: 进度回调
            
        Returns:
            模块加载结果字典
        """
        self._load_callback = load_callback
        self._progress_callback = progress_callback
        self._load_start_time = time.time()
        
        results = {}
        total = len(self._load_order)
        
        logger.info(f"Starting to load {total} modules")
        
        for i, name in enumerate(self._load_order):
            if self._progress_callback:
                self._progress_callback(i, total, name)
            
            results[name] = self.load_module(name)
        
        total_time = time.time() - self._load_start_time
        success_count = sum(1 for v in results.values() if v)
        
        logger.info(
            f"Loaded {success_count}/{total} modules in {total_time:.3f}s"
        )
        
        return results
    
    def load_async(
        self,
        on_complete: Optional[Callable[[Dict[str, bool]], None]] = None,
        load_callback: Optional[Callable[[str, bool], None]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Future:
        """
        异步加载所有模块
        
        Args:
            on_complete: 全部加载完成回调
            load_callback: 单个模块加载完成回调
            progress_callback: 进度回调
            
        Returns:
            Future对象
        """
        def _load():
            results = self.load_all(load_callback, progress_callback)
            if on_complete:
                on_complete(results)
            return results
        
        return self._executor.submit(_load)
    
    def load_priority_group(self, priority: LoadPriority) -> Dict[str, bool]:
        """
        加载指定优先级的所有模块
        
        Args:
            priority: 优先级
            
        Returns:
            模块加载结果字典
        """
        results = {}
        for name in self._load_order:
            info = self._modules.get(name)
            if info and info.priority == priority:
                results[name] = self.load_module(name)
        return results
    
    def load_up_to(self, priority: LoadPriority) -> Dict[str, bool]:
        """
        加载到指定优先级（包含）
        
        Args:
            priority: 目标优先级
            
        Returns:
            模块加载结果字典
        """
        results = {}
        for name in self._load_order:
            info = self._modules.get(name)
            if info and info.priority <= priority:
                results[name] = self.load_module(name)
        return results
    
    def get_module(self, name: str) -> Optional[Any]:
        """
        获取已加载的模块实例
        
        Args:
            name: 模块名称
            
        Returns:
            模块实例或None
        """
        info = self._modules.get(name)
        if info and info.is_loaded:
            return info.instance
        return None
    
    def get_load_stats(self) -> Dict[str, Any]:
        """
        获取加载统计信息
        
        Returns:
            统计信息字典
        """
        total = len(self._modules)
        loaded = sum(1 for info in self._modules.values() if info.is_loaded)
        failed = sum(1 for info in self._modules.values() if info.error is not None)
        total_time = sum(info.load_time for info in self._modules.values())
        
        return {
            "total_modules": total,
            "loaded_modules": loaded,
            "failed_modules": failed,
            "total_load_time": total_time,
            "modules": {
                name: {
                    "is_loaded": info.is_loaded,
                    "load_time": info.load_time,
                    "priority": info.priority.name,
                    "error": str(info.error) if info.error else None
                }
                for name, info in self._modules.items()
            }
        }
    
    def reset(self) -> None:
        """重置加载状态"""
        for info in self._modules.values():
            info.is_loaded = False
            info.load_time = 0.0
            info.error = None
            info.instance = None
        logger.info("LazyLoader reset")
    
    def shutdown(self) -> None:
        """关闭加载器"""
        self._executor.shutdown(wait=True)
        logger.info("LazyLoader shutdown")


def get_lazy_loader() -> LazyLoader:
    """获取LazyLoader单例"""
    return LazyLoader()
