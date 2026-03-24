"""
小说生成服务

V1.0版本
创建日期: 2026-03-24

特性:
- 封装流水线调用逻辑
- 管理Agent注册表
- 提供GUI回调接口
"""

import logging
import threading
import os
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass

from agents.pipeline_orchestrator import (
    PipelineOrchestrator,
    PipelineState,
    PipelineExecutionResult,
    NovelGenerationConfig,
)
from agents.core.base_agent import BaseAgent
# P0修复：统一使用plugins模块的Agent实现
from agents.plugins import (
    OutlineAnalysisAgent,
    StyleLearningAgent,
    NovelGenerationAgent,
    QualityValidationAgent,
)

logger = logging.getLogger(__name__)


@dataclass
class GenerationProgress:
    """生成进度"""
    pipeline_id: str
    stage_name: str
    progress_percent: float
    iteration: int
    max_iterations: int
    message: str


class NovelGenerationService:
    """
    小说生成服务
    
    负责：
    1. 初始化Agent注册表
    2. 管理流水线编排器
    3. 提供GUI回调接口
    4. 处理LLM客户端配置
    """
    
    def __init__(self, event_bus=None, llm_client=None):
        """
        初始化服务
        
        Args:
            event_bus: 事件总线
            llm_client: LLM客户端实例
        """
        self._event_bus = event_bus
        self._llm_client = llm_client
        
        # Agent注册表
        self._agents: Dict[str, BaseAgent] = {}
        self._initialize_agents()
        
        # 流水线编排器
        self._orchestrator = PipelineOrchestrator(
            agent_registry=self,
            event_bus=event_bus,
        )
        
        # 进度回调
        self._progress_callbacks: List[Callable[[GenerationProgress], None]] = []
        self._orchestrator.add_progress_callback(self._on_progress)
        
        # 当前执行状态
        self._current_pipeline_id: Optional[str] = None
        self._lock = threading.RLock()
    
    def _initialize_agents(self) -> None:
        """初始化内置Agent
        
        P0修复：统一使用plugins模块的Agent实现
        """
        # 注册小说生成流水线Agent（来自plugins模块）
        agents = [
            OutlineAnalysisAgent(),
            StyleLearningAgent(),
            NovelGenerationAgent(),  # 替代原ContentGenerationAgent
            QualityValidationAgent(),
        ]
        
        for agent in agents:
            agent.initialize()
            self._agents[agent.agent_type] = agent
            logger.info(f"Agent已注册: {agent.agent_type}")
    
    def set_llm_client(self, llm_client) -> None:
        """设置LLM客户端"""
        self._llm_client = llm_client
        # 更新小说生成Agent的LLM客户端
        generation_agent = self._agents.get("novel_generation")
        if generation_agent and hasattr(generation_agent, "set_llm_client"):
            generation_agent.set_llm_client(llm_client)
    
    # === Agent注册表接口 ===
    
    def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        """获取Agent实例"""
        return self._agents.get(agent_type)
    
    def register_agent(self, agent: BaseAgent) -> bool:
        """注册Agent"""
        if agent.agent_type in self._agents:
            logger.warning(f"Agent已存在，将覆盖: {agent.agent_type}")
        
        if not agent.is_initialized:
            if not agent.initialize():
                logger.error(f"Agent初始化失败: {agent.agent_type}")
                return False
        
        self._agents[agent.agent_type] = agent
        logger.info(f"Agent注册成功: {agent.agent_type}")
        return True
    
    def unregister_agent(self, agent_type: str) -> bool:
        """注销Agent"""
        if agent_type not in self._agents:
            return False
        
        agent = self._agents[agent_type]
        agent.cleanup()
        del self._agents[agent_type]
        logger.info(f"Agent注销成功: {agent_type}")
        return True
    
    def list_agents(self) -> List[str]:
        """列出所有Agent"""
        return list(self._agents.keys())
    
    # === 生成接口 ===
    
    def generate_chapter(
        self,
        chapter_title: str,
        chapter_number: int,
        outline_content: str,
        chapter_outline: str,
        target_word_count: int = 2000,
        style_sample_path: str = "",
        style_profile: Dict[str, Any] = None,
        characters: List[Dict[str, Any]] = None,
        worldview: Dict[str, Any] = None,
        previous_chapter_text: str = "",
        max_iterations: int = 5,
        callback: Callable[[PipelineExecutionResult], None] = None,
    ) -> str:
        """
        生成章节内容（异步）
        
        Args:
            chapter_title: 章节标题
            chapter_number: 章节编号
            outline_content: 完整大纲内容
            chapter_outline: 当前章节大纲
            target_word_count: 目标字数
            style_sample_path: 风格样本路径
            style_profile: 风格档案
            characters: 人物设定
            worldview: 世界观设定
            previous_chapter_text: 上一章内容
            max_iterations: 最大迭代次数
            callback: 完成回调
            
        Returns:
            流水线ID
        """
        config = NovelGenerationConfig(
            chapter_title=chapter_title,
            chapter_number=chapter_number,
            target_word_count=target_word_count,
            outline_content=outline_content,
            chapter_outline=chapter_outline,
            style_sample_path=style_sample_path,
            style_profile=style_profile or {},
            characters=characters or [],
            worldview=worldview or {},
            max_iterations=max_iterations,
            previous_chapter_text=previous_chapter_text,
        )
        
        # 包装回调
        def _callback_wrapper(result: PipelineExecutionResult):
            with self._lock:
                if self._current_pipeline_id == result.pipeline_id:
                    self._current_pipeline_id = None
            
            if callback:
                try:
                    callback(result)
                except Exception as e:
                    logger.error(f"回调执行异常: {e}")
        
        with self._lock:
            pipeline_id = self._orchestrator.execute_novel_generation_async(
                config=config,
                callback=_callback_wrapper,
            )
            self._current_pipeline_id = pipeline_id
        
        return pipeline_id
    
    def generate_chapter_sync(
        self,
        chapter_title: str,
        chapter_number: int,
        outline_content: str,
        chapter_outline: str,
        **kwargs
    ) -> PipelineExecutionResult:
        """
        生成章节内容（同步）
        
        Returns:
            流水线执行结果
        """
        config = NovelGenerationConfig(
            chapter_title=chapter_title,
            chapter_number=chapter_number,
            outline_content=outline_content,
            chapter_outline=chapter_outline,
            **kwargs
        )
        
        return self._orchestrator.execute_novel_generation(config)
    
    def cancel_generation(self) -> bool:
        """取消当前生成"""
        return self._orchestrator.cancel()
    
    def get_generation_state(self) -> PipelineState:
        """获取当前生成状态"""
        return self._orchestrator.get_state()
    
    def get_generation_result(self, pipeline_id: str) -> Optional[PipelineExecutionResult]:
        """获取生成结果"""
        return self._orchestrator.get_result(pipeline_id)
    
    # === 进度回调 ===
    
    def add_progress_callback(
        self,
        callback: Callable[[GenerationProgress], None]
    ) -> None:
        """添加进度回调"""
        self._progress_callbacks.append(callback)
    
    def remove_progress_callback(
        self,
        callback: Callable[[GenerationProgress], None]
    ) -> None:
        """移除进度回调"""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)
    
    def _on_progress(
        self,
        pipeline_id: str,
        stage_name: str,
        progress_percent: float,
        iteration: int = 1,
        max_iterations: int = 5,
    ) -> None:
        """内部进度处理
        
        P2修复：支持迭代信息传递
        """
        progress = GenerationProgress(
            pipeline_id=pipeline_id,
            stage_name=stage_name,
            progress_percent=progress_percent,
            iteration=iteration,
            max_iterations=max_iterations,
            message=f"[迭代{iteration}/{max_iterations}] 正在执行: {stage_name}",
        )
        
        for callback in self._progress_callbacks:
            try:
                callback(progress)
            except Exception as e:
                logger.error(f"进度回调异常: {e}")
    
    # === 清理 ===
    
    def shutdown(self) -> None:
        """关闭服务"""
        self._orchestrator.shutdown()
        
        # 清理所有Agent
        for agent in self._agents.values():
            try:
                agent.cleanup()
            except Exception as e:
                logger.error(f"清理Agent失败: {e}")
        
        self._agents.clear()
        logger.info("NovelGenerationService已关闭")


# === 单例模式 ===

_service_instance: Optional[NovelGenerationService] = None
_service_lock = threading.Lock()


def get_generation_service(
    event_bus=None,
    llm_client=None,
) -> NovelGenerationService:
    """
    获取生成服务单例
    
    Args:
        event_bus: 事件总线
        llm_client: LLM客户端
        
    Returns:
        NovelGenerationService实例
    """
    global _service_instance
    
    with _service_lock:
        if _service_instance is None:
            _service_instance = NovelGenerationService(
                event_bus=event_bus,
                llm_client=llm_client,
            )
        elif llm_client:
            _service_instance.set_llm_client(llm_client)
        
        return _service_instance
