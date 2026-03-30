"""
AI服务管理器 - 统一管理所有AI调用

V1.0版本
创建日期：2026-03-24

设计目标：
- 单例模式：全局唯一实例
- 动态切换：根据配置动态创建/切换AIProvider
- 配置监听：监听配置变更事件，自动重新加载Provider
- 统一接口：提供统一的AI调用接口，屏蔽底层差异
- 线程安全：所有操作都是线程安全的

架构角色：
- 服务层：协调ConfigService、EventBus、AIProvider
- 代理层：对外提供统一的AI调用接口
- 管理层：管理Provider的生命周期
"""

import threading
import time
import hashlib
import logging
from typing import Any, Callable, Dict, Optional

from .ai_provider import (
    AIProvider,
    AIProviderState,
    AIProviderError,
    AIProviderUnavailableError,
    GenerationConfig,
    GenerationResult,
    AIModelInfo,
)
from .config_service import ConfigService, get_config_service
from .event_bus import EventBus, get_event_bus

logger = logging.getLogger(__name__)


class AIServiceManager:
    """
    AI服务管理器（单例）
    
    核心职责：
    1. 根据配置动态创建/切换AIProvider
    2. 缓存当前使用的AIProvider实例
    3. 提供统一的调用接口
    4. 监听配置变更事件
    5. 线程安全的Provider管理
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """
        初始化AI服务管理器
        """
        if self._initialized:
            return
        
        self._provider_lock = threading.RLock()
        self._config_service = get_config_service()
        self._event_bus = get_event_bus()
        
        # Provider管理
        self._current_provider: Optional[AIProvider] = None
        self._current_config_hash: Optional[str] = None
        
        # 统计信息
        self._total_calls = 0
        self._total_errors = 0
        self._provider_switch_count = 0
        
        # 订阅配置变更事件
        self._subscribe_config_changes()
        
        self._initialized = True
        logger.info("AIServiceManager初始化完成")
    
    def _subscribe_config_changes(self):
        """订阅配置变更事件"""
        def on_config_changed(event_data):
            logger.info(f"收到配置变更事件: {event_data}")
            self._reload_provider()
        
        self._event_bus.subscribe("config.changed", on_config_changed)
        logger.info("已订阅配置变更事件")
    
    def _calculate_config_hash(self, config: Dict[str, Any]) -> str:
        """
        计算配置哈希值
        
        Args:
            config: 配置字典
            
        Returns:
            str: 配置哈希值
        """
        # 只计算影响Provider选择的配置项
        hash_keys = [
            "service_mode",
            "provider",
            "model",
            "api_key",
            "base_url",
            "local_url",
            "temperature",
        ]
        hash_dict = {k: config.get(k, "") for k in hash_keys}
        hash_str = str(sorted(hash_dict.items()))
        return hashlib.md5(hash_str.encode()).hexdigest()
    
    def _reload_provider(self) -> None:
        """
        根据最新配置重新创建Provider
        
        设计原则：
        - 配置哈希检查：避免无变化时重建
        - 线程安全：使用锁保护Provider创建
        - 错误处理：创建失败时保留旧Provider
        """
        with self._provider_lock:
            try:
                # 获取AI配置
                config = self._get_ai_config()
                new_hash = self._calculate_config_hash(config)
                
                # 检查配置是否变化
                if new_hash == self._current_config_hash:
                    logger.debug("配置未变化，跳过Provider重建")
                    return
                
                logger.info(f"检测到配置变化，准备重新创建Provider")
                
                # 创建新Provider
                old_provider = self._current_provider
                new_provider = self._create_provider(config)
                
                # 验证新Provider是否可用
                if not new_provider.is_available():
                    logger.warning("新Provider不可用，保留旧Provider")
                    raise AIProviderUnavailableError(
                        "新创建的Provider不可用",
                        provider=new_provider.__class__.__name__
                    )
                
                # 切换Provider
                self._current_provider = new_provider
                self._current_config_hash = new_hash
                self._provider_switch_count += 1
                
                # 发布Provider切换事件
                self._event_bus.publish(
                    "ai.provider.changed",
                    {
                        "mode": config.get("service_mode", "online"),
                        "provider": config.get("provider", "unknown"),
                        "model": config.get("model", "unknown"),
                        "switch_count": self._provider_switch_count,
                    }
                )
                
                logger.info(
                    f"Provider切换成功: {new_provider.__class__.__name__} "
                    f"(累计切换{self._provider_switch_count}次)"
                )
                
            except Exception as e:
                logger.error(f"重新加载Provider失败: {e}", exc_info=True)
                # 发布错误事件
                self._event_bus.publish(
                    "ai.provider.error",
                    {
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )
    
    def _get_ai_config(self) -> Dict[str, Any]:
        """
        获取AI配置
        
        Returns:
            Dict[str, Any]: AI配置字典
        """
        # 从ConfigService获取配置
        config = self._config_service.get_all()
        
        # 构建AI配置
        ai_config = {
            "service_mode": config.get("service_mode", "remote"),
            "provider": config.get("provider", "DeepSeek"),
            "model": config.get("model", "deepseek-chat"),
            "api_key": config.get("api_key", ""),
            "temperature": config.get("temperature", 0.7),
        }
        
        # 读取base_url（优先级：deepseek.base_url > base_url > local_url）
        if "deepseek" in config and isinstance(config["deepseek"], dict):
            ai_config["base_url"] = config["deepseek"].get("base_url", "https://api.deepseek.com")
        elif "base_url" in config:
            ai_config["base_url"] = config["base_url"]
        else:
            ai_config["base_url"] = config.get("local_url", "http://localhost:11434/v1")
        
        # 如果有嵌套的local配置，也读取
        local_config = config.get("local", {})
        if local_config:
            ai_config["local"] = local_config
        
        return ai_config
    
    def _create_provider(self, config: Dict[str, Any]) -> AIProvider:
        """
        根据配置创建Provider
        
        Args:
            config: 配置字典
            
        Returns:
            AIProvider: Provider实例
            
        Raises:
            AIProviderError: 创建失败
        """
        service_mode = config.get("service_mode", "local")
        
        if service_mode == "online" or service_mode == "remote":
            # 线上API模式
            provider = self._create_online_provider(config)
        else:
            # 本地模型模式
            provider = self._create_local_provider(config)
        
        logger.info(
            f"创建Provider成功: {provider.__class__.__name__} "
            f"(mode={service_mode})"
        )
        return provider
    
    def _create_online_provider(self, config: Dict[str, Any]) -> AIProvider:
        """
        创建线上Provider
        
        Args:
            config: 配置字典
            
        Returns:
            AIProvider: 线上Provider实例
        """
        # 延迟导入避免循环依赖
        try:
            from .online_provider import OnlineProvider
            return OnlineProvider(config)
        except ImportError as e:
            logger.error(f"导入OnlineProvider失败: {e}")
            raise AIProviderError(
                "OnlineProvider未实现",
                provider="OnlineProvider",
                original_error=e
            )
    
    def _create_local_provider(self, config: Dict[str, Any]) -> AIProvider:
        """
        创建本地Provider
        
        Args:
            config: 配置字典
            
        Returns:
            AIProvider: 本地Provider实例
        """
        provider_name = config.get("provider", "").lower()
        
        # 根据provider类型选择对应的Provider类
        if provider_name == "qwen":
            # Qwen本地模型（F:\Qwen）
            try:
                from .qwen_provider import QwenProvider
                logger.info("使用QwenProvider（本地Qwen模型）")
                return QwenProvider(config)
            except ImportError as e:
                logger.error(f"导入QwenProvider失败: {e}")
                raise AIProviderError(
                    "QwenProvider未实现",
                    provider="QwenProvider",
                    original_error=e
                )
        else:
            # 默认使用LocalProvider（Ollama/llama.cpp/vLLM/LocalAI）
            try:
                from .local_provider import LocalProvider
                logger.info("使用LocalProvider（通用本地框架）")
                return LocalProvider(config)
            except ImportError as e:
                logger.error(f"导入LocalProvider失败: {e}")
                raise AIProviderError(
                    "LocalProvider未实现",
                    provider="LocalProvider",
                    original_error=e
                )
    
    def get_provider(self) -> AIProvider:
        """
        获取当前AIProvider实例（自动按需初始化）
        
        Returns:
            AIProvider: 当前Provider实例
            
        Raises:
            AIProviderError: Provider未初始化或不可用
        """
        with self._provider_lock:
            if self._current_provider is None:
                logger.info("Provider未初始化，自动加载")
                self._reload_provider()
            
            if self._current_provider is None:
                raise AIProviderUnavailableError(
                    "无法获取可用的AIProvider",
                    provider="AIServiceManager"
                )
            
            return self._current_provider
    
    # ==================== 对外暴露的便捷方法（直接透传给Provider）====================
    
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
            **kwargs: 其他参数
            
        Returns:
            GenerationResult: 生成结果
        """
        self._total_calls += 1
        try:
            return self.get_provider().generate_text(prompt, config, **kwargs)
        except Exception as e:
            self._total_errors += 1
            logger.error(f"生成文本失败: {e}", exc_info=True)
            raise
    
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
            callback: 回调函数
            config: 生成配置（可选）
            **kwargs: 其他参数
            
        Returns:
            GenerationResult: 最终生成结果
        """
        self._total_calls += 1
        try:
            return self.get_provider().generate_text_stream(prompt, callback, config, **kwargs)
        except Exception as e:
            self._total_errors += 1
            logger.error(f"流式生成失败: {e}", exc_info=True)
            raise
    
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
            analysis_type: 分析类型
            config: 生成配置（可选）
            **kwargs: 其他参数
            
        Returns:
            Dict[str, Any]: 分析结果
        """
        self._total_calls += 1
        try:
            return self.get_provider().analyze_text(text, analysis_type, config, **kwargs)
        except Exception as e:
            self._total_errors += 1
            logger.error(f"文本分析失败: {e}", exc_info=True)
            raise
    
    def estimate_tokens(self, text: str) -> int:
        """
        估算token数
        
        Args:
            text: 文本内容
            
        Returns:
            int: 估算的token数
        """
        return self.get_provider().estimate_tokens(text)
    
    def get_model_info(self) -> AIModelInfo:
        """
        获取模型信息
        
        Returns:
            AIModelInfo: 模型信息
        """
        return self.get_provider().get_model_info()
    
    def is_available(self) -> bool:
        """
        检查服务是否可用
        
        Returns:
            bool: 是否可用
        """
        try:
            return self.get_provider().is_available()
        except Exception:
            return False
    
    # ==================== 管理方法 ====================
    
    def reload_provider(self) -> bool:
        """
        强制重新加载Provider
        
        Returns:
            bool: 是否成功
        """
        try:
            # 清除配置哈希，强制重建
            with self._provider_lock:
                self._current_config_hash = None
            
            self._reload_provider()
            return True
        except Exception as e:
            logger.error(f"强制重新加载Provider失败: {e}", exc_info=True)
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息（P1-4修复：添加持久化）
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        from datetime import datetime
        
        with self._provider_lock:
            provider_name = (
                self._current_provider.__class__.__name__ 
                if self._current_provider else "None"
            )
            
            stats = {
                "provider": provider_name,
                "provider_state": (
                    self._current_provider.get_state().value 
                    if self._current_provider else "none"
                ),
                "total_calls": self._total_calls,
                "total_errors": self._total_errors,
                "error_rate": (
                    self._total_errors / self._total_calls 
                    if self._total_calls > 0 else 0
                ),
                "provider_switch_count": self._provider_switch_count,
                "config_hash": self._current_config_hash,
                "timestamp": datetime.now().isoformat(),
            }
        
        # P1-4修复：持久化到数据库
        try:
            from .database import get_database
            db = get_database()
            # 保存到ai_stats表（如果存在）
            if hasattr(db, 'save_ai_stats'):
                db.save_ai_stats(stats)
        except Exception as e:
            logger.warning(f"保存AI统计信息失败: {e}")
        
        return stats
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            Dict[str, Any]: 健康状态信息
        """
        health = {
            "service_manager": "healthy",
            "provider": "unknown",
            "available": False,
            "stats": self.get_stats(),
        }
        
        try:
            provider = self.get_provider()
            health["provider"] = provider.health_check()
            health["available"] = provider.is_available()
        except Exception as e:
            health["error"] = str(e)
        
        return health


# 全局单例实例
_ai_service_manager_instance: Optional[AIServiceManager] = None
_ai_service_manager_lock = threading.Lock()


def get_ai_service_manager() -> AIServiceManager:
    """
    获取全局AIServiceManager实例
    
    Returns:
        AIServiceManager: AI服务管理器实例
    """
    global _ai_service_manager_instance
    if _ai_service_manager_instance is None:
        with _ai_service_manager_lock:
            if _ai_service_manager_instance is None:
                _ai_service_manager_instance = AIServiceManager()
    return _ai_service_manager_instance
