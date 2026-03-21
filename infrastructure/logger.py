"""
结构化日志系统

V1.0版本
创建日期: 2026-03-21

特性：
- 结构化JSON格式日志
- 敏感信息自动脱敏
- 日志轮转与归档
- 多日志级别支持
"""

import logging
import json
import sys
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, Optional
import threading
from logging.handlers import RotatingFileHandler


class LogLevel(IntEnum):
    """日志级别"""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class StructuredFormatter(logging.Formatter):
    """
    结构化日志格式化器
    
    输出JSON格式的日志，便于解析和分析
    """
    
    SENSITIVE_FIELDS = {
        "password", "token", "secret", "api_key", "apikey",
        "authorization", "credential", "private_key"
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # 添加额外字段
        if hasattr(record, "extra_data"):
            extra = self._sanitize(record.extra_data)
            log_data["extra"] = extra
        
        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)
    
    def _sanitize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """脱敏敏感字段"""
        result = {}
        for key, value in data.items():
            if key.lower() in self.SENSITIVE_FIELDS:
                result[key] = "***MASKED***"
            elif isinstance(value, dict):
                result[key] = self._sanitize(value)
            else:
                result[key] = value
        return result


class StructuredLogger:
    """
    结构化日志器
    
    提供结构化日志记录功能，支持：
    - JSON格式输出
    - 敏感信息自动脱敏
    - 上下文信息附加
    """
    
    def __init__(self, name: str, level: LogLevel = LogLevel.INFO):
        """
        初始化日志器
        
        Args:
            name: 日志器名称
            level: 日志级别
        """
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._context: Dict[str, Any] = {}
        self._lock = threading.Lock()
    
    def set_context(self, **kwargs: Any) -> None:
        """设置上下文信息"""
        with self._lock:
            self._context.update(kwargs)
    
    def clear_context(self) -> None:
        """清除上下文信息"""
        with self._lock:
            self._context.clear()
    
    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        """内部日志方法"""
        extra_data = {**self._context, **kwargs}
        self._logger.log(level, message, extra={"extra_data": extra_data})
    
    def debug(self, message: str, **kwargs: Any) -> None:
        """调试日志"""
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs: Any) -> None:
        """信息日志"""
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs: Any) -> None:
        """警告日志"""
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, exc_info: bool = False, **kwargs: Any) -> None:
        """错误日志"""
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs: Any) -> None:
        """严重错误日志"""
        self._log(logging.CRITICAL, message, **kwargs)
    
    def exception(self, message: str, **kwargs: Any) -> None:
        """异常日志（自动包含堆栈跟踪）"""
        self._logger.exception(message, extra={"extra_data": {**self._context, **kwargs}})


# 全局日志器缓存
_loggers: Dict[str, StructuredLogger] = {}
_loggers_lock = threading.Lock()

# 默认配置
_default_log_dir: Optional[Path] = None
_default_log_level: LogLevel = LogLevel.INFO
_initialized = False


def setup_logging(
    log_dir: Optional[Path] = None,
    level: LogLevel = LogLevel.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    console_output: bool = True,
) -> None:
    """
    配置日志系统
    
    Args:
        log_dir: 日志文件目录
        level: 日志级别
        max_bytes: 单个日志文件最大大小
        backup_count: 保留的日志文件数量
        console_output: 是否输出到控制台
    """
    global _default_log_dir, _default_log_level, _initialized
    
    _default_log_dir = log_dir
    _default_log_level = level
    
    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 清除已有的处理器
    root_logger.handlers.clear()
    
    # 结构化格式化器
    formatter = StructuredFormatter()
    
    # 控制台处理器
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # 文件处理器
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / "app.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    _initialized = True


def get_logger(name: str) -> StructuredLogger:
    """
    获取日志器
    
    Args:
        name: 日志器名称
    
    Returns:
        StructuredLogger实例
    """
    with _loggers_lock:
        if name not in _loggers:
            _loggers[name] = StructuredLogger(name, _default_log_level)
        return _loggers[name]
