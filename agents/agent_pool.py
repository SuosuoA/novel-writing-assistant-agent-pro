"""
Agent池管理器

V2.0版本
创建日期: 2026-03-21

特性:
- Agent注册与管理
- 热插拔支持
- 健康检查
"""

import threading
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from .base_agent import BaseAgent
from .agent_state import AgentState
from core.event_bus import EventBus

logger = logging.getLogger(__name__)


class AgentPool:
    """
    Agent池

    管理所有Agent实例，提供注册、注销、获取等功能
    """

    def __init__(self, event_bus: EventBus):
        """
        初始化Agent池

        Args:
            event_bus: 事件总线实例
        """
        self._agents: Dict[str, BaseAgent] = {}
        self._event_bus = event_bus
        self._initialized = False
        self._lock = threading.RLock()

    def initialize(self) -> None:
        """初始化Agent池"""
        if self._initialized:
            return

        with self._lock:
            # 初始化所有已注册的Agent
            for agent_type, agent in self._agents.items():
                if not agent.is_initialized:
                    try:
                        agent.initialize()
                        logger.info(f"Agent初始化成功: {agent_type}")
                    except Exception as e:
                        logger.error(f"Agent初始化失败 {agent_type}: {e}")

            # 发布Agent池就绪事件
            self._event_bus.publish(
                "agent.pool.ready",
                {"agents": list(self._agents.keys())},
                source="AgentPool",
            )

            self._initialized = True
            logger.info(f"Agent池初始化完成，共 {len(self._agents)} 个Agent")

    def register_agent(self, agent: BaseAgent) -> bool:
        """
        注册Agent

        Args:
            agent: Agent实例

        Returns:
            是否注册成功
        """
        with self._lock:
            if agent.agent_type in self._agents:
                logger.warning(f"Agent已存在，将覆盖: {agent.agent_type}")

            try:
                # 如果Agent池已初始化，立即初始化新Agent
                if self._initialized:
                    if not agent.initialize():
                        logger.error(f"Agent初始化失败: {agent.agent_type}")
                        return False

                self._agents[agent.agent_type] = agent

                # 发布Agent注册事件
                self._event_bus.publish(
                    "agent.registered",
                    {"agent_type": agent.agent_type},
                    source="AgentPool",
                )

                logger.info(f"Agent注册成功: {agent.agent_type}")
                return True

            except Exception as e:
                logger.error(f"Agent注册失败 {agent.agent_type}: {e}")
                return False

    def unregister_agent(self, agent_type: str) -> bool:
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

            try:
                agent = self._agents[agent_type]

                # 清理资源
                agent.cleanup()

                # 从池中移除
                del self._agents[agent_type]

                # 发布Agent注销事件
                self._event_bus.publish(
                    "agent.unregistered", {"agent_type": agent_type}, source="AgentPool"
                )

                logger.info(f"Agent注销成功: {agent_type}")
                return True

            except Exception as e:
                logger.error(f"Agent注销失败 {agent_type}: {e}")
                return False

    def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        """
        获取Agent实例

        Args:
            agent_type: Agent类型

        Returns:
            Agent实例，不存在返回None
        """
        with self._lock:
            return self._agents.get(agent_type)

    def list_agents(self) -> List[str]:
        """
        列出所有Agent类型

        Returns:
            Agent类型列表
        """
        with self._lock:
            return list(self._agents.keys())

    def get_active_agents(self) -> List[str]:
        """
        获取所有活跃状态的Agent

        Returns:
            活跃Agent类型列表
        """
        with self._lock:
            return [
                agent_type
                for agent_type, agent in self._agents.items()
                if agent.status.state == AgentState.ACTIVE
            ]

    def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """
        检查所有Agent健康状态

        Returns:
            各Agent健康状态
        """
        results = {}
        with self._lock:
            for agent_type, agent in self._agents.items():
                try:
                    results[agent_type] = agent.health_check()
                except Exception as e:
                    results[agent_type] = {"status": "error", "error": str(e)}
        return results

    def cleanup_all(self) -> None:
        """清理所有Agent资源"""
        with self._lock:
            for agent_type, agent in self._agents.items():
                try:
                    agent.cleanup()
                except Exception as e:
                    logger.error(f"清理Agent失败 {agent_type}: {e}")

            self._agents.clear()
            self._initialized = False

            logger.info("Agent池已清理")

    def reload_agent(self, agent_type: str) -> bool:
        """
        重新加载Agent

        Args:
            agent_type: Agent类型

        Returns:
            是否重载成功
        """
        with self._lock:
            agent = self._agents.get(agent_type)
            if not agent:
                logger.warning(f"Agent不存在: {agent_type}")
                return False

            try:
                # 先清理
                agent.cleanup()

                # 重新初始化
                if agent.initialize():
                    logger.info(f"Agent重载成功: {agent_type}")
                    return True
                else:
                    logger.error(f"Agent重载失败: {agent_type}")
                    return False

            except Exception as e:
                logger.error(f"Agent重载异常 {agent_type}: {e}")
                return False

    def get_agent_count(self) -> int:
        """获取Agent数量"""
        with self._lock:
            return len(self._agents)

    def is_ready(self) -> bool:
        """Agent池是否就绪"""
        return self._initialized
