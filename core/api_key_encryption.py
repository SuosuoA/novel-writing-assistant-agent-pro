"""
API Key加密存储模块

V1.0版本
创建日期: 2026-03-26
最后更新: 2026-03-26

功能:
- 使用AES-256-GCM加密API Key
- 主密钥自动生成并存储在本地
- 支持多个Provider的API Key管理
- 提供备份和恢复功能

安全设计:
- 主密钥32字节（256位）随机生成
- 每次加密使用随机nonce（12字节）
- 加密文件权限限制为用户可读写（0o600）
- 支持 AEAD 认证加密

使用示例:
    from core.api_key_encryption import APIKeyEncryption
    
    encryption = APIKeyEncryption()
    
    # 保存API Key
    encryption.save_api_key("DeepSeek", "sk-xxxxxxxxxx")
    
    # 获取API Key
    api_key = encryption.get_api_key("DeepSeek")
    
    # 备份所有API Key
    encryption.backup_keys("/path/to/backup.enc")
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime

# 尝试导入cryptography
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logging.warning("cryptography not available, API Key encryption disabled")


class APIKeyEncryption:
    """
    API Key加密存储
    
    使用AES-256-GCM加密算法，主密钥自动生成并存储在本地。
    """
    
    # 路径常量
    SECRETS_DIR = Path(".secrets")
    MASTER_KEY_PATH = SECRETS_DIR / ".master_key"
    SECRETS_FILE = SECRETS_DIR / "api_keys.enc"
    
    # API Key模式检测
    API_KEY_PATTERNS = {
        "DeepSeek": r"sk-[a-zA-Z0-9]{32,}",
        "OpenAI": r"sk-[a-zA-Z0-9]{48,}",
        "Anthropic": r"sk-ant-[a-zA-Z0-9\-]{80,}",
    }
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        初始化加密存储
        
        Args:
            project_root: 项目根目录（可选，默认为当前工作目录）
        """
        self._logger = logging.getLogger(__name__)
        
        # 设置项目根目录
        if project_root is None:
            project_root = Path.cwd()
        self._project_root = Path(project_root)
        
        # 更新路径为绝对路径
        self._secrets_dir = self._project_root / self.SECRETS_DIR
        self._master_key_path = self._project_root / self.MASTER_KEY_PATH
        self._secrets_file = self._project_root / self.SECRETS_FILE
        
        # 检查加密库是否可用
        if not CRYPTO_AVAILABLE:
            self._logger.warning("cryptography library not available, using plaintext storage")
            self._aesgcm = None
            self._master_key = None
            return
        
        # 确保目录存在
        self._ensure_secrets_dir()
        
        # 加载或创建主密钥
        self._master_key = self._load_or_create_master_key()
        self._aesgcm = AESGCM(self._master_key)
        
        self._logger.info("API Key encryption initialized")
    
    def _ensure_secrets_dir(self) -> None:
        """确保.secrets目录存在"""
        if not self._secrets_dir.exists():
            self._secrets_dir.mkdir(parents=True, exist_ok=True)
            # 设置目录权限（仅用户可访问）
            try:
                os.chmod(self._secrets_dir, 0o700)
            except Exception as e:
                self._logger.warning(f"Failed to set directory permissions: {e}")
    
    def _load_or_create_master_key(self) -> bytes:
        """
        加载或创建主密钥
        
        Returns:
            32字节的主密钥
        """
        if self._master_key_path.exists():
            try:
                key = self._master_key_path.read_bytes()
                if len(key) == 32:
                    return key
                else:
                    self._logger.warning("Invalid master key length, regenerating")
            except Exception as e:
                self._logger.error(f"Failed to load master key: {e}")
        
        # 生成新的主密钥
        key = os.urandom(32)
        
        # 保存主密钥
        try:
            self._master_key_path.write_bytes(key)
            # 设置文件权限（仅用户可读写）
            os.chmod(self._master_key_path, 0o600)
            self._logger.info("New master key generated and saved")
        except Exception as e:
            self._logger.error(f"Failed to save master key: {e}")
        
        return key
    
    def save_api_key(self, provider: str, api_key: str) -> bool:
        """
        保存API Key（加密存储）
        
        Args:
            provider: 服务提供商（DeepSeek/OpenAI/Anthropic等）
            api_key: API密钥
        
        Returns:
            是否保存成功
        """
        if not api_key:
            self._logger.warning(f"Empty API key for {provider}")
            return False
        
        # 加载现有API Keys
        api_keys = self.load_all_api_keys()
        
        # 更新或添加
        api_keys[provider] = {
            "key": api_key,
            "updated_at": datetime.now().isoformat()
        }
        
        # 加密保存
        return self._encrypt_and_save(api_keys)
    
    def get_api_key(self, provider: str) -> Optional[str]:
        """
        获取API Key（解密）
        
        Args:
            provider: 服务提供商
        
        Returns:
            API密钥或None
        """
        api_keys = self.load_all_api_keys()
        
        if provider in api_keys:
            key_data = api_keys[provider]
            if isinstance(key_data, dict):
                return key_data.get("key")
            elif isinstance(key_data, str):
                # 兼容旧格式
                return key_data
        
        return None
    
    def load_all_api_keys(self) -> Dict[str, Any]:
        """
        加载所有API Keys（解密）
        
        Returns:
            API Keys字典
        """
        if not CRYPTO_AVAILABLE or self._aesgcm is None:
            # 降级：使用明文存储
            return self._load_plaintext()
        
        if not self._secrets_file.exists():
            return {}
        
        try:
            data = self._secrets_file.read_bytes()
            nonce = data[:12]
            ciphertext = data[12:]
            
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
            return json.loads(plaintext.decode('utf-8'))
        except Exception as e:
            self._logger.error(f"Failed to decrypt API keys: {e}")
            return {}
    
    def _encrypt_and_save(self, api_keys: Dict[str, Any]) -> bool:
        """
        加密并保存API Keys
        
        Args:
            api_keys: API Keys字典
        
        Returns:
            是否保存成功
        """
        if not CRYPTO_AVAILABLE or self._aesgcm is None:
            # 降级：使用明文存储
            return self._save_plaintext(api_keys)
        
        try:
            # 生成随机nonce
            nonce = os.urandom(12)
            
            # 加密
            plaintext = json.dumps(api_keys, ensure_ascii=False, indent=2).encode('utf-8')
            ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
            
            # 保存（nonce + ciphertext）
            self._secrets_file.write_bytes(nonce + ciphertext)
            
            # 设置文件权限
            os.chmod(self._secrets_file, 0o600)
            
            self._logger.info(f"API keys encrypted and saved ({len(api_keys)} providers)")
            return True
        except Exception as e:
            self._logger.error(f"Failed to encrypt and save API keys: {e}")
            return False
    
    def _load_plaintext(self) -> Dict[str, Any]:
        """降级：加载明文API Keys"""
        plaintext_file = self._secrets_dir / "api_keys.json"
        if plaintext_file.exists():
            try:
                return json.loads(plaintext_file.read_text(encoding='utf-8'))
            except Exception:
                return {}
        return {}
    
    def _save_plaintext(self, api_keys: Dict[str, Any]) -> bool:
        """降级：保存明文API Keys"""
        plaintext_file = self._secrets_dir / "api_keys.json"
        try:
            plaintext_file.write_text(
                json.dumps(api_keys, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            os.chmod(plaintext_file, 0o600)
            self._logger.warning("API keys saved in plaintext (cryptography not available)")
            return True
        except Exception as e:
            self._logger.error(f"Failed to save plaintext API keys: {e}")
            return False
    
    def delete_api_key(self, provider: str) -> bool:
        """
        删除API Key
        
        Args:
            provider: 服务提供商
        
        Returns:
            是否删除成功
        """
        api_keys = self.load_all_api_keys()
        
        if provider in api_keys:
            del api_keys[provider]
            return self._encrypt_and_save(api_keys)
        
        return False
    
    def backup_keys(self, backup_path: Path) -> bool:
        """
        备份API Keys到指定路径
        
        Args:
            backup_path: 备份文件路径
        
        Returns:
            是否备份成功
        """
        try:
            # 读取加密数据
            if self._secrets_file.exists():
                import shutil
                shutil.copy2(self._secrets_file, backup_path)
                self._logger.info(f"API keys backed up to {backup_path}")
                return True
            else:
                self._logger.warning("No API keys to backup")
                return False
        except Exception as e:
            self._logger.error(f"Failed to backup API keys: {e}")
            return False
    
    def restore_keys(self, backup_path: Path) -> bool:
        """
        从备份恢复API Keys
        
        Args:
            backup_path: 备份文件路径
        
        Returns:
            是否恢复成功
        """
        try:
            if not backup_path.exists():
                self._logger.error(f"Backup file not found: {backup_path}")
                return False
            
            import shutil
            shutil.copy2(backup_path, self._secrets_file)
            os.chmod(self._secrets_file, 0o600)
            self._logger.info(f"API keys restored from {backup_path}")
            return True
        except Exception as e:
            self._logger.error(f"Failed to restore API keys: {e}")
            return False
    
    def get_security_status(self) -> Dict[str, Any]:
        """
        获取安全状态
        
        Returns:
            安全状态字典
        """
        status = {
            "encryption_available": CRYPTO_AVAILABLE,
            "secrets_dir_exists": self._secrets_dir.exists(),
            "master_key_exists": self._master_key_path.exists(),
            "secrets_file_exists": self._secrets_file.exists(),
            "providers_configured": list(self.load_all_api_keys().keys()),
            "recommendations": []
        }
        
        # 生成建议
        if not CRYPTO_AVAILABLE:
            status["recommendations"].append("安装cryptography库以启用加密存储")
        
        if not self._master_key_path.exists():
            status["recommendations"].append("首次保存API Key后系统将自动生成加密密钥")
        
        # 检查.gitignore
        gitignore_path = self._project_root / ".gitignore"
        if gitignore_path.exists():
            gitignore_content = gitignore_path.read_text(encoding='utf-8')
            if ".secrets/" not in gitignore_content:
                status["recommendations"].append("建议在.gitignore中添加.secrets/目录")
        else:
            status["recommendations"].append("创建.gitignore文件以保护敏感信息")
        
        return status


# 全局单例
_encryption_instance: Optional[APIKeyEncryption] = None
_encryption_lock = None


def get_api_key_encryption(project_root: Optional[Path] = None) -> APIKeyEncryption:
    """
    获取全局API Key加密实例
    
    Args:
        project_root: 项目根目录（可选）
    
    Returns:
        APIKeyEncryption实例
    """
    global _encryption_instance, _encryption_lock
    
    if _encryption_instance is None:
        import threading
        _encryption_lock = threading.Lock()
        
        with _encryption_lock:
            if _encryption_instance is None:
                _encryption_instance = APIKeyEncryption(project_root)
    
    return _encryption_instance
