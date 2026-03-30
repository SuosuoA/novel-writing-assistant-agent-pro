"""
AI能力提供者抽象基类

V1.0版本
创建日期：2026-03-24

设计目标：
- 定义统一的AI能力接口，屏蔽底层差异
- 支持同步和流式生成
- 提供文本分析、token估算、模型信息查询
- 线程安全设计

架构角色：
- 抽象层：定义所有AI能力接口
- 实现层：OnlineProvider、LocalProvider等具体实现
- 管理层：AIServiceManager负责创建和切换Provider
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AIProviderType(Enum):
    """AI提供者类型"""
    ONLINE = "online"    # 线上API
    LOCAL = "local"      # 本地大模型


class AIProviderState(Enum):
    """AI提供者状态"""
    UNINITIALIZED = "uninitialized"  # 未初始化
    READY = "ready"                  # 就绪
    ERROR = "error"                  # 错误
    BUSY = "busy"                    # 忙碌


@dataclass
class AIModelInfo:
    """AI模型信息"""
    provider_type: AIProviderType    # 提供者类型
    provider_name: str               # 提供者名称（如：DeepSeek、OpenAI、Ollama）
    model_name: str                  # 模型名称
    max_tokens: int                  # 最大token数
    supports_streaming: bool         # 是否支持流式生成
    supports_vision: bool            # 是否支持视觉
    metadata: Dict[str, Any]         # 其他元数据


@dataclass
class GenerationConfig:
    """生成配置"""
    temperature: float = 0.7         # 温度参数（0-2）
    max_tokens: int = 4096           # 最大生成token数
    top_p: float = 1.0               # Top-p采样
    frequency_penalty: float = 0.0   # 频率惩罚
    presence_penalty: float = 0.0    # 存在惩罚
    stop: Optional[list] = None      # 停止词列表
    timeout: int = 120               # 超时时间（秒）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stop": self.stop,
            "timeout": self.timeout,
        }


@dataclass
class GenerationResult:
    """生成结果"""
    text: str                        # 生成的文本
    finish_reason: str               # 结束原因（stop/length/error）
    usage: Dict[str, int]            # token使用情况
    model: str                       # 使用的模型
    provider: str                    # 提供者名称
    latency_ms: int                  # 延迟（毫秒）
    success: bool = True             # 是否成功
    error: Optional[str] = None      # 错误信息
    
    def get_token_count(self) -> int:
        """获取总token数"""
        return self.usage.get("total_tokens", 0)


class AIProvider(ABC):
    """
    AI能力提供者抽象基类
    
    设计原则：
    - 最小化接口：只定义必要的AI能力方法
    - 向后兼容：新增方法使用默认实现
    - 线程安全：所有方法都是线程安全的
    - 错误处理：明确的异常类型和错误信息
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化AI提供者
        
        Args:
            config: 配置字典
        """
        self._config = config
        self._state = AIProviderState.UNINITIALIZED
        self._lock = None  # 子类实现时初始化
        logger.info(f"AIProvider初始化: {self.__class__.__name__}")
    
    @abstractmethod
    def generate_text(
        self, 
        prompt: str, 
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> GenerationResult:
        """
        生成文本（同步）
        
        Args:
            prompt: 提示词
            config: 生成配置（可选）
            **kwargs: 其他参数（如system_prompt、messages等）
            
        Returns:
            GenerationResult: 生成结果
            
        Raises:
            AIProviderError: AI提供者错误
        """
        pass
    
    @abstractmethod
    def generate_text_stream(
        self, 
        prompt: str,
        callback: Callable[[str], None],
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> GenerationResult:
        """
        流式生成文本（异步回调）
        
        Args:
            prompt: 提示词
            callback: 回调函数，每次收到新token时调用
            config: 生成配置（可选）
            **kwargs: 其他参数
            
        Returns:
            GenerationResult: 最终生成结果
            
        Raises:
            AIProviderError: AI提供者错误
        """
        pass
    
    @abstractmethod
    def analyze_text(
        self, 
        text: str, 
        analysis_type: str,
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        分析文本（结构化输出）
        
        Args:
            text: 待分析文本
            analysis_type: 分析类型（如：sentiment、summary、extraction）
            config: 生成配置（可选）
            **kwargs: 其他参数（如schema、fields等）
            
        Returns:
            Dict[str, Any]: 分析结果（结构化数据）
            
        Raises:
            AIProviderError: AI提供者错误
        """
        pass
    
    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """
        估算token数
        
        Args:
            text: 文本内容
            
        Returns:
            int: 估算的token数
        """
        pass
    
    @abstractmethod
    def get_model_info(self) -> AIModelInfo:
        """
        获取模型信息
        
        Returns:
            AIModelInfo: 模型信息
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        检查服务是否可用
        
        Returns:
            bool: 是否可用
        """
        pass
    
    def get_state(self) -> AIProviderState:
        """
        获取提供者状态
        
        Returns:
            AIProviderState: 状态
        """
        return self._state
    
    def get_config(self) -> Dict[str, Any]:
        """
        获取配置
        
        Returns:
            Dict[str, Any]: 配置字典
        """
        return self._config.copy()
    
    def update_config(self, config: Dict[str, Any]) -> None:
        """
        更新配置
        
        Args:
            config: 新配置（会与旧配置合并）
        """
        self._config.update(config)
        logger.info(f"AIProvider配置更新: {self.__class__.__name__}")
    
    # ==================== 可选方法（提供默认实现）====================
    
    def generate_with_context(
        self,
        prompt: str,
        context: Dict[str, Any],
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> GenerationResult:
        """
        带上下文的生成（可选实现）
        
        Args:
            prompt: 提示词
            context: 上下文信息（如大纲、人设、世界观等）
            config: 生成配置（可选）
            **kwargs: 其他参数
            
        Returns:
            GenerationResult: 生成结果
        """
        # 默认实现：将上下文拼接到prompt
        context_str = self._format_context(context)
        full_prompt = f"{context_str}\n\n{prompt}" if context_str else prompt
        return self.generate_text(full_prompt, config, **kwargs)
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """
        格式化上下文（内部方法）
        
        Args:
            context: 上下文字典
            
        Returns:
            str: 格式化后的上下文字符串
        """
        parts = []
        for key, value in context.items():
            if value:
                parts.append(f"【{key}】\n{value}")
        return "\n\n".join(parts)
    
    def batch_generate(
        self,
        prompts: list,
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> list:
        """
        批量生成（可选实现）
        
        Args:
            prompts: 提示词列表
            config: 生成配置（可选）
            **kwargs: 其他参数
            
        Returns:
            list: GenerationResult列表
        """
        # 默认实现：顺序执行
        results = []
        for prompt in prompts:
            result = self.generate_text(prompt, config, **kwargs)
            results.append(result)
        return results
    
    def validate_config(self) -> bool:
        """
        验证配置是否有效（可选实现）
        
        Returns:
            bool: 配置是否有效
        """
        return True
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查（可选实现）
        
        Returns:
            Dict[str, Any]: 健康状态信息
        """
        return {
            "provider": self.__class__.__name__,
            "state": self._state.value,
            "available": self.is_available(),
            "model": self.get_model_info().model_name,
        }


class AIProviderError(Exception):
    """AI提供者错误"""
    
    def __init__(self, message: str, provider: str = None, original_error: Exception = None):
        super().__init__(message)
        self.provider = provider
        self.original_error = original_error
    
    def __str__(self):
        parts = [super().__str__()]
        if self.provider:
            parts.insert(0, f"[{self.provider}]")
        if self.original_error:
            parts.append(f"原因: {self.original_error}")
        return " ".join(parts)


class AIProviderTimeoutError(AIProviderError):
    """AI提供者超时错误"""
    pass


class AIProviderUnavailableError(AIProviderError):
    """AI提供者不可用错误"""
    pass


class AIProviderConfigError(AIProviderError):
    """AI提供者配置错误"""
    pass
