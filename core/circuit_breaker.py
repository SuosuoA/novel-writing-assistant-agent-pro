"""
熔断器 - 故障自动恢复

V1.2新增模块
创建日期：2026-03-21

特性：
- CLOSED→OPEN→HALF_OPEN→CLOSED状态转换
- 故障阈值可配置
- 自动恢复探测
"""

import threading
import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class CircuitState(str, Enum):
    """熔断器状态"""
    CLOSED = "CLOSED"      # 正常状态
    OPEN = "OPEN"          # 熔断状态
    HALF_OPEN = "HALF_OPEN"  # 半开状态（探测恢复）


class CircuitBreaker:
    """
    熔断器 - 故障自动恢复
    
    状态转换：
    - CLOSED → OPEN：失败次数超过阈值
    - OPEN → HALF_OPEN：冷却时间到期
    - HALF_OPEN → CLOSED：探测成功
    - HALF_OPEN → OPEN：探测失败
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        timeout: float = 60.0,
        name: str = "default"
    ):
        """
        初始化熔断器
        
        Args:
            failure_threshold: 失败阈值（触发熔断）
            success_threshold: 成功阈值（解除熔断）
            timeout: 冷却时间（秒）
            name: 熔断器名称
        """
        self._name = name
        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._timeout = timeout
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        
        self._lock = threading.RLock()
        self._listeners: List[Callable[[CircuitState, CircuitState], None]] = []
    
    @property
    def state(self) -> CircuitState:
        """获取当前状态"""
        with self._lock:
            self._check_timeout()
            return self._state
    
    @property
    def name(self) -> str:
        """获取熔断器名称"""
        return self._name
    
    def can_execute(self) -> bool:
        """
        检查是否可以执行
        
        Returns:
            是否允许执行
        """
        with self._lock:
            self._check_timeout()
            return self._state != CircuitState.OPEN
    
    def record_success(self) -> None:
        """记录成功"""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                
                if self._success_count >= self._success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            
            elif self._state == CircuitState.CLOSED:
                # 重置失败计数
                self._failure_count = 0
    
    def record_failure(self) -> None:
        """记录失败"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                # 探测失败，回到OPEN状态
                self._transition_to(CircuitState.OPEN)
            
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self._failure_threshold:
                    self._transition_to(CircuitState.OPEN)
    
    def reset(self) -> None:
        """重置熔断器"""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
    
    def add_listener(
        self,
        listener: Callable[[CircuitState, CircuitState], None]
    ) -> None:
        """
        添加状态变更监听器
        
        Args:
            listener: 监听器函数 (old_state, new_state) -> None
        """
        with self._lock:
            self._listeners.append(listener)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            return {
                "name": self._name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "failure_threshold": self._failure_threshold,
                "success_threshold": self._success_threshold,
                "timeout": self._timeout,
                "last_failure_time": self._last_failure_time
            }
    
    def _check_timeout(self) -> None:
        """检查冷却时间"""
        if (
            self._state == CircuitState.OPEN and
            self._last_failure_time and
            time.time() - self._last_failure_time >= self._timeout
        ):
            self._transition_to(CircuitState.HALF_OPEN)
    
    def _transition_to(self, new_state: CircuitState) -> None:
        """
        状态转换
        
        Args:
            new_state: 新状态
        """
        old_state = self._state
        self._state = new_state
        
        # 重置计数器
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
        
        # 通知监听器
        for listener in self._listeners:
            try:
                listener(old_state, new_state)
            except Exception:
                pass


class CircuitBreakerManager:
    """
    熔断器管理器
    
    管理多个命名熔断器
    """
    
    def __init__(self):
        """初始化管理器"""
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.RLock()
    
    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        timeout: float = 60.0
    ) -> CircuitBreaker:
        """
        获取或创建熔断器
        
        Args:
            name: 熔断器名称
            failure_threshold: 失败阈值
            success_threshold: 成功阈值
            timeout: 冷却时间
        
        Returns:
            熔断器实例
        """
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(
                    name=name,
                    failure_threshold=failure_threshold,
                    success_threshold=success_threshold,
                    timeout=timeout
                )
            return self._breakers[name]
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """
        获取熔断器
        
        Args:
            name: 熔断器名称
        
        Returns:
            熔断器实例或None
        """
        with self._lock:
            return self._breakers.get(name)
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有熔断器统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            return {
                name: breaker.get_stats()
                for name, breaker in self._breakers.items()
            }
    
    def reset_all(self) -> None:
        """重置所有熔断器"""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()


# 全局管理器
_manager_instance: Optional[CircuitBreakerManager] = None
_manager_lock = threading.Lock()


def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """获取全局熔断器管理器"""
    global _manager_instance
    if _manager_instance is None:
        with _manager_lock:
            if _manager_instance is None:
                _manager_instance = CircuitBreakerManager()
    return _manager_instance
