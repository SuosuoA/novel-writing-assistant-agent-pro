"""
AI服务路由插件

V1.0版本
创建日期: 2026-03-26
最后更新: 2026-03-26

功能:
- 根据service_mode选择本地/线上服务
- 根据provider选择正确的AI Provider
- 提供统一的LLM客户端接口
- 订阅配置变更事件实时切换

核心能力:
1. get_llm_client(): 获取配置好的LLM客户端
2. switch_service(): 切换服务（响应配置变更）
3. get_current_provider(): 获取当前Provider信息

参考文档:
- 《11.2API安全使用方案✅️.md》
"""

import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

from core.plugin_interface import AIPlugin, PluginContext, PluginState
from core.event_bus import EventBus, get_event_bus

# 尝试导入OpenAI SDK
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logging.warning("openai package not available")


@dataclass
class AIServiceConfig:
    """AI服务配置"""
    service_mode: str = "remote"
    provider: str = "DeepSeek"
    model: str = "deepseek-chat"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    local_url: str = "http://localhost:11434/v1"
    temperature: float = 0.7
    max_tokens: int = 4096


class AIServiceRouterPlugin(AIPlugin):
    """
    AI服务路由插件
    
    功能:
    - 根据配置路由到正确的AI服务
    - 提供统一的LLM客户端接口
    - 实时响应配置变更
    """
    
    # 插件元数据
    PLUGIN_ID = "ai-service-router-v1"
    PLUGIN_NAME = "AI服务路由器"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "统一AI服务路由，支持本地/线上切换"
    
    # Provider配置映射
    PROVIDER_BASE_URLS = {
        "DeepSeek": "https://api.deepseek.com",
        "OpenAI": "https://api.openai.com/v1",
        "Anthropic": "https://api.anthropic.com",
        "Ollama": "http://localhost:11434/v1"
    }
    
    def __init__(self):
        # 调用父类初始化
        super().__init__(metadata=self.get_metadata())
        self._logger = logging.getLogger(__name__)
        
        # 当前客户端和配置
        self._client: Optional[OpenAI] = None
        self._config: Optional[AIServiceConfig] = None
        
        # EventBus
        self._event_bus: Optional[EventBus] = None
        
        # 配置管理器引用
        self._config_manager_plugin = None
    
    @classmethod
    def get_metadata(cls) -> "PluginMetadata":
        """获取插件元数据"""
        from core.plugin_interface import PluginMetadata, PluginType
        return PluginMetadata(
            id=cls.PLUGIN_ID,
            name=cls.PLUGIN_NAME,
            version=cls.PLUGIN_VERSION,
            description=cls.PLUGIN_DESCRIPTION,
            author="Agent Pro Team",
            plugin_type=PluginType.AI
        )
    
    def call(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        """调用AI模型"""
        result = self.chat({"messages": [{"role": "user", "content": prompt}]})
        return result.get("content", "")
    
    def stream_call(self, prompt: str, context: Optional[Dict[str, Any]] = None):
        """流式调用AI模型"""
        # 简化实现，返回非流式结果
        yield self.call(prompt, context)
        
        # 当前客户端和配置
        self._client: Optional[OpenAI] = None
        self._config: Optional[AIServiceConfig] = None
        
        # EventBus
        self._event_bus: Optional[EventBus] = None
        
        # 配置管理器引用
        self._config_manager_plugin = None
    
    @property
    def category(self) -> str:
        return "ai"
    
    def initialize(self, context: PluginContext) -> bool:
        """
        初始化插件
        
        Args:
            context: 插件上下文
        
        Returns:
            是否初始化成功
        """
        try:
            self._context = context
            self._state = PluginState.LOADING
            
            # 获取EventBus
            if context.event_bus:
                self._event_bus = context.event_bus
            else:
                self._event_bus = get_event_bus()
            
            # 订阅配置变更事件
            if self._event_bus:
                self._event_bus.subscribe(
                    "api.config.changed",
                    self._on_config_changed,
                    self.PLUGIN_ID
                )
                self._logger.info("Subscribed to api.config.changed event")
            
            # 初始化配置
            self._init_config()
            
            self._state = PluginState.ACTIVE
            self._logger.info(f"Plugin {self.PLUGIN_ID} initialized successfully")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to initialize plugin: {e}")
            self._state = PluginState.ERROR
            return False
    
    def _init_config(self) -> None:
        """初始化配置"""
        # 尝试从API配置管理器获取配置
        if self._context and self._context.plugin_registry:
            try:
                config_manager = self._context.plugin_registry.get_plugin("api-config-manager-v1")
                if config_manager:
                    config = config_manager.execute("get_config", {})
                    self._config = AIServiceConfig(
                        service_mode=config.get("service_mode", "remote"),
                        provider=config.get("provider", "DeepSeek"),
                        model=config.get("model", "deepseek-chat"),
                        api_key=config.get("api_key", ""),
                        base_url=config.get("base_url", "https://api.deepseek.com"),
                        local_url=config.get("local_url", "http://localhost:11434/v1"),
                        temperature=config.get("temperature", 0.7),
                        max_tokens=config.get("max_tokens", 4096)
                    )
                    self._logger.info("Config loaded from api-config-manager")
                    return
            except Exception as e:
                self._logger.warning(f"Failed to get config from api-config-manager: {e}")
        
        # 默认配置
        self._config = AIServiceConfig()
        self._logger.info("Using default config")
    
    def _on_config_changed(self, event_data: Dict[str, Any]) -> None:
        """
        配置变更事件处理器
        
        Args:
            event_data: 事件数据
        """
        try:
            config = event_data.get("config", {})
            self._logger.info(f"Received config changed event: {list(config.keys())}")
            
            # 更新配置
            if self._config is None:
                self._config = AIServiceConfig()
            
            for key, value in config.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)
            
            # 重置客户端（下次获取时重新创建）
            self._client = None
            
            self._logger.info(f"Service switched to: mode={self._config.service_mode}, provider={self._config.provider}")
            
        except Exception as e:
            self._logger.error(f"Failed to handle config change: {e}")
    
    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        执行操作
        
        Args:
            action: 操作类型
            params: 操作参数
        
        Returns:
            操作结果
        """
        params = params or {}
        
        if action == "get_llm_client":
            return self.get_llm_client()
        elif action == "get_current_config":
            return self.get_current_config()
        elif action == "get_current_provider":
            return self.get_current_provider()
        elif action == "switch_service":
            return self.switch_service(params)
        elif action == "chat":
            return self.chat(params)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    def get_llm_client(self) -> Optional[OpenAI]:
        """
        获取LLM客户端（自动路由到正确的服务）
        
        Returns:
            配置好的OpenAI客户端
        """
        if not OPENAI_AVAILABLE:
            self._logger.error("OpenAI SDK not available")
            return None
        
        # 如果客户端已存在且配置未变，直接返回
        if self._client is not None:
            return self._client
        
        # 创建新客户端
        try:
            if self._config is None:
                self._init_config()
            
            if self._config.service_mode == "local":
                # 本地模式
                self._client = OpenAI(
                    api_key="ollama",  # Ollama不需要真实key
                    base_url=self._config.local_url
                )
                self._logger.info(f"Local LLM client created: {self._config.local_url}")
            else:
                # 线上模式
                api_key = self._config.api_key
                if not api_key:
                    # 尝试从加密存储获取
                    if self._context and self._context.plugin_registry:
                        try:
                            config_manager = self._context.plugin_registry.get_plugin("api-config-manager-v1")
                            if config_manager:
                                config = config_manager.execute("get_config", {})
                                api_key = config.get("api_key", "")
                        except Exception:
                            pass
                
                if not api_key:
                    self._logger.error("API Key not configured")
                    return None
                
                self._client = OpenAI(
                    api_key=api_key,
                    base_url=self._config.base_url
                )
                self._logger.info(f"Remote LLM client created: {self._config.provider}")
            
            return self._client
            
        except Exception as e:
            self._logger.error(f"Failed to create LLM client: {e}")
            return None
    
    def get_current_config(self) -> Dict[str, Any]:
        """
        获取当前配置
        
        Returns:
            配置字典
        """
        if self._config is None:
            self._init_config()
        
        return {
            "service_mode": self._config.service_mode,
            "provider": self._config.provider,
            "model": self._config.model,
            "base_url": self._config.base_url,
            "local_url": self._config.local_url,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens
        }
    
    def get_current_provider(self) -> Dict[str, str]:
        """
        获取当前Provider信息
        
        Returns:
            Provider信息
        """
        if self._config is None:
            self._init_config()
        
        return {
            "provider": self._config.provider,
            "model": self._config.model,
            "service_mode": self._config.service_mode,
            "base_url": self._config.base_url if self._config.service_mode == "remote" else self._config.local_url
        }
    
    def switch_service(self, config: Dict[str, Any]) -> bool:
        """
        手动切换服务
        
        Args:
            config: 新配置
        
        Returns:
            是否切换成功
        """
        try:
            # 更新配置
            for key, value in config.items():
                if self._config and hasattr(self._config, key):
                    setattr(self._config, key, value)
            
            # 重置客户端
            self._client = None
            
            self._logger.info(f"Service switched manually: {config}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to switch service: {e}")
            return False
    
    def chat(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行对话（便捷方法）
        
        Args:
            params: 对话参数
                - messages: 消息列表
                - model: 模型（可选）
                - temperature: 温度（可选）
                - max_tokens: 最大token（可选）
        
        Returns:
            响应结果
        """
        result = {
            "success": False,
            "content": "",
            "usage": None,
            "error": None
        }
        
        try:
            client = self.get_llm_client()
            if client is None:
                result["error"] = "LLM client not available"
                return result
            
            messages = params.get("messages", [])
            if not messages:
                result["error"] = "Messages are required"
                return result
            
            # 构建请求参数
            request_params = {
                "model": params.get("model", self._config.model if self._config else "deepseek-chat"),
                "messages": messages
            }
            
            if "temperature" in params:
                request_params["temperature"] = params["temperature"]
            elif self._config:
                request_params["temperature"] = self._config.temperature
            
            if "max_tokens" in params:
                request_params["max_tokens"] = params["max_tokens"]
            elif self._config:
                request_params["max_tokens"] = self._config.max_tokens
            
            # 调用API
            response = client.chat.completions.create(**request_params)
            
            result["success"] = True
            result["content"] = response.choices[0].message.content
            result["usage"] = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            
        except Exception as e:
            result["error"] = str(e)
            self._logger.error(f"Chat failed: {e}")
        
        return result
    
    def shutdown(self) -> None:
        """关闭插件"""
        self._logger.info(f"Plugin {self.PLUGIN_ID} shutting down")
        
        # 取消订阅
        if self._event_bus:
            try:
                self._event_bus.unsubscribe("api.config.changed", self.PLUGIN_ID)
            except Exception:
                pass
        
        self._state = PluginState.UNLOADING
        self._client = None
        self._config = None
        self._state = PluginState.UNLOADED


# 插件工厂函数
def create_plugin():
    """创建插件实例"""
    return AIServiceRouterPlugin()
