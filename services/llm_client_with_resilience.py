"""
LLM客户端容错模块

V2.0版本
创建日期: 2026-03-21

特性:
- 四级容错机制（重试→熔断→降级→缓存回退）
- 多模型回退
- 请求缓存
"""

from typing import Dict, Any, Optional, List
from enum import Enum
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from core.circuit_breaker import CircuitBreaker
from agents.retry_manager import RetryManager, RetryConfig, RetryPolicy

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """LLM提供商"""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class LLMClientWithResilience:
    """
    带容错机制的LLM客户端
    
    实现四级容错:
    1. 请求重试（指数退避 + 抖动）
    2. 熔断器（快速失败 + 半开恢复）
    3. 模型降级（切换到备用模型）
    4. 缓存回退（返回历史结果或默认值）
    """
    
    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str,
        base_url: str = None
    ):
        """
        初始化LLM客户端
        
        Args:
            provider: 提供商（deepseek/openai/anthropic/ollama）
            model: 模型名称
            api_key: API密钥
            base_url: 基础URL（可选）
        """
        self._provider = provider
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        
        # 初始化容错组件
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            half_open_max_calls=3
        )
        self._retry_manager = RetryManager(RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            max_delay=30.0,
            policy=RetryPolicy.EXPONENTIAL
        ))
        
        # 备用模型列表（降级策略）
        self._fallback_models = self._get_fallback_models()
        
        # 请求缓存
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 3600  # 1小时
        
        # 实际客户端（延迟初始化）
        self._client = None
        self._executor = ThreadPoolExecutor(max_workers=5)
    
    def _get_fallback_models(self) -> List[str]:
        """获取备用模型列表"""
        fallback_map = {
            "deepseek": ["deepseek-chat"],
            "openai": ["gpt-3.5-turbo", "gpt-4"],
            "anthropic": ["claude-3-haiku", "claude-3-sonnet"],
            "ollama": ["llama3", "mistral"],
        }
        return fallback_map.get(self._provider, [])
    
    def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        timeout: int = 30,
        **kwargs
    ) -> str:
        """
        生成文本（带容错）
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            timeout: 超时时间（秒）
            **kwargs: 额外参数
            
        Returns:
            生成的文本
            
        Raises:
            Exception: 所有容错机制均失败
        """
        # 尝试主模型
        try:
            result = self._try_generate(
                self._model,
                prompt,
                system_prompt,
                timeout,
                **kwargs
            )
            return result
        
        except Exception as e:
            logger.warning(f"主模型生成失败: {e}，尝试备用模型")
            
            # 尝试备用模型
            for fallback_model in self._fallback_models:
                try:
                    result = self._try_generate(
                        fallback_model,
                        prompt,
                        system_prompt,
                        timeout,
                        **kwargs
                    )
                    logger.info(f"备用模型 {fallback_model} 生成成功")
                    return result
                
                except Exception as fallback_e:
                    logger.warning(
                        f"备用模型 {fallback_model} 生成失败: {fallback_e}"
                    )
            
            # 所有模型都失败，尝试缓存回退
            cached = self._get_cached_result(prompt)
            if cached:
                logger.info("返回缓存结果")
                return cached
            
            # 彻底失败
            raise Exception(f"所有模型生成均失败: {e}")
    
    def _try_generate(
        self,
        model: str,
        prompt: str,
        system_prompt: str = None,
        timeout: int = 30,
        **kwargs
    ) -> str:
        """
        尝试生成（单次尝试）
        
        Args:
            model: 模型名称
            prompt: 提示词
            system_prompt: 系统提示词
            timeout: 超时时间
            **kwargs: 额外参数
            
        Returns:
            生成的文本
            
        Raises:
            Exception: 生成失败
        """
        def _call_llm():
            return self._circuit_breaker.call(
                self._raw_generate,
                model,
                prompt,
                system_prompt,
                **kwargs
            )
        
        # 使用重试管理器
        result, retry_count = self._retry_manager.execute_with_retry(_call_llm)
        
        # 缓存结果
        self._cache_result(prompt, result)
        
        logger.info(f"LLM生成成功，重试次数: {retry_count}")
        return result
    
    def _raw_generate(
        self,
        model: str,
        prompt: str,
        system_prompt: str = None,
        **kwargs
    ) -> str:
        """
        原始生成调用（无容错）
        
        Args:
            model: 模型名称
            prompt: 提示词
            system_prompt: 系统提示词
            **kwargs: 额外参数
            
        Returns:
            生成的文本
        """
        # 延迟初始化客户端
        if self._client is None:
            self._client = self._create_client()
        
        # 构建消息
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # 调用API
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )
        
        return response.choices[0].message.content
    
    def _create_client(self):
        """创建OpenAI兼容客户端"""
        from openai import OpenAI
        
        client_kwargs = {"api_key": self._api_key}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url
        
        return OpenAI(**client_kwargs)
    
    def _cache_result(self, prompt: str, result: str) -> None:
        """缓存结果"""
        from datetime import datetime, timezone
        import hashlib
        
        cache_key = hashlib.md5(prompt.encode()).hexdigest()
        self._cache[cache_key] = {
            "result": result,
            "timestamp": datetime.now(timezone.utc)
        }
    
    def _get_cached_result(self, prompt: str) -> Optional[str]:
        """获取缓存结果"""
        from datetime import datetime, timezone
        import hashlib
        
        cache_key = hashlib.md5(prompt.encode()).hexdigest()
        
        if cache_key not in self._cache:
            return None
        
        cached = self._cache[cache_key]
        age = (datetime.now(timezone.utc) - cached["timestamp"]).total_seconds()
        
        # 检查是否过期
        if age > self._cache_ttl:
            del self._cache[cache_key]
            return None
        
        return cached["result"]
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            健康状态信息
        """
        try:
            test_prompt = "你好"
            self.generate(test_prompt, max_tokens=10)
            
            return {
                "provider": self._provider,
                "model": self._model,
                "status": "healthy",
                "circuit_breaker": {
                    "state": self._circuit_breaker.state.value,
                    "failure_count": self._circuit_breaker.failure_count
                }
            }
        except Exception as e:
            return {
                "provider": self._provider,
                "model": self._model,
                "status": "unhealthy",
                "error": str(e),
                "circuit_breaker": {
                    "state": self._circuit_breaker.state.value,
                    "failure_count": self._circuit_breaker.failure_count
                }
            }
    
    def cleanup(self) -> None:
        """清理资源"""
        self._executor.shutdown(wait=True, cancel_futures=False)
        self._cache.clear()
