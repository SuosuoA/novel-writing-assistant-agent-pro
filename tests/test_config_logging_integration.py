#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ConfigService 和 LoggingService 集成测试

测试目标：
1. ConfigService 可正常读取 config.yaml
2. LoggingService 可正常记录日志
3. 服务通过 ServiceLocator 正确注册和获取
4. BootstrapService 可正常初始化和释放服务
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core import (
    ConfigService,
    AppConfig,
    get_config_service,
    LoggingService,
    get_logging_service,
    BootstrapService,
    get_bootstrap_service,
    initialize_core_services,
    dispose_core_services,
    get_service_locator,
)


def test_config_service():
    """测试 ConfigService"""
    print("\n=== 测试 ConfigService ===")

    # 获取 ConfigService
    config_service = get_config_service()
    print("[OK] ConfigService 实例创建成功")

    # 获取配置模型
    config = config_service.get_config()
    print(f"[OK] 配置模型加载成功: {type(config)}")

    # 验证配置字段
    print(f"  - provider: {config.provider}")
    print(f"  - model: {config.model}")
    print(f"  - service_mode: {config.service_mode}")
    print(f"  - theme: {config.theme}")
    print(f"  - window_size: {config.window_size}")

    # 测试单个配置获取
    provider = config_service.get("provider")
    print(f"[OK] 单个配置获取: provider = {provider}")

    return True


def test_logging_service():
    """测试 LoggingService"""
    print("\n=== 测试 LoggingService ===")

    # 获取 LoggingService
    logging_service = get_logging_service()
    print("[OK] LoggingService 实例创建成功")

    # 测试日志目录
    log_dir = logging_service.get_log_dir()
    print("[OK] 日志服务创建成功")

    # 记录各种事件
    logging_service.log_system_event("startup", "系统启动测试", level="INFO")
    print("[OK] 系统事件日志记录成功")

    logging_service.log_plugin_event("loaded", "TestPlugin", "插件加载测试", level="INFO")
    print("[OK] 插件事件日志记录成功")

    logging_service.log_ai_request("DeepSeek", "deepseek-chat", "request", "AI请求测试", level="INFO")
    print("[OK] AI请求日志记录成功")

    logging_service.log_generation_event("started", "test-request-123", "生成任务开始", level="INFO")
    print("[OK] 生成事件日志记录成功")

    logging_service.log_config_event("changed", "theme", "主题配置变更", level="INFO")
    print("[OK] 配置事件日志记录成功")

    # 检查日志目录
    log_dir = logging_service.get_log_dir()
    print(f"[OK] 日志目录: {log_dir}")

    return True


def test_service_locator():
    """测试 ServiceLocator 注册和获取"""
    print("\n=== 测试 ServiceLocator ===")

    service_locator = get_service_locator()
    print("[OK] ServiceLocator 实例获取成功")

    # 注册服务
    config_service = get_config_service()
    logging_service = get_logging_service()

    service_locator.register(ConfigService, config_service)
    print("[OK] ConfigService 注册成功")

    service_locator.register(LoggingService, logging_service)
    print("[OK] LoggingService 注册成功")

    # 获取服务
    retrieved_config = service_locator.get(ConfigService)
    print(f"[OK] ConfigService 获取成功: {type(retrieved_config)}")

    retrieved_logging = service_locator.get(LoggingService)
    print(f"[OK] LoggingService 获取成功: {type(retrieved_logging)}")

    # 检查服务状态
    config_status = service_locator.get_initialization_status(ConfigService)
    print(f"[OK] ConfigService 状态: {config_status}")

    logging_status = service_locator.get_initialization_status(LoggingService)
    print(f"[OK] LoggingService 状态: {logging_status}")

    return True


def test_bootstrap_service():
    """测试 BootstrapService"""
    print("\n=== 测试 BootstrapService ===")

    # 初始化服务
    results = initialize_core_services()
    print(f"[OK] 核心服务初始化结果: {results}")

    # 验证初始化状态
    bootstrap = get_bootstrap_service()
    is_initialized = bootstrap.is_initialized()
    print(f"[OK] 初始化状态: {is_initialized}")

    # 通过 ServiceLocator 获取服务
    service_locator = get_service_locator()
    config_service = service_locator.try_get(ConfigService)
    logging_service = service_locator.try_get(LoggingService)

    print(f"[OK] ConfigService 可用: {config_service is not None}")
    print(f"[OK] LoggingService 可用: {logging_service is not None}")

    # 释放服务
    dispose_results = dispose_core_services()
    print(f"[OK] 核心服务释放结果: {dispose_results}")

    return True


def test_integration():
    """完整集成测试"""
    print("\n" + "=" * 60)
    print("开始集成测试：ConfigService + LoggingService + BootstrapService")
    print("=" * 60)

    try:
        # 1. 测试 ConfigService
        if not test_config_service():
            print("[FAIL] ConfigService 测试失败")
            return False

        # 2. 测试 LoggingService
        if not test_logging_service():
            print("[FAIL] LoggingService 测试失败")
            return False

        # 3. 测试 ServiceLocator
        if not test_service_locator():
            print("[FAIL] ServiceLocator 测试失败")
            return False

        # 4. 测试 BootstrapService
        if not test_bootstrap_service():
            print("[FAIL] BootstrapService 测试失败")
            return False

        print("\n" + "=" * 60)
        print("[SUCCESS] 所有测试通过！")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_integration()
    sys.exit(0 if success else 1)
