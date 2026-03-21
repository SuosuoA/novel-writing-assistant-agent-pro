"""
配置管理器 - YAML/JSON配置 + 环境变量覆盖 + 变更通知

V1.2版本（最终修订版）
创建日期：2026-03-21

特性：
- YAML/JSON配置文件支持
- 环境变量覆盖
- 配置验证器
- 变更历史记录
- 线程安全（RLock + 写锁）
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class ConfigValidationError(Exception):
    """配置验证异常"""
    pass


class ConfigKeyError(Exception):
    """配置键错误"""
    pass


class ConfigHistory:
    """配置变更历史"""
    
    def __init__(self, max_size: int = 100):
        """
        初始化配置历史
        
        Args:
            max_size: 最大历史记录数
        """
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._max_size = max_size
        self._lock = threading.Lock()
    
    def add(
        self,
        key_path: str,
        old_value: Any,
        new_value: Any,
        source: str
    ) -> None:
        """
        添加历史记录
        
        Args:
            key_path: 配置路径
            old_value: 旧值
            new_value: 新值
            source: 变更来源
        """
        with self._lock:
            if key_path not in self._history:
                self._history[key_path] = []
            
            if len(self._history[key_path]) >= self._max_size:
                self._history[key_path].pop(0)
            
            self._history[key_path].append({
                "old_value": old_value,
                "new_value": new_value,
                "source": source,
                "timestamp": datetime.now().isoformat()
            })
    
    def get(self, key_path: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取历史记录
        
        Args:
            key_path: 配置路径
            limit: 最大返回数量
        
        Returns:
            历史记录列表
        """
        with self._lock:
            history = self._history.get(key_path, [])
            return history[-limit:]


class ConfigValidator:
    """配置验证器"""
    
    def __init__(self):
        """初始化验证器"""
        self._validators: Dict[str, Callable[[Any], bool]] = {}
    
    def register(self, key_path: str, validator: Callable[[Any], bool]) -> None:
        """
        注册验证器
        
        Args:
            key_path: 配置路径
            validator: 验证函数（返回True表示验证通过）
        """
        self._validators[key_path] = validator
    
    def validate(self, key_path: str, value: Any) -> bool:
        """
        验证配置值
        
        Args:
            key_path: 配置路径
            value: 配置值
        
        Returns:
            是否验证通过
        """
        if key_path in self._validators:
            return self._validators[key_path](value)
        return True  # 无验证器默认通过


class ConfigManager:
    """
    配置管理器
    
    特性：
    - YAML/JSON配置文件支持
    - 环境变量覆盖（优先级最高）
    - 配置验证器
    - 变更历史记录
    - 变更通知
    - 线程安全
    """
    
    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径（可选）
        """
        self._config: Dict[str, Any] = {}
        self._config_path = Path(config_path) if config_path else None
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()  # 写锁
        
        self._history = ConfigHistory()
        self._validator = ConfigValidator()
        self._observers: List[Callable[[str, Any, Any], None]] = []
        
        # 环境变量前缀
        self._env_prefix = "AGENT_"
        
        # 加载配置
        if self._config_path and self._config_path.exists():
            self._load_config()
    
    def get(
        self,
        key_path: str,
        default: Any = None
    ) -> Any:
        """
        获取配置值
        
        Args:
            key_path: 配置路径（支持点号分隔，如 "llm.api_key"）
            default: 默认值
        
        Returns:
            配置值
        """
        with self._lock:
            # 1. 先检查环境变量（优先级最高）
            env_key = self._get_env_key(key_path)
            env_value = os.getenv(env_key)
            if env_value is not None:
                return self._parse_env_value(env_value)
            
            # 2. 从配置字典获取
            keys = key_path.split(".")
            value = self._config
            
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return default
            
            return value
    
    def set(
        self,
        key_path: str,
        value: Any,
        source: str = "user"
    ) -> None:
        """
        设置配置值
        
        Args:
            key_path: 配置路径
            value: 配置值
            source: 变更来源
        """
        with self._write_lock:
            # 验证
            if not self._validator.validate(key_path, value):
                raise ConfigValidationError(
                    f"Validation failed for {key_path}"
                )
            
            # 获取旧值
            old_value = self.get(key_path)
            
            # 设置新值
            keys = key_path.split(".")
            config = self._config
            
            for key in keys[:-1]:
                if key not in config:
                    config[key] = {}
                config = config[key]
            
            config[keys[-1]] = value
            
            # 记录历史
            self._history.add(key_path, old_value, value, source)
            
            # 通知观察者
            self._notify_observers(key_path, old_value, value)
    
    def get_all(self) -> Dict[str, Any]:
        """
        获取全部配置
        
        Returns:
            配置字典副本
        """
        with self._lock:
            return dict(self._config)
    
    def add_validator(
        self,
        key_path: str,
        validator: Callable[[Any], bool]
    ) -> None:
        """
        添加配置验证器
        
        Args:
            key_path: 配置路径
            validator: 验证函数
        """
        self._validator.register(key_path, validator)
    
    def validate(self, key_path: str) -> Dict[str, Any]:
        """
        验证配置
        
        Args:
            key_path: 配置路径
        
        Returns:
            验证结果 {
                "valid": bool,
                "value": Any,
                "error": Optional[str]
            }
        """
        value = self.get(key_path)
        
        try:
            is_valid = self._validator.validate(key_path, value)
            return {
                "valid": is_valid,
                "value": value,
                "error": None if is_valid else "Validation failed"
            }
        except Exception as e:
            return {
                "valid": False,
                "value": value,
                "error": str(e)
            }
    
    def reload(self) -> None:
        """重新加载配置文件"""
        with self._write_lock:
            if self._config_path and self._config_path.exists():
                self._load_config()
    
    def get_history(
        self,
        key_path: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取配置变更历史
        
        Args:
            key_path: 配置路径
            limit: 最大返回数量
        
        Returns:
            历史记录列表
        """
        return self._history.get(key_path, limit)
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """
        列出所有配置键
        
        Args:
            prefix: 键前缀过滤
        
        Returns:
            配置键列表
        """
        with self._lock:
            keys: List[str] = []
            self._collect_keys(self._config, "", keys)
            
            if prefix:
                keys = [k for k in keys if k.startswith(prefix)]
            
            return keys
    
    def add_observer(
        self,
        observer: Callable[[str, Any, Any], None]
    ) -> None:
        """
        添加配置变更观察者
        
        Args:
            observer: 观察者函数 (key_path, old_value, new_value) -> None
        """
        with self._lock:
            self._observers.append(observer)
    
    def remove_observer(
        self,
        observer: Callable[[str, Any, Any], None]
    ) -> bool:
        """
        移除观察者
        
        Args:
            observer: 观察者函数
        
        Returns:
            是否移除成功
        """
        with self._lock:
            try:
                self._observers.remove(observer)
                return True
            except ValueError:
                return False
    
    def _load_config(self) -> None:
        """加载配置文件"""
        if not self._config_path:
            return
        
        try:
            content = self._config_path.read_text(encoding="utf-8")
            
            if self._config_path.suffix in [".yaml", ".yml"]:
                if YAML_AVAILABLE:
                    self._config = yaml.safe_load(content) or {}
                else:
                    raise ImportError("PyYAML not installed")
            elif self._config_path.suffix == ".json":
                self._config = json.loads(content)
            else:
                # 尝试自动检测格式
                try:
                    self._config = json.loads(content)
                except json.JSONDecodeError:
                    if YAML_AVAILABLE:
                        self._config = yaml.safe_load(content) or {}
                    else:
                        self._config = {}
        except Exception as e:
            import logging
            logging.error(f"Failed to load config: {e}")
            self._config = {}
    
    def _save_config(self) -> None:
        """保存配置到文件"""
        if not self._config_path:
            return
        
        try:
            if self._config_path.suffix in [".yaml", ".yml"]:
                if YAML_AVAILABLE:
                    content = yaml.dump(self._config, allow_unicode=True)
                else:
                    raise ImportError("PyYAML not installed")
            else:
                content = json.dumps(self._config, indent=2, ensure_ascii=False)
            
            self._config_path.write_text(content, encoding="utf-8")
        except Exception as e:
            import logging
            logging.error(f"Failed to save config: {e}")
    
    def _get_env_key(self, key_path: str) -> str:
        """
        获取环境变量键名
        
        Args:
            key_path: 配置路径
        
        Returns:
            环境变量键名
        """
        return self._env_prefix + key_path.upper().replace(".", "_")
    
    def _parse_env_value(self, value: str) -> Any:
        """
        解析环境变量值
        
        Args:
            value: 环境变量字符串
        
        Returns:
            解析后的值
        """
        # 尝试解析为JSON
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
        
        # 布尔值
        if value.lower() in ["true", "yes", "1"]:
            return True
        if value.lower() in ["false", "no", "0"]:
            return False
        
        # 数值
        try:
            return int(value)
        except ValueError:
            pass
        
        try:
            return float(value)
        except ValueError:
            pass
        
        # 字符串
        return value
    
    def _collect_keys(
        self,
        config: Dict[str, Any],
        prefix: str,
        keys: List[str]
    ) -> None:
        """
        递归收集配置键
        
        Args:
            config: 配置字典
            prefix: 键前缀
            keys: 键列表
        """
        for key, value in config.items():
            full_key = f"{prefix}.{key}" if prefix else key
            keys.append(full_key)
            
            if isinstance(value, dict):
                self._collect_keys(value, full_key, keys)
    
    def _notify_observers(
        self,
        key_path: str,
        old_value: Any,
        new_value: Any
    ) -> None:
        """
        通知观察者配置变更
        
        Args:
            key_path: 配置路径
            old_value: 旧值
            new_value: 新值
        """
        for observer in self._observers:
            try:
                observer(key_path, old_value, new_value)
            except Exception:
                pass  # 观察者异常不影响主流程


# 全局单例
_config_instance: Optional[ConfigManager] = None
_config_lock = threading.Lock()


def get_config_manager() -> ConfigManager:
    """获取全局ConfigManager实例"""
    global _config_instance
    if _config_instance is None:
        with _config_lock:
            if _config_instance is None:
                _config_instance = ConfigManager()
    return _config_instance
