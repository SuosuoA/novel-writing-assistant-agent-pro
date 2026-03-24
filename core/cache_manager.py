"""
缓存管理器

V1.0版本
创建日期: 2026-03-24

特性:
- TTL缓存支持（基于cachetools）
- LRU淘汰策略
- 分类缓存管理
- 性能统计
"""

import threading
import time
import hashlib
import json
import logging
from typing import Any, Dict, Optional, Callable
from dataclasses import dataclass, field
from functools import wraps

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
    
    # 各类型缓存大小限制
    worldview_max_size: int = 100  # 条目数
    outline_max_size: int = 50
    character_max_size: int = 100
    style_max_size: int = 50
    continuation_max_size: int = 200
    analysis_max_size: int = 100


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
    
    def __init__(self, maxsize: int, ttl: float):
        self._maxsize = maxsize
        self._ttl = ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if entry.is_expired():
                    del self._cache[key]
                    self._misses += 1
                    return None
                entry.access()
                self._hits += 1
                return entry.value
            self._misses += 1
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
    """
    
    # 缓存类型映射到配置属性
    CACHE_TYPE_MAP = {
        "worldview": ("worldview_ttl", "worldview_max_size"),
        "outline": ("outline_ttl", "outline_max_size"),
        "character": ("character_ttl", "character_max_size"),
        "style": ("style_ttl", "style_max_size"),
        "continuation": ("continuation_ttl", "continuation_max_size"),
        "analysis": ("analysis_ttl", "analysis_max_size"),
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
                self._caches[cache_type] = SimpleTTLCache(maxsize=maxsize, ttl=ttl)
            
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
                return cache.get(key)
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
            else:
                cache.set(key, value, ttl)
    
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
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        stats = {}
        
        for cache_type, cache in self._caches.items():
            if CACHETOOLS_AVAILABLE:
                # cachetools没有直接的统计方法
                stats[cache_type] = {
                    "size": len(cache),
                    "maxsize": cache.maxsize,
                    "ttl": cache.ttl,
                }
            else:
                stats[cache_type] = {
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
    "SimpleTTLCache",
    "generate_cache_key",
    "cached",
    "get_cache_manager",
    "init_cache_manager",
    "CACHETOOLS_AVAILABLE",
]
