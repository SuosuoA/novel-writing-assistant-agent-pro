"""
日志服务 - 按日期滚动的日志系统

V1.1版本（评审后修订版）
创建日期：2026-03-22
修订日期：2026-03-22

特性：
- 按日期滚动的日志文件
- 记录关键事件（插件加载、AI请求等）
- 结构化日志格式
- 日志级别控制
- 线程安全
- 敏感信息脱敏
- 动态日志级别调整
"""

import logging
import os
import threading
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

# 导入日志脱敏模块
try:
    from .log_sanitizer import LogSanitizer, get_log_sanitizer

    LOG_SANITIZER_AVAILABLE = True
except ImportError:
    LOG_SANITIZER_AVAILABLE = False


class SanitizingLogFormatter(logging.Formatter):
    """
    自定义日志格式化器（带脱敏功能）
    """

    def __init__(self, *args, sanitizer=None, **kwargs):
        """
        初始化格式化器

        Args:
            sanitizer: 日志脱敏器实例
        """
        super().__init__(*args, **kwargs)
        self._sanitizer = sanitizer

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        # 添加额外字段
        if not hasattr(record, "event_type"):
            record.event_type = "general"

        # 格式化消息
        formatted = super().format(record)

        # 脱敏处理
        if self._sanitizer:
            formatted = self._sanitizer.sanitize(formatted)

        return formatted


class LogFormatter(logging.Formatter):
    """自定义日志格式化器（无脱敏）"""

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        # 添加额外字段
        if not hasattr(record, "event_type"):
            record.event_type = "general"

        return super().format(record)


class LoggingService:
    """
    日志服务

    提供按日期滚动的日志记录功能，支持敏感信息脱敏
    """

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        log_level: str = "INFO",
        app_name: str = "NovelAssistant",
        enable_sanitization: bool = True,
    ):
        """
        初始化日志服务

        Args:
            log_dir: 日志目录（可选，默认为项目根目录下的 logs 文件夹）
            log_level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
            app_name: 应用名称
            enable_sanitization: 是否启用日志脱敏
        """
        self._lock = threading.RLock()
        self._app_name = app_name
        self._initialized = False
        self._enable_sanitization = enable_sanitization

        # 确定日志目录
        if log_dir is None:
            project_root = Path(__file__).parent.parent
            log_dir = project_root / "logs"

        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

        # 设置日志级别
        self._log_level = getattr(logging, log_level.upper(), logging.INFO)
        self._log_level_str = log_level.upper()

        # 初始化日志脱敏器
        self._sanitizer = None
        if enable_sanitization and LOG_SANITIZER_AVAILABLE:
            try:
                self._sanitizer = get_log_sanitizer()
            except Exception:
                pass  # 脱敏器初始化失败不影响日志服务

        # 初始化日志器
        self._logger = logging.getLogger(app_name)
        self._logger.setLevel(self._log_level)

        # 避免重复添加 handler
        if not self._logger.handlers:
            self._setup_handlers()

        self._initialized = True

    def _setup_handlers(self) -> None:
        """设置日志处理器"""
        # 日志格式
        if self._sanitizer:
            formatter = SanitizingLogFormatter(
                fmt="%(asctime)s - %(name)s - %(levelname)s - [%(event_type)s] - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                sanitizer=self._sanitizer,
            )
        else:
            formatter = LogFormatter(
                fmt="%(asctime)s - %(name)s - %(levelname)s - [%(event_type)s] - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self._log_level)
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

        # 文件处理器（按日期滚动）
        log_file = self._log_dir / f"{self._app_name}.log"
        file_handler = TimedRotatingFileHandler(
            filename=str(log_file),
            when="midnight",  # 每天午夜滚动
            interval=1,
            backupCount=30,  # 保留30天的日志
            encoding="utf-8",
        )
        file_handler.setLevel(self._log_level)
        file_handler.setFormatter(formatter)
        file_handler.suffix = "%Y-%m-%d"  # 日志文件后缀格式
        self._logger.addHandler(file_handler)

    def set_level(self, level: str) -> None:
        """
        动态设置日志级别

        Args:
            level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
        """
        with self._lock:
            new_level = getattr(logging, level.upper(), logging.INFO)
            self._log_level = new_level
            self._log_level_str = level.upper()
            self._logger.setLevel(new_level)

            # 更新所有 handler 的级别
            for handler in self._logger.handlers:
                handler.setLevel(new_level)

    def get_level(self) -> str:
        """
        获取当前日志级别

        Returns:
            日志级别字符串
        """
        return self._log_level_str

    def log_plugin_event(
        self, event_type: str, plugin_name: str, message: str, level: str = "INFO"
    ) -> None:
        """
        记录插件事件

        Args:
            event_type: 事件类型（loaded/unloaded/activated/deactivated/error）
            plugin_name: 插件名称
            message: 日志消息
            level: 日志级别
        """
        extra = {"event_type": f"plugin.{event_type}"}
        log_method = getattr(self._logger, level.lower(), self._logger.info)
        log_method(f"[Plugin:{plugin_name}] {message}", extra=extra)

    def log_ai_request(
        self,
        provider: str,
        model: str,
        request_type: str,
        message: str,
        level: str = "INFO",
    ) -> None:
        """
        记录AI请求事件

        Args:
            provider: 服务提供商
            model: 模型名称
            request_type: 请求类型
            message: 日志消息
            level: 日志级别
        """
        extra = {"event_type": f"ai.{request_type}"}
        log_method = getattr(self._logger, level.lower(), self._logger.info)
        log_method(f"[AI:{provider}/{model}] {message}", extra=extra)

    def log_generation_event(
        self, event_type: str, request_id: str, message: str, level: str = "INFO"
    ) -> None:
        """
        记录生成事件

        Args:
            event_type: 事件类型（started/progress/completed/error）
            request_id: 请求ID
            message: 日志消息
            level: 日志级别
        """
        extra = {"event_type": f"generation.{event_type}"}
        log_method = getattr(self._logger, level.lower(), self._logger.info)
        log_method(f"[Generation:{request_id}] {message}", extra=extra)

    def log_config_event(
        self, event_type: str, key: str, message: str, level: str = "INFO"
    ) -> None:
        """
        记录配置事件

        Args:
            event_type: 事件类型（loaded/changed/reload）
            key: 配置键
            message: 日志消息
            level: 日志级别
        """
        extra = {"event_type": f"config.{event_type}"}
        log_method = getattr(self._logger, level.lower(), self._logger.info)
        log_method(f"[Config:{key}] {message}", extra=extra)

    def log_system_event(
        self, event_type: str, message: str, level: str = "INFO"
    ) -> None:
        """
        记录系统事件

        Args:
            event_type: 事件类型（startup/shutdown/error）
            message: 日志消息
            level: 日志级别
        """
        extra = {"event_type": f"system.{event_type}"}
        log_method = getattr(self._logger, level.lower(), self._logger.info)
        log_method(message, extra=extra)

    def debug(self, message: str, **kwargs) -> None:
        """记录DEBUG日志"""
        self._logger.debug(message, extra=kwargs)

    def info(self, message: str, **kwargs) -> None:
        """记录INFO日志"""
        self._logger.info(message, extra=kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """记录WARNING日志"""
        self._logger.warning(message, extra=kwargs)

    def error(self, message: str, **kwargs) -> None:
        """记录ERROR日志"""
        self._logger.error(message, extra=kwargs)

    def critical(self, message: str, **kwargs) -> None:
        """记录CRITICAL日志"""
        self._logger.critical(message, extra=kwargs)

    def get_logger(self) -> logging.Logger:
        """
        获取底层 Logger 实例

        Returns:
            Logger 实例
        """
        return self._logger

    def get_log_dir(self) -> Path:
        """
        获取日志目录

        Returns:
            日志目录路径
        """
        return self._log_dir


# 全局单例
_logging_service_instance: Optional[LoggingService] = None
_logging_service_lock = threading.Lock()


def get_logging_service() -> LoggingService:
    """获取全局 LoggingService 实例"""
    global _logging_service_instance
    if _logging_service_instance is None:
        with _logging_service_lock:
            if _logging_service_instance is None:
                _logging_service_instance = LoggingService()
    return _logging_service_instance
