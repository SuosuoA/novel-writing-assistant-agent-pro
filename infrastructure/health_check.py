"""
健康检查模块

V1.0版本
创建日期: 2026-03-21

特性：
- 健康检查端点
- 依赖项状态检测
- 健康状态聚合
"""

import time
import threading
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    name: str
    status: HealthStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    latency_ms: float = 0.0


@dataclass
class HealthReport:
    """健康报告"""
    status: HealthStatus
    checks: List[HealthCheckResult]
    timestamp: datetime = field(default_factory=datetime.now)
    version: str = "1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "version": self.version,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "details": c.details,
                    "latency_ms": c.latency_ms,
                }
                for c in self.checks
            ],
        }


class HealthChecker:
    """
    健康检查器
    
    用于检查系统各组件的健康状态
    
    用法:
        checker = HealthChecker()
        
        # 注册检查项
        checker.register("database", check_database)
        checker.register("cache", check_cache)
        
        # 执行检查
        report = checker.check()
    """
    
    def __init__(self, version: str = "1.0.0"):
        """
        初始化健康检查器
        
        Args:
            version: 应用版本
        """
        self._checks: Dict[str, Callable[[], HealthCheckResult]] = {}
        self._version = version
        self._lock = threading.RLock()
        
        # 状态权重（用于聚合）
        self._status_weights = {
            HealthStatus.HEALTHY: 0,
            HealthStatus.DEGRADED: 1,
            HealthStatus.UNHEALTHY: 2,
        }
    
    def register(
        self, name: str, check_func: Callable[[], HealthCheckResult]
    ) -> None:
        """
        注册健康检查项
        
        Args:
            name: 检查项名称
            check_func: 检查函数（返回HealthCheckResult）
        """
        with self._lock:
            self._checks[name] = check_func
    
    def unregister(self, name: str) -> bool:
        """取消注册检查项"""
        with self._lock:
            if name in self._checks:
                del self._checks[name]
                return True
            return False
    
    def check(self, names: Optional[List[str]] = None) -> HealthReport:
        """
        执行健康检查
        
        Args:
            names: 要检查的项（None表示全部）
        
        Returns:
            健康报告
        """
        checks_to_run = names or list(self._checks.keys())
        results: List[HealthCheckResult] = []
        
        for name in checks_to_run:
            if name not in self._checks:
                results.append(HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check '{name}' not found",
                ))
                continue
            
            try:
                start_time = time.time()
                result = self._checks[name]()
                result.latency_ms = (time.time() - start_time) * 1000
                results.append(result)
            except Exception as e:
                results.append(HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(e)}",
                ))
        
        # 聚合状态
        overall_status = self._aggregate_status(results)
        
        return HealthReport(
            status=overall_status,
            checks=results,
            version=self._version,
        )
    
    def _aggregate_status(self, results: List[HealthCheckResult]) -> HealthStatus:
        """聚合状态"""
        if not results:
            return HealthStatus.HEALTHY
        
        max_weight = max(
            self._status_weights.get(r.status, 0) for r in results
        )
        
        for status, weight in self._status_weights.items():
            if weight == max_weight:
                return status
        
        return HealthStatus.HEALTHY
    
    def check_single(self, name: str) -> Optional[HealthCheckResult]:
        """检查单个项"""
        with self._lock:
            if name not in self._checks:
                return None
        
        try:
            start_time = time.time()
            result = self._checks[name]()
            result.latency_ms = (time.time() - start_time) * 1000
            return result
        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}",
            )
    
    def list_checks(self) -> List[str]:
        """列出所有检查项"""
        with self._lock:
            return list(self._checks.keys())


# 预定义的常用检查函数
def check_database_connection(
    db_path: str = ":memory:",
) -> HealthCheckResult:
    """
    检查数据库连接
    
    Args:
        db_path: 数据库路径
    
    Returns:
        检查结果
    """
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        
        return HealthCheckResult(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Database connection successful",
            details={"path": db_path},
        )
    except Exception as e:
        return HealthCheckResult(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=f"Database connection failed: {str(e)}",
        )


def check_file_system(
    base_path: str = ".",
) -> HealthCheckResult:
    """
    检查文件系统
    
    Args:
        base_path: 基础路径
    
    Returns:
        检查结果
    """
    try:
        from pathlib import Path
        
        path = Path(base_path)
        if not path.exists():
            return HealthCheckResult(
                name="file_system",
                status=HealthStatus.UNHEALTHY,
                message=f"Path does not exist: {base_path}",
            )
        
        # 检查读写权限
        test_file = path / ".health_check_test"
        test_file.write_text("test")
        test_file.read_text()
        test_file.unlink()
        
        return HealthCheckResult(
            name="file_system",
            status=HealthStatus.HEALTHY,
            message="File system is accessible",
            details={"path": str(path.absolute())},
        )
    except Exception as e:
        return HealthCheckResult(
            name="file_system",
            status=HealthStatus.UNHEALTHY,
            message=f"File system check failed: {str(e)}",
        )


def check_memory_usage(
    threshold_percent: float = 90.0,
) -> HealthCheckResult:
    """
    检查内存使用情况
    
    Args:
        threshold_percent: 阈值百分比
    
    Returns:
        检查结果
    """
    try:
        import psutil
        
        memory = psutil.virtual_memory()
        percent_used = memory.percent
        
        if percent_used >= threshold_percent:
            return HealthCheckResult(
                name="memory",
                status=HealthStatus.DEGRADED,
                message=f"Memory usage high: {percent_used:.1f}%",
                details={
                    "percent_used": percent_used,
                    "threshold": threshold_percent,
                },
            )
        
        return HealthCheckResult(
            name="memory",
            status=HealthStatus.HEALTHY,
            message=f"Memory usage normal: {percent_used:.1f}%",
            details={
                "total_gb": memory.total / (1024**3),
                "available_gb": memory.available / (1024**3),
                "percent_used": percent_used,
            },
        )
    except ImportError:
        return HealthCheckResult(
            name="memory",
            status=HealthStatus.DEGRADED,
            message="psutil not installed, cannot check memory",
        )
    except Exception as e:
        return HealthCheckResult(
            name="memory",
            status=HealthStatus.UNHEALTHY,
            message=f"Memory check failed: {str(e)}",
        )


# 全局健康检查器
_health_checker: Optional[HealthChecker] = None
_hc_lock = threading.Lock()


def get_health_checker(version: str = "1.0.0") -> HealthChecker:
    """获取全局健康检查器"""
    global _health_checker
    if _health_checker is None:
        with _hc_lock:
            if _health_checker is None:
                _health_checker = HealthChecker(version=version)
    return _health_checker
