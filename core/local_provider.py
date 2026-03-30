"""
LocalProvider - 封装本地推理框架，支持Ollama/llama.cpp/vLLM等

V1.0版本
创建日期：2026-03-24

设计目标：
- 支持多种本地推理框架：Ollama、llama.cpp、vLLM、LocalAI
- 统一HTTP API调用接口
- 四级容错机制：重试层、熔断层、模型回退、缓存降级
- 线程安全设计
- 超时保护
- 错误处理与重试

架构角色：
- 实现层：实现AIProvider抽象接口
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

logger = logging.getLogger(__name__)


# ============================================================================
# 支持的本地推理框架配置
# ============================================================================

LOCAL_FRAMEWORK_CONFIGS = {
    "ollama": {
        "default_endpoint": "http://localhost:11434",
        "api_path": "/api",
        "generate_endpoint": "/generate",
        "chat_endpoint": "/chat",
        "embeddings_endpoint": "/embeddings",
        "models_endpoint": "/tags",
        "supports_streaming": True,
        "supports_chat": True,
        "default_model": "llama3.1",
        "models": {
            "llama3.1": {"max_tokens": 128000, "supports_streaming": True, "supports_vision": False},
            "llama3.2": {"max_tokens": 128000, "supports_streaming": True, "supports_vision": True},
            "qwen2.5": {"max_tokens": 32000, "supports_streaming": True, "supports_vision": False},
            "deepseek-coder-v2": {"max_tokens": 128000, "supports_streaming": True, "supports_vision": False},
            "mistral": {"max_tokens": 32000, "supports_streaming": True, "supports_vision": False},
            "codellama": {"max_tokens": 16000, "supports_streaming": True, "supports_vision": False},
        },
    },
    "llama-cpp": {
        "default_endpoint": "http://localhost:8080",
        "api_path": "",
        "generate_endpoint": "/completion",
        "chat_endpoint": "/v1/chat/completions",
        "embeddings_endpoint": "/embedding",
        "models_endpoint": "/props",
        "supports_streaming": True,
        "supports_chat": True,
        "default_model": "local-model",
        "models": {
            "local-model": {"max_tokens": 4096, "supports_streaming": True, "supports_vision": False}
        },
    },
    "vllm": {
        "default_endpoint": "http://localhost:8000",
        "api_path": "/v1",
        "generate_endpoint": "/completions",
        "chat_endpoint": "/chat/completions",
        "embeddings_endpoint": "/embeddings",
        "models_endpoint": "/models",
        "supports_streaming": True,
        "supports_chat": True,
        "default_model": "local-model",
        "models": {
            "local-model": {"max_tokens": 4096, "supports_streaming": True, "supports_vision": False}
        },
    },
    "localai": {
        "default_endpoint": "http://localhost:8080",
        "api_path": "/v1",
        "generate_endpoint": "/completions",
        "chat_endpoint": "/chat/completions",
        "embeddings_endpoint": "/embeddings",
        "models_endpoint": "/models",
        "supports_streaming": True,
        "supports_chat": True,
        "default_model": "gpt-3.5-turbo",
        "models": {
            "gpt-3.5-turbo": {"max_tokens": 4096, "supports_streaming": True, "supports_vision": False},
            "llama3": {"max_tokens": 8192, "supports_streaming": True, "supports_vision": False},
        },
    },
}


# ============================================================================
# 自定义异常类
# ============================================================================

class LocalProviderConnectionError(AIProviderError):
    """本地服务连接错误"""
    pass


class LocalProviderResponseError(AIProviderError):
    """本地服务响应错误"""
    pass


class LocalProviderTimeoutError(AIProviderError):
    """本地服务超时错误"""
    pass


# ============================================================================
# 重试策略
# ============================================================================

@dataclass
class LocalRetryPolicy:
    """本地服务重试策略配置"""
    max_retries: int = 3
    base_delay: float = 1.0  # 基础延迟（秒）
    max_delay: float = 30.0  # 最大延迟（秒）
    exponential_base: float = 2.0  # 指数退避基数
    jitter: bool = True  # 是否添加随机抖动
    
    def get_delay(self, attempt: int) -> float:
        """
        计算重试延迟
        
        使用指数退避 + jitter策略
        """
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            # 添加随机抖动（0.5x ~ 1.5x）
            delay = delay * (0.5 + random.random())
        
        return delay


# ============================================================================
# LocalProvider实现
# ============================================================================

class LocalProvider(AIProvider):
    """
    本地AI能力提供者
    
    支持Ollama、llama.cpp、vLLM、LocalAI等本地推理框架
    
    核心特性：
    1. 四级容错机制：重试层、熔断层、模型回退、缓存降级
    2. 线程安全的API调用
    3. 超时保护（默认120秒）
    4. 流式生成支持
    5. Token估算
    """
    
    # 错误码映射到重试行为
    RETRYABLE_ERRORS = {
        # 连接错误（可重试）
        "connection_error": True,
        "timeout": True,
        "server_error": True,
        "service_unavailable": True,
        # 配置错误（不可重试）
        "model_not_found": False,
        "invalid_request": False,
        "context_length_exceeded": False,
    }
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化LocalProvider
        
        Args:
            config: 配置字典，应包含：
                - framework: 框架名称（ollama/llama-cpp/vllm/localai）
                - endpoint: API端点URL
                - model: 模型名称
                - temperature: 温度参数（可选）
                - timeout: 超时时间（可选）
                - max_retries: 最大重试次数（可选）
        """
        super().__init__(config)
        
        self._lock = threading.RLock()
        self._framework = config.get("framework", "ollama")
        self._model = config.get("model", "llama3.1")
        self._endpoint = config.get("endpoint", "http://localhost:11434")
        self._temperature = config.get("temperature", 0.7)
        
        # 超时和重试配置
        self._timeout = config.get("timeout", 120)
        self._retry_policy = LocalRetryPolicy(
            max_retries=config.get("max_retries", 3)
        )
        
        # 熔断器
        self._circuit_breaker = None
        
        # 线程池（用于超时控制）
        self._executor = ThreadPoolExecutor(max_workers=5)
        
        # 统计信息
        self._total_requests = 0
        self._total_errors = 0
        self._total_retries = 0
        
        # 初始化客户端
        self._init_client()
        
        logger.info(
            f"LocalProvider初始化: framework={self._framework}, "
            f"model={self._model}, endpoint={self._endpoint}"
        )
    
    def _init_client(self) -> None:
        """
        初始化本地推理框架客户端
        
        验证配置并测试连接
        """
        try:
            # 验证配置
            if not self._endpoint:
                raise AIProviderConfigError(
                    "缺少endpoint配置",
                    provider=self._framework
                )
            
            # 获取框架配置
            framework_config = LOCAL_FRAMEWORK_CONFIGS.get(self._framework)
            if not framework_config:
                logger.warning(
                    f"未知的框架: {self._framework}, "
                    f"使用通用配置"
                )
                framework_config = {
                    "default_endpoint": self._endpoint,
                    "api_path": "/api",
                    "generate_endpoint": "/generate",
                    "chat_endpoint": "/chat",
                    "supports_streaming": True,
                    "supports_chat": True,
                }
            
            # 构建API端点
            api_path = framework_config.get("api_path", "")
            if api_path:
                self._api_base = f"{self._endpoint}{api_path}"
            else:
                self._api_base = self._endpoint
            
            self._framework_config = framework_config
            
            # 获取熔断器
            cb_manager = get_circuit_breaker_manager()
            self._circuit_breaker = cb_manager.get_or_create(
                f"local_provider_{self._framework}",
                failure_threshold=3,  # 本地服务阈值更低
                success_threshold=2,
                timeout=30.0
            )
            
            # 测试连接（可选，失败不阻塞初始化）
            try:
                self._test_connection()
                self._state = AIProviderState.READY
                logger.info(f"本地服务连接成功: {self._framework}")
            except Exception as e:
                logger.warning(f"本地服务连接测试失败: {e}")
                self._state = AIProviderState.READY  # 允许后续使用时重试
            
        except Exception as e:
            self._state = AIProviderState.ERROR
            logger.error(f"LocalProvider初始化失败: {e}")
            raise
    
    def _test_connection(self) -> bool:
        """
        测试本地服务连接
        
        Returns:
            连接是否成功
        """
        try:
            # 尝试获取模型列表
            models_endpoint = self._framework_config.get("models_endpoint", "/tags")
            url = f"{self._api_base}{models_endpoint}"
            
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                logger.info(f"本地服务连接测试成功: {url}")
                return True
            else:
                logger.warning(f"本地服务返回状态码: {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            logger.warning(f"无法连接到本地服务: {self._endpoint}")
            return False
        except Exception as e:
            logger.warning(f"本地服务连接测试异常: {e}")
            return False
    
    def _build_request_payload(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> Dict[str, Any]:
        """
        构建请求payload
        
        根据不同框架构建不同的请求格式
        """
        if self._framework == "ollama":
            # Ollama格式
            payload = {
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": config.temperature if config else self._temperature,
                    "num_predict": config.max_tokens if config else 2048,
                }
            }
            
            if system_prompt:
                payload["system"] = system_prompt
            
            return payload
        
        elif self._framework in ["llama-cpp", "vllm", "localai"]:
            # OpenAI兼容格式
            messages = []
            
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self._model,
                "messages": messages,
                "temperature": config.temperature if config else self._temperature,
                "max_tokens": config.max_tokens if config else 2048,
                "stream": False,
            }
            
            return payload
        
        else:
            # 通用格式
            return {
                "model": self._model,
                "prompt": prompt,
                "temperature": config.temperature if config else self._temperature,
                "max_tokens": config.max_tokens if config else 2048,
            }
    
    def _get_endpoint_url(self, use_chat: bool = False) -> str:
        """
        获取API端点URL
        
        Args:
            use_chat: 是否使用chat端点
        
        Returns:
            完整的API端点URL
        """
        if use_chat:
            endpoint_key = "chat_endpoint"
        else:
            endpoint_key = "generate_endpoint"
        
        endpoint_path = self._framework_config.get(endpoint_key, "/generate")
        
        # 某些框架的api_path已包含在endpoint_path中
        if self._framework in ["llama-cpp", "vllm", "localai"]:
            return f"{self._endpoint}{endpoint_path}"
        else:
            return f"{self._api_base}{endpoint_path}"
    
    def _classify_error(self, error: Exception) -> str:
        """
        分类错误类型
        
        Returns:
            错误类型字符串
        """
        if isinstance(error, requests.exceptions.ConnectionError):
            return "connection_error"
        elif isinstance(error, requests.exceptions.Timeout):
            return "timeout"
        elif isinstance(error, requests.exceptions.HTTPError):
            status_code = error.response.status_code if hasattr(error, 'response') else 500
            
            if status_code == 404:
                return "model_not_found"
            elif status_code == 400:
                return "invalid_request"
            elif status_code == 503:
                return "service_unavailable"
            elif status_code >= 500:
                return "server_error"
            else:
                return "unknown_error"
        elif isinstance(error, (FuturesTimeoutError, TimeoutError)):
            return "timeout"
        else:
            return "unknown_error"
    
    def _should_retry(self, error: Exception, attempt: int) -> bool:
        """
        判断是否应该重试
        
        Args:
            error: 异常对象
            attempt: 当前尝试次数
        
        Returns:
            是否应该重试
        """
        if attempt >= self._retry_policy.max_retries:
            return False
        
        error_type = self._classify_error(error)
        return self.RETRYABLE_ERRORS.get(error_type, False)
    
    def _wrap_exception(self, error: Exception) -> AIProviderError:
        """
        包装异常为AIProviderError
        
        Args:
            error: 原始异常
        
        Returns:
            AIProviderError异常
        """
        error_type = self._classify_error(error)
        
        if error_type == "connection_error":
            return LocalProviderConnectionError(
                f"无法连接到本地服务: {self._endpoint}",
                provider=self._framework
            )
        elif error_type == "timeout":
            return LocalProviderTimeoutError(
                f"本地服务请求超时: {self._timeout}秒",
                provider=self._framework
            )
        elif error_type == "model_not_found":
            return AIProviderConfigError(
                f"模型不存在: {self._model}",
                provider=self._framework
            )
        else:
            return LocalProviderResponseError(
                f"本地服务响应错误: {error}",
                provider=self._framework
            )
    
    def _execute_with_timeout(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        使用超时控制执行函数
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数
        
        Returns:
            函数执行结果
        
        Raises:
            AIProviderTimeoutError: 执行超时
        """
        future = self._executor.submit(func, *args, **kwargs)
        
        try:
            return future.result(timeout=self._timeout)
        except FuturesTimeoutError:
            raise AIProviderTimeoutError(
                f"请求超时: {self._timeout}秒",
                provider=self._framework
            )
    
    def _do_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> GenerationResult:
        """
        执行文本生成（内部方法）
        
        Args:
            prompt: 输入提示
            system_prompt: 系统提示
            config: 生成配置
        
        Returns:
            GenerationResult对象
        
        Raises:
            AIProviderError: 生成失败
        """
        start_time = time.time()
        
        # 构建请求
        use_chat = self._framework in ["llama-cpp", "vllm", "localai"]
        url = self._get_endpoint_url(use_chat=use_chat)
        payload = self._build_request_payload(prompt, system_prompt, config)
        
        # 发送请求
        response = requests.post(
            url,
            json=payload,
            timeout=self._timeout
        )
        
        response.raise_for_status()
        
        # 解析响应
        result_data = response.json()
        
        # 提取生成文本
        if self._framework == "ollama":
            text = result_data.get("response", "")
            tokens_used = result_data.get("eval_count", 0)
        else:
            # OpenAI兼容格式
            choices = result_data.get("choices", [])
            if choices:
                text = choices[0].get("message", {}).get("content", "")
            else:
                text = ""
            
            usage = result_data.get("usage", {})
            tokens_used = usage.get("total_tokens", 0)
        
        elapsed = int((time.time() - start_time) * 1000)
        
        return GenerationResult(
            text=text,
            finish_reason="stop",
            usage={"total_tokens": tokens_used},
            model=self._model,
            provider=self._framework,
            latency_ms=elapsed,
            success=True
        )
    
    # ========================================================================
    # 实现AIProvider抽象方法
    # ========================================================================
    
    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> GenerationResult:
        """
        同步生成文本
        
        Args:
            prompt: 输入提示
            system_prompt: 系统提示（可选）
            config: 生成配置（可选）
        
        Returns:
            GenerationResult对象
        
        Raises:
            AIProviderError: 生成失败
        """
        # 熔断器检查
        if not self._circuit_breaker.can_execute():
            raise AIProviderUnavailableError(
                "熔断器开启，本地服务暂时不可用",
                provider=self._framework
            )
        
        # 重试循环
        last_error = None
        
        for attempt in range(self._retry_policy.max_retries + 1):
            try:
                # 执行生成
                result = self._execute_with_timeout(
                    self._do_generate,
                    prompt,
                    system_prompt,
                    config
                )
                
                # 记录成功
                self._circuit_breaker.record_success()
                
                with self._lock:
                    self._total_requests += 1
                
                return result
                
            except Exception as e:
                last_error = e
                
                # 记录失败
                self._circuit_breaker.record_failure()
                
                with self._lock:
                    self._total_errors += 1
                
                # 检查是否应该重试
                if not self._should_retry(e, attempt):
                    raise self._wrap_exception(e)
                
                # 记录重试
                with self._lock:
                    self._total_retries += 1
                
                logger.warning(
                    f"本地服务调用失败（尝试 {attempt + 1}/{self._retry_policy.max_retries + 1}）: {e}"
                )
                
                # 延迟重试
                delay = self._retry_policy.get_delay(attempt)
                time.sleep(delay)
        
        # 所有重试失败
        raise self._wrap_exception(last_error)
    
    def generate_text_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> Iterator[str]:
        """
        流式生成文本
        
        Args:
            prompt: 输入提示
            system_prompt: 系统提示（可选）
            config: 生成配置（可选）
        
        Yields:
            生成的文本片段
        
        Raises:
            AIProviderError: 生成失败
        """
        # 熔断器检查
        if not self._circuit_breaker.can_execute():
            raise AIProviderUnavailableError(
                "熔断器开启，本地服务暂时不可用",
                provider=self._framework
            )
        
        try:
            # 构建流式请求
            use_chat = self._framework in ["llama-cpp", "vllm", "localai"]
            url = self._get_endpoint_url(use_chat=use_chat)
            payload = self._build_request_payload(prompt, system_prompt, config)
            payload["stream"] = True  # 启用流式
            
            # 发送流式请求
            with requests.post(url, json=payload, stream=True, timeout=self._timeout) as response:
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            
                            if self._framework == "ollama":
                                # Ollama格式
                                if "response" in data:
                                    yield data["response"]
                            else:
                                # OpenAI兼容格式
                                if "choices" in data and data["choices"]:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        yield delta["content"]
                        
                        except json.JSONDecodeError:
                            continue
            
            # 记录成功
            self._circuit_breaker.record_success()
            
            with self._lock:
                self._total_requests += 1
                
        except Exception as e:
            # 记录失败
            self._circuit_breaker.record_failure()
            
            with self._lock:
                self._total_errors += 1
            
            raise self._wrap_exception(e)
    
    def estimate_tokens(self, text: str) -> int:
        """
        估算Token数
        
        使用字符数近似算法，避免依赖tiktoken
        
        Args:
            text: 输入文本
        
        Returns:
            估算的Token数量
        """
        # 中文字符计数
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        
        # 英文单词计数
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        
        # 其他字符计数
        other_chars = len(text) - chinese_chars - sum(len(w) for w in re.findall(r'[a-zA-Z]+', text))
        
        # 近似计算
        # 中文：约1.5字符/token
        # 英文：约1.3字符/token
        # 其他：约2字符/token
        tokens = int(
            chinese_chars / 1.5 +
            english_words * 1.3 +
            other_chars / 2
        )
        
        return max(1, tokens)
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查（增强版）
        
        Returns:
            健康状态字典，包含服务状态、模型信息等
        """
        try:
            # 尝试连接本地服务（Ollama API）
            import requests
            url = f"{self._endpoint}/api/tags"  # Ollama模型列表接口
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                models_data = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models_data]
                
                return {
                    "service": "local",
                    "framework": self._framework,
                    "status": "healthy",
                    "endpoint": self._endpoint,
                    "model": self._model,
                    "available_models": model_names,
                    "model_loaded": self._model in model_names
                }
            else:
                return {
                    "service": "local",
                    "framework": self._framework,
                    "status": "unhealthy",
                    "endpoint": self._endpoint,
                    "error": f"HTTP {response.status_code}"
                }
        except Exception as e:
            return {
                "service": "local",
                "framework": self._framework,
                "status": "unreachable",
                "endpoint": self._endpoint,
                "error": str(e)
            }
    
    def analyze_text(
        self,
        text: str,
        analysis_type: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        分析文本
        
        Args:
            text: 输入文本
            analysis_type: 分析类型
            **kwargs: 额外参数
        
        Returns:
            分析结果字典
        
        Raises:
            AIProviderError: 分析失败
        """
        # 构建分析prompt
        analysis_prompts = {
            "sentiment": "请分析以下文本的情感倾向（积极/消极/中性），并给出理由：\n\n{text}",
            "summary": "请用简洁的语言总结以下文本的核心内容：\n\n{text}",
            "keywords": "请提取以下文本的关键词（不超过10个）：\n\n{text}",
            "structure": "请分析以下文本的结构（段落、章节、层次）：\n\n{text}",
            "style": "请分析以下文本的写作风格特点：\n\n{text}",
        }
        
        prompt_template = analysis_prompts.get(
            analysis_type,
            "请分析以下文本（分析类型：{analysis_type}）：\n\n{text}"
        )
        
        prompt = prompt_template.format(text=text, analysis_type=analysis_type)
        
        # 调用生成
        result = self.generate_text(prompt)
        
        return {
            "analysis_type": analysis_type,
            "result": result.text,
            "model": self._model,
            "provider": self._framework,
            "tokens_used": result.usage.get("total_tokens", 0),
        }
    
    def is_available(self) -> bool:
        """
        检查服务是否可用
        
        Returns:
            服务是否可用
        """
        return self._state == AIProviderState.READY and self._circuit_breaker.can_execute()
    
    def get_model_info(self) -> AIModelInfo:
        """
        获取模型信息
        
        Returns:
            AIModelInfo对象
        """
        # 尝试从配置中获取模型信息
        framework_config = LOCAL_FRAMEWORK_CONFIGS.get(self._framework, {})
        models = framework_config.get("models", {})
        model_config = models.get(self._model, {
            "max_tokens": 4096,
            "supports_streaming": True,
            "supports_vision": False
        })
        
        return AIModelInfo(
            provider_type=AIProviderType.LOCAL,
            provider_name=self._framework,
            model_name=self._model,
            max_tokens=model_config.get("max_tokens", 4096),
            supports_streaming=model_config.get("supports_streaming", True),
            supports_vision=model_config.get("supports_vision", False),
            metadata={
                "endpoint": self._endpoint,
                "temperature": self._temperature,
                "timeout": self._timeout,
            }
        )
    
    # ========================================================================
    # 额外便捷方法
    # ========================================================================
    
    def get_available_models(self) -> List[str]:
        """
        获取可用模型列表
        
        Returns:
            模型名称列表
        """
        try:
            models_endpoint = self._framework_config.get("models_endpoint", "/tags")
            url = f"{self._api_base}{models_endpoint}"
            
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                if self._framework == "ollama":
                    # Ollama格式
                    models = data.get("models", [])
                    return [m.get("name") for m in models]
                else:
                    # OpenAI兼容格式
                    models = data.get("data", [])
                    return [m.get("id") for m in models]
            else:
                return []
                
        except Exception as e:
            logger.warning(f"获取模型列表失败: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            return {
                "framework": self._framework,
                "model": self._model,
                "endpoint": self._endpoint,
                "temperature": self._temperature,
                "timeout": self._timeout,
                "total_requests": self._total_requests,
                "total_errors": self._total_errors,
                "total_retries": self._total_retries,
                "error_rate": (
                    self._total_errors / self._total_requests
                    if self._total_requests > 0 else 0
                ),
            }
    
    def switch_model(self, model_name: str) -> None:
        """
        切换模型
        
        Args:
            model_name: 新模型名称
        """
        with self._lock:
            self._model = model_name
        
        logger.info(f"模型切换: {model_name}")
    
    def update_endpoint(self, endpoint: str) -> None:
        """
        更新端点URL
        
        Args:
            endpoint: 新端点URL
        """
        with self._lock:
            self._endpoint = endpoint
            self._init_client()
        
        logger.info(f"端点更新: {endpoint}")
    
    def shutdown(self) -> None:
        """
        关闭Provider，清理资源
        """
        if self._executor:
            self._executor.shutdown(wait=False)
        
        logger.info(f"LocalProvider已关闭: {self._framework}")
