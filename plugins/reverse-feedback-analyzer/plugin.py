"""
逆向反馈分析插件包装器

V1.1版本（重构版）
更新日期: 2026-03-24

此文件是插件入口包装器，继承自核心实现ReverseFeedbackAnalyzer。
核心实现位于 reverse_feedback_analyzer.py。

架构说明：
- ReverseFeedbackAnalyzer: 核心实现（reverse_feedback_analyzer.py）
- ReverseFeedbackAnalyzerPlugin: 插件包装器（本文件），继承核心实现
"""

from typing import Dict, Any, Optional
import os
import sys
import importlib.util

# 动态导入核心实现（支持连字符目录名）
def _load_core_module():
    """动态加载核心模块"""
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    core_file = os.path.join(plugin_dir, "reverse_feedback_analyzer.py")
    
    if not os.path.exists(core_file):
        raise ImportError(f"Core module not found: {core_file}")
    
    spec = importlib.util.spec_from_file_location("reverse_feedback_analyzer", core_file)
    module = importlib.util.module_from_spec(spec)
    sys.modules["reverse_feedback_analyzer"] = module
    spec.loader.exec_module(module)
    return module

# 尝试相对导入，失败则动态加载
try:
    from .reverse_feedback_analyzer import (
        ReverseFeedbackAnalyzer,
        AnalysisCache,
        LLMAnalyzer,
    )
except ImportError:
    try:
        _core_module = _load_core_module()
        ReverseFeedbackAnalyzer = _core_module.ReverseFeedbackAnalyzer
        AnalysisCache = _core_module.AnalysisCache
        LLMAnalyzer = _core_module.LLMAnalyzer
    except Exception as e:
        raise ImportError(f"Failed to load reverse_feedback_analyzer: {e}")

try:
    from core.plugin_interface import (
        PluginMetadata,
        PluginType,
        PluginContext,
        ConsistencyReport,
    )
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from core.plugin_interface import (
        PluginMetadata,
        PluginType,
        PluginContext,
        ConsistencyReport,
    )


class ReverseFeedbackAnalyzerPlugin(ReverseFeedbackAnalyzer):
    """逆向反馈分析器插件包装器
    
    继承自 ReverseFeedbackAnalyzer 核心实现，作为插件系统的入口类。
    
    使用继承而非组合的原因：
    1. 保持与原有接口的完全兼容
    2. 避免重复实现所有方法代理
    3. 允许插件级别的定制扩展
    """
    
    def __init__(self):
        """初始化插件包装器"""
        # 调用父类初始化（ReverseFeedbackAnalyzer会设置正确的metadata）
        super().__init__()
        
        # 插件级别的额外配置可以在这里添加
        self._plugin_extra_config: Dict[str, Any] = {}
    
    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据"""
        return PluginMetadata(
            id="reverse-feedback-analyzer",
            name="逆向反馈分析器",
            version="1.1.0",
            description="分析章节与设定的一致性，检测冲突并生成修正建议",
            author="项目组",
            plugin_type=PluginType.ANALYZER,
            priority=100,
            permissions=["llm.call", "project.read", "cache.readwrite"]
        )
    
    def initialize(self, context: PluginContext) -> bool:
        """初始化插件
        
        扩展父类初始化，添加插件级别的配置处理。
        """
        # 调用父类初始化
        success = super().initialize(context)
        if not success:
            return False
        
        # 插件级别的额外初始化
        try:
            # 获取插件专属配置
            plugin_config = context.config_manager.get_plugin_config(
                "reverse-feedback-analyzer"
            ) if hasattr(context.config_manager, 'get_plugin_config') else {}
            
            self._plugin_extra_config = plugin_config
            
            # 订阅章节生成事件（如果配置启用）
            if plugin_config.get("auto_analyze_on_chapter_generated", True):
                context.event_bus.subscribe(
                    "chapter.generated",
                    self._on_chapter_generated
                )
            
            return True
            
        except Exception as e:
            # 初始化失败但不影响核心功能
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"插件级别初始化失败（非关键）: {e}")
            return True
    
    def shutdown(self) -> bool:
        """关闭插件"""
        # 取消事件订阅
        if self._context:
            try:
                self._context.event_bus.unsubscribe("chapter.generated")
            except Exception:
                pass
        
        # 调用父类关闭
        return super().shutdown()
    
    def _on_chapter_generated(self, event):
        """处理章节生成事件
        
        章节生成后自动进行一致性分析。
        """
        try:
            chapter_data = event.data
            
            # 异步分析，避免阻塞主流程
            import threading
            thread = threading.Thread(
                target=self._async_analyze_chapter,
                args=(chapter_data,),
                daemon=True
            )
            thread.start()
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"处理章节生成事件失败: {e}")
    
    def _async_analyze_chapter(self, chapter_data: Dict[str, Any]):
        """异步分析章节"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            chapter_text = chapter_data.get("content", "")
            chapter_id = chapter_data.get("id", "")
            chapter_title = chapter_data.get("title", "")
            
            if not chapter_text:
                return
            
            # 获取当前设定
            current_settings = chapter_data.get("settings", {})
            
            # 执行分析
            report = self.analyze_chapter_vs_settings(
                chapter_text,
                current_settings,
                chapter_id
            )
            
            # 如果发现问题，发布事件
            if len(report.issues) > 0:
                self._context.event_bus.publish(
                    "consistency.issue.detected",
                    {
                        "chapter_id": chapter_id,
                        "chapter_title": chapter_title,
                        "report": report.to_dict()
                    },
                    source="ReverseFeedbackAnalyzer"
                )
                
                logger.info(f"章节 {chapter_title} 一致性分析完成，发现 {len(report.issues)} 个问题")
            else:
                logger.info(f"章节 {chapter_title} 一致性分析完成，未发现问题")
                
        except Exception as e:
            logger.error(f"异步分析章节失败: {e}")


# 导出核心实现类（方便外部直接使用）
__all__ = [
    "ReverseFeedbackAnalyzerPlugin",
    "ReverseFeedbackAnalyzer",
    "AnalysisCache",
    "LLMAnalyzer",
]
