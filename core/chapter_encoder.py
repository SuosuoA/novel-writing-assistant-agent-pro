"""
章节向量编码器 - OpenClaw L2温记忆

V1.0版本
创建日期：2026-03-25

特性：
- 为每章小说生成语义向量（OpenClaw L2温记忆）
- 支持增量更新（新章节追加，不重建索引）
- 支持批量编码（多章节同时处理）
- 支持更新已存在章节（内容修改后重新编码）
- 集成LanceDB向量存储（recall_similar_chapters）
- EventBus集成（编码完成事件）
- 线程安全设计
- 编码统计（总数、成功率、失败数）

设计参考：
- OpenClaw mem9 L2温记忆架构
- 升级方案 10.升级方案✅️.md
- ADR-001: LanceDB作为向量数据库

使用示例：
    # 创建编码器实例
    encoder = ChapterEncoder(workspace_root=Path("E:/project"))
    
    # 编码单个章节
    success = encoder.encode_chapter(
        chapter_id="chapter-001",
        content="第一章的内容...",
        metadata={"title": "开篇", "word_count": 3000}
    )
    
    # 批量编码
    results = encoder.encode_chapters_batch([
        {"chapter_id": "chapter-001", "content": "...", "metadata": {...}},
        {"chapter_id": "chapter-002", "content": "...", "metadata": {...}}
    ])
    
    # 增量更新（检测新增章节）
    encoder.incremental_encode(chapters_dir=Path("大纲"))
    
    # 查询章节向量
    chapter = encoder.get_chapter_vector("chapter-001")
    
    # 召回相似章节
    similar_chapters = encoder.recall_similar_chapters(
        query="星际飞船穿越虫洞",
        top_k=10
    )
"""

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Pydantic数据模型
# ============================================================================


class ChapterEncodingResult(BaseModel):
    """章节编码结果"""
    
    model_config = ConfigDict(frozen=False)
    
    chapter_id: str = Field(description="章节ID")
    success: bool = Field(description="编码是否成功")
    vector_dimension: Optional[int] = Field(default=None, description="向量维度")
    content_length: int = Field(description="内容长度（字符数）")
    encoding_time_ms: float = Field(description="编码耗时（毫秒）")
    error_message: Optional[str] = Field(default=None, description="错误信息（如果失败）")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="时间戳")


class BatchEncodingResult(BaseModel):
    """批量编码结果"""
    
    model_config = ConfigDict(frozen=False)
    
    total_chapters: int = Field(description="总章节数")
    successful: int = Field(description="成功编码数量")
    failed: int = Field(description="失败数量")
    total_time_ms: float = Field(description="总耗时（毫秒）")
    results: List[ChapterEncodingResult] = Field(default_factory=list, description="各章节编码结果")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="时间戳")


class EncodingStats(BaseModel):
    """编码统计"""
    
    model_config = ConfigDict(frozen=False)
    
    total_encoded: int = Field(default=0, description="已编码章节总数")
    successful: int = Field(default=0, description="成功编码总数")
    failed: int = Field(default=0, description="失败编码总数")
    last_encoding_time: Optional[str] = Field(default=None, description="最后编码时间")
    total_content_length: int = Field(default=0, description="已编码内容总长度（字符数）")
    average_encoding_time_ms: float = Field(default=0.0, description="平均编码耗时（毫秒）")


# ============================================================================
# 章节向量编码器
# ============================================================================


class ChapterEncoder:
    """
    章节向量编码器 - OpenClaw L2温记忆
    
    功能：
    - 为每章小说生成语义向量
    - 支持增量更新
    - 支持批量编码
    - 集成LanceDB向量存储
    - EventBus集成
    - 线程安全
    """
    
    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        vector_store=None,
        embedding_type: str = "openai",
        embedding_model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None
    ):
        """
        初始化章节编码器
        
        Args:
            workspace_root: 工作区根目录
            vector_store: NovelVectorStore实例（可选，自动创建）
            embedding_type: 嵌入类型（openai/local）
            embedding_model: 嵌入模型名称
            api_key: OpenAI API密钥
            api_base: OpenAI API基础URL
        """
        self.workspace_root = workspace_root or Path.cwd()
        self._embedding_type = embedding_type
        self._embedding_model = embedding_model
        self._api_key = api_key
        self._api_base = api_base
        
        # 延迟导入VectorStore，避免循环依赖
        self._vector_store = None
        self._vector_store_provided = vector_store is not None
        if vector_store:
            self._vector_store = vector_store
        
        # 编码统计
        self._stats = EncodingStats()
        self._stats_lock = threading.RLock()
        
        # 线程安全锁
        self._encoding_lock = threading.RLock()
        
        # EventBus延迟导入
        self._event_bus = None
        
        # Logger
        self._logger = logging.getLogger(__name__)
        
        # 编码历史记录（用于增量更新）
        self._encoding_history: Dict[str, Dict[str, Any]] = {}
        self._history_lock = threading.RLock()
        
        # 历史记录文件路径
        self._history_file = self.workspace_root / "data" / "chapter_encoding_history.json"
        
        # 加载历史记录
        self._load_history()
    
    def _get_vector_store(self):
        """延迟获取VectorStore实例"""
        if not self._vector_store:
            try:
                from infrastructure.vector_store import get_vector_store
                self._vector_store = get_vector_store(
                    embedding_type=self._embedding_type,
                    embedding_model=self._embedding_model,
                    api_key=self._api_key,
                    api_base=self._api_base
                )
            except Exception as e:
                self._logger.error(f"获取VectorStore失败: {e}")
                raise
        return self._vector_store
    
    def _get_event_bus(self):
        """延迟获取EventBus实例"""
        if not self._event_bus:
            try:
                from core.event_bus import EventBus
                self._event_bus = EventBus.get_instance()
            except Exception:
                # EventBus不可用时忽略
                pass
        return self._event_bus
    
    def _load_history(self):
        """加载编码历史记录"""
        if not self._history_file.exists():
            return
        
        try:
            with open(self._history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
                with self._history_lock:
                    self._encoding_history = history
        except Exception as e:
            self._logger.warning(f"加载编码历史失败: {e}")
    
    def _save_history(self):
        """保存编码历史记录"""
        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._history_file, 'w', encoding='utf-8') as f:
                with self._history_lock:
                    json.dump(self._encoding_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._logger.error(f"保存编码历史失败: {e}")
    
    def encode_chapter(
        self,
        chapter_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChapterEncodingResult:
        """
        编码单个章节
        
        Args:
            chapter_id: 章节ID（如chapter-001）
            content: 章节文本内容
            metadata: 元数据（标题、字数等）
        
        Returns:
            ChapterEncodingResult: 编码结果
        """
        start_time = time.time()
        
        try:
            # 参数验证
            if not chapter_id:
                raise ValueError("chapter_id不能为空")
            if not content or len(content.strip()) == 0:
                raise ValueError("content不能为空")
            
            # 获取VectorStore
            vector_store = self._get_vector_store()
            
            # 编码前检查章节是否已存在
            existing_chapter = self.get_chapter_vector(chapter_id)
            if existing_chapter:
                self._logger.info(f"章节 {chapter_id} 已存在，将更新向量")
            
            # 调用VectorStore添加章节
            success = vector_store.add_chapter(
                chapter_id=chapter_id,
                content=content,
                metadata=metadata or {}
            )
            
            if not success:
                raise RuntimeError("VectorStore添加章节失败")
            
            # 计算编码耗时
            encoding_time_ms = (time.time() - start_time) * 1000
            
            # 获取向量维度
            vector_dimension = None
            if hasattr(vector_store, '_embedding_dimension'):
                vector_dimension = vector_store._embedding_dimension
            
            # 更新统计
            with self._stats_lock:
                self._stats.total_encoded += 1
                self._stats.successful += 1
                self._stats.last_encoding_time = datetime.now().isoformat()
                self._stats.total_content_length += len(content)
                if self._stats.successful > 0:
                    self._stats.average_encoding_time_ms = (
                        (self._stats.average_encoding_time_ms * (self._stats.successful - 1) + encoding_time_ms)
                        / self._stats.successful
                    )
            
            # 更新历史记录
            with self._history_lock:
                self._encoding_history[chapter_id] = {
                    "chapter_id": chapter_id,
                    "content_length": len(content),
                    "metadata": metadata,
                    "encoding_time_ms": encoding_time_ms,
                    "vector_dimension": vector_dimension,
                    "timestamp": datetime.now().isoformat()
                }
            self._save_history()
            
            # 发布EventBus事件
            event_bus = self._get_event_bus()
            if event_bus:
                event_bus.publish(
                    event_type="chapter.encoding.completed",
                    data={
                        "chapter_id": chapter_id,
                        "content_length": len(content),
                        "encoding_time_ms": encoding_time_ms,
                        "vector_dimension": vector_dimension
                    },
                    source="ChapterEncoder"
                )
            
            self._logger.info(
                f"章节编码成功: {chapter_id}, "
                f"内容长度={len(content)}, "
                f"耗时={encoding_time_ms:.2f}ms"
            )
            
            return ChapterEncodingResult(
                chapter_id=chapter_id,
                success=True,
                vector_dimension=vector_dimension,
                content_length=len(content),
                encoding_time_ms=encoding_time_ms,
                timestamp=datetime.now().isoformat()
            )
        
        except Exception as e:
            encoding_time_ms = (time.time() - start_time) * 1000
            
            # 更新失败统计
            with self._stats_lock:
                self._stats.total_encoded += 1
                self._stats.failed += 1
                self._stats.last_encoding_time = datetime.now().isoformat()
            
            # 发布失败事件
            event_bus = self._get_event_bus()
            if event_bus:
                event_bus.publish(
                    event_type="chapter.encoding.failed",
                    data={
                        "chapter_id": chapter_id,
                        "error": str(e),
                        "encoding_time_ms": encoding_time_ms
                    },
                    source="ChapterEncoder"
                )
            
            self._logger.error(f"章节编码失败: {chapter_id}, 错误: {e}")
            
            return ChapterEncodingResult(
                chapter_id=chapter_id,
                success=False,
                content_length=len(content) if content else 0,
                encoding_time_ms=encoding_time_ms,
                error_message=str(e),
                timestamp=datetime.now().isoformat()
            )
    
    def encode_chapters_batch(
        self,
        chapters: List[Dict[str, Any]]
    ) -> BatchEncodingResult:
        """
        批量编码章节
        
        Args:
            chapters: 章节列表，每个元素包含chapter_id、content、metadata
        
        Returns:
            BatchEncodingResult: 批量编码结果
        """
        start_time = time.time()
        results = []
        successful = 0
        failed = 0
        
        for chapter_data in chapters:
            chapter_id = chapter_data.get("chapter_id")
            content = chapter_data.get("content")
            metadata = chapter_data.get("metadata")
            
            result = self.encode_chapter(
                chapter_id=chapter_id,
                content=content,
                metadata=metadata
            )
            
            results.append(result)
            
            if result.success:
                successful += 1
            else:
                failed += 1
        
        total_time_ms = (time.time() - start_time) * 1000
        
        self._logger.info(
            f"批量编码完成: 总数={len(chapters)}, "
            f"成功={successful}, 失败={failed}, "
            f"总耗时={total_time_ms:.2f}ms"
        )
        
        return BatchEncodingResult(
            total_chapters=len(chapters),
            successful=successful,
            failed=failed,
            total_time_ms=total_time_ms,
            results=results,
            timestamp=datetime.now().isoformat()
        )
    
    def incremental_encode(
        self,
        chapters_dir: Path,
        force: bool = False
    ) -> BatchEncodingResult:
        """
        增量编码 - 检测新增章节并编码
        
        Args:
            chapters_dir: 章节目录路径
            force: 是否强制重新编码所有章节
        
        Returns:
            BatchEncodingResult: 增量编码结果
        """
        if not chapters_dir.exists():
            raise FileNotFoundError(f"章节目录不存在: {chapters_dir}")
        
        # 扫描章节文件
        chapter_files = list(chapters_dir.glob("*.md")) + list(chapters_dir.glob("*.txt"))
        
        if not chapter_files:
            self._logger.info(f"章节目录为空: {chapters_dir}")
            return BatchEncodingResult(
                total_chapters=0,
                successful=0,
                failed=0,
                total_time_ms=0.0,
                results=[],
                timestamp=datetime.now().isoformat()
            )
        
        # 过滤需要编码的章节
        chapters_to_encode = []
        
        for chapter_file in chapter_files:
            chapter_id = chapter_file.stem  # 文件名（不含扩展名）
            
            # 检查是否需要编码
            if not force and chapter_id in self._encoding_history:
                # 检查文件是否修改
                file_mtime = chapter_file.stat().st_mtime
                history_entry = self._encoding_history[chapter_id]
                encoding_time = datetime.fromisoformat(history_entry["timestamp"]).timestamp()
                
                if file_mtime <= encoding_time:
                    # 文件未修改，跳过
                    continue
            
            # 读取章节内容
            try:
                content = chapter_file.read_text(encoding='utf-8')
                
                # 提取元数据（从文件名或内容开头）
                metadata = self._extract_metadata(chapter_file, content)
                
                chapters_to_encode.append({
                    "chapter_id": chapter_id,
                    "content": content,
                    "metadata": metadata
                })
            
            except Exception as e:
                self._logger.error(f"读取章节文件失败: {chapter_file}, 错误: {e}")
        
        if not chapters_to_encode:
            self._logger.info("所有章节已编码，无需增量更新")
            return BatchEncodingResult(
                total_chapters=0,
                successful=0,
                failed=0,
                total_time_ms=0.0,
                results=[],
                timestamp=datetime.now().isoformat()
            )
        
        self._logger.info(f"检测到 {len(chapters_to_encode)} 个新章节/修改章节")
        
        # 批量编码
        return self.encode_chapters_batch(chapters_to_encode)
    
    def _extract_metadata(self, chapter_file: Path, content: str) -> Dict[str, Any]:
        """
        提取章节元数据
        
        Args:
            chapter_file: 章节文件路径
            content: 章节内容
        
        Returns:
            元数据字典
        """
        metadata = {
            "file_name": chapter_file.name,
            "file_path": str(chapter_file),
            "word_count": len(content)
        }
        
        # 尝试从内容开头提取标题（如：# 第一章）
        lines = content.split('\n')
        if lines and lines[0].startswith('#'):
            metadata["title"] = lines[0].lstrip('#').strip()
        
        return metadata
    
    def get_chapter_vector(self, chapter_id: str) -> Optional[Dict[str, Any]]:
        """
        获取章节向量
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            章节向量信息（如果存在）
        """
        try:
            vector_store = self._get_vector_store()
            
            # 检查章节是否存在
            if hasattr(vector_store, 'get_chapter'):
                return vector_store.get_chapter(chapter_id)
            
            # 降级：从历史记录获取
            with self._history_lock:
                return self._encoding_history.get(chapter_id)
        
        except Exception as e:
            self._logger.error(f"获取章节向量失败: {chapter_id}, 错误: {e}")
            return None
    
    def recall_similar_chapters(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        召回相似章节（长篇连贯性召回）
        
        Args:
            query: 查询文本
            top_k: 返回数量
            min_score: 最小相似度阈值
        
        Returns:
            相似章节列表
        """
        try:
            vector_store = self._get_vector_store()
            
            results = vector_store.recall_similar_chapters(
                query=query,
                top_k=top_k
            )
            
            # 过滤低分结果
            filtered_results = [
                r for r in results
                if r.get("score", 0) >= min_score
            ]
            
            self._logger.info(
                f"召回相似章节: 查询='{query[:30]}...', "
                f"结果数={len(filtered_results)}"
            )
            
            return filtered_results
        
        except Exception as e:
            self._logger.error(f"召回相似章节失败: {e}")
            return []
    
    def delete_chapter(self, chapter_id: str) -> bool:
        """
        删除章节向量
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            是否删除成功
        """
        try:
            vector_store = self._get_vector_store()
            
            # 调用VectorStore删除章节
            if hasattr(vector_store, 'delete_chapter'):
                success = vector_store.delete_chapter(chapter_id)
            else:
                self._logger.warning("VectorStore不支持delete_chapter方法")
                success = False
            
            # 更新历史记录
            if success:
                with self._history_lock:
                    if chapter_id in self._encoding_history:
                        del self._encoding_history[chapter_id]
                self._save_history()
                
                self._logger.info(f"删除章节向量成功: {chapter_id}")
            
            return success
        
        except Exception as e:
            self._logger.error(f"删除章节向量失败: {chapter_id}, 错误: {e}")
            return False
    
    def get_stats(self) -> EncodingStats:
        """
        获取编码统计
        
        Returns:
            EncodingStats: 编码统计信息
        """
        with self._stats_lock:
            return self._stats.model_copy()
    
    def clear_stats(self):
        """清空统计信息"""
        with self._stats_lock:
            self._stats = EncodingStats()
    
    def clear_history(self):
        """清空历史记录"""
        with self._history_lock:
            self._encoding_history = {}
        
        # 删除历史文件
        if self._history_file.exists():
            try:
                self._history_file.unlink()
            except Exception as e:
                self._logger.error(f"删除历史文件失败: {e}")


# ============================================================================
# 单例模式
# ============================================================================


_chapter_encoder_instance: Optional[ChapterEncoder] = None
_chapter_encoder_lock = threading.RLock()


def get_chapter_encoder(
    workspace_root: Optional[Path] = None,
    **kwargs
) -> ChapterEncoder:
    """
    获取章节编码器单例
    
    Args:
        workspace_root: 工作区根目录
        **kwargs: 其他参数（传递给ChapterEncoder）
    
    Returns:
        ChapterEncoder实例
    """
    global _chapter_encoder_instance
    
    if _chapter_encoder_instance is None:
        with _chapter_encoder_lock:
            if _chapter_encoder_instance is None:
                _chapter_encoder_instance = ChapterEncoder(
                    workspace_root=workspace_root,
                    **kwargs
                )
    
    return _chapter_encoder_instance


def reset_chapter_encoder():
    """重置章节编码器单例（测试用）"""
    global _chapter_encoder_instance
    
    with _chapter_encoder_lock:
        _chapter_encoder_instance = None


# ============================================================================
# 便捷导出
# ============================================================================


__all__ = [
    "ChapterEncoder",
    "ChapterEncodingResult",
    "BatchEncodingResult",
    "EncodingStats",
    "get_chapter_encoder",
    "reset_chapter_encoder",
]
