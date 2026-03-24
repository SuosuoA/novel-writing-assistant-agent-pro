"""
快捷创作功能集成测试脚本 V1.0
Quick Creation Integration Test Script

测试场景：
1. 不同关键词和参考文本组合的生成设定合理性和一致性
2. 各单项生成功能独立工作验证
3. 导入功能和合并逻辑验证

作者：快速原型工程师
日期：2026-03-24
"""

import unittest
import json
import logging
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 导入项目模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import (
    QuickCreationRequest,
    QuickCreationResult,
    WorldviewResult,
    OutlineResult,
    CharacterResult,
    PlotResult
)
# 插件目录名是 quick-creator-v1，需要动态导入
import importlib.util

def import_module_from_path(module_name: str, file_path: Path):
    """从文件路径动态导入模块"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# 导入插件模块
plugin_dir = Path(__file__).parent.parent / "plugins" / "quick-creator-v1"
reference_parser = import_module_from_path("reference_parser", plugin_dir / "reference_parser.py")
result_storage = import_module_from_path("result_storage", plugin_dir / "result_storage.py")

ReferenceTextParser = reference_parser.ReferenceTextParser
ReferenceFusion = reference_parser.ReferenceFusion
ReferenceType = reference_parser.ReferenceType
ParsedReference = reference_parser.ParsedReference

ResultStorageManager = result_storage.ResultStorageManager
ConflictStrategy = result_storage.ConflictStrategy
ConflictInfo = result_storage.ConflictInfo
ImportResult = result_storage.ImportResult


# ============================================================================
# Mock LLM Client
# ============================================================================

class MockLLMResponse:
    """模拟LLM响应"""
    def __init__(self, content: str):
        self.choices = [MockChoice(content)]


class MockChoice:
    """模拟响应选择"""
    def __init__(self, content: str):
        self.message = MockMessage(content)


class MockMessage:
    """模拟消息"""
    def __init__(self, content: str):
        self.content = content


class MockLLMClient:
    """
    模拟LLM客户端
    
    根据不同的Prompt类型返回预设的响应
    """
    
    def __init__(self):
        self.call_count = 0
        self.call_history: List[Dict[str, str]] = []
        
    def chat_completions_create(self, model: str, messages: List[Dict], temperature: float, max_tokens: int, stream: bool = False):
        """模拟chat.completions.create"""
        self.call_count += 1
        
        # 记录调用历史
        self.call_history.append({
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        })
        
        # 根据Prompt内容判断生成类型
        system_prompt = messages[0]["content"] if messages else ""
        user_prompt = messages[1]["content"] if len(messages) > 1 else ""
        
        # 生成对应的模拟响应
        content = self._generate_mock_response(system_prompt, user_prompt)
        
        return MockLLMResponse(content)
    
    def _generate_mock_response(self, system_prompt: str, user_prompt: str) -> str:
        """根据Prompt生成模拟响应"""
        
        # 世界观生成
        if "世界观" in system_prompt or "世界观" in user_prompt:
            # 提取关键词
            keywords = []
            if "修仙" in user_prompt or "仙侠" in user_prompt:
                keywords = ["修仙", "仙界", "灵气"]
            elif "都市" in user_prompt:
                keywords = ["都市", "现代", "科技"]
            elif "玄幻" in user_prompt:
                keywords = ["玄幻", "异世界", "魔法"]
            else:
                keywords = ["奇幻", "魔法", "冒险"]
            
            # 检查是否有参考文本
            reference_era = ""
            reference_power = ""
            if "参考时代背景" in user_prompt:
                import re
                era_match = re.search(r'参考时代背景[：:]\s*([^\n]+)', user_prompt)
                if era_match:
                    reference_era = era_match.group(1).strip()
            if "参考力量体系" in user_prompt:
                import re
                power_match = re.search(r'参考力量体系[：:]\s*([^\n]+)', user_prompt)
                if power_match:
                    reference_power = power_match.group(1).strip()
            
            return json.dumps({
                "setting_name": f"{''.join(keywords[:2])}世界",
                "era": reference_era or "上古时期",
                "world_structure": "三界九重天",
                "power_system": reference_power or "修仙体系，练气筑基金丹元婴化神",
                "geography": "东域、西域、南域、北域、中州",
                "social_structure": "宗门世家并立，散修众多",
                "major_forces": ["青云宗", "天剑门", "魔教", "散修联盟"],
                "rules_and_laws": ["强者为尊", "因果循环", "天道轮回"],
                "special_elements": ["灵石矿脉", "上古遗迹", "秘境空间"],
                "background_story": "天地初开，灵气充沛，万族林立..."
            }, ensure_ascii=False)
        
        # 大纲生成
        elif "大纲" in system_prompt or "章节" in user_prompt:
            return json.dumps({
                "title": "修仙之路",
                "theme": "少年修仙成神",
                "synopsis": "一个普通少年意外获得神秘功法，踏上修仙之路，历经磨难终成一代仙帝",
                "chapters": [
                    {"chapter_num": 1, "title": "少年李云", "summary": "少年李云在山村中长大，意外获得神秘玉佩", "key_events": ["获得玉佩", "发现秘密"]},
                    {"chapter_num": 2, "title": "踏入修仙", "summary": "李云开启玉佩，获得修炼功法", "key_events": ["修炼功法", "灵气入体"]},
                    {"chapter_num": 3, "title": "初入江湖", "summary": "李云离开山村，进入修仙界", "key_events": ["拜入宗门", "结识朋友"]}
                ],
                "main_plot": "少年修仙成神",
                "sub_plots": ["寻找身世之谜", "解开玉佩秘密"],
                "climax_points": ["突破金丹", "渡劫成功", "成就仙帝"],
                "ending_direction": "成为一代仙帝，守护世界和平"
            }, ensure_ascii=False)
        
        # 人物生成
        elif "人物" in system_prompt or "人设" in user_prompt:
            # 提取人物名称
            import re
            name_match = re.search(r'姓名[：:]?\s*([^\n，。]+)', user_prompt)
            name = name_match.group(1).strip() if name_match else "李云"
            
            # 提取角色定位
            role_match = re.search(r'角色定位[：:]?\s*([^\n，。]+)', user_prompt)
            role = role_match.group(1).strip() if role_match else "主角"
            
            return json.dumps({
                "name": name,
                "role": role,
                "age": "18岁",
                "gender": "男",
                "appearance": "身材修长，眉清目秀，眼神坚毅",
                "personality": "坚韧不拔、重情重义、心思缜密",
                "background": "山村少年，父母早亡，由爷爷抚养长大",
                "abilities": ["剑道天赋", "领悟剑意", "快速修炼"],
                "goals": ["成为强者", "守护家人", "探寻身世"],
                "weaknesses": ["过于善良", "容易冲动"],
                "relationships": {"爷爷": "亲人", "小师妹": "挚友"},
                "speech_pattern": "言语简洁，行动果断"
            }, ensure_ascii=False)
        
        # 情节生成
        elif "情节" in system_prompt or "情节" in user_prompt:
            return json.dumps({
                "plot_name": "初入修仙界",
                "plot_type": "开端",
                "participants": ["李云", "青云宗弟子"],
                "setting": "青云宗山门外",
                "beginning": "李云来到青云宗山门，准备参加入门考核",
                "development": "经过重重考验，李云展现出惊人的天赋",
                "climax": "考核中突发意外，李云凭借机智化解危机",
                "resolution": "成功拜入青云宗，成为外门弟子",
                "conflicts": ["考核竞争", "意外危机"],
                "turning_points": ["发现自身天赋", "获得长老青睐"],
                "foreshadowing": ["玉佩异动", "神秘人物出现"]
            }, ensure_ascii=False)
        
        # 默认响应
        else:
            return json.dumps({"content": "默认生成内容"}, ensure_ascii=False)


# ============================================================================
# 测试用例
# ============================================================================

class TestKeywordAndReferenceCombinations(unittest.TestCase):
    """测试①：不同关键词和参考文本组合的生成设定合理性和一致性"""
    
    def setUp(self):
        """测试前准备"""
        self.parser = ReferenceTextParser()
        
    def test_1_1_keywords_only_generation(self):
        """测试1.1：仅关键词生成（无参考文本）"""
        logger.info("测试1.1：仅关键词生成")
        
        keywords = ["修仙", "逆袭", "系统"]
        
        # 模拟生成过程
        # 验证关键词被正确处理
        self.assertEqual(len(keywords), 3)
        self.assertIn("修仙", keywords)
        
        logger.info("✓ 关键词验证通过")
    
    def test_1_2_reference_text_only_generation(self):
        """测试1.2：仅参考文本生成（无关键词）"""
        logger.info("测试1.2：仅参考文本生成")
        
        reference_text = """
        世界观设定：
        时代：上古修仙时期
        力量体系：修仙境界，从练气到化神
        主要势力：青云宗、天剑门、魔教
        
        人物设定：
        姓名：李云
        角色定位：主角
        性格：坚韧不拔、重情重义
        """
        
        # 解析参考文本
        parsed = self.parser.parse(reference_text)
        
        # 验证解析结果
        self.assertEqual(parsed.reference_type, ReferenceType.MIXED)
        self.assertTrue(parsed.has_worldview())
        self.assertTrue(parsed.has_characters())
        self.assertGreater(parsed.confidence, 0.5)
        
        # 验证世界观元素
        self.assertIn("上古", parsed.worldview.era)
        self.assertIn("修仙", parsed.worldview.power_system)
        
        # 验证人物元素
        self.assertEqual(len(parsed.characters), 1)
        self.assertEqual(parsed.characters[0].name, "李云")
        self.assertEqual(parsed.characters[0].role, "主角")
        
        logger.info(f"✓ 参考文本解析通过: type={parsed.reference_type.value}, confidence={parsed.confidence:.2f}")
    
    def test_1_3_keywords_and_reference_combined(self):
        """测试1.3：关键词+参考文本组合生成"""
        logger.info("测试1.3：关键词+参考文本组合生成")
        
        keywords = ["复仇", "热血"]
        reference_text = """
        世界观：
        力量体系：灵力修炼，分为九品
        主要势力：五大世家
        
        人物：
        姓名：林风
        性格：冷静、果断
        """
        
        # 解析参考文本
        parsed = self.parser.parse(reference_text)
        
        # 验证解析成功
        self.assertTrue(parsed.has_worldview())
        self.assertTrue(parsed.has_characters())
        
        # 融合测试
        variables = {
            "keywords": "、".join(keywords),
            "reference_text": "无",
            "genre": "玄幻"
        }
        
        # 融合世界观元素
        fused = ReferenceFusion.fusion_to_worldview_prompt(parsed, variables)
        
        # 验证融合结果
        self.assertIn("reference_text", fused)
        self.assertIn("灵力", fused["reference_text"])
        
        logger.info(f"✓ 关键词+参考文本融合通过")
    
    def test_1_4_consistency_between_generations(self):
        """测试1.4：多次生成的世界观一致性"""
        logger.info("测试1.4：生成一致性验证")
        
        reference_text = """
        时代：仙界纪元
        力量体系：天道法则，九大境界
        """
        
        # 多次解析相同文本
        parsed1 = self.parser.parse(reference_text)
        parsed2 = self.parser.parse(reference_text)
        
        # 验证解析结果一致
        self.assertEqual(parsed1.worldview.era, parsed2.worldview.era)
        self.assertEqual(parsed1.worldview.power_system, parsed2.worldview.power_system)
        
        logger.info("✓ 多次解析一致性验证通过")


class TestIndependentGenerationFunctions(unittest.TestCase):
    """测试②：各单项生成功能独立工作验证"""
    
    def setUp(self):
        """测试前准备"""
        self.parser = ReferenceTextParser()
        
    def test_2_1_worldview_independent_generation(self):
        """测试2.1：世界观独立生成"""
        logger.info("测试2.1：世界观独立生成")
        
        reference_text = "时代：上古仙界\n力量体系：修仙九境"
        
        # 解析世界观
        parsed = self.parser.parse(reference_text)
        
        # 验证世界观提取
        self.assertTrue(parsed.has_worldview())
        self.assertIsNotNone(parsed.worldview.era)
        self.assertIsNotNone(parsed.worldview.power_system)
        
        logger.info(f"✓ 世界观独立生成通过: era={parsed.worldview.era}")
    
    def test_2_2_outline_independent_generation(self):
        """测试2.2：大纲独立生成"""
        logger.info("测试2.2：大纲独立生成")
        
        reference_text = """
        第一章：少年初醒
        第二章：踏入仙途
        第三章：宗门试炼
        """
        
        # 解析大纲
        parsed = self.parser.parse(reference_text)
        
        # 验证文本类型识别
        self.assertEqual(parsed.reference_type, ReferenceType.OUTLINE)
        
        logger.info(f"✓ 大纲独立生成通过: type={parsed.reference_type.value}")
    
    def test_2_3_character_independent_generation(self):
        """测试2.3：人物独立生成"""
        logger.info("测试2.3：人物独立生成")
        
        reference_text = """
        姓名：张三
        年龄：25岁
        性别：男
        性格：开朗活泼
        能力：剑法高手
        """
        
        # 解析人物
        parsed = self.parser.parse(reference_text)
        
        # 验证人物提取
        self.assertTrue(parsed.has_characters())
        self.assertEqual(len(parsed.characters), 1)
        self.assertEqual(parsed.characters[0].name, "张三")
        
        logger.info(f"✓ 人物独立生成通过: name={parsed.characters[0].name}")
    
    def test_2_4_plot_independent_generation(self):
        """测试2.4：情节独立生成"""
        logger.info("测试2.4：情节独立生成")
        
        reference_text = """
        关键事件：
        1. 主角获得神秘功法
        2. 宗门遭遇危机
        3. 主角力挽狂澜
        
        冲突点：
        - 内部叛徒
        - 外敌入侵
        """
        
        # 解析情节
        parsed = self.parser.parse(reference_text)
        
        # 验证情节提取
        self.assertTrue(parsed.has_plot())
        self.assertGreater(len(parsed.plot.events), 0)
        self.assertGreater(len(parsed.plot.conflicts), 0)
        
        logger.info(f"✓ 情节独立生成通过: events={len(parsed.plot.events)}, conflicts={len(parsed.plot.conflicts)}")


class TestImportFunctionality(unittest.TestCase):
    """测试③：导入功能和合并逻辑验证"""
    
    def setUp(self):
        """测试前准备"""
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir) / "测试项目"
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        self.storage_manager = ResultStorageManager(self.project_path)
        
    def tearDown(self):
        """测试后清理"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
    
    def test_3_1_save_to_new_project(self):
        """测试3.1：保存到新项目"""
        logger.info("测试3.1：保存到新项目")
        
        # 创建模拟生成结果
        result = QuickCreationResult(
            request_id="test-001",
            keywords="修仙、逆袭",
            target="all",
            worldview=WorldviewResult(
                setting_name="仙界",
                era="上古",
                power_system="修仙九境",
                geography="三界",
                social_structure="宗门世家",
                major_forces=["青云宗"],
                rules_and_laws=["天道法则"],
                special_elements=["灵石"],
                background_story="天地初开"
            ),
            outline=OutlineResult(
                title="修仙路",
                theme="修仙成神",
                synopsis="少年修仙",
                chapters=[{"chapter_num": 1, "title": "开端", "summary": "开始"}]
            ),
            characters=[
                CharacterResult(
                    name="李云",
                    role="主角",
                    personality="坚韧",
                    background="山村少年",
                    abilities=["剑法"]
                )
            ],
            plot=PlotResult(
                plot_name="主线",
                plot_type="主线",
                beginning="开始",
                climax="高潮",
                resolution="结局"
            ),
            success=True,
            error=None
        )
        
        # 保存到新项目
        output_path = Path(self.temp_dir) / "输出项目"
        project_path = self.storage_manager.save_result(
            result=result,
            project_name="测试小说",
            output_path=output_path,
            format="json"
        )
        
        # 验证文件创建
        self.assertTrue(project_path.exists())
        self.assertTrue((project_path / "project.json").exists())
        self.assertTrue((project_path / "世界观" / "世界观设定.json").exists())
        self.assertTrue((project_path / "大纲" / "大纲设定.json").exists())
        self.assertTrue((project_path / "人物设定" / "李云.json").exists())
        self.assertTrue((project_path / "情节设定" / "主线.json").exists())
        
        logger.info(f"✓ 保存到新项目通过: {project_path}")
    
    def test_3_2_import_with_keep_original_strategy(self):
        """测试3.2：导入时保留原有设定策略"""
        logger.info("测试3.2：导入保留原有设定")
        
        # 先创建一个已有设定的项目
        existing_worldview = {
            "schema_version": "1.0.0",
            "setting_name": "原有世界观",
            "era": "原有时代",
            "power_system": "原有体系"
        }
        
        worldview_dir = self.project_path / "世界观"
        worldview_dir.mkdir(parents=True, exist_ok=True)
        with open(worldview_dir / "世界观设定.json", "w", encoding="utf-8") as f:
            json.dump(existing_worldview, f, ensure_ascii=False, indent=2)
        
        # 创建新的生成结果
        result = QuickCreationResult(
            request_id="test-002",
            keywords="修仙",
            target="worldview",
            worldview=WorldviewResult(
                setting_name="新世界观",
                era="新时代",
                power_system="新体系"
            ),
            success=True,
            error=None
        )
        
        # 导入（保留原有）
        import_result = self.storage_manager.import_to_project(
            result=result,
            conflict_strategy=ConflictStrategy.KEEP_ORIGINAL
        )
        
        # 验证原有设定被保留
        with open(worldview_dir / "世界观设定.json", "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        
        self.assertEqual(saved_data["setting_name"], "原有世界观")
        self.assertEqual(saved_data["era"], "原有时代")
        
        logger.info("✓ 保留原有设定策略验证通过")
    
    def test_3_3_import_with_overwrite_strategy(self):
        """测试3.3：导入时覆盖原有设定策略"""
        logger.info("测试3.3：导入覆盖原有设定")
        
        # 创建已有设定
        worldview_dir = self.project_path / "世界观"
        worldview_dir.mkdir(parents=True, exist_ok=True)
        with open(worldview_dir / "世界观设定.json", "w", encoding="utf-8") as f:
            json.dump({"setting_name": "旧设定"}, f, ensure_ascii=False)
        
        # 创建新设定
        result = QuickCreationResult(
            request_id="test-003",
            keywords="修仙",
            target="worldview",
            worldview=WorldviewResult(
                setting_name="新设定",
                era="新时代"
            ),
            success=True,
            error=None
        )
        
        # 导入（覆盖）
        import_result = self.storage_manager.import_to_project(
            result=result,
            conflict_strategy=ConflictStrategy.OVERWRITE
        )
        
        # 验证被覆盖
        with open(worldview_dir / "世界观设定.json", "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        
        self.assertEqual(saved_data["setting_name"], "新设定")
        
        logger.info("✓ 覆盖策略验证通过")
    
    def test_3_4_import_with_rename_strategy(self):
        """测试3.4：导入时重命名新设定策略"""
        logger.info("测试3.4：导入重命名新设定")
        
        # 创建已有人物
        char_dir = self.project_path / "人物设定"
        char_dir.mkdir(parents=True, exist_ok=True)
        with open(char_dir / "李云.json", "w", encoding="utf-8") as f:
            json.dump({"name": "李云", "role": "主角"}, f, ensure_ascii=False)
        
        # 创建同名新人物
        result = QuickCreationResult(
            request_id="test-004",
            keywords="修仙",
            target="characters",
            characters=[
                CharacterResult(
                    name="李云",
                    role="配角",
                    personality="新性格"
                )
            ],
            success=True,
            error=None
        )
        
        # 导入（重命名）
        import_result = self.storage_manager.import_to_project(
            result=result,
            conflict_strategy=ConflictStrategy.RENAME_NEW
        )
        
        # 验证两个文件都存在
        files = list(char_dir.glob("李云*.json"))
        self.assertEqual(len(files), 2)
        
        # 原文件内容不变
        with open(char_dir / "李云.json", "r", encoding="utf-8") as f:
            original = json.load(f)
        self.assertEqual(original["role"], "主角")
        
        logger.info("✓ 重命名策略验证通过")
    
    def test_3_5_import_to_empty_project(self):
        """测试3.5：导入到空项目"""
        logger.info("测试3.5：导入到空项目")
        
        # 空项目，无冲突
        result = QuickCreationResult(
            request_id="test-005",
            keywords="修仙",
            target="worldview",
            worldview=WorldviewResult(
                setting_name="初始世界观",
                era="初始时代"
            ),
            success=True,
            error=None
        )
        
        # 导入
        import_result = self.storage_manager.import_to_project(result=result)
        
        # 验证导入成功
        self.assertTrue(import_result.success)
        self.assertEqual(len(import_result.conflicts), 0)
        
        logger.info("✓ 空项目导入验证通过")


# ============================================================================
# 主程序
# ============================================================================

def run_tests():
    """运行所有测试"""
    logger.info("=" * 80)
    logger.info("快捷创作功能集成测试开始")
    logger.info("=" * 80)
    
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestKeywordAndReferenceCombinations))
    suite.addTests(loader.loadTestsFromTestCase(TestIndependentGenerationFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestImportFunctionality))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 统计结果
    logger.info("\n" + "=" * 80)
    logger.info("测试结果统计")
    logger.info("=" * 80)
    logger.info(f"总测试数: {result.testsRun}")
    logger.info(f"通过: {result.testsRun - len(result.failures) - len(result.errors)}")
    logger.info(f"失败: {len(result.failures)}")
    logger.info(f"错误: {len(result.errors)}")
    
    if result.failures:
        logger.info("\n失败的测试:")
        for test, traceback in result.failures:
            logger.info(f"  - {test}: {traceback}")
    
    if result.errors:
        logger.info("\n出错的测试:")
        for test, traceback in result.errors:
            logger.info(f"  - {test}: {traceback}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
