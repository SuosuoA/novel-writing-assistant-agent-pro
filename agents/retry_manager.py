"""
重试管理器

V2.0版本
创建日期: 2026-03-21

特性:
- 指数退避策略
- 抖动机制
- 可配置重试次数
"""

import random
import time
import threading
from typing import Callable, Type, Any, Optional, Tuple
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class RetryPolicy(Enum):
    """重试策略"""

    EXPONENTIAL = "exponential"  # 指数退避
    LINEAR = "linear"  # 线性退避
    IMMEDIATE = "immediate"  # 立即重试
    FIXED = "fixed"  # 固定间隔


@dataclass
class RetryConfig:
    """重试配置"""

    max_attempts: int = 3  # 最大重试次数
    base_delay: float = 1.0  # 基础延迟(秒)
    max_delay: float = 60.0  # 最大延迟(秒)
    policy: RetryPolicy = RetryPolicy.EXPONENTIAL
    jitter: bool = True  # 是否添加随机抖动
    backoff_multiplier: float = 2.0  # 退避倍数
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
    )


class RetryManager:
    """
    重试管理器

    实现指数退避+抖动重试策略
    """

    def __init__(self, config: RetryConfig = None):
        """
        初始化重试管理器

        Args:
            config: 重试配置
        """
        self._config = config or RetryConfig()

    def calculate_delay(self, attempt: int) -> float:
        """
        计算重试延迟

        Args:
            attempt: 当前尝试次数

        Returns:
            延迟时间（秒）
        """
        if self._config.policy == RetryPolicy.EXPONENTIAL:
            delay = self._config.base_delay * (self._config.backoff_multiplier**attempt)
        elif self._config.policy == RetryPolicy.LINEAR:
            delay = self._config.base_delay * (attempt + 1)
        elif self._config.policy == RetryPolicy.FIXED:
            delay = self._config.base_delay
        else:  # IMMEDIATE
            delay = 0

        # 限制最大延迟
        delay = min(delay, self._config.max_delay)

        # 添加随机抖动(避免惊群效应)
        if self._config.jitter and delay > 0:
            delay = delay * random.uniform(0.8, 1.2)

        return delay

    def execute_with_retry(self, func: Callable, *args, **kwargs) -> Tuple[Any, int]:
        """
        执行函数并自动重试(同步版本)

        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            (结果, 实际重试次数)

        Raises:
            最后一次异常(如果所有重试都失败)
        """
        last_exception = None

        for attempt in range(self._config.max_attempts):
            try:
                result = func(*args, **kwargs)
                return result, attempt

            except self._config.retryable_exceptions as e:
                last_exception = e
                logger.warning(
                    f"执行失败(尝试 {attempt + 1}/{self._config.max_attempts}): {e}"
                )

                # 最后一次尝试不等待
                if attempt < self._config.max_attempts - 1:
                    delay = self.calculate_delay(attempt)
                    logger.info(f"等待 {delay:.2f}秒后重试...")
                    time.sleep(delay)
                else:
                    logger.error("所有重试尝试均失败")
                    raise

            except Exception as e:
                # 非重试异常直接抛出
                logger.error(f"非重试异常: {e}")
                raise

        # 理论上不会到达这里
        raise last_exception
