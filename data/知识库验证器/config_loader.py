#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置加载器 - 支持配置化阈值

从TOML配置文件加载各项阈值参数，支持用户自定义质量标准。

配置文件位置：data/知识库验证器/verifier_config.toml
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# 默认配置（当配置文件不存在时使用）
DEFAULT_CONFIG = {
    "duplicates": {
        "similarity_threshold": 0.85,
        "overlap_threshold": 0.70,
        "simhash_hamming_threshold": 10,
        "simhash_prefix_bits": 8
    },
    "quality": {
        "quality_threshold": 6.0,
        "auto_delete_threshold": 4.0,
        "content_length_weight": 0.25,
        "keyword_count_weight": 0.20,
        "reference_count_weight": 0.20,
        "content_relevance_weight": 0.20,
        "language_quality_weight": 0.15,
        "content_length_excellent": 2500,
        "content_length_good": 1000,
        "content_length_poor": 500,
        "keyword_count_excellent": 8,
        "keyword_count_good": 5,
        "keyword_count_poor": 3,
        "reference_count_excellent": 3,
        "reference_count_good": 2,
        "reference_count_poor": 1
    },
    "backup": {
        "auto_cleanup_days": 30,
        "max_backup_count": 10
    },
    "security": {
        "dangerous_patterns": "../, ..\\, /, C:\\, ~/",
        "enable_whitelist": True
    },
    "monitoring": {
        "enable_dashboard": True,
        "stats_retention_days": 90
    }
}


class ConfigLoader:
    """配置加载器"""
    
    _instance: Optional['ConfigLoader'] = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls, config_path: Optional[Path] = None):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        初始化配置加载器
        
        Args:
            config_path: 配置文件路径（可选）
        """
        if self._initialized:
            return
        
        self._initialized = True
        self.config_path = config_path or self._get_default_config_path()
        self._config = self._load_config()
        
        logger.info(f"[CONFIG_LOADER] 配置加载完成: {self.config_path}")
    
    def _get_default_config_path(self) -> Path:
        """获取默认配置文件路径"""
        return Path(__file__).parent / "verifier_config.toml"
    
    def _load_config(self) -> Dict[str, Any]:
        """
        加载配置文件
        
        Returns:
            配置字典
        """
        config = DEFAULT_CONFIG.copy()
        
        if not self.config_path.exists():
            logger.warning(f"[CONFIG_LOADER] 配置文件不存在，使用默认配置: {self.config_path}")
            return config
        
        try:
            # 尝试使用tomllib（Python 3.11+）或tomli
            try:
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib
                except ImportError:
                    logger.warning("[CONFIG_LOADER] TOML库未安装，使用默认配置")
                    return config
            
            with open(self.config_path, 'rb') as f:
                user_config = tomllib.load(f)
            
            # 合并配置（用户配置覆盖默认配置）
            for section, values in user_config.items():
                if section in config:
                    config[section].update(values)
                else:
                    config[section] = values
            
            logger.info(f"[CONFIG_LOADER] 成功加载用户配置")
            
        except Exception as e:
            logger.error(f"[CONFIG_LOADER] 加载配置文件失败: {e}")
        
        return config
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            section: 配置节
            key: 配置键
            default: 默认值
        
        Returns:
            配置值
        """
        return self._config.get(section, {}).get(key, default)
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """
        获取整个配置节
        
        Args:
            section: 配置节
        
        Returns:
            配置字典
        """
        return self._config.get(section, {})
    
    def get_duplicates_config(self) -> Dict[str, Any]:
        """获取查重配置"""
        return self.get_section("duplicates")
    
    def get_quality_config(self) -> Dict[str, Any]:
        """获取质量评估配置"""
        return self.get_section("quality")
    
    def get_backup_config(self) -> Dict[str, Any]:
        """获取备份配置"""
        return self.get_section("backup")
    
    def get_security_config(self) -> Dict[str, Any]:
        """获取安全配置"""
        return self.get_section("security")
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """获取监控配置"""
        return self.get_section("monitoring")
    
    def validate_config(self) -> bool:
        """
        验证配置有效性
        
        Returns:
            是否有效
        """
        # 验证权重总和为1.0
        quality_config = self.get_quality_config()
        weights = [
            quality_config.get("content_length_weight", 0),
            quality_config.get("keyword_count_weight", 0),
            quality_config.get("reference_count_weight", 0),
            quality_config.get("content_relevance_weight", 0),
            quality_config.get("language_quality_weight", 0)
        ]
        
        weight_sum = sum(weights)
        if abs(weight_sum - 1.0) > 0.01:
            logger.error(f"[CONFIG_LOADER] 权重总和不为1.0: {weight_sum}")
            return False
        
        # 验证阈值范围
        similarity = self.get("duplicates", "similarity_threshold", 0)
        if not (0 <= similarity <= 1):
            logger.error(f"[CONFIG_LOADER] 相似度阈值超出范围: {similarity}")
            return False
        
        overlap = self.get("duplicates", "overlap_threshold", 0)
        if not (0 <= overlap <= 1):
            logger.error(f"[CONFIG_LOADER] 重叠度阈值超出范围: {overlap}")
            return False
        
        logger.info("[CONFIG_LOADER] 配置验证通过")
        return True
    
    def reload(self) -> bool:
        """
        重新加载配置
        
        Returns:
            是否成功
        """
        self._config = self._load_config()
        return self.validate_config()


# 全局配置加载器实例
_config_loader: Optional[ConfigLoader] = None


def get_config_loader(config_path: Optional[Path] = None) -> ConfigLoader:
    """
    获取配置加载器单例
    
    Args:
        config_path: 配置文件路径（可选）
    
    Returns:
        ConfigLoader实例
    """
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader(config_path)
    return _config_loader


# 便捷函数
def get_similarity_threshold() -> float:
    """获取语义相似度阈值"""
    return get_config_loader().get("duplicates", "similarity_threshold", 0.85)


def get_overlap_threshold() -> float:
    """获取内容重叠度阈值"""
    return get_config_loader().get("duplicates", "overlap_threshold", 0.70)


def get_quality_threshold() -> float:
    """获取质量评分阈值"""
    return get_config_loader().get("quality", "quality_threshold", 6.0)


def get_auto_delete_threshold() -> float:
    """获取自动删除阈值"""
    return get_config_loader().get("quality", "auto_delete_threshold", 4.0)


def get_quality_weights() -> Dict[str, float]:
    """获取质量评分权重"""
    config = get_config_loader().get_quality_config()
    return {
        "content_length": config.get("content_length_weight", 0.25),
        "keyword_count": config.get("keyword_count_weight", 0.20),
        "reference_count": config.get("reference_count_weight", 0.20),
        "content_relevance": config.get("content_relevance_weight", 0.20),
        "language_quality": config.get("language_quality_weight", 0.15)
    }


if __name__ == "__main__":
    # 测试配置加载
    loader = get_config_loader()
    
    print("\n配置加载测试:")
    print(f"  相似度阈值: {get_similarity_threshold()}")
    print(f"  重叠度阈值: {get_overlap_threshold()}")
    print(f"  质量阈值: {get_quality_threshold()}")
    print(f"  自动删除阈值: {get_auto_delete_threshold()}")
    print(f"  权重配置: {get_quality_weights()}")
    
    print(f"\n配置验证: {'通过' if loader.validate_config() else '失败'}")
