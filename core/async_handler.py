"""
异步事件处理器 - UI线程安全的后台任务执行

V1.0版本
创建日期：2026-03-21

特性：
- 优先级任务队列
- 工作线程池（可配置3-5个）
- 结果回调在主线程执行（使用root.after）
- 任务取消和超时控制
- 与EventBus集成
"""

import threading
import queue
import uuid
import atexit
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from concurrent.futures import Future, ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)


class TaskPriority(IntEnum):
    """任务优先级（数值越小优先级越高）"""

    HIGHEST = 0  # 立即执行
    HIGH = 10  # 高优先级
    NORMAL = 20  # 普通优先级
    LOW = 30  # 低优先级
    BACKGROUND = 40  # 后台任务


class TaskState(IntEnum):
    """任务状态"""

    PENDING = 0  # 等待执行
    RUNNING = 1  # 正在执行
    COMPLETED = 2  # 执行完成
    FAILED = 3  # 执行失败
    CANCELLED = 4  # 已取消
    TIMEOUT = 5  # 超时


@dataclass
class Task:
    """
    异步任务

    Attributes:
        id: 任务唯一ID
        func: 执行函数
        args: 位置参数
        kwargs: 关键字参数
        priority: 优先级
        callback: 成功回调（在主线程执行）
        error_callback: 错误回调（在主线程执行）
        timeout: 超时时间（秒）
        created_at: 创建时间
        state: 任务状态
        result: 执行结果
        error: 错误信息
    """

    id: str
    func: Callable
    args: Tuple = field(default_factory=tuple)
    kwargs: Dict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    callback: Optional[Callable[[Any], None]] = None
    error_callback: Optional[Callable[[Exception], None]] = None
    timeout: float = 30.0
    created_at: float = field(default_factory=time.time)
    state: TaskState = TaskState.PENDING
    result: Any = None
    error: Optional[Exception] = None


class PriorityTaskQueue:
    """
    线程安全的优先级任务队列

    使用heapq实现优先级排序，同优先级按创建时间FIFO
    """

    def __init__(self):
        self._queue: List[Tuple[int, float, Task]] = []
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._counter = 0  # 用于同优先级FIFO排序

    def put(self, task: Task) -> None:
        """添加任务到队列"""
        with self._lock:
            self._counter += 1
            # 优先级 + 创建时间 + 序号（保证FIFO）
            entry = (task.priority, task.created_at, self._counter, task)
            self._queue.append(entry)
            # 按优先级排序
            self._queue.sort(key=lambda x: (x[0], x[1], x[2]))
            self._not_empty.notify()

    def get(self, timeout: Optional[float] = None) -> Optional[Task]:
        """
        获取优先级最高的任务

        Args:
            timeout: 超时时间（秒），None表示无限等待

        Returns:
            任务对象，如果超时返回None
        """
        with self._not_empty:
            if not self._queue:
                if not self._not_empty.wait(timeout):
                    return None

            if not self._queue:
                return None

            # 取出优先级最高的任务
            _, _, _, task = self._queue.pop(0)
            return task

    def peek(self) -> Optional[Task]:
        """查看优先级最高的任务但不移除"""
        with self._lock:
            if not self._queue:
                return None
            return self._queue[0][3]

    def qsize(self) -> int:
        """获取队列大小"""
        with self._lock:
            return len(self._queue)

    def clear(self) -> int:
        """清空队列，返回清除的任务数"""
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            return count

    def get_all_tasks(self) -> List[Task]:
        """获取所有任务（按优先级排序）"""
        with self._lock:
            return [entry[3] for entry in self._queue]


class AsyncHandler:
    """
    异步事件处理器

    功能：
    1. 优先级任务队列：按优先级顺序执行任务
    2. 工作线程池：可配置3-5个工作线程
    3. 主线程回调：使用root.after在主线程执行回调
    4. 任务管理：支持取消、超时、状态跟踪

    使用示例：
    ```python
    # 初始化（需要传入Tk root窗口）
    handler = AsyncHandler(root=tk_root, worker_count=4)

    # 提交任务
    task_id = handler.submit(
        func=long_running_task,
        args=(arg1, arg2),
        callback=on_success,
        error_callback=on_error,
        priority=TaskPriority.HIGH
    )

    # 取消任务
    handler.cancel(task_id)
    ```
    """

    def __init__(
        self,
        root: Any = None,
        worker_count: int = 4,
        default_timeout: float = 30.0,
    ):
        """
        初始化异步处理器

        Args:
            root: Tkinter root窗口（用于root.after回调）
            worker_count: 工作线程数（推荐3-5个）
            default_timeout: 默认超时时间（秒）
        """
        self._root = root
        self._worker_count = max(1, min(worker_count, 10))  # 限制1-10个
        self._default_timeout = default_timeout

        # 优先级任务队列
        self._task_queue = PriorityTaskQueue()

        # 任务存储
        self._tasks: Dict[str, Task] = {}
        self._tasks_lock = threading.Lock()

        # 线程池
        self._executor = ThreadPoolExecutor(
            max_workers=self._worker_count,
            thread_name_prefix="AsyncHandler-",
        )

        # 运行状态
        self._running = False
        self._shutdown = False

        # 监控指标
        self._total_submitted = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_timeout = 0
        self._total_cancelled = 0
        self._monitor_lock = threading.Lock()

        # 启动工作线程
        self._start_workers()

        # 注册清理函数
        atexit.register(self.shutdown)

        logger.info(
            f"AsyncHandler initialized: workers={self._worker_count}, "
            f"timeout={default_timeout}s"
        )

    def _start_workers(self) -> None:
        """启动工作线程"""
        self._running = True
        for i in range(self._worker_count):
            thread = threading.Thread(
                target=self._worker_loop,
                name=f"AsyncHandler-Worker-{i}",
                daemon=True,
            )
            thread.start()

    def _worker_loop(self) -> None:
        """工作线程主循环"""
        while self._running:
            try:
                # 从队列获取任务（阻塞等待）
                task = self._task_queue.get(timeout=0.5)

                if task is None:
                    continue

                # 检查任务是否已取消
                if task.state == TaskState.CANCELLED:
                    continue

                # 执行任务
                self._execute_task(task)

            except Exception as e:
                logger.error(f"Worker loop error: {e}")

    def _execute_task(self, task: Task) -> None:
        """
        执行单个任务

        Args:
            task: 任务对象
        """
        # 更新状态
        task.state = TaskState.RUNNING

        try:
            # 使用线程池执行
            future = self._executor.submit(task.func, *task.args, **task.kwargs)

            # 等待结果（带超时）
            result = future.result(timeout=task.timeout)

            # 成功完成
            task.result = result
            task.state = TaskState.COMPLETED

            # 更新监控指标
            with self._monitor_lock:
                self._total_completed += 1

            # 在主线程执行回调
            if task.callback:
                self._invoke_callback(task.callback, result)

        except TimeoutError:
            task.state = TaskState.TIMEOUT
            task.error = TimeoutError(
                f"Task {task.id} timed out after {task.timeout}s"
            )
            logger.warning(f"Task {task.id} timed out")

            # 更新监控指标
            with self._monitor_lock:
                self._total_timeout += 1

            if task.error_callback:
                self._invoke_callback(task.error_callback, task.error)

        except Exception as e:
            task.state = TaskState.FAILED
            task.error = e
            logger.error(f"Task {task.id} failed: {e}")

            # 更新监控指标
            with self._monitor_lock:
                self._total_failed += 1

            if task.error_callback:
                self._invoke_callback(task.error_callback, e)

    def _invoke_callback(self, callback: Callable, *args) -> None:
        """
        在主线程执行回调

        Args:
            callback: 回调函数
            *args: 回调参数
        """
        if self._root is None:
            # 没有root窗口，直接执行
            try:
                callback(*args)
            except Exception as e:
                logger.error(f"Callback error: {e}")
        else:
            # 使用root.after在主线程执行
            try:
                self._root.after(0, lambda: callback(*args))
            except Exception as e:
                logger.error(f"Failed to schedule callback: {e}")

    def submit(
        self,
        func: Callable,
        args: Tuple = (),
        kwargs: Optional[Dict] = None,
        task_id: Optional[str] = None,
        callback: Optional[Callable[[Any], None]] = None,
        error_callback: Optional[Callable[[Exception], None]] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout: Optional[float] = None,
    ) -> str:
        """
        提交异步任务

        Args:
            func: 执行函数
            args: 位置参数
            kwargs: 关键字参数
            task_id: 任务ID（不提供则自动生成）
            callback: 成功回调（在主线程执行）
            error_callback: 错误回调（在主线程执行）
            priority: 任务优先级
            timeout: 超时时间（秒）

        Returns:
            任务ID

        示例：
        ```python
        def long_task(n):
            import time
            time.sleep(n)
            return f"completed in {n}s"

        def on_success(result):
            print(f"成功: {result}")

        def on_error(error):
            print(f"失败: {error}")

        task_id = handler.submit(
            func=long_task,
            args=(5,),
            callback=on_success,
            error_callback=on_error,
            priority=TaskPriority.HIGH,
            timeout=10.0
        )
        ```
        """
        if self._shutdown:
            raise RuntimeError("AsyncHandler is shutdown")

        # 创建任务
        if task_id is None:
            task_id = f"task_{uuid.uuid4().hex[:8]}"

        task = Task(
            id=task_id,
            func=func,
            args=args,
            kwargs=kwargs or {},
            priority=priority,
            callback=callback,
            error_callback=error_callback,
            timeout=timeout or self._default_timeout,
        )

        # 存储任务
        with self._tasks_lock:
            self._tasks[task_id] = task

        # 更新监控指标
        with self._monitor_lock:
            self._total_submitted += 1

        # 添加到队列
        self._task_queue.put(task)

        logger.debug(
            f"Task submitted: id={task_id}, priority={priority.name}, "
            f"queue_size={self._task_queue.qsize()}"
        )

        return task_id

    def cancel(self, task_id: str) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功取消
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False

            # 只能取消PENDING状态的任务
            if task.state == TaskState.PENDING:
                task.state = TaskState.CANCELLED
                # 更新监控指标
                with self._monitor_lock:
                    self._total_cancelled += 1
                logger.info(f"Task cancelled: {task_id}")
                return True

            return False

    def get_task_state(self, task_id: str) -> Optional[TaskState]:
        """
        获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态，如果任务不存在返回None
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            return task.state if task else None

    def get_task_result(self, task_id: str) -> Optional[Any]:
        """
        获取任务结果

        Args:
            task_id: 任务ID

        Returns:
            任务结果，如果任务未完成或失败返回None
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task and task.state == TaskState.COMPLETED:
                return task.result
            return None

    def get_task_error(self, task_id: str) -> Optional[Exception]:
        """
        获取任务错误

        Args:
            task_id: 任务ID

        Returns:
            任务错误，如果任务未失败返回None
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task and task.state in (TaskState.FAILED, TaskState.TIMEOUT):
                return task.error
            return None

    def get_pending_count(self) -> int:
        """获取等待执行的任务数"""
        return self._task_queue.qsize()

    def get_running_count(self) -> int:
        """获取正在执行的任务数"""
        with self._tasks_lock:
            return sum(
                1 for t in self._tasks.values() if t.state == TaskState.RUNNING
            )

    def get_statistics(self) -> Dict[str, int]:
        """
        获取任务统计信息

        Returns:
            各状态任务数量统计
        """
        with self._tasks_lock:
            stats = {
                "total": len(self._tasks),
                "pending": 0,
                "running": 0,
                "completed": 0,
                "failed": 0,
                "cancelled": 0,
                "timeout": 0,
            }

            for task in self._tasks.values():
                if task.state == TaskState.PENDING:
                    stats["pending"] += 1
                elif task.state == TaskState.RUNNING:
                    stats["running"] += 1
                elif task.state == TaskState.COMPLETED:
                    stats["completed"] += 1
                elif task.state == TaskState.FAILED:
                    stats["failed"] += 1
                elif task.state == TaskState.CANCELLED:
                    stats["cancelled"] += 1
                elif task.state == TaskState.TIMEOUT:
                    stats["timeout"] += 1

            return stats

    def get_metrics(self) -> Dict[str, Any]:
        """
        获取监控指标

        Returns:
            监控指标字典
        """
        with self._monitor_lock:
            return {
                "queue_length": self._task_queue.qsize(),
                "max_queue_length": 100,
                "worker_count": self._worker_count,
                "active_workers": self.get_running_count(),
                "total_submitted": self._total_submitted,
                "total_completed": self._total_completed,
                "total_failed": self._total_failed,
                "total_timeout": self._total_timeout,
                "total_cancelled": self._total_cancelled,
                "success_rate": (
                    self._total_completed / self._total_submitted * 100
                    if self._total_submitted > 0
                    else 0
                ),
            }

    def check_health(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            健康状态和告警信息
        """
        metrics = self.get_metrics()
        alerts = []

        if metrics["queue_length"] > metrics["max_queue_length"]:
            alerts.append({
                "level": "warning",
                "message": f"队列长度 {metrics['queue_length']} 超过阈值"
            })

        if metrics["total_submitted"] > 10 and metrics["success_rate"] < 80:
            alerts.append({
                "level": "warning",
                "message": f"任务成功率 {metrics['success_rate']:.1f}% 低于 80%"
            })

        if not self._running:
            alerts.append({
                "level": "error",
                "message": "工作线程未运行"
            })

        return {
            "status": "healthy" if not alerts else "warning",
            "alerts": alerts,
            "metrics": metrics
        }

    def clear_completed_tasks(self, max_age: float = 3600.0) -> int:
        """
        清理已完成/失败/取消的任务

        Args:
            max_age: 最大保留时间（秒），超过此时间的任务会被清理

        Returns:
            清理的任务数
        """
        now = time.time()
        count = 0

        with self._tasks_lock:
            to_remove = []
            for task_id, task in self._tasks.items():
                if task.state in (
                    TaskState.COMPLETED,
                    TaskState.FAILED,
                    TaskState.CANCELLED,
                    TaskState.TIMEOUT,
                ):
                    if now - task.created_at > max_age:
                        to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]
                count += 1

        if count > 0:
            logger.info(f"Cleared {count} completed tasks")

        return count

    def shutdown(self, wait: bool = True, timeout: float = 10.0) -> None:
        """
        关闭异步处理器

        Args:
            wait: 是否等待所有任务完成
            timeout: 等待超时时间
        """
        if self._shutdown:
            return

        self._shutdown = True
        self._running = False

        # 清空队列中等待的任务
        cleared = self._task_queue.clear()
        if cleared > 0:
            logger.info(f"Cleared {cleared} pending tasks")

        # 关闭线程池
        try:
            self._executor.shutdown(wait=wait, cancel_futures=True)
        except Exception:
            # Python 3.8 兼容
            self._executor.shutdown(wait=wait)

        logger.info("AsyncHandler shutdown completed")

    def set_root(self, root: Any) -> None:
        """
        设置Tkinter root窗口（用于主线程回调）

        Args:
            root: Tkinter root窗口
        """
        self._root = root
        logger.debug("Root window updated")


# 全局单例
_async_handler_instance: Optional[AsyncHandler] = None
_async_handler_lock = threading.Lock()


def get_async_handler(root: Any = None) -> AsyncHandler:
    """
    获取全局AsyncHandler实例

    Args:
        root: Tkinter root窗口（首次调用时需要提供）

    Returns:
        AsyncHandler实例
    """
    global _async_handler_instance
    if _async_handler_instance is None:
        with _async_handler_lock:
            if _async_handler_instance is None:
                _async_handler_instance = AsyncHandler(root=root)
    return _async_handler_instance


def init_async_handler(
    root: Any, worker_count: int = 4, default_timeout: float = 30.0
) -> AsyncHandler:
    """
    初始化全局AsyncHandler实例

    Args:
        root: Tkinter root窗口
        worker_count: 工作线程数
        default_timeout: 默认超时时间

    Returns:
        AsyncHandler实例
    """
    global _async_handler_instance
    with _async_handler_lock:
        if _async_handler_instance is not None:
            _async_handler_instance.shutdown()

        _async_handler_instance = AsyncHandler(
            root=root,
            worker_count=worker_count,
            default_timeout=default_timeout,
        )
    return _async_handler_instance
