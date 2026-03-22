"""
配置服务 - 封装 config.yaml 读取，通过 ServiceLocator 提供

V1.1版本（评审后修订版）
创建日期：2026-03-22
修订日期：2026-03-22

特性：
- 封装 ConfigManager，提供配置读取服务
- 支持 Pydantic 模型验证（含字段验证器）
- 线程安全
- 通过 ServiceLocator 注册和获取
- 配置变更EventBus通知
"""

import re
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .config_manager import ConfigManager, get_config_manager


class AppConfig(BaseModel):
    """应用配置模型（含字段验证器）"""

    ai_learning: bool = Field(default=True, description="AI学习开关")
    api_key: str = Field(default="", description="API密钥")
    auto_save: bool = Field(default=True, description="自动保存")
    backup_interval: str = Field(default="30", description="备份间隔（分钟）")
    font_size: str = Field(default="19", description="字体大小")
    local_url: str = Field(
        default="http://localhost:11434/v1", description="本地服务URL"
    )
    model: str = Field(default="deepseek-chat", description="模型名称")
    provider: str = Field(default="DeepSeek", description="服务提供商")
    save_path: str = Field(default="", description="保存路径")
    service_mode: str = Field(default="local", description="服务模式（local/remote）")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数（0-2）")
    theme: str = Field(default="dark", description="主题（dark/light）")
    window_size: str = Field(default="1280x720", description="窗口大小")

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """验证API密钥格式"""
        if not v:
            return v  # 空值允许
        # API密钥长度至少16字符
        if len(v) < 16:
            raise ValueError("API密钥长度不足（至少16字符）")
        # API密钥只允许字母、数字、下划线、连字符
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("API密钥格式无效（只允许字母、数字、下划线、连字符）")
        return v

    @field_validator("backup_interval")
    @classmethod
    def validate_backup_interval(cls, v: str) -> str:
        """验证备份间隔"""
        try:
            interval = int(v)
            if interval < 1 or interval > 1440:  # 1分钟到24小时
                raise ValueError("备份间隔必须在1-1440分钟之间")
        except ValueError:
            raise ValueError("备份间隔必须是数字")
        return v

    @field_validator("font_size")
    @classmethod
    def validate_font_size(cls, v: str) -> str:
        """验证字体大小"""
        try:
            size = int(v)
            if size < 8 or size > 72:
                raise ValueError("字体大小必须在8-72之间")
        except ValueError:
            raise ValueError("字体大小必须是数字")
        return v

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v: str) -> str:
        """验证主题"""
        if v not in ["dark", "light"]:
            raise ValueError("主题必须是 dark 或 light")
        return v

    @field_validator("service_mode")
    @classmethod
    def validate_service_mode(cls, v: str) -> str:
        """验证服务模式"""
        if v not in ["local", "remote"]:
            raise ValueError("服务模式必须是 local 或 remote")
        return v

    @field_validator("window_size")
    @classmethod
    def validate_window_size(cls, v: str) -> str:
        """验证窗口大小"""
        if not re.match(r"^\d{3,5}x\d{3,5}$", v):
            raise ValueError("窗口大小格式无效（如：1280x720）")
        # 解析并检查范围
        try:
            width, height = map(int, v.split("x"))
            if width < 800 or height < 600:
                raise ValueError("窗口大小不能小于800x600")
            if width > 3840 or height > 2160:
                raise ValueError("窗口大小不能超过3840x2160")
        except ValueError:
            raise ValueError("窗口大小格式无效")
        return v

    @field_validator("local_url")
    @classmethod
    def validate_local_url(cls, v: str) -> str:
        """验证本地服务URL"""
        if not v:
            return v
        # 简单的URL格式检查
        if not re.match(r"^https?://", v):
            raise ValueError("URL必须以 http:// 或 https:// 开头")
        return v


class ConfigService:
    """
    配置服务

    封装 ConfigManager，提供类型安全的配置访问
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        初始化配置服务

        Args:
            config_path: 配置文件路径（可选，默认为项目根目录的 config.yaml）
        """
        self._lock = threading.RLock()

        # 确定配置文件路径
        if config_path is None:
            # 默认使用项目根目录的 config.yaml
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config.yaml"

        # 初始化 ConfigManager
        self._config_manager = ConfigManager(config_path)

        # 缓存配置模型
        self._config_cache: Optional[AppConfig] = None

    def get_config(self) -> AppConfig:
        """
        获取应用配置（Pydantic模型）

        Returns:
            AppConfig: 应用配置模型
        """
        with self._lock:
            if self._config_cache is None:
                # 从 ConfigManager 加载配置
                config_dict = self._config_manager.get_all()
                self._config_cache = AppConfig(**config_dict)

            return self._config_cache

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取单个配置值

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值
        """
        return self._config_manager.get(key, default)

    def set(self, key: str, value: Any, source: str = "user") -> None:
        """
        设置配置值

        Args:
            key: 配置键
            value: 配置值
            source: 变更来源
        """
        with self._lock:
            self._config_manager.set(key, value, source)
            # 清除缓存，下次获取时重新加载
            self._config_cache = None

    def reload(self) -> None:
        """重新加载配置"""
        with self._lock:
            self._config_manager.reload()
            self._config_cache = None

    def get_all(self) -> Dict[str, Any]:
        """
        获取所有配置（字典格式）

        Returns:
            配置字典
        """
        return self._config_manager.get_all()

    def get_config_manager(self) -> ConfigManager:
        """
        获取底层 ConfigManager 实例

        Returns:
            ConfigManager 实例
        """
        return self._config_manager


# 全局单例
_config_service_instance: Optional[ConfigService] = None
_config_service_lock = threading.Lock()


def get_config_service() -> ConfigService:
    """获取全局 ConfigService 实例"""
    global _config_service_instance
    if _config_service_instance is None:
        with _config_service_lock:
            if _config_service_instance is None:
                _config_service_instance = ConfigService()
    return _config_service_instance
