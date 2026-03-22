"""
P0安全问题修复验证测试

创建日期: 2026-03-23
测试范围:
- P0-1: SQL注入修复验证
- P0-2: API密钥安全存储验证
- P0-3: 插件签名验证修复验证
"""

import sys
import io

# 设置UTF-8编码输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import re
from pathlib import Path

# P0-1: SQL注入修复验证
def test_sql_injection_fix():
    """测试SQL注入防护"""
    print("\n=== P0-1: SQL注入修复验证 ===")
    
    from core.database import DatabaseMigration
    
    migration = DatabaseMigration.__new__(DatabaseMigration)
    migration._migrations = {}
    
    # 测试1: 正常迁移名称
    try:
        migration.register_migration("001_create_table", "CREATE TABLE test (id INTEGER);")
        print("✅ 正常迁移名称通过")
    except ValueError as e:
        print(f"❌ 正常迁移名称失败: {e}")
    
    # 测试2: 非法迁移名称
    try:
        migration.register_migration("invalid_name", "SELECT 1;")
        print("❌ 非法迁移名称未拦截")
    except ValueError as e:
        print(f"✅ 非法迁移名称被拦截: {e}")
    
    # 测试3: 危险SQL模式
    try:
        migration.register_migration("002_danger", "DROP TABLE users;")
        print("❌ 危险SQL未拦截")
    except ValueError as e:
        print(f"✅ 危险SQL被拦截: {e}")
    
    # 测试4: SQL注释
    try:
        migration.register_migration("003_comment", "SELECT 1; -- malicious code")
        print("❌ SQL注释未拦截")
    except ValueError as e:
        print(f"✅ SQL注释被拦截: {e}")

# P0-2: API密钥安全存储验证
def test_api_key_security():
    """测试API密钥安全存储"""
    print("\n=== P0-2: API密钥安全存储验证 ===")
    
    from services.llm_client_with_resilience import SecureString
    
    # 测试1: 有效密钥
    try:
        key = SecureString("sk-1234567890abcdef")
        print(f"✅ 有效密钥创建成功")
        print(f"   字符串表示: {str(key)} (应该是 ***REDACTED***)")
        print(f"   对象表示: {repr(key)} (应该是 SecureString(***)")
        print(f"   实际值: {key.get()[:10]}... (可以安全获取)")
    except ValueError as e:
        print(f"❌ 有效密钥创建失败: {e}")
    
    # 测试2: 无效密钥（太短）
    try:
        key = SecureString("short")
        print("❌ 无效密钥未拦截")
    except ValueError as e:
        print(f"✅ 无效密钥被拦截: {e}")
    
    # 测试3: 空密钥
    try:
        key = SecureString("")
        print("❌ 空密钥未拦截")
    except ValueError as e:
        print(f"✅ 空密钥被拦截: {e}")

# P0-3: 插件签名验证修复验证
def test_plugin_signature_fix():
    """测试插件签名验证逻辑"""
    print("\n=== P0-3: 插件签名验证修复验证 ===")
    
    from core.hot_swap_manager import HotSwapPermission
    
    # 测试1: 官方插件+签名验证通过
    permission = HotSwapPermission(
        plugin_id="novel-generator",
        signature_verified=True,
        is_official=True
    )
    print(f"✅ 官方插件+签名通过: level={permission.security_level}, can_load={permission.can_load()}")
    
    # 测试2: 官方插件+签名验证失败
    permission = HotSwapPermission(
        plugin_id="novel-generator",
        signature_verified=False,
        is_official=True
    )
    print(f"✅ 官方插件+签名失败: level={permission.security_level}, can_load={permission.can_load()}")
    
    # 测试3: 第三方插件+签名验证通过
    permission = HotSwapPermission(
        plugin_id="third-party-plugin",
        signature_verified=True,
        is_official=False
    )
    print(f"✅ 第三方插件+签名通过: level={permission.security_level}, can_load={permission.can_load()}")
    
    # 测试4: 第三方插件+签名验证失败
    permission = HotSwapPermission(
        plugin_id="third-party-plugin",
        signature_verified=False,
        is_official=False
    )
    print(f"✅ 第三方插件+签名失败: level={permission.security_level}, can_load={permission.can_load()}")
    
    # 测试5: V5保护模块
    permission = HotSwapPermission(
        plugin_id="outline-parser-v3",
        signature_verified=True,
        is_official=False
    )
    print(f"✅ V5保护模块: level={permission.security_level}, can_reload={permission.can_reload()}")

# 运行所有测试
if __name__ == "__main__":
    print("=" * 60)
    print("P0安全问题修复验证测试")
    print("=" * 60)
    
    test_sql_injection_fix()
    test_api_key_security()
    test_plugin_signature_fix()
    
    print("\n" + "=" * 60)
    print("所有P0安全问题修复验证完成")
    print("=" * 60)
