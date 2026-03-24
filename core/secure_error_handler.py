"""
安全错误处理模块

V1.0 - P2-2安全修复
创建日期: 2026-03-24

功能:
- 统一错误处理
- 敏感信息脱敏
- 安全错误消息生成
- 错误分类与分级
"""

import re
import logging
import traceback
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """错误严重级别"""
    LOW = "low"           # 低风险，不影响功能
    MEDIUM = "medium"     # 中风险，部分功能受影响
    HIGH = "high"         # 高风险，核心功能受影响
    CRITICAL = "critical" # 严重，系统崩溃


class ErrorCategory(Enum):
    """错误类别"""
    NETWORK = "network"           # 网络错误
    AUTH = "auth"                 # 认证授权错误
    VALIDATION = "validation"     # 输入验证错误
    RESOURCE = "resource"         # 资源错误（内存、文件等）
    CONFIGURATION = "config"      # 配置错误
    EXECUTION = "execution"       # 执行错误
    TIMEOUT = "timeout"           # 超时错误
    PERMISSION = "permission"     # 权限错误
    UNKNOWN = "unknown"           # 未知错误


@dataclass
class SecureError:
    """安全错误对象"""
    original_message: str           # 原始错误消息（内部使用）
    safe_message: str               # 安全错误消息（对外展示）
    category: ErrorCategory         # 错误类别
    severity: ErrorSeverity         # 严重级别
    is_retryable: bool              # 是否可重试
    sensitive_data_found: bool      # 是否发现敏感数据
    context: Dict[str, Any] = field(default_factory=dict)  # 上下文信息
    exception_type: str = ""        # 异常类型
    stack_trace: str = ""           # 堆栈跟踪（内部使用）


class SensitiveDataPattern:
    """敏感数据模式定义"""
    
    # 敏感数据正则模式
    PATTERNS = {
        # API密钥（常见格式）
        "api_key": [
            r'["\']?api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{20,}["\']?',
            r'sk-[a-zA-Z0-9]{48,}',  # OpenAI格式
            r'pk-[a-zA-Z0-9]{48,}',  # 公钥格式
            r'Bearer\s+[a-zA-Z0-9_\-\.]{20,}',  # Bearer token
        ],
        # 密码
        "password": [
            r'["\']?password["\']?\s*[:=]\s*["\']?[^\s"\']{8,}["\']?',
            r'["\']?passwd["\']?\s*[:=]\s*["\']?[^\s"\']{8,}["\']?',
            r'["\']?pwd["\']?\s*[:=]\s*["\']?[^\s"\']{8,}["\']?',
        ],
        # 数据库连接字符串
        "database_url": [
            r'(mysql|postgres|mongodb|redis)://[^\s"\']+:[^\s"\']+@[^\s"\']+',
            r'jdbc:[^\s"\']+password[^\s"\']+',
        ],
        # 文件路径（Windows和Unix）
        "file_path": [
            r'[A-Z]:\\[^\s"\']+',  # Windows绝对路径
            r'/home/[^\s"\']+',    # Linux用户目录
            r'/Users/[^\s"\']+',   # macOS用户目录
        ],
        # IP地址（内网）
        "internal_ip": [
            r'192\.168\.\d{1,3}\.\d{1,3}',
            r'10\.\d{1,3}\.\d{1,3}\.\d{1,3}',
            r'172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}',
        ],
        # 邮箱地址
        "email": [
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        ],
        # 手机号（中国）
        "phone": [
            r'1[3-9]\d{9}',
        ],
        # 身份证号（中国）
        "id_card": [
            r'\d{17}[\dXx]',
        ],
        # 银行卡号
        "bank_card": [
            r'\d{16,19}',
        ],
        # 私钥
        "private_key": [
            r'-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----',
            r'-----BEGIN PGP PRIVATE KEY BLOCK-----',
        ],
    }
    
    @classmethod
    def detect_sensitive(cls, text: str) -> Tuple[bool, List[str]]:
        """
        检测文本中的敏感数据
        
        Args:
            text: 待检测文本
            
        Returns:
            (是否发现敏感数据, 敏感数据类型列表)
        """
        found_types = []
        
        for data_type, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    found_types.append(data_type)
                    break
        
        return len(found_types) > 0, found_types
    
    @classmethod
    def mask_sensitive(cls, text: str, mask_char: str = "***") -> str:
        """
        脱敏文本中的敏感数据
        
        Args:
            text: 待脱敏文本
            mask_char: 替换字符
            
        Returns:
            脱敏后的文本
        """
        masked_text = text
        
        for data_type, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                masked_text = re.sub(
                    pattern, 
                    f"[{data_type.upper()}_MASKED]", 
                    masked_text, 
                    flags=re.IGNORECASE
                )
        
        return masked_text


class SecureErrorHandler:
    """
    安全错误处理器（P2-2安全修复）
    
    功能:
    - 统一错误处理
    - 敏感信息检测与脱敏
    - 安全错误消息生成
    - 错误分类与分级
    """
    
    # 已知异常类型映射
    EXCEPTION_MAPPING = {
        # 网络错误
        "ConnectionError": (ErrorCategory.NETWORK, ErrorSeverity.HIGH, True),
        "TimeoutError": (ErrorCategory.TIMEOUT, ErrorSeverity.MEDIUM, True),
        "ConnectionResetError": (ErrorCategory.NETWORK, ErrorSeverity.HIGH, True),
        
        # 认证授权错误
        "PermissionError": (ErrorCategory.PERMISSION, ErrorSeverity.HIGH, False),
        "AuthenticationError": (ErrorCategory.AUTH, ErrorSeverity.HIGH, False),
        "UnauthorizedError": (ErrorCategory.AUTH, ErrorSeverity.HIGH, False),
        
        # 验证错误
        "ValueError": (ErrorCategory.VALIDATION, ErrorSeverity.LOW, False),
        "TypeError": (ErrorCategory.VALIDATION, ErrorSeverity.LOW, False),
        
        # 资源错误
        "MemoryError": (ErrorCategory.RESOURCE, ErrorSeverity.CRITICAL, False),
        "FileNotFoundError": (ErrorCategory.RESOURCE, ErrorSeverity.MEDIUM, False),
        "IOError": (ErrorCategory.RESOURCE, ErrorSeverity.MEDIUM, True),
        
        # 配置错误
        "ImportError": (ErrorCategory.CONFIGURATION, ErrorSeverity.HIGH, False),
        "ModuleNotFoundError": (ErrorCategory.CONFIGURATION, ErrorSeverity.HIGH, False),
        
        # 执行错误
        "RuntimeError": (ErrorCategory.EXECUTION, ErrorSeverity.HIGH, True),
        "Exception": (ErrorCategory.UNKNOWN, ErrorSeverity.MEDIUM, True),
    }
    
    # 安全错误消息模板
    SAFE_MESSAGES = {
        ErrorCategory.NETWORK: "网络连接失败，请检查网络设置",
        ErrorCategory.AUTH: "认证失败，请检查权限设置",
        ErrorCategory.VALIDATION: "输入验证失败，请检查输入参数",
        ErrorCategory.RESOURCE: "资源访问失败，请检查资源状态",
        ErrorCategory.CONFIGURATION: "配置错误，请检查系统配置",
        ErrorCategory.EXECUTION: "执行失败，请稍后重试",
        ErrorCategory.TIMEOUT: "操作超时，请稍后重试",
        ErrorCategory.PERMISSION: "权限不足，无法执行操作",
        ErrorCategory.UNKNOWN: "未知错误，请联系管理员",
    }
    
    def __init__(self, enable_logging: bool = True, enable_masking: bool = True):
        """
        初始化安全错误处理器
        
        Args:
            enable_logging: 是否启用日志记录
            enable_masking: 是否启用敏感信息脱敏
        """
        self._enable_logging = enable_logging
        self._enable_masking = enable_masking
    
    def handle_error(
        self, 
        error: Exception, 
        context: Dict[str, Any] = None,
        safe_message_override: str = None
    ) -> SecureError:
        """
        处理错误
        
        Args:
            error: 异常对象
            context: 上下文信息
            safe_message_override: 自定义安全消息
            
        Returns:
            SecureError对象
        """
        # 获取异常信息
        exception_type = type(error).__name__
        original_message = str(error)
        stack_trace = traceback.format_exc()
        
        # 检测敏感数据
        has_sensitive, sensitive_types = SensitiveDataPattern.detect_sensitive(
            f"{original_message}\n{stack_trace}"
        )
        
        # 确定错误类别和严重级别
        category, severity, is_retryable = self.EXCEPTION_MAPPING.get(
            exception_type, 
            (ErrorCategory.UNKNOWN, ErrorSeverity.MEDIUM, True)
        )
        
        # 生成安全消息
        if safe_message_override:
            safe_message = safe_message_override
        elif self._enable_masking and has_sensitive:
            safe_message = self.SAFE_MESSAGES[category]
        elif self._enable_masking:
            safe_message = SensitiveDataPattern.mask_sensitive(original_message)
        else:
            safe_message = original_message
        
        # 记录日志
        if self._enable_logging:
            if has_sensitive:
                logger.warning(
                    f"错误包含敏感数据 [{exception_type}]: "
                    f"类型={sensitive_types}, 安全消息={safe_message}"
                )
            else:
                logger.error(
                    f"错误处理 [{exception_type}]: "
                    f"类别={category.value}, 严重级别={severity.value}, "
                    f"消息={original_message}"
                )
        
        return SecureError(
            original_message=original_message,
            safe_message=safe_message,
            category=category,
            severity=severity,
            is_retryable=is_retryable,
            sensitive_data_found=has_sensitive,
            context=context or {},
            exception_type=exception_type,
            stack_trace=stack_trace
        )
    
    def format_error_for_user(self, error: SecureError) -> str:
        """
        格式化错误信息用于用户展示
        
        Args:
            error: SecureError对象
            
        Returns:
            格式化的错误消息
        """
        parts = [error.safe_message]
        
        if error.is_retryable:
            parts.append("（该错误可能通过重试解决）")
        
        return "".join(parts)
    
    def format_error_for_log(self, error: SecureError) -> str:
        """
        格式化错误信息用于日志记录
        
        Args:
            error: SecureError对象
            
        Returns:
            格式化的日志消息
        """
        parts = [
            f"[{error.exception_type}]",
            f"类别: {error.category.value}",
            f"严重级别: {error.severity.value}",
            f"可重试: {error.is_retryable}",
            f"消息: {error.original_message}",
        ]
        
        if error.sensitive_data_found:
            parts.append("⚠️ 包含敏感数据")
        
        if error.context:
            parts.append(f"上下文: {error.context}")
        
        return " | ".join(parts)


def secure_error_handler(
    context_provider: callable = None,
    safe_message: str = None
):
    """
    安全错误处理装饰器（P2-2安全修复）
    
    Args:
        context_provider: 上下文信息提供函数
        safe_message: 自定义安全消息
        
    Usage:
        @secure_error_handler(context_provider=lambda args: {"agent": args[0].agent_type})
        def execute(self, task):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # 获取上下文
                context = {}
                if context_provider:
                    try:
                        context = context_provider(args, kwargs)
                    except:
                        pass
                
                # 处理错误
                handler = SecureErrorHandler()
                secure_error = handler.handle_error(e, context, safe_message)
                
                # 记录详细日志
                logger.error(handler.format_error_for_log(secure_error))
                
                # 重新抛出，但使用安全消息
                raise SecureErrorException(secure_error)
        
        return wrapper
    return decorator


class SecureErrorException(Exception):
    """安全错误异常包装类"""
    
    def __init__(self, secure_error: SecureError):
        self.secure_error = secure_error
        super().__init__(secure_error.safe_message)
    
    def __str__(self):
        return self.secure_error.safe_message
    
    def get_details(self) -> SecureError:
        """获取详细错误信息（仅限内部使用）"""
        return self.secure_error


# 全局错误处理器实例
_global_handler: Optional[SecureErrorHandler] = None


def get_error_handler() -> SecureErrorHandler:
    """获取全局错误处理器"""
    global _global_handler
    if _global_handler is None:
        _global_handler = SecureErrorHandler()
    return _global_handler


def set_error_handler(handler: SecureErrorHandler) -> None:
    """设置全局错误处理器"""
    global _global_handler
    _global_handler = handler
