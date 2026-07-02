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
# 启动性能修复：vector_store 会在模块导入时加载 lancedb（约1.9s），
# 而向量召回是启动后才用到的功能。这里改为 PEP 562 惰性暴露——
# 仅当真正访问下列符号时才导入 vector_store（及 lancedb），
# 避免"导入 infrastructure（哪怕只为用 logger）"就把 lancedb 整个拖进来。
_VECTOR_STORE_EXPORTS = {
    "NovelVectorStore",
    "ChapterVector",
    "KnowledgeVector",
    "StyleVector",
    "VectorSearchResult",
    "EmbeddingFunction",
    "get_vector_store",
    "reset_vector_store",
}


def __getattr__(name):
    """惰性加载 vector_store 符号（PEP 562）。

    使 `from infrastructure import get_vector_store` 等包级访问仍然可用，
    但只有在实际访问时才触发 lancedb 的加载，从而不拖慢启动。
    """
    if name in _VECTOR_STORE_EXPORTS:
        from . import vector_store as _vs
        return getattr(_vs, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

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
    # Vector Store
    "NovelVectorStore",
    "ChapterVector",
    "KnowledgeVector",
    "StyleVector",
    "VectorSearchResult",
    "EmbeddingFunction",
    "get_vector_store",
    "reset_vector_store",
]
