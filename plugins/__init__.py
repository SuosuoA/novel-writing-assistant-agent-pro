"""
插件包

包含所有插件的顶层包。
"""

# 插件目录不直接导入子插件，由PluginLoader动态发现和加载
# 子插件目录使用连字符命名（如reverse-feedback-analyzer），非合法Python模块名
__all__ = []
