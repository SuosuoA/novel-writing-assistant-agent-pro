"""
MasterAgent核心调度器

V1.0版本
创建日期: 2026-03-23

特性:
- Agent发现与注册
- 优先级调度
- 流水线执行
- 依赖解析
- ServiceLocator集成
"""

import threading
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Set, Type, Tuple
from collections import defaultdict, deque

from .base_agent import (
    BaseAgent,
    AgentMetadata,
    AgentContext,
    AgentResult,
    AgentState,
    AgentStatus,
    AgentCapability,
)


class TaskPriority(IntEnum):
    """任务优先级枚举（数值越小优先级越高）"""
    CRITICAL = 0    # 紧急任务: 用户主动触发
    HIGH = 1        # 高优先: 重要操作
    NORMAL = 2      # 正常: 常规任务
    LOW = 3         # 低优先: 后台任务
    BACKGROUND = 4  # 后台: 监控/清理


@dataclass
class TaskDefinition:
    """任务定义"""
    task_id: str
    task_type: str
    payload: Dict[str, Any]
    priority: TaskPriority = TaskPriority.NORMAL
    dependencies: List[str] = field(default_factory=list)
    timeout_seconds: int = 30
    max_retries: int = 1
    created_at: datetime = None
    started_at: datetime = None
    completed_at: datetime = None
    retry_count: int = 0
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
    
    @property
    def can_retry(self) -> bool:
        """是否可以重试"""
        return self.retry_count < self.max_retries


@dataclass
class PipelineStage:
    """流水线阶段"""
    name: str
    agent_type: str
    dependencies: List[str] = field(default_factory=list)
    timeout_seconds: int = 30
    optional: bool = False  # 可选阶段，失败不影响后续


@dataclass  
class PipelineDefinition:
    """流水线定义"""
    name: str
    stages: List[PipelineStage]
    description: str = ""


class AgentRegistry:
    """
    Agent注册表
    
    管理Agent的注册、发现和生命周期
    """
    
    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._metadata: Dict[str, AgentMetadata] = {}
        self._capabilities_index: Dict[AgentCapability, Set[str]] = defaultdict(set)
        self._lock = threading.RLock()
    
    def register(self, agent: BaseAgent) -> bool:
        """
        注册Agent
        
        Args:
            agent: Agent实例
            
        Returns:
            是否注册成功
        """
        with self._lock:
            if agent.agent_type in self._agents:
                logging.warning(f"Agent已存在，将覆盖: {agent.agent_type}")
            
            self._agents[agent.agent_type] = agent
            self._metadata[agent.agent_type] = agent.metadata
            
            # 更新能力索引
            for capability in agent.metadata.capabilities:
                self._capabilities_index[capability].add(agent.agent_type)
            
            logging.info(f"Agent注册成功: {agent.agent_type}")
            return True
    
    def unregister(self, agent_type: str) -> bool:
        """
        注销Agent
        
        Args:
            agent_type: Agent类型
            
        Returns:
            是否注销成功
        """
        with self._lock:
            if agent_type not in self._agents:
                return False
            
            agent = self._agents[agent_type]
            
            # 更新能力索引
            for capability in agent.metadata.capabilities:
                self._capabilities_index[capability].discard(agent_type)
            
            del self._agents[agent_type]
            del self._metadata[agent_type]
            
            logging.info(f"Agent注销成功: {agent_type}")
            return True
    
    def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        """获取Agent实例"""
        with self._lock:
            return self._agents.get(agent_type)
    
    def get_metadata(self, agent_type: str) -> Optional[AgentMetadata]:
        """获取Agent元数据"""
        with self._lock:
            return self._metadata.get(agent_type)
    
    def find_by_capability(self, capability: AgentCapability) -> List[str]:
        """按能力查找Agent"""
        with self._lock:
            return list(self._capabilities_index.get(capability, set()))
    
    def list_agents(self) -> List[str]:
        """列出所有Agent"""
        with self._lock:
            return list(self._agents.keys())
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有Agent状态"""
        with self._lock:
            return {
                agent_type: agent.status.to_dict()
                for agent_type, agent in self._agents.items()
            }


class TaskQueue:
    """
    任务优先级队列
    
    支持优先级排序和依赖管理
    """
    
    def __init__(self):
        self._tasks: Dict[str, TaskDefinition] = {}
        self._pending: List[Tuple[int, float, str]] = []  # (priority, created_at, task_id)
        self._lock = threading.RLock()
    
    def push(self, task: TaskDefinition) -> bool:
        """添加任务"""
        with self._lock:
            if task.task_id in self._tasks:
                return False
            
            self._tasks[task.task_id] = task
            # 使用堆结构，优先级相同时按创建时间排序
            import heapq
            heapq.heappush(self._pending, (task.priority, task.created_at.timestamp(), task.task_id))
            return True
    
    def pop(self) -> Optional[TaskDefinition]:
        """取出最高优先级任务"""
        with self._lock:
            if not self._pending:
                return None
            
            import heapq
            _, _, task_id = heapq.heappop(self._pending)
            return self._tasks.pop(task_id, None)
    
    def peek(self) -> Optional[TaskDefinition]:
        """查看最高优先级任务（不移除）"""
        with self._lock:
            if not self._pending:
                return None
            
            task_id = self._pending[0][2]
            return self._tasks.get(task_id)
    
    def remove(self, task_id: str) -> bool:
        """移除任务"""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                # 标记删除（惰性删除）
                return True
            return False
    
    def size(self) -> int:
        """队列大小"""
        with self._lock:
            return len(self._tasks)


class DependencyResolver:
    """
    依赖解析器
    
    使用DAG拓扑排序解析任务依赖
    """
    
    def __init__(self):
        self._dependency_graph: Dict[str, Set[str]] = defaultdict(set)  # task_id -> dependencies
        self._reverse_graph: Dict[str, Set[str]] = defaultdict(set)     # task_id -> dependents
        self._lock = threading.RLock()
    
    def add_task(self, task_id: str, dependencies: List[str]) -> None:
        """添加任务依赖"""
        with self._lock:
            self._dependency_graph[task_id] = set(dependencies)
            for dep_id in dependencies:
                self._reverse_graph[dep_id].add(task_id)
    
    def remove_task(self, task_id: str) -> None:
        """移除任务"""
        with self._lock:
            # 从依赖图中移除
            for dep_id in self._dependency_graph.pop(task_id, set()):
                self._reverse_graph[dep_id].discard(task_id)
            
            # 从反向图中移除
            for dependent_id in self._reverse_graph.pop(task_id, set()):
                self._dependency_graph[dependent_id].discard(task_id)
    
    def get_ready_tasks(self, completed: Set[str]) -> List[str]:
        """
        获取可执行的任务（所有依赖已完成）
        
        Args:
            completed: 已完成的任务ID集合
            
        Returns:
            可执行的任务ID列表
        """
        with self._lock:
            ready = []
            for task_id, deps in self._dependency_graph.items():
                if deps.issubset(completed):
                    ready.append(task_id)
            return ready
    
    def detect_cycle(self) -> Optional[List[str]]:
        """
        检测循环依赖
        
        Returns:
            循环依赖的任务ID列表，无循环返回None
        """
        with self._lock:
            # 使用DFS检测环
            WHITE, GRAY, BLACK = 0, 1, 2
            color = {task_id: WHITE for task_id in self._dependency_graph}
            path = []
            
            def dfs(task_id: str) -> Optional[List[str]]:
                color[task_id] = GRAY
                path.append(task_id)
                
                for dep_id in self._dependency_graph[task_id]:
                    if color.get(dep_id, WHITE) == GRAY:
                        # 发现环
                        cycle_start = path.index(dep_id)
                        return path[cycle_start:] + [dep_id]
                    elif color.get(dep_id, WHITE) == WHITE:
                        result = dfs(dep_id)
                        if result:
                            return result
                
                color[task_id] = BLACK
                path.pop()
                return None
            
            for task_id in self._dependency_graph:
                if color[task_id] == WHITE:
                    result = dfs(task_id)
                    if result:
                        return result
            
            return None


class MasterAgent:
    """
    MasterAgent总控调度器
    
    职责:
    1. Agent注册与发现
    2. 任务调度与执行
    3. 流水线编排
    4. 依赖解析
    5. ServiceLocator集成
    
    使用示例:
    ```python
    # 创建MasterAgent
    master = MasterAgent()
    
    # 设置ServiceLocator
    master.set_service_locator(service_locator)
    
    # 注册Agent
    master.register_agent(my_agent)
    
    # 提交任务
    task_id = master.submit_task(
        task_type="generation",
        payload={"text": "..."},
        priority=TaskPriority.HIGH
    )
    
    # 执行流水线
    result = master.execute_pipeline(pipeline_definition)
    ```
    """
    
    def __init__(self, max_workers: int = 10):
        """
        初始化MasterAgent
        
        Args:
            max_workers: 线程池最大工作线程数
        """
        self._registry = AgentRegistry()
        self._task_queue = TaskQueue()
        self._dependency_resolver = DependencyResolver()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._task_event = threading.Event()
        self._lock = threading.RLock()
        
        # 任务状态追踪
        self._pending_tasks: Dict[str, TaskDefinition] = {}
        self._running_tasks: Dict[str, Future] = {}
        self._completed_tasks: Dict[str, AgentResult] = {}
        self._completed_ids: Set[str] = set()
        self._failed_ids: Set[str] = set()
        
        # ServiceLocator
        self._service_locator = None
        self._logger: Optional[logging.Logger] = None
        
        # 流水线定义
        self._pipelines: Dict[str, PipelineDefinition] = {}
    
    # === ServiceLocator集成 ===
    
    def set_service_locator(self, service_locator) -> None:
        """
        设置服务定位器
        
        Args:
            service_locator: ServiceLocator实例
        """
        self._service_locator = service_locator
        self._logger = None  # 重置日志器
        
        # 为所有已注册的Agent设置ServiceLocator
        for agent in self._registry._agents.values():
            agent.set_service_locator(service_locator)
    
    def get_service(self, service_type: Type) -> Any:
        """获取服务实例"""
        if self._service_locator is None:
            return None
        return self._service_locator.try_get(service_type)
    
    def get_logger(self) -> logging.Logger:
        """获取日志器"""
        if self._logger is None:
            if self._service_locator:
                try:
                    from core.logging_service import LoggingService
                    logging_service = self.get_service(LoggingService)
                    if logging_service:
                        self._logger = logging_service.get_logger("master_agent")
                except ImportError:
                    pass
            
            if self._logger is None:
                self._logger = logging.getLogger("master_agent")
        
        return self._logger
    
    def get_event_bus(self):
        """获取事件总线"""
        try:
            from core.event_bus import EventBus
            return self.get_service(EventBus)
        except ImportError:
            return None
    
    # === Agent管理 ===
    
    def register_agent(self, agent: BaseAgent) -> bool:
        """
        注册Agent
        
        Args:
            agent: Agent实例
            
        Returns:
            是否注册成功
        """
        # 设置ServiceLocator
        if self._service_locator:
            agent.set_service_locator(self._service_locator)
        
        # 初始化Agent
        if not agent.is_initialized:
            try:
                if not agent.initialize():
                    self.get_logger().error(f"Agent初始化失败: {agent.agent_type}")
                    return False
            except Exception as e:
                self.get_logger().error(f"Agent初始化异常 {agent.agent_type}: {e}")
                return False
        
        return self._registry.register(agent)
    
    def unregister_agent(self, agent_type: str) -> bool:
        """
        注销Agent
        
        Args:
            agent_type: Agent类型
            
        Returns:
            是否注销成功
        """
        agent = self._registry.get_agent(agent_type)
        if agent:
            try:
                agent.cleanup()
            except Exception as e:
                self.get_logger().warning(f"Agent清理异常 {agent_type}: {e}")
        
        return self._registry.unregister(agent_type)
    
    def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        """获取Agent实例"""
        return self._registry.get_agent(agent_type)
    
    def list_agents(self) -> List[str]:
        """列出所有Agent"""
        return self._registry.list_agents()
    
    def find_agents_by_capability(self, capability: AgentCapability) -> List[str]:
        """按能力查找Agent"""
        return self._registry.find_by_capability(capability)
    
    # === 任务调度 ===
    
    def start(self) -> None:
        """启动调度器"""
        if self._running:
            self.get_logger().warning("调度器已在运行中")
            return
        
        self._running = True
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        
        self.get_logger().info("MasterAgent调度器已启动")
    
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
            self._executor.shutdown(wait=True)
        
        self.get_logger().info("MasterAgent调度器已停止")
    
    def submit_task(
        self,
        task_type: str,
        payload: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        dependencies: List[str] = None,
        timeout_seconds: int = 30,
        max_retries: int = 1,
    ) -> str:
        """
        提交任务
        
        Args:
            task_type: 任务类型
            payload: 任务载荷
            priority: 优先级
            dependencies: 依赖任务ID列表
            timeout_seconds: 超时时间
            max_retries: 最大重试次数
            
        Returns:
            任务ID
        """
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        
        task = TaskDefinition(
            task_id=task_id,
            task_type=task_type,
            payload=payload,
            priority=priority,
            dependencies=dependencies or [],
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        
        with self._lock:
            self._pending_tasks[task_id] = task
            self._task_queue.push(task)
            self._dependency_resolver.add_task(task_id, task.dependencies)
        
        self._task_event.set()
        
        self.get_logger().info(f"任务已提交: {task_id} (类型: {task_type}, 优先级: {priority.name})")
        return task_id
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._lock:
            # 从待处理队列移除
            if task_id in self._pending_tasks:
                del self._pending_tasks[task_id]
                self._task_queue.remove(task_id)
                self._dependency_resolver.remove_task(task_id)
                return True
            
            # 尝试取消正在运行的任务
            if task_id in self._running_tasks:
                future = self._running_tasks[task_id]
                return future.cancel()
        
        return False
    
    def get_task_result(self, task_id: str) -> Optional[AgentResult]:
        """获取任务结果"""
        return self._completed_tasks.get(task_id)
    
    def get_task_status(self, task_id: str) -> str:
        """获取任务状态"""
        with self._lock:
            if task_id in self._completed_tasks:
                return "completed" if self._completed_tasks[task_id].success else "failed"
            if task_id in self._running_tasks:
                return "running"
            if task_id in self._pending_tasks:
                return "pending"
            return "unknown"
    
    # === 流水线执行 ===
    
    def register_pipeline(self, pipeline: PipelineDefinition) -> None:
        """注册流水线"""
        self._pipelines[pipeline.name] = pipeline
    
    def execute_pipeline(
        self,
        pipeline_name: str,
        payload: Dict[str, Any],
        context: AgentContext = None,
    ) -> Dict[str, AgentResult]:
        """
        执行流水线
        
        Args:
            pipeline_name: 流水线名称
            payload: 初始载荷
            context: 执行上下文
            
        Returns:
            各阶段执行结果 {stage_name: AgentResult}
        """
        pipeline = self._pipelines.get(pipeline_name)
        if not pipeline:
            raise ValueError(f"流水线未定义: {pipeline_name}")
        
        results: Dict[str, AgentResult] = {}
        current_payload = payload.copy()
        
        # 构建阶段依赖图
        stage_status: Dict[str, str] = {stage.name: "pending" for stage in pipeline.stages}
        completed_stages: Set[str] = set()
        
        # 按依赖顺序执行
        for stage in pipeline.stages:
            # 检查依赖是否完成
            deps_completed = all(
                stage_status.get(dep) == "completed"
                for dep in stage.dependencies
            )
            
            if not deps_completed:
                # 跳过依赖未完成的阶段
                stage_status[stage.name] = "skipped"
                continue
            
            # 执行阶段
            agent = self._registry.get_agent(stage.agent_type)
            if not agent:
                self.get_logger().warning(f"阶段 {stage.name} 的Agent不存在: {stage.agent_type}")
                if not stage.optional:
                    stage_status[stage.name] = "failed"
                    break
                stage_status[stage.name] = "skipped"
                continue
            
            try:
                result = agent.execute(
                    task_id=f"{pipeline_name}_{stage.name}_{uuid.uuid4().hex[:8]}",
                    payload=current_payload,
                    context=context,
                )
                
                results[stage.name] = result
                
                if result.success:
                    stage_status[stage.name] = "completed"
                    completed_stages.add(stage.name)
                    # 更新载荷供后续阶段使用
                    if result.data and isinstance(result.data, dict):
                        current_payload.update(result.data)
                else:
                    stage_status[stage.name] = "failed"
                    if not stage.optional:
                        break
                    
            except Exception as e:
                self.get_logger().error(f"阶段 {stage.name} 执行异常: {e}")
                results[stage.name] = AgentResult.failure_result(
                    task_id=f"{pipeline_name}_{stage.name}",
                    agent_type=stage.agent_type,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                stage_status[stage.name] = "failed"
                if not stage.optional:
                    break
        
        return results
    
    # === 内部方法 ===
    
    def _scheduler_loop(self) -> None:
        """调度循环"""
        self.get_logger().info("调度循环启动")
        
        while self._running:
            try:
                # 检查依赖完成的任务
                ready_tasks = self._dependency_resolver.get_ready_tasks(self._completed_ids)
                
                # 从队列取出任务
                task = self._task_queue.peek()
                
                if task and task.task_id in ready_tasks:
                    task = self._task_queue.pop()
                    if task:
                        self._execute_task_async(task)
                else:
                    # 等待新任务或完成事件
                    self._task_event.wait(timeout=1.0)
                    self._task_event.clear()
            
            except Exception as e:
                self.get_logger().error(f"调度循环异常: {e}", exc_info=True)
                time.sleep(1)
    
    def _execute_task_async(self, task: TaskDefinition) -> None:
        """异步执行任务"""
        future = self._executor.submit(self._execute_task_sync, task)
        
        with self._lock:
            self._running_tasks[task.task_id] = future
            if task.task_id in self._pending_tasks:
                del self._pending_tasks[task.task_id]
    
    def _execute_task_sync(self, task: TaskDefinition) -> None:
        """同步执行任务"""
        logger = self.get_logger()
        task.started_at = datetime.now(timezone.utc)
        
        try:
            # 查找能处理该任务的Agent
            agent = self._find_agent_for_task(task.task_type, task.payload)
            
            if not agent:
                logger.error(f"未找到能处理任务的Agent: {task.task_type}")
                self._record_failure(task, "未找到合适的Agent")
                return
            
            # 执行任务
            context = AgentContext(task_id=task.task_id)
            
            result = agent.execute(
                task_id=task.task_id,
                payload=task.payload,
                context=context,
            )
            
            task.completed_at = datetime.now(timezone.utc)
            
            if result.success:
                logger.info(f"任务 {task.task_id} 执行成功")
                self._record_success(task, result)
            else:
                self._handle_task_failure(task, result.error or "执行失败")
            
        except FutureTimeoutError:
            logger.error(f"任务 {task.task_id} 执行超时")
            self._handle_task_failure(task, "执行超时")
        
        except Exception as e:
            logger.error(f"任务 {task.task_id} 执行异常: {e}")
            self._handle_task_failure(task, str(e))
    
    def _find_agent_for_task(self, task_type: str, payload: Dict[str, Any]) -> Optional[BaseAgent]:
        """查找能处理任务的Agent"""
        # 按优先级遍历所有Agent
        for agent_type in self._registry.list_agents():
            agent = self._registry.get_agent(agent_type)
            if agent and agent.is_initialized and agent.can_handle(task_type, payload):
                return agent
        return None
    
    def _handle_task_failure(self, task: TaskDefinition, error: str) -> None:
        """处理任务失败"""
        if task.can_retry:
            task.retry_count += 1
            self.get_logger().info(f"任务 {task.task_id} 准备重试 ({task.retry_count}/{task.max_retries})")
            
            # 重新入队
            with self._lock:
                self._pending_tasks[task.task_id] = task
                self._task_queue.push(task)
        else:
            self._record_failure(task, error)
    
    def _record_success(self, task: TaskDefinition, result: AgentResult) -> None:
        """记录任务成功"""
        with self._lock:
            self._completed_tasks[task.task_id] = result
            self._completed_ids.add(task.task_id)
            if task.task_id in self._running_tasks:
                del self._running_tasks[task.task_id]
            self._dependency_resolver.remove_task(task.task_id)
        
        # 发布事件
        event_bus = self.get_event_bus()
        if event_bus:
            event_bus.publish(
                "agent.task.completed",
                {"task_id": task.task_id, "task_type": task.task_type, "result": result.to_dict()},
                source="MasterAgent",
            )
        
        self._task_event.set()
    
    def _record_failure(self, task: TaskDefinition, error: str) -> None:
        """记录任务失败"""
        result = AgentResult.failure_result(
            task_id=task.task_id,
            agent_type="unknown",
            error=error,
        )
        
        with self._lock:
            self._completed_tasks[task.task_id] = result
            self._failed_ids.add(task.task_id)
            if task.task_id in self._running_tasks:
                del self._running_tasks[task.task_id]
            self._dependency_resolver.remove_task(task.task_id)
        
        # 发布事件
        event_bus = self.get_event_bus()
        if event_bus:
            event_bus.publish(
                "agent.task.failed",
                {"task_id": task.task_id, "task_type": task.task_type, "error": error},
                source="MasterAgent",
            )
        
        self._task_event.set()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "running": self._running,
                "pending_tasks": len(self._pending_tasks),
                "running_tasks": len(self._running_tasks),
                "completed_tasks": len(self._completed_ids),
                "failed_tasks": len(self._failed_ids),
                "registered_agents": len(self._registry.list_agents()),
                "registered_pipelines": len(self._pipelines),
            }
