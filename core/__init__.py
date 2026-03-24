"""
Core模块入口

V1.2版本（最终修订版）
创建日期：2026-03-21

导出所有核心类和函数
"""

# 核心类
from .event_bus import EventBus, EventPriority, DeadLetterQueue, get_event_bus

from .plugin_registry import (
    PluginRegistry,
    PluginState,
    PluginType,
    get_plugin_registry,
)

from .service_locator import (
    ServiceLocator,
    ServiceScope,
    ServiceScopeManager,
    CircularDependencyError,
    ServiceNotFoundError,
    get_service_locator,
)

from .config_manager import (
    ConfigManager,
    ConfigValidationError,
    ConfigKeyError,
    get_config_manager,
)

from .plugin_loader import (
    PluginLoader,
    PluginLoadResult,
    DependencyResolver,
    HotSwapPermission,
    PluginSignatureVerifier,
    get_plugin_loader,
)

from .hot_swap_manager import (
    HotSwapManager,
    HotSwapAction,
    HotSwapState,
    HotSwapEvent,
    PluginStateInfo,
    get_hot_swap_manager,
)

from .plugin_interface import (
    BasePlugin,
    AnalyzerPlugin,
    GeneratorPlugin,
    ValidatorPlugin,
    StoragePlugin,
    AIPlugin,
    ToolPlugin,
    ProtocolPlugin,
)

from .models import (
    Event,
    HandlerInfo,
    PluginMetadata,
    PluginInfo,
    ValidationScores,
    GenerationRequest,
    GenerationResult,
    PluginEvent,
)

# V1.2新增模块
from .circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerManager,
    get_circuit_breaker_manager,
)

from .secure_config import SecureConfig, SecureConfigError, get_secure_config

from .log_sanitizer import LogSanitizer, SanitizingFormatter, get_log_sanitizer

from .plugin_signer import PluginSigner, PluginSignatureError, get_plugin_signer

# UI层API
from .ui_api import (
    CoreServiceManager,
    GenerationServiceProxy,
    PluginServiceProxy,
    ConfigServiceProxy,
    EventServiceProxy,
)

# Database（V1.0新增）
from .database import (
    ConnectionPool,
    DatabaseMigration,
    AgentStateStore,
    GenerationHistoryStore,
    get_database,
    get_agent_state_store,
    get_generation_history_store,
    close_database,
)

# AsyncHandler（V1.0新增）
from .async_handler import (
    AsyncHandler,
    Task,
    TaskPriority,
    TaskState,
    PriorityTaskQueue,
    get_async_handler,
    init_async_handler,
)

# Launcher（V1.0新增）
from .launcher import (
    LazyLoader,
    LoadPriority,
    ModuleInfo,
    get_lazy_loader,
)

from .app_launcher import (
    OptimizedLauncher,
    StartupConfig,
    get_optimized_launcher,
)

# ConfigService（V1.3新增）
from .config_service import ConfigService, AppConfig, get_config_service

# LoggingService（V1.3新增）
from .logging_service import LoggingService, get_logging_service

# BootstrapService（V1.3新增）
from .bootstrap import (
    BootstrapService,
    get_bootstrap_service,
    initialize_core_services,
    dispose_core_services,
)

# CacheManager（V1.4新增）
from .cache_manager import (
    CacheManager,
    CacheConfig,
    CacheEntry,
    SimpleTTLCache,
    generate_cache_key,
    cached,
    get_cache_manager,
    init_cache_manager,
    CACHETOOLS_AVAILABLE,
)

__all__ = [
    # EventBus
    "EventBus",
    "EventPriority",
    "DeadLetterQueue",
    "get_event_bus",
    # PluginRegistry
    "PluginRegistry",
    "PluginState",
    "PluginType",
    "get_plugin_registry",
    # ServiceLocator
    "ServiceLocator",
    "ServiceScope",
    "ServiceScopeManager",
    "CircularDependencyError",
    "ServiceNotFoundError",
    "get_service_locator",
    # ConfigManager
    "ConfigManager",
    "ConfigValidationError",
    "ConfigKeyError",
    "get_config_manager",
    # PluginLoader
    "PluginLoader",
    "PluginLoadResult",
    "DependencyResolver",
    "HotSwapPermission",
    "PluginSignatureVerifier",
    "get_plugin_loader",
    # HotSwapManager
    "HotSwapManager",
    "HotSwapAction",
    "HotSwapState",
    "HotSwapEvent",
    "PluginStateInfo",
    "get_hot_swap_manager",
    # PluginInterface
    "BasePlugin",
    "AnalyzerPlugin",
    "GeneratorPlugin",
    "ValidatorPlugin",
    "StoragePlugin",
    "AIPlugin",
    "ToolPlugin",
    "ProtocolPlugin",
    # Models
    "Event",
    "HandlerInfo",
    "PluginMetadata",
    "PluginInfo",
    "ValidationScores",
    "GenerationRequest",
    "GenerationResult",
    "PluginEvent",
    # V1.2新增
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerManager",
    "get_circuit_breaker_manager",
    "SecureConfig",
    "SecureConfigError",
    "get_secure_config",
    "LogSanitizer",
    "SanitizingFormatter",
    "get_log_sanitizer",
    "PluginSigner",
    "PluginSignatureError",
    "get_plugin_signer",
    # UI层API
    "CoreServiceManager",
    "GenerationServiceProxy",
    "PluginServiceProxy",
    "ConfigServiceProxy",
    "EventServiceProxy",
    # Database
    "ConnectionPool",
    "DatabaseMigration",
    "AgentStateStore",
    "GenerationHistoryStore",
    "get_database",
    "get_agent_state_store",
    "get_generation_history_store",
    "close_database",
    # AsyncHandler
    "AsyncHandler",
    "Task",
    "TaskPriority",
    "TaskState",
    "PriorityTaskQueue",
    "get_async_handler",
    "init_async_handler",
    # Launcher
    "LazyLoader",
    "LoadPriority",
    "ModuleInfo",
    "get_lazy_loader",
    "OptimizedLauncher",
    "StartupConfig",
    "get_optimized_launcher",
    # ConfigService
    "ConfigService",
    "AppConfig",
    "get_config_service",
    # LoggingService
    "LoggingService",
    "get_logging_service",
    # BootstrapService
    "BootstrapService",
    "get_bootstrap_service",
    "initialize_core_services",
    "dispose_core_services",
    # CacheManager
    "CacheManager",
    "CacheConfig",
    "CacheEntry",
    "SimpleTTLCache",
    "generate_cache_key",
    "cached",
    "get_cache_manager",
    "init_cache_manager",
    "CACHETOOLS_AVAILABLE",
]


__version__ = "1.4.0"
__author__ = "Novel Assistant Team"
