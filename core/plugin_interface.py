"""
插件接口定义

V1.2版本（最终修订版）
创建日期：2026-03-21

特性：
- BasePlugin基础接口
- 专用插件接口（Analyzer/Generator/Validator）
- 生命周期管理
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .models import GenerationRequest, GenerationResult, ValidationScores


class BasePlugin(ABC):
    """
    插件基类
    
    所有插件必须继承此类并实现必要的方法
    """
    
    # 插件元数据（子类必须覆盖）
    PLUGIN_ID: str = "base_plugin"
    PLUGIN_NAME: str = "Base Plugin"
    PLUGIN_VERSION: str = "1.0.0"
    PLUGIN_TYPE: str = "TOOL"
    
    # 插件依赖（可选）
    DEPENDENCIES: List[str] = []
    
    def __init__(self):
        """初始化插件"""
        self._initialized: bool = False
        self._context: Optional[Dict[str, Any]] = None
    
    def initialize(self, context: Dict[str, Any]) -> bool:
        """
        初始化插件
        
        Args:
            context: 插件上下文（包含EventBus、ConfigManager等）
        
        Returns:
            是否初始化成功
        """
        if self._initialized:
            return True
        
        self._context = context
        
        try:
            # 子类可覆盖此方法进行自定义初始化
            self._initialized = True
            return True
        except Exception as e:
            import logging
            logging.error(f"Plugin {self.PLUGIN_ID} initialization failed: {e}")
            return False
    
    def dispose(self) -> None:
        """
        释放插件资源
        
        子类可覆盖此方法进行自定义清理
        """
        self._initialized = False
        self._context = None
    
    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized
    
    @property
    def context(self) -> Optional[Dict[str, Any]]:
        """获取插件上下文"""
        return self._context
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        获取插件元数据
        
        Returns:
            元数据字典
        """
        return {
            "id": self.PLUGIN_ID,
            "name": self.PLUGIN_NAME,
            "version": self.PLUGIN_VERSION,
            "type": self.PLUGIN_TYPE,
            "dependencies": self.DEPENDENCIES
        }


class AnalyzerPlugin(BasePlugin):
    """
    分析器插件基类
    
    用于大纲解析、风格分析、人物分析等
    """
    
    PLUGIN_TYPE: str = "ANALYZER"
    
    @abstractmethod
    def analyze(
        self,
        content: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行分析
        
        Args:
            content: 待分析内容
            context: 分析上下文
        
        Returns:
            分析结果
        """
        pass


class GeneratorPlugin(BasePlugin):
    """
    生成器插件基类
    
    用于章节内容生成
    """
    
    PLUGIN_TYPE: str = "GENERATOR"
    
    @abstractmethod
    def generate(
        self,
        request: GenerationRequest
    ) -> GenerationResult:
        """
        执行生成
        
        Args:
            request: 生成请求
        
        Returns:
            生成结果
        """
        pass
    
    def cancel(self, request_id: str) -> bool:
        """
        取消生成
        
        Args:
            request_id: 请求ID
        
        Returns:
            是否取消成功
        """
        return False  # 默认不支持取消


class ValidatorPlugin(BasePlugin):
    """
    验证器插件基类
    
    用于内容质量评分验证
    """
    
    PLUGIN_TYPE: str = "VALIDATOR"
    
    @abstractmethod
    def validate(
        self,
        content: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationScores:
        """
        执行验证
        
        Args:
            content: 待验证内容
            context: 验证上下文
        
        Returns:
            验证评分
        """
        pass


class StoragePlugin(BasePlugin):
    """
    存储插件基类
    
    用于数据持久化
    """
    
    PLUGIN_TYPE: str = "STORAGE"
    
    @abstractmethod
    def save(
        self,
        key: str,
        data: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        保存数据
        
        Args:
            key: 数据键
            data: 数据内容
            metadata: 元数据
        
        Returns:
            是否保存成功
        """
        pass
    
    @abstractmethod
    def load(
        self,
        key: str
    ) -> Optional[Any]:
        """
        加载数据
        
        Args:
            key: 数据键
        
        Returns:
            数据内容
        """
        pass
    
    @abstractmethod
    def delete(
        self,
        key: str
    ) -> bool:
        """
        删除数据
        
        Args:
            key: 数据键
        
        Returns:
            是否删除成功
        """
        pass
    
    @abstractmethod
    def list_keys(
        self,
        prefix: str = ""
    ) -> List[str]:
        """
        列出所有键
        
        Args:
            prefix: 键前缀
        
        Returns:
            键列表
        """
        pass


class AIPlugin(BasePlugin):
    """
    AI插件基类
    
    用于LLM调用封装
    """
    
    PLUGIN_TYPE: str = "AI"
    
    @abstractmethod
    def call(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        调用AI模型
        
        Args:
            prompt: 提示词
            context: 调用上下文
        
        Returns:
            AI响应
        """
        pass
    
    @abstractmethod
    def stream_call(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        流式调用AI模型
        
        Args:
            prompt: 提示词
            context: 调用上下文
        
        Yields:
            AI响应片段
        """
        pass


class ToolPlugin(BasePlugin):
    """
    工具插件基类
    
    用于通用工具功能
    """
    
    PLUGIN_TYPE: str = "TOOL"
    
    @abstractmethod
    def execute(
        self,
        action: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行工具操作
        
        Args:
            action: 操作名称
            params: 操作参数
        
        Returns:
            执行结果
        """
        pass


class ProtocolPlugin(BasePlugin):
    """
    协议插件基类
    
    用于导入导出格式转换
    """
    
    PLUGIN_TYPE: str = "PROTOCOL"
    
    @abstractmethod
    def import_data(
        self,
        source: str,
        format: str
    ) -> Dict[str, Any]:
        """
        导入数据
        
        Args:
            source: 数据源
            format: 数据格式
        
        Returns:
            解析后的数据
        """
        pass
    
    @abstractmethod
    def export_data(
        self,
        data: Dict[str, Any],
        format: str
    ) -> str:
        """
        导出数据
        
        Args:
            data: 数据内容
            format: 目标格式
        
        Returns:
            导出后的数据
        """
        pass
