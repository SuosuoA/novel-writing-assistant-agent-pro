"""
端到端测试用例 - 完整业务流程测试

依据：经验文档/2.2 插件接口定义✅️.md
创建日期：2026-03-21
测试级别：P1
测试类型：端到端（E2E）测试

测试覆盖：
1. 插件生命周期管理流程（加载→激活→执行→停用→卸载）
2. 事件总线通信流程（发布→订阅→处理→熔断→死信）
3. 服务定位器依赖注入流程（注册→获取→生命周期管理）
4. V5核心模块保护机制
5. 完整生成流程（请求→验证→生成→评分→输出）
6. 插件协作流程（分析器→生成器→验证器）
"""

import pytest
import threading
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, MagicMock, patch

# 导入核心模块
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.event_bus import EventBus, EventPriority, DeadLetterQueue
from core.plugin_registry import PluginRegistry, PluginState, PluginType, V5_PROTECTED_MODULES, PluginProtectionError
from core.service_locator import ServiceLocator, ServiceScope, CircularDependencyError, ServiceNotFoundError
from core.plugin_interface import (
    BasePlugin, AnalyzerPlugin, GeneratorPlugin, ValidatorPlugin,
    PluginContext, V5_PROTECTED_MODULES as INTERFACE_PROTECTED_MODULES
)
from core.models import (
    GenerationRequest, GenerationResult, ValidationScores, Event, PluginInfo,
    PluginMetadata
)


# ============================================================================
# 测试夹具
# ============================================================================

@pytest.fixture
def event_bus():
    """创建EventBus实例"""
    bus = EventBus(max_workers=5, circuit_threshold=3)
    yield bus
    bus.shutdown()


@pytest.fixture
def plugin_registry():
    """创建PluginRegistry实例"""
    return PluginRegistry()


@pytest.fixture
def service_locator():
    """创建ServiceLocator实例"""
    return ServiceLocator()


@pytest.fixture
def plugin_context(event_bus, plugin_registry, service_locator):
    """创建插件上下文"""
    from core.config_manager import ConfigManager
    config_manager = ConfigManager()
    
    return PluginContext(
        event_bus=event_bus,
        service_locator=service_locator,
        config_manager=config_manager,
        plugin_registry=plugin_registry,
        logger=None,
        v5_modules={}
    )


# ============================================================================
# 第一部分：插件生命周期管理流程测试
# ============================================================================

class TestPluginLifecycle:
    """测试插件完整生命周期"""
    
    def test_01_plugin_registration(self, plugin_registry):
        """测试插件注册（LOADED状态）"""
        metadata = PluginMetadata(
            id="test-plugin-001",
            name="测试插件",
            version="1.0.0",
            description="测试用插件",
            author="QA工程师",
            plugin_type="TOOL"
        )
        
        # 注册插件
        result = plugin_registry.register("test-plugin-001", metadata)
        assert result is True
        
        # 验证状态
        state = plugin_registry.get_state("test-plugin-001")
        assert state == PluginState.LOADED.value
        
        # 验证信息
        info = plugin_registry.get_plugin_info("test-plugin-001")
        assert info is not None
        assert info.metadata.id == "test-plugin-001"
    
    def test_02_plugin_activation(self, plugin_registry):
        """测试插件激活（LOADED→ACTIVE）"""
        metadata = PluginMetadata(
            id="test-plugin-002",
            name="测试插件2",
            version="1.0.0",
            plugin_type="ANALYZER"
        )
        
        plugin_registry.register("test-plugin-002", metadata)
        
        # 激活
        result = plugin_registry.activate("test-plugin-002")
        assert result is True
        
        # 验证状态
        state = plugin_registry.get_state("test-plugin-002")
        assert state == PluginState.ACTIVE.value
    
    def test_03_plugin_deactivation(self, plugin_registry):
        """测试插件停用（ACTIVE→LOADED）"""
        metadata = PluginMetadata(
            id="test-plugin-003",
            name="测试插件3",
            version="1.0.0",
            plugin_type="GENERATOR"
        )
        
        plugin_registry.register("test-plugin-003", metadata)
        plugin_registry.activate("test-plugin-003")
        
        # 停用
        result = plugin_registry.deactivate("test-plugin-003")
        assert result is True
        
        # 验证状态
        state = plugin_registry.get_state("test-plugin-003")
        assert state == PluginState.LOADED.value
    
    def test_04_plugin_error_recovery(self, plugin_registry):
        """测试插件错误恢复（ERROR→LOADED）"""
        metadata = PluginMetadata(
            id="test-plugin-004",
            name="测试插件4",
            version="1.0.0",
            plugin_type="VALIDATOR"
        )
        
        plugin_registry.register("test-plugin-004", metadata)
        plugin_registry.activate("test-plugin-004")
        
        # 设置错误（从ACTIVE状态）
        result = plugin_registry.set_error("test-plugin-004", "模拟错误")
        # V2.0修订：ACTIVE状态可以直接转到ERROR（符合架构设计说明书V1.2）
        # 状态机允许：ACTIVE → ERROR（用于运行时错误处理）
        assert result is True  # ACTIVE→ERROR允许
        
        # 正确流程：先停用，再设置错误
        plugin_registry.deactivate("test-plugin-004")
        result = plugin_registry.set_error("test-plugin-004", "模拟错误")
        assert result is True
        state = plugin_registry.get_state("test-plugin-004")
        assert state == PluginState.ERROR.value
        
        # 恢复
        result = plugin_registry.reset_error("test-plugin-004")
        assert result is True
        
        # 验证状态
        state = plugin_registry.get_state("test-plugin-004")
        assert state == PluginState.LOADED.value
    
    def test_05_plugin_unregistration(self, plugin_registry):
        """测试插件卸载（UNLOADING）"""
        metadata = PluginMetadata(
            id="test-plugin-005",
            name="测试插件5",
            version="1.0.0",
            plugin_type="TOOL"
        )
        
        plugin_registry.register("test-plugin-005", metadata)
        
        # 卸载
        result = plugin_registry.unregister("test-plugin-005")
        assert result is True
        
        # 验证已移除
        info = plugin_registry.get_plugin_info("test-plugin-005")
        assert info is None
    
    def test_06_full_lifecycle_flow(self, plugin_registry):
        """测试完整生命周期流程"""
        metadata = PluginMetadata(
            id="test-plugin-lifecycle",
            name="生命周期测试插件",
            version="1.0.0",
            plugin_type="TOOL"
        )
        
        # 1. 注册
        assert plugin_registry.register("test-plugin-lifecycle", metadata)
        assert plugin_registry.get_state("test-plugin-lifecycle") == PluginState.LOADED.value
        
        # 2. 激活
        assert plugin_registry.activate("test-plugin-lifecycle")
        assert plugin_registry.get_state("test-plugin-lifecycle") == PluginState.ACTIVE.value
        
        # 3. 停用
        assert plugin_registry.deactivate("test-plugin-lifecycle")
        assert plugin_registry.get_state("test-plugin-lifecycle") == PluginState.LOADED.value
        
        # 4. 设置错误（从LOADED状态可以设置ERROR）
        assert plugin_registry.set_error("test-plugin-lifecycle", "测试错误")
        assert plugin_registry.get_state("test-plugin-lifecycle") == PluginState.ERROR.value
        
        # 5. 恢复
        assert plugin_registry.reset_error("test-plugin-lifecycle")
        assert plugin_registry.get_state("test-plugin-lifecycle") == PluginState.LOADED.value
        
        # 6. 再次激活
        assert plugin_registry.activate("test-plugin-lifecycle")
        assert plugin_registry.get_state("test-plugin-lifecycle") == PluginState.ACTIVE.value
        
        # 7. 卸载（需要先停用）
        plugin_registry.deactivate("test-plugin-lifecycle")
        assert plugin_registry.unregister("test-plugin-lifecycle")
        assert plugin_registry.get_plugin_info("test-plugin-lifecycle") is None


# ============================================================================
# 第二部分：事件总线通信流程测试
# ============================================================================

class TestEventBusCommunication:
    """测试事件总线完整通信流程"""
    
    def test_01_publish_subscribe_flow(self, event_bus):
        """测试发布-订阅流程"""
        received_events = []
        
        def handler(event):
            received_events.append(event)
        
        # 订阅
        handler_id = event_bus.subscribe(
            "test.event",
            handler,
            handler_id="test-handler-001"
        )
        
        # 发布
        event_bus.publish("test.event", {"message": "hello"})
        
        # 等待异步执行
        time.sleep(0.5)
        
        # 验证
        assert len(received_events) == 1
        assert received_events[0].data["message"] == "hello"
    
    def test_02_sync_publish_flow(self, event_bus):
        """测试同步发布流程"""
        results = []
        
        def handler(event):
            return event.data["value"] * 2
        
        event_bus.subscribe("test.sync", handler)
        
        # 同步发布
        results = event_bus.publish_sync("test.sync", {"value": 10})
        
        # 验证
        assert len(results) == 1
        assert results[0] == 20
    
    def test_03_priority_order(self, event_bus):
        """测试优先级排序"""
        execution_order = []
        
        def handler_low(event):
            execution_order.append("low")
        
        def handler_high(event):
            execution_order.append("high")
        
        def handler_normal(event):
            execution_order.append("normal")
        
        # 订阅（不同优先级）
        event_bus.subscribe("test.priority", handler_low, priority=EventPriority.LOW)
        event_bus.subscribe("test.priority", handler_high, priority=EventPriority.HIGH)
        event_bus.subscribe("test.priority", handler_normal, priority=EventPriority.NORMAL)
        
        # 同步发布
        event_bus.publish_sync("test.priority", {})
        
        # 验证执行顺序（数值越小越先执行）
        assert execution_order == ["high", "normal", "low"]
    
    def test_04_circuit_breaker_flow(self, event_bus):
        """测试熔断器流程"""
        failure_count = [0]
        
        def failing_handler(event):
            failure_count[0] += 1
            raise RuntimeError("模拟失败")
        
        event_bus.subscribe("test.circuit", failing_handler)
        
        # 触发多次失败
        for i in range(5):
            event_bus.publish("test.circuit", {})
            time.sleep(0.1)
        
        # 验证熔断
        assert failure_count[0] < 5  # 熔断后不再执行
    
    def test_05_dead_letter_queue(self, event_bus):
        """测试死信队列"""
        def failing_handler(event):
            raise ValueError("测试错误")
        
        event_bus.subscribe("test.deadletter", failing_handler)
        event_bus.publish("test.deadletter", {"key": "value"})
        
        time.sleep(0.5)
        
        # 验证死信队列
        dead_letters = event_bus.get_dead_letter_queue()
        assert len(dead_letters) > 0
        assert dead_letters[0]["event"]["data"]["key"] == "value"


# ============================================================================
# 第三部分：服务定位器依赖注入流程测试
# ============================================================================

class TestServiceLocatorDI:
    """测试服务定位器依赖注入流程"""
    
    def test_01_register_and_get(self, service_locator):
        """测试服务注册和获取"""
        class TestService:
            def __init__(self):
                self.name = "test_service"
        
        instance = TestService()
        service_locator.register(TestService, instance)
        
        # 获取
        retrieved = service_locator.get(TestService)
        assert retrieved is instance
        assert retrieved.name == "test_service"
    
    def test_02_singleton_scope(self, service_locator):
        """测试单例生命周期"""
        call_count = [0]
        
        def factory():
            call_count[0] += 1
            return f"instance_{call_count[0]}"
        
        service_locator.register_factory(str, factory, scope=ServiceScope.SINGLETON)
        
        # 多次获取
        instance1 = service_locator.get(str)
        instance2 = service_locator.get(str)
        
        # 验证同一实例
        assert instance1 == instance2
        assert call_count[0] == 1  # 只调用一次工厂
    
    def test_03_transient_scope(self, service_locator):
        """测试瞬态生命周期"""
        call_count = [0]
        
        def factory():
            call_count[0] += 1
            return f"instance_{call_count[0]}"
        
        service_locator.register_factory(str, factory, scope=ServiceScope.TRANSIENT)
        
        # 多次获取
        instance1 = service_locator.get(str)
        instance2 = service_locator.get(str)
        
        # 验证不同实例
        assert instance1 != instance2
        assert call_count[0] == 2  # 每次都创建
    
    def test_04_circular_dependency_detection(self, service_locator):
        """测试循环依赖检测"""
        class ServiceA:
            pass
        
        class ServiceB:
            pass
        
        # 注册依赖关系
        service_locator.register(ServiceA, ServiceA(), dependencies={ServiceB})
        service_locator.register(ServiceB, ServiceB(), dependencies={ServiceA})
        
        # 检测循环依赖
        has_circular = service_locator.check_circular_dependency(ServiceA)
        assert has_circular is True
    
    def test_05_service_not_found(self, service_locator):
        """测试服务未找到异常"""
        class UnregisteredService:
            pass
        
        with pytest.raises(ServiceNotFoundError):
            service_locator.get(UnregisteredService)


# ============================================================================
# 第四部分：V5核心模块保护机制测试
# ============================================================================

class TestV5ProtectionMechanism:
    """测试V5核心模块保护机制"""
    
    def test_01_protected_modules_list(self, plugin_registry):
        """测试保护模块列表"""
        protected = plugin_registry.get_protected_modules()
        
        # 验证保护模块列表完整（V1.3定义的9个模块：8+hot-ranking）
        assert len(protected) == 9
        assert "outline-parser-v3" in protected
        assert "style-learner-v2" in protected
        assert "character-manager" in protected
        assert "worldview-parser" in protected
        assert "context-builder" in protected
        assert "iterative-generator-v2" in protected
        assert "weighted-validator" in protected
        assert "optimized-generator-v2" in protected
    
    def test_02_prevent_unload_protected(self, plugin_registry):
        """测试禁止卸载保护模块"""
        metadata = PluginMetadata(
            id="outline-parser-v3",
            name="大纲解析器",
            version="3.0.0",
            plugin_type="ANALYZER"
        )
        
        plugin_registry.register("outline-parser-v3", metadata)
        
        # 尝试卸载
        with pytest.raises(PluginProtectionError) as exc_info:
            plugin_registry.unregister("outline-parser-v3")
        
        assert "禁止卸载V5保护模块" in str(exc_info.value)
    
    def test_03_prevent_disable_protected(self, plugin_registry):
        """测试禁止禁用保护模块"""
        metadata = PluginMetadata(
            id="style-learner-v2",
            name="风格学习器",
            version="2.0.0",
            plugin_type="ANALYZER"
        )
        
        plugin_registry.register("style-learner-v2", metadata)
        plugin_registry.activate("style-learner-v2")
        
        # 尝试禁用
        with pytest.raises(PluginProtectionError) as exc_info:
            plugin_registry.disable("style-learner-v2")
        
        assert "禁止禁用V5保护模块" in str(exc_info.value)
    
    def test_04_is_protected_check(self, plugin_registry):
        """测试保护模块检查"""
        assert plugin_registry.is_protected("outline-parser-v3") is True
        assert plugin_registry.is_protected("non-protected-plugin") is False


# ============================================================================
# 第五部分：完整生成流程测试
# ============================================================================

class TestGenerationFlow:
    """测试完整生成流程"""
    
    def test_01_generation_request_validation(self):
        """测试生成请求验证"""
        # 有效请求
        valid_request = GenerationRequest(
            request_id="req-001",
            title="第一章 开端",
            outline="主角出场，初遇关键人物",
            word_count=2000,
            max_iterations=5
        )
        
        assert valid_request.request_id == "req-001"
        assert valid_request.word_count == 2000
        
        # 无效请求（字数超范围）
        with pytest.raises(Exception):  # Pydantic ValidationError
            GenerationRequest(
                request_id="req-002",
                title="测试章节",
                outline="测试",
                word_count=100  # 低于最小值500
            )
    
    def test_02_validation_scores_calculation(self):
        """测试评分计算"""
        scores = ValidationScores(
            word_count_score=0.95,
            outline_score=0.90,
            style_score=0.88,
            character_score=0.85,
            worldview_score=0.80,
            naturalness_score=0.92,
            has_chapter_end=True
        )
        
        # 计算总分
        total = scores.calculate_total()
        
        # 验证加权计算
        expected = (
            0.95 * 0.10 +
            0.90 * 0.15 +
            0.88 * 0.25 +
            0.85 * 0.25 +
            0.80 * 0.20 +
            0.92 * 0.05
        )
        
        assert abs(total - expected) < 0.001
        assert total >= 0.8  # 达到阈值（87.25%）
    
    def test_03_generation_result_model(self):
        """测试生成结果模型"""
        scores = ValidationScores()
        scores.calculate_total()
        
        result = GenerationResult(
            request_id="req-001",
            content="这是生成的内容..." + "【本章完】",
            word_count=2000,
            iteration_count=3,
            validation_scores=scores
        )
        
        assert result.request_id == "req-001"
        assert result.word_count == 2000
        assert result.iteration_count == 3
        assert "【本章完】" in result.content


# ============================================================================
# 第六部分：插件协作流程测试
# ============================================================================

class TestPluginCollaboration:
    """测试插件协作流程"""
    
    def test_01_analyzer_plugin_interface(self, plugin_context):
        """测试分析器插件接口"""
        class MockAnalyzerPlugin(AnalyzerPlugin):
            def __init__(self):
                metadata = PluginMetadata(
                    id="mock-analyzer",
                    name="模拟分析器",
                    version="1.0.0",
                    plugin_type="ANALYZER"
                )
                super().__init__(metadata)
            
            @classmethod
            def get_metadata(cls):
                return PluginMetadata(
                    id="mock-analyzer",
                    name="模拟分析器",
                    version="1.0.0",
                    plugin_type="ANALYZER"
                )
            
            def initialize(self, context):
                return True
            
            def analyze(self, content, options=None):
                return {"result": "analyzed", "content_length": len(content)}
            
            def get_supported_formats(self):
                return ["txt", "json", "md"]
            
            def get_analysis_types(self):
                return ["outline", "style"]
        
        plugin = MockAnalyzerPlugin()
        
        # 测试接口
        result = plugin.analyze("测试内容")
        assert result["result"] == "analyzed"
        assert result["content_length"] == 4
        
        formats = plugin.get_supported_formats()
        assert "txt" in formats
        
        types = plugin.get_analysis_types()
        assert "outline" in types
    
    def test_02_generator_plugin_interface(self, plugin_context):
        """测试生成器插件接口"""
        class MockGeneratorPlugin(GeneratorPlugin):
            def __init__(self):
                metadata = PluginMetadata(
                    id="mock-generator",
                    name="模拟生成器",
                    version="1.0.0",
                    plugin_type="GENERATOR"
                )
                super().__init__(metadata)
            
            @classmethod
            def get_metadata(cls):
                return PluginMetadata(
                    id="mock-generator",
                    name="模拟生成器",
                    version="1.0.0",
                    plugin_type="GENERATOR"
                )
            
            def initialize(self, context):
                return True
            
            def generate(self, request):
                return GenerationResult(
                    request_id=request.request_id,
                    content="生成的内容【本章完】",
                    word_count=100,
                    iteration_count=1
                )
            
            def validate_request(self, request):
                errors = []
                if request.word_count < 500:
                    errors.append("字数过低")
                return len(errors) == 0, errors
            
            def get_generation_options(self):
                return {"word_count": {"default": 2000}}
        
        plugin = MockGeneratorPlugin()
        
        # 测试请求验证
        request = GenerationRequest(
            request_id="req-001",
            title="测试章节",
            outline="测试大纲",
            word_count=2000
        )
        
        valid, errors = plugin.validate_request(request)
        assert valid is True
        
        # 测试生成
        result = plugin.generate(request)
        assert result.request_id == "req-001"
        assert "【本章完】" in result.content
    
    def test_03_validator_plugin_interface(self, plugin_context):
        """测试验证器插件接口"""
        class MockValidatorPlugin(ValidatorPlugin):
            def __init__(self):
                metadata = PluginMetadata(
                    id="mock-validator",
                    name="模拟验证器",
                    version="1.0.0",
                    plugin_type="VALIDATOR"
                )
                super().__init__(metadata)
            
            @classmethod
            def get_metadata(cls):
                return PluginMetadata(
                    id="mock-validator",
                    name="模拟验证器",
                    version="1.0.0",
                    plugin_type="VALIDATOR"
                )
            
            def initialize(self, context):
                return True
            
            def validate(self, content, context=None):
                scores = ValidationScores(
                    word_count_score=0.9,
                    outline_score=0.85,
                    style_score=0.8,
                    character_score=0.75,
                    worldview_score=0.8,
                    naturalness_score=0.9,
                    has_chapter_end="【本章完】" in content
                )
                scores.calculate_total()
                return scores
            
            def get_validation_dimensions(self):
                return ["word_count", "style", "character", "worldview"]
        
        plugin = MockValidatorPlugin()
        
        # 测试验证
        scores = plugin.validate("内容【本章完】")
        assert scores.total_score >= 0.8
        assert scores.has_chapter_end is True
        
        # 测试维度
        dimensions = plugin.get_validation_dimensions()
        assert "word_count" in dimensions


# ============================================================================
# 第七部分：集成测试 - 完整业务流程
# ============================================================================

class TestFullBusinessFlow:
    """完整业务流程集成测试"""
    
    def test_complete_generation_workflow(
        self, event_bus, plugin_registry, service_locator
    ):
        """测试完整的章节生成工作流"""
        
        # 1. 初始化核心组件
        service_locator.register(EventBus, event_bus)
        service_locator.register(PluginRegistry, plugin_registry)
        
        # 2. 注册插件
        metadata = PluginMetadata(
            id="test-generator-plugin",
            name="测试生成器",
            version="1.0.0",
            plugin_type="GENERATOR"
        )
        
        assert plugin_registry.register("test-generator-plugin", metadata)
        assert plugin_registry.activate("test-generator-plugin")
        
        # 3. 订阅事件
        events_received = []
        
        def on_generation_started(event):
            events_received.append(("started", event.data))
        
        def on_generation_completed(event):
            events_received.append(("completed", event.data))
        
        event_bus.subscribe("generation.started", on_generation_started)
        event_bus.subscribe("generation.completed", on_generation_completed)
        
        # 4. 触发生成流程
        event_bus.publish("generation.started", {
            "chapter_title": "第一章",
            "word_count": 2000
        })
        
        time.sleep(0.5)
        
        event_bus.publish("generation.completed", {
            "content": "生成内容【本章完】",
            "word_count": 2000,
            "score": 0.85
        })
        
        time.sleep(0.5)
        
        # 5. 验证事件流
        assert len(events_received) == 2
        assert events_received[0][0] == "started"
        assert events_received[1][0] == "completed"
        
        # 6. 清理
        event_bus.unsubscribe("generation.started")
        event_bus.unsubscribe("generation.completed")


# ============================================================================
# 运行测试
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
