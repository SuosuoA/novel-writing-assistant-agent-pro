"""
质量验证Agent - QualityValidationAgent

调用 quality-validator-v1 插件，实现 Validator 能力

功能:
- 6维度加权评分系统
- 字数符合性评分 (10%)
- 大纲符合性评分 (15%)
- 风格一致性评分 (25%)
- 人设一致性评分 (25%)
- 世界观一致性评分 (20%，一票否决)
- 自然度评分 (5%)

核心规则（强制保护）:
1. 章节结束必须添加【本章完】标记
2. 评分阈值 >= 0.8 才能输出
3. 迭代上限 5 次
4. 6维度评分权重固定
5. 世界观严重违背一票否决

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


class QualityValidationAgent(BaseAgent):
    """质量验证Agent - 调用 quality-validator-v1 插件
    
    实现 Validator 能力:
    - 6维度加权评分验证
    - 字数符合性评分 (10%)
    - 大纲符合性评分 (15%)
    - 风格一致性评分 (25%)
    - 人设一致性评分 (25%)
    - 世界观一致性评分 (20%，一票否决)
    - 自然度评分 (5%)
    
    核心规则（强制保护）:
    1. 章节结束必须添加【本章完】标记
    2. 评分阈值 >= 0.8 才能输出
    3. 迭代上限 5 次
    4. 6维度评分权重固定
    5. 世界观严重违背一票否决
    
    被MasterAgent调度，用于验证生成内容质量。
    """
    
    # 类常量
    AGENT_TYPE = "quality_validation"
    PLUGIN_ID = "quality-validator-v1"
    
    # 评分权重配置（强制保护 - 不可变更）
    WEIGHTS = {
        'word_count': 0.10,
        'outline': 0.15,
        'style': 0.25,
        'character': 0.25,
        'worldview': 0.20,
        'naturalness': 0.05
    }
    
    def __init__(self):
        """初始化质量验证Agent"""
        metadata = AgentMetadata(
            agent_type=self.AGENT_TYPE,
            name="质量验证Agent",
            description="调用 quality-validator-v1 插件进行6维度加权评分验证",
            version="1.0.0",
            capabilities=[AgentCapability.VALIDATION],
            dependencies=[],
            tags=["quality", "validation", "scoring", "review"],
            author="项目组",
            priority=100,
            timeout_seconds=30,  # 验证任务通常较快
            max_retries=0,  # 验证不重试
            max_concurrent_tasks=3,  # 可以并行验证多个内容
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
                    from plugins.quality_validator_v1.plugin import QualityValidatorPlugin
                    self._plugin = QualityValidatorPlugin()
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
        """执行质量验证任务
        
        Args:
            task_id: 任务ID
            payload: 任务载荷
                - content: 待验证内容
                - target_word_count: 目标字数
                - chapter_outline: 章节大纲（可选）
                - style_profile: 风格配置（可选）
                - character_profiles: 人物设定列表（可选）
                - world_view: 世界观设定（可选）
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
            target_word_count = payload.get("target_word_count", 2000)
            chapter_outline = payload.get("chapter_outline")
            style_profile = payload.get("style_profile")
            character_profiles = payload.get("character_profiles")
            world_view = payload.get("world_view")
            
            # 构建验证上下文
            validation_context = {
                'target_word_count': target_word_count,
                'chapter_outline': chapter_outline,
                'style_profile': style_profile,
                'character_profiles': character_profiles,
                'world_view': world_view,
            }
            
            # 调用插件进行验证
            scores = self._plugin.validate(content, validation_context)
            
            # 检查验证结果
            if scores:
                # 转换为AgentResult
                agent_result = AgentResult.success_result(
                    task_id=task_id,
                    agent_type=self.AGENT_TYPE,
                    data={
                        "scores": {
                            "word_count_score": scores.word_count_score,
                            "outline_score": scores.outline_score,
                            "style_score": scores.style_score,
                            "character_score": scores.character_score,
                            "worldview_score": scores.worldview_score,
                            "naturalness_score": scores.naturalness_score,
                            "total_score": scores.total_score,
                        },
                        "has_chapter_end": scores.has_chapter_end,
                        "passed": scores.passed,
                    },
                    metadata={
                        "total_score": scores.total_score,
                        "passed": scores.passed,
                        "has_chapter_end": scores.has_chapter_end,
                        "word_count_score": scores.word_count_score,
                        "style_score": scores.style_score,
                    }
                )
                self._increment_completed()
                self._logger.info(f"[{self.AGENT_TYPE}] 任务完成: {task_id}, 总分: {scores.total_score:.3f}, 通过: {scores.passed}, 结束标记: {scores.has_chapter_end}")
            else:
                agent_result = AgentResult.failure_result(
                    task_id=task_id,
                    agent_type=self.AGENT_TYPE,
                    error="验证失败：无法获取评分结果",
                    error_type="ValidationError"
                )
                self._increment_failed()
                self._logger.error(f"[{self.AGENT_TYPE}] 任务失败: {task_id}")
            
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
            "quality_validation",
            "content_validation",
            "score_validation",
            "validate_quality",
        ]
        
        if task_type in supported_types:
            return True
        
        # 检查payload中是否有验证相关内容
        if payload.get("content"):
            if any(kw in task_type.lower() for kw in ["valid", "验证", "评分", "score", "quality", "质量"]):
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
    return QualityValidationAgent


def register_agent():
    """注册Agent"""
    return QualityValidationAgent
