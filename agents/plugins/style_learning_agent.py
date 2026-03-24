"""
风格学习Agent - StyleLearningAgent

调用 style-learner-v5 插件，实现 Analyzer 能力

功能:
- 分析文本风格特征
- 提取词汇、句式、修辞模式
- 识别叙事风格和情感色彩
- 生成风格档案

创建日期: 2026-03-23
"""

import logging
from typing import Any, Dict, Optional

import sys
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from agents.core.base_agent import (
    BaseAgent,
    AgentMetadata,
    AgentContext,
    AgentResult,
    AgentState,
    AgentCapability,
)


class StyleLearningAgent(BaseAgent):
    """风格学习Agent - 调用 style-learner-v5 插件
    
    实现 Analyzer 能力:
    - 分析词汇特征（高频词、低频词、专有名词）
    - 识别句式模式（倒装句、排比句、设问句）
    - 检测修辞手法（比喻、拟人、夸张）
    - 分析叙事风格和情感色彩
    - 生成完整风格档案
    
    被MasterAgent调度，用于学习目标写作风格。
    """
    
    # 类常量
    AGENT_TYPE = "style_learning"
    PLUGIN_ID = "style-learner-v5"
    
    def __init__(self):
        """初始化风格学习Agent"""
        metadata = AgentMetadata(
            agent_type=self.AGENT_TYPE,
            name="风格学习Agent",
            description="调用 style-learner-v5 插件进行深度风格分析学习",
            version="1.0.0",
            capabilities=[AgentCapability.ANALYSIS],
            dependencies=[],
            tags=["style", "learning", "analysis", "writing"],
            author="项目组",
            priority=100,
            timeout_seconds=120,  # 风格分析可能需要较长时间
            max_retries=1,
            max_concurrent_tasks=1,
        )
        super().__init__(self.AGENT_TYPE, metadata)
        
        # 插件引用（延迟初始化）
        self._plugin = None
        self._logger = logging.getLogger(f"agent.{self.AGENT_TYPE}")
    
    def initialize(self) -> bool:
        """初始化Agent
        
        Returns:
            是否初始化成功
        """
        try:
            self._set_state(AgentState.LOADED)
            
            # 尝试从服务定位器获取插件
            if self._service_locator:
                try:
                    self._plugin = self._service_locator.try_get(self.PLUGIN_ID)
                    if self._plugin:
                        self._logger.info(f"[{self.AGENT_TYPE}] 从服务定位器获取插件成功: {self.PLUGIN_ID}")
                except Exception as e:
                    self._logger.warning(f"[{self.AGENT_TYPE}] 服务定位器获取插件失败: {e}")
            
            # 如果没有获取到，尝试动态导入
            if not self._plugin:
                try:
                    from plugins.style_learner_v5.plugin import StyleLearnerPlugin
                    self._plugin = StyleLearnerPlugin()
                    self._logger.info(f"[{self.AGENT_TYPE}] 创建本地插件实例: {self.PLUGIN_ID}")
                except ImportError as e:
                    self._logger.error(f"[{self.AGENT_TYPE}] 无法导入插件: {e}")
                    self._set_state(AgentState.ERROR)
                    self._set_error(f"插件导入失败: {e}")
                    return False
            
            self._initialized = True
            self._set_state(AgentState.ACTIVE)
            self._logger.info(f"[{self.AGENT_TYPE}] 初始化完成")
            return True
            
        except Exception as e:
            self._set_state(AgentState.ERROR)
            self._set_error(str(e))
            self._logger.error(f"[{self.AGENT_TYPE}] 初始化失败: {e}", exc_info=True)
            return False
    
    def execute(
        self,
        task_id: str,
        payload: Dict[str, Any],
        context: AgentContext = None
    ) -> AgentResult:
        """执行风格学习任务
        
        Args:
            task_id: 任务ID
            payload: 任务载荷
                - content: 样本文本内容
                - file_path: 样本文件路径（可选）
                - author_name: 作者名称（可选）
                - genre: 作品类型（可选）
                - analysis_type: 分析类型 (full/vocabulary/sentence/rhetoric/narrative/emotion)
            context: 执行上下文
            
        Returns:
            AgentResult 执行结果
        """
        if not self._initialized or not self._plugin:
            return AgentResult.failure_result(
                task_id=task_id,
                agent_type=self.AGENT_TYPE,
                error="Agent未初始化或插件不可用",
                error_type="InitializationError"
            )
        
        try:
            self._logger.info(f"[{self.AGENT_TYPE}] 开始执行任务: {task_id}")
            self._status.current_task_id = task_id
            
            # 提取参数
            content = payload.get("content", "")
            file_path = payload.get("file_path")
            options = {
                "author_name": payload.get("author_name", "未知作者"),
                "genre": payload.get("genre", "未知类型"),
                "analysis_type": payload.get("analysis_type", "full"),
            }
            
            # 调用插件进行分析
            if file_path:
                result = self._plugin.analyze(file_path, options)
            else:
                result = self._plugin.analyze(content, options)
            
            # 检查结果
            if result.get("success"):
                # 转换为AgentResult
                agent_result = AgentResult.success_result(
                    task_id=task_id,
                    agent_type=self.AGENT_TYPE,
                    data=result,
                    metadata={
                        "author_name": result.get("author_name", "未知作者"),
                        "genre": result.get("genre", "未知类型"),
                        "sample_size_chars": result.get("sample_size_chars", 0),
                        "style_tags": result.get("style_tags", []),
                        "writing_characteristics": result.get("writing_characteristics", []),
                    }
                )
                self._increment_completed()
                self._logger.info(f"[{self.AGENT_TYPE}] 任务完成: {task_id}, 作者: {result.get('author_name')}, 样本: {result.get('sample_size_chars')}字")
            else:
                agent_result = AgentResult.failure_result(
                    task_id=task_id,
                    agent_type=self.AGENT_TYPE,
                    error=result.get("error", "风格分析失败"),
                    error_type="AnalysisError"
                )
                self._increment_failed()
                self._logger.error(f"[{self.AGENT_TYPE}] 任务失败: {task_id}, 错误: {result.get('error')}")
            
            self._status.current_task_id = None
            return agent_result
            
        except Exception as e:
            self._increment_failed()
            self._set_error(str(e))
            self._status.current_task_id = None
            self._logger.error(f"[{self.AGENT_TYPE}] 执行异常: {e}", exc_info=True)
            return AgentResult.failure_result(
                task_id=task_id,
                agent_type=self.AGENT_TYPE,
                error=str(e),
                error_type="ExecutionError"
            )
    
    def can_handle(self, task_type: str, payload: Dict[str, Any]) -> bool:
        """判断是否能处理该任务
        
        Args:
            task_type: 任务类型
            payload: 任务载荷
            
        Returns:
            是否能处理
        """
        # 可以处理的任务类型
        supported_types = [
            "style_learning",
            "style_analysis",
            "style_extract",
            "writing_style",
        ]
        
        if task_type in supported_types:
            return True
        
        # 检查payload中是否有风格相关内容
        if payload.get("content") or payload.get("file_path"):
            if any(kw in task_type.lower() for kw in ["style", "风格", "写作", "writing"]):
                return True
        
        return False
    
    def cleanup(self) -> bool:
        """清理资源
        
        Returns:
            是否清理成功
        """
        try:
            self._plugin = None
            self._initialized = False
            self._set_state(AgentState.UNLOADED)
            self._logger.info(f"[{self.AGENT_TYPE}] 资源清理完成")
            return True
        except Exception as e:
            self._logger.error(f"[{self.AGENT_TYPE}] 清理失败: {e}")
            return False


# 模块级函数（供AgentPool使用）
def get_agent_class():
    """获取Agent类"""
    return StyleLearningAgent


def register_agent():
    """注册Agent"""
    return StyleLearningAgent
