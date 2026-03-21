"""
Agent热插拔注册表

V2.0版本
创建日期: 2026-03-21

特性:
- 动态加载/卸载Agent
- 文件监控（轮询方式）
- 热重载支持
"""

import threading
import logging
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
import importlib.util
import sys

from agents.base_agent import BaseAgent
from agents.agent_state import AgentState
from core.event_bus import EventBus

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Agent注册表

    管理Agent的动态加载、卸载和热重载
    """

    def __init__(self, event_bus: EventBus, plugins_dir: str = "plugins/agents"):
        """
        初始化Agent注册表

        Args:
            event_bus: 事件总线实例
            plugins_dir: Agent插件目录
        """
        self._event_bus = event_bus
        self._plugins_dir = Path(plugins_dir)
        self._agent_classes: Dict[str, type] = {}
        self._agent_modules: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._running = False
        self._watch_thread: Optional[threading.Thread] = None
        self._file_mtimes: Dict[str, float] = {}

    def initialize(self) -> None:
        """初始化注册表"""
        # 创建插件目录
        self._plugins_dir.mkdir(parents=True, exist_ok=True)

        # 扫描现有Agent插件
        self._scan_plugins()

        # 启动文件监控
        self._start_watcher()

        logger.info(f"Agent注册表初始化完成，已注册{len(self._agent_classes)}个Agent")

    def _scan_plugins(self) -> None:
        """扫描插件目录"""
        if not self._plugins_dir.exists():
            return

        for plugin_file in self._plugins_dir.glob("*.py"):
            if plugin_file.name.startswith("_"):
                continue
            self._load_agent_from_file(plugin_file)

    def _load_agent_from_file(self, file_path: Path) -> bool:
        """
        从文件加载Agent

        Args:
            file_path: 插件文件路径

        Returns:
            是否加载成功
        """
        try:
            # 动态导入模块
            module_name = f"agents.plugins.{file_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 查找Agent类
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseAgent)
                    and attr is not BaseAgent
                ):
                    agent_type = attr_name.lower().replace("agent", "")

                    with self._lock:
                        self._agent_classes[agent_type] = attr
                        self._agent_modules[agent_type] = module
                        self._file_mtimes[str(file_path)] = file_path.stat().st_mtime

                    # 发布事件
                    self._event_bus.publish(
                        "agent.loaded",
                        {"agent_type": agent_type, "file": str(file_path)},
                        source="AgentRegistry",
                    )

                    logger.info(f"Agent注册成功: {agent_type}")
                    return True

            logger.warning(f"未找到Agent类: {file_path}")
            return False

        except Exception as e:
            logger.error(f"加载Agent失败 {file_path}: {e}", exc_info=True)
            return False

    def reload_agent_from_file(self, file_path: Path) -> bool:
        """
        重新加载Agent

        Args:
            file_path: 插件文件路径

        Returns:
            是否重载成功
        """
        agent_type = file_path.stem.lower().replace("_agent", "")

        # 卸载旧Agent
        if agent_type in self._agent_classes:
            self._unload_agent(agent_type)

        # 加载新Agent
        return self._load_agent_from_file(file_path)

    def unload_agent_from_file(self, file_path: Path) -> bool:
        """
        卸载Agent

        Args:
            file_path: 插件文件路径

        Returns:
            是否卸载成功
        """
        agent_type = file_path.stem.lower().replace("_agent", "")
        return self._unload_agent(agent_type)

    def _unload_agent(self, agent_type: str) -> bool:
        """
        卸载Agent

        Args:
            agent_type: Agent类型

        Returns:
            是否卸载成功
        """
        with self._lock:
            if agent_type not in self._agent_classes:
                return False

            try:
                # 从sys.modules移除
                module = self._agent_modules[agent_type]
                module_name = module.__name__
                if module_name in sys.modules:
                    del sys.modules[module_name]

                # 从注册表移除
                del self._agent_classes[agent_type]
                del self._agent_modules[agent_type]

                # 发布事件
                self._event_bus.publish(
                    "agent.unloaded", {"agent_type": agent_type}, source="AgentRegistry"
                )

                logger.info(f"Agent卸载成功: {agent_type}")
                return True

            except Exception as e:
                logger.error(f"卸载Agent失败 {agent_type}: {e}")
                return False

    def get_agent_class(self, agent_type: str) -> Optional[type]:
        """
        获取Agent类

        Args:
            agent_type: Agent类型

        Returns:
            Agent类，不存在返回None
        """
        with self._lock:
            return self._agent_classes.get(agent_type)

    def list_agents(self) -> List[str]:
        """列出所有已注册Agent"""
        with self._lock:
            return list(self._agent_classes.keys())

    def _start_watcher(self) -> None:
        """启动文件监控（轮询方式）"""
        if self._running:
            return

        self._running = True
        self._watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watch_thread.start()
        logger.info("Agent插件监控已启动")

    def _watch_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                if self._plugins_dir.exists():
                    for plugin_file in self._plugins_dir.glob("*.py"):
                        if plugin_file.name.startswith("_"):
                            continue

                        current_mtime = plugin_file.stat().st_mtime
                        file_key = str(plugin_file)

                        if file_key in self._file_mtimes:
                            if current_mtime > self._file_mtimes[file_key]:
                                # 文件已修改
                                logger.info(f"检测到Agent插件更新: {plugin_file}")
                                self.reload_agent_from_file(plugin_file)
                        else:
                            # 新文件
                            logger.info(f"检测到新Agent插件: {plugin_file}")
                            self._load_agent_from_file(plugin_file)

                        self._file_mtimes[file_key] = current_mtime

                time.sleep(2)  # 每2秒检查一次

            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                time.sleep(5)

    def stop(self) -> None:
        """停止监控"""
        self._running = False
        if self._watch_thread:
            self._watch_thread.join(timeout=2)
