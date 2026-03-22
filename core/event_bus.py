"""
事件总线 - 发布订阅机制

V1.2版本（最终修订版）
创建日期：2026-03-21

特性：
- ThreadPoolExecutor真异步发布
- 线程安全（RLock + 快照拷贝）
- 熔断器集成
- 死信队列
"""

import threading
import atexit
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime
from enum import IntEnum
import uuid

from .models import Event, HandlerInfo


class EventPriority(IntEnum):
    """事件优先级（数值越小优先级越高）"""

    HIGHEST = 0
    HIGH = 10
    NORMAL = 20
    LOW = 30
    LOWEST = 40


class DeadLetterQueue:
    """
    死信队列

    P1-6修复：添加自动清理和过期机制
    """

    # P1-6修复：默认过期时间（7天）
    DEFAULT_TTL_DAYS = 7
    DEFAULT_TTL_SECONDS = DEFAULT_TTL_DAYS * 24 * 60 * 60

    def __init__(self, max_size: int = 100, ttl_seconds: int = None):
        """
        初始化死信队列

        Args:
            max_size: 最大队列大小
            ttl_seconds: 过期时间（秒），None表示使用默认值
        """
        self._queue: List[Dict[str, Any]] = []
        self._max_size = max_size
        self._ttl = ttl_seconds or self.DEFAULT_TTL_SECONDS
        self._lock = threading.Lock()

        # P1-6修复：统计信息
        self._total_added = 0
        self._total_expired = 0

    def add(self, event: Event, error: Exception) -> None:
        """
        添加失败事件到死信队列

        Args:
            event: 事件对象
            error: 异常对象
        """
        with self._lock:
            # P1-6修复：添加前先清理过期项
            self._cleanup_expired_unlocked()

            if len(self._queue) >= self._max_size:
                # 移除最旧的
                removed = self._queue.pop(0)
                self._total_expired += 1

            self._queue.append(
                {
                    "event": event.model_dump(),
                    "error": str(error),
                    "timestamp": datetime.now().isoformat(),
                    "event_type": event.type,
                }
            )
            self._total_added += 1

    def get_all(self) -> List[Dict[str, Any]]:
        """获取所有死信"""
        with self._lock:
            return list(self._queue)

    def get_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        """
        P1-6修复：按事件类型获取死信

        Args:
            event_type: 事件类型

        Returns:
            该类型的死信列表
        """
        with self._lock:
            return [
                item for item in self._queue
                if item.get("event_type") == event_type
            ]

    def cleanup_expired(self) -> int:
        """
        P1-6修复：清理过期的死信

        Returns:
            清理的数量
        """
        with self._lock:
            return self._cleanup_expired_unlocked()

    def _cleanup_expired_unlocked(self) -> int:
        """
        清理过期的死信（内部方法，不获取锁）

        Returns:
            清理的数量
        """
        import time

        current_time = datetime.now().timestamp()
        original_size = len(self._queue)

        self._queue = [
            item for item in self._queue
            if current_time - datetime.fromisoformat(item["timestamp"]).timestamp() < self._ttl
        ]

        removed = original_size - len(self._queue)
        self._total_expired += removed

        return removed

    def clear(self) -> None:
        """清空死信队列"""
        with self._lock:
            self._total_expired += len(self._queue)
            self._queue.clear()

    def get_stats(self) -> Dict[str, Any]:
        """
        P1-6修复：获取死信队列统计信息

        Returns:
            统计信息字典
        """
        with self._lock:
            # 按事件类型统计
            by_type: Dict[str, int] = {}
            for item in self._queue:
                event_type = item.get("event_type", "unknown")
                by_type[event_type] = by_type.get(event_type, 0) + 1

            return {
                "current_size": len(self._queue),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl,
                "total_added": self._total_added,
                "total_expired": self._total_expired,
                "by_type": by_type,
            }


class EventBus:
    """
    事件总线 - 线程安全的发布订阅机制

    V1.2特性：
    - ThreadPoolExecutor真异步发布
    - 熔断器集成（失败次数过多自动熔断）
    - 死信队列（失败事件存储）
    """

    def __init__(self, max_workers: int = 10, circuit_threshold: int = 5):
        """
        初始化事件总线

        Args:
            max_workers: 线程池最大工作线程数
            circuit_threshold: 熔断阈值（单个handler失败次数）
        """
        self._handlers: Dict[str, List[HandlerInfo]] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        # 熔断器状态
        self._failure_counts: Dict[str, int] = {}
        self._circuit_broken: Dict[str, bool] = {}
        self._circuit_threshold = circuit_threshold

        # 死信队列
        self._dead_letter_queue = DeadLetterQueue()

        # 注册清理函数
        atexit.register(self.shutdown)

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], Any],
        handler_id: Optional[str] = None,
        priority: EventPriority = EventPriority.NORMAL,
        is_async: bool = False,
        timeout: float = 30.0,
    ) -> str:
        """
        订阅事件

        Args:
            event_type: 事件类型
            handler: 处理函数
            handler_id: 处理器ID（不提供则自动生成）
            priority: 优先级
            is_async: 是否异步执行
            timeout: 超时时间

        Returns:
            订阅ID
        """
        if handler_id is None:
            handler_id = f"{event_type}_{uuid.uuid4().hex[:8]}"

        handler_info = HandlerInfo(
            id=handler_id,
            handler=handler,
            priority=priority,
            is_async=is_async,
            timeout=timeout,
        )

        with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler_info)

        return handler_id

    def subscribe_once(
        self,
        event_type: str,
        handler: Callable[[Event], Any],
        handler_id: Optional[str] = None,
    ) -> str:
        """
        一次性订阅（触发后自动取消）

        Args:
            event_type: 事件类型
            handler: 处理函数
            handler_id: 处理器ID

        Returns:
            订阅ID
        """
        if handler_id is None:
            handler_id = f"{event_type}_once_{uuid.uuid4().hex[:8]}"

        def wrapper(event: Event):
            try:
                handler(event)
            finally:
                self.unsubscribe(handler_id)

        return self.subscribe(event_type, wrapper, handler_id)

    def unsubscribe(self, subscription_id: str) -> bool:
        """
        取消订阅

        Args:
            subscription_id: 订阅ID

        Returns:
            是否成功取消
        """
        with self._lock:
            for event_type, handlers in self._handlers.items():
                for i, handler_info in enumerate(handlers):
                    if handler_info.id == subscription_id:
                        handlers.pop(i)
                        return True
        return False

    def publish(
        self, event_type: str, data: Any = None, source: Optional[str] = None
    ) -> None:
        """
        发布事件 - 真异步，使用线程池执行

        实现细节：
        1. 创建Event对象
        2. 在锁内拷贝handlers快照
        3. 提交到ThreadPoolExecutor异步执行
        4. 立即返回，不阻塞调用线程

        线程安全：所有写操作使用 threading.RLock
        """
        event = Event(
            type=event_type,
            data=data,
            source=source,
            timestamp=datetime.now().timestamp(),
            event_id=uuid.uuid4().hex,
        )

        # 1. 在锁内拷贝handlers快照（读拷贝模式）
        with self._lock:
            handlers = list(self._handlers.get(event_type, []))

        # 2. 提交到线程池异步执行（不阻塞调用线程）
        if handlers:
            self._executor.submit(self._dispatch_event, event, handlers)

        # 3. 立即返回，调用线程不被阻塞

    def publish_sync(
        self,
        event_type: str,
        data: Any = None,
        source: Optional[str] = None,
        timeout: float = 30.0,
    ) -> List[Any]:
        """
        同步发布事件（阻塞等待所有handler执行完成）

        Args:
            event_type: 事件类型
            data: 事件数据
            source: 事件来源
            timeout: 超时时间

        Returns:
            各handler执行结果列表
        """
        event = Event(
            type=event_type,
            data=data,
            source=source,
            timestamp=datetime.now().timestamp(),
            event_id=uuid.uuid4().hex,
        )

        with self._lock:
            handlers = list(self._handlers.get(event_type, []))

        results = []
        if handlers:
            results = self._dispatch_event_sync(event, handlers, timeout)

        return results

    def publish_batch(self, events: List[Dict[str, Any]]) -> None:
        """
        批量发布事件

        Args:
            events: 事件列表 [{"type": str, "data": Any, "source": str}, ...]
        """
        for event_dict in events:
            self.publish(
                event_type=event_dict.get("type"),
                data=event_dict.get("data"),
                source=event_dict.get("source"),
            )

    def _dispatch_event(self, event: Event, handlers: List[HandlerInfo]) -> None:
        """
        在线程池中分发事件（异步执行）

        Args:
            event: 事件对象
            handlers: 处理器信息列表
        """
        # 按优先级排序（数值越小越先执行）
        sorted_handlers = sorted(handlers, key=lambda h: h.priority)

        for handler_info in sorted_handlers:
            # 检查熔断状态
            if self._is_circuit_broken(handler_info.id):
                continue

            try:
                if handler_info.is_async:
                    # 异步handler在独立线程中执行
                    self._executor.submit(self._execute_handler, handler_info, event)
                else:
                    # 同步handler直接执行
                    self._execute_handler(handler_info, event)

            except Exception as e:
                self._handle_handler_error(event, handler_info, e)

    def _dispatch_event_sync(
        self, event: Event, handlers: List[HandlerInfo], timeout: float
    ) -> List[Any]:
        """
        同步分发事件

        Args:
            event: 事件对象
            handlers: 处理器列表
            timeout: 超时时间

        Returns:
            执行结果列表
        """
        sorted_handlers = sorted(handlers, key=lambda h: h.priority)
        results = []

        for handler_info in sorted_handlers:
            if self._is_circuit_broken(handler_info.id):
                continue

            try:
                result = handler_info.handler(event)
                results.append(result)
                self._reset_failure_count(handler_info.id)
            except Exception as e:
                self._handle_handler_error(event, handler_info, e)
                results.append(None)

        return results

    def _execute_handler(self, handler_info: HandlerInfo, event: Event) -> Any:
        """执行单个handler"""
        try:
            result = handler_info.handler(event)
            self._reset_failure_count(handler_info.id)
            return result
        except Exception as e:
            self._handle_handler_error(event, handler_info, e)
            raise

    def _handle_handler_error(
        self, event: Event, handler_info: HandlerInfo, error: Exception
    ) -> None:
        """
        处理handler执行异常

        P0-1修复：发布失败事件供监控系统感知

        Args:
            event: 事件对象
            handler_info: 处理器信息
            error: 异常对象
        """
        # 1. 记录错误日志（含完整堆栈）
        import logging

        logger = logging.getLogger(__name__)
        logger.error(
            f"EventBus handler error: "
            f"event_type={event.type}, "
            f"handler_id={handler_info.id}, "
            f"error={error}",
            exc_info=True,
            extra={
                "event_type": event.type,
                "event_data": str(event.data)[:200] if event.data else None,
                "handler_id": handler_info.id,
            }
        )

        # 2. 熔断器计数+1
        self._increment_failure_count(handler_info.id)

        # 3. 添加到死信队列
        self._dead_letter_queue.add(event, error)

        # 4. P0-1修复：发布失败事件供监控
        try:
            self.publish(
                f"{event.type}.callback_failed",
                {
                    "callback": handler_info.id,
                    "error": str(error),
                    "error_type": type(error).__name__,
                    "original_event": str(event.data)[:500] if event.data else None,
                },
                source="EventBus"
            )
        except Exception as publish_error:
            logger.warning(f"Failed to publish callback_failed event: {publish_error}")

    def _increment_failure_count(self, handler_id: str) -> None:
        """增加失败计数"""
        with self._lock:
            self._failure_counts[handler_id] = (
                self._failure_counts.get(handler_id, 0) + 1
            )

            # 检查是否达到熔断阈值
            if self._failure_counts[handler_id] >= self._circuit_threshold:
                self._circuit_broken[handler_id] = True

    def _reset_failure_count(self, handler_id: str) -> None:
        """重置失败计数"""
        with self._lock:
            self._failure_counts[handler_id] = 0
            self._circuit_broken[handler_id] = False

    def _is_circuit_broken(self, handler_id: str) -> bool:
        """检查是否熔断"""
        with self._lock:
            return self._circuit_broken.get(handler_id, False)

    def reset_circuit(self, handler_id: str) -> None:
        """
        重置熔断器

        Args:
            handler_id: 处理器ID
        """
        self._reset_failure_count(handler_id)

    def get_handler_count(self, event_type: str) -> int:
        """
        获取事件类型的处理器数量

        Args:
            event_type: 事件类型

        Returns:
            处理器数量
        """
        with self._lock:
            return len(self._handlers.get(event_type, []))

    def list_event_types(self) -> List[str]:
        """
        列出所有事件类型

        Returns:
            事件类型列表
        """
        with self._lock:
            return list(self._handlers.keys())

    def get_dead_letter_queue(self) -> List[Dict[str, Any]]:
        """获取死信队列内容"""
        return self._dead_letter_queue.get_all()

    def get_dead_letter_stats(self) -> Dict[str, Any]:
        """
        P1-6修复：获取死信队列统计信息

        Returns:
            统计信息字典
        """
        return self._dead_letter_queue.get_stats()

    def cleanup_dead_letters(self) -> int:
        """
        P1-6修复：清理过期的死信

        Returns:
            清理的数量
        """
        return self._dead_letter_queue.cleanup_expired()

    def clear_dead_letters(self) -> None:
        """P1-6修复：清空死信队列"""
        self._dead_letter_queue.clear()

    def shutdown(self) -> None:
        """优雅关闭线程池"""
        import sys
        if sys.version_info >= (3, 9):
            self._executor.shutdown(wait=True, cancel_futures=False)
        else:
            self._executor.shutdown(wait=True)


# 全局单例
_event_bus_instance: Optional[EventBus] = None
_event_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """获取全局EventBus实例"""
    global _event_bus_instance
    if _event_bus_instance is None:
        with _event_bus_lock:
            if _event_bus_instance is None:
                _event_bus_instance = EventBus()
    return _event_bus_instance
