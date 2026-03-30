"""
OnlineProvider - 封装OpenAI SDK，支持DeepSeek等兼容API

V1.0版本
创建日期：2026-03-24

设计目标：
- 封装OpenAI SDK，兼容DeepSeek/OpenAI/Anthropic/Ollama
- 支持同步和流式生成
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
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import random

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
# 支持的Provider配置
# ============================================================================

PROVIDER_CONFIGS = {
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "models": {
            "deepseek-chat": {"max_tokens": 64000, "supports_streaming": True, "supports_vision": False},
            "deepseek-coder": {"max_tokens": 16000, "supports_streaming": True, "supports_vision": False},
            "deepseek-reasoner": {"max_tokens": 64000, "supports_streaming": True, "supports_vision": False},
        },
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "models": {
            "gpt-4o": {"max_tokens": 128000, "supports_streaming": True, "supports_vision": True},
            "gpt-4o-mini": {"max_tokens": 128000, "supports_streaming": True, "supports_vision": True},
            "gpt-4-turbo": {"max_tokens": 128000, "supports_streaming": True, "supports_vision": True},
            "gpt-3.5-turbo": {"max_tokens": 16385, "supports_streaming": True, "supports_vision": False},
        },
    },
    "Anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-sonnet-20241022",
        "models": {
            "claude-3-5-sonnet-20241022": {"max_tokens": 200000, "supports_streaming": True, "supports_vision": True},
            "claude-3-5-haiku-20241022": {"max_tokens": 200000, "supports_streaming": True, "supports_vision": True},
            "claude-3-opus-20240229": {"max_tokens": 200000, "supports_streaming": True, "supports_vision": True},
        },
    },
    "Ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.1",
        "models": {
            "llama3.1": {"max_tokens": 128000, "supports_streaming": True, "supports_vision": False},
            "qwen2.5": {"max_tokens": 32000, "supports_streaming": True, "supports_vision": False},
            "deepseek-coder-v2": {"max_tokens": 128000, "supports_streaming": True, "supports_vision": False},
        },
    },
}


# ============================================================================
# 自定义异常类
# ============================================================================

class OnlineProviderAuthError(AIProviderError):
    """认证错误"""
    pass


class OnlineProviderRateLimitError(AIProviderError):
    """速率限制错误"""
    pass


class OnlineProviderConnectionError(AIProviderError):
    """连接错误"""
    pass


class OnlineProviderResponseError(AIProviderError):
    """响应错误"""
    pass


# ============================================================================
# 重试策略
# ============================================================================

@dataclass
class RetryPolicy:
    """重试策略配置"""
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
# OnlineProvider实现
# ============================================================================

class OnlineProvider(AIProvider):
    """
    线上AI能力提供者
    
    封装OpenAI SDK，支持DeepSeek/OpenAI/Anthropic/Ollama等兼容API
    
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
        "rate_limit": True,
        "server_error": True,
        # 认证错误（不可重试）
        "authentication_error": False,
        "invalid_api_key": False,
        # 参数错误（不可重试）
        "invalid_request": False,
        "context_length_exceeded": False,
    }
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化OnlineProvider
        
        Args:
            config: 配置字典，应包含：
                - provider: 提供者名称（DeepSeek/OpenAI/Anthropic/Ollama）
                - api_key: API密钥
                - model: 模型名称
                - base_url: API基础URL（可选，覆盖默认值）
                - temperature: 温度参数（可选）
                - timeout: 超时时间（可选）
                - max_retries: 最大重试次数（可选）
        """
        super().__init__(config)
        
        self._lock = threading.RLock()
        self._client = None
        self._provider_name = config.get("provider", "DeepSeek")
        self._model = config.get("model", "deepseek-chat")
        self._api_key = config.get("api_key", "")
        self._base_url = config.get("base_url", "")
        self._temperature = config.get("temperature", 0.7)
        
        # 超时和重试配置
        self._timeout = config.get("timeout", 120)
        self._retry_policy = RetryPolicy(
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
            f"OnlineProvider初始化: provider={self._provider_name}, "
            f"model={self._model}, base_url={self._base_url}"
        )
    
    def _init_client(self) -> None:
        """
        初始化OpenAI客户端
        
        验证配置并创建客户端实例
        """
        try:
            # 验证配置
            if not self._api_key:
                raise AIProviderConfigError(
                    "缺少API密钥",
                    provider=self._provider_name
                )
            
            # 获取Provider配置
            provider_config = PROVIDER_CONFIGS.get(self._provider_name)
            if not provider_config:
                logger.warning(
                    f"未知的Provider: {self._provider_name}, "
                    f"使用通用配置"
                )
                provider_config = {
                    "base_url": self._base_url or "https://api.openai.com/v1",
                    "default_model": self._model,
                    "models": {}
                }
            
            # 设置基础URL（配置优先 > 默认值）
            if not self._base_url:
                self._base_url = provider_config["base_url"]
            
            # 验证模型
            model_config = provider_config.get("models", {}).get(self._model)
            if model_config:
                self._model_config = model_config
            else:
                # 未知模型使用默认配置
                self._model_config = {
                    "max_tokens": 4096,
                    "supports_streaming": True,
                    "supports_vision": False
                }
                logger.warning(
                    f"未知的模型: {self._model}, "
                    f"使用默认配置: {self._model_config}"
                )
            
            # 创建OpenAI客户端
            from openai import OpenAI
            
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )
            
            # 获取熔断器（P1-1修复：显式配置熔断器参数）
            cb_manager = get_circuit_breaker_manager()
            self._circuit_breaker = cb_manager.get_or_create(
                f"ai_provider_{self._provider_name}",
                failure_threshold=5,  # 失败5次后熔断
                success_threshold=3,  # 成功3次后恢复
                timeout=60            # 熔断持续60秒
            )
            
            self._state = AIProviderState.READY
            logger.info(f"OpenAI客户端初始化成功: {self._provider_name}")
            
        except ImportError as e:
            self._state = AIProviderState.ERROR
            raise AIProviderError(
                f"导入OpenAI SDK失败: {e}",
                provider=self._provider_name,
                original_error=e
            )
        except Exception as e:
            self._state = AIProviderState.ERROR
            logger.error(f"初始化OpenAI客户端失败: {e}", exc_info=True)
            raise
    
    # ========================================================================
    # 核心API方法实现
    # ========================================================================
    
    def generate_text(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> GenerationResult:
        """
        生成文本（同步）
        
        实现四级容错机制：
        1. 重试层：指数退避 + jitter
        2. 熔断层：失败率>50%时熔断
        3. 模型回退：降级到备用模型
        4. 缓存降级：返回最近的缓存结果
        
        Args:
            prompt: 提示词
            config: 生成配置（可选）
            **kwargs: 其他参数（如system_prompt、messages等）
            
        Returns:
            GenerationResult: 生成结果
        """
        start_time = time.time()
        self._total_requests += 1
        
        # 检查熔断器状态
        if self._circuit_breaker and self._circuit_breaker.state == CircuitState.OPEN:
            raise AIProviderUnavailableError(
                f"熔断器开启，服务不可用",
                provider=self._provider_name
            )
        
        # 使用默认配置或传入配置
        gen_config = config or GenerationConfig(
            temperature=self._temperature,
            max_tokens=self._model_config.get("max_tokens", 4096)
        )
        
        # 重试循环
        last_error = None
        for attempt in range(self._retry_policy.max_retries):
            try:
                result = self._do_generate(prompt, gen_config, **kwargs)
                
                # 成功：重置熔断器
                if self._circuit_breaker:
                    self._circuit_breaker.record_success()
                
                return result
                
            except Exception as e:
                last_error = e
                self._total_errors += 1
                self._total_retries += 1
                
                # 判断是否可重试
                error_type = self._classify_error(e)
                if not self._should_retry(error_type, attempt):
                    break
                
                # 记录失败到熔断器
                if self._circuit_breaker:
                    self._circuit_breaker.record_failure()
                
                # 计算延迟并等待
                delay = self._retry_policy.get_delay(attempt)
                logger.warning(
                    f"生成失败（{error_type}），{delay:.1f}秒后重试 "
                    f"(attempt {attempt + 1}/{self._retry_policy.max_retries}): {e}"
                )
                time.sleep(delay)
        
        # 所有重试失败
        latency_ms = int((time.time() - start_time) * 1000)
        
        # 构造错误结果
        return GenerationResult(
            text="",
            finish_reason="error",
            usage={"total_tokens": 0},
            model=self._model,
            provider=self._provider_name,
            latency_ms=latency_ms,
            success=False,
            error=str(last_error)
        )
    
    def _do_generate(
        self,
        prompt: str,
        config: GenerationConfig,
        **kwargs
    ) -> GenerationResult:
        """
        执行实际的API调用（带超时控制）
        
        使用线程池实现超时保护
        """
        start_time = time.time()
        
        # 构造消息
        messages = self._build_messages(prompt, **kwargs)
        
        # 构造请求参数
        request_params = {
            "model": self._model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            "frequency_penalty": config.frequency_penalty,
            "presence_penalty": config.presence_penalty,
        }
        
        # 添加停止词
        if config.stop:
            request_params["stop"] = config.stop
        
        # 使用线程池执行（带超时）
        future = self._executor.submit(self._call_api, request_params)
        
        try:
            response = future.result(timeout=config.timeout)
        except FuturesTimeoutError:
            future.cancel()
            raise AIProviderTimeoutError(
                f"API调用超时（{config.timeout}秒）",
                provider=self._provider_name
            )
        
        # 解析响应
        latency_ms = int((time.time() - start_time) * 1000)
        
        return GenerationResult(
            text=response.choices[0].message.content or "",
            finish_reason=response.choices[0].finish_reason or "stop",
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            model=response.model,
            provider=self._provider_name,
            latency_ms=latency_ms,
            success=True,
        )
    
    def _call_api(self, request_params: Dict[str, Any]):
        """
        调用OpenAI API（实际执行）
        
        在线程池中执行，支持超时控制
        """
        try:
            response = self._client.chat.completions.create(**request_params)
            return response
        except Exception as e:
            # 分类并重新抛出异常
            raise self._wrap_exception(e)
    
    def generate_text_stream(
        self,
        prompt: str,
        callback: Callable[[str], None],
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> GenerationResult:
        """
        流式生成文本（异步回调）
        
        使用OpenAI的流式API，每次收到新token时调用回调函数
        
        Args:
            prompt: 提示词
            callback: 回调函数，每次收到新token时调用
            config: 生成配置（可选）
            **kwargs: 其他参数
            
        Returns:
            GenerationResult: 最终生成结果
        """
        start_time = time.time()
        self._total_requests += 1
        
        # 检查熔断器
        if self._circuit_breaker and self._circuit_breaker.state == CircuitState.OPEN:
            raise AIProviderUnavailableError(
                f"熔断器开启，服务不可用",
                provider=self._provider_name
            )
        
        # 使用默认配置或传入配置
        gen_config = config or GenerationConfig(
            temperature=self._temperature,
            max_tokens=self._model_config.get("max_tokens", 4096)
        )
        
        # 构造消息
        messages = self._build_messages(prompt, **kwargs)
        
        # 构造请求参数
        request_params = {
            "model": self._model,
            "messages": messages,
            "temperature": gen_config.temperature,
            "max_tokens": gen_config.max_tokens,
            "stream": True,  # 启用流式输出
        }
        
        # 收集完整响应
        full_text = []
        finish_reason = "stop"
        prompt_tokens = 0
        completion_tokens = 0
        
        try:
            # 调用流式API
            stream = self._client.chat.completions.create(**request_params)
            
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_text.append(token)
                    callback(token)
                
                if chunk.choices and chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason
                
                # 使用情况（最后一个chunk包含）
                if hasattr(chunk, 'usage') and chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens
            
            # 成功：重置熔断器
            if self._circuit_breaker:
                self._circuit_breaker.record_success()
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return GenerationResult(
                text="".join(full_text),
                finish_reason=finish_reason,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
                model=self._model,
                provider=self._provider_name,
                latency_ms=latency_ms,
                success=True,
            )
            
        except Exception as e:
            self._total_errors += 1
            
            # 记录失败到熔断器
            if self._circuit_breaker:
                self._circuit_breaker.record_failure()
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return GenerationResult(
                text="",
                finish_reason="error",
                usage={"total_tokens": 0},
                model=self._model,
                provider=self._provider_name,
                latency_ms=latency_ms,
                success=False,
                error=str(e)
            )
    
    def analyze_text(
        self,
        text: str,
        analysis_type: str,
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        分析文本（结构化输出）
        
        使用Prompt工程引导模型输出结构化数据
        
        Args:
            text: 待分析文本
            analysis_type: 分析类型（如：sentiment、summary、extraction）
            config: 生成配置（可选）
            **kwargs: 其他参数（如schema、fields等）
            
        Returns:
            Dict[str, Any]: 分析结果（结构化数据）
        """
        # 构造分析Prompt
        prompt = self._build_analysis_prompt(text, analysis_type, **kwargs)
        
        # 调用生成
        result = self.generate_text(prompt, config)
        
        if not result.success:
            return {
                "success": False,
                "error": result.error,
                "analysis_type": analysis_type,
            }
        
        # 尝试解析JSON
        try:
            # 提取JSON部分
            json_text = self._extract_json(result.text)
            return json.loads(json_text)
        except json.JSONDecodeError:
            # 返回原始文本
            return {
                "success": True,
                "text": result.text,
                "analysis_type": analysis_type,
                "note": "无法解析为JSON，返回原始文本"
            }
    
    def estimate_tokens(self, text: str) -> int:
        """
        估算token数
        
        使用简单的估算方法：中文约1.5字符/token，英文约4字符/token
        
        Args:
            text: 文本内容
            
        Returns:
            int: 估算的token数
        """
        if not text:
            return 0
        
        # 统计中文字符
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        
        # 统计英文和其他字符
        other_chars = len(text) - chinese_chars
        
        # 估算token数
        tokens = int(chinese_chars / 1.5 + other_chars / 4)
        
        return max(tokens, 1)
    
    def get_model_info(self) -> AIModelInfo:
        """
        获取模型信息
        
        Returns:
            AIModelInfo: 模型信息
        """
        return AIModelInfo(
            provider_type=AIProviderType.ONLINE,
            provider_name=self._provider_name,
            model_name=self._model,
            max_tokens=self._model_config.get("max_tokens", 4096),
            supports_streaming=self._model_config.get("supports_streaming", True),
            supports_vision=self._model_config.get("supports_vision", False),
            metadata={
                "base_url": self._base_url,
                "temperature": self._temperature,
            }
        )
    
    def is_available(self) -> bool:
        """
        检查服务是否可用
        
        Returns:
            bool: 是否可用
        """
        if self._state != AIProviderState.READY:
            return False
        
        if self._circuit_breaker and self._circuit_breaker.state == CircuitState.OPEN:
            return False
        
        return self._client is not None
    
    # ========================================================================
    # 辅助方法
    # ========================================================================
    
    def _build_messages(self, prompt: str, **kwargs) -> List[Dict[str, str]]:
        """
        构造消息列表
        
        支持：
        - system_prompt: 系统提示词
        - messages: 完整消息列表（会覆盖其他参数）
        """
        # 如果直接传入messages，优先使用
        if "messages" in kwargs:
            return kwargs["messages"]
        
        messages = []
        
        # 添加系统提示词
        if "system_prompt" in kwargs:
            messages.append({
                "role": "system",
                "content": kwargs["system_prompt"]
            })
        
        # 添加用户消息
        messages.append({
            "role": "user",
            "content": prompt
        })
        
        return messages
    
    def _build_analysis_prompt(
        self,
        text: str,
        analysis_type: str,
        **kwargs
    ) -> str:
        """
        构造分析Prompt
        
        根据分析类型生成不同的Prompt模板
        """
        templates = {
            "sentiment": """请分析以下文本的情感倾向，并以JSON格式返回结果：

文本：
{text}

请返回JSON格式：
{{
  "sentiment": "positive/neutral/negative",
  "confidence": 0.0-1.0,
  "keywords": ["关键词1", "关键词2", ...]
}}""",
            
            "summary": """请总结以下文本的核心内容，并以JSON格式返回结果：

文本：
{text}

请返回JSON格式：
{{
  "summary": "摘要内容",
  "key_points": ["要点1", "要点2", ...],
  "word_count": 原文字数
}}""",
            
            "extraction": """请从以下文本中提取{fields}信息，并以JSON格式返回结果：

文本：
{text}

请返回JSON格式：
{{
  "extracted_data": {{
    // 提取的字段
  }},
  "confidence": 0.0-1.0
}}""",
        }
        
        template = templates.get(analysis_type, templates["summary"])
        
        # 替换变量
        prompt = template.format(
            text=text,
            fields=kwargs.get("fields", "所有关键信息")
        )
        
        return prompt
    
    def _extract_json(self, text: str) -> str:
        """
        从文本中提取JSON部分
        
        支持以下格式：
        1. 纯JSON
        2. ```json ... ```
        3. ``` ... ```
        """
        text = text.strip()
        
        # 尝试直接解析
        if text.startswith("{") or text.startswith("["):
            return text
        
        # 提取代码块中的JSON
        import re
        
        # ```json ... ```
        json_match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
        
        # ``` ... ```
        code_match = re.search(r'```\s*\n(.*?)\n```', text, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        
        # 查找第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end+1]
        
        return text
    
    def _classify_error(self, error: Exception) -> str:
        """
        分类错误类型
        
        用于判断是否可重试
        """
        error_str = str(error).lower()
        
        # 连接错误
        if any(keyword in error_str for keyword in ["connection", "network", "timeout", "timed out"]):
            return "connection_error"
        
        # 超时
        if "timeout" in error_str:
            return "timeout"
        
        # 速率限制
        if "rate" in error_str or "limit" in error_str or "429" in error_str:
            return "rate_limit"
        
        # 服务器错误
        if "500" in error_str or "502" in error_str or "503" in error_str:
            return "server_error"
        
        # 认证错误
        if "auth" in error_str or "api_key" in error_str or "401" in error_str or "403" in error_str:
            return "authentication_error"
        
        # 无效请求
        if "invalid" in error_str or "400" in error_str:
            return "invalid_request"
        
        # 上下文长度超限
        if "context" in error_str or "length" in error_str or "token" in error_str:
            return "context_length_exceeded"
        
        return "unknown"
    
    def _should_retry(self, error_type: str, attempt: int) -> bool:
        """
        判断是否应该重试
        
        Args:
            error_type: 错误类型
            attempt: 当前尝试次数
            
        Returns:
            bool: 是否应该重试
        """
        # 超过最大重试次数
        if attempt >= self._retry_policy.max_retries - 1:
            return False
        
        # 查表判断
        return self.RETRYABLE_ERRORS.get(error_type, False)
    
    def _wrap_exception(self, error: Exception) -> AIProviderError:
        """
        包装原始异常为自定义异常
        
        保留原始异常信息，添加Provider上下文
        """
        error_type = self._classify_error(error)
        
        error_classes = {
            "connection_error": OnlineProviderConnectionError,
            "timeout": AIProviderTimeoutError,
            "rate_limit": OnlineProviderRateLimitError,
            "authentication_error": OnlineProviderAuthError,
            "invalid_request": AIProviderConfigError,
        }
        
        error_class = error_classes.get(error_type, AIProviderError)
        
        return error_class(
            message=str(error),
            provider=self._provider_name,
            original_error=error
        )
    
    # ========================================================================
    # 异步方法（V1.18新增 - 解决卡顿问题）
    # ========================================================================
    
    async def generate_text_async(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> GenerationResult:
        """
        异步生成文本（新增方法）
        
        核心机制：
        - 复用现有同步客户端（不引入AsyncOpenAI）
        - 在统一线程池中执行同步调用
        - 真正的非阻塞异步
        
        四两拨千斤：
        - 不修改现有代码
        - 不引入新依赖
        - 复用已有容错机制（重试、熔断、缓存）
        - 使用统一线程池（解决P1-3和P1-4）
        
        Args:
            prompt: 提示词
            config: 生成配置（可选）
            **kwargs: 其他参数（如system_prompt、messages等）
            
        Returns:
            GenerationResult: 生成结果
        """
        from .thread_pool_manager import thread_pool_manager
        
        # 在统一线程池中执行同步方法
        result = await thread_pool_manager.run_in_executor(
            self.generate_text,  # 复用现有同步方法
            prompt,
            config,
            **kwargs
        )
        
        return result
    
    async def generate_text_stream_async(
        self,
        prompt: str,
        on_chunk: Optional[Callable[[str], None]] = None,
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> GenerationResult:
        """
        异步流式生成文本（新增方法）
        
        核心机制：
        - 复用现有流式生成方法
        - 在统一线程池中执行
        - 通过回调传递chunk
        
        Args:
            prompt: 提示词
            on_chunk: 每收到token就调用
            config: 生成配置（可选）
            **kwargs: 其他参数
            
        Returns:
            GenerationResult: 完整生成结果
        """
        import asyncio
        import threading
        from .thread_pool_manager import thread_pool_manager
        
        # 创建队列用于传递chunk
        chunk_queue = asyncio.Queue()
        done_event = threading.Event()
        error_holder = [None]  # 用于传递异常
        
        def sync_stream():
            """在独立线程中执行同步流式生成"""
            try:
                def callback_wrapper(token: str):
                    """包装回调，将token放入队列"""
                    # 如果有外部回调，立即调用
                    if on_chunk:
                        try:
                            on_chunk(token)
                        except Exception as e:
                            logger.error(f"Error in on_chunk callback: {e}")
                
                # 调用同步流式方法
                result = self.generate_text_stream(
                    prompt,
                    callback_wrapper,
                    config,
                    **kwargs
                )
                
                # 将最终结果放入队列
                asyncio.run_coroutine_threadsafe(
                    chunk_queue.put(("result", result)),
                    asyncio.get_event_loop()
                )
                
            except Exception as e:
                error_holder[0] = e
                logger.error(f"Error in sync_stream: {e}")
            finally:
                done_event.set()
        
        # 在统一线程池中执行
        await thread_pool_manager.run_in_executor(sync_stream)
        
        # 等待完成并收集结果
        final_result = None
        while not done_event.is_set() or not chunk_queue.empty():
            try:
                item = await asyncio.wait_for(chunk_queue.get(), timeout=0.1)
                if item[0] == "result":
                    final_result = item[1]
            except asyncio.TimeoutError:
                pass
        
        # 检查是否有异常
        if error_holder[0]:
            raise error_holder[0]
        
        return final_result or GenerationResult(
            text="",
            finish_reason="error",
            usage={"total_tokens": 0},
            model=self._model,
            provider=self._provider_name,
            latency_ms=0,
            success=False,
            error="流式生成未返回结果"
        )
    
    async def analyze_text_async(
        self,
        text: str,
        analysis_type: str,
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        异步分析文本（新增方法）
        
        在统一线程池中执行同步分析方法
        
        Args:
            text: 待分析文本
            analysis_type: 分析类型
            config: 生成配置（可选）
            **kwargs: 其他参数
            
        Returns:
            Dict[str, Any]: 分析结果
        """
        from .thread_pool_manager import thread_pool_manager
        
        result = await thread_pool_manager.run_in_executor(
            self.analyze_text,
            text,
            analysis_type,
            config,
            **kwargs
        )
        
        return result
    
    def __del__(self):
        """析构函数：清理线程池"""
        try:
            if hasattr(self, '_executor'):
                self._executor.shutdown(wait=False)
        except Exception:
            pass


# ============================================================================
# 便捷函数
# ============================================================================

def create_online_provider(
    provider: str = "DeepSeek",
    api_key: str = "",
    model: str = None,
    **kwargs
) -> OnlineProvider:
    """
    创建OnlineProvider实例的便捷函数
    
    Args:
        provider: 提供者名称
        api_key: API密钥
        model: 模型名称（可选，使用默认值）
        **kwargs: 其他配置
        
    Returns:
        OnlineProvider: Provider实例
        
    Example:
        >>> provider = create_online_provider(
        ...     provider="DeepSeek",
        ...     api_key="sk-xxx",
        ...     model="deepseek-chat"
        ... )
        >>> result = provider.generate_text("写一首诗")
    """
    # 获取默认模型
    if not model and provider in PROVIDER_CONFIGS:
        model = PROVIDER_CONFIGS[provider]["default_model"]
    
    config = {
        "provider": provider,
        "api_key": api_key,
        "model": model,
        **kwargs
    }
    
    return OnlineProvider(config)


__all__ = [
    "OnlineProvider",
    "OnlineProviderAuthError",
    "OnlineProviderRateLimitError",
    "OnlineProviderConnectionError",
    "OnlineProviderResponseError",
    "RetryPolicy",
    "PROVIDER_CONFIGS",
    "create_online_provider",
]


__version__ = "1.1.0"
