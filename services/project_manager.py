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
from typing import Dict, Any, Optional
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
