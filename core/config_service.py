"""
配置服务 - 封装 config.yaml 读取，通过 ServiceLocator 提供

V1.2版本（大模型集成V1.0）
创建日期：2026-03-22
修订日期：2026-03-24

特性：
- 封装 ConfigManager，提供配置读取服务
- 支持 Pydantic 模型验证（含字段验证器）
- 线程安全
- 通过 ServiceLocator 注册和获取
- 监听器模式：支持配置变更监听
- EventBus集成：发布config.changed事件
- AI配置获取：提供get_ai_config()方法
"""

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .config_manager import ConfigManager, get_config_manager
from .event_bus import EventBus, get_event_bus
from .models import Event


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
    V1.2新增：监听器模式、EventBus集成、AI配置获取
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

        # V1.2新增：监听器列表
        self._listeners: List[Callable[[str, Any, Any], None]] = []
        self._listeners_lock = threading.RLock()

        # V1.2新增：EventBus实例（延迟初始化）
        self._event_bus: Optional[EventBus] = None

        # V1.2新增：向ConfigManager注册内部观察者
        self._config_manager.add_observer(self._on_config_changed_internal)

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

    # ==================== V1.2新增：监听器模式 ====================

    def add_listener(self, listener: Callable[[str, Any, Any], None]) -> None:
        """
        添加配置变更监听器

        Args:
            listener: 监听器函数 (key_path, old_value, new_value) -> None

        示例:
            def my_listener(key_path, old_value, new_value):
                print(f"配置 {key_path} 已变更: {old_value} -> {new_value}")

            config_service.add_listener(my_listener)
        """
        with self._listeners_lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[str, Any, Any], None]) -> bool:
        """
        移除配置变更监听器

        Args:
            listener: 监听器函数

        Returns:
            是否移除成功
        """
        with self._listeners_lock:
            try:
                self._listeners.remove(listener)
                return True
            except ValueError:
                return False

    def clear_listeners(self) -> None:
        """清除所有监听器"""
        with self._listeners_lock:
            self._listeners.clear()

    def _on_config_changed_internal(self, key_path: str, old_value: Any, new_value: Any) -> None:
        """
        内部观察者：ConfigManager变更时触发

        Args:
            key_path: 配置路径
            old_value: 旧值
            new_value: 新值
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # P1-5修复：检查值是否真正变化（幂等性保护）
        if old_value == new_value:
            logger.debug(f"配置 {key_path} 值未变化，跳过事件发布")
            return
        
        # P2-4修复：审计日志
        logger.info(
            f"[CONFIG_AUDIT] {key_path}: {repr(old_value)[:100]} -> {repr(new_value)[:100]}"
        )

        # 1. 清除配置缓存
        with self._lock:
            self._config_cache = None

        # 2. 通知所有监听器
        self._notify_listeners(key_path, old_value, new_value)

        # 3. 发布EventBus事件
        self._publish_config_changed_event(key_path, old_value, new_value)

    def _notify_listeners(self, key_path: str, old_value: Any, new_value: Any) -> None:
        """
        通知所有监听器

        Args:
            key_path: 配置路径
            old_value: 旧值
            new_value: 新值
        """
        with self._listeners_lock:
            listeners_snapshot = list(self._listeners)

        for listener in listeners_snapshot:
            try:
                listener(key_path, old_value, new_value)
            except Exception as e:
                # 监听器异常不阻塞其他监听器
                import logging
                logging.getLogger(__name__).warning(
                    f"Config listener failed: {e}, listener={listener}, key_path={key_path}"
                )

    def _publish_config_changed_event(self, key_path: str, old_value: Any, new_value: Any) -> None:
        """
        发布配置变更事件到EventBus

        Args:
            key_path: 配置路径
            old_value: 旧值
            new_value: 新值
        """
        # 延迟初始化EventBus（避免循环依赖）
        if self._event_bus is None:
            self._event_bus = get_event_bus()

        event_data = {
            "key_path": key_path,
            "old_value": old_value,
            "new_value": new_value,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            # V1.3修复：EventBus.publish签名是(event_type, data, source)
            self._event_bus.publish(
                event_type="config.changed",
                data=event_data,
                source="ConfigService"
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                f"Failed to publish config.changed event: {e}"
            )

    # ==================== V1.2新增：AI配置便捷方法 ====================

    def get_ai_config(self) -> Dict[str, Any]:
        """
        获取AI相关配置（供AIServiceManager使用）

        Returns:
            AI配置字典，包含：
            - service_mode: "local" 或 "remote"
            - provider: 服务提供商
            - model: 模型名称
            - api_key: API密钥
            - base_url: API基础URL（可选）
            - temperature: 温度参数
            - max_tokens: 最大token数（可选）
            - local: 本地配置（可选）
        """
        config = self.get_config()

        ai_config = {
            "service_mode": config.service_mode,
            "provider": config.provider,
            "model": config.model,
            "api_key": config.api_key,
            "temperature": config.temperature,
            "local_url": config.local_url,
        }

        # 从config.yaml获取可选配置
        all_config = self.get_all()

        # base_url（优先从provider配置块读取）
        # DeepSeek配置
        if "deepseek" in all_config and isinstance(all_config["deepseek"], dict):
            ai_config["base_url"] = all_config["deepseek"].get("base_url", "https://api.deepseek.com")
        elif "base_url" in all_config:
            ai_config["base_url"] = all_config["base_url"]

        # max_tokens（可选）
        if "max_tokens" in all_config:
            ai_config["max_tokens"] = all_config["max_tokens"]

        # local配置块（当service_mode="local"时使用）
        if "local" in all_config:
            ai_config["local"] = all_config["local"]

        return ai_config

    def update_ai_config(self, new_config: Dict[str, Any]) -> None:
        """
        更新AI配置并发布变更事件（事务性）
        
        如果更新失败，会自动回滚到旧配置。

        Args:
            new_config: 新的AI配置字典

        示例:
            config_service.update_ai_config({
                "service_mode": "remote",
                "provider": "DeepSeek",
                "model": "deepseek-chat",
                "api_key": "sk-xxx"
            })
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # 映射到顶层配置键
        key_mapping = {
            "service_mode": "service_mode",
            "provider": "provider",
            "model": "model",
            "api_key": "api_key",
            "base_url": "base_url",
            "temperature": "temperature",
            "max_tokens": "max_tokens",
            "local_url": "local_url",
        }

        # P0-3修复：保存旧值用于回滚
        old_values: Dict[str, Any] = {}
        
        with self._lock:
            # 收集所有将要更新的键及其旧值
            for config_key, value in new_config.items():
                if config_key in key_mapping:
                    key = key_mapping[config_key]
                    old_values[key] = self.get(key)
                elif config_key == "local" and isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        key = f"local.{sub_key}"
                        old_values[key] = self.get(key)
            
            try:
                # V2.20修复：service_mode值验证和自动修正
                if "service_mode" in new_config:
                    service_mode = new_config["service_mode"]
                    # Pydantic模型要求必须是"local"或"remote"
                    if service_mode == "online":
                        logger.warning("[CONFIG_VALIDATION] service_mode 'online' is deprecated, auto-correcting to 'remote'")
                        new_config["service_mode"] = "remote"
                    elif service_mode not in ["local", "remote"]:
                        logger.error(f"[CONFIG_VALIDATION] Invalid service_mode '{service_mode}', must be 'local' or 'remote'")
                        raise ValueError(f"service_mode must be 'local' or 'remote', got '{service_mode}'")
                
                # 尝试更新所有配置
                for config_key, value in new_config.items():
                    if config_key in key_mapping:
                        self.set(key_mapping[config_key], value, source="ai_config_update")
                    elif config_key == "local":
                        # local配置块单独处理
                        if isinstance(value, dict):
                            for sub_key, sub_value in value.items():
                                self.set(f"local.{sub_key}", sub_value, source="ai_config_update")
            except Exception as e:
                # P0-3修复：回滚到旧值
                logger.error(f"更新AI配置失败，正在回滚: {e}")
                try:
                    for key, old_value in old_values.items():
                        self.set(key, old_value, source="ai_config_rollback")
                    logger.info("AI配置已成功回滚")
                except Exception as rollback_error:
                    logger.error(f"回滚AI配置失败: {rollback_error}")
                raise


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
