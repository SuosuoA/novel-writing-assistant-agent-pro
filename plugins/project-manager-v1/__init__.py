"""
项目管理器插件

提供项目保存、加载、同步等核心功能。
"""

from .plugin import ProjectManagerPlugin, ProjectPluginMetadata

__all__ = [
    'ProjectManagerPlugin',
    'ProjectPluginMetadata'
]
