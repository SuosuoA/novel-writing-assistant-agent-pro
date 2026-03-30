"""
缓存预热服务

V1.0版本
创建日期: 2026-03-24

特性:
- 用户登录时预加载常用缓存
- 支持多种预热数据源
- 异步预热，不阻塞启动
- 预热进度监控
"""

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class CacheWarmupService:
    """
    缓存预热服务
    
    在用户登录或项目打开时，自动预加载常用数据到缓存中，
    减少首次访问时的延迟。
    
    预热数据源优先级：
    1. 项目设定文件（大纲、人设、世界观）
    2. 用户偏好配置
    3. 常用Prompt模板
    4. 历史生成记录统计
    """
    
    def __init__(self, cache_manager: Any, project_path: Optional[str] = None):
        """
        初始化缓存预热服务
        
        Args:
            cache_manager: 缓存管理器实例
            project_path: 项目根目录路径
        """
        self._cache_manager = cache_manager
        self._project_path = Path(project_path) if project_path else None
        self._lock = threading.Lock()
        self._warmup_status: Dict[str, Any] = {
            "in_progress": False,
            "completed": False,
            "results": {}
        }
        
        # 注册默认预热加载器
        self._register_default_loaders()
    
    def _register_default_loaders(self) -> None:
        """注册默认的预热加载器"""
        self._cache_manager.register_warmup_loader(
            "worldview", self._load_worldview_data
        )
        self._cache_manager.register_warmup_loader(
            "outline", self._load_outline_data
        )
        self._cache_manager.register_warmup_loader(
            "character", self._load_character_data
        )
        self._cache_manager.register_warmup_loader(
            "style", self._load_style_data
        )
        
        logger.debug("已注册默认缓存预热加载器")
    
    def warmup_async(
        self, 
        cache_types: Optional[List[str]] = None,
        callback: Optional[Callable[[Dict[str, int]], None]] = None
    ) -> None:
        """
        异步执行缓存预热
        
        Args:
            cache_types: 要预热的缓存类型列表
            callback: 预热完成后的回调函数
        """
        with self._lock:
            if self._warmup_status["in_progress"]:
                logger.warning("缓存预热正在进行中，跳过")
                return
            
            self._warmup_status["in_progress"] = True
            self._warmup_status["completed"] = False
        
        def _warmup_thread():
            try:
                results = self.warmup(cache_types)
                
                with self._lock:
                    self._warmup_status["completed"] = True
                    self._warmup_status["in_progress"] = False
                    self._warmup_status["results"] = results
                
                if callback:
                    callback(results)
                    
            except Exception as e:
                logger.error(f"缓存预热失败: {e}")
                with self._lock:
                    self._warmup_status["in_progress"] = False
        
        thread = threading.Thread(target=_warmup_thread, daemon=True)
        thread.start()
        
        logger.info("缓存预热已启动（异步）")
    
    def warmup(self, cache_types: Optional[List[str]] = None) -> Dict[str, int]:
        """
        同步执行缓存预热
        
        Args:
            cache_types: 要预热的缓存类型列表
            
        Returns:
            各类型预热的条目数
        """
        start_time = time.time()
        logger.info("开始缓存预热...")
        
        results = self._cache_manager.warmup(cache_types)
        
        elapsed = time.time() - start_time
        total_items = sum(results.values())
        
        logger.info(
            f"缓存预热完成: 加载{total_items}条数据, 耗时{elapsed:.2f}秒, "
            f"结果={results}"
        )
        
        return results
    
    def get_warmup_status(self) -> Dict[str, Any]:
        """获取预热状态"""
        with self._lock:
            return dict(self._warmup_status)
    
    # =========================================================================
    # 默认预热加载器实现
    # =========================================================================
    
    def _load_worldview_data(self) -> Dict[str, Any]:
        """加载世界观数据"""
        data = {}
        
        if not self._project_path:
            return data
        
        # 查找世界观文件
        worldview_patterns = ["世界观", "worldview", "设定"]
        for pattern in worldview_patterns:
            for ext in ['.txt', '.md', '.json', '.yaml']:
                worldview_file = self._project_path / f"{pattern}{ext}"
                if worldview_file.exists():
                    try:
                        content = worldview_file.read_text(encoding='utf-8')
                        # 使用文件路径作为缓存键
                        key = f"file:{worldview_file.name}"
                        data[key] = {
                            "content": content,
                            "source": str(worldview_file),
                            "type": "worldview"
                        }
                        logger.debug(f"预热世界观: {worldview_file.name}")
                    except Exception as e:
                        logger.warning(f"读取世界观文件失败: {worldview_file}: {e}")
        
        return data
    
    def _load_outline_data(self) -> Dict[str, Any]:
        """加载大纲数据"""
        data = {}
        
        if not self._project_path:
            return data
        
        # 查找大纲文件
        outline_patterns = ["大纲", "outline", "章节大纲"]
        for pattern in outline_patterns:
            for ext in ['.txt', '.md', '.json']:
                outline_file = self._project_path / f"{pattern}{ext}"
                if outline_file.exists():
                    try:
                        content = outline_file.read_text(encoding='utf-8')
                        key = f"file:{outline_file.name}"
                        data[key] = {
                            "content": content,
                            "source": str(outline_file),
                            "type": "outline"
                        }
                        logger.debug(f"预热大纲: {outline_file.name}")
                    except Exception as e:
                        logger.warning(f"读取大纲文件失败: {outline_file}: {e}")
        
        return data
    
    def _load_character_data(self) -> Dict[str, Any]:
        """加载人物设定数据"""
        data = {}
        
        if not self._project_path:
            return data
        
        # 查找人物设定目录或文件
        char_dir = self._project_path / "人物设定"
        if char_dir.exists() and char_dir.is_dir():
            for char_file in char_dir.glob("*.md"):
                try:
                    content = char_file.read_text(encoding='utf-8')
                    key = f"char:{char_file.stem}"
                    data[key] = {
                        "content": content,
                        "name": char_file.stem,
                        "source": str(char_file),
                        "type": "character"
                    }
                    logger.debug(f"预热人物: {char_file.stem}")
                except Exception as e:
                    logger.warning(f"读取人物文件失败: {char_file}: {e}")
        
        # 也检查单文件格式
        char_patterns = ["人物设定", "characters", "人物"]
        for pattern in char_patterns:
            for ext in ['.txt', '.md', '.json']:
                char_file = self._project_path / f"{pattern}{ext}"
                if char_file.exists():
                    try:
                        content = char_file.read_text(encoding='utf-8')
                        key = f"file:{char_file.name}"
                        data[key] = {
                            "content": content,
                            "source": str(char_file),
                            "type": "character_collection"
                        }
                        logger.debug(f"预热人物设定: {char_file.name}")
                    except Exception as e:
                        logger.warning(f"读取人物设定文件失败: {char_file}: {e}")
        
        return data
    
    def _load_style_data(self) -> Dict[str, Any]:
        """加载风格档案数据"""
        data = {}
        
        if not self._project_path:
            return data
        
        # 查找风格档案文件
        style_patterns = ["风格档案", "style_profile", "风格"]
        for pattern in style_patterns:
            for ext in ['.json', '.yaml', '.txt']:
                style_file = self._project_path / f"{pattern}{ext}"
                if style_file.exists():
                    try:
                        content = style_file.read_text(encoding='utf-8')
                        key = f"style:{style_file.name}"
                        data[key] = {
                            "content": content,
                            "source": str(style_file),
                            "type": "style"
                        }
                        logger.debug(f"预热风格档案: {style_file.name}")
                    except Exception as e:
                        logger.warning(f"读取风格档案失败: {style_file}: {e}")
        
        return data
    
    # =========================================================================
    # 项目路径管理
    # =========================================================================
    
    def set_project_path(self, path: str) -> None:
        """设置项目路径"""
        self._project_path = Path(path)
        logger.info(f"缓存预热服务项目路径已设置: {path}")
    
    def warmup_for_project(self, project_path: str) -> Dict[str, int]:
        """
        为指定项目执行缓存预热
        
        Args:
            project_path: 项目路径
            
        Returns:
            预热结果
        """
        self.set_project_path(project_path)
        return self.warmup()


# 全局实例
_warmup_service: Optional[CacheWarmupService] = None
_warmup_lock = threading.Lock()


def get_warmup_service(
    cache_manager: Optional[Any] = None, 
    project_path: Optional[str] = None
) -> CacheWarmupService:
    """
    获取全局缓存预热服务实例
    
    Args:
        cache_manager: 缓存管理器实例
        project_path: 项目路径
        
    Returns:
        缓存预热服务实例
    """
    global _warmup_service
    
    if _warmup_service is None:
        with _warmup_lock:
            if _warmup_service is None:
                if cache_manager is None:
                    from core.cache_manager import get_cache_manager
                    cache_manager = get_cache_manager()
                
                _warmup_service = CacheWarmupService(cache_manager, project_path)
    
    return _warmup_service


__all__ = [
    "CacheWarmupService",
    "get_warmup_service",
]
