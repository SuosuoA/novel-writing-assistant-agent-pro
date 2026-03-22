"""
MasterAgent总控调度器

V2.0版本
创建日期: 2026-03-21

特性:
- ThreadPoolExecutor调度
- 优先级队列管理
- 依赖解析
- 重试与熔断
- 事件驱动
"""

import threading
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from .priority import AgentTask, TaskPriority
from .task_queue import AgentTaskQueue
from .dependency_resolver import DependencyResolver
from .dependency_state import DependencyState
from .retry_manager import RetryManager, RetryConfig
from .agent_pool import AgentPool
from .agent_state import AgentState
from .agent_constraints import (
    ThinkerConstraints,
    OptimizerConstraints,
    ValidatorConstraints,
    PlannerConstraints,
)
from core.event_bus import EventBus

logger = logging.getLogger(__name__)


class MasterAgent:
    """
    MasterAgent总控调度器

    职责:
    1. 接收任务并提交到优先级队列
    2. 解析任务依赖关系
    3. 调度Agent执行任务
    4. 管理重试和降级策略
    5. 发布任务事件
    """

    # Agent类型到约束配置的映射
    CONSTRAINTS_MAP = {
        "thinker": ThinkerConstraints(),
        "optimizer": OptimizerConstraints(),
        "validator": ValidatorConstraints(),
        "planner": PlannerConstraints(),
        # V5模块适配器约束（使用默认值）
        "outline_parser": None,
        "style_learner": None,
        "weighted_validator": None,
        "context_builder": None,
        "iterative_generator": None,
    }

    def __init__(self, event_bus: EventBus, max_workers: int = 10):
        """
        初始化MasterAgent

        Args:
            event_bus: 事件总线实例
            max_workers: 线程池最大工作线程数
        """
        self._event_bus = event_bus
        self._task_queue = AgentTaskQueue()
        self._dependency_resolver = DependencyResolver()
        self._dependency_state = DependencyState()
        self._retry_manager = RetryManager(RetryConfig())
        self._agent_pool = AgentPool(event_bus)
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._scheduler_thread: Optional[threading.Thread] = None
        self._task_event = threading.Event()
        self._tasks: Dict[str, AgentTask] = {}
        self._lock = threading.RLock()

        # 订阅事件
        self._subscribe_events()

    def _subscribe_events(self) -> None:
        """订阅事件总线"""
        self._event_bus.subscribe(
            "user.generation_requested", self._on_generation_requested
        )
        self._event_bus.subscribe("generation.completed", self._on_generation_completed)
        self._event_bus.subscribe("generation.failed", self._on_generation_failed)

    def start(self) -> None:
        """启动调度器"""
        if self._running:
            logger.warning("调度器已在运行中")
            return

        self._running = True
        self._agent_pool.initialize()

        # 启动调度线程
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop, daemon=True
        )
        self._scheduler_thread.start()

        logger.info("MasterAgent调度器已启动")

    def stop(self) -> None:
        """停止调度器"""
        self._running = False
        self._task_event.set()

        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5.0)

        # Python 3.9+支持cancel_futures参数
        try:
            self._executor.shutdown(wait=True, cancel_futures=True)
        except TypeError:
            # Python 3.8及以下版本不支持cancel_futures
            self._executor.shutdown(wait=True)
        self._agent_pool.cleanup_all()

        logger.info("MasterAgent调度器已停止")

    def _scheduler_loop(self) -> None:
        """调度循环（事件驱动）"""
        logger.info("调度循环启动")

        while self._running:
            try:
                # 获取可执行任务
                ready_tasks = self._dependency_resolver.get_ready_tasks(
                    self._dependency_state._completed
                )

                # 按优先级选择任务
                task = self._task_queue.peek()
                if task and task.task_id in ready_tasks:
                    self._execute_task_async(task)
                else:
                    # 没有可执行任务，等待事件
                    self._task_event.wait(timeout=1.0)
                    self._task_event.clear()

            except Exception as e:
                logger.error(f"调度循环异常: {e}", exc_info=True)
                time.sleep(1)

    def _execute_task_async(self, task: AgentTask) -> None:
        """异步执行任务"""
        self._executor.submit(self._execute_task_sync, task)

    def _execute_task_sync(self, task: AgentTask) -> None:
        """
        同步执行任务（在线程池中执行）

        Args:
            task: 任务对象
        """
        try:
            logger.info(f"开始执行任务: {task.task_id} " f"(Agent: {task.agent_type})")

            # 从队列取出任务
            popped_task = self._task_queue.pop()
            if popped_task is None:
                logger.warning("任务队列为空，跳过执行")
                return

            # 使用实际取出的任务
            task = popped_task

            # 标记状态
            if not self._dependency_state.mark_in_progress(task.task_id):
                logger.warning(f"任务 {task.task_id} 状态异常，重新入队")
                self._task_queue.push(task)
                return

            # 获取Agent实例
            agent = self._agent_pool.get_agent(task.agent_type)
            if not agent:
                logger.error(f"未找到Agent类型: {task.agent_type}")
                self._dependency_state.mark_failed(task.task_id)
                return

            # 获取约束配置
            constraints = self.CONSTRAINTS_MAP.get(task.agent_type)
            if constraints:
                task.timeout_seconds = constraints.timeout_seconds
                task.max_retries = constraints.max_retries

            # 执行任务
            def execute_sync():
                return agent.execute(task)

            try:
                # 提交到线程池并设置超时
                future = self._executor.submit(execute_sync)
                result = future.result(timeout=task.timeout_seconds)

                logger.info(f"任务 {task.task_id} 执行成功")

                # 标记为完成
                self._dependency_state.mark_completed(task.task_id)
                task.completed_at = datetime.now(timezone.utc)

                # 发布完成事件
                self._event_bus.publish(
                    "agent.task.completed",
                    {
                        "task_id": task.task_id,
                        "agent_type": task.agent_type,
                        "result": result,
                    },
                    source="MasterAgent",
                )

                # 唤醒调度循环
                self._task_event.set()

            except FutureTimeoutError:
                logger.error(f"任务 {task.task_id} 执行超时")
                self._handle_task_failure(task, "执行超时", constraints)

            except Exception as e:
                logger.error(f"任务 {task.task_id} 执行失败: {e}")
                self._handle_task_failure(task, str(e), constraints)

        except Exception as e:
            logger.error(f"执行任务异常: {e}", exc_info=True)

    def _handle_task_failure(
        self, task: AgentTask, error: str, constraints: Any
    ) -> None:
        """
        处理任务失败

        Args:
            task: 任务对象
            error: 错误信息
            constraints: 约束配置
        """
        # 检查是否可以重试
        if task.can_retry:
            task.retry_count += 1
            logger.info(
                f"任务 {task.task_id} 准备重试 "
                f"({task.retry_count}/{task.max_retries})"
            )
            # 重试任务重新入队，状态改为PENDING
            self._dependency_state.mark_pending(task.task_id)
            self._task_queue.push(task)
        else:
            # 标记为失败
            self._dependency_state.mark_failed(task.task_id)

            # 尝试降级策略
            if constraints:
                try:
                    fallback_result = constraints.get_fallback_strategy()()
                    logger.info(f"任务 {task.task_id} 使用降级策略")

                    # 发布降级事件
                    self._event_bus.publish(
                        "agent.task.fallback",
                        {
                            "task_id": task.task_id,
                            "agent_type": task.agent_type,
                            "fallback_result": fallback_result,
                        },
                        source="MasterAgent",
                    )
                except Exception as fallback_e:
                    logger.error(f"降级策略也失败: {fallback_e}")

            # 发布失败事件
            self._event_bus.publish(
                "agent.task.failed",
                {
                    "task_id": task.task_id,
                    "agent_type": task.agent_type,
                    "error": error,
                    "retry_count": task.retry_count,
                },
                source="MasterAgent",
            )

        # 唤醒调度循环
        self._task_event.set()

    def submit_task(self, task: AgentTask) -> str:
        """
        提交任务

        Args:
            task: 任务对象

        Returns:
            任务ID
        """
        # 生成任务ID（如果未提供）
        if not task.task_id:
            task.task_id = f"task-{uuid.uuid4().hex[:8]}"

        with self._lock:
            # 添加到任务字典
            self._tasks[task.task_id] = task

            # 添加到优先级队列
            if not self._task_queue.push(task):
                logger.warning(f"任务 {task.task_id} 已存在")
                return task.task_id

            # 构建依赖图
            try:
                self._dependency_resolver.build_graph(self._tasks)
            except ValueError as e:
                logger.error(f"依赖解析失败: {e}")
                self._task_queue.remove(task.task_id)
                del self._tasks[task.task_id]
                raise

        # 唤醒调度循环
        self._task_event.set()

        logger.info(f"任务已提交: {task.task_id} " f"(优先级: {task.priority.name})")
        return task.task_id

    def submit_tasks(self, tasks: List[AgentTask]) -> List[str]:
        """
        批量提交任务

        Args:
            tasks: 任务列表

        Returns:
            任务ID列表
        """
        task_ids = []
        for task in tasks:
            task_id = self.submit_task(task)
            task_ids.append(task_id)
        return task_ids

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否取消成功
        """
        with self._lock:
            if task_id not in self._tasks:
                return False

            # 从队列移除
            self._task_queue.remove(task_id)

            # 从任务字典移除
            del self._tasks[task_id]

            logger.info(f"任务已取消: {task_id}")
            return True

    def get_task_status(self, task_id: str) -> Optional[str]:
        """
        获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态
        """
        return self._dependency_state.get_status(task_id)

    def get_agent_pool(self) -> AgentPool:
        """获取Agent池实例"""
        return self._agent_pool

    # === 事件处理器 ===

    def _on_generation_requested(self, event) -> None:
        """
        处理生成请求事件（链式协作模式）

        Args:
            event: 事件对象
        """
        try:
            data = event.data

            # 创建任务链: Planner → Thinker → Optimizer → Validator
            planner_task = AgentTask(
                task_id=f"planner-{uuid.uuid4().hex[:8]}",
                agent_type="planner",
                priority=TaskPriority.CRITICAL,
                payload=data,
                dependencies=[],
            )

            thinker_task = AgentTask(
                task_id=f"thinker-{uuid.uuid4().hex[:8]}",
                agent_type="thinker",
                priority=TaskPriority.CRITICAL,
                payload=data,
                dependencies=[planner_task.task_id],
            )

            optimizer_task = AgentTask(
                task_id=f"optimizer-{uuid.uuid4().hex[:8]}",
                agent_type="optimizer",
                priority=TaskPriority.CRITICAL,
                payload=data,
                dependencies=[thinker_task.task_id],
            )

            validator_task = AgentTask(
                task_id=f"validator-{uuid.uuid4().hex[:8]}",
                agent_type="validator",
                priority=TaskPriority.CRITICAL,
                payload=data,
                dependencies=[optimizer_task.task_id],
            )

            # 提交任务链
            self.submit_tasks(
                [planner_task, thinker_task, optimizer_task, validator_task]
            )

        except Exception as e:
            logger.error(f"处理生成请求事件异常: {e}", exc_info=True)
            self._event_bus.publish(
                "agent.event.error",
                {
                    "event_type": "user.generation_requested",
                    "error": str(e),
                },
                source="MasterAgent",
            )

    def _on_generation_completed(self, event) -> None:
        """生成完成事件处理"""
        try:
            task_id = event.data.get("task_id")
            logger.info(f"生成任务完成: {task_id}")
        except Exception as e:
            logger.error(f"处理生成完成事件异常: {e}", exc_info=True)

    def _on_generation_failed(self, event) -> None:
        """生成失败事件处理"""
        try:
            task_id = event.data.get("task_id")
            error = event.data.get("error")
            logger.error(f"生成任务失败: {task_id}, 错误: {error}")
        except Exception as e:
            logger.error(f"处理生成失败事件异常: {e}", exc_info=True)
