"""
快捷创作结果存储模块单元测试

测试内容：
1. ResultStorageManager 初始化
2. JSON Schema定义验证
3. save_result()保存功能
4. import_to_project()导入功能
5. 冲突处理策略
6. 便捷函数
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "plugins"))

# 导入测试模块
# 直接导入result_storage模块
import importlib.util
spec = importlib.util.spec_from_file_location(
    "result_storage",
    project_root / "plugins" / "quick-creator-v1" / "result_storage.py"
)
result_storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(result_storage)

# 从模块中获取类
ResultStorageManager = result_storage.ResultStorageManager
ConflictStrategy = result_storage.ConflictStrategy
ConflictInfo = result_storage.ConflictInfo
ImportResult = result_storage.ImportResult
save_quick_creation_result = result_storage.save_quick_creation_result
import_quick_creation_result = result_storage.import_quick_creation_result
WORLDVIEW_SCHEMA = result_storage.WORLDVIEW_SCHEMA
OUTLINE_SCHEMA = result_storage.OUTLINE_SCHEMA
CHARACTER_SCHEMA = result_storage.CHARACTER_SCHEMA
PLOT_SCHEMA = result_storage.PLOT_SCHEMA
SCHEMA_VERSION = result_storage.SCHEMA_VERSION

from core.models import (
    WorldviewResult,
    OutlineResult,
    CharacterResult,
    PlotResult,
    QuickCreationResult,
    QuickCreationMetadata
)


def test_storage_manager_init():
    """测试1: ResultStorageManager初始化"""
    print("测试1: ResultStorageManager初始化...")
    
    # 无路径初始化
    manager = ResultStorageManager()
    assert manager.project_path is None, "无路径初始化应设置project_path为None"
    
    # 有路径初始化
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = ResultStorageManager(Path(tmpdir))
        assert manager.project_path == Path(tmpdir), "有路径初始化应设置project_path"
        
        # 检查目录结构创建
        assert (Path(tmpdir) / "世界观").exists(), "应创建世界观目录"
        assert (Path(tmpdir) / "大纲").exists(), "应创建大纲目录"
        assert (Path(tmpdir) / "人物设定").exists(), "应创建人物设定目录"
        assert (Path(tmpdir) / "情节设定").exists(), "应创建情节设定目录"
    
    print("  [PASS] 初始化测试通过")


def test_json_schemas():
    """测试2: JSON Schema定义验证"""
    print("测试2: JSON Schema定义验证...")
    
    # 检查Schema存在
    assert WORLDVIEW_SCHEMA is not None, "世界观Schema应存在"
    assert OUTLINE_SCHEMA is not None, "大纲Schema应存在"
    assert CHARACTER_SCHEMA is not None, "人物Schema应存在"
    assert PLOT_SCHEMA is not None, "情节Schema应存在"
    
    # 检查Schema基本结构
    assert WORLDVIEW_SCHEMA.get("title") == "WorldviewSetting"
    assert OUTLINE_SCHEMA.get("title") == "OutlineSetting"
    assert CHARACTER_SCHEMA.get("title") == "CharacterSetting"
    assert PLOT_SCHEMA.get("title") == "PlotSetting"
    
    # 检查必需字段
    assert "setting_name" in WORLDVIEW_SCHEMA.get("required", [])
    assert "title" in OUTLINE_SCHEMA.get("required", [])
    assert "name" in CHARACTER_SCHEMA.get("required", [])
    assert "plot_name" in PLOT_SCHEMA.get("required", [])
    
    print("  [PASS] JSON Schema验证通过")


def test_save_result():
    """测试3: save_result保存功能"""
    print("测试3: save_result保存功能...")
    
    # 创建测试数据
    worldview = WorldviewResult(
        setting_name="玄幻世界",
        era="上古时代",
        power_system="修仙等级体系",
        major_forces=["天庭", "魔界"],
        rules_and_laws=["弱肉强食", "因果轮回"]
    )
    
    outline = OutlineResult(
        title="修仙之路",
        theme="逆袭成长",
        synopsis="少年从凡人成长为仙帝",
        chapters=[
            {"chapter_num": 1, "title": "开篇", "summary": "少年觉醒"}
        ]
    )
    
    characters = [
        CharacterResult(
            name="叶凡",
            role="主角",
            age="18",
            personality="坚毅不屈"
        ),
        CharacterResult(
            name="林月",
            role="女主",
            age="17",
            personality="温柔善良"
        )
    ]
    
    plot = PlotResult(
        plot_name="仙门大比",
        plot_type="主线",
        participants=["叶凡", "林月"],
        beginning="仙门选拔开始",
        climax="叶凡夺魁",
        resolution="进入仙门"
    )
    
    result = QuickCreationResult(
        keywords="修仙,逆袭",
        target="all",
        worldview=worldview,
        outline=outline,
        characters=characters,
        plot=plot,
        success=True
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = ResultStorageManager()
        project_path = manager.save_result(
            result,
            project_name="测试项目",
            output_path=Path(tmpdir),
            format="json"
        )
        
        # 检查项目目录结构
        assert project_path.exists(), "项目目录应存在"
        assert (project_path / "project.json").exists(), "项目元数据应存在"
        
        # 检查世界观文件
        worldview_file = project_path / "世界观" / "世界观设定.json"
        assert worldview_file.exists(), "世界观文件应存在"
        with open(worldview_file, 'r', encoding='utf-8') as f:
            wv_data = json.load(f)
        assert wv_data["setting_name"] == "玄幻世界"
        
        # 检查大纲文件
        outline_file = project_path / "大纲" / "大纲设定.json"
        assert outline_file.exists(), "大纲文件应存在"
        
        # 检查人物文件
        char_dir = project_path / "人物设定"
        assert char_dir.exists(), "人物设定目录应存在"
        assert (char_dir / "叶凡.json").exists(), "叶凡文件应存在"
        assert (char_dir / "林月.json").exists(), "林月文件应存在"
        
        # 检查情节文件
        plot_file = project_path / "情节设定" / "仙门大比.json"
        assert plot_file.exists(), "情节文件应存在"
        
        # 检查项目元数据
        with open(project_path / "project.json", 'r', encoding='utf-8') as f:
            meta = json.load(f)
        assert meta["project_name"] == "测试项目"
        assert "worldview" in meta["generated_items"]
        assert meta["success"] == True
    
    print("  [PASS] save_result保存测试通过")


def test_save_result_markdown():
    """测试4: save_result Markdown格式保存"""
    print("测试4: save_result Markdown格式保存...")
    
    worldview = WorldviewResult(
        setting_name="科幻世界",
        era="2150年",
        social_structure="星际联盟"
    )
    
    result = QuickCreationResult(
        keywords="科幻,未来",
        worldview=worldview,
        success=True
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = ResultStorageManager()
        project_path = manager.save_result(
            result,
            project_name="Markdown测试",
            output_path=Path(tmpdir),
            format="markdown"
        )
        
        # 检查Markdown文件
        worldview_file = project_path / "世界观" / "世界观设定.md"
        assert worldview_file.exists(), "世界观Markdown文件应存在"
        
        with open(worldview_file, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "# 科幻世界" in content, "Markdown应包含标题"
    
    print("  [PASS] Markdown保存测试通过")


def test_import_to_project():
    """测试5: import_to_project导入功能"""
    print("测试5: import_to_project导入功能...")
    
    worldview = WorldviewResult(
        setting_name="测试世界",
        era="现代"
    )
    
    result = QuickCreationResult(
        keywords="测试",
        worldview=worldview,
        success=True
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = ResultStorageManager(Path(tmpdir))
        
        # 首次导入
        import_result = manager.import_to_project(
            result,
            ConflictStrategy.KEEP_ORIGINAL
        )
        
        assert import_result.success, "导入应成功"
        assert "worldview" in import_result.imported_items
        assert len(import_result.conflicts) == 0, "首次导入无冲突"
        
        # 再次导入，检测冲突
        import_result2 = manager.import_to_project(
            result,
            ConflictStrategy.KEEP_ORIGINAL
        )
        
        assert import_result2.success, "再次导入应成功"
        assert len(import_result2.conflicts) > 0, "再次导入应有冲突"
        
        # 使用RENAME_NEW策略
        import_result3 = manager.import_to_project(
            result,
            ConflictStrategy.RENAME_NEW
        )
        
        assert import_result3.success, "RENAME_NEW导入应成功"
    
    print("  [PASS] import_to_project导入测试通过")


def test_conflict_strategies():
    """测试6: 冲突处理策略"""
    print("测试6: 冲突处理策略...")
    
    char1 = CharacterResult(name="主角", role="主角", personality="勇敢")
    char2 = CharacterResult(name="主角", role="主角", personality="善良")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = ResultStorageManager(Path(tmpdir))
        
        # 导入第一个人物
        result1 = QuickCreationResult(
            keywords="测试",
            characters=[char1],
            success=True
        )
        manager.import_to_project(result1, ConflictStrategy.KEEP_ORIGINAL)
        
        # KEEP_ORIGINAL策略：保留原有人物
        result2 = QuickCreationResult(
            keywords="测试",
            characters=[char2],
            success=True
        )
        import_result = manager.import_to_project(
            result2, 
            ConflictStrategy.KEEP_ORIGINAL
        )
        
        # 检查原有文件未被修改
        char_file = Path(tmpdir) / "人物设定" / "主角.json"
        with open(char_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data["personality"] == "勇敢", "KEEP_ORIGINAL应保留原有设定"
        
        # OVERWRITE策略：覆盖原有人物
        manager.import_to_project(result2, ConflictStrategy.OVERWRITE)
        
        with open(char_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data["personality"] == "善良", "OVERWRITE应覆盖原有设定"
    
    print("  [PASS] 冲突处理策略测试通过")


def test_convenience_functions():
    """测试7: 便捷函数"""
    print("测试7: 便捷函数...")
    
    result = QuickCreationResult(
        keywords="便捷测试",
        worldview=WorldviewResult(setting_name="便捷世界"),
        success=True
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 测试save_quick_creation_result
        project_path = save_quick_creation_result(
            result,
            Path(tmpdir),
            "便捷测试项目"
        )
        
        assert project_path.exists(), "便捷保存应创建项目目录"
        
        # 测试import_quick_creation_result
        import_result = import_quick_creation_result(
            result,
            project_path,
            strategy="keep_original"
        )
        
        assert import_result.success, "便捷导入应成功"
    
    print("  [PASS] 便捷函数测试通过")


def test_project_summary():
    """测试8: 项目摘要功能"""
    print("测试8: 项目摘要功能...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = ResultStorageManager(Path(tmpdir))
        
        # 空项目摘要
        summary = manager.get_project_summary()
        assert summary["project_exists"] == True
        assert summary["has_worldview"] == False
        assert summary["character_count"] == 0
        
        # 导入数据后摘要
        result = QuickCreationResult(
            keywords="摘要测试",
            worldview=WorldviewResult(setting_name="摘要世界"),
            characters=[CharacterResult(name="角色1")],
            success=True
        )
        manager.import_to_project(result, ConflictStrategy.OVERWRITE)
        
        summary = manager.get_project_summary()
        assert summary["has_worldview"] == True
        assert summary["character_count"] == 1
    
    print("  [PASS] 项目摘要测试通过")


def test_sanitize_filename():
    """测试9: 文件名清理"""
    print("测试9: 文件名清理...")
    
    manager = ResultStorageManager()
    
    # 测试非法字符
    assert manager._sanitize_filename("test<file>") == "test_file_"
    assert manager._sanitize_filename("文件:name") == "文件_name"
    assert manager._sanitize_filename("a/b\\c|d?e*f") == "a_b_c_d_e_f"
    
    # 测试长度限制
    long_name = "a" * 100
    assert len(manager._sanitize_filename(long_name)) == 50
    
    print("  [PASS] 文件名清理测试通过")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("快捷创作结果存储模块单元测试")
    print("=" * 60)
    print()
    
    tests = [
        test_storage_manager_init,
        test_json_schemas,
        test_save_result,
        test_save_result_markdown,
        test_import_to_project,
        test_conflict_strategies,
        test_convenience_functions,
        test_project_summary,
        test_sanitize_filename
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] 测试失败: {e}")
            failed += 1
        except Exception as e:
            print(f"  [FAIL] 测试异常: {e}")
            failed += 1
    
    print()
    print("=" * 60)
    print(f"测试结果: {passed} 通过 / {failed} 失败")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
