"""
项目管理器服务

负责项目数据的保存、加载、同步等核心逻辑。
遵循架构设计：微内核+插件化，服务层提供共享能力。

功能：
- 项目文件保存/加载
- 模块数据同步
- 项目元数据管理
- 与EventBus集成实现数据变更通知
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

from core.event_bus import EventBus
from core.models import Event
import logging

# 尝试导入结构化日志器
try:
    from infrastructure.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


class ProjectDataEvent(Event):
    """项目数据变更事件"""
    
    data_type: str = ""
    operation: str = "update"
    
    def __init__(self, data_type: str, data: Any, operation: str = "update"):
        """
        Args:
            data_type: 数据类型（outline/characters/worldview等）
            data: 数据内容
            operation: 操作类型（update/delete）
        """
        super().__init__(
            type=f"project.data.{operation}",
            data={
                "type": data_type,
                "operation": operation,
                "timestamp": datetime.now().isoformat(),
                "content": data
            }
        )
        # 存储额外字段用于回调
        object.__setattr__(self, 'data_type', data_type)
        object.__setattr__(self, 'operation', operation)


class ProjectSavedEvent(Event):
    """项目保存完成事件"""
    
    def __init__(self, project_name: str, project_path: str):
        super().__init__(
            type="project.saved",
            data={
                "name": project_name,
                "path": project_path,
                "timestamp": datetime.now().isoformat()
            }
        )
        # 存储额外字段用于回调
        object.__setattr__(self, 'project_name', project_name)
        object.__setattr__(self, 'project_path', project_path)


class ProjectLoadedEvent(Event):
    """项目加载完成事件"""
    
    def __init__(self, project_name: str, project_path: str):
        super().__init__(
            type="project.loaded",
            data={
                "name": project_name,
                "path": project_path,
                "timestamp": datetime.now().isoformat()
            }
        )
        # 存储额外字段用于回调
        object.__setattr__(self, 'project_name', project_name)
        object.__setattr__(self, 'project_path', project_path)


class ProjectManager:
    """
    项目管理器
    
    职责：
    1. 项目文件I/O操作
    2. 模块数据同步
    3. 数据变更事件发布
    4. 项目元数据管理
    """
    
    def __init__(self, event_bus: Optional[EventBus] = None):
        """
        初始化项目管理器
        
        Args:
            event_bus: 事件总线实例（可选）
        """
        self._event_bus = event_bus
        self._current_project: Optional[Dict[str, Any]] = None
        self._project_file: Optional[str] = None
        self._data_cache: Dict[str, Any] = {}
        
        logger.info("[ProjectManager] 初始化完成")
    
    def set_event_bus(self, event_bus: EventBus):
        """设置事件总线"""
        self._event_bus = event_bus
        logger.info("[ProjectManager] 事件总线已设置")
    
    def create_project(self, project_name: str, project_path: str) -> Dict[str, Any]:
        """
        创建新项目
        
        Args:
            project_name: 项目名称
            project_path: 项目文件路径
            
        Returns:
            新建的项目字典
        """
        project = {
            "name": project_name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "modified_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            # 各模块数据
            "outline": "",
            "characters": [],
            "worldview": [],
            "style": {},
            "reverse_chapters": [],
            "reverse_feedback": {},
            "completed_chapters": [],
            "generated_content": ""
        }
        
        self._current_project = project
        self._project_file = project_path
        
        # 保存到文件
        self._save_to_file(project, project_path)
        
        logger.info(f"[ProjectManager] 创建项目: {project_name}")
        return project
    
    def load_project(self, project_path: str) -> Optional[Dict[str, Any]]:
        """
        加载项目文件
        
        Args:
            project_path: 项目文件路径
            
        Returns:
            项目字典，加载失败返回None
        """
        try:
            if not os.path.exists(project_path):
                logger.error(f"[ProjectManager] 项目文件不存在: {project_path}")
                return None
            
            with open(project_path, 'r', encoding='utf-8') as f:
                project = json.load(f)
            
            self._current_project = project
            self._project_file = project_path
            self._data_cache = project.copy()
            
            # 发布项目加载事件
            if self._event_bus:
                event = ProjectLoadedEvent(
                    project.get('name', '未命名项目'),
                    project_path
                )
                self._event_bus.publish(event)
            
            logger.info(f"[ProjectManager] 加载项目: {project.get('name', '未命名项目')}")
            return project
            
        except Exception as e:
            logger.error(f"[ProjectManager] 加载项目失败: {e}")
            return None
    
    def save_project(self, project: Optional[Dict[str, Any]] = None) -> bool:
        """
        保存项目
        
        Args:
            project: 项目数据（可选，默认使用当前项目）
            
        Returns:
            是否保存成功
        """
        try:
            if project is None:
                project = self._current_project
            
            if not project or not self._project_file:
                logger.warning("[ProjectManager] 没有可保存的项目")
                return False
            
            # 更新修改时间
            project['modified_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 保存到文件
            self._save_to_file(project, self._project_file)
            
            # 更新缓存
            self._data_cache = project.copy()
            
            # 发布项目保存事件
            if self._event_bus:
                event = ProjectSavedEvent(
                    project.get('name', '未命名项目'),
                    self._project_file
                )
                self._event_bus.publish(event)
            
            logger.info(f"[ProjectManager] 保存项目: {project.get('name', '未命名项目')}")
            return True
            
        except Exception as e:
            logger.error(f"[ProjectManager] 保存项目失败: {e}")
            return False
    
    def _save_to_file(self, project: Dict[str, Any], file_path: str) -> None:
        """
        保存项目到文件（私有方法）
        
        Args:
            project: 项目数据
            file_path: 文件路径
        """
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(project, f, ensure_ascii=False, indent=2)
    
    def sync_module_data(self, data_type: str, data: Any) -> None:
        """
        同步模块数据到项目
        
        Args:
            data_type: 数据类型（outline/characters/worldview等）
            data: 数据内容
        """
        if not self._current_project:
            logger.warning(f"[ProjectManager] 没有当前项目，无法同步{data_type}")
            return
        
        # 更新项目数据
        self._current_project[data_type] = data
        
        # 发布数据变更事件
        if self._event_bus:
            event = ProjectDataEvent(data_type, data, "update")
            self._event_bus.publish(event)
        
        logger.info(f"[ProjectManager] 同步{data_type}数据")
    
    def get_module_data(self, data_type: str) -> Any:
        """
        获取模块数据
        
        Args:
            data_type: 数据类型（outline/characters/worldview等）
            
        Returns:
            数据内容，不存在返回None
        """
        if not self._current_project:
            return None
        
        return self._current_project.get(data_type)
    
    def get_current_project(self) -> Optional[Dict[str, Any]]:
        """获取当前项目"""
        return self._current_project
    
    def get_project_data(self) -> Optional[Dict[str, Any]]:
        """获取项目数据（别名方法，便于理解）"""
        return self._current_project
    
    def get_project_file(self) -> Optional[str]:
        """获取项目文件路径"""
        return self._project_file
    
    def get_project_name(self) -> str:
        """获取项目名称"""
        if self._current_project:
            return self._current_project.get('name', '未命名项目')
        return '未命名项目'
    
    def is_project_open(self) -> bool:
        """是否有打开的项目"""
        return self._current_project is not None

    # ========== 跨板块数据流兼容接口（V2.3新增，遵循"新增不改旧"） ==========
    # 背景：GUI 的快捷创作导入、续写上下文/选章/保存、长篇检测选章共调用
    # 12 个本类不存在的方法（旧版 ProjectManager 迁移时接口丢失）——
    # 快捷→项目、项目→续写、续写→项目、项目→长篇检测四条跨板块数据流
    # 全部 AttributeError 断裂。此处按现行数据模型补齐。
    #
    # 章节条目规范形状（completed_chapters 列表元素）：
    #   {"title": str, "content": str, "word_count": int,
    #    "source": "generation"|"continuation"|"import", "created_at": str}

    @staticmethod
    def _as_text(value: Any) -> str:
        """把 dict/list 形状的设定归一化为文本（续写等消费方需要 str）"""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for key in ("content", "outline_content", "text", "summary"):
                inner = value.get(key)
                if isinstance(inner, str) and inner.strip():
                    return inner
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("title") or ""
                    desc = (item.get("description") or item.get("content")
                            or item.get("summary") or "")
                    parts.append(f"{name}: {desc}" if name else str(desc))
                else:
                    parts.append(str(item))
            return "\n".join(p for p in parts if p)
        return str(value)

    # ---- 设定写入（快捷创作导入） ----

    def set_worldview(self, worldview: Any) -> None:
        """设置世界观设定（快捷创作导入路径）"""
        self.sync_module_data('worldview', worldview)

    def set_outline(self, outline: Any) -> None:
        """设置大纲（快捷创作导入路径）"""
        self.sync_module_data('outline', outline)

    def set_characters(self, characters: Any) -> None:
        """设置人物设定（快捷创作导入路径）"""
        self.sync_module_data('characters', characters)

    def set_plot(self, plot: Any) -> None:
        """设置关键情节（快捷创作导入路径）"""
        self.sync_module_data('plot', plot)

    # ---- 设定读取（续写上下文构建，返回类型对齐 ContinuationRequest） ----

    def get_outline(self) -> str:
        """获取大纲文本（dict 形状自动归一化）"""
        return self._as_text(self.get_module_data('outline'))

    def get_worldview(self) -> str:
        """获取世界观文本（list 形状自动归一化）"""
        return self._as_text(self.get_module_data('worldview'))

    def get_characters(self) -> List[Dict[str, Any]]:
        """获取人物设定列表（归一化为 List[Dict]）"""
        chars = self.get_module_data('characters')
        if isinstance(chars, list):
            return [c for c in chars if isinstance(c, dict)]
        if isinstance(chars, dict):
            result = []
            for name, profile in chars.items():
                if isinstance(profile, dict):
                    entry = dict(profile)
                    entry.setdefault('name', name)
                    result.append(entry)
                else:
                    result.append({'name': str(name), 'description': str(profile)})
            return result
        if isinstance(chars, str) and chars.strip():
            return [{'name': '设定文本', 'description': chars}]
        return []

    # ---- 章节访问（续写选章/长篇检测选章/前文参考） ----

    def _chapter_list(self) -> List[Dict[str, Any]]:
        """内部：获取规范化章节列表引用"""
        if not self._current_project:
            return []
        chapters = self._current_project.setdefault('completed_chapters', [])
        if not isinstance(chapters, list):
            chapters = []
            self._current_project['completed_chapters'] = chapters
        return chapters

    def list_chapters(self) -> List[Dict[str, Any]]:
        """列出项目章节（title/word_count 供选择对话框展示）"""
        result = []
        for ch in self._chapter_list():
            if isinstance(ch, dict) and ch.get('content'):
                result.append({
                    'title': ch.get('title', '未命名章节'),
                    'word_count': ch.get('word_count', len(ch.get('content', ''))),
                })
        return result

    def get_chapter_content(self, chapter_title: str) -> Optional[str]:
        """按标题获取章节内容"""
        for ch in self._chapter_list():
            if isinstance(ch, dict) and ch.get('title') == chapter_title:
                return ch.get('content', '')
        return None

    def get_recent_chapters(self, count: int = 5) -> List[str]:
        """获取最近 N 章正文（前文上下文参考，上下文记忆前5章）"""
        texts = [ch.get('content', '') for ch in self._chapter_list()
                 if isinstance(ch, dict) and ch.get('content')]
        return texts[-count:]

    def add_chapter(self, title: str, content: str,
                    source: str = "continuation") -> None:
        """追加章节到项目（续写保存/生成沉淀路径）

        同名章节覆盖内容（用户重复保存同一章的自然预期）。
        """
        if not self._current_project:
            logger.warning("[ProjectManager] 没有当前项目，无法保存章节")
            return
        if not isinstance(content, str) or not content.strip():
            logger.warning("[ProjectManager] 章节内容为空，跳过保存")
            return
        chapters = self._chapter_list()
        entry = {
            'title': title or f'第{len(chapters) + 1}章',
            'content': content,
            'word_count': len(content),
            'source': source,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        for i, ch in enumerate(chapters):
            if isinstance(ch, dict) and ch.get('title') == entry['title']:
                chapters[i] = entry
                break
        else:
            chapters.append(entry)
        # 发布数据变更事件（与 sync_module_data 一致）
        if self._event_bus:
            self._event_bus.publish(
                ProjectDataEvent('completed_chapters', entry, 'update'))
        logger.info(f"[ProjectManager] 章节已保存: {entry['title']} "
                    f"({entry['word_count']}字, {source})")

    def update_current_chapter(self, content: str) -> None:
        """更新最近一章内容（续写"追加到当前章节"路径）"""
        chapters = self._chapter_list()
        if not chapters:
            self.add_chapter("第1章", content, source="continuation")
            return
        last = chapters[-1]
        if isinstance(last, dict):
            last['content'] = content
            last['word_count'] = len(content)
            last['created_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"[ProjectManager] 已更新章节: {last.get('title', '')}")


# 全局单例
_project_manager_instance: Optional[ProjectManager] = None


def get_project_manager(event_bus: Optional[EventBus] = None) -> ProjectManager:
    """
    获取项目管理器单例
    
    Args:
        event_bus: 事件总线实例（仅首次创建时需要）
        
    Returns:
        项目管理器实例
    """
    global _project_manager_instance
    
    if _project_manager_instance is None:
        _project_manager_instance = ProjectManager(event_bus)
        logger.info("[ProjectManager] 创建全局单例")
    elif event_bus is not None:
        _project_manager_instance.set_event_bus(event_bus)
    
    return _project_manager_instance
