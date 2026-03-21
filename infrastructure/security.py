"""
安全工具模块

V1.0版本
创建日期: 2026-03-21

特性：
- 敏感信息脱敏
- 数据清洗
- 安全模式匹配
"""

import re
from typing import Any, Dict, List, Optional, Set, Pattern
import threading


# 预定义的敏感字段模式
SECURITY_PATTERNS = {
    # API密钥
    "api_key": re.compile(r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"]?([a-zA-Z0-9_-]{20,})['\"]?"),
    # 密码
    "password": re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"]?([^'\"\s]{6,})['\"]?"),
    # Token
    "token": re.compile(r"(?i)(token|access_token|auth_token)\s*[=:]\s*['\"]?([a-zA-Z0-9_.-]{20,})['\"]?"),
    # 私钥
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"),
    # 数据库连接串
    "connection_string": re.compile(r"(?i)(connectionstring|connstr)\s*[=:]\s*['\"]?([^'\"\s]{10,})['\"]?"),
    # 邮箱
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    # 手机号（中国）
    "phone_cn": re.compile(r"1[3-9]\d{9}"),
    # 身份证号
    "id_card_cn": re.compile(r"\d{17}[\dXx]"),
    # 银行卡号
    "bank_card": re.compile(r"\d{15,19}"),
}


class SensitiveDataFilter:
    """
    敏感数据过滤器
    
    用于检测和脱敏文本中的敏感信息
    """
    
    # 默认敏感字段名
    DEFAULT_SENSITIVE_FIELDS = {
        "password", "passwd", "pwd",
        "token", "access_token", "auth_token", "refresh_token",
        "api_key", "apikey", "api_secret",
        "secret", "secret_key",
        "private_key", "privatekey",
        "authorization", "credential", "credentials",
        "session_id", "sessionid",
        "cookie", "cookies",
    }
    
    def __init__(
        self,
        custom_patterns: Optional[Dict[str, Pattern]] = None,
        custom_fields: Optional[Set[str]] = None,
        mask_char: str = "*",
        visible_chars: int = 4,
    ):
        """
        初始化敏感数据过滤器
        
        Args:
            custom_patterns: 自定义模式
            custom_fields: 自定义敏感字段
            mask_char: 脱敏字符
            visible_chars: 可见字符数
        """
        self._patterns = {**SECURITY_PATTERNS, **(custom_patterns or {})}
        self._sensitive_fields = self.DEFAULT_SENSITIVE_FIELDS | (custom_fields or set())
        self._mask_char = mask_char
        self._visible_chars = visible_chars
        self._lock = threading.Lock()
    
    def add_pattern(self, name: str, pattern: Pattern) -> None:
        """添加模式"""
        with self._lock:
            self._patterns[name] = pattern
    
    def add_sensitive_field(self, field_name: str) -> None:
        """添加敏感字段"""
        with self._lock:
            self._sensitive_fields.add(field_name.lower())
    
    def mask_text(self, text: str, patterns: Optional[List[str]] = None) -> str:
        """
        脱敏文本
        
        Args:
            text: 原始文本
            patterns: 要应用的模式列表（None表示全部）
        
        Returns:
            脱敏后的文本
        """
        result = text
        patterns_to_apply = patterns or list(self._patterns.keys())
        
        with self._lock:
            for pattern_name in patterns_to_apply:
                if pattern_name in self._patterns:
                    pattern = self._patterns[pattern_name]
                    result = self._mask_matches(result, pattern)
        
        return result
    
    def _mask_matches(self, text: str, pattern: Pattern) -> str:
        """脱敏匹配内容"""
        def replace_fn(match):
            matched_text = match.group(0)
            if len(matched_text) <= self._visible_chars * 2:
                return self._mask_char * len(matched_text)
            
            visible_start = matched_text[:self._visible_chars]
            visible_end = matched_text[-self._visible_chars:]
            mask_length = len(matched_text) - self._visible_chars * 2
            return f"{visible_start}{self._mask_char * mask_length}{visible_end}"
        
        return pattern.sub(replace_fn, text)
    
    def mask_dict(
        self, data: Dict[str, Any], deep: bool = True
    ) -> Dict[str, Any]:
        """
        脱敏字典数据
        
        Args:
            data: 原始数据
            deep: 是否深度脱敏（递归处理嵌套字典）
        
        Returns:
            脱敏后的数据
        """
        result = {}
        
        for key, value in data.items():
            lower_key = key.lower()
            
            # 检查是否是敏感字段
            if lower_key in self._sensitive_fields:
                result[key] = self._mask_value(str(value))
            elif isinstance(value, str):
                # 对字符串值进行模式匹配脱敏
                result[key] = self.mask_text(value)
            elif isinstance(value, dict) and deep:
                # 递归处理嵌套字典
                result[key] = self.mask_dict(value, deep=True)
            elif isinstance(value, list) and deep:
                # 处理列表
                result[key] = [
                    self.mask_dict(item, deep=True) if isinstance(item, dict)
                    else self.mask_text(item) if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        
        return result
    
    def _mask_value(self, value: str) -> str:
        """脱敏单个值"""
        if len(value) <= self._visible_chars:
            return self._mask_char * len(value)
        
        visible_start = value[:self._visible_chars]
        mask_length = len(value) - self._visible_chars
        return f"{visible_start}{self._mask_char * mask_length}"
    
    def detect_sensitive(self, text: str) -> List[Dict[str, Any]]:
        """
        检测敏感信息
        
        Args:
            text: 要检测的文本
        
        Returns:
            检测到的敏感信息列表
        """
        findings = []
        
        with self._lock:
            for pattern_name, pattern in self._patterns.items():
                for match in pattern.finditer(text):
                    findings.append({
                        "type": pattern_name,
                        "value": match.group(0),
                        "start": match.start(),
                        "end": match.end(),
                    })
        
        return findings


def mask_sensitive(
    data: Any,
    patterns: Optional[List[str]] = None,
    deep: bool = True,
) -> Any:
    """
    脱敏敏感信息的便捷函数
    
    Args:
        data: 要脱敏的数据（字符串或字典）
        patterns: 要应用的模式列表
        deep: 是否深度脱敏
    
    Returns:
        脱敏后的数据
    """
    filter_instance = SensitiveDataFilter()
    
    if isinstance(data, str):
        return filter_instance.mask_text(data, patterns)
    elif isinstance(data, dict):
        return filter_instance.mask_dict(data, deep)
    else:
        return data


def sanitize_data(
    data: Dict[str, Any],
    sensitive_fields: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    清洗数据（移除或脱敏敏感字段）
    
    Args:
        data: 原始数据
        sensitive_fields: 额外的敏感字段
    
    Returns:
        清洗后的数据
    """
    filter_instance = SensitiveDataFilter(
        custom_fields=sensitive_fields
    )
    return filter_instance.mask_dict(data, deep=True)
