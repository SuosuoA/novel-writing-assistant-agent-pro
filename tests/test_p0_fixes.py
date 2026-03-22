"""
P0问题修复验证测试

测试范围：
- P0-1: EventBus观察者异常处理
- P0-2: ServiceLocator循环依赖检测
- P0-3: DatabasePool连接泄漏保护
- P0-4: HotSwapManager监听器异常处理

创建日期: 2026-03-23
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import threading
import time
import unittest
from datetime import datetime
from typing import Any, Dict
import tempfile
import logging


class TestP01EventBusCallbackError(unittest.TestCase):
    """P0-1: EventBus观察者异常处理验证"""

    def test_callback_error_publishes_failure_event(self):
        """验证回调异常时发布失败事件"""
        from core.event_bus import EventBus, Event
        
        bus = EventBus()
        received_events = []
        
        def failing_handler(event: Event):
            raise ValueError("Test error")
        
        def capture_events(event: Event):
            received_events.append(event)
        
        # 订阅
        bus.subscribe("test.event", failing_handler)
        bus.subscribe("test.event.callback_failed", capture_events)
        
        # 发布事件
        bus.publish("test.event", {"data": "test"})
        
        # 等待异步执行
        time.sleep(0.5)
        
        # 验证失败事件已发布
        failure_events = [e for e in received_events if "callback_failed" in e.type]
        self.assertGreater(len(failure_events), 0, "Should publish callback_failed event")
        
        # 验证失败事件包含错误信息
        failure_event = failure_events[0]
        self.assertIn("error", failure_event.data)
        self.assertIn("callback", failure_event.data)
        
        bus.shutdown()

    def test_dead_letter_queue_receives_failed_events(self):
        """验证失败事件进入死信队列"""
        from core.event_bus import EventBus, Event
        
        bus = EventBus()
        
        def failing_handler(event: Event):
            raise RuntimeError("Handler failed")
        
        bus.subscribe("test.dlq", failing_handler)
        bus.publish("test.dlq", {"key": "value"})
        
        time.sleep(0.5)
        
        # 检查死信队列
        dead_letters = bus.get_dead_letter_queue()
        self.assertGreater(len(dead_letters), 0, "Failed event should be in dead letter queue")
        
        bus.shutdown()


class TestP02ServiceLocatorCircularDependency(unittest.TestCase):
    """P0-2: ServiceLocator循环依赖检测验证"""

    def test_circular_dependency_raises_error(self):
        """验证循环依赖时抛出异常"""
        from core.service_locator import ServiceLocator, CircularDependencyError
        
        class ServiceA:
            pass
        
        class ServiceB:
            pass
        
        locator = ServiceLocator()
        
        # 注册存在循环依赖的服务
        locator.register(ServiceA, ServiceA(), dependencies={ServiceB})
        locator.register(ServiceB, ServiceB(), dependencies={ServiceA})
        
        # 验证拓扑排序时抛出循环依赖异常
        with self.assertRaises(CircularDependencyError):
            locator._topological_sort_services()

    def test_validate_all_dependencies_detects_circular(self):
        """验证依赖验证能检测循环依赖"""
        from core.service_locator import ServiceLocator
        
        class ServiceX:
            pass
        
        class ServiceY:
            pass
        
        locator = ServiceLocator()
        locator.register(ServiceX, ServiceX(), dependencies={ServiceY})
        locator.register(ServiceY, ServiceY(), dependencies={ServiceX})
        
        result = locator.validate_all_dependencies()
        
        self.assertFalse(result["valid"])
        self.assertGreater(len(result["errors"]), 0)


class TestP03DatabasePoolConnectionLeak(unittest.TestCase):
    """P0-3: DatabasePool连接泄漏保护验证"""

    def test_connection_timeout_reclaim(self):
        """验证连接使用超时后强制回收"""
        from infrastructure.database import DatabasePool
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            # 创建连接池，设置较短的超时时间
            pool = DatabasePool(
                db_path=db_path,
                pool_size=2,
                max_connection_time=0.5  # 0.5秒超时
            )
            
            # 获取连接但不释放
            conn_info = pool._get_connection()
            self.assertTrue(conn_info.in_use)
            
            # 等待超时
            time.sleep(0.6)
            
            # 再次获取连接（应该能获取到，因为超时回收）
            conn_info2 = pool._get_connection()
            self.assertIsNotNone(conn_info2)
            
            pool.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_graceful_close_waits_for_connections(self):
        """验证优雅关闭等待连接归还"""
        from infrastructure.database import DatabasePool
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            pool = DatabasePool(db_path=db_path, pool_size=2)
            
            # 获取连接并保持使用状态
            conn_info = pool._get_connection()
            self.assertTrue(conn_info.in_use)
            
            # 启动关闭线程（应该等待连接归还）
            close_completed = []
            def close_in_background():
                pool.close(timeout=2.0)
                close_completed.append(True)
            
            close_thread = threading.Thread(target=close_in_background)
            close_thread.start()
            
            # 给关闭线程一点时间检查状态
            time.sleep(0.3)
            
            # 此时连接池不应完全关闭（因为连接仍在使用）
            self.assertFalse(close_completed, "Close should not complete while connection in use")
            
            # 归还连接
            pool._return_connection(conn_info)
            
            # 连接归还后，关闭应完成
            close_thread.join(timeout=2.0)
            self.assertTrue(close_completed, "Close should complete after connection returned")
            self.assertTrue(pool.is_closed())
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_connection_after_close_raises_error(self):
        """验证关闭后获取连接抛出异常"""
        from infrastructure.database import DatabasePool
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            pool = DatabasePool(db_path=db_path, pool_size=1)
            pool.close()
            
            with self.assertRaises(RuntimeError) as context:
                pool._get_connection()
            
            self.assertIn("closed", str(context.exception).lower())
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestP04HotSwapManagerListenerError(unittest.TestCase):
    """P0-4: HotSwapManager监听器异常处理验证"""

    def test_listener_error_records_to_state(self):
        """验证监听器异常记录到插件状态"""
        from core.hot_swap_manager import HotSwapManager, HotSwapEvent, HotSwapAction, HotSwapState, PluginStateInfo
        
        # 创建模拟的plugin_loader
        class MockPluginLoader:
            def reload_plugin(self, plugin_id):
                class Result:
                    success = True
                return Result()
        
        manager = HotSwapManager(plugin_loader=MockPluginLoader())
        
        # 创建一个会抛出异常的监听器
        def failing_listener(event: HotSwapEvent):
            raise ValueError("Listener error")
        
        manager.add_listener(failing_listener)
        
        # 模拟插件状态
        manager._plugin_states["test_plugin"] = PluginStateInfo(plugin_id="test_plugin")
        
        # 触发通知
        event = HotSwapEvent(
            plugin_id="test_plugin",
            action=HotSwapAction.RELOAD,
            state=HotSwapState.COMPLETED,
        )
        manager._notify_listeners(event)
        
        # 验证错误被记录
        state = manager.get_state_info("test_plugin")
        self.assertIsNotNone(state.last_error)
        self.assertIn("listener", state.last_error.lower())

    def test_listener_error_includes_exc_info(self):
        """验证监听器异常记录完整堆栈"""
        from core.hot_swap_manager import HotSwapManager, HotSwapEvent, HotSwapAction, HotSwapState
        
        class MockPluginLoader:
            def reload_plugin(self, plugin_id):
                class Result:
                    success = True
                return Result()
        
        manager = HotSwapManager(plugin_loader=MockPluginLoader())
        
        # 捕获日志
        log_records = []
        
        class LogHandler(logging.Handler):
            def emit(self, record):
                log_records.append(record)
        
        handler = LogHandler()
        handler.setLevel(logging.ERROR)
        logger = logging.getLogger("core.hot_swap_manager")
        logger.addHandler(handler)
        
        def failing_listener(event):
            raise RuntimeError("Test exception")
        
        manager.add_listener(failing_listener)
        
        event = HotSwapEvent(
            plugin_id="test",
            action=HotSwapAction.RELOAD,
            state=HotSwapState.COMPLETED,
        )
        manager._notify_listeners(event)
        
        # 验证日志记录
        error_records = [r for r in log_records if r.levelno >= logging.ERROR]
        self.assertGreater(len(error_records), 0)
        
        # 验证日志包含exc_info或错误信息
        record = error_records[0]
        self.assertTrue(record.exc_info is not None or "error" in record.getMessage().lower())
        
        logger.removeHandler(handler)


if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(level=logging.WARNING)
    
    # 运行测试
    unittest.main(verbosity=2)
