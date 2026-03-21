"""
安全配置管理 - API密钥安全存储

V1.2新增模块
创建日期：2026-03-21

特性：
- 系统密钥环集成
- 加密配置存储
- 密钥迁移支持
- 降级加密存储（密钥环不可用时）
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 加密存储相关导入
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    import base64

    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False
    logger.warning("cryptography not installed, encrypted storage unavailable")


class SecureConfigError(Exception):
    """安全配置异常"""

    pass


class SecureConfig:
    """
    安全配置管理

    优先级：
    1. 系统密钥环（最高优先级）
    2. 加密配置文件
    3. 环境变量
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        service_name: str = "novel-assistant-agent-pro",
        encryption_key: Optional[bytes] = None,
    ):
        """
        初始化安全配置

        Args:
            config_path: 配置文件路径
            service_name: 密钥环服务名称
            encryption_key: 加密密钥（用于降级加密存储）
        """
        self._config_path = (
            config_path or Path.home() / ".novel-assistant" / "secure_config.json"
        )
        self._encrypted_path = self._config_path.parent / "secure_config_encrypted.json"
        self._service_name = service_name
        self._lock = threading.RLock()

        # 配置缓存
        self._config: Dict[str, Any] = {}
        self._keyring_available = False
        self._encryption_available = False
        self._fernet: Optional[Any] = None

        # 检查keyring可用性
        self._check_keyring()

        # 初始化加密存储（密钥环不可用时的降级方案）
        self._init_encryption(encryption_key)

        # 加载配置
        self._load_config()

    def _check_keyring(self) -> None:
        """检查keyring是否可用"""
        try:
            import keyring

            # 测试keyring
            keyring.get_password(self._service_name, "__test__")
            self._keyring_available = True
            logger.info("System keyring is available")
        except Exception as e:
            self._keyring_available = False
            logger.warning(f"System keyring not available: {e}")

    def _init_encryption(self, encryption_key: Optional[bytes] = None) -> None:
        """
        初始化加密存储

        Args:
            encryption_key: 加密密钥（可选）
        """
        if not ENCRYPTION_AVAILABLE:
            logger.warning(
                "Cryptography library not available, encrypted storage disabled"
            )
            return

        try:
            if encryption_key:
                # 使用提供的密钥
                self._fernet = Fernet(encryption_key)
            else:
                # 从文件加载或生成新密钥
                key_path = self._config_path.parent / ".encryption_key"

                if key_path.exists():
                    encryption_key = key_path.read_bytes()
                else:
                    # 生成新密钥（基于机器信息）
                    import hashlib

                    machine_id = (
                        os.uname().nodename
                        if hasattr(os, "uname")
                        else os.getenv("COMPUTERNAME", "default")
                    )
                    salt = b"novel-assistant-salt"
                    kdf = PBKDF2HMAC(
                        algorithm=hashes.SHA256(),
                        length=32,
                        salt=salt,
                        iterations=100000,
                    )
                    encryption_key = base64.urlsafe_b64encode(
                        kdf.derive(machine_id.encode())
                    )
                    key_path.parent.mkdir(parents=True, exist_ok=True)
                    key_path.write_bytes(encryption_key)
                    key_path.chmod(0o600)  # 仅所有者可读写

                self._fernet = Fernet(encryption_key)

            self._encryption_available = True
            logger.info("Encrypted storage initialized successfully")

        except Exception as e:
            logger.warning(f"Failed to initialize encryption: {e}")
            self._encryption_available = False

    def get(self, key: str, default: Any = None, use_keyring: bool = True) -> Any:
        """
        获取配置值

        Args:
            key: 配置键
            default: 默认值
            use_keyring: 是否使用密钥环

        Returns:
            配置值
        """
        with self._lock:
            # 1. 环境变量（最高优先级）
            env_key = key.upper().replace(".", "_")
            env_value = os.getenv(env_key)
            if env_value is not None:
                return env_value

            # 2. 系统密钥环
            if use_keyring and self._keyring_available:
                try:
                    import keyring

                    value = keyring.get_password(self._service_name, key)
                    if value is not None:
                        return value
                except Exception as e:
                    logger.warning(f"Failed to get from keyring: {e}")

            # 3. 配置文件（优先使用加密存储）
            if self._encryption_available and self._encrypted_path.exists():
                encrypted_value = self._get_encrypted(key)
                if encrypted_value is not None:
                    return encrypted_value

            return self._config.get(key, default)

    def set(self, key: str, value: Any, use_keyring: bool = True) -> bool:
        """
        设置配置值

        Args:
            key: 配置键
            value: 配置值
            use_keyring: 是否使用密钥环

        Returns:
            是否设置成功
        """
        with self._lock:
            # 敏感字段使用密钥环
            sensitive_keys = ["api_key", "secret", "password", "token"]
            is_sensitive = any(s in key.lower() for s in sensitive_keys)

            if is_sensitive:
                # 敏感字段优先使用密钥环
                if use_keyring and self._keyring_available:
                    try:
                        import keyring

                        keyring.set_password(self._service_name, key, str(value))
                        # 从配置文件中移除
                        if key in self._config:
                            del self._config[key]
                        self._save_config()
                        return True
                    except Exception as e:
                        logger.error(f"Failed to set in keyring: {e}")

                # 密钥环不可用时，使用加密存储
                if self._encryption_available:
                    try:
                        self._set_encrypted(key, value)
                        return True
                    except Exception as e:
                        logger.error(f"Failed to set encrypted value: {e}")
                        return False

                logger.warning(f"No secure storage available for sensitive key: {key}")
                return False

            # 非敏感字段保存到配置文件
            self._config[key] = value
            self._save_config()
            return True

    def delete(self, key: str, use_keyring: bool = True) -> bool:
        """
        删除配置值

        Args:
            key: 配置键
            use_keyring: 是否从密钥环删除

        Returns:
            是否删除成功
        """
        with self._lock:
            success = True

            # 从密钥环删除
            if use_keyring and self._keyring_available:
                try:
                    import keyring

                    keyring.delete_password(self._service_name, key)
                except Exception:
                    pass  # 密钥环中不存在不算错误

            # 从配置文件删除
            if key in self._config:
                del self._config[key]
                self._save_config()

            return success

    def migrate_from_env(self, keys: Dict[str, str]) -> Dict[str, bool]:
        """
        从环境变量迁移到密钥环

        Args:
            keys: 环境变量名 -> 配置键映射

        Returns:
            迁移结果 {key: bool}
        """
        results: Dict[str, bool] = {}

        for env_name, config_key in keys.items():
            env_value = os.getenv(env_name)
            if env_value:
                results[config_key] = self.set(config_key, env_value, use_keyring=True)
            else:
                results[config_key] = False

        return results

    def migrate_from_config(
        self, config_dict: Dict[str, Any], sensitive_keys: Optional[list] = None
    ) -> Dict[str, bool]:
        """
        从配置字典迁移敏感字段到密钥环

        Args:
            config_dict: 配置字典
            sensitive_keys: 敏感字段列表

        Returns:
            迁移结果 {key: bool}
        """
        if sensitive_keys is None:
            sensitive_keys = ["api_key", "secret", "password", "token"]

        results: Dict[str, bool] = {}

        def _migrate_recursive(d: Dict[str, Any], prefix: str = ""):
            for key, value in d.items():
                full_key = f"{prefix}.{key}" if prefix else key

                if isinstance(value, dict):
                    _migrate_recursive(value, full_key)
                elif any(s in key.lower() for s in sensitive_keys):
                    # 敏感字段迁移到密钥环
                    results[full_key] = self.set(full_key, value, use_keyring=True)

        _migrate_recursive(config_dict)
        return results

    def export_safe_config(self) -> Dict[str, Any]:
        """
        导出安全配置（不包含敏感信息）

        Returns:
            安全配置字典
        """
        with self._lock:
            return {
                "keyring_available": self._keyring_available,
                "config": dict(self._config),
            }

    def _load_config(self) -> None:
        """加载配置文件"""
        if not self._config_path.exists():
            return

        try:
            content = self._config_path.read_text(encoding="utf-8")
            self._config = json.loads(content)
        except Exception as e:
            logger.error(f"Failed to load secure config: {e}")
            self._config = {}

    def _get_encrypted(self, key: str) -> Optional[str]:
        """
        从加密存储获取值

        Args:
            key: 配置键

        Returns:
            解密后的值或None
        """
        if not self._encryption_available or not self._fernet:
            return None

        try:
            if not self._encrypted_path.exists():
                return None

            content = self._encrypted_path.read_text(encoding="utf-8")
            encrypted_data = json.loads(content)

            if key not in encrypted_data:
                return None

            encrypted_value = encrypted_data[key]
            decrypted = self._fernet.decrypt(encrypted_value.encode())
            return decrypted.decode()

        except Exception as e:
            logger.error(f"Failed to get encrypted value: {e}")
            return None

    def _set_encrypted(self, key: str, value: Any) -> None:
        """
        设置加密存储值

        Args:
            key: 配置键
            value: 配置值
        """
        if not self._encryption_available or not self._fernet:
            raise SecureConfigError("Encryption not available")

        try:
            # 读取现有加密数据
            encrypted_data: Dict[str, str] = {}
            if self._encrypted_path.exists():
                content = self._encrypted_path.read_text(encoding="utf-8")
                encrypted_data = json.loads(content)

            # 加密并保存
            encrypted_value = self._fernet.encrypt(str(value).encode())
            encrypted_data[key] = encrypted_value.decode()

            # 确保目录存在
            self._encrypted_path.parent.mkdir(parents=True, exist_ok=True)

            # 保存加密数据
            content = json.dumps(encrypted_data, indent=2, ensure_ascii=False)
            self._encrypted_path.write_text(content, encoding="utf-8")
            self._encrypted_path.chmod(0o600)  # 仅所有者可读写

        except Exception as e:
            raise SecureConfigError(f"Failed to set encrypted value: {e}")

    def _save_config(self) -> None:
        """保存配置文件"""
        try:
            # 确保目录存在
            self._config_path.parent.mkdir(parents=True, exist_ok=True)

            # 保存（不包含敏感信息）
            safe_config = {
                k: v
                for k, v in self._config.items()
                if not any(
                    s in k.lower() for s in ["api_key", "secret", "password", "token"]
                )
            }

            content = json.dumps(safe_config, indent=2, ensure_ascii=False)
            self._config_path.write_text(content, encoding="utf-8")

        except Exception as e:
            logger.error(f"Failed to save secure config: {e}")


# 全局实例
_secure_config_instance: Optional[SecureConfig] = None
_secure_config_lock = threading.Lock()


def get_secure_config() -> SecureConfig:
    """获取全局安全配置实例"""
    global _secure_config_instance
    if _secure_config_instance is None:
        with _secure_config_lock:
            if _secure_config_instance is None:
                _secure_config_instance = SecureConfig()
    return _secure_config_instance
