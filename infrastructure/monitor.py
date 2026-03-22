"""
性能监控与指标采集

V1.0版本
创建日期: 2026-03-21

特性：
- 指标采集（计数器、仪表、直方图）
- 性能监控（响应时间、吞吐量）
- 资源使用监控（内存、CPU）
"""

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import statistics


@dataclass
class MetricValue:
    """指标值"""
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class HistogramData:
    """
    直方图数据

    P1-9修复：添加容量限制，防止内存无界增长
    """
    values: List[float] = field(default_factory=list)
    max_size: int = 10000  # P1-9修复：最大保留样本数
    count: int = 0  # 总计数（包含已清理的样本）
    sum: float = 0.0
    min: float = float('inf')
    max: float = float('-inf')

    def add(self, value: float) -> None:
        """
        添加值

        P1-9修复：超过max_size时使用滑动窗口清理最老的10%数据
        """
        # P1-9修复：容量限制检查
        if len(self.values) >= self.max_size:
            # 滑动窗口：移除最老的10%
            trim_count = self.max_size // 10
            self.values = self.values[trim_count:]

        self.values.append(value)
        self.count += 1
        self.sum += value
        self.min = min(self.min, value)
        self.max = max(self.max, value)
    
    def get_percentile(self, p: float) -> float:
        """计算百分位数"""
        if not self.values:
            return 0.0
        sorted_values = sorted(self.values)
        index = int(len(sorted_values) * p / 100)
        return sorted_values[min(index, len(sorted_values) - 1)]
    
    def get_mean(self) -> float:
        """计算平均值"""
        if self.count == 0:
            return 0.0
        return self.sum / self.count


class MetricsCollector:
    """
    指标采集器
    
    支持三种指标类型：
    - Counter: 单调递增计数器
    - Gauge: 可增可减的仪表
    - Histogram: 值分布直方图
    """
    
    def __init__(self):
        """初始化指标采集器"""
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)
        self._histograms: Dict[str, HistogramData] = defaultdict(HistogramData)
        self._lock = threading.RLock()
        self._callbacks: List[Callable[[MetricValue], None]] = []
    
    def register_callback(self, callback: Callable[[MetricValue], None]) -> None:
        """注册指标变更回调"""
        self._callbacks.append(callback)
    
    def _notify(self, metric: MetricValue) -> None:
        """通知回调"""
        for callback in self._callbacks:
            try:
                callback(metric)
            except Exception:
                pass  # 忽略回调异常
    
    # Counter操作
    def increment(
        self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None
    ) -> None:
        """增加计数器"""
        with self._lock:
            self._counters[name] += value
            self._notify(MetricValue(name, self._counters[name], tags=tags or {}))
    
    def get_counter(self, name: str) -> float:
        """获取计数器值"""
        with self._lock:
            return self._counters.get(name, 0.0)
    
    # Gauge操作
    def set_gauge(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None
    ) -> None:
        """设置仪表值"""
        with self._lock:
            self._gauges[name] = value
            self._notify(MetricValue(name, value, tags=tags or {}))
    
    def get_gauge(self, name: str) -> float:
        """获取仪表值"""
        with self._lock:
            return self._gauges.get(name, 0.0)
    
    # Histogram操作
    def observe(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None
    ) -> None:
        """记录观测值"""
        with self._lock:
            self._histograms[name].add(value)
            self._notify(MetricValue(name, value, tags=tags or {}))
    
    def get_histogram(self, name: str) -> HistogramData:
        """获取直方图数据"""
        with self._lock:
            return self._histograms.get(name, HistogramData())
    
    # 统计信息
    def get_all_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        with self._lock:
            result = {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {},
            }
            
            for name, hist in self._histograms.items():
                result["histograms"][name] = {
                    "count": hist.count,
                    "sum": hist.sum,
                    "min": hist.min if hist.count > 0 else 0,
                    "max": hist.max if hist.count > 0 else 0,
                    "mean": hist.get_mean(),
                    "p50": hist.get_percentile(50),
                    "p90": hist.get_percentile(90),
                    "p99": hist.get_percentile(99),
                }
            
            return result
    
    def reset(self) -> None:
        """重置所有指标"""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


class PerformanceMonitor:
    """
    性能监控器

    提供以下功能：
    - 方法执行时间监控
    - 吞吐量监控
    - 慢操作告警
    - P1-10修复：慢操作频繁告警升级机制
    """

    # P1-10修复：慢操作频繁阈值
    SLOW_OPERATION_ALERT_THRESHOLD = 10

    def __init__(
        self,
        metrics_collector: Optional[MetricsCollector] = None,
        slow_threshold: float = 1.0,  # 秒
        event_bus: Optional[Any] = None,  # P1-10修复：添加event_bus参数
    ):
        """
        初始化性能监控器

        Args:
            metrics_collector: 指标采集器
            slow_threshold: 慢操作阈值（秒）
            event_bus: 事件总线实例（用于告警升级）
        """
        self._metrics = metrics_collector or MetricsCollector()
        self._slow_threshold = slow_threshold
        self._event_bus = event_bus  # P1-10修复
        self._active_operations: Dict[str, float] = {}
        self._lock = threading.Lock()
        # P1-10修复：慢操作计数器
        self._slow_operation_count: Dict[str, int] = defaultdict(int)
        # P1-10修复：慢操作平均耗时
        self._slow_operation_total: Dict[str, float] = defaultdict(float)
    
    def start_operation(self, operation_name: str) -> str:
        """
        开始操作
        
        Args:
            operation_name: 操作名称
        
        Returns:
            操作ID
        """
        op_id = f"{operation_name}_{time.time_ns()}"
        with self._lock:
            self._active_operations[op_id] = time.time()
        return op_id
    
    def end_operation(
        self, op_id: str, success: bool = True, tags: Optional[Dict[str, str]] = None
    ) -> float:
        """
        结束操作
        
        Args:
            op_id: 操作ID
            success: 是否成功
            tags: 标签
        
        Returns:
            操作耗时（秒）
        """
        end_time = time.time()
        
        with self._lock:
            start_time = self._active_operations.pop(op_id, None)
        
        if start_time is None:
            return 0.0
        
        duration = end_time - start_time
        operation_name = op_id.rsplit("_", 1)[0]
        
        # 记录指标
        self._metrics.observe(f"operation_duration_{operation_name}", duration, tags)
        self._metrics.increment(f"operation_count_{operation_name}")
        
        if not success:
            self._metrics.increment(f"operation_errors_{operation_name}")
        
        # 慢操作告警
        if duration > self._slow_threshold:
            self._metrics.increment(f"slow_operations_{operation_name}")

            # P1-10修复：慢操作频繁告警升级
            with self._lock:
                self._slow_operation_count[operation_name] += 1
                self._slow_operation_total[operation_name] += duration
                count = self._slow_operation_count[operation_name]

                # 达到频繁阈值时发布告警事件
                if count >= self.SLOW_OPERATION_ALERT_THRESHOLD:
                    avg_duration = self._slow_operation_total[operation_name] / count

                    # 记录ERROR级别日志
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(
                        f"慢操作频繁: {operation_name} 已连续 {count} 次超时, "
                        f"平均耗时 {avg_duration:.2f}s, 阈值 {self._slow_threshold}s"
                    )

                    # 发布告警事件
                    if self._event_bus:
                        try:
                            self._event_bus.publish(
                                "performance.slow_operation_frequent",
                                {
                                    "operation": operation_name,
                                    "count": count,
                                    "avg_duration": avg_duration,
                                    "threshold": self._slow_threshold,
                                    "last_duration": duration,
                                },
                                source="PerformanceMonitor"
                            )
                        except Exception as e:
                            logger.warning(f"发布慢操作告警事件失败: {e}")
                else:
                    # 未达阈值时记录WARNING日志
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"慢操作检测: {operation_name}, 耗时 {duration:.2f}s "
                        f"({count}/{self.SLOW_OPERATION_ALERT_THRESHOLD})"
                    )
        
        return duration
    
    def time_it(
        self, operation_name: str, tags: Optional[Dict[str, str]] = None
    ) -> "TimerContext":
        """
        计时上下文管理器
        
        用法:
            with monitor.time_it("my_operation"):
                # 执行操作
                pass
        """
        return TimerContext(self, operation_name, tags)
    
    def get_stats(self, operation_name: str) -> Dict[str, Any]:
        """获取操作统计信息"""
        return {
            "count": self._metrics.get_counter(f"operation_count_{operation_name}"),
            "errors": self._metrics.get_counter(f"operation_errors_{operation_name}"),
            "slow_count": self._metrics.get_counter(f"slow_operations_{operation_name}"),
            "duration_histogram": self._metrics.get_histogram(
                f"operation_duration_{operation_name}"
            ).get_mean(),
        }


class TimerContext:
    """计时上下文管理器"""
    
    def __init__(
        self,
        monitor: PerformanceMonitor,
        operation_name: str,
        tags: Optional[Dict[str, str]] = None,
    ):
        self._monitor = monitor
        self._operation_name = operation_name
        self._tags = tags
        self._op_id: Optional[str] = None
        self._success = True
    
    def __enter__(self) -> "TimerContext":
        self._op_id = self._monitor.start_operation(self._operation_name)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._success = exc_type is None
        if self._op_id:
            self._monitor.end_operation(self._op_id, self._success, self._tags)
    
    def fail(self) -> None:
        """标记操作失败"""
        self._success = False


# 全局实例
_metrics_collector: Optional[MetricsCollector] = None
_performance_monitor: Optional[PerformanceMonitor] = None
_infra_lock = threading.Lock()


def get_metrics_collector() -> MetricsCollector:
    """获取全局指标采集器"""
    global _metrics_collector
    if _metrics_collector is None:
        with _infra_lock:
            if _metrics_collector is None:
                _metrics_collector = MetricsCollector()
    return _metrics_collector


def get_performance_monitor() -> PerformanceMonitor:
    """获取全局性能监控器"""
    global _performance_monitor
    if _performance_monitor is None:
        with _infra_lock:
            if _performance_monitor is None:
                _performance_monitor = PerformanceMonitor(get_metrics_collector())
    return _performance_monitor
