"""
基础设施层

V1.0版本
创建日期: 2026-03-21

提供以下基础设施服务：
- logger: 结构化日志系统
- monitor: 性能监控与指标采集
- security: 安全工具（敏感信息脱敏）
- circuit_breaker: 熔断器
- health_check: 健康检查
- database: 数据库连接池
"""

from .logger import (
    get_logger,
    setup_logging,
    StructuredLogger,
    LogLevel,
)
from .monitor import (
    MetricsCollector,
    PerformanceMonitor,
    get_metrics_collector,
    get_performance_monitor,
)
from .security import (
    sanitize_data,
    mask_sensitive,
    SensitiveDataFilter,
    SECURITY_PATTERNS,
)
from .circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerError,
    get_circuit_breaker,
)
from .health_check import (
    HealthChecker,
    HealthStatus,
    HealthCheckResult,
    get_health_checker,
)
from .database import (
    DatabasePool,
    get_database_pool,
    init_database,
)

__all__ = [
    # Logger
    "get_logger",
    "setup_logging",
    "StructuredLogger",
    "LogLevel",
    # Monitor
    "MetricsCollector",
    "PerformanceMonitor",
    "get_metrics_collector",
    "get_performance_monitor",
    # Security
    "sanitize_data",
    "mask_sensitive",
    "SensitiveDataFilter",
    "SECURITY_PATTERNS",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerError",
    "get_circuit_breaker",
    # Health Check
    "HealthChecker",
    "HealthStatus",
    "HealthCheckResult",
    "get_health_checker",
    # Database
    "DatabasePool",
    "get_database_pool",
    "init_database",
]
