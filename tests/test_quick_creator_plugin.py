#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快捷创作生成器插件测试套件

测试覆盖：
1. 插件元数据和基础功能
2. 数据模型验证
3. Prompt模板系统
4. 缓存机制
5. 异常类型

创建日期: 2026-03-24
作者: 高级开发工程师
"""

import unittest
import tempfile
import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 使用项目包导入
try:
    from plugins.quick_creator_v1.plugin import (
        QuickCreationPlugin,
        CreationType,
        GenerationType,
        QuickCreationError,
        QuickCreationTimeoutError,
        QuickCreationAPIError
    )
except ImportError:
    # 备用方式：使用importlib处理带连字符的模块名
    import importlib.util
    
    # 加载依赖模块
    ref_parser_spec = importlib.util.spec_from_file_location(
        "reference_parser",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "plugins", "quick-creator-v1", "reference_parser.py")
    )
    reference_parser_module = importlib.util.module_from_spec(ref_parser_spec)
    sys.modules['reference_parser'] = reference_parser_module
    ref_parser_spec.loader.exec_module(reference_parser_module)
    
    result_storage_spec = importlib.util.spec_from_file_location(
        "result_storage",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "plugins", "quick-creator-v1", "result_storage.py")
    )
    result_storage_module = importlib.util.module_from_spec(result_storage_spec)
    sys.modules['result_storage'] = result_storage_module
    result_storage_spec.loader.exec_module(result_storage_module)
    
    spec = importlib.util.spec_from_file_location(
        "plugin",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "plugins", "quick-creator-v1", "plugin.py")
    )
    plugin_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin_module)

    QuickCreationPlugin = plugin_module.QuickCreationPlugin
    CreationType = plugin_module.CreationType
    GenerationType = plugin_module.GenerationType
    QuickCreationError = plugin_module.QuickCreationError
    QuickCreationTimeoutError = plugin_module.QuickCreationTimeoutError
    QuickCreationAPIError = plugin_module.QuickCreationAPIError


class TestQuickCreationPluginMetadata(unittest.TestCase):
    """测试插件元数据"""
    
    def test_plugin_metadata_exists(self):
        """测试插件元数据存在"""
        metadata = QuickCreationPlugin.get_metadata()
        self.assertIsNotNone(metadata)
    
    def test_plugin_id(self):
        """测试插件ID"""
        metadata = QuickCreationPlugin.get_metadata()
        self.assertEqual(metadata.id, "quick-creator-v1")
    
    def test_plugin_version(self):
        """测试插件版本"""
        metadata = QuickCreationPlugin.get_metadata()
        self.assertEqual(metadata.version, "1.3.0")
    
    def test_plugin_type(self):
        """测试插件类型"""
        from core.plugin_interface import PluginType
        metadata = QuickCreationPlugin.get_metadata()
        self.assertEqual(metadata.plugin_type, PluginType.GENERATOR)


class TestQuickCreationPluginBasic(unittest.TestCase):
    """测试插件基础功能"""
    
    def setUp(self):
        """设置测试环境"""
        self.plugin = QuickCreationPlugin()
    
    def test_plugin_initialization(self):
        """测试插件初始化"""
        self.assertIsNotNone(self.plugin)
        self.assertIsNone(self.plugin.api_client)
    
    def test_set_api_client(self):
        """测试设置API客户端"""
        mock_client = Mock()
        self.plugin.set_api_client(mock_client)
        self.assertEqual(self.plugin.api_client, mock_client)
    
    def test_get_available_creation_types(self):
        """测试获取可用创作类型"""
        types = self.plugin.get_available_creation_types()
        self.assertIn("worldview", types)
        self.assertIn("outline", types)
        self.assertIn("character", types)
        self.assertIn("plot", types)
        self.assertIn("all", types)
    
    def test_get_generation_types(self):
        """测试获取生成详细程度选项"""
        types = self.plugin.get_generation_types()
        self.assertIn("quick", types)
        self.assertIn("standard", types)
        self.assertIn("detailed", types)
    
    def test_clear_cache(self):
        """测试清除缓存"""
        self.plugin._generation_history = {"test": "data"}
        self.plugin.clear_cache()
        self.assertEqual(self.plugin._generation_history, {})


class TestPromptTemplates(unittest.TestCase):
    """测试Prompt模板系统"""
    
    def setUp(self):
        """设置测试环境"""
        self.plugin = QuickCreationPlugin()
        # 模拟初始化加载模板
        self.plugin._load_prompt_templates()
    
    def test_worldview_template_exists(self):
        """测试世界观模板存在"""
        self.assertIn("worldview", self.plugin._prompt_templates)
    
    def test_outline_template_exists(self):
        """测试大纲模板存在"""
        self.assertIn("outline", self.plugin._prompt_templates)
    
    def test_character_template_exists(self):
        """测试人物模板存在"""
        self.assertIn("character", self.plugin._prompt_templates)
    
    def test_plot_template_exists(self):
        """测试情节模板存在"""
        self.assertIn("plot", self.plugin._prompt_templates)
    
    def test_render_prompt(self):
        """测试渲染Prompt模板"""
        template = self.plugin._prompt_templates["worldview"]
        system_prompt, user_prompt = self.plugin._render_prompt(template, {
            "keywords": "修仙、穿越",
            "reference_text": "无",
            "genre": "玄幻",
            "generation_type": "standard"
        })
        
        self.assertIn("修仙、穿越", user_prompt)
        self.assertIn("玄幻", user_prompt)


class TestExceptionTypes(unittest.TestCase):
    """测试自定义异常类型"""
    
    def test_base_exception(self):
        """测试基础异常"""
        with self.assertRaises(QuickCreationError):
            raise QuickCreationError("测试异常")
    
    def test_timeout_exception(self):
        """测试超时异常"""
        with self.assertRaises(QuickCreationTimeoutError):
            raise QuickCreationTimeoutError("调用超时")
    
    def test_api_exception(self):
        """测试API异常"""
        with self.assertRaises(QuickCreationAPIError):
            raise QuickCreationAPIError("API调用失败")
    
    def test_exception_inheritance(self):
        """测试异常继承关系"""
        self.assertTrue(issubclass(QuickCreationTimeoutError, QuickCreationError))
        self.assertTrue(issubclass(QuickCreationAPIError, QuickCreationError))


class TestCacheMechanism(unittest.TestCase):
    """测试缓存机制"""
    
    def setUp(self):
        """设置测试环境"""
        self.plugin = QuickCreationPlugin()
        self.temp_dir = tempfile.mkdtemp()
        self.plugin._cache_file = Path(self.temp_dir) / "test_cache.json"
    
    def tearDown(self):
        """清理测试环境"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_save_cache_to_disk(self):
        """测试保存缓存到磁盘"""
        self.plugin._generation_history = {
            "worldview": {"world_name": "测试世界"}
        }
        
        result = self.plugin.save_cache_to_disk()
        self.assertTrue(result)
        self.assertTrue(self.plugin._cache_file.exists())
    
    def test_load_cache_from_disk(self):
        """测试从磁盘加载缓存"""
        # 先保存
        self.plugin._generation_history = {
            "worldview": {"world_name": "测试世界"}
        }
        self.plugin.save_cache_to_disk()
        
        # 清除后重新加载
        self.plugin._generation_history = {}
        result = self.plugin._load_cache_from_disk()
        
        self.assertTrue(result)
        self.assertIn("worldview", self.plugin._generation_history)
    
    def test_get_cache_stats(self):
        """测试获取缓存统计"""
        self.plugin._generation_history = {
            "worldview": {"world_name": "测试世界"},
            "characters": {"主角": {"name": "张三"}}
        }
        
        stats = self.plugin.get_cache_stats()
        
        self.assertTrue(stats["worldview_cached"])
        self.assertFalse(stats["outline_cached"])
        self.assertEqual(stats["characters_count"], 1)


class TestJSONParsing(unittest.TestCase):
    """测试JSON解析"""
    
    def setUp(self):
        """设置测试环境"""
        self.plugin = QuickCreationPlugin()
    
    def test_parse_valid_json(self):
        """测试解析有效JSON"""
        response = '这是一些文本 {"name": "测试", "value": 123} 还有其他内容'
        result = self.plugin._parse_json_response(response)
        
        self.assertEqual(result["name"], "测试")
        self.assertEqual(result["value"], 123)
    
    def test_parse_invalid_json(self):
        """测试解析无效JSON"""
        response = "这不是JSON格式"
        result = self.plugin._parse_json_response(response)
        
        self.assertIn("raw_content", result)


class TestHelperMethods(unittest.TestCase):
    """测试辅助方法"""
    
    def setUp(self):
        """设置测试环境"""
        self.plugin = QuickCreationPlugin()
    
    def test_get_worldview_summary_empty(self):
        """测试获取空世界观概述"""
        summary = self.plugin._get_worldview_summary()
        self.assertEqual(summary, "")
    
    def test_get_worldview_summary_with_data(self):
        """测试获取有数据的世界观概述"""
        self.plugin._generation_history = {
            "worldview": {
                "world_name": "仙界",
                "social_structure": "修仙门派林立"
            }
        }
        
        summary = self.plugin._get_worldview_summary()
        self.assertIn("仙界", summary)
    
    def test_get_outline_summary_empty(self):
        """测试获取空大纲概述"""
        summary = self.plugin._get_outline_summary()
        self.assertEqual(summary, "")
    
    def test_get_outline_summary_with_data(self):
        """测试获取有大纲的概述"""
        long_text = "这是一段很长的大纲内容。" * 100
        self.plugin._generation_history = {
            "outline": long_text
        }
        
        summary = self.plugin._get_outline_summary()
        self.assertLessEqual(len(summary), 503)  # 500 + "..."


class TestAPIErrorHandling(unittest.TestCase):
    """测试API错误处理"""
    
    def setUp(self):
        """设置测试环境"""
        self.plugin = QuickCreationPlugin()
    
    def test_call_llm_without_client(self):
        """测试无客户端调用LLM"""
        with self.assertRaises(QuickCreationAPIError):
            self.plugin._call_llm("system", "user")


if __name__ == "__main__":
    unittest.main(verbosity=2)
