"""
性能监控日志工具

V1.0版本
创建日期: 2026-03-24

特性:
- API调用耗时监控
- 缓存命中率统计
- 性能指标上报
- 慢操作告警
"""

import logging
import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """性能指标"""
    # API调用统计
    api_calls: int = 0
    api_total_time: float = 0.0
    api_errors: int = 0
    api_avg_time: float = 0.0
    
    # 缓存统计
    cache_hits: int = 0
    cache_misses: int = 0
    cache_hit_rate: float = 0.0
    
    # 慢操作统计
    slow_operations: int = 0
    slowest_operation_time: float = 0.0
    
    # 时间戳
    last_updated: datetime = field(default_factory=datetime.now)
    
    def update_api_stats(self, duration: float, is_error: bool = False) -> None:
        """更新API统计"""
        self.api_calls += 1
        self.api_total_time += duration
        if is_error:
            self.api_errors += 1
        self.api_avg_time = self.api_total_time / self.api_calls
        self.last_updated = datetime.now()
    
    def update_cache_stats(self, hits: int, misses: int) -> None:
        """更新缓存统计"""
        self.cache_hits = hits
        self.cache_misses = misses
        total = hits + misses
        self.cache_hit_rate = hits / total if total > 0 else 0.0
        self.last_updated = datetime.now()
    
    def record_slow_operation(self, duration: float) -> None:
        """记录慢操作"""
        self.slow_operations += 1
        if duration > self.slowest_operation_time:
            self.slowest_operation_time = duration
        self.last_updated = datetime.now()


class PerformanceMonitor:
    """
    性能监控器
    
    提供API调用监控、缓存统计、慢操作告警等功能。
    """
    
    def __init__(
        self,
        cache_manager: Optional[Any] = None,
        slow_threshold: float = 1.0,
        log_interval: int = 60
    ):
        """
        初始化性能监控器
        
        Args:
            cache_manager: 缓存管理器实例
            slow_threshold: 慢操作阈值（秒）
            log_interval: 日志记录间隔（秒）
        """
        self._cache_manager = cache_manager
        self._slow_threshold = slow_threshold
        self._log_interval = log_interval
        self._lock = threading.Lock()
        
        # 性能指标
        self._metrics = PerformanceMetrics()
        
        # 上次日志记录时间
        self._last_log_time = time.time()
        
        # 慢操作回调
        self._slow_operation_callbacks: List[Callable[[str, float], None]] = []
    
    def register_slow_callback(self, callback: Callable[[str, float], None]) -> None:
        """注册慢操作回调"""
        self._slow_operation_callbacks.append(callback)
    
    @contextmanager
    def track_api_call(self, operation_name: str):
        """
        追踪API调用耗时
        
        Args:
            operation_name: 操作名称
            
        Yields:
            None
        """
        start_time = time.time()
        is_error = False
        
        try:
            yield
        except Exception as e:
            is_error = True
            logger.error(f"API调用失败: {operation_name}, 错误: {e}")
            raise
        finally:
            duration = time.time() - start_time
            
            with self._lock:
                self._metrics.update_api_stats(duration, is_error)
            
            # 记录API调用日志
            logger.info(
                f"[PerformanceMonitor] API调用: {operation_name}, "
                f"耗时={duration:.3f}s, "
                f"状态={'失败' if is_error else '成功'}"
            )
            
            # 慢操作检测
            if duration > self._slow_threshold:
                self._handle_slow_operation(operation_name, duration)
            
            # 定期记录性能摘要
            self._maybe_log_summary()
    
    def _handle_slow_operation(self, operation_name: str, duration: float) -> None:
        """处理慢操作"""
        with self._lock:
            self._metrics.record_slow_operation(duration)
        
        # 记录告警日志
        logger.warning(
            f"[PerformanceMonitor] 慢操作告警: {operation_name}, "
            f"耗时={duration:.3f}s, 阈值={self._slow_threshold}s"
        )
        
        # 触发回调
        for callback in self._slow_operation_callbacks:
            try:
                callback(operation_name, duration)
            except Exception as e:
                logger.error(f"慢操作回调执行失败: {e}")
    
    def _maybe_log_summary(self) -> None:
        """定期记录性能摘要"""
        current_time = time.time()
        
        if current_time - self._last_log_time >= self._log_interval:
            self._last_log_time = current_time
            self.log_summary()
    
    def log_summary(self) -> None:
        """记录性能摘要日志"""
        # 更新缓存统计
        if self._cache_manager:
            try:
                stats = self._cache_manager.get_stats()
                global_stats = stats.get("global", {})
                self._metrics.update_cache_stats(
                    global_stats.get("total_hits", 0),
                    global_stats.get("total_misses", 0)
                )
            except Exception as e:
                logger.warning(f"获取缓存统计失败: {e}")
        
        # 输出摘要
        with self._lock:
            m = self._metrics
            
            logger.info(
                f"[PerformanceMonitor] 性能摘要: "
                f"API调用={m.api_calls}(avg={m.api_avg_time:.3f}s, err={m.api_errors}), "
                f"缓存命中率={m.cache_hit_rate:.1%}(hits={m.cache_hits}, misses={m.cache_misses}), "
                f"慢操作={m.slow_operations}(最慢={m.slowest_operation_time:.3f}s)"
            )
    
    def get_metrics(self) -> PerformanceMetrics:
        """获取性能指标"""
        with self._lock:
            # 返回副本
            return PerformanceMetrics(
                api_calls=self._metrics.api_calls,
                api_total_time=self._metrics.api_total_time,
                api_errors=self._metrics.api_errors,
                api_avg_time=self._metrics.api_avg_time,
                cache_hits=self._metrics.cache_hits,
                cache_misses=self._metrics.cache_misses,
                cache_hit_rate=self._metrics.cache_hit_rate,
                slow_operations=self._metrics.slow_operations,
                slowest_operation_time=self._metrics.slowest_operation_time,
                last_updated=self._metrics.last_updated
            )
    
    def reset(self) -> None:
        """重置性能指标"""
        with self._lock:
            self._metrics = PerformanceMetrics()
        logger.info("[PerformanceMonitor] 性能指标已重置")


# 全局实例
_performance_monitor: Optional[PerformanceMonitor] = None
_monitor_lock = threading.Lock()


def get_performance_monitor(
    cache_manager: Optional[Any] = None,
    slow_threshold: float = 1.0,
    log_interval: int = 60
) -> PerformanceMonitor:
    """
    获取全局性能监控器实例
    
    Args:
        cache_manager: 缓存管理器实例
        slow_threshold: 慢操作阈值
        log_interval: 日志记录间隔
        
    Returns:
        性能监控器实例
    """
    global _performance_monitor
    
    if _performance_monitor is None:
        with _monitor_lock:
            if _performance_monitor is None:
                if cache_manager is None:
                    try:
                        from core.cache_manager import get_cache_manager
                        cache_manager = get_cache_manager()
                    except Exception:
                        pass
                
                _performance_monitor = PerformanceMonitor(
                    cache_manager=cache_manager,
                    slow_threshold=slow_threshold,
                    log_interval=log_interval
                )
    
    return _performance_monitor


__all__ = [
    "PerformanceMetrics",
    "PerformanceMonitor",
    "get_performance_monitor",
]
