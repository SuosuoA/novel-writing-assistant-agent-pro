"""
API配置管理插件

V1.0版本
创建日期: 2026-03-26
最后更新: 2026-03-26

功能:
- 全局API配置管理（本地/线上切换）
- API Key加密存储
- 配置变更事件发布到EventBus
- 提供统一配置查询接口
- 支持测试连接

核心能力:
1. save_config(): 保存全局配置（加密API Key）
2. get_config(): 获取完整配置（解密API Key）
3. test_connection(): 测试API连接
4. backup_keys(): 备份API Key
5. restore_keys(): 恢复API Key

参考文档:
- 《11.2API安全使用方案✅️.md》
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

from core.plugin_interface import ToolPlugin, PluginContext, PluginState
from core.event_bus import EventBus, get_event_bus

# 尝试导入加密模块
try:
    from core.api_key_encryption import APIKeyEncryption, get_api_key_encryption, CRYPTO_AVAILABLE
except ImportError:
    CRYPTO_AVAILABLE = False
    APIKeyEncryption = None
    get_api_key_encryption = None


@dataclass
class APIConfig:
    """API配置数据类"""
    service_mode: str = "remote"  # local / remote
    provider: str = "DeepSeek"
    model: str = "deepseek-chat"
    api_key: str = ""
    local_url: str = "http://localhost:11434/v1"
    base_url: str = "https://api.deepseek.com"
    temperature: float = 0.7
    max_tokens: int = 4096


class APIConfigManagerPlugin(ToolPlugin):
    """
    API配置管理插件
    
    功能:
    - 管理全局API配置
    - 加密存储API Key
    - 发布配置变更事件
    - 提供配置查询接口
    """
    
    # 插件元数据
    PLUGIN_ID = "api-config-manager-v1"
    PLUGIN_NAME = "API配置管理器"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "全局API配置管理，支持加密存储和实时同步"
    
    # 支持的Provider配置
    PROVIDER_CONFIGS = {
        "DeepSeek": {
            "base_url": "https://api.deepseek.com",
            "models": ["deepseek-chat", "deepseek-reasoner"],
            "default_model": "deepseek-chat"
        },
        "OpenAI": {
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
            "default_model": "gpt-4o"
        },
        "Anthropic": {
            "base_url": "https://api.anthropic.com",
            "models": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
            "default_model": "claude-3-sonnet"
        },
        "Ollama": {
            "base_url": "http://localhost:11434/v1",
            "models": ["llama3", "mistral", "qwen2"],
            "default_model": "llama3"
        }
    }
    
    def __init__(self):
        # 调用父类初始化
        super().__init__(metadata=self.get_metadata())
        self._logger = logging.getLogger(__name__)
        
        # 配置存储
        self._config: Optional[APIConfig] = None
        self._encryption: Optional[APIKeyEncryption] = None
        
        # 配置文件路径
        self._config_path: Optional[Path] = None
        self._event_bus: Optional[EventBus] = None
    
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
            plugin_type=PluginType.TOOL
        )
        
        # 配置存储
        self._config: Optional[APIConfig] = None
        self._encryption: Optional[APIKeyEncryption] = None
        
        # 配置文件路径
        self._config_path: Optional[Path] = None
        self._event_bus: Optional[EventBus] = None
    
    @property
    def category(self) -> str:
        return "tool"
    
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
            
            # 确定项目根目录
            if context.config_manager:
                self._config_path = Path(context.config_manager.config_path).parent / "config.yaml"
            else:
                self._config_path = Path.cwd() / "config.yaml"
            
            # 初始化加密模块
            if CRYPTO_AVAILABLE and get_api_key_encryption:
                project_root = self._config_path.parent
                self._encryption = get_api_key_encryption(project_root)
                self._logger.info("API Key encryption initialized")
            else:
                self._logger.warning("API Key encryption not available, using plaintext")
            
            # 加载配置
            self._load_config()
            
            self._state = PluginState.ACTIVE
            self._logger.info(f"Plugin {self.PLUGIN_ID} initialized successfully")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to initialize plugin: {e}")
            self._state = PluginState.ERROR
            return False
    
    def _load_config(self) -> None:
        """从config.yaml加载配置"""
        if not self._config_path or not self._config_path.exists():
            self._logger.warning(f"Config file not found, using defaults")
            self._config = APIConfig()
            return
        
        try:
            import yaml
            with open(self._config_path, 'r', encoding='utf-8') as f:
                config_dict = yaml.safe_load(f) or {}
            
            # 从加密存储加载API Key
            api_key = ""
            if self._encryption:
                provider = config_dict.get("provider", "DeepSeek")
                api_key = self._encryption.get_api_key(provider) or ""
            
            # 构建配置对象
            self._config = APIConfig(
                service_mode=config_dict.get("service_mode", "remote"),
                provider=config_dict.get("provider", "DeepSeek"),
                model=config_dict.get("model", "deepseek-chat"),
                api_key=api_key,
                local_url=config_dict.get("local_url", "http://localhost:11434/v1"),
                base_url=config_dict.get("base_url", self._get_provider_base_url(config_dict.get("provider", "DeepSeek"))),
                temperature=config_dict.get("temperature", 0.7),
                max_tokens=config_dict.get("max_tokens", 4096)
            )
            
            self._logger.info(f"Config loaded: mode={self._config.service_mode}, provider={self._config.provider}")
            
        except Exception as e:
            self._logger.error(f"Failed to load config: {e}")
            self._config = APIConfig()
    
    def _get_provider_base_url(self, provider: str) -> str:
        """获取Provider的默认Base URL"""
        if provider in self.PROVIDER_CONFIGS:
            return self.PROVIDER_CONFIGS[provider]["base_url"]
        return "https://api.deepseek.com"
    
    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        执行工具操作
        
        Args:
            action: 操作类型
            params: 操作参数
        
        Returns:
            操作结果
        """
        params = params or {}
        
        if action == "get_config":
            return self.get_config()
        elif action == "save_config":
            return self.save_config(params)
        elif action == "test_connection":
            return self.test_connection(params)
        elif action == "backup_keys":
            return self.backup_keys(params.get("backup_path"))
        elif action == "restore_keys":
            return self.restore_keys(params.get("backup_path"))
        elif action == "get_provider_models":
            return self.get_provider_models(params.get("provider"))
        elif action == "get_security_status":
            return self.get_security_status()
        else:
            raise ValueError(f"Unknown action: {action}")
    
    def get_config(self) -> Dict[str, Any]:
        """
        获取完整配置
        
        Returns:
            配置字典
        """
        if self._config is None:
            self._load_config()
        
        return {
            "service_mode": self._config.service_mode,
            "provider": self._config.provider,
            "model": self._config.model,
            "api_key": self._config.api_key,
            "local_url": self._config.local_url,
            "base_url": self._config.base_url,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens
        }
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """
        保存配置
        
        Args:
            config: 配置字典
        
        Returns:
            是否保存成功
        """
        try:
            # 验证配置
            if "service_mode" in config and config["service_mode"] not in ["local", "remote"]:
                raise ValueError("service_mode must be 'local' or 'remote'")
            
            # 保存API Key到加密存储
            if "api_key" in config and config["api_key"] and self._encryption:
                provider = config.get("provider", self._config.provider if self._config else "DeepSeek")
                self._encryption.save_api_key(provider, config["api_key"])
                self._logger.info(f"API Key encrypted and saved for {provider}")
            
            # 更新内存配置
            if self._config is None:
                self._config = APIConfig()
            
            # 更新配置字段
            for key, value in config.items():
                if key != "api_key" and hasattr(self._config, key):
                    setattr(self._config, key, value)
            
            # 更新base_url
            if "provider" in config:
                self._config.base_url = self._get_provider_base_url(config["provider"])
            
            # 保存非敏感配置到config.yaml
            self._save_config_to_yaml()
            
            # 发布配置变更事件
            self._publish_config_changed_event(config)
            
            self._logger.info("Config saved successfully")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to save config: {e}")
            return False
    
    def _save_config_to_yaml(self) -> None:
        """保存非敏感配置到config.yaml"""
        if not self._config_path:
            return
        
        try:
            import yaml
            
            # 读取现有配置
            existing_config = {}
            if self._config_path.exists():
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    existing_config = yaml.safe_load(f) or {}
            
            # 更新配置（不包含api_key）
            existing_config.update({
                "service_mode": self._config.service_mode,
                "provider": self._config.provider,
                "model": self._config.model,
                "local_url": self._config.local_url,
                "base_url": self._config.base_url,
                "temperature": self._config.temperature,
                "max_tokens": self._config.max_tokens
            })
            
            # 保存
            with open(self._config_path, 'w', encoding='utf-8') as f:
                yaml.dump(existing_config, f, allow_unicode=True, default_flow_style=False)
            
            self._logger.info(f"Config saved to {self._config_path}")
            
        except Exception as e:
            self._logger.error(f"Failed to save config to YAML: {e}")
    
    def _publish_config_changed_event(self, changed_config: Dict[str, Any]) -> None:
        """发布配置变更事件"""
        if self._event_bus:
            event_data = {
                "config": changed_config,
                "timestamp": datetime.now().isoformat(),
                "source": self.PLUGIN_ID
            }
            self._event_bus.publish("api.config.changed", event_data, self.PLUGIN_ID)
            self._logger.info("Published api.config.changed event")
    
    def test_connection(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        测试API连接
        
        Args:
            config: 测试配置（可选，默认使用当前配置）
        
        Returns:
            测试结果
        """
        test_config = config or self.get_config()
        
        result = {
            "success": False,
            "message": "",
            "latency_ms": 0
        }
        
        try:
            import time
            from openai import OpenAI
            
            # 构建客户端
            if test_config["service_mode"] == "local":
                client = OpenAI(
                    api_key="ollama",  # Ollama不需要真实key
                    base_url=test_config["local_url"]
                )
            else:
                # 获取API Key
                api_key = test_config.get("api_key", "")
                if not api_key and self._encryption:
                    api_key = self._encryption.get_api_key(test_config["provider"]) or ""
                
                if not api_key:
                    result["message"] = "API Key未配置"
                    return result
                
                client = OpenAI(
                    api_key=api_key,
                    base_url=test_config.get("base_url", "https://api.deepseek.com")
                )
            
            # 发送测试请求
            start_time = time.time()
            response = client.chat.completions.create(
                model=test_config["model"],
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10
            )
            latency_ms = int((time.time() - start_time) * 1000)
            
            result["success"] = True
            result["message"] = f"连接成功，延迟{latency_ms}ms"
            result["latency_ms"] = latency_ms
            
            self._logger.info(f"Connection test passed: {latency_ms}ms")
            
        except Exception as e:
            result["message"] = f"连接失败: {str(e)}"
            self._logger.error(f"Connection test failed: {e}")
        
        return result
    
    def backup_keys(self, backup_path: Optional[str] = None) -> Dict[str, Any]:
        """
        备份API Keys
        
        Args:
            backup_path: 备份路径（可选）
        
        Returns:
            备份结果
        """
        result = {
            "success": False,
            "message": "",
            "backup_path": ""
        }
        
        if not self._encryption:
            result["message"] = "加密模块未初始化"
            return result
        
        try:
            if backup_path is None:
                backup_path = str(Path.cwd() / f"api_keys_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.enc")
            
            if self._encryption.backup_keys(Path(backup_path)):
                result["success"] = True
                result["message"] = "备份成功"
                result["backup_path"] = backup_path
            else:
                result["message"] = "备份失败"
                
        except Exception as e:
            result["message"] = f"备份失败: {str(e)}"
        
        return result
    
    def restore_keys(self, backup_path: Optional[str] = None) -> Dict[str, Any]:
        """
        恢复API Keys
        
        Args:
            backup_path: 备份文件路径
        
        Returns:
            恢复结果
        """
        result = {
            "success": False,
            "message": ""
        }
        
        if not self._encryption:
            result["message"] = "加密模块未初始化"
            return result
        
        if not backup_path:
            result["message"] = "请指定备份文件路径"
            return result
        
        try:
            if self._encryption.restore_keys(Path(backup_path)):
                result["success"] = True
                result["message"] = "恢复成功"
                # 重新加载配置
                self._load_config()
            else:
                result["message"] = "恢复失败"
                
        except Exception as e:
            result["message"] = f"恢复失败: {str(e)}"
        
        return result
    
    def get_provider_models(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """
        获取Provider支持的模型列表
        
        Args:
            provider: 服务提供商（可选，默认返回所有）
        
        Returns:
            模型列表
        """
        if provider:
            if provider in self.PROVIDER_CONFIGS:
                return {
                    "provider": provider,
                    "models": self.PROVIDER_CONFIGS[provider]["models"],
                    "default_model": self.PROVIDER_CONFIGS[provider]["default_model"],
                    "base_url": self.PROVIDER_CONFIGS[provider]["base_url"]
                }
            else:
                return {"error": f"Unknown provider: {provider}"}
        else:
            return {
                "providers": {
                    p: {
                        "models": cfg["models"],
                        "default_model": cfg["default_model"],
                        "base_url": cfg["base_url"]
                    }
                    for p, cfg in self.PROVIDER_CONFIGS.items()
                }
            }
    
    def get_security_status(self) -> Dict[str, Any]:
        """
        获取安全状态
        
        Returns:
            安全状态信息
        """
        if self._encryption:
            return self._encryption.get_security_status()
        else:
            return {
                "encryption_available": False,
                "message": "加密模块未初始化"
            }
    
    def shutdown(self) -> None:
        """关闭插件"""
        self._logger.info(f"Plugin {self.PLUGIN_ID} shutting down")
        self._state = PluginState.UNLOADING
        self._config = None
        self._encryption = None
        self._state = PluginState.UNLOADED


# 插件工厂函数
def create_plugin():
    """创建插件实例"""
    return APIConfigManagerPlugin()
