"""
大纲解析器适配器

V2.0版本
创建日期: 2026-03-21
"""

import logging
from typing import Any, Dict

from ..agent_adapter import AgentAdapter
from ..priority import AgentTask

logger = logging.getLogger(__name__)


class OutlineParserAdapter(AgentAdapter):
    """
    大纲解析器适配器

    包装 scripts.outline_parser_v3.OutlineParserV3
    """

    def __init__(self):
        super().__init__(
            agent_type="outline_parser",
            module_path="scripts.outline_parser_v3",
            class_name="OutlineParserV3",
        )

    def execute(self, task: AgentTask) -> Dict[str, Any]:
        """
        执行大纲解析

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
                payload.get("outline_content"), **payload.get("options", {})
            )

            # 更新状态
            self._increment_completed()

            return {
                "task_id": task.task_id,
                "result": result,
                "metadata": {
                    "chapter_count": len(result.get("chapters", [])),
                    "total_words": result.get("total_words", 0),
                },
            }

        except Exception as e:
            self._increment_failed()
            self._set_error(str(e))
            logger.error(f"大纲解析失败: {e}", exc_info=True)
            raise
