"""
大纲分析Agent - OutlineAnalysisAgent

调用 outline-parser-v3 插件，实现 Analyzer 能力

功能:
- 解析小说大纲文件
- 提取章节结构
- 识别情节要点
- 计算预估字数

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


class OutlineAnalysisAgent(BaseAgent):
    """大纲分析Agent - 调用 outline-parser-v3 插件
    
    实现 Analyzer 能力:
    - 解析Markdown/TXT大纲文件
    - 提取章节结构和元数据
    - 识别关键情节和人物
    - 计算预估字数
    
    被MasterAgent调度，用于小说创作前的准备工作。
    """
    
    # 类常量
    AGENT_TYPE = "outline_analysis"
    PLUGIN_ID = "outline-parser-v3"
    
    def __init__(self):
        """初始化大纲分析Agent"""
        metadata = AgentMetadata(
            agent_type=self.AGENT_TYPE,
            name="大纲分析Agent",
            description="调用 outline-parser-v3 插件进行大纲解析分析",
            version="1.0.0",
            capabilities=[AgentCapability.ANALYSIS],
            dependencies=[],
            tags=["outline", "parser", "analysis", "structure"],
            author="项目组",
            priority=100,
            timeout_seconds=60,
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
                    from plugins.outline_parser_v3.plugin import OutlineParserPlugin
                    self._plugin = OutlineParserPlugin()
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
        """执行大纲分析任务
        
        Args:
            task_id: 任务ID
            payload: 任务载荷
                - content: 大纲文本内容
                - file_path: 大纲文件路径（可选）
                - options: 解析选项（可选）
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
            options = payload.get("options", {})
            
            # 调用插件进行分析
            if file_path:
                # 文件解析
                result = self._plugin.parse_file(file_path)
            else:
                # 内容解析
                result = self._plugin.analyze(content, options)
            
            # 检查结果
            if result.get("success"):
                # 转换为AgentResult
                agent_result = AgentResult.success_result(
                    task_id=task_id,
                    agent_type=self.AGENT_TYPE,
                    data=result,
                    metadata={
                        "chapter_count": result.get("total_chapters", 0),
                        "estimated_words": result.get("total_estimated_words", 0),
                        "extraction_method": result.get("extraction_method", "unknown"),
                    }
                )
                self._increment_completed()
                self._logger.info(f"[{self.AGENT_TYPE}] 任务完成: {task_id}, 章节数: {result.get('total_chapters', 0)}")
            else:
                agent_result = AgentResult.failure_result(
                    task_id=task_id,
                    agent_type=self.AGENT_TYPE,
                    error=result.get("error", "解析失败"),
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
            "outline_analysis",
            "outline_parse",
            "outline_extract",
            "structure_analysis",
        ]
        
        if task_type in supported_types:
            return True
        
        # 检查payload中是否有大纲相关内容
        if payload.get("content") or payload.get("file_path"):
            if any(kw in task_type.lower() for kw in ["outline", "大纲", "结构", "structure"]):
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
    return OutlineAnalysisAgent


def register_agent():
    """注册Agent"""
    return OutlineAnalysisAgent
