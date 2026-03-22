"""
核心启动服务 - 集成配置和日志服务

V1.0版本
创建日期：2026-03-22

特性：
- 初始化 ConfigService 并注册到 ServiceLocator
- 初始化 LoggingService 并注册到 ServiceLocator
- 按依赖顺序启动核心服务
- 提供统一的启动入口
"""

import logging
import threading
from pathlib import Path
from typing import Dict, Optional

from .config_service import ConfigService, get_config_service
from .logging_service import LoggingService, get_logging_service
from .service_locator import ServiceLocator, get_service_locator


class BootstrapService:
    """
    启动服务

    负责初始化和注册核心服务
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        初始化启动服务

        Args:
            config_path: 配置文件路径（可选）
        """
        self._lock = threading.RLock()
        self._config_path = config_path
        self._initialized = False
        self._service_locator = get_service_locator()

    def initialize(self) -> Dict[str, bool]:
        """
        初始化核心服务

        P1-7修复：关键服务失败时终止初始化，保持状态一致性

        Returns:
            初始化结果 {service_name: bool}
        """
        with self._lock:
            if self._initialized:
                return {"already_initialized": True}

            results: Dict[str, bool] = {}

            # 1. 初始化并注册 ConfigService（必需服务）
            try:
                config_service = get_config_service()
                self._service_locator.register(
                    service_type=ConfigService,
                    instance=config_service,
                )
                results["ConfigService"] = True

                # 获取日志级别
                config = config_service.get_config()
                log_level = "DEBUG" if config.ai_learning else "INFO"

            except Exception as e:
                results["ConfigService"] = False
                logging.error(f"ConfigService初始化失败，终止启动: {e}", exc_info=True)
                # P1-7修复：关键服务失败，不继续初始化依赖服务
                self._initialized = False
                return results

            # 2. 初始化并注册 LoggingService（依赖ConfigService）
            try:
                logging_service = get_logging_service()
                self._service_locator.register(
                    service_type=LoggingService,
                    instance=logging_service,
                )
                results["LoggingService"] = True

                # 记录启动事件
                logging_service.log_system_event(
                    event_type="startup",
                    message="核心服务启动完成",
                    level="INFO",
                )

            except Exception as e:
                results["LoggingService"] = False
                logging.error(f"LoggingService初始化失败: {e}", exc_info=True)
                # LoggingService失败不影响核心功能，继续标记为已初始化

            # P1-7修复：只有ConfigService成功才标记为已初始化
            self._initialized = results.get("ConfigService", False)
            return results

    def dispose(self) -> Dict[str, bool]:
        """
        释放核心服务

        Returns:
            释放结果 {service_name: bool}
        """
        with self._lock:
            if not self._initialized:
                return {"not_initialized": True}

            results: Dict[str, bool] = {}

            # 记录关闭事件
            try:
                logging_service = self._service_locator.try_get(LoggingService)
                if logging_service:
                    logging_service.log_system_event(
                        event_type="shutdown",
                        message="核心服务关闭",
                        level="INFO",
                    )
            except Exception:
                pass

            # 逆序释放服务
            try:
                self._service_locator.unregister(LoggingService)
                results["LoggingService"] = True
            except Exception as e:
                results["LoggingService"] = False
                logging.error(f"Failed to dispose LoggingService: {e}")

            try:
                self._service_locator.unregister(ConfigService)
                results["ConfigService"] = True
            except Exception as e:
                results["ConfigService"] = False
                logging.error(f"Failed to dispose ConfigService: {e}")

            self._initialized = False
            return results

    def is_initialized(self) -> bool:
        """
        检查是否已初始化

        Returns:
            是否已初始化
        """
        return self._initialized


# 全局单例
_bootstrap_instance: Optional[BootstrapService] = None
_bootstrap_lock = threading.Lock()


def get_bootstrap_service() -> BootstrapService:
    """获取全局 BootstrapService 实例"""
    global _bootstrap_instance
    if _bootstrap_instance is None:
        with _bootstrap_lock:
            if _bootstrap_instance is None:
                _bootstrap_instance = BootstrapService()
    return _bootstrap_instance


def initialize_core_services() -> Dict[str, bool]:
    """
    初始化核心服务（便捷函数）

    Returns:
        初始化结果
    """
    bootstrap = get_bootstrap_service()
    return bootstrap.initialize()


def dispose_core_services() -> Dict[str, bool]:
    """
    释放核心服务（便捷函数）

    Returns:
        释放结果
    """
    bootstrap = get_bootstrap_service()
    return bootstrap.dispose()
