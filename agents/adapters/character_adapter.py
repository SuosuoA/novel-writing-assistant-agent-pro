"""
人物管理器适配器

V2.0版本
创建日期: 2026-03-21
"""

import logging
from typing import Any, Dict

from ..agent_adapter import AgentAdapter
from ..priority import AgentTask

logger = logging.getLogger(__name__)


class CharacterManagerAdapter(AgentAdapter):
    """
    人物管理器适配器

    包装 scripts.enhanced_character_manager.CharacterManager
    """

    def __init__(self):
        super().__init__(
            agent_type="character_manager",
            module_path="scripts.enhanced_character_manager",
            class_name="CharacterManager",
        )

    def execute(self, task: AgentTask) -> Dict[str, Any]:
        """
        执行人物管理操作

        Args:
            task: 任务对象

        Returns:
            操作结果
        """
        if not self._initialized or not self._wrapped_instance:
            raise RuntimeError(f"Agent {self.agent_type} 未初始化")

        payload = task.payload
        operation = payload.get("operation", "get_character")

        try:
            # 根据操作类型调用不同方法
            if operation == "get_character":
                result = self._wrapped_instance.get_character(
                    payload.get("character_name")
                )
            elif operation == "add_character":
                result = self._wrapped_instance.add_character(
                    payload.get("character_data")
                )
            elif operation == "update_character":
                result = self._wrapped_instance.update_character(
                    payload.get("character_name"), payload.get("updates")
                )
            elif operation == "list_characters":
                result = self._wrapped_instance.list_characters()
            else:
                raise ValueError(f"未知操作: {operation}")

            # 更新状态
            self._increment_completed()

            return {
                "task_id": task.task_id,
                "result": result,
                "metadata": {"operation": operation},
            }

        except Exception as e:
            self._increment_failed()
            self._set_error(str(e))
            logger.error(f"人物管理操作失败: {e}", exc_info=True)
            raise
