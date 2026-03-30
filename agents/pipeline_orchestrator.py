"""
小说生成流水线编排器

V1.0版本
创建日期: 2026-03-24

特性:
- 流水线阶段定义与执行
- 上下文传递：前一个Agent输出作为下一个输入
- 验证失败时的反馈优化循环
- 进度回调与事件发布
- 集成MasterAgent调度
"""

import threading
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, Future

from agents.core.base_agent import (
    BaseAgent,
    AgentMetadata,
    AgentContext,
    AgentResult,
    AgentState,
    AgentCapability,
)

logger = logging.getLogger(__name__)


class PipelineState(Enum):
    """流水线状态"""
    IDLE = "idle"                   # 空闲
    RUNNING = "running"             # 运行中
    PAUSED = "paused"               # 暂停
    COMPLETED = "completed"         # 已完成
    FAILED = "failed"               # 失败
    CANCELLED = "cancelled"         # 已取消


@dataclass
class PipelineStageResult:
    """流水线阶段结果"""
    stage_name: str
    agent_type: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    iteration: int = 0  # 迭代次数（用于验证优化循环）


@dataclass
class PipelineExecutionResult:
    """流水线执行结果"""
    pipeline_id: str
    pipeline_name: str
    success: bool
    stages: List[PipelineStageResult] = field(default_factory=list)
    final_output: Any = None
    total_iterations: int = 0
    total_duration_seconds: float = 0.0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "pipeline_id": self.pipeline_id,
            "pipeline_name": self.pipeline_name,
            "success": self.success,
            "stages": [
                {
                    "stage_name": s.stage_name,
                    "agent_type": s.agent_type,
                    "success": s.success,
                    "error": s.error,
                    "duration_seconds": s.duration_seconds,
                    "iteration": s.iteration,
                }
                for s in self.stages
            ],
            "total_iterations": self.total_iterations,
            "total_duration_seconds": self.total_duration_seconds,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class NovelGenerationConfig:
    """小说生成配置"""
    # 章节信息
    chapter_title: str = ""
    chapter_number: int = 1
    target_word_count: int = 2000
    
    # 大纲相关
    outline_content: str = ""
    chapter_outline: str = ""
    
    # 风格相关
    style_sample_path: str = ""
    style_profile: Dict[str, Any] = field(default_factory=dict)
    
    # 人物相关
    characters: List[Dict[str, Any]] = field(default_factory=list)
    
    # 世界观相关
    worldview: Dict[str, Any] = field(default_factory=dict)
    
    # 生成参数
    max_iterations: int = 5           # 最大迭代次数
    validation_threshold: float = 0.8  # 验证通过阈值
    
    # LLM参数
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 4000
    
    # 前文上下文
    previous_chapters: List[str] = field(default_factory=list)
    previous_chapter_text: str = ""
    
    # 知识库相关（V2.12新增）
    knowledge_categories: List[str] = field(default_factory=list)  # 选中的知识库分类
    knowledge_domains: List[str] = field(default_factory=list)     # 选中的知识领域
    
    # 写作技巧（V2.12新增）
    writing_techniques: List[str] = field(default_factory=list)    # 选中的写作技巧


class PipelineOrchestrator:
    """
    流水线编排器
    
    负责：
    1. 定义和执行流水线阶段
    2. 管理阶段间的上下文传递
    3. 处理验证失败时的反馈优化循环
    4. 发布进度事件和回调
    """
    
    # 小说生成流水线阶段定义
    # 注意：agent_type 必须与 agents/plugins/ 中的 AGENT_TYPE 一致
    NOVEL_GENERATION_STAGES = [
        {
            "name": "outline_analysis",
            "agent_type": "outline_analysis",  # 对应 plugins.outline_analysis_agent
            "description": "大纲解析与分析",
            "timeout_seconds": 60,
            "optional": False,
        },
        {
            "name": "style_learning",
            "agent_type": "style_learning",  # 对应 plugins.style_learning_agent
            "description": "风格学习",
            "timeout_seconds": 120,
            "optional": False,
        },
        {
            "name": "context_building",
            "agent_type": "context_building",  # 内置上下文构建（无独立Agent，在服务中处理）
            "description": "上下文构建",
            "timeout_seconds": 30,
            "optional": True,  # 可选阶段，由novel_generation_agent内部处理
        },
        {
            "name": "content_generation",
            "agent_type": "novel_generation",  # 对应 plugins.novel_generation_agent
            "description": "内容生成",
            "timeout_seconds": 300,
            "optional": False,
        },
        {
            "name": "validation",
            "agent_type": "quality_validation",  # 对应 plugins.quality_validation_agent
            "description": "质量验证",
            "timeout_seconds": 30,
            "optional": False,
        },
    ]
    
    def __init__(
        self,
        agent_registry,
        event_bus=None,
        max_workers: int = 4,
    ):
        """
        初始化流水线编排器
        
        Args:
            agent_registry: Agent注册表（提供get_agent方法）
            event_bus: 事件总线（可选）
            max_workers: 最大并发工作线程数
        """
        self._agent_registry = agent_registry
        self._event_bus = event_bus
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # 状态管理
        self._state = PipelineState.IDLE
        self._current_pipeline_id: Optional[str] = None
        self._cancel_requested = False
        self._lock = threading.RLock()
        
        # 进度回调
        self._progress_callbacks: List[Callable[[str, str, float], None]] = []
        
        # 结果缓存
        self._results: Dict[str, PipelineExecutionResult] = {}
    
    # === 流水线定义 ===
    
    def create_novel_generation_pipeline(self) -> str:
        """
        创建小说生成流水线
        
        Returns:
            流水线ID
        """
        pipeline_id = f"novel_gen_{uuid.uuid4().hex[:8]}"
        return pipeline_id
    
    # === 执行方法 ===
    
    def execute_novel_generation(
        self,
        config: NovelGenerationConfig,
        pipeline_id: str = None,
    ) -> PipelineExecutionResult:
        """
        执行小说生成流水线（同步）
        
        Args:
            config: 生成配置
            pipeline_id: 流水线ID（可选）
            
        Returns:
            流水线执行结果
        """
        pipeline_id = pipeline_id or self.create_novel_generation_pipeline()
        
        result = PipelineExecutionResult(
            pipeline_id=pipeline_id,
            pipeline_name="小说生成流水线",
            success=False,  # 初始为False，成功后再更新
            started_at=datetime.now(timezone.utc),
        )
        
        with self._lock:
            self._state = PipelineState.RUNNING
            self._current_pipeline_id = pipeline_id
            self._cancel_requested = False
        
        try:
            # 初始化上下文
            context = self._initialize_context(config)
            
            # 执行各阶段
            iteration = 0
            while iteration < config.max_iterations:
                iteration += 1
                result.total_iterations = iteration
                
                # 发布迭代开始事件
                self._publish_event("pipeline.iteration_started", {
                    "pipeline_id": pipeline_id,
                    "iteration": iteration,
                    "max_iterations": config.max_iterations,
                })
                
                # 执行一次完整流水线
                stage_results, should_retry = self._execute_pipeline_iteration(
                    pipeline_id=pipeline_id,
                    config=config,
                    context=context,
                    iteration=iteration,
                )
                
                result.stages.extend(stage_results)
                
                # 检查是否需要重试
                if not should_retry:
                    # 验证通过，提取最终输出
                    for stage_result in reversed(stage_results):
                        if stage_result.success and stage_result.data:
                            result.final_output = stage_result.data
                            break
                    break
                
                # 检查取消请求
                if self._cancel_requested:
                    result.success = False
                    result.error = "用户取消"
                    self._state = PipelineState.CANCELLED
                    break
                
                # 发布需要重试事件
                self._publish_event("pipeline.retry_needed", {
                    "pipeline_id": pipeline_id,
                    "iteration": iteration,
                    "reason": "验证未通过阈值",
                })
            
            # 检查是否成功
            if result.final_output:
                result.success = True
                self._state = PipelineState.COMPLETED
            else:
                result.success = False
                result.error = result.error or "达到最大迭代次数仍未通过验证"
                self._state = PipelineState.FAILED
            
        except Exception as e:
            logger.error(f"流水线执行异常: {e}", exc_info=True)
            result.success = False
            result.error = str(e)
            self._state = PipelineState.FAILED
        
        finally:
            result.completed_at = datetime.now(timezone.utc)
            if result.started_at:
                result.total_duration_seconds = (
                    result.completed_at - result.started_at
                ).total_seconds()
            
            # 缓存结果
            self._results[pipeline_id] = result
            
            # 发布完成事件
            self._publish_event("pipeline.completed", result.to_dict())
            
            with self._lock:
                self._state = PipelineState.IDLE
                self._current_pipeline_id = None
        
        return result
    
    def execute_novel_generation_async(
        self,
        config: NovelGenerationConfig,
        callback: Callable[[PipelineExecutionResult], None] = None,
    ) -> str:
        """
        异步执行小说生成流水线
        
        Args:
            config: 生成配置
            callback: 完成回调
            
        Returns:
            流水线ID
        """
        pipeline_id = self.create_novel_generation_pipeline()
        
        def _execute():
            try:
                result = self.execute_novel_generation(config, pipeline_id)
                if callback:
                    callback(result)
            except Exception as e:
                logger.error(f"异步执行异常: {e}", exc_info=True)
                if callback:
                    callback(PipelineExecutionResult(
                        pipeline_id=pipeline_id,
                        pipeline_name="小说生成流水线",
                        success=False,
                        error=str(e),
                    ))
        
        self._executor.submit(_execute)
        return pipeline_id
    
    def _execute_pipeline_iteration(
        self,
        pipeline_id: str,
        config: NovelGenerationConfig,
        context: AgentContext,
        iteration: int,
    ) -> Tuple[List[PipelineStageResult], bool]:
        """
        执行一次流水线迭代
        
        Args:
            pipeline_id: 流水线ID
            config: 生成配置
            context: 执行上下文
            iteration: 当前迭代次数
            
        Returns:
            (阶段结果列表, 是否需要重试)
        """
        stage_results = []
        current_payload = self._build_initial_payload(config, context)
        
        for stage_info in self.NOVEL_GENERATION_STAGES:
            # 检查取消
            if self._cancel_requested:
                break
            
            stage_name = stage_info["name"]
            agent_type = stage_info["agent_type"]
            timeout = stage_info.get("timeout_seconds", 60)
            
            # 更新进度（P2修复：添加迭代信息）
            self._notify_progress(
                pipeline_id, stage_name, 0.0,
                iteration=iteration, max_iterations=config.max_iterations
            )
            
            # 发布阶段开始事件
            self._publish_event("pipeline.stage_started", {
                "pipeline_id": pipeline_id,
                "stage_name": stage_name,
                "agent_type": agent_type,
                "iteration": iteration,
            })
            
            # 执行阶段
            stage_result = self._execute_stage(
                agent_type=agent_type,
                stage_name=stage_name,
                payload=current_payload,
                context=context,
                timeout=timeout,
                iteration=iteration,
            )
            
            stage_results.append(stage_result)
            
            # 更新进度（P2修复：添加迭代信息）
            progress = (len(stage_results) / len(self.NOVEL_GENERATION_STAGES)) * 100
            self._notify_progress(
                pipeline_id, stage_name, progress,
                iteration=iteration, max_iterations=config.max_iterations
            )
            
            # 发布阶段完成事件
            self._publish_event("pipeline.stage_completed", {
                "pipeline_id": pipeline_id,
                "stage_name": stage_name,
                "success": stage_result.success,
                "duration_seconds": stage_result.duration_seconds,
                "iteration": iteration,
            })
            
            # 处理失败
            if not stage_result.success:
                if not stage_info.get("optional", False):
                    return stage_results, True  # 需要重试
                continue
            
            # 传递上下文：将当前阶段的输出合并到下一个阶段的输入
            if stage_result.data:
                if isinstance(stage_result.data, dict):
                    current_payload.update(stage_result.data)
                    # 更新共享内存
                    for key, value in stage_result.data.items():
                        context.set_shared(f"{stage_name}.{key}", value)
                else:
                    # 非字典数据，存储为 "output"
                    current_payload["previous_output"] = stage_result.data
                    context.set_shared(f"{stage_name}.output", stage_result.data)
            
            # 特殊处理：验证阶段
            if stage_name == "validation" and stage_result.success:
                validation_score = self._extract_validation_score(stage_result.data)
                if validation_score is not None:
                    if validation_score < config.validation_threshold:
                        # 验证未通过，需要重试
                        # 将验证反馈添加到下一次迭代的输入中
                        feedback = self._extract_validation_feedback(stage_result.data)
                        context.set_shared("validation.feedback", feedback)
                        context.set_shared("validation.score", validation_score)
                        
                        # 构建优化提示
                        current_payload["optimization_feedback"] = feedback
                        current_payload["previous_score"] = validation_score
                        
                        return stage_results, True  # 需要重试
        
        return stage_results, False  # 不需要重试
    
    def _execute_stage(
        self,
        agent_type: str,
        stage_name: str,
        payload: Dict[str, Any],
        context: AgentContext,
        timeout: int,
        iteration: int,
    ) -> PipelineStageResult:
        """执行单个阶段"""
        start_time = time.time()
        
        result = PipelineStageResult(
            stage_name=stage_name,
            agent_type=agent_type,
            success=False,
            iteration=iteration,
        )
        
        try:
            # 获取Agent
            agent = self._agent_registry.get_agent(agent_type)
            if not agent:
                raise RuntimeError(f"Agent未注册: {agent_type}")
            
            # 确保Agent已初始化
            if not agent.is_initialized:
                if not agent.initialize():
                    raise RuntimeError(f"Agent初始化失败: {agent_type}")
            
            # 构建任务ID
            task_id = f"{stage_name}_{uuid.uuid4().hex[:8]}"
            
            # 执行任务
            agent_result = agent.execute(
                task_id=task_id,
                payload=payload,
                context=context,
            )
            
            # 处理结果
            if isinstance(agent_result, AgentResult):
                result.success = agent_result.success
                result.data = agent_result.data
                result.error = agent_result.error
            elif isinstance(agent_result, dict):
                result.success = agent_result.get("success", True)
                result.data = agent_result.get("data", agent_result)
                result.error = agent_result.get("error")
            else:
                result.success = True
                result.data = agent_result
        
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"阶段执行失败 {stage_name}: {e}", exc_info=True)
        
        finally:
            result.duration_seconds = time.time() - start_time
        
        return result
    
    # === 上下文管理 ===
    
    def _initialize_context(self, config: NovelGenerationConfig) -> AgentContext:
        """初始化执行上下文"""
        context = AgentContext(
            task_id=f"novel_gen_{uuid.uuid4().hex[:8]}",
            session_id=str(uuid.uuid4()),
        )
        
        # 设置初始共享数据
        context.set_shared("config", {
            "chapter_title": config.chapter_title,
            "chapter_number": config.chapter_number,
            "target_word_count": config.target_word_count,
            "outline_content": config.outline_content,
            "chapter_outline": config.chapter_outline,
            "characters": config.characters,
            "worldview": config.worldview,
            "style_profile": config.style_profile,
            "model": config.model,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "previous_chapter_text": config.previous_chapter_text,
            "knowledge_categories": config.knowledge_categories,  # V2.12新增
            "knowledge_domains": config.knowledge_domains,        # V2.12新增
            "writing_techniques": config.writing_techniques,      # V2.12新增
        })
        
        return context
    
    def _build_initial_payload(
        self,
        config: NovelGenerationConfig,
        context: AgentContext,
    ) -> Dict[str, Any]:
        """构建初始载荷"""
        return {
            "chapter_title": config.chapter_title,
            "chapter_number": config.chapter_number,
            "target_word_count": config.target_word_count,
            "outline_content": config.outline_content,
            "chapter_outline": config.chapter_outline,
            "style_sample_path": config.style_sample_path,
            "style_profile": config.style_profile,
            "characters": config.characters,
            "worldview": config.worldview,
            "previous_chapter_text": config.previous_chapter_text,
            "previous_chapters": config.previous_chapters,
            "model": config.model,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "knowledge_categories": config.knowledge_categories,  # V2.12新增
            "knowledge_domains": config.knowledge_domains,        # V2.12新增
            "writing_techniques": config.writing_techniques,      # V2.12新增
            # 从上下文获取之前的结果
            "shared_memory": context.shared_memory,
        }
    
    def _extract_validation_score(self, validation_data: Any) -> Optional[float]:
        """提取验证分数"""
        if validation_data is None:
            return None
        
        if isinstance(validation_data, dict):
            # 尝试多种可能的分数字段
            for key in ["total_score", "score", "overall_score", "validation_score"]:
                if key in validation_data:
                    return float(validation_data[key])
        
        return None
    
    def _extract_validation_feedback(self, validation_data: Any) -> str:
        """提取验证反馈"""
        if validation_data is None:
            return ""
        
        if isinstance(validation_data, dict):
            feedback_parts = []
            
            # 提取各维度的反馈
            for key in ["suggestions", "feedback", "issues", "recommendations"]:
                if key in validation_data:
                    value = validation_data[key]
                    if isinstance(value, list):
                        feedback_parts.extend(value)
                    elif isinstance(value, str):
                        feedback_parts.append(value)
            
            # 提取各维度的评分详情
            for key in ["word_count_reason", "outline_reason", "style_reason",
                       "character_reason", "worldview_reason", "naturalness_reason"]:
                if key in validation_data:
                    feedback_parts.append(f"{key}: {validation_data[key]}")
            
            return "\n".join(feedback_parts) if feedback_parts else ""
        
        return str(validation_data)
    
    # === 控制方法 ===
    
    def cancel(self) -> bool:
        """取消当前流水线"""
        with self._lock:
            if self._state != PipelineState.RUNNING:
                return False
            self._cancel_requested = True
            self._state = PipelineState.CANCELLED
        
        logger.info("流水线取消请求已发送")
        return True
    
    def get_state(self) -> PipelineState:
        """获取当前状态"""
        return self._state
    
    def get_result(self, pipeline_id: str) -> Optional[PipelineExecutionResult]:
        """获取流水线结果"""
        return self._results.get(pipeline_id)
    
    # === 进度回调 ===
    
    def add_progress_callback(
        self,
        callback: Callable[[str, str, float, int, int], None]
    ) -> None:
        """
        添加进度回调
        
        Args:
            callback: 回调函数 (pipeline_id, stage_name, progress_percent, iteration, max_iterations)
        """
        self._progress_callbacks.append(callback)
    
    def remove_progress_callback(
        self,
        callback: Callable[[str, str, float, int, int], None]
    ) -> None:
        """移除进度回调"""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)
    
    def _notify_progress(
        self,
        pipeline_id: str,
        stage_name: str,
        progress: float,
        iteration: int = 1,
        max_iterations: int = 5,
    ) -> None:
        """通知进度更新
        
        Args:
            pipeline_id: 流水线ID
            stage_name: 阶段名称
            progress: 进度百分比
            iteration: 当前迭代次数
            max_iterations: 最大迭代次数
        """
        for callback in self._progress_callbacks:
            try:
                callback(pipeline_id, stage_name, progress, iteration, max_iterations)
            except Exception as e:
                logger.error(f"进度回调异常: {e}")
    
    # === 事件发布 ===
    
    def _publish_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """发布事件"""
        if self._event_bus:
            try:
                self._event_bus.publish(event_type, data, source="PipelineOrchestrator")
            except Exception as e:
                logger.error(f"发布事件失败: {e}")
    
    # === 清理 ===
    
    def shutdown(self) -> None:
        """关闭编排器"""
        self._cancel_requested = True
        
        try:
            self._executor.shutdown(wait=True, cancel_futures=True)
        except TypeError:
            self._executor.shutdown(wait=True)
        
        logger.info("PipelineOrchestrator已关闭")


# === 工厂函数 ===

def create_novel_generation_pipeline(
    agent_registry,
    event_bus=None,
) -> PipelineOrchestrator:
    """
    创建小说生成流水线编排器
    
    Args:
        agent_registry: Agent注册表
        event_bus: 事件总线
        
    Returns:
        PipelineOrchestrator实例
    """
    return PipelineOrchestrator(
        agent_registry=agent_registry,
        event_bus=event_bus,
        max_workers=4,
    )
