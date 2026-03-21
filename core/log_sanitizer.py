"""
日志脱敏 - 敏感信息过滤

V1.2新增模块
创建日期：2026-03-21

特性：
- 敏感信息自动检测
- 多种脱敏模式
- 可配置规则
"""

import logging
import re
from typing import Any, Dict, List, Optional, Pattern, Set


class LogSanitizer:
    """
    日志脱敏器
    
    自动检测和脱敏日志中的敏感信息
    """
    
    # 默认敏感字段模式
    DEFAULT_SENSITIVE_PATTERNS = [
        r"api[_-]?key",
        r"secret[_-]?key",
        r"access[_-]?token",
        r"auth[_-]?token",
        r"password",
        r"passwd",
        r"pwd",
        r"private[_-]?key",
        r"credential",
    ]
    
    # 默认脱敏规则
    DEFAULT_SANITIZE_RULES = {
        "api_key": {
            "pattern": r"(api[_-]?key\s*[=:]\s*)['\"]?([a-zA-Z0-9_-]+)['\"]?",
            "replacement": r"\1***REDACTED***"
        },
        "password": {
            "pattern": r"(password\s*[=:]\s*)['\"]?[^'\"]+['\"]?",
            "replacement": r"\1***REDACTED***"
        },
        "token": {
            "pattern": r"(token\s*[=:]\s*)['\"]?([a-zA-Z0-9_.-]+)['\"]?",
            "replacement": r"\1***REDACTED***"
        },
        "email": {
            "pattern": r"([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",
            "replacement": r"***@\2"
        },
        "phone": {
            "pattern": r"(\d{3})\d{4}(\d{4})",
            "replacement": r"\1****\2"
        },
        "credit_card": {
            "pattern": r"(\d{4})\d{8,11}(\d{4})",
            "replacement": r"\1********\2"
        },
        "id_card": {
            "pattern": r"(\d{4})\d{10,13}(\d{4})",
            "replacement": r"\1**********\2"
        },
    }
    
    def __init__(
        self,
        custom_patterns: Optional[List[str]] = None,
        custom_rules: Optional[Dict[str, Dict[str, str]]] = None
    ):
        """
        初始化日志脱敏器
        
        Args:
            custom_patterns: 自定义敏感字段模式
            custom_rules: 自定义脱敏规则
        """
        # 编译敏感字段模式
        patterns = self.DEFAULT_SENSITIVE_PATTERNS.copy()
        if custom_patterns:
            patterns.extend(custom_patterns)
        
        self._sensitive_pattern = re.compile(
            "|".join(patterns),
            re.IGNORECASE
        )
        
        # 编译脱敏规则
        self._rules: Dict[str, Pattern] = {}
        rules = {**self.DEFAULT_SANITIZE_RULES, **(custom_rules or {})}
        
        for name, rule in rules.items():
            self._rules[name] = {
                "pattern": re.compile(rule["pattern"], re.IGNORECASE),
                "replacement": rule["replacement"]
            }
    
    def sanitize(self, message: str) -> str:
        """
        脱敏消息
        
        Args:
            message: 原始消息
        
        Returns:
            脱敏后的消息
        """
        if not message:
            return message
        
        result = message
        
        # 应用所有脱敏规则
        for name, rule in self._rules.items():
            try:
                result = rule["pattern"].sub(rule["replacement"], result)
            except Exception:
                pass  # 规则应用失败不影响其他规则
        
        return result
    
    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        脱敏字典数据
        
        Args:
            data: 原始字典
        
        Returns:
            脱敏后的字典
        """
        result: Dict[str, Any] = {}
        
        for key, value in data.items():
            # 检查键是否敏感
            if self._is_sensitive_key(key):
                result[key] = "***REDACTED***"
            elif isinstance(value, dict):
                result[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                result[key] = self.sanitize_list(value)
            elif isinstance(value, str):
                result[key] = self.sanitize(value)
            else:
                result[key] = value
        
        return result
    
    def sanitize_list(self, data: List[Any]) -> List[Any]:
        """
        脱敏列表数据
        
        Args:
            data: 原始列表
        
        Returns:
            脱敏后的列表
        """
        result: List[Any] = []
        
        for item in data:
            if isinstance(item, dict):
                result.append(self.sanitize_dict(item))
            elif isinstance(item, list):
                result.append(self.sanitize_list(item))
            elif isinstance(item, str):
                result.append(self.sanitize(item))
            else:
                result.append(item)
        
        return result
    
    def is_sensitive(self, message: str) -> bool:
        """
        检查消息是否包含敏感信息
        
        Args:
            message: 消息内容
        
        Returns:
            是否包含敏感信息
        """
        return bool(self._sensitive_pattern.search(message))
    
    def _is_sensitive_key(self, key: str) -> bool:
        """
        检查键名是否敏感
        
        Args:
            key: 键名
        
        Returns:
            是否敏感
        """
        return bool(self._sensitive_pattern.search(key))


class SanitizingFormatter(logging.Formatter):
    """
    日志格式化器（带脱敏）
    
    自动脱敏日志消息中的敏感信息
    """
    
    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        sanitizer: Optional[LogSanitizer] = None
    ):
        """
        初始化格式化器
        
        Args:
            fmt: 格式字符串
            datefmt: 日期格式
            sanitizer: 脱敏器实例
        """
        super().__init__(fmt, datefmt)
        self._sanitizer = sanitizer or LogSanitizer()
    
    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录（带脱敏）
        
        Args:
            record: 日志记录
        
        Returns:
            格式化后的字符串
        """
        # 脱敏消息
        record.msg = self._sanitizer.sanitize(str(record.msg))
        
        # 脱敏参数
        if record.args:
            if isinstance(record.args, dict):
                record.args = self._sanitizer.sanitize_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._sanitizer.sanitize(str(arg))
                    if isinstance(arg, str) else arg
                    for arg in record.args
                )
        
        return super().format(record)


# 全局脱敏器
_sanitizer_instance: Optional[LogSanitizer] = None


def get_log_sanitizer() -> LogSanitizer:
    """获取全局日志脱敏器"""
    global _sanitizer_instance
    if _sanitizer_instance is None:
        _sanitizer_instance = LogSanitizer()
    return _sanitizer_instance
