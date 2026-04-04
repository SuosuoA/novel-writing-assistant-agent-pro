"""
项目管理器插件

提供项目管理功能的插件接口。
遵循《插件接口定义V2.3》规范。
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from core.plugin_interface import BasePlugin, PluginMetadata, PluginType, PluginContext
from core.event_bus import EventBus
from services.project_manager import (
    ProjectManager,
    get_project_manager,
    ProjectDataEvent,
    ProjectSavedEvent,
    ProjectLoadedEvent
)
import logging

# 使用标准日志器(避免导入错误)
logger = logging.getLogger(__name__)


@dataclass
class ProjectPluginMetadata(PluginMetadata):
    """项目管理器插件元数据"""
    id: str = "project-manager-v1"
    name: str = "项目管理器"
    version: str = "1.0.0"
    description: str = "提供项目保存、加载、同步等核心功能"
    author: str = "Agent Pro Team"
    plugin_type: PluginType = PluginType.TOOL


class ProjectManagerPlugin(BasePlugin):
    """
    项目管理器插件
    
    功能：
    1. 项目文件保存/加载
    2. 模块数据同步
    3. 与EventBus集成，发布数据变更事件
    4. 提供项目管理器服务给其他插件
    """
    
    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        self._project_manager: Optional[ProjectManager] = None
    
    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return ProjectPluginMetadata()
    
    def initialize(self, context: PluginContext) -> bool:
        """
        初始化插件
        
        Args:
            context: 插件上下文
            
        Returns:
            是否初始化成功
        """
        try:
            # 创建项目管理器实例
            self._project_manager = ProjectManager(context.event_bus)
            
            # 注册到服务定位器
            context.service_locator.register_service(
                "project_manager",
                self._project_manager
            )
            
            # 订阅项目数据变更事件（用于日志）
            context.event_bus.subscribe("project.data.*", self._on_data_changed)
            context.event_bus.subscribe("project.saved", self._on_project_saved)
            context.event_bus.subscribe("project.loaded", self._on_project_loaded)
            
            logger.info(f"[ProjectManagerPlugin] 初始化成功: {self.metadata.id}")
            return True
            
        except Exception as e:
            logger.error(f"[ProjectManagerPlugin] 初始化失败: {e}")
            return False
    
    def shutdown(self) -> bool:
        """关闭插件"""
        try:
            # 自动保存项目
            if self._project_manager and self._project_manager.is_project_open():
                self._project_manager.save_project()
            
            logger.info(f"[ProjectManagerPlugin] 关闭完成: {self.metadata.id}")
            return True
        except Exception as e:
            logger.error(f"[ProjectManagerPlugin] 关闭失败: {e}")
            return False
    
    def _on_data_changed(self, event: ProjectDataEvent) -> None:
        """数据变更事件回调"""
        logger.info(
            f"[ProjectManagerPlugin] 数据变更: "
            f"{event.data_type} ({event.operation})"
        )
    
    def _on_project_saved(self, event: ProjectSavedEvent) -> None:
        """项目保存事件回调"""
        logger.info(
            f"[ProjectManagerPlugin] 项目已保存: "
            f"{event.project_name} ({event.project_path})"
        )
    
    def _on_project_loaded(self, event: ProjectLoadedEvent) -> None:
        """项目加载事件回调"""
        logger.info(
            f"[ProjectManagerPlugin] 项目已加载: "
            f"{event.project_name} ({event.project_path})"
        )
    
    # ===== 便捷方法（供其他插件调用）=====
    
    def get_manager(self) -> ProjectManager:
        """
        获取项目管理器实例
        
        Returns:
            项目管理器实例
        """
        return self._project_manager
