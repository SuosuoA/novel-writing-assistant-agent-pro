"""
服务定位器 - 依赖注入 + 生命周期管理

V1.2版本（最终修订版）
创建日期：2026-03-21

V1.1增强：
- 增加生命周期管理接口
- 增加initialized字段
- 循环依赖检测

特性：
- 线程安全（RLock）
- 循环依赖检测
- 单例/瞬态/作用域生命周期
"""

import threading
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type


class ServiceScope(str, Enum):
    """服务生命周期"""

    SINGLETON = "SINGLETON"  # 单例（全局唯一）
    TRANSIENT = "TRANSIENT"  # 瞬态（每次创建新实例）
    SCOPED = "SCOPED"  # 作用域（同一作用域共享）


class ServiceDescriptor:
    """
    服务描述符

    V1.1新增：initialized字段
    """

    def __init__(
        self,
        service_type: Type,
        implementation: Any = None,
        scope: ServiceScope = ServiceScope.SINGLETON,
        factory: Optional[Callable] = None,
        dependencies: Optional[Set[Type]] = None,
    ):
        """
        初始化服务描述符

        Args:
            service_type: 服务类型
            implementation: 实现实例
            scope: 生命周期
            factory: 工厂函数
            dependencies: 依赖的服务类型集合
        """
        self.service_type = service_type
        self.implementation = implementation
        self.scope = scope
        self.factory = factory
        self.dependencies = dependencies or set()
        self.initialized: bool = False  # V1.1新增


class CircularDependencyError(Exception):
    """循环依赖异常"""

    pass


class ServiceNotFoundError(Exception):
    """服务未找到异常"""

    pass


class ServiceLocator:
    """
    服务定位器 - 依赖注入 + 生命周期管理

    V1.1增强：
    - 增加initialize_all()、dispose_all()、get_initialization_status()接口
    - 循环依赖检测（通过dependencies属性）
    """

    def __init__(self):
        """初始化服务定位器"""
        self._services: Dict[Type, Any] = {}
        self._descriptors: Dict[Type, ServiceDescriptor] = {}
        self._lock = threading.RLock()
        self._initializing: Set[Type] = set()  # 用于检测循环依赖

    def register(
        self,
        service_type: Type,
        instance: Any,
        scope: ServiceScope = ServiceScope.SINGLETON,
        dependencies: Optional[Set[Type]] = None,
    ) -> None:
        """
        注册服务实例

        Args:
            service_type: 服务类型
            instance: 服务实例
            scope: 生命周期
            dependencies: 依赖的服务类型集合
        """
        with self._lock:
            descriptor = ServiceDescriptor(
                service_type=service_type,
                implementation=instance,
                scope=scope,
                dependencies=dependencies,
            )
            self._descriptors[service_type] = descriptor

            if scope == ServiceScope.SINGLETON:
                self._services[service_type] = instance

    def register_factory(
        self,
        service_type: Type,
        factory: Callable,
        scope: ServiceScope = ServiceScope.SINGLETON,
        dependencies: Optional[Set[Type]] = None,
    ) -> None:
        """
        注册服务工厂

        Args:
            service_type: 服务类型
            factory: 工厂函数
            scope: 生命周期
            dependencies: 依赖的服务类型集合
        """
        with self._lock:
            descriptor = ServiceDescriptor(
                service_type=service_type,
                scope=scope,
                factory=factory,
                dependencies=dependencies,
            )
            self._descriptors[service_type] = descriptor

    def register_singleton(
        self,
        service_type: Type,
        factory: Callable,
        dependencies: Optional[Set[Type]] = None,
    ) -> None:
        """
        注册单例服务（便捷方法）

        Args:
            service_type: 服务类型
            factory: 工厂函数
            dependencies: 依赖的服务类型集合
        """
        self.register_factory(
            service_type,
            factory,
            scope=ServiceScope.SINGLETON,
            dependencies=dependencies,
        )

    def unregister(self, service_type: Type) -> bool:
        """
        注销服务

        Args:
            service_type: 服务类型

        Returns:
            是否注销成功
        """
        with self._lock:
            if service_type in self._descriptors:
                del self._descriptors[service_type]
            if service_type in self._services:
                del self._services[service_type]
            return True

    def get(self, service_type: Type) -> Any:
        """
        获取服务实例

        Args:
            service_type: 服务类型

        Returns:
            服务实例

        Raises:
            ServiceNotFoundError: 服务未注册
            CircularDependencyError: 循环依赖检测失败
        """
        with self._lock:
            # 检查是否已注册
            if service_type not in self._descriptors:
                raise ServiceNotFoundError(f"Service {service_type} not registered")

            # 检查循环依赖
            if service_type in self._initializing:
                raise CircularDependencyError(
                    f"Circular dependency detected: {service_type}"
                )

            descriptor = self._descriptors[service_type]

            # 单例：已创建则直接返回
            if descriptor.scope == ServiceScope.SINGLETON:
                if service_type in self._services:
                    return self._services[service_type]

            # 创建新实例
            self._initializing.add(service_type)
            try:
                instance = self._create_instance(descriptor)

                if descriptor.scope == ServiceScope.SINGLETON:
                    self._services[service_type] = instance

                return instance
            finally:
                self._initializing.discard(service_type)

    def get_or_default(self, service_type: Type, default: Any = None) -> Any:
        """
        获取服务实例，不存在则返回默认值

        Args:
            service_type: 服务类型
            default: 默认值

        Returns:
            服务实例或默认值
        """
        try:
            return self.get(service_type)
        except ServiceNotFoundError:
            return default

    def try_get(self, service_type: Type) -> Optional[Any]:
        """
        尝试获取服务实例

        Args:
            service_type: 服务类型

        Returns:
            服务实例或None
        """
        try:
            return self.get(service_type)
        except (ServiceNotFoundError, CircularDependencyError):
            return None

    def has_service(self, service_type: Type) -> bool:
        """
        检查服务是否已注册

        Args:
            service_type: 服务类型

        Returns:
            是否已注册
        """
        with self._lock:
            return service_type in self._descriptors

    def check_circular_dependency(self, service_type: Type) -> bool:
        """
        检查是否存在循环依赖

        Args:
            service_type: 起始服务类型

        Returns:
            是否存在循环依赖
        """
        with self._lock:
            visited: Set[Type] = set()
            return self._check_circular_recursive(service_type, visited)

    def _check_circular_recursive(self, service_type: Type, visited: Set[Type]) -> bool:
        """递归检查循环依赖"""
        if service_type in visited:
            return True

        visited.add(service_type)

        descriptor = self._descriptors.get(service_type)
        if descriptor:
            for dep_type in descriptor.dependencies:
                if self._check_circular_recursive(dep_type, visited):
                    return True

        visited.discard(service_type)
        return False

    def validate_all_dependencies(self) -> Dict[str, Any]:
        """
        验证所有服务的依赖关系

        Returns:
            验证结果 {
                "valid": bool,
                "errors": List[str],
                "warnings": List[str]
            }
        """
        with self._lock:
            errors: List[str] = []
            warnings: List[str] = []

            for service_type, descriptor in self._descriptors.items():
                # 检查循环依赖
                if self.check_circular_dependency(service_type):
                    errors.append(f"Circular dependency detected for {service_type}")

                # 检查依赖是否注册
                for dep_type in descriptor.dependencies:
                    if dep_type not in self._descriptors:
                        warnings.append(
                            f"Dependency {dep_type} not registered for {service_type}"
                        )

            return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    def initialize_all(self) -> Dict[str, bool]:
        """
        按依赖顺序初始化所有服务（V1.1新增）

        Returns:
            初始化结果 {service_name: bool}
        """
        with self._lock:
            results: Dict[str, bool] = {}

            # 拓扑排序获取初始化顺序
            sorted_services = self._topological_sort_services()

            for service_type in sorted_services:
                try:
                    descriptor = self._descriptors[service_type]

                    # 跳过已初始化的单例
                    if descriptor.initialized and service_type in self._services:
                        results[service_type.__name__] = True
                        continue

                    # 创建实例
                    instance = self.get(service_type)

                    # 调用初始化方法
                    if hasattr(instance, "initialize") and callable(
                        instance.initialize
                    ):
                        instance.initialize()

                    descriptor.initialized = True
                    results[service_type.__name__] = True

                except Exception as e:
                    results[service_type.__name__] = False
                    import logging

                    logging.error(f"Failed to initialize {service_type}: {e}")

            return results

    def dispose_all(self) -> Dict[str, bool]:
        """
        逆序释放所有服务资源（V1.1新增）

        Returns:
            释放结果 {service_name: bool}
        """
        with self._lock:
            results: Dict[str, bool] = {}

            # 逆序释放
            sorted_services = self._topological_sort_services()
            sorted_services.reverse()

            for service_type in sorted_services:
                try:
                    if service_type in self._services:
                        instance = self._services[service_type]

                        # 调用释放方法
                        if hasattr(instance, "dispose") and callable(instance.dispose):
                            instance.dispose()

                        descriptor = self._descriptors.get(service_type)
                        if descriptor:
                            descriptor.initialized = False

                        results[service_type.__name__] = True

                except Exception as e:
                    results[service_type.__name__] = False
                    import logging

                    logging.error(f"Failed to dispose {service_type}: {e}")

            return results

    def get_initialization_status(self, service_type: Type) -> Dict[str, Any]:
        """
        查询服务初始化状态（V1.1新增）

        Args:
            service_type: 服务类型

        Returns:
            初始化状态 {
                "registered": bool,
                "initialized": bool,
                "scope": str,
                "dependencies": List[str]
            }
        """
        with self._lock:
            descriptor = self._descriptors.get(service_type)

            if not descriptor:
                return {
                    "registered": False,
                    "initialized": False,
                    "scope": None,
                    "dependencies": [],
                }

            return {
                "registered": True,
                "initialized": descriptor.initialized,
                "scope": descriptor.scope.value,
                "dependencies": [dep.__name__ for dep in descriptor.dependencies],
            }

    def _topological_sort_services(self) -> List[Type]:
        """
        服务拓扑排序（V1.1新增）

        使用Kahn算法

        Returns:
            排序后的服务类型列表
        """
        # 计算入度
        in_degree: Dict[Type, int] = {
            service_type: 0 for service_type in self._descriptors
        }

        # 构建依赖图
        graph: Dict[Type, List[Type]] = {
            service_type: [] for service_type in self._descriptors
        }

        for service_type, descriptor in self._descriptors.items():
            for dep_type in descriptor.dependencies:
                if dep_type in self._descriptors:
                    graph[dep_type].append(service_type)
                    in_degree[service_type] += 1

        # Kahn算法
        queue: List[Type] = [
            service_type for service_type, degree in in_degree.items() if degree == 0
        ]

        sorted_services: List[Type] = []

        while queue:
            current = queue.pop(0)
            sorted_services.append(current)

            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 如果存在循环依赖，返回所有服务（顺序可能不正确）
        if len(sorted_services) != len(self._descriptors):
            return list(self._descriptors.keys())

        return sorted_services

    def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
        """
        创建服务实例

        Args:
            descriptor: 服务描述符

        Returns:
            服务实例
        """
        if descriptor.factory:
            return descriptor.factory()
        elif descriptor.implementation:
            return descriptor.implementation
        else:
            raise ServiceNotFoundError(
                f"No implementation or factory for {descriptor.service_type}"
            )


class ServiceScopeManager:
    """
    作用域管理器

    管理SCOPED生命周期服务的实例
    """

    def __init__(self, locator: "ServiceLocator"):
        """
        初始化作用域管理器

        Args:
            locator: 服务定位器实例
        """
        self._locator = locator
        self._scoped_services: Dict[Type, Any] = {}
        self._lock = threading.RLock()

    def get(self, service_type: Type) -> Any:
        """
        获取作用域服务实例

        Args:
            service_type: 服务类型

        Returns:
            服务实例
        """
        with self._lock:
            # 检查是否已创建
            if service_type in self._scoped_services:
                return self._scoped_services[service_type]

            # 创建新实例
            instance = self._locator.get(service_type)
            self._scoped_services[service_type] = instance
            return instance

    def clear(self) -> None:
        """清理作用域内所有服务"""
        with self._lock:
            self._scoped_services.clear()


# 全局单例
_locator_instance: Optional[ServiceLocator] = None
_locator_lock = threading.Lock()


def get_service_locator() -> ServiceLocator:
    """获取全局ServiceLocator实例"""
    global _locator_instance
    if _locator_instance is None:
        with _locator_lock:
            if _locator_instance is None:
                _locator_instance = ServiceLocator()
    return _locator_instance
