"""
插件签名器 - 代码签名与验证

V1.2新增模块
创建日期：2026-03-21

特性：
- RSA签名验证
- 证书管理
- 白名单机制
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class PluginSignatureError(Exception):
    """插件签名异常"""

    pass


class PluginSigner:
    """
    插件代码签名器

    签名流程：
    1. 计算插件文件哈希
    2. 序列化manifest
    3. 使用私钥签名
    4. 保存签名文件

    验证流程：
    1. 检查签名文件是否存在
    2. 验证签名（使用白名单公钥）
    3. 加载插件或拒绝
    """

    def __init__(self, private_key_path: Optional[Path] = None):
        """
        初始化签名器

        Args:
            private_key_path: 私钥文件路径
        """
        self._private_key = None
        self._public_keys: Dict[str, bytes] = {}  # key_id -> public_key_pem
        self._whitelist: Set[str] = set()  # 官方插件白名单

        if private_key_path:
            self._load_private_key(private_key_path)

        # 加载内置公钥白名单
        self._load_builtin_keys()

    def sign_plugin(self, plugin_dir: Path) -> str:
        """
        对插件目录进行签名

        Args:
            plugin_dir: 插件目录

        Returns:
            签名字符串
        """
        if not self._private_key:
            raise PluginSignatureError("No private key loaded")

        # 1. 计算插件文件哈希
        manifest = self._calculate_file_hashes(plugin_dir)

        # 2. 序列化manifest
        manifest_str = json.dumps(manifest, sort_keys=True)

        # 3. 使用私钥签名
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding

            signature = self._private_key.sign(
                manifest_str.encode(), padding.PKCS1v15(), hashes.SHA256()
            )
        except ImportError:
            # 回退到简单签名（用于开发环境）
            signature = self._simple_sign(manifest_str)
        except Exception as e:
            raise PluginSignatureError(f"Failed to sign plugin: {e}")

        # 4. 保存签名文件
        signature_path = plugin_dir / "plugin.sig"
        signature_path.write_bytes(signature)

        return signature.hex()

    def verify_signature(
        self,
        plugin_dir: Path,
        public_key_pem: Optional[bytes] = None,
        strict_mode: bool = False,
    ) -> bool:
        """
        验证插件签名

        Args:
            plugin_dir: 插件目录
            public_key_pem: 公钥PEM（可选，使用白名单公钥）
            strict_mode: 严格模式（True时禁止简单签名）

        Returns:
            签名是否有效
        """
        signature_path = plugin_dir / "plugin.sig"

        # 检查签名文件是否存在
        if not signature_path.exists():
            logger.warning(f"No signature file for {plugin_dir}")
            return False

        # 检测简单签名（开发环境）
        signature = signature_path.read_bytes()
        if self._is_simple_signature(signature):
            if strict_mode:
                logger.error(
                    f"Simple signature not allowed in strict mode for {plugin_dir}"
                )
                return False
            logger.warning(
                f"Using simple signature for {plugin_dir} (development mode)"
            )

        try:
            # 读取签名
            signature = signature_path.read_bytes()

            # 计算文件哈希
            manifest = self._calculate_file_hashes(plugin_dir)
            manifest_str = json.dumps(manifest, sort_keys=True)

            # 验证签名
            if public_key_pem:
                return self._verify_with_key(manifest_str, signature, public_key_pem)
            else:
                # 尝试所有白名单公钥
                for key_id, pub_key in self._public_keys.items():
                    if self._verify_with_key(manifest_str, signature, pub_key):
                        return True
                return False

        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    def add_public_key(self, key_id: str, public_key_pem: bytes) -> None:
        """
        添加公钥到白名单

        Args:
            key_id: 密钥ID
            public_key_pem: 公钥PEM
        """
        self._public_keys[key_id] = public_key_pem

    def remove_public_key(self, key_id: str) -> bool:
        """
        从白名单移除公钥

        Args:
            key_id: 密钥ID

        Returns:
            是否移除成功
        """
        if key_id in self._public_keys:
            del self._public_keys[key_id]
            return True
        return False

    def add_to_whitelist(self, plugin_id: str) -> None:
        """
        添加插件到白名单

        Args:
            plugin_id: 插件ID
        """
        self._whitelist.add(plugin_id)

    def is_in_whitelist(self, plugin_id: str) -> bool:
        """
        检查插件是否在白名单

        Args:
            plugin_id: 插件ID

        Returns:
            是否在白名单
        """
        return plugin_id in self._whitelist

    def _calculate_file_hashes(self, plugin_dir: Path) -> Dict[str, str]:
        """
        计算插件文件哈希

        Args:
            plugin_dir: 插件目录

        Returns:
            文件哈希字典 {relative_path: sha256}
        """
        manifest: Dict[str, str] = {}

        for file_path in plugin_dir.rglob("*"):
            if file_path.is_file() and file_path.name != "plugin.sig":
                relative_path = file_path.relative_to(plugin_dir)

                # 计算SHA256
                sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
                manifest[str(relative_path)] = sha256

        return manifest

    def _load_private_key(self, key_path: Path) -> None:
        """
        加载私钥

        Args:
            key_path: 私钥文件路径
        """
        try:
            from cryptography.hazmat.primitives import serialization

            key_pem = key_path.read_bytes()
            self._private_key = serialization.load_pem_private_key(
                key_pem, password=None
            )
        except ImportError:
            logger.warning("cryptography not installed, using simple signing")
        except Exception as e:
            raise PluginSignatureError(f"Failed to load private key: {e}")

    def _load_builtin_keys(self) -> None:
        """加载内置公钥白名单"""
        # 内置官方插件白名单
        self._whitelist = {
            "novel-generator",
            "novel-analyzer",
            "novel-validator",
            "style-learner",
            "character-manager",
            "worldview-parser",
        }

        # TODO: 加载内置公钥
        # 这里可以硬编码官方公钥，或从配置文件加载

    def _is_simple_signature(self, signature: bytes) -> bool:
        """
        检测是否为简单签名

        Args:
            signature: 签名字节

        Returns:
            是否为简单签名
        """
        # 简单签名使用HMAC-SHA256，长度为32字节
        # RSA签名通常为256或512字节
        return len(signature) == 32

    def _simple_sign(self, data: str) -> bytes:
        """
        简单签名（开发环境）

        Args:
            data: 待签名数据

        Returns:
            签名字节
        """
        # 使用HMAC作为简单签名
        import hmac

        key = b"development_key_do_not_use_in_production"
        return hmac.new(key, data.encode(), hashlib.sha256).digest()

    def _verify_with_key(
        self, data: str, signature: bytes, public_key_pem: bytes
    ) -> bool:
        """
        使用指定公钥验证签名

        Args:
            data: 原始数据
            signature: 签名
            public_key_pem: 公钥PEM

        Returns:
            签名是否有效
        """
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            public_key = serialization.load_pem_public_key(public_key_pem)

            public_key.verify(
                signature, data.encode(), padding.PKCS1v15(), hashes.SHA256()
            )
            return True

        except ImportError:
            # 回退到简单验证
            expected = self._simple_sign(data)
            return hmac.compare_digest(expected, signature)

        except Exception:
            return False


# 全局签名器
_signer_instance: Optional[PluginSigner] = None


def get_plugin_signer() -> PluginSigner:
    """获取全局插件签名器"""
    global _signer_instance
    if _signer_instance is None:
        _signer_instance = PluginSigner()
    return _signer_instance
