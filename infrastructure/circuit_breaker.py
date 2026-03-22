"""
熔断器模块

V1.0版本
创建日期: 2026-03-21

特性：
- 熔断状态机（关闭/打开/半开）
- 自动恢复
- 线程安全
"""

import time
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional
from functools import wraps


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 关闭（正常）
    OPEN = "open"          # 打开（熔断）
    HALF_OPEN = "half_open"  # 半开（试探）


class CircuitBreakerError(Exception):
    """熔断器异常"""
    pass


@dataclass
class CircuitStats:
    """熔断器统计信息"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    last_failure_time: Optional[float] = None
    last_failure_exception: Optional[Exception] = None
    consecutive_failures: int = 0
    state_changed_at: float = field(default_factory=time.time)


class CircuitBreaker:
    """
    熔断器
    
    状态转换：
    CLOSED -> OPEN: 连续失败次数达到阈值
    OPEN -> HALF_OPEN: 冷却时间过后
    HALF_OPEN -> CLOSED: 试探成功
    HALF_OPEN -> OPEN: 试探失败
    
    用法:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        
        # 方式1：装饰器
        @breaker
        def my_function():
            # 可能失败的操作
            pass
        
        # 方式2：上下文管理器
        with breaker:
            my_function()
        
        # 方式3：手动调用
        try:
            result = breaker.call(my_function)
        except CircuitBreakerError:
            # 熔断器打开
            pass
    """
    
    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        expected_exceptions: tuple = (Exception,),
    ):
        """
        初始化熔断器
        
        Args:
            name: 熔断器名称
            failure_threshold: 失败阈值
            recovery_timeout: 恢复超时时间（秒）
            half_open_max_calls: 半开状态最大试探次数
            expected_exceptions: 预期的异常类型
        """
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._expected_exceptions = expected_exceptions
        
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._lock = threading.RLock()
        self._half_open_calls = 0
        
        # 回调
        self._on_state_change: Optional[Callable[[CircuitState, CircuitState], None]] = None
        self._on_failure: Optional[Callable[[Exception], None]] = None
        self._fallback: Optional[Callable[..., Any]] = None
    
    def set_on_state_change(
        self, callback: Callable[[CircuitState, CircuitState], None]
    ) -> None:
        """设置状态变更回调"""
        self._on_state_change = callback
    
    def set_on_failure(self, callback: Callable[[Exception], None]) -> None:
        """设置失败回调"""
        self._on_failure = callback
    
    def set_fallback(self, fallback: Callable[..., Any]) -> None:
        """设置降级函数"""
        self._fallback = fallback
    
    @property
    def state(self) -> CircuitState:
        """当前状态"""
        with self._lock:
            self._check_state_transition()
            return self._state
    
    @property
    def stats(self) -> CircuitStats:
        """统计信息"""
        with self._lock:
            return self._stats
    
    def _check_state_transition(self) -> None:
        """检查状态转换（内部方法，需在锁内调用）"""
        if self._state == CircuitState.OPEN:
            # 检查是否可以进入半开状态
            if self._stats.last_failure_time is not None:
                elapsed = time.time() - self._stats.last_failure_time
                if elapsed >= self._recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
    
    def _transition_to(self, new_state: CircuitState) -> None:
        """状态转换（内部方法，需在锁内调用）"""
        old_state = self._state
        self._state = new_state
        self._stats.state_changed_at = time.time()
        
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
        
        # 回调通知
        if self._on_state_change:
            try:
                self._on_state_change(old_state, new_state)
            except Exception:
                pass
    
    def can_execute(self) -> bool:
        """检查是否可以执行"""
        with self._lock:
            self._check_state_transition()
            
            if self._state == CircuitState.CLOSED:
                return True
            elif self._state == CircuitState.HALF_OPEN:
                return self._half_open_calls < self._half_open_max_calls
            else:  # OPEN
                return False
    
    def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        执行函数
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数
        
        Returns:
            函数执行结果
        
        Raises:
            CircuitBreakerError: 熔断器打开
        """
        with self._lock:
            self._check_state_transition()
            
            if self._state == CircuitState.OPEN:
                if self._fallback:
                    return self._fallback(*args, **kwargs)
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is open"
                )
            
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self._half_open_max_calls:
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self.name}' is in half-open state "
                        f"and has reached max calls"
                    )
                self._half_open_calls += 1
        
        # 执行函数
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self._expected_exceptions as e:
            self._on_failure(e)
            raise
    
    def _on_success(self) -> None:
        """成功回调"""
        with self._lock:
            self._stats.total_calls += 1
            self._stats.successful_calls += 1
            self._stats.consecutive_failures = 0
            
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.CLOSED)
    
    def _on_failure(self, error: Exception) -> None:
        """失败回调"""
        with self._lock:
            self._stats.total_calls += 1
            self._stats.failed_calls += 1
            self._stats.consecutive_failures += 1
            self._stats.last_failure_time = time.time()
            self._stats.last_failure_exception = error
            
            # 回调通知
            if self._on_failure:
                try:
                    self._on_failure(error)
                except Exception:
                    pass
            
            # 状态转换
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif self._stats.consecutive_failures >= self._failure_threshold:
                self._transition_to(CircuitState.OPEN)
    
    def reset(self) -> None:
        """重置熔断器"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._stats = CircuitStats()
            self._half_open_calls = 0
    
    def force_open(self) -> None:
        """强制打开熔断器"""
        with self._lock:
            self._transition_to(CircuitState.OPEN)
            self._stats.last_failure_time = time.time()
    
    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """装饰器用法"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)
        return wrapper
    
    def __enter__(self) -> "CircuitBreaker":
        """上下文管理器入口"""
        if not self.can_execute():
            if self._fallback:
                return self
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is open"
            )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        if exc_type and issubclass(exc_type, self._expected_exceptions):
            self._on_failure(exc_val)
        elif exc_type is None:
            self._on_success()


# 全局熔断器注册表
_circuit_breakers: Dict[str, CircuitBreaker] = {}
_cb_lock = threading.Lock()


def get_circuit_breaker(
    name: str = "default",
    **kwargs
) -> CircuitBreaker:
    """
    获取或创建熔断器
    
    Args:
        name: 熔断器名称
        **kwargs: 熔断器配置参数
    
    Returns:
        CircuitBreaker实例
    """
    with _cb_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(name=name, **kwargs)
        return _circuit_breakers[name]
