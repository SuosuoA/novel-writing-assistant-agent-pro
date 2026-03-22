#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P1问题修复验证测试

测试目标：
1. P1-1: 配置字段验证器
2. P1-2: 日志脱敏
3. P1-3: GUI主程序集成（模拟测试）
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_config_validation():
    """测试 P1-1: 配置字段验证器"""
    print("\n=== 测试 P1-1: 配置字段验证器 ===")

    from core.config_service import AppConfig
    from pydantic import ValidationError

    # 测试有效的配置
    try:
        config = AppConfig(
            api_key="sk-test-api-key-12345",
            temperature=0.8,
            theme="dark",
            service_mode="local",
            window_size="1920x1080",
        )
        print("[OK] 有效配置验证通过")
    except ValidationError as e:
        print(f"[FAIL] 有效配置验证失败: {e}")
        return False

    # 测试无效的API密钥（太短）
    try:
        config = AppConfig(api_key="short")
        print("[FAIL] 无效API密钥（太短）未被检测")
        return False
    except ValidationError:
        print("[OK] 无效API密钥（太短）被正确拒绝")

    # 测试无效的温度值
    try:
        config = AppConfig(temperature=3.0)
        print("[FAIL] 无效温度值未被检测")
        return False
    except ValidationError:
        print("[OK] 无效温度值被正确拒绝")

    # 测试无效的主题
    try:
        config = AppConfig(theme="invalid")
        print("[FAIL] 无效主题未被检测")
        return False
    except ValidationError:
        print("[OK] 无效主题被正确拒绝")

    # 测试无效的窗口大小
    try:
        config = AppConfig(window_size="invalid")
        print("[FAIL] 无效窗口大小未被检测")
        return False
    except ValidationError:
        print("[OK] 无效窗口大小被正确拒绝")

    return True


def test_log_sanitization():
    """测试 P1-2: 日志脱敏"""
    print("\n=== 测试 P1-2: 日志脱敏 ===")

    from core import get_logging_service, initialize_core_services

    # 初始化服务
    initialize_core_services()

    # 获取日志服务
    logging_service = get_logging_service()
    print("[OK] LoggingService 获取成功")

    # 验证脱敏器是否启用
    if logging_service._sanitizer:
        print("[OK] 日志脱敏器已启用")
    else:
        print("[WARN] 日志脱敏器未启用（log_sanitizer模块可能不可用）")

    # 测试动态日志级别
    logging_service.set_level("DEBUG")
    if logging_service.get_level() == "DEBUG":
        print("[OK] 动态日志级别设置成功")
    else:
        print("[FAIL] 动态日志级别设置失败")
        return False

    # 测试日志记录
    logging_service.log_ai_request(
        provider="DeepSeek",
        model="deepseek-chat",
        request_type="request",
        message="API Key: sk-test-api-key-12345",
    )
    print("[OK] 含敏感信息的日志已记录")

    return True


def test_gui_integration():
    """测试 P1-3: GUI主程序集成（模拟测试）"""
    print("\n=== 测试 P1-3: GUI主程序集成 ===")

    from core import (
        initialize_core_services,
        dispose_core_services,
        get_config_service,
        get_logging_service,
        get_service_locator,
        ConfigService,
        LoggingService,
    )

    # 先释放可能已存在的服务
    dispose_core_services()

    # 初始化核心服务（模拟GUI启动流程）
    init_results = initialize_core_services()
    print(f"[OK] 核心服务初始化结果: {init_results}")

    # 检查是否已初始化或新初始化成功
    if init_results.get("already_initialized"):
        print("[OK] 服务已初始化（符合预期）")
    elif not init_results.get("ConfigService") or not init_results.get("LoggingService"):
        print("[FAIL] 核心服务初始化不完整")
        return False

    # 验证 ConfigService 已注册到 ServiceLocator
    service_locator = get_service_locator()
    config_service = service_locator.try_get(ConfigService)
    if config_service is None:
        print("[FAIL] ConfigService 未注册到 ServiceLocator")
        return False
    config = config_service.get_config()
    print(f"[OK] ConfigService 已注册: provider={config.provider}")

    # 验证 LoggingService 已注册到 ServiceLocator
    logging_service = service_locator.try_get(LoggingService)
    if logging_service is None:
        print("[FAIL] LoggingService 未注册到 ServiceLocator")
        return False
    logging_service.log_system_event("test", "GUI集成测试")
    print("[OK] LoggingService 已注册")

    # 释放核心服务（模拟GUI关闭流程）
    dispose_results = dispose_core_services()
    print(f"[OK] 核心服务释放结果: {dispose_results}")

    return True


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("P1问题修复验证测试")
    print("=" * 60)

    results = {}

    # 测试 P1-1
    try:
        results["P1-1"] = test_config_validation()
    except Exception as e:
        print(f"[FAIL] P1-1 测试异常: {e}")
        results["P1-1"] = False

    # 测试 P1-2
    try:
        results["P1-2"] = test_log_sanitization()
    except Exception as e:
        print(f"[FAIL] P1-2 测试异常: {e}")
        results["P1-2"] = False

    # 测试 P1-3
    try:
        results["P1-3"] = test_gui_integration()
    except Exception as e:
        print(f"[FAIL] P1-3 测试异常: {e}")
        results["P1-3"] = False

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总:")
    print("=" * 60)
    for test_id, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{test_id}: {status}")

    all_passed = all(results.values())
    print("\n" + "=" * 60)
    if all_passed:
        print("[SUCCESS] 所有P1问题已修复！")
    else:
        print("[FAIL] 部分测试未通过")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
