"""
敏感信息脱敏工具

V1.0版本
创建日期：2026-03-23

特性：
- 自动检测敏感字段
- 日志脱敏过滤器
- 配置导出脱敏
- 字符串掩码处理
"""

import re
import logging
from typing import Any, Dict, List, Optional, Set, Union


class SensitiveDataMasker:
    """
    敏感数据脱敏器

    P1-3修复：完善敏感信息脱敏
    """

    # 敏感字段名模式（不区分大小写）
    SENSITIVE_PATTERNS = [
        r'password',
        r'passwd',
        r'pwd',
        r'secret',
        r'token',
        r'api[_-]?key',
        r'access[_-]?key',
        r'private[_-]?key',
        r'auth[_-]?token',
        r'bearer',
        r'credential',
        r'session[_-]?id',
        r'cookie',
        r'jwt',
        r'refresh[_-]?token',
        r'client[_-]?secret',
        r'consumer[_-]?secret',
        r'signature',
    ]

    # 编译正则表达式
    _SENSITIVE_RE = re.compile(
        '|'.join(SENSITIVE_PATTERNS),
        re.IGNORECASE
    )

    # 脱敏后显示的字符
    MASK_CHAR = '***REDACTED***'

    # 部分脱敏：保留前缀
    PARTIAL_MASK_PREFIX_LEN = 4
    PARTIAL_MASK_SUFFIX_LEN = 4

    @classmethod
    def is_sensitive_key(cls, key: str) -> bool:
        """
        检查键名是否是敏感字段

        Args:
            key: 字段名

        Returns:
            是否是敏感字段
        """
        return bool(cls._SENSITIVE_RE.search(key))

    @classmethod
    def mask_value(cls, value: str, partial: bool = False) -> str:
        """
        脱敏字符串值

        Args:
            value: 原始值
            partial: 是否部分脱敏（保留前后各4个字符）

        Returns:
            脱敏后的值
        """
        if not isinstance(value, str):
            value = str(value)

        if not value:
            return value

        if partial and len(value) > cls.PARTIAL_MASK_PREFIX_LEN + cls.PARTIAL_MASK_SUFFIX_LEN:
            prefix = value[:cls.PARTIAL_MASK_PREFIX_LEN]
            suffix = value[-cls.PARTIAL_MASK_SUFFIX_LEN:]
            return f"{prefix}...{suffix}"
        else:
            return cls.MASK_CHAR

    @classmethod
    def mask_dict(
        cls,
        data: Dict[str, Any],
        sensitive_keys: Optional[Set[str]] = None,
        deep: bool = True
    ) -> Dict[str, Any]:
        """
        脱敏字典中的敏感数据

        Args:
            data: 原始字典
            sensitive_keys: 额外的敏感键名集合
            deep: 是否递归处理嵌套字典

        Returns:
            脱敏后的字典副本
        """
        result = {}
        extra_keys = sensitive_keys or set()

        for key, value in data.items():
            # 检查是否是敏感字段
            is_sensitive = (
                cls.is_sensitive_key(key) or
                key.lower() in extra_keys or
                key in extra_keys
            )

            if is_sensitive:
                if isinstance(value, str):
                    result[key] = cls.mask_value(value, partial=True)
                else:
                    result[key] = cls.MASK_CHAR
            elif deep and isinstance(value, dict):
                result[key] = cls.mask_dict(value, sensitive_keys, deep=True)
            elif deep and isinstance(value, list):
                result[key] = [
                    cls.mask_dict(item, sensitive_keys, deep=True)
                    if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value

        return result

    @classmethod
    def mask_string(cls, text: str, patterns: Optional[List[str]] = None) -> str:
        """
        脱敏字符串中的敏感信息

        Args:
            text: 原始字符串
            patterns: 额外的敏感信息正则模式列表

        Returns:
            脱敏后的字符串
        """
        result = text

        # 默认敏感模式
        default_patterns = [
            # API Key格式
            (r'(sk-[a-zA-Z0-9]{20,})', r'sk-***REDACTED***'),
            # Bearer Token
            (r'(Bearer\s+)[a-zA-Z0-9_\-\.]+', r'\1***REDACTED***'),
            # JWT Token
            (r'(eyJ[a-zA-Z0-9_-]*)\.[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*', r'\1.***REDACTED***'),
            # 密码字段
            (r'(password["\s:=]+)["\']?[^"\s,}]+["\']?', r'\1"***REDACTED***"'),
            # API Key字段
            (r'(api[_-]?key["\s:=]+)["\']?[^"\s,}]+["\']?', r'\1"***REDACTED***"'),
        ]

        all_patterns = default_patterns + (patterns or [])

        for pattern, replacement in all_patterns:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        return result


class SensitiveDataFilter(logging.Filter):
    """
    日志敏感信息过滤器

    P1-3修复：防止敏感信息泄露到日志
    P1-11修复：添加审计日志记录敏感数据访问
    """

    # P1-11修复：审计日志器
    _audit_logger = None

    def __init__(self, name: str = 'SensitiveDataFilter'):
        super().__init__(name)
        self._masker = SensitiveDataMasker()
        self._sensitive_count = 0  # P1-11修复：统计脱敏次数

    @classmethod
    def _get_audit_logger(cls) -> logging.Logger:
        """获取审计日志器"""
        if cls._audit_logger is None:
            cls._audit_logger = logging.getLogger('audit.sensitive_data')
        return cls._audit_logger

    def filter(self, record: logging.LogRecord) -> bool:
        """过滤日志记录中的敏感信息"""
        has_sensitive = False

        # 脱敏消息
        if record.msg and isinstance(record.msg, str):
            original = record.msg
            record.msg = self._masker.mask_string(record.msg)
            if original != record.msg:
                has_sensitive = True

        # 脱敏参数
        if record.args:
            if isinstance(record.args, dict):
                original_args = str(record.args)
                record.args = self._masker.mask_dict(record.args)
                if str(record.args) != original_args:
                    has_sensitive = True
            elif isinstance(record.args, tuple):
                new_args = []
                for arg in record.args:
                    if isinstance(arg, str):
                        masked = self._masker.mask_string(arg)
                        if masked != arg:
                            has_sensitive = True
                        new_args.append(masked)
                    else:
                        new_args.append(arg)
                record.args = tuple(new_args)

        # P1-11修复：记录审计日志
        if has_sensitive:
            self._sensitive_count += 1
            audit_logger = self._get_audit_logger()
            audit_logger.info(
                f"Sensitive data masked in log: "
                f"logger={record.name}, "
                f"level={record.levelname}, "
                f"file={record.filename}:{record.lineno}, "
                f"total_count={self._sensitive_count}"
            )

        return True


def setup_sensitive_data_logging():
    """
    配置日志系统以自动脱敏敏感信息

    使用方法：
        from core.sensitive_data import setup_sensitive_data_logging
        setup_sensitive_data_logging()
    """
    # 获取根日志器
    root_logger = logging.getLogger()

    # 添加敏感信息过滤器
    sensitive_filter = SensitiveDataFilter()

    # 添加到所有handler
    for handler in root_logger.handlers:
        handler.addFilter(sensitive_filter)

    # 同时添加到根日志器
    root_logger.addFilter(sensitive_filter)


# 便捷函数
def mask_sensitive(data: Union[Dict, str, Any]) -> Union[Dict, str, Any]:
    """
    便捷脱敏函数

    Args:
        data: 要脱敏的数据（字典或字符串）

    Returns:
        脱敏后的数据
    """
    if isinstance(data, dict):
        return SensitiveDataMasker.mask_dict(data)
    elif isinstance(data, str):
        return SensitiveDataMasker.mask_string(data)
    else:
        return data


def is_sensitive(key: str) -> bool:
    """
    检查键名是否是敏感字段

    Args:
        key: 字段名

    Returns:
        是否是敏感字段
    """
    return SensitiveDataMasker.is_sensitive_key(key)
