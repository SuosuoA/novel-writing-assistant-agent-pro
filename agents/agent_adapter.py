"""
Agent适配器基类

V2.0版本
创建日期: 2026-03-21

特性:
- 动态模块加载
- V5模块包装
- 错误处理
"""

import importlib
import logging
from typing import Any

from .base_agent import BaseAgent
from .priority import AgentTask
from .agent_state import AgentState

logger = logging.getLogger(__name__)


class AgentAdapter(BaseAgent):
    """
    Agent适配器基类

    用于将V5现有模块包装为Agent能力
    采用适配器模式，实现零额外依赖
    """

    def __init__(
        self, agent_type: str, module_path: str, class_name: str, init_args: dict = None
    ):
        """
        初始化适配器

        Args:
            agent_type: Agent类型标识
            module_path: 模块路径（如 scripts.outline_parser_v3）
            class_name: 类名（如 OutlineParserV3）
            init_args: 初始化参数
        """
        super().__init__(agent_type)
        self._module_path = module_path
        self._class_name = class_name
        self._init_args = init_args or {}
        self._wrapped_instance = None

    def initialize(self) -> bool:
        """
        初始化适配器

        实现细节:
        1. 动态导入模块
        2. 获取类
        3. 创建实例
        4. 调用initialize方法（如果存在）

        Returns:
            是否初始化成功
        """
        try:
            self._set_state(AgentState.LOADED)

            # 动态导入模块
            module = importlib.import_module(self._module_path)

            # 获取类
            cls = getattr(module, self._class_name)

            # 创建实例
            self._wrapped_instance = cls(**self._init_args)

            # 调用initialize方法（如果存在）
            if hasattr(self._wrapped_instance, "initialize"):
                init_result = self._wrapped_instance.initialize()
                # 如果initialize返回False，则初始化失败
                if init_result is False:
                    self._set_state(AgentState.ERROR)
                    self._set_error("包装实例初始化失败")
                    return False

            self._set_state(AgentState.ACTIVE)
            self._initialized = True
            logger.info(f"Agent适配器初始化成功: {self.agent_type}")
            return True

        except Exception as e:
            self._set_state(AgentState.ERROR)
            self._set_error(str(e))
            logger.error(f"Agent适配器初始化失败 {self.agent_type}: {e}", exc_info=True)
            return False

    def execute(self, task: AgentTask) -> Any:
        """
        执行任务（委托给包装实例）

        Args:
            task: 任务对象

        Returns:
            执行结果
        """
        if not self._initialized or not self._wrapped_instance:
            raise RuntimeError(f"Agent {self.agent_type} 未初始化")

        try:
            # 调用包装实例的execute方法
            if hasattr(self._wrapped_instance, "execute"):
                method = getattr(self._wrapped_instance, "execute")
                result = method(task)
            elif hasattr(self._wrapped_instance, "process"):
                # 兼容V5模块的process方法
                method = getattr(self._wrapped_instance, "process")
                result = method(task.payload)
            else:
                raise AttributeError(
                    f"包装实例 {self._class_name} 没有 execute 或 process 方法"
                )

            # 更新状态
            self._increment_completed()
            return result

        except Exception as e:
            self._increment_failed()
            self._set_error(str(e))
            logger.error(f"Agent执行失败 {self.agent_type}: {e}", exc_info=True)
            raise

    def can_handle(self, task: AgentTask) -> bool:
        """
        判断是否能处理该任务

        Args:
            task: 任务对象

        Returns:
            是否能处理
        """
        return task.agent_type == self.agent_type

    def cleanup(self) -> bool:
        """
        清理资源

        Returns:
            是否清理成功
        """
        if self._wrapped_instance and hasattr(self._wrapped_instance, "cleanup"):
            try:
                self._wrapped_instance.cleanup()
            except Exception as e:
                logger.error(f"清理Agent资源失败 {self.agent_type}: {e}")

        self._wrapped_instance = None
        self._initialized = False
        self._set_state(AgentState.UNLOADED)
        return True

    def get_wrapped_instance(self) -> Any:
        """获取包装实例"""
        return self._wrapped_instance
