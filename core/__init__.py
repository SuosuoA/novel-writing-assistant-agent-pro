"""
Core模块入口

V1.2版本（最终修订版）
创建日期：2026-03-21

导出所有核心类和函数
"""

# 核心类
from .event_bus import (
    EventBus,
    EventPriority,
    DeadLetterQueue,
    get_event_bus
)

from .plugin_registry import (
    PluginRegistry,
    PluginState,
    PluginType,
    get_plugin_registry
)

from .service_locator import (
    ServiceLocator,
    ServiceScope,
    ServiceScopeManager,
    CircularDependencyError,
    ServiceNotFoundError,
    get_service_locator
)

from .config_manager import (
    ConfigManager,
    ConfigValidationError,
    ConfigKeyError,
    get_config_manager
)

from .plugin_loader import (
    PluginLoader,
    PluginLoadResult,
    DependencyResolver,
    HotSwapPermission,
    get_plugin_loader
)

from .plugin_interface import (
    BasePlugin,
    AnalyzerPlugin,
    GeneratorPlugin,
    ValidatorPlugin,
    StoragePlugin,
    AIPlugin,
    ToolPlugin,
    ProtocolPlugin
)

from .models import (
    Event,
    HandlerInfo,
    PluginMetadata,
    PluginInfo,
    ValidationScores,
    GenerationRequest,
    GenerationResult,
    PluginEvent
)

# V1.2新增模块
from .circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerManager,
    get_circuit_breaker_manager
)

from .secure_config import (
    SecureConfig,
    SecureConfigError,
    get_secure_config
)

from .log_sanitizer import (
    LogSanitizer,
    SanitizingFormatter,
    get_log_sanitizer
)

from .plugin_signer import (
    PluginSigner,
    PluginSignatureError,
    get_plugin_signer
)

# UI层API
from .ui_api import (
    CoreServiceManager,
    GenerationServiceProxy,
    PluginServiceProxy,
    ConfigServiceProxy,
    EventServiceProxy
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
    "get_plugin_loader",
    
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
]


__version__ = "1.2.0"
__author__ = "Novel Assistant Team"
