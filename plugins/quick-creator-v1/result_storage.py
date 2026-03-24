"""
快捷创作结果存储模块 V1.0
Quick Creation Result Storage Module

功能：
1. 定义生成结果的JSON Schema
2. 实现"保存结果"功能，创建新项目文件
3. 实现"导入当前项目"功能，合并到当前项目的设定中
4. 冲突处理：支持保留用户原有设定

作者：高级开发工程师
日期：2026-03-24
"""

import json
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum

# Pydantic模型
from pydantic import BaseModel, Field, field_validator

# JSON Schema验证（可选）
try:
    import jsonschema
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    logger.warning("jsonschema库未安装，Schema验证功能不可用")

# 项目内部模型
from core.models import (
    WorldviewResult,
    OutlineResult,
    CharacterResult,
    PlotResult,
    QuickCreationResult
)


logger = logging.getLogger(__name__)


# ============================================================================
# JSON Schema定义
# ============================================================================

SCHEMA_VERSION = "1.0.0"

WORLDVIEW_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "WorldviewSetting",
    "description": "世界观设定JSON Schema",
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "default": "1.0.0"},
        "setting_name": {"type": "string", "description": "世界观名称"},
        "era": {"type": "string", "description": "时代背景"},
        "world_structure": {"type": "string", "description": "世界结构"},
        "power_system": {"type": "string", "description": "力量体系"},
        "geography": {"type": "string", "description": "地理环境"},
        "social_structure": {"type": "string", "description": "社会结构"},
        "major_forces": {
            "type": "array",
            "items": {"type": "string"},
            "description": "主要势力列表"
        },
        "rules_and_laws": {
            "type": "array",
            "items": {"type": "string"},
            "description": "规则与法则列表"
        },
        "special_elements": {
            "type": "array",
            "items": {"type": "string"},
            "description": "特殊元素列表"
        },
        "background_story": {"type": "string", "description": "背景故事"},
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"}
    },
    "required": ["setting_name"]
}

OUTLINE_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "OutlineSetting",
    "description": "大纲设定JSON Schema",
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "default": "1.0.0"},
        "title": {"type": "string", "description": "作品标题"},
        "theme": {"type": "string", "description": "主题"},
        "synopsis": {"type": "string", "description": "故事梗概"},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chapter_num": {"type": "integer"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "key_events": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                }
            },
            "description": "章节列表"
        },
        "main_plot": {"type": "string", "description": "主线剧情"},
        "sub_plots": {
            "type": "array",
            "items": {"type": "string"},
            "description": "支线剧情列表"
        },
        "climax_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "高潮节点列表"
        },
        "ending_direction": {"type": "string", "description": "结局走向"},
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"}
    },
    "required": ["title"]
}

CHARACTER_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "CharacterSetting",
    "description": "人物设定JSON Schema",
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "default": "1.0.0"},
        "name": {"type": "string", "description": "人物名称"},
        "role": {"type": "string", "description": "角色定位"},
        "age": {"type": "string", "description": "年龄"},
        "gender": {"type": "string", "description": "性别"},
        "appearance": {"type": "string", "description": "外貌描述"},
        "personality": {"type": "string", "description": "性格特点"},
        "background": {"type": "string", "description": "背景故事"},
        "abilities": {
            "type": "array",
            "items": {"type": "string"},
            "description": "能力/技能列表"
        },
        "goals": {
            "type": "array",
            "items": {"type": "string"},
            "description": "目标/动机列表"
        },
        "weaknesses": {
            "type": "array",
            "items": {"type": "string"},
            "description": "弱点/缺陷列表"
        },
        "relationships": {
            "type": "object",
            "additionalProperties": {"type": "string"},
            "description": "人物关系字典"
        },
        "speech_pattern": {"type": "string", "description": "说话风格"},
        "character_arc": {"type": "string", "description": "人物弧线"},
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"}
    },
    "required": ["name"]
}

PLOT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "PlotSetting",
    "description": "情节设定JSON Schema",
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "default": "1.0.0"},
        "plot_name": {"type": "string", "description": "情节名称"},
        "plot_type": {"type": "string", "description": "情节类型"},
        "participants": {
            "type": "array",
            "items": {"type": "string"},
            "description": "参与角色列表"
        },
        "setting": {"type": "string", "description": "场景设定"},
        "beginning": {"type": "string", "description": "开端"},
        "development": {"type": "string", "description": "发展"},
        "climax": {"type": "string", "description": "高潮"},
        "resolution": {"type": "string", "description": "结局"},
        "conflicts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "冲突点列表"
        },
        "turning_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "转折点列表"
        },
        "foreshadowing": {
            "type": "array",
            "items": {"type": "string"},
            "description": "伏笔列表"
        },
        "involved_chapters": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "涉及章节列表"
        },
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"}
    },
    "required": ["plot_name"]
}


# ============================================================================
# 冲突处理策略
# ============================================================================

class ConflictStrategy(str, Enum):
    """冲突处理策略枚举"""
    KEEP_ORIGINAL = "keep_original"      # 保留原有设定
    OVERWRITE = "overwrite"              # 覆盖原有设定
    MERGE = "merge"                      # 合并设定
    RENAME_NEW = "rename_new"            # 重命名新设定


@dataclass
class ConflictInfo:
    """冲突信息"""
    field_name: str                      # 冲突字段名
    original_value: Any                  # 原有值
    new_value: Any                       # 新值
    suggested_strategy: ConflictStrategy # 建议策略


@dataclass
class ImportResult:
    """导入结果"""
    success: bool
    imported_items: List[str]
    conflicts: List[ConflictInfo]
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 结果存储管理器
# ============================================================================

class ResultStorageManager:
    """
    快捷创作结果存储管理器
    
    职责：
    1. 保存生成结果到项目文件
    2. 导入结果到当前项目（合并处理）
    3. 冲突检测与处理
    4. 文件格式转换（JSON/Markdown）
    """
    
    # 项目目录结构
    PROJECT_DIRS = {
        "worldview": "世界观",
        "outline": "大纲",
        "characters": "人物设定",
        "plots": "情节设定"
    }
    
    def __init__(self, project_path: Optional[Path] = None):
        """
        初始化存储管理器
        
        参数:
            project_path: 项目根目录路径
        """
        self.project_path = project_path
        self._ensure_project_structure()
    
    def set_project_path(self, path: Union[str, Path]) -> None:
        """设置项目路径"""
        self.project_path = Path(path)
        self._ensure_project_structure()
    
    def _ensure_project_structure(self) -> None:
        """确保项目目录结构存在"""
        if not self.project_path:
            return
        
        for dir_name in self.PROJECT_DIRS.values():
            dir_path = self.project_path / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)
    
    # ==================== JSON Schema验证 ====================
    
    def validate_worldview(self, data: Dict[str, Any]) -> bool:
        """
        验证世界观数据是否符合Schema
        
        参数:
            data: 世界观数据字典
            
        返回:
            是否验证通过
        """
        if not JSONSCHEMA_AVAILABLE:
            logger.debug("jsonschema不可用，跳过验证")
            return True
        
        try:
            jsonschema.validate(instance=data, schema=WORLDVIEW_SCHEMA)
            return True
        except jsonschema.ValidationError as e:
            logger.warning(f"世界观数据验证失败: {e.message}")
            return False
        except Exception as e:
            logger.warning(f"验证过程出错: {e}")
            return False
    
    def validate_outline(self, data: Dict[str, Any]) -> bool:
        """
        验证大纲数据是否符合Schema
        
        参数:
            data: 大纲数据字典
            
        返回:
            是否验证通过
        """
        if not JSONSCHEMA_AVAILABLE:
            return True
        
        try:
            jsonschema.validate(instance=data, schema=OUTLINE_SCHEMA)
            return True
        except jsonschema.ValidationError as e:
            logger.warning(f"大纲数据验证失败: {e.message}")
            return False
        except Exception as e:
            logger.warning(f"验证过程出错: {e}")
            return False
    
    def validate_character(self, data: Dict[str, Any]) -> bool:
        """
        验证人物数据是否符合Schema
        
        参数:
            data: 人物数据字典
            
        返回:
            是否验证通过
        """
        if not JSONSCHEMA_AVAILABLE:
            return True
        
        try:
            jsonschema.validate(instance=data, schema=CHARACTER_SCHEMA)
            return True
        except jsonschema.ValidationError as e:
            logger.warning(f"人物数据验证失败: {e.message}")
            return False
        except Exception as e:
            logger.warning(f"验证过程出错: {e}")
            return False
    
    def validate_plot(self, data: Dict[str, Any]) -> bool:
        """
        验证情节数据是否符合Schema
        
        参数:
            data: 情节数据字典
            
        返回:
            是否验证通过
        """
        if not JSONSCHEMA_AVAILABLE:
            return True
        
        try:
            jsonschema.validate(instance=data, schema=PLOT_SCHEMA)
            return True
        except jsonschema.ValidationError as e:
            logger.warning(f"情节数据验证失败: {e.message}")
            return False
        except Exception as e:
            logger.warning(f"验证过程出错: {e}")
            return False
    
    # ==================== 保存结果 ====================
    
    class StorageError(Exception):
        """存储操作异常"""
        pass
    
    def save_result(
        self,
        result: QuickCreationResult,
        project_name: str = "新建项目",
        output_path: Optional[Path] = None,
        format: str = "json"
    ) -> Path:
        """
        保存生成结果到新项目文件
        
        参数:
            result: 快捷创作结果
            project_name: 项目名称
            output_path: 输出路径（可选，默认使用project_path）
            format: 保存格式（json/markdown）
            
        返回:
            项目目录路径
            
        异常:
            StorageError: 文件写入失败
        """
        try:
            # 确定输出路径
            if output_path:
                save_path = Path(output_path) / project_name
            elif self.project_path:
                save_path = self.project_path
            else:
                save_path = Path.cwd() / project_name
            
            # 创建项目目录结构
            save_path.mkdir(parents=True, exist_ok=True)
            self._ensure_dirs_exist(save_path)
            
            timestamp = datetime.now().isoformat()
            
            # 保存世界观
            if result.worldview:
                self._save_worldview(result.worldview, save_path, timestamp, format)
            
            # 保存大纲
            if result.outline:
                self._save_outline(result.outline, save_path, timestamp, format)
            
            # 保存人物
            if result.characters:
                self._save_characters(result.characters, save_path, timestamp, format)
            
            # 保存情节
            if result.plot:
                self._save_plot(result.plot, save_path, timestamp, format)
            
            # 保存项目元数据
            self._save_project_metadata(save_path, project_name, result, timestamp)
            
            logger.info(f"结果已保存到: {save_path}")
            return save_path
            
        except PermissionError as e:
            logger.error(f"文件权限错误: {e}")
            raise self.StorageError(f"无法写入文件，请检查权限: {save_path if 'save_path' in locals() else '未知路径'}")
        except OSError as e:
            logger.error(f"文件系统错误: {e}")
            raise self.StorageError(f"文件系统错误: {e}")
    
    def _ensure_dirs_exist(self, base_path: Path) -> None:
        """确保所有必要目录存在"""
        for dir_name in self.PROJECT_DIRS.values():
            (base_path / dir_name).mkdir(parents=True, exist_ok=True)
    
    def _save_worldview(
        self,
        worldview: WorldviewResult,
        save_path: Path,
        timestamp: str,
        format: str
    ) -> None:
        """保存世界观设定"""
        try:
            worldview_dir = save_path / self.PROJECT_DIRS["worldview"]
            worldview_dir.mkdir(parents=True, exist_ok=True)
            
            if format == "json":
                file_path = worldview_dir / "世界观设定.json"
                data = worldview.model_dump()
                data["schema_version"] = SCHEMA_VERSION
                data["created_at"] = timestamp
                data["updated_at"] = timestamp
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                file_path = worldview_dir / "世界观设定.md"
                content = worldview.get_full_text()
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            logger.debug(f"世界观已保存: {file_path}")
        except PermissionError as e:
            logger.error(f"文件权限错误: {e}")
            raise
        except OSError as e:
            logger.error(f"文件系统错误: {e}")
            raise
    
    def _save_outline(
        self,
        outline: OutlineResult,
        save_path: Path,
        timestamp: str,
        format: str
    ) -> None:
        """保存大纲设定"""
        try:
            outline_dir = save_path / self.PROJECT_DIRS["outline"]
            outline_dir.mkdir(parents=True, exist_ok=True)
            
            if format == "json":
                file_path = outline_dir / "大纲设定.json"
                data = outline.model_dump()
                data["schema_version"] = SCHEMA_VERSION
                data["created_at"] = timestamp
                data["updated_at"] = timestamp
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                file_path = outline_dir / "大纲设定.md"
                content = outline.get_full_text()
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            logger.debug(f"大纲已保存: {file_path}")
        except PermissionError as e:
            logger.error(f"文件权限错误: {e}")
            raise
        except OSError as e:
            logger.error(f"文件系统错误: {e}")
            raise
    
    def _save_characters(
        self,
        characters: List[CharacterResult],
        save_path: Path,
        timestamp: str,
        format: str
    ) -> None:
        """保存人物设定"""
        try:
            char_dir = save_path / self.PROJECT_DIRS["characters"]
            char_dir.mkdir(parents=True, exist_ok=True)
            
            for char in characters:
                safe_name = self._sanitize_filename(char.name or "未命名角色")
                
                if format == "json":
                    file_path = char_dir / f"{safe_name}.json"
                    data = char.model_dump()
                    data["schema_version"] = SCHEMA_VERSION
                    data["created_at"] = timestamp
                    data["updated_at"] = timestamp
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                else:
                    file_path = char_dir / f"{safe_name}.md"
                    content = char.get_full_text()
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
            
            logger.debug(f"已保存 {len(characters)} 个人物设定")
        except PermissionError as e:
            logger.error(f"文件权限错误: {e}")
            raise
        except OSError as e:
            logger.error(f"文件系统错误: {e}")
            raise
    
    def _save_plot(
        self,
        plot: PlotResult,
        save_path: Path,
        timestamp: str,
        format: str
    ) -> None:
        """保存情节设定"""
        try:
            plot_dir = save_path / self.PROJECT_DIRS["plots"]
            plot_dir.mkdir(parents=True, exist_ok=True)
            
            safe_name = self._sanitize_filename(plot.plot_name or "未命名情节")
            
            if format == "json":
                file_path = plot_dir / f"{safe_name}.json"
                data = plot.model_dump()
                data["schema_version"] = SCHEMA_VERSION
                data["created_at"] = timestamp
                data["updated_at"] = timestamp
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                file_path = plot_dir / f"{safe_name}.md"
                content = plot.get_full_text()
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            logger.debug(f"情节已保存: {file_path}")
        except PermissionError as e:
            logger.error(f"文件权限错误: {e}")
            raise
        except OSError as e:
            logger.error(f"文件系统错误: {e}")
            raise
    
    def _save_project_metadata(
        self,
        save_path: Path,
        project_name: str,
        result: QuickCreationResult,
        timestamp: str
    ) -> None:
        """保存项目元数据"""
        metadata = {
            "project_name": project_name,
            "created_at": timestamp,
            "updated_at": timestamp,
            "generator": "QuickCreationPlugin",
            "version": SCHEMA_VERSION,
            "keywords": result.keywords,
            "generated_items": list(result.get_generated_items().keys()),
            "success": result.success,
            "error": result.error
        }
        
        file_path = save_path / "project.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"项目元数据已保存: {file_path}")
    
    # ==================== 导入到当前项目 ====================
    
    def import_to_project(
        self,
        result: QuickCreationResult,
        conflict_strategy: ConflictStrategy = ConflictStrategy.KEEP_ORIGINAL,
        merge_mode: str = "append"
    ) -> ImportResult:
        """
        将生成结果导入到当前项目
        
        参数:
            result: 快捷创作结果
            conflict_strategy: 冲突处理策略
            merge_mode: 合并模式（append追加/replace替换）
            
        返回:
            导入结果
        """
        if not self.project_path:
            return ImportResult(
                success=False,
                imported_items=[],
                conflicts=[],
                error="未设置项目路径"
            )
        
        imported_items = []
        conflicts = []
        
        try:
            # 导入世界观
            if result.worldview:
                item_conflicts = self._import_worldview(
                    result.worldview, 
                    conflict_strategy
                )
                conflicts.extend(item_conflicts)
                imported_items.append("worldview")
            
            # 导入大纲
            if result.outline:
                item_conflicts = self._import_outline(
                    result.outline,
                    conflict_strategy
                )
                conflicts.extend(item_conflicts)
                imported_items.append("outline")
            
            # 导入人物
            if result.characters:
                item_conflicts = self._import_characters(
                    result.characters,
                    conflict_strategy,
                    merge_mode
                )
                conflicts.extend(item_conflicts)
                imported_items.append(f"characters({len(result.characters)})")
            
            # 导入情节
            if result.plot:
                item_conflicts = self._import_plot(
                    result.plot,
                    conflict_strategy
                )
                conflicts.extend(item_conflicts)
                imported_items.append("plot")
            
            logger.info(f"导入完成: {imported_items}, 冲突数: {len(conflicts)}")
            
            return ImportResult(
                success=True,
                imported_items=imported_items,
                conflicts=conflicts,
                details={
                    "project_path": str(self.project_path),
                    "strategy": conflict_strategy.value,
                    "merge_mode": merge_mode
                }
            )
            
        except Exception as e:
            logger.error(f"导入失败: {e}")
            return ImportResult(
                success=False,
                imported_items=imported_items,
                conflicts=conflicts,
                error=str(e)
            )
    
    def _import_worldview(
        self,
        worldview: WorldviewResult,
        strategy: ConflictStrategy
    ) -> List[ConflictInfo]:
        """导入世界观设定"""
        conflicts = []
        worldview_dir = self.project_path / self.PROJECT_DIRS["worldview"]
        worldview_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = worldview_dir / "世界观设定.json"
        
        # 检测冲突
        if file_path.exists():
            conflicts.append(ConflictInfo(
                field_name="worldview",
                original_value=str(file_path),
                new_value=worldview.setting_name,
                suggested_strategy=ConflictStrategy.KEEP_ORIGINAL
            ))
            
            if strategy == ConflictStrategy.KEEP_ORIGINAL:
                logger.info("保留原有世界观设定")
                return conflicts
            elif strategy == ConflictStrategy.RENAME_NEW:
                # 重命名新文件
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_path = worldview_dir / f"世界观设定_{timestamp}.json"
        
        # 保存文件
        timestamp = datetime.now().isoformat()
        data = worldview.model_dump()
        data["schema_version"] = SCHEMA_VERSION
        data["created_at"] = timestamp
        data["updated_at"] = timestamp
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return conflicts
    
    def _import_outline(
        self,
        outline: OutlineResult,
        strategy: ConflictStrategy
    ) -> List[ConflictInfo]:
        """导入大纲设定"""
        conflicts = []
        outline_dir = self.project_path / self.PROJECT_DIRS["outline"]
        outline_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = outline_dir / "大纲设定.json"
        
        # 检测冲突
        if file_path.exists():
            conflicts.append(ConflictInfo(
                field_name="outline",
                original_value=str(file_path),
                new_value=outline.title,
                suggested_strategy=ConflictStrategy.KEEP_ORIGINAL
            ))
            
            if strategy == ConflictStrategy.KEEP_ORIGINAL:
                logger.info("保留原有大纲设定")
                return conflicts
            elif strategy == ConflictStrategy.RENAME_NEW:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_path = outline_dir / f"大纲设定_{timestamp}.json"
        
        # 保存文件
        timestamp = datetime.now().isoformat()
        data = outline.model_dump()
        data["schema_version"] = SCHEMA_VERSION
        data["created_at"] = timestamp
        data["updated_at"] = timestamp
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return conflicts
    
    def _import_characters(
        self,
        characters: List[CharacterResult],
        strategy: ConflictStrategy,
        merge_mode: str
    ) -> List[ConflictInfo]:
        """导入人物设定"""
        conflicts = []
        char_dir = self.project_path / self.PROJECT_DIRS["characters"]
        char_dir.mkdir(parents=True, exist_ok=True)
        
        for char in characters:
            safe_name = self._sanitize_filename(char.name or "未命名角色")
            file_path = char_dir / f"{safe_name}.json"
            
            # 检测冲突
            if file_path.exists():
                conflicts.append(ConflictInfo(
                    field_name=f"character:{char.name}",
                    original_value=str(file_path),
                    new_value=char.name,
                    suggested_strategy=strategy
                ))
                
                if strategy == ConflictStrategy.KEEP_ORIGINAL:
                    logger.info(f"保留原有人物设定: {char.name}")
                    continue
                elif strategy == ConflictStrategy.RENAME_NEW:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    file_path = char_dir / f"{safe_name}_{timestamp}.json"
            
            # 保存文件
            timestamp = datetime.now().isoformat()
            data = char.model_dump()
            data["schema_version"] = SCHEMA_VERSION
            data["created_at"] = timestamp
            data["updated_at"] = timestamp
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        return conflicts
    
    def _import_plot(
        self,
        plot: PlotResult,
        strategy: ConflictStrategy
    ) -> List[ConflictInfo]:
        """导入情节设定"""
        conflicts = []
        plot_dir = self.project_path / self.PROJECT_DIRS["plots"]
        plot_dir.mkdir(parents=True, exist_ok=True)
        
        safe_name = self._sanitize_filename(plot.plot_name or "未命名情节")
        file_path = plot_dir / f"{safe_name}.json"
        
        # 检测冲突
        if file_path.exists():
            conflicts.append(ConflictInfo(
                field_name=f"plot:{plot.plot_name}",
                original_value=str(file_path),
                new_value=plot.plot_name,
                suggested_strategy=strategy
            ))
            
            if strategy == ConflictStrategy.KEEP_ORIGINAL:
                logger.info(f"保留原有情节设定: {plot.plot_name}")
                return conflicts
            elif strategy == ConflictStrategy.RENAME_NEW:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_path = plot_dir / f"{safe_name}_{timestamp}.json"
        
        # 保存文件
        timestamp = datetime.now().isoformat()
        data = plot.model_dump()
        data["schema_version"] = SCHEMA_VERSION
        data["created_at"] = timestamp
        data["updated_at"] = timestamp
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return conflicts
    
    # ==================== 辅助方法 ====================
    
    def _sanitize_filename(self, name: str) -> str:
        """清理文件名，移除非法字符"""
        illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        safe_name = name
        for char in illegal_chars:
            safe_name = safe_name.replace(char, '_')
        return safe_name.strip()[:50]  # 限制长度
    
    def load_existing_worldview(self) -> Optional[Dict[str, Any]]:
        """加载现有世界观设定"""
        if not self.project_path:
            return None
        
        file_path = self.project_path / self.PROJECT_DIRS["worldview"] / "世界观设定.json"
        
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        return None
    
    def load_existing_outline(self) -> Optional[Dict[str, Any]]:
        """加载现有大纲设定"""
        if not self.project_path:
            return None
        
        file_path = self.project_path / self.PROJECT_DIRS["outline"] / "大纲设定.json"
        
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        return None
    
    def load_existing_characters(self) -> List[Dict[str, Any]]:
        """加载现有人物设定"""
        if not self.project_path:
            return []
        
        char_dir = self.project_path / self.PROJECT_DIRS["characters"]
        characters = []
        
        if char_dir.exists():
            for file_path in char_dir.glob("*.json"):
                with open(file_path, 'r', encoding='utf-8') as f:
                    characters.append(json.load(f))
        
        return characters
    
    def get_project_summary(self) -> Dict[str, Any]:
        """获取项目摘要"""
        if not self.project_path:
            return {"error": "未设置项目路径"}
        
        return {
            "project_path": str(self.project_path),
            "has_worldview": bool(self.load_existing_worldview()),
            "has_outline": bool(self.load_existing_outline()),
            "character_count": len(self.load_existing_characters()),
            "project_exists": self.project_path.exists()
        }


# ============================================================================
# 便捷函数
# ============================================================================

def save_quick_creation_result(
    result: QuickCreationResult,
    output_path: Union[str, Path],
    project_name: str = "新建项目",
    format: str = "json"
) -> Path:
    """
    便捷函数：保存快捷创作结果
    
    参数:
        result: 快捷创作结果
        output_path: 输出目录
        project_name: 项目名称
        format: 保存格式
        
    返回:
        项目目录路径
    """
    manager = ResultStorageManager()
    return manager.save_result(result, project_name, Path(output_path), format)


def import_quick_creation_result(
    result: QuickCreationResult,
    project_path: Union[str, Path],
    strategy: str = "keep_original"
) -> ImportResult:
    """
    便捷函数：导入快捷创作结果到当前项目
    
    参数:
        result: 快捷创作结果
        project_path: 项目路径
        strategy: 冲突处理策略
        
    返回:
        导入结果
    """
    manager = ResultStorageManager(Path(project_path))
    return manager.import_to_project(
        result,
        ConflictStrategy(strategy)
    )
