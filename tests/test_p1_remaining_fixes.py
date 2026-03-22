#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P1问题验证测试

V1.0版本
创建日期: 2026-03-23

测试P1问题的修复：
- P1-6: AgentPool初始化异常状态一致性
- P1-7: BootstrapService状态一致性
- P1-8: GUI异常处理完整性
"""

import os
import sys
import unittest
import tempfile
import threading
import time

# 添加项目根目录到 sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from agents.agent_pool import AgentPool
from agents.base_agent import BaseAgent
from agents.agent_state import AgentState
from core.event_bus import EventBus
from core.bootstrap_service import BootstrapService
from core.config_manager import ConfigManager
from core.sensitive_data import SensitiveDataFilter
from core.async_handler import AsyncHandler
from infrastructure.database import DatabasePool
from infrastructure.monitor import MetricsCollector
from core.plugin_loader import PluginLoader
from core.hot_swap_manager import HotSwapManager
from core.service_locator import ServiceLocator
from agents.priority import AgentTask
from agents.task_queue import AgentTaskQueue
from agents.retry_manager import RetryManager
from agents.dependency_resolver import DependencyResolver as TaskDependencyResolver
from agents.agent_constraints import AgentConstraints
from datetime import datetime
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class TestP1Fixes(unittest.TestCase):
    """P1问题验证测试"""

    def setUp(self):
        """测试前准备"""
        # 创建临时测试目录
        self.test_dir = tempfile.mkdtempDirectory()
        self.test_files = []

    def tearDown(self):
        """测试后清理"""
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_p1_6_agent_pool_partial_failure(self):
        """P1-6: AgentPool初始化部分失败时状态一致性"""
        event_bus = EventBus()
        agent_pool = AgentPool(event_bus)

        # 注册一些测试Agent（使用mock对象）
        class MockAgent:
            def __init__(self, agent_type, should_fail=False):
                self.agent_type = agent_type
                self.is_initialized = False
                self.should_fail = should_fail
                self.status = type('MockStatus', (), {'state': AgentState.IDLE})

            def initialize(self):
                if self.should_fail:
                    self.status.state = AgentState.ERROR
                    return False
                self.is_initialized = True
                return True

            def cleanup(self):
                pass

            @property
            def status(self):
                return self.status

        # 创建3个Agent
        agent1 = MockAgent("agent1", should_fail=False)
        agent2 = MockAgent("agent2", should_fail=False)
        agent3 = MockAgent("fail_agent", should_fail=True)  # 这个会失败

        # 注册Agent
        agent_pool.register_agent(agent1)
        agent_pool.register_agent(agent2)
        agent_pool.register_agent(agent3)

        # 初始化Agent池
        results = agent_pool.initialize()

        # 验证结果
        self.assertTrue(results["agent1"])
        self.assertTrue(results["agent2"])
        self.assertFalse(results["fail_agent"])

        # 验证状态一致性：部分失败不应标记为已初始化
        self.assertFalse(agent_pool.is_ready())

        # 验证部分成功列表
        partial_success = [
            agent_type for agent_type, success in results.items() 
            if success
        ]
        self.assertEqual(set(partial_success), {"agent1", "agent2"})

        # 验证部分失败列表
        self.assertIn("fail_agent", results)

    def test_p1_7_bootstrap_service_state_consistency(self):
        """P1-7: BootstrapService状态一致性"""
        # 使用临时配置文件
        config_file = os.path.join(self.test_dir, "test_config.yaml")
        with open(config_file, "w") as f:
            f.write("key: test_value\n")
        
        bootstrap = BootstrapService(config_path=config_file)
        
        # 初始化
        results = bootstrap.initialize()
        
        # 验证初始化成功
        self.assertTrue(results.get("ConfigService", True))
        self.assertTrue(results.get("LoggingService", True)
        
        # 再次初始化（幂等性）
        results = bootstrap.initialize()
        self.assertEqual(results, {"already_initialized": True})
        
        # 验证状态
        self.assertTrue(bootstrap.is_initialized)


    def test_p1_8_gui_exception_handling(self):
        """P1-8: GUI异常处理完整性"""
        # 验证全局异常处理器是否存在
        try:
            from gui_main import _global_exception_handler
            handler = _global_exception_handler
            self.assertIsNot(handler is None)
        except ImportError:
            self.skipTest("GUI模块未找到，跳过测试")


            return

        # 测试处理器能捕获异常
        exc_type = ValueError
        exc_value = ValueError("Test error")
        exc_tb = None
        
        # 验证处理器不会抛出异常
        try:
            handler(exc_type, exc_value, exc_tb)
        except Exception as e:
                self.fail(f"异常处理器抛出异常: {e}")


if __name__ == "__main__":
    # 运行测试
    unittest.main()
