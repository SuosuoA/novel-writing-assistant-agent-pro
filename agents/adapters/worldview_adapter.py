"""
世界观解析器适配器

V2.0版本
创建日期: 2026-03-21
"""

import logging
from typing import Any, Dict

from ..agent_adapter import AgentAdapter
from ..priority import AgentTask

logger = logging.getLogger(__name__)


class WorldviewParserAdapter(AgentAdapter):
    """
    世界观解析器适配器

    包装 scripts.universal_worldview_parser.UniversalWorldviewParser
    """

    def __init__(self):
        super().__init__(
            agent_type="worldview_parser",
            module_path="scripts.universal_worldview_parser",
            class_name="UniversalWorldviewParser",
        )

    def execute(self, task: AgentTask) -> Dict[str, Any]:
        """
        执行世界观解析

        Args:
            task: 任务对象

        Returns:
            解析结果
        """
        if not self._initialized or not self._wrapped_instance:
            raise RuntimeError(f"Agent {self.agent_type} 未初始化")

        payload = task.payload

        try:
            # 调用V5模块的parse方法
            result = self._wrapped_instance.parse(
                payload.get("worldview_content"), **payload.get("options", {})
            )

            # 更新状态
            self._increment_completed()

            return {
                "task_id": task.task_id,
                "result": result,
                "metadata": {
                    "elements_count": len(result.get("elements", [])),
                    "rules_count": len(result.get("rules", [])),
                },
            }

        except Exception as e:
            self._increment_failed()
            self._set_error(str(e))
            logger.error(f"世界观解析失败: {e}", exc_info=True)
            raise
