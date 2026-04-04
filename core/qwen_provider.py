"""
QwenProvider - 封装本地Qwen模型服务（项目内Qwen目录）

V1.1版本
创建日期：2026-03-28
更新日期：2026-04-04

设计目标：
- 支持项目内Qwen目录部署的Qwen2.5-14B-GPTQ-Int4模型
- 兼容OpenAI API格式（v1/chat/completions）
- 复用LocalProvider的容错机制
- 支持传统/chat接口和OpenAI兼容接口

架构角色：
- 实现层：继承LocalProvider
- 服务层：被AIServiceManager调用
"""

import threading
import time
import json
import logging
import requests
from typing import Any, Callable, Dict, Iterator, List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import random
import re

from .ai_provider import (
    AIProvider,
    AIProviderState,
    AIProviderError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    AIProviderConfigError,
    GenerationConfig,
    GenerationResult,
    AIModelInfo,
    AIProviderType,
)
from .circuit_breaker import CircuitBreaker, CircuitState, get_circuit_breaker_manager
from .local_provider import LocalProvider, LocalRetryPolicy

logger = logging.getLogger(__name__)


# ============================================================================
# Qwen模型配置
# ============================================================================

QWEN_MODEL_CONFIGS = {
    "qwen2.5-14b-gptq": {
        "max_tokens": 4096,
        "supports_streaming": True,
        "supports_vision": False,
        "description": "Qwen2.5-14B-GPTQ-Int4（4-bit量化，8GB显存）",
    },
    "qwen2.5-7b": {
        "max_tokens": 4096,
        "supports_streaming": True,
        "supports_vision": False,
        "description": "Qwen2.5-7B-Instruct（FP16，14GB显存）",
    },
}


# ============================================================================
# QwenProvider实现
# ============================================================================

class QwenProvider(LocalProvider):
    """
    Qwen本地模型提供者
    
    支持项目内Qwen目录部署的Qwen2.5-14B-GPTQ-Int4模型
    
    核心特性：
    1. OpenAI兼容API（/v1/chat/completions）
    2. 传统API（/chat?msg=xxx）
    3. 四级容错机制
    4. 流式生成支持
    
    使用方式：
    ```yaml
    # config.yaml
    service_mode: local
    provider: Qwen
    model: qwen2.5-14b-gptq
    local_url: http://localhost:8000
    
    # 启动Qwen服务
    cd Qwen && python start_server_v2.py
    ```
    """
    
    # Qwen服务端点
    QWEN_ENDPOINTS = {
        "chat": "/chat",
        "completions": "/v1/completions",
        "chat_completions": "/v1/chat/completions",
        "models": "/v1/models",
        "health": "/health",
    }
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化QwenProvider

        Args:
            config: 配置字典，应包含：
                - endpoint: API端点URL（默认 http://localhost:8000）
                - model: 模型名称（默认 qwen2.5-14b-gptq）
                - temperature: 温度参数（可选，默认0.7）
                - timeout: 超时时间（可选，默认120秒）
                - auto_start_service: 是否自动启动服务（默认True）
        """
        # 设置默认配置
        config.setdefault("framework", "qwen")
        config.setdefault("endpoint", "http://localhost:8000")
        config.setdefault("model", "qwen2.5-14b-gptq")
        config.setdefault("auto_start_service", True)  # 新增：自动启动服务

        # 调用父类初始化
        super().__init__(config)

        # Qwen特有配置
        self._qwen_model = config.get("model", "qwen2.5-14b-gptq")
        self._use_openai_api = config.get("use_openai_api", True)
        self._auto_start_service = config.get("auto_start_service", True)

        # 更新框架配置
        self._framework_config = {
            "default_endpoint": self._endpoint,
            "api_path": "",
            "generate_endpoint": "/v1/completions",
            "chat_endpoint": "/v1/chat/completions",
            "models_endpoint": "/v1/models",
            "supports_streaming": True,
            "supports_chat": True,
            "default_model": self._qwen_model,
            "models": QWEN_MODEL_CONFIGS,
        }

        # 测试连接，如果失败且启用自动启动，则尝试启动服务
        if not self._test_qwen_connection():
            if self._auto_start_service:
                logger.info("Qwen服务未运行，尝试自动启动...")
                self._start_qwen_service()

        logger.info(
            f"QwenProvider初始化: model={self._qwen_model}, "
            f"endpoint={self._endpoint}, use_openai_api={self._use_openai_api}"
        )
    
    def _test_connection(self) -> bool:
        """重写连接测试，使用Qwen的health端点"""
        return self._test_qwen_connection()
    
    def _test_qwen_connection(self) -> bool:
        """
        测试Qwen服务连接
        
        Returns:
            连接是否成功
        """
        try:
            url = f"{self._endpoint}{self.QWEN_ENDPOINTS['health']}"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(
                    f"Qwen服务连接成功: model_loaded={data.get('model_loaded', False)}"
                )
                return data.get("model_loaded", True)
            else:
                logger.warning(f"Qwen服务返回状态码: {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            error_msg = (
                f"无法连接到本地Qwen服务: {self._endpoint}\n"
                f"请先启动本地大模型服务：\n"
                f"  1. 打开命令行窗口\n"
                f"  2. cd F:\\Qwen\n"
                f"  3. python start_server_v2.py\n"
                f"启动后等待'服务已就绪'提示，然后重试。"
            )
            logger.error(error_msg)
            # 不抛出异常，让程序继续运行，用户会看到错误提示
            # V3.2.2修复：AIProviderState没有UNAVAILABLE，使用ERROR代替
            self._state = AIProviderState.ERROR
            return False
        except Exception as e:
            logger.warning(f"Qwen服务连接测试异常: {e}")
            self._state = AIProviderState.ERROR
            return False

    def _start_qwen_service(self) -> bool:
        """
        启动Qwen服务（通过LocalServicePlugin）

        Returns:
            服务是否启动成功
        """
        try:
            # 尝试通过ServiceLocator获取LocalServicePlugin实例
            try:
                from core.service_locator import ServiceLocator
                local_service = ServiceLocator.get_service("local_service_plugin")

                if local_service:
                    result = local_service.start_service("qwen")

                    if result.get("success"):
                        logger.info(f"Qwen服务启动成功: {result.get('message')}")
                        # 重新测试连接
                        return self._test_qwen_connection()
                    else:
                        logger.error(f"Qwen服务启动失败: {result.get('message')}")
                        return False
            except Exception:
                # ServiceLocator中未注册，尝试直接加载插件
                logger.info("LocalServicePlugin未在ServiceLocator中注册，尝试直接加载...")

                # 导入插件
                import sys
                from pathlib import Path
                plugin_path = Path(__file__).parent.parent / "plugins" / "local-service-v1"

                if str(plugin_path) not in sys.path:
                    sys.path.insert(0, str(plugin_path))

                from plugin import LocalServicePlugin

                # 创建插件实例
                from plugins.plugin_types import ToolPlugin
                from plugins.base_plugin import PluginContext

                plugin = LocalServicePlugin()
                context = PluginContext(
                    plugin_id="local-service-v1",
                    config={
                        "qwen_service_path": "F:\\Qwen\\start_server_v2.py",
                        "qwen_endpoint": self._endpoint,
                        "auto_start_on_demand": True,
                        "auto_stop_on_exit": True
                    }
                )

                # 初始化插件
                if plugin.initialize(context):
                    # 启动服务
                    result = plugin.start_service("qwen")

                    if result.get("success"):
                        logger.info(f"Qwen服务启动成功: {result.get('message')}")

                        # 注册到ServiceLocator以便后续使用
                        try:
                            ServiceLocator.get_instance().register_named(
                                "local_service_plugin",
                                plugin
                            )
                        except Exception:
                            pass  # 忽略注册失败

                        # 重新测试连接
                        return self._test_qwen_connection()
                    else:
                        logger.error(f"Qwen服务启动失败: {result.get('message')}")
                        return False
                else:
                    logger.error("LocalServicePlugin初始化失败")
                    return False

        except Exception as e:
            logger.error(f"启动Qwen服务失败: {e}", exc_info=True)
            return False

    def _build_request_payload(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> Dict[str, Any]:
        """
        构建OpenAI兼容的请求payload
        
        Args:
            prompt: 用户输入
            system_prompt: 系统提示词
            config: 生成配置
            
        Returns:
            OpenAI格式的请求字典
        """
        # 构建messages
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        # 构建payload
        payload = {
            "model": self._qwen_model,
            "messages": messages,
            "max_tokens": config.max_tokens if config else 512,
            "temperature": config.temperature if config else self._temperature,
            "top_p": config.top_p if config else 0.9,
            "stream": False,
        }
        
        return payload
    
    def _parse_response(self, response: Dict[str, Any]) -> str:
        """
        解析OpenAI格式的响应
        
        Args:
            response: API响应字典
            
        Returns:
            生成的文本
        """
        try:
            # OpenAI格式: {"choices": [{"message": {"content": "..."}}]}
            choices = response.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                return message.get("content", "")
            
            # 传统格式: {"response": "..."}
            if "response" in response:
                return response["response"]
            
            logger.warning(f"未知的响应格式: {list(response.keys())}")
            return ""
            
        except Exception as e:
            logger.error(f"解析响应失败: {e}")
            return ""
    
    def _call_api(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        调用Qwen API
        
        优先使用OpenAI兼容API，失败则降级到传统API
        
        Args:
            prompt: 用户输入
            system_prompt: 系统提示词
            config: 生成配置
            stream: 是否流式生成
            
        Returns:
            API响应字典
        """
        if self._use_openai_api:
            try:
                # 尝试OpenAI兼容API
                return self._call_openai_api(prompt, system_prompt, config, stream)
            except Exception as e:
                logger.warning(f"OpenAI API调用失败，降级到传统API: {e}")
                return self._call_traditional_api(prompt, config)
        else:
            return self._call_traditional_api(prompt, config)
    
    def _call_openai_api(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        调用OpenAI兼容API
        
        Args:
            prompt: 用户输入
            system_prompt: 系统提示词
            config: 生成配置
            stream: 是否流式生成
            
        Returns:
            OpenAI格式的响应字典
        """
        url = f"{self._endpoint}{self.QWEN_ENDPOINTS['chat_completions']}"
        payload = self._build_request_payload(prompt, system_prompt, config)
        payload["stream"] = stream
        
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self._timeout
        )
        
        if response.status_code != 200:
            raise AIProviderError(
                f"Qwen API返回错误: {response.status_code}",
                provider="qwen"
            )
        
        return response.json()
    
    def _call_traditional_api(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None
    ) -> Dict[str, Any]:
        """
        调用传统/chat API
        
        Args:
            prompt: 用户输入
            config: 生成配置
            
        Returns:
            传统格式的响应字典
        """
        params = {
            "msg": prompt,
            "max_tokens": config.max_tokens if config else 512,
            "temperature": config.temperature if config else self._temperature,
        }
        
        url = f"{self._endpoint}{self.QWEN_ENDPOINTS['chat']}"
        response = requests.get(url, params=params, timeout=self._timeout)
        
        if response.status_code != 200:
            raise AIProviderError(
                f"Qwen传统API返回错误: {response.status_code}",
                provider="qwen"
            )
        
        return response.json()
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> GenerationResult:
        """
        同步生成文本
        
        Args:
            prompt: 用户输入
            system_prompt: 系统提示词
            config: 生成配置
            
        Returns:
            GenerationResult对象
        """
        start_time = time.time()
        
        try:
            # 检查熔断器
            if self._circuit_breaker and self._circuit_breaker.state == CircuitState.OPEN:
                raise AIProviderUnavailableError(
                    "Qwen服务熔断中",
                    provider="qwen"
                )
            
            # 调用API
            response = self._call_api(prompt, system_prompt, config)
            
            # 解析响应
            text = self._parse_response(response)
            
            # 更新熔断器
            if self._circuit_breaker:
                self._circuit_breaker.record_success()
            
            # 构建结果
            elapsed = time.time() - start_time
            usage = response.get("usage", {})
            
            result = GenerationResult(
                success=True,
                text=text,
                provider="qwen",
                model=self._qwen_model,
                latency_ms=int(elapsed * 1000),
                finish_reason="stop",
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
            )
            
            self._total_requests += 1
            logger.info(f"Qwen生成成功: elapsed={elapsed:.2f}s, tokens={result.usage.get('total_tokens', 0)}")
            
            return result
            
        except Exception as e:
            self._total_errors += 1
            
            # 更新熔断器
            if self._circuit_breaker:
                self._circuit_breaker.record_failure()
            
            elapsed = time.time() - start_time
            
            return GenerationResult(
                success=False,
                text="",
                provider="qwen",
                model=self._qwen_model,
                latency_ms=int(elapsed * 1000),
                finish_reason="error",
                usage={},
                error=str(e),
            )
    
    def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> Iterator[str]:
        """
        流式生成文本
        
        注意：当前实现为模拟流式，实际返回完整文本
        
        Args:
            prompt: 用户输入
            system_prompt: 系统提示词
            config: 生成配置
            
        Yields:
            文本片段
        """
        # Qwen服务支持SSE流式，但实现复杂
        # 这里简化为一次性返回
        result = self.generate(prompt, system_prompt, config)
        
        if result.success:
            # 简单的分段输出模拟流式
            chunk_size = 20
            text = result.text
            for i in range(0, len(text), chunk_size):
                yield text[i:i+chunk_size]
                time.sleep(0.05)
        else:
            raise AIProviderError(result.error, provider="qwen")
    
    def get_model_info(self) -> AIModelInfo:
        """
        获取模型信息
        
        Returns:
            AIModelInfo对象
        """
        model_config = QWEN_MODEL_CONFIGS.get(self._qwen_model, {})
        
        return AIModelInfo(
            provider_type=AIProviderType.LOCAL,
            provider_name="Qwen",
            model_name=self._qwen_model,
            max_tokens=model_config.get("max_tokens", 4096),
            supports_streaming=model_config.get("supports_streaming", True),
            supports_vision=model_config.get("supports_vision", False),
            metadata={
                "description": model_config.get("description", "Qwen本地模型"),
                "endpoint": self._endpoint,
            }
        )
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            健康状态字典
        """
        is_healthy = self._test_qwen_connection()
        
        return {
            "provider": "qwen",
            "model": self._qwen_model,
            "endpoint": self._endpoint,
            "healthy": is_healthy,
            "state": self._state.value,
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
        }


# ============================================================================
# 工厂函数
# ============================================================================

def create_qwen_provider(config: Dict[str, Any]) -> QwenProvider:
    """
    创建QwenProvider实例
    
    Args:
        config: 配置字典
        
    Returns:
        QwenProvider实例
    """
    return QwenProvider(config)
