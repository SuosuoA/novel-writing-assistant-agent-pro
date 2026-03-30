"""
缓存管理器

V1.1版本
创建日期: 2026-03-24
更新日期: 2026-03-24

特性:
- TTL缓存支持（基于cachetools）
- LRU淘汰策略
- 分类缓存管理
- 性能统计（统一命中率）
- 缓存预热支持
- API调用和缓存日志记录
"""

import threading
import time
import hashlib
import json
import logging
from typing import Any, Dict, Optional, Callable, List
from dataclasses import dataclass, field
from functools import wraps
from datetime import datetime

# 尝试导入cachetools，如果没有则使用内置实现
try:
    from cachetools import TTLCache, LRUCache
    CACHETOOLS_AVAILABLE = True
except ImportError:
    CACHETOOLS_AVAILABLE = False
    TTLCache = None
    LRUCache = None

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """缓存配置"""
    
    # 缓存大小限制（MB）
    max_size_mb: float = 100.0
    
    # 各类型缓存配置
    worldview_ttl: int = 86400  # 24小时
    outline_ttl: int = 3600  # 1小时
    character_ttl: int = 43200  # 12小时
    style_ttl: int = 86400  # 24小时
    continuation_ttl: int = 1800  # 30分钟
    analysis_ttl: int = 7200  # 2小时
    prompt_ttl: int = 3600  # 1小时（V1.1新增：Prompt缓存）
    
    # 各类型缓存大小限制
    worldview_max_size: int = 100  # 条目数
    outline_max_size: int = 50
    character_max_size: int = 100
    style_max_size: int = 50
    continuation_max_size: int = 200
    analysis_max_size: int = 100
    prompt_max_size: int = 500  # V1.1新增
    
    # V1.1新增：是否启用日志
    enable_logging: bool = True


@dataclass
class CacheStats:
    """缓存统计信息（V1.1新增）"""
    total_hits: int = 0
    total_misses: int = 0
    api_calls: int = 0
    cache_saves: int = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.total_hits + self.total_misses
        return self.total_hits / total if total > 0 else 0.0


class CacheEntry:
    """缓存条目"""
    
    def __init__(self, key: str, value: Any, ttl: int):
        self.key = key
        self.value = value
        self.ttl = ttl
        self.created_at = time.time()
        self.expires_at = self.created_at + ttl
        self.access_count = 0
        self.last_access = self.created_at
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() > self.expires_at
    
    def access(self):
        """访问缓存"""
        self.access_count += 1
        self.last_access = time.time()


class SimpleTTLCache:
    """简单的TTL缓存实现（当cachetools不可用时使用）"""
    
    def __init__(self, maxsize: int, ttl: float, stats: Optional['CacheStats'] = None):
        self._maxsize = maxsize
        self._ttl = ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._stats = stats  # V1.1新增：引用全局统计
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if entry.is_expired():
                    del self._cache[key]
                    self._misses += 1
                    # V1.1新增：更新全局统计
                    if self._stats:
                        self._stats.total_misses += 1
                    return None
                entry.access()
                self._hits += 1
                # V1.1新增：更新全局统计
                if self._stats:
                    self._stats.total_hits += 1
                return entry.value
            self._misses += 1
            # V1.1新增：更新全局统计
            if self._stats:
                self._stats.total_misses += 1
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """设置缓存"""
        with self._lock:
            # 清理过期条目
            self._cleanup_expired()
            
            # 如果超过最大大小，删除最旧的条目
            if len(self._cache) >= self._maxsize:
                self._evict_oldest()
            
            entry_ttl = ttl if ttl is not None else self._ttl
            self._cache[key] = CacheEntry(key, value, entry_ttl)
            
            # V1.1新增：更新全局统计
            if self._stats:
                self._stats.cache_saves += 1
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
    
    def _cleanup_expired(self) -> None:
        """清理过期条目"""
        expired_keys = [k for k, v in self._cache.items() if v.is_expired()]
        for key in expired_keys:
            del self._cache[key]
    
    def _evict_oldest(self) -> None:
        """驱逐最旧的条目"""
        if not self._cache:
            return
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].created_at)
        del self._cache[oldest_key]
    
    def __len__(self) -> int:
        return len(self._cache)
    
    @property
    def hits(self) -> int:
        return self._hits
    
    @property
    def misses(self) -> int:
        return self._misses
    
    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0


class CacheManager:
    """
    缓存管理器
    
    管理多种类型的缓存，支持TTL和LRU淘汰策略
    
    V1.1新增：
    - 统一命中率统计
    - 缓存预热支持
    - API调用日志记录
    """
    
    # 缓存类型映射到配置属性
    CACHE_TYPE_MAP = {
        "worldview": ("worldview_ttl", "worldview_max_size"),
        "outline": ("outline_ttl", "outline_max_size"),
        "character": ("character_ttl", "character_max_size"),
        "style": ("style_ttl", "style_max_size"),
        "continuation": ("continuation_ttl", "continuation_max_size"),
        "analysis": ("analysis_ttl", "analysis_max_size"),
        "prompt": ("prompt_ttl", "prompt_max_size"),  # V1.1新增
    }
    
    def __init__(self, config: Optional[CacheConfig] = None):
        """
        初始化缓存管理器
        
        Args:
            config: 缓存配置
        """
        self._config = config or CacheConfig()
        self._caches: Dict[str, Any] = {}
        self._lock = threading.RLock()
        
        # V1.1新增：统一统计
        self._stats = CacheStats()
        
        # V1.1新增：预热数据加载器注册表
        self._warmup_loaders: Dict[str, Callable[[], Dict[str, Any]]] = {}
        
        # 初始化各类缓存
        self._init_caches()
    
    def _init_caches(self) -> None:
        """初始化各类缓存"""
        for cache_type, (ttl_attr, size_attr) in self.CACHE_TYPE_MAP.items():
            ttl = getattr(self._config, ttl_attr)
            maxsize = getattr(self._config, size_attr)
            
            if CACHETOOLS_AVAILABLE:
                self._caches[cache_type] = TTLCache(maxsize=maxsize, ttl=ttl)
            else:
                self._caches[cache_type] = SimpleTTLCache(
                    maxsize=maxsize, ttl=ttl, stats=self._stats
                )
            
            logger.debug(f"初始化缓存: {cache_type}, TTL={ttl}s, maxsize={maxsize}")
    
    def get(self, cache_type: str, key: str) -> Optional[Any]:
        """
        获取缓存
        
        Args:
            cache_type: 缓存类型
            key: 缓存键
            
        Returns:
            缓存值，不存在或过期返回None
        """
        with self._lock:
            cache = self._caches.get(cache_type)
            if not cache:
                logger.warning(f"未知的缓存类型: {cache_type}")
                return None
            
            if CACHETOOLS_AVAILABLE:
                value = cache.get(key)
                # V1.1新增：更新统计
                if value is not None:
                    self._stats.total_hits += 1
                else:
                    self._stats.total_misses += 1
                return value
            else:
                return cache.get(key)
    
    def set(self, cache_type: str, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        设置缓存
        
        Args:
            cache_type: 缓存类型
            key: 缓存键
            value: 缓存值
            ttl: 可选的TTL覆盖
        """
        with self._lock:
            cache = self._caches.get(cache_type)
            if not cache:
                logger.warning(f"未知的缓存类型: {cache_type}")
                return
            
            if CACHETOOLS_AVAILABLE:
                if ttl is not None:
                    # cachetools的TTLCache不支持单独设置TTL，使用默认值
                    cache[key] = value
                else:
                    cache[key] = value
                # V1.1新增：更新统计
                self._stats.cache_saves += 1
            else:
                cache.set(key, value, ttl)
            
            # V1.1新增：记录日志
            if self._config.enable_logging:
                logger.debug(f"缓存存储: {cache_type}/{key[:16]}...")
    
    def delete(self, cache_type: str, key: str) -> bool:
        """删除缓存"""
        with self._lock:
            cache = self._caches.get(cache_type)
            if not cache:
                return False
            
            if CACHETOOLS_AVAILABLE:
                if key in cache:
                    del cache[key]
                    return True
                return False
            else:
                return cache.delete(key)
    
    def clear(self, cache_type: Optional[str] = None) -> None:
        """
        清空缓存
        
        Args:
            cache_type: 可选的缓存类型，不指定则清空所有
        """
        with self._lock:
            if cache_type:
                cache = self._caches.get(cache_type)
                if cache:
                    if CACHETOOLS_AVAILABLE:
                        cache.clear()
                    else:
                        cache.clear()
            else:
                for cache in self._caches.values():
                    if CACHETOOLS_AVAILABLE:
                        cache.clear()
                    else:
                        cache.clear()
    
    # =========================================================================
    # V1.1新增：缓存预热支持
    # =========================================================================
    
    def register_warmup_loader(
        self, cache_type: str, loader: Callable[[], Dict[str, Any]]
    ) -> None:
        """
        注册缓存预热数据加载器
        
        Args:
            cache_type: 缓存类型
            loader: 数据加载函数，返回 {key: value} 字典
        """
        self._warmup_loaders[cache_type] = loader
        logger.debug(f"注册预热加载器: {cache_type}")
    
    def warmup(self, cache_types: Optional[List[str]] = None) -> Dict[str, int]:
        """
        执行缓存预热
        
        Args:
            cache_types: 要预热的缓存类型列表，None表示全部
            
        Returns:
            各类型预热的条目数
        """
        results = {}
        types_to_warmup = cache_types or list(self._warmup_loaders.keys())
        
        for cache_type in types_to_warmup:
            loader = self._warmup_loaders.get(cache_type)
            if not loader:
                logger.debug(f"未注册预热加载器: {cache_type}")
                continue
            
            try:
                data = loader()
                count = 0
                for key, value in data.items():
                    self.set(cache_type, key, value)
                    count += 1
                
                results[cache_type] = count
                logger.info(f"缓存预热完成: {cache_type}, 加载{count}条")
                
            except Exception as e:
                logger.error(f"缓存预热失败: {cache_type}, {e}")
                results[cache_type] = 0
        
        return results
    
    def warmup_from_file(
        self, cache_type: str, file_path: str, key_field: str = "key"
    ) -> int:
        """
        从文件预热缓存
        
        Args:
            cache_type: 缓存类型
            file_path: 数据文件路径（JSON格式）
            key_field: 用作缓存键的字段名
            
        Returns:
            预热的条目数
        """
        try:
            from pathlib import Path
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"预热文件不存在: {file_path}")
                return 0
            
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            count = 0
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and key_field in item:
                        key = str(item[key_field])
                        self.set(cache_type, key, item)
                        count += 1
            elif isinstance(data, dict):
                for key, value in data.items():
                    self.set(cache_type, key, value)
                    count += 1
            
            logger.info(f"从文件预热缓存: {cache_type}, 加载{count}条")
            return count
            
        except Exception as e:
            logger.error(f"从文件预热缓存失败: {e}")
            return 0
    
    # =========================================================================
    # V1.1新增：统计和日志
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        stats = {
            "global": {
                "total_hits": self._stats.total_hits,
                "total_misses": self._stats.total_misses,
                "api_calls": self._stats.api_calls,
                "cache_saves": self._stats.cache_saves,
                "hit_rate": self._stats.hit_rate,
            },
            "caches": {}
        }
        
        for cache_type, cache in self._caches.items():
            if CACHETOOLS_AVAILABLE:
                # cachetools没有直接的统计方法
                stats["caches"][cache_type] = {
                    "size": len(cache),
                    "maxsize": cache.maxsize,
                    "ttl": cache.ttl,
                }
            else:
                stats["caches"][cache_type] = {
                    "size": len(cache),
                    "maxsize": cache._maxsize,
                    "ttl": cache._ttl,
                    "hits": cache.hits,
                    "misses": cache.misses,
                    "hit_rate": cache.hit_rate,
                }
        
        return stats
    
    def get_hit_rate(self, cache_type: str) -> float:
        """获取缓存命中率"""
        cache = self._caches.get(cache_type)
        if not cache:
            return 0.0
        
        if CACHETOOLS_AVAILABLE:
            # cachetools不支持命中率统计
            return -1.0  # 表示不支持
        else:
            return cache.hit_rate
    
    def record_api_call(self) -> None:
        """记录API调用（V1.1新增）"""
        self._stats.api_calls += 1
    
    def log_performance_summary(self) -> None:
        """记录性能摘要日志（V1.1新增）"""
        stats = self.get_stats()
        global_stats = stats["global"]
        
        logger.info(
            f"缓存性能摘要: "
            f"命中率={global_stats['hit_rate']:.2%}, "
            f"命中={global_stats['total_hits']}, "
            f"未命中={global_stats['total_misses']}, "
            f"API调用={global_stats['api_calls']}, "
            f"缓存保存={global_stats['cache_saves']}"
        )


def generate_cache_key(*args, **kwargs) -> str:
    """
    生成缓存键
    
    基于参数生成唯一的缓存键
    """
    key_data = {
        "args": [str(a) for a in args],
        "kwargs": {k: str(v) for k, v in sorted(kwargs.items())}
    }
    key_str = json.dumps(key_data, sort_keys=True)
    return hashlib.md5(key_str.encode()).hexdigest()


def cached(cache_type: str, key_func: Optional[Callable] = None):
    """
    缓存装饰器
    
    Args:
        cache_type: 缓存类型
        key_func: 可选的自定义键生成函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 获取缓存管理器实例
            cache_manager = get_cache_manager()
            
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = generate_cache_key(*args, **kwargs)
            
            # 尝试从缓存获取
            cached_value = cache_manager.get(cache_type, cache_key)
            if cached_value is not None:
                logger.debug(f"缓存命中: {cache_type}/{cache_key}")
                return cached_value
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 存入缓存
            if result is not None:
                cache_manager.set(cache_type, cache_key, result)
                logger.debug(f"缓存存储: {cache_type}/{cache_key}")
            
            return result
        
        return wrapper
    return decorator


# 全局单例
_cache_manager: Optional[CacheManager] = None
_cache_lock = threading.Lock()


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器实例"""
    global _cache_manager
    if _cache_manager is None:
        with _cache_lock:
            if _cache_manager is None:
                _cache_manager = CacheManager()
    return _cache_manager


def init_cache_manager(config: Optional[CacheConfig] = None) -> CacheManager:
    """
    初始化全局缓存管理器
    
    Args:
        config: 缓存配置
        
    Returns:
        缓存管理器实例
    """
    global _cache_manager
    with _cache_lock:
        _cache_manager = CacheManager(config)
    return _cache_manager


__all__ = [
    "CacheManager",
    "CacheConfig",
    "CacheEntry",
    "CacheStats",
    "SimpleTTLCache",
    "generate_cache_key",
    "cached",
    "get_cache_manager",
    "init_cache_manager",
    "CACHETOOLS_AVAILABLE",
]
