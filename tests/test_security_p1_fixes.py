# -*- coding: utf-8 -*-
"""
P1中危问题修复验证测试

验证内容：
1. P1-1: 数据库连接池大小限制
2. P1-2: 配置管理器输入验证
3. P1-3: 敏感信息脱敏
4. P1-4: Agent任务超时控制
5. P1-5: 缓存键碰撞防护
6. P1-6: EventBus死信队列清理
"""

import sys
import os
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_p1_1_database_pool_limits():
    """P1-1: 验证数据库连接池大小限制"""
    print("\n[P1-1] Testing database pool limits...")
    from core.database import ConnectionPool

    # Test 1: Verify default pool size
    pool = ConnectionPool(":memory:", pool_size=10)
    assert pool._pool_size == 10, "Pool size should be 10"
    print("  OK - Pool size set correctly")

    # Test 2: Verify max connections limit
    assert pool._pool_size <= pool.MAX_CONNECTIONS_LIMIT
    print("  OK - Pool size within limit")

    # Test 3: Verify invalid pool_size is rejected
    try:
        invalid_pool = ConnectionPool(":memory:", pool_size=0)
        assert False, "pool_size=0 should be rejected"
    except ValueError:
        print("  OK - Invalid pool_size correctly rejected")

    # Test 4: Verify pool exceeds max limit is rejected
    try:
        invalid_pool = ConnectionPool(":memory:", pool_size=1000)
        assert False, "pool_size=1000 should be rejected"
    except ValueError:
        print("  OK - Excessive pool_size correctly rejected")

    # Test 5: Verify get_pool_status method exists
    status = pool.get_pool_status()
    assert "max_connections" in status
    print("  OK - Pool status method works")

    print("[P1-1] PASSED\n")
    return True


def test_p1_2_config_validation():
    """P1-2: 验证配置管理器输入验证"""
    print("[P1-2] Testing config input validation...")
    from core.config_manager import ConfigManager, ConfigKeyError, ConfigValidationError

    config = ConfigManager()

    # Test 1: Dangerous key names are rejected
    try:
        config.set("__class__.test", "value")
        assert False, "Dangerous key should be rejected"
    except ConfigKeyError:
        print("  OK - Dangerous key rejected")

    # Test 2: Invalid key format is rejected
    try:
        config.set("123invalid.key", "value")
        assert False, "Invalid key format should be rejected"
    except ConfigKeyError:
        print("  OK - Invalid key format rejected")

    # Test 3: Normal keys work
    config.set("test.normal_key", "value", source="test")
    assert config.get("test.normal_key") == "value"
    print("  OK - Normal keys work")

    print("[P1-2] PASSED\n")
    return True


def test_p1_3_sensitive_data_masking():
    """P1-3: 验证敏感信息脱敏"""
    print("[P1-3] Testing sensitive data masking...")
    from core.sensitive_data import SensitiveDataMasker, is_sensitive

    # Test 1: Sensitive key detection
    assert is_sensitive("password")
    assert is_sensitive("api_key")
    assert not is_sensitive("username")
    print("  OK - Sensitive key detection")

    # Test 2: Value masking
    masked = SensitiveDataMasker.mask_value("sk-test-key-12345", partial=True)
    assert "sk-t" in masked
    print("  OK - Partial masking works")

    # Test 3: Dict masking
    test_dict = {
        "username": "admin",
        "password": "secret123",
        "api_key": "sk-test-key"
    }
    masked_dict = SensitiveDataMasker.mask_dict(test_dict)
    assert masked_dict["username"] == "admin"
    assert masked_dict["password"] != "secret123"
    print("  OK - Dict masking works")

    print("[P1-3] PASSED\n")
    return True


def test_p1_4_agent_timeout_control():
    """P1-4: 验证Agent任务超时控制"""
    print("[P1-4] Testing agent timeout control...")
    from agents.agent_constraints import (
        ThinkerConstraints, OptimizerConstraints,
        ValidatorConstraints, PlannerConstraints, TimeoutContext
    )

    # Test 1: Constraints validation
    constraints = ThinkerConstraints()
    assert constraints.validate_constraints()
    print("  OK - Constraints validation")

    # Test 2: Resource limit fields exist
    assert hasattr(constraints, 'max_memory_mb')
    assert hasattr(constraints, 'max_output_size')
    print("  OK - Resource limit fields exist")

    # Test 3: TimeoutContext works
    try:
        with TimeoutContext(timeout_seconds=1) as ctx:
            time.sleep(0.5)
            ctx.check_timeout()
        print("  OK - TimeoutContext works (no timeout)")
    except TimeoutError:
        assert False, "Should not timeout"

    # Test 4: TimeoutContext triggers on timeout
    try:
        with TimeoutContext(timeout_seconds=1) as ctx:
            time.sleep(1.5)
            ctx.check_timeout()
        assert False, "Should timeout"
    except TimeoutError:
        print("  OK - TimeoutContext triggers on timeout")

    print("[P1-4] PASSED\n")
    return True


def test_p1_5_cache_collision_protection():
    """P1-5: 验证缓存键碰撞防护"""
    print("[P1-5] Testing cache collision protection...")
    from services.llm_client_with_resilience import LRUCache

    # Test 1: Safe key generation
    key1 = LRUCache.generate_safe_key("prompt1", "model1")
    key2 = LRUCache.generate_safe_key("prompt2", "model1")
    assert key1 != key2
    print("  OK - Different prompts generate different keys")

    # Test 2: Same input generates same key
    key3 = LRUCache.generate_safe_key("prompt1", "model1")
    assert key1 == key3
    print("  OK - Same input generates same key")

    # Test 3: Cache stats
    cache = LRUCache(max_size=10)
    cache.set("key1", {"value": "test1"}, value_hash="hash1")
    stats = cache.get_stats()
    assert "collision_count" in stats
    print("  OK - Cache stats work")

    print("[P1-5] PASSED\n")
    return True


def test_p1_6_dead_letter_cleanup():
    """P1-6: 验证EventBus死信队列清理"""
    print("[P1-6] Testing dead letter queue cleanup...")
    from core.event_bus import DeadLetterQueue, EventBus
    from core.models import Event

    # Test 1: Dead letter queue stats
    dlq = DeadLetterQueue(max_size=10, ttl_seconds=60)
    stats = dlq.get_stats()
    assert "current_size" in stats
    assert "ttl_seconds" in stats
    print("  OK - DLQ stats work")

    # Test 2: Add dead letter
    test_event = Event(
        type="test.event",
        data={"test": "data"},
        source="test",
        timestamp=time.time(),
        event_id="test123"
    )
    dlq.add(test_event, Exception("Test error"))
    assert dlq.get_stats()["current_size"] == 1
    print("  OK - Add dead letter works")

    # Test 3: EventBus methods
    bus = EventBus()
    assert hasattr(bus, 'get_dead_letter_stats')
    assert hasattr(bus, 'cleanup_dead_letters')
    print("  OK - EventBus methods exist")

    print("[P1-6] PASSED\n")
    return True


def run_all_tests():
    """运行所有P1修复验证测试"""
    print("=" * 60)
    print("P1 Security Fixes Verification Tests")
    print("=" * 60)

    results = []

    tests = [
        ("P1-1", test_p1_1_database_pool_limits),
        ("P1-2", test_p1_2_config_validation),
        ("P1-3", test_p1_3_sensitive_data_masking),
        ("P1-4", test_p1_4_agent_timeout_control),
        ("P1-5", test_p1_5_cache_collision_protection),
        ("P1-6", test_p1_6_dead_letter_cleanup),
    ]

    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result, None))
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"[{name}] FAILED: {e}\n")

    print("=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    passed = sum(1 for _, r, _ in results if r)
    total = len(results)

    for name, result, error in results:
        status = "PASSED" if result else f"FAILED: {error}"
        print(f"  {name}: {status}")

    print(f"\nTotal: {passed}/{total} passed")

    if passed == total:
        print("\nAll P1 fixes verified!")
        return 0
    else:
        print("\nSome tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
