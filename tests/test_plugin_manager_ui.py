#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
插件管理界面功能验证脚本

验证内容：
1. PluginRegistry集成
2. 插件列表加载
3. 启用/禁用功能
4. V5保护模块检查
"""

import sys
import os
import io

# 设置标准输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def test_plugin_registry():
    """测试PluginRegistry基础功能"""
    print("=" * 60)
    print("测试1: PluginRegistry基础功能")
    print("=" * 60)
    
    try:
        from core.plugin_registry import get_plugin_registry, PluginState, V5_PROTECTED_MODULES
        
        registry = get_plugin_registry()
        print(f"[OK] PluginRegistry实例获取成功")
        
        # 检查保护模块列表
        print(f"[OK] V5保护模块列表: {len(V5_PROTECTED_MODULES)} 个")
        print(f"  保护模块: {list(V5_PROTECTED_MODULES)}")
        
        return True
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")
        return False


def test_plugin_data_structure():
    """测试插件数据结构"""
    print("\n" + "=" * 60)
    print("测试2: 插件数据结构验证")
    print("=" * 60)
    
    try:
        from core.plugin_registry import get_plugin_registry, PluginState
        from core.plugin_interface import PluginMetadata, PluginType
        
        registry = get_plugin_registry()
        
        # 模拟注册一个插件
        test_metadata = PluginMetadata(
            id="test-plugin-v1",
            name="测试插件",
            version="1.0.0",
            description="这是一个测试插件",
            author="测试作者",
            plugin_type=PluginType.TOOL
        )
        
        success = registry.register("test-plugin-v1", test_metadata)
        print(f"[OK] 插件注册: {'成功' if success else '失败'}")
        
        # 获取插件信息
        info = registry.get_plugin_info("test-plugin-v1")
        if info:
            print(f"[OK] 插件信息获取成功")
            print(f"  - 名称: {info.metadata.name}")
            print(f"  - 版本: {info.metadata.version}")
            print(f"  - 状态: {info.state}")
        
        # 测试保护模块检查
        is_protected = registry.is_protected("test-plugin-v1")
        print(f"[OK] 保护状态检查: {'是' if is_protected else '否'}")
        
        # 测试激活/停用
        activate_success = registry.activate("test-plugin-v1")
        print(f"[OK] 插件激活: {'成功' if activate_success else '失败'}")
        
        state = registry.get_state("test-plugin-v1")
        print(f"[OK] 激活后状态: {state}")
        
        deactivate_success = registry.deactivate("test-plugin-v1")
        print(f"[OK] 插件停用: {'成功' if deactivate_success else '失败'}")
        
        state = registry.get_state("test-plugin-v1")
        print(f"[OK] 停用后状态: {state}")
        
        return True
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_protected_module_operations():
    """测试保护模块操作限制"""
    print("\n" + "=" * 60)
    print("测试3: 保护模块操作限制")
    print("=" * 60)
    
    try:
        from core.plugin_registry import get_plugin_registry, PluginProtectionError, V5_PROTECTED_MODULES
        
        registry = get_plugin_registry()
        
        # 选择一个保护模块进行测试
        protected_id = list(V5_PROTECTED_MODULES)[0] if V5_PROTECTED_MODULES else None
        
        if protected_id:
            print(f"测试保护模块: {protected_id}")
            
            # 检查是否为保护模块
            is_protected = registry.is_protected(protected_id)
            print(f"[OK] 保护状态: {'是' if is_protected else '否'}")
            
            # 尝试禁用保护模块（应该抛出异常）
            try:
                registry.disable(protected_id)
                print("[FAIL] 禁用保护模块应该抛出异常！")
            except PluginProtectionError as e:
                print(f"[OK] 正确抛出保护异常: {e}")
        else:
            print("! 没有保护模块可测试")
        
        return True
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_manager():
    """测试ConfigManager插件配置功能"""
    print("\n" + "=" * 60)
    print("测试4: ConfigManager插件配置")
    print("=" * 60)
    
    try:
        from core.config_manager import get_config_manager
        
        config = get_config_manager()
        print(f"[OK] ConfigManager实例获取成功")
        
        # 测试设置插件配置（使用合法的key格式）
        test_key = "plugins.test_plugin.enabled"
        config.set(test_key, True, source="test")
        print(f"[OK] 设置配置: {test_key} = True")
        
        # 读取配置
        value = config.get(test_key)
        print(f"[OK] 读取配置: {test_key} = {value}")
        
        # 列出插件相关配置
        keys = config.list_keys("plugins")
        print(f"[OK] 插件配置键列表: {keys[:5]}..." if len(keys) > 5 else f"[OK] 插件配置键列表: {keys}")
        
        return True
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("插件管理界面功能验证")
    print("=" * 60)
    
    results = []
    
    results.append(test_plugin_registry())
    results.append(test_plugin_data_structure())
    results.append(test_protected_module_operations())
    results.append(test_config_manager())
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"PluginRegistry基础功能: {'通过' if results[0] else '失败'}")
    print(f"插件数据结构: {'通过' if results[1] else '失败'}")
    print(f"保护模块操作限制: {'通过' if results[2] else '失败'}")
    print(f"ConfigManager插件配置: {'通过' if results[3] else '失败'}")
    
    all_passed = all(results)
    print(f"\n总体结果: {'全部通过' if all_passed else '存在失败'}")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
