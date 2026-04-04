"""
向量存储模块 - OpenClaw L2温记忆

V1.0版本
创建日期：2026-03-25

特性：
- 集成LanceDB向量数据库（嵌入式、零配置）
- 支持OpenAI Embedding API（text-embedding-3-small）
- 支持本地模型（all-MiniLM-L6-v2）
- 章节向量存储（长篇连贯性召回）
- 知识库向量存储（分类知识库+通用知识库）
- 风格向量存储（经典文学作品风格）
- 余弦相似度检索（top-k召回）
- 增量更新（新章节追加）

设计参考：
- OpenClaw mem9 L2温记忆架构
- 升级方案10.1
- ADR-001: LanceDB作为向量数据库

使用示例：
    # 创建向量存储实例
    vector_store = NovelVectorStore(db_path="data/vector_store")
    
    # 添加章节向量
    vector_store.add_chapter(
        chapter_id="chapter-001",
        content="第一章的内容...",
        metadata={"title": "开篇", "word_count": 3000}
    )
    
    # 召回相似上下文
    results = vector_store.recall_similar_context(
        query="星际飞船穿越虫洞",
        top_k=10
    )
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, ConfigDict

# 初始化logger
logger = logging.getLogger(__name__)

# 延迟导入LanceDB和OpenAI，避免强制依赖
try:
    import lancedb
    from lancedb.pydantic import LanceModel, Vector
    LANCEDB_AVAILABLE = True
except ImportError:
    LANCEDB_AVAILABLE = False
    LanceModel = BaseModel  # 类型占位符

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# ============================================================================
# Pydantic数据模型
# ============================================================================


class ChapterVector(LanceModel if LANCEDB_AVAILABLE else BaseModel):
    """章节向量模型"""
    
    model_config = ConfigDict(frozen=False)
    
    chapter_id: str = Field(description="章节ID（如chapter-001）")
    content: str = Field(description="章节文本内容")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据（标题、字数等）")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="更新时间")
    
    # 向量字段（动态维度，由embedding模型决定）
    # 注意：LanceModel会自动处理vector字段


class KnowledgeVector(LanceModel if LANCEDB_AVAILABLE else BaseModel):
    """知识库向量模型"""
    
    model_config = ConfigDict(frozen=False)
    
    knowledge_id: str = Field(description="知识点ID（如scifi-physics-001）")
    category: str = Field(description="分类（科幻/玄幻/历史）")
    domain: str = Field(description="领域（物理/化学/生物/宗教/神话）")
    title: str = Field(description="知识点标题")
    content: str = Field(description="知识点详细内容")
    keywords: List[str] = Field(default_factory=list, description="关键词列表")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据（引用、来源等）")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="更新时间")


class StyleVector(LanceModel if LANCEDB_AVAILABLE else BaseModel):
    """风格向量模型"""
    
    model_config = ConfigDict(frozen=False)
    
    style_id: str = Field(description="风格ID（如style-chinese-modern）")
    author: str = Field(description="作者/风格流派")
    content: str = Field(description="风格样本文本")
    style_features: Dict[str, Any] = Field(default_factory=dict, description="风格特征（句子长度、修辞手法等）")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="更新时间")


class VectorSearchResult(BaseModel):
    """向量检索结果"""
    
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(description="ID（chapter_id/knowledge_id/style_id）")
    content: str = Field(description="文本内容")
    score: float = Field(description="相似度分数（0-1）")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


# ============================================================================
# Embedding函数封装
# ============================================================================


class EmbeddingFunction:
    """Embedding函数封装 - 支持OpenAI、DeepSeek和本地模型
    
    V1.2版本更新（2026-03-28）：
    - 新增DeepSeek Embedding支持（调用OpenAI兼容API）
    - 支持3种模型类型：openai、deepseek、local
    - DeepSeek使用OpenAI兼容接口（base_url: https://api.deepseek.com）
    """
    
    def __init__(
        self,
        model_type: str = "openai",  # "openai"、"deepseek" 或 "local"
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        初始化Embedding函数（延迟加载模式）
        
        Args:
            model_type: 模型类型（"openai"、"deepseek" 或 "local"）
            model_name: 模型名称
                - OpenAI: "text-embedding-3-small"（默认）、"text-embedding-3-large"
                - DeepSeek: 暂不支持独立的embedding模型，使用本地模型
                - Local: "all-MiniLM-L6-v2"（默认）
            api_key: API密钥（OpenAI/DeepSeek需要）
            base_url: API基础URL（OpenAI/DeepSeek需要）
                - OpenAI: https://api.openai.com/v1
                - DeepSeek: https://api.deepseek.com
        """
        # DeepSeek暂不支持embedding，降级到local
        if model_type == "deepseek":
            logger.warning("[EmbeddingFunction] DeepSeek暂不支持embedding，降级到local模型")
            model_type = "local"
        
        self.model_type = model_type
        self.model_name = model_name or (
            "text-embedding-3-small" if model_type == "openai" else "all-MiniLM-L6-v2"
        )
        
        # 延迟加载相关属性
        self.client = None
        self.local_model = None
        self._model_loaded = False
        self._loading = False
        self._lock = threading.Lock()
        
        # 保存配置，延迟初始化
        self._api_key = api_key
        self._base_url = base_url
        
        # 不在初始化时加载模型！
        logger.info(f"[EmbeddingFunction] 延迟加载模式，模型将在首次使用时加载: {self.model_name}")
    
    def _ensure_model_loaded(self):
        """延迟加载模型（首次调用时才加载）"""
        if self._model_loaded:
            return
        
        with self._lock:
            if self._model_loaded:
                return
            
            if self._loading:
                # 等待其他线程加载完成
                while self._loading:
                    import time
                    time.sleep(0.1)
                return
            
            self._loading = True
            try:
                logger.info(f"[EmbeddingFunction] 开始加载模型: {self.model_name}")
                
                if self.model_type == "openai":
                    self._init_openai_client()
                else:
                    self._init_local_model()
                
                self._model_loaded = True
                logger.info(f"[EmbeddingFunction] 模型加载完成: {self.model_name}")
            except Exception as e:
                logger.error(f"[EmbeddingFunction] 模型加载失败: {e}")
                raise
            finally:
                self._loading = False
    
    def _init_openai_client(self):
        """初始化OpenAI/DeepSeek客户端（OpenAI兼容接口）"""
        if not OPENAI_AVAILABLE:
            # 自动降级到本地模型
            logger.warning("OpenAI库未安装，自动降级到本地模型")
            self.model_type = "local"
            self.model_name = "all-MiniLM-L6-v2"
            self._init_local_model()
            return
        
        # 从环境变量或参数获取API密钥
        import os
        self._api_key = self._api_key or os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        self._base_url = self._base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL")
        
        if not self._api_key:
            # 自动降级到本地模型
            logger.warning("API密钥未配置，自动降级到本地模型（all-MiniLM-L6-v2）")
            self.model_type = "local"
            self.model_name = "all-MiniLM-L6-v2"
            self._init_local_model()
            return
        
        self.client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url
        )
        self.api_key = self._api_key
        self.base_url = self._base_url
        logger.info(f"[EmbeddingFunction] OpenAI兼容客户端初始化成功: {self._base_url or 'https://api.openai.com/v1'}")
    
    def _init_local_model(self):
        """初始化本地模型（离线模式已在gui_main.py入口设置）
        
        V1.2版本更新（2026-04-04）：
        - 模型缓存目录迁移到项目内部：sentence_transformers_cache
        - 离线模式环境变量已在程序入口（gui_main.py）设置
        - 此处仅做安全检查和模型加载
        - 避免重复设置导致日志混乱
        """
        try:
            import os
            from sentence_transformers import SentenceTransformer
            from pathlib import Path
            
            # 设置模型缓存目录到项目内部
            project_root = Path(__file__).parent.parent
            cache_dir = project_root / "sentence_transformers_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(cache_dir)
            
            logger.info(f"[VectorStore] 本地模型缓存目录: {cache_dir}")
            
            # 【重要】检查离线模式状态（已在gui_main.py入口设置）
            hf_offline = os.environ.get("HF_HUB_OFFLINE", "未设置")
            transformers_offline = os.environ.get("TRANSFORMERS_OFFLINE", "未设置")
            
            if hf_offline != "1":
                # 安全起见，如果入口未设置，在此处补充
                os.environ["HF_HUB_OFFLINE"] = "1"
                logger.warning("[VectorStore] HF_HUB_OFFLINE未在入口设置，已在此处补充")
            
            logger.info(f"[VectorStore] 离线模式状态: HF_HUB_OFFLINE={hf_offline}, TRANSFORMERS_OFFLINE={transformers_offline}")
            logger.info(f"[VectorStore] 离线模式已启用，使用本地缓存（不联网验证）")
            
            # 使用HuggingFace国内镜像（仅在首次下载时生效）
            # 镜像站：https://hf-mirror.com
            original_hf_url = os.environ.get("HF_ENDPOINT", "")
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
            logger.info(f"[VectorStore] HuggingFace镜像: https://hf-mirror.com")
            
            # 临时禁用系统代理：若代理未运行（WinError 10061），huggingface_hub 会
            # 将 httpx 客户端关闭并抛出 "Cannot send a request, as the client has been closed"
            proxy_vars = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")
            saved_proxies = {k: os.environ.pop(k, None) for k in proxy_vars}
            
            try:
                self.local_model = SentenceTransformer(self.model_name, cache_folder=cache_dir)
                logger.info(f"[VectorStore] 本地模型加载成功: {self.model_name}")
            except Exception as e:
                # 如果离线模式加载失败（本地缓存不完整），尝试在线下载
                logger.warning(f"[VectorStore] 离线加载失败，尝试在线下载: {e}")
                os.environ.pop("HF_HUB_OFFLINE", None)  # 移除离线模式
                
                # 恢复代理环境变量（在线下载可能需要）
                for k, v in saved_proxies.items():
                    if v is not None:
                        os.environ[k] = v
                
                # 再次尝试加载（在线模式）
                self.local_model = SentenceTransformer(self.model_name, cache_folder=cache_dir)
                logger.info(f"[VectorStore] 本地模型在线下载成功: {self.model_name}")
            finally:
                # 恢复原始设置
                if original_hf_url:
                    os.environ["HF_ENDPOINT"] = original_hf_url
                else:
                    os.environ.pop("HF_ENDPOINT", None)
                # 恢复代理环境变量
                for k, v in saved_proxies.items():
                    if v is not None:
                        os.environ[k] = v
                    
        except ImportError:
            raise ImportError("sentence-transformers库未安装，请运行: pip install sentence-transformers")
    
    def embed(self, text: str) -> List[float]:
        """
        生成文本的Embedding向量（延迟加载模型）
        
        Args:
            text: 输入文本
            
        Returns:
            向量列表（维度由模型决定）
        """
        # 延迟加载模型
        self._ensure_model_loaded()
        
        if self.model_type == "openai":
            # OpenAI Embedding API
            response = self.client.embeddings.create(
                model=self.model_name,
                input=text
            )
            return response.data[0].embedding
        else:
            # 本地模型
            import numpy as np
            embedding = self.local_model.encode(text)
            return embedding.tolist()
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量生成Embedding向量（延迟加载模型）
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表的列表
        """
        # 延迟加载模型
        self._ensure_model_loaded()
        
        if self.model_type == "openai":
            # OpenAI Embedding API
            response = self.client.embeddings.create(
                model=self.model_name,
                input=texts
            )
            return [item.embedding for item in response.data]
        else:
            # 本地模型
            import numpy as np
            embeddings = self.local_model.encode(texts)
            return embeddings.tolist()
    
    def get_dimension(self) -> int:
        """
        获取向量维度（延迟加载模型）
        
        Returns:
            向量维度
        """
        if self.model_type == "openai":
            # OpenAI text-embedding-3-small: 1536维
            # OpenAI text-embedding-3-large: 3072维
            return 1536 if "small" in self.model_name else 3072
        else:
            # 本地模型维度（需要加载模型才能获取）
            self._ensure_model_loaded()
            return self.local_model.get_sentence_embedding_dimension()
    
    def is_model_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._model_loaded


# ============================================================================
# 向量存储管理器
# ============================================================================


class NovelVectorStore:
    """
    小说向量存储 - 实现OpenClaw L2温记忆
    
    功能：
    - 章节向量存储（长篇连贯性召回）
    - 知识库向量存储（分类知识库+通用知识库）
    - 风格向量存储（经典文学作品风格）
    - 向量检索（余弦相似度）
    """
    
    def __init__(
        self,
        db_path: str = "data/vector_store",
        embedding_type: str = "openai",
        embedding_model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        初始化向量存储（延迟加载模型）
        
        V1.1版本更新（2026-03-28）：
        - 模型延迟加载，启动时不再阻塞
        - 向量维度在首次使用时获取
        
        Args:
            db_path: 数据库路径
            embedding_type: Embedding类型（"openai" 或 "local"）
            embedding_model: Embedding模型名称
            api_key: OpenAI API密钥（仅OpenAI需要）
            base_url: OpenAI API基础URL（仅OpenAI需要）
        """
        if not LANCEDB_AVAILABLE:
            raise ImportError("LanceDB库未安装，请运行: pip install lancedb")
        
        # 数据库路径
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # 连接LanceDB
        self.db = lancedb.connect(str(self.db_path))
        
        # Embedding函数（延迟加载）
        self.embed_func = EmbeddingFunction(
            model_type=embedding_type,
            model_name=embedding_model,
            api_key=api_key,
            base_url=base_url
        )
        
        # 向量维度（延迟获取，首次使用时才调用get_dimension）
        self._vector_dim = None
        
        # 线程安全锁
        self._lock = threading.RLock()
        
        # 初始化表（延迟创建，首次使用时创建）
        self._chapters_table = None
        self._knowledge_table = None
        self._styles_table = None
    
    @property
    def vector_dim(self) -> int:
        """获取向量维度（延迟加载）"""
        if self._vector_dim is None:
            self._vector_dim = self.embed_func.get_dimension()
        return self._vector_dim
    
    # ========================================================================
    # 章节向量管理
    # ========================================================================
    
    def _get_chapters_table(self):
        """获取章节表（延迟创建）"""
        if self._chapters_table is None:
            with self._lock:
                if "chapters" not in self.db.table_names():
                    # 创建表（使用空表初始化）
                    # 注意：LanceDB需要至少一条数据才能创建表
                    # 所以我们延迟到第一次添加数据时创建
                    pass
                else:
                    self._chapters_table = self.db.open_table("chapters")
        
        return self._chapters_table
    
    def add_chapter(
        self,
        chapter_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        添加章节向量
        
        Args:
            chapter_id: 章节ID
            content: 章节内容
            metadata: 元数据（标题、字数等）
            
        Returns:
            是否成功
        """
        with self._lock:
            try:
                # 生成Embedding
                vector = self.embed_func.embed(content)
                
                # 准备数据
                data = [{
                    "chapter_id": chapter_id,
                    "content": content,
                    "vector": vector,
                    "metadata": metadata or {},
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }]
                
                # 检查表是否存在
                if "chapters" not in self.db.table_names():
                    # 创建表
                    self.db.create_table("chapters", data=data)
                    self._chapters_table = self.db.open_table("chapters")
                else:
                    # 添加数据
                    table = self.db.open_table("chapters")
                    
                    # 检查是否已存在
                    existing = table.search().where(f"chapter_id = '{chapter_id}'").to_pandas()
                    if len(existing) > 0:
                        # 更新现有记录
                        # 注意：LanceDB不支持直接更新，需要删除+添加
                        table.delete(f"chapter_id = '{chapter_id}'")
                    
                    table.add(data)
                
                return True
            except Exception as e:
                print(f"添加章节向量失败: {e}")
                return False
    
    def add_chapters_batch(
        self,
        chapters: List[Dict[str, Any]]
    ) -> int:
        """
        批量添加章节向量
        
        Args:
            chapters: 章节列表，每个元素包含chapter_id、content、metadata
            
        Returns:
            成功添加的数量
        """
        with self._lock:
            try:
                # 批量生成Embedding
                contents = [ch["content"] for ch in chapters]
                vectors = self.embed_func.embed_batch(contents)
                
                # 准备数据
                data = []
                for i, ch in enumerate(chapters):
                    data.append({
                        "chapter_id": ch["chapter_id"],
                        "content": ch["content"],
                        "vector": vectors[i],
                        "metadata": ch.get("metadata", {}),
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat()
                    })
                
                # 创建或添加到表
                if "chapters" not in self.db.table_names():
                    self.db.create_table("chapters", data=data)
                    self._chapters_table = self.db.open_table("chapters")
                else:
                    table = self.db.open_table("chapters")
                    table.add(data)
                
                return len(data)
            except Exception as e:
                print(f"批量添加章节向量失败: {e}")
                return 0
    
    def recall_similar_chapters(
        self,
        query: str,
        top_k: int = 10
    ) -> List[VectorSearchResult]:
        """
        召回相似章节（用于长篇连贯性）
        
        Args:
            query: 查询文本（如新章节大纲）
            top_k: 返回数量
            
        Returns:
            相似章节列表
        """
        with self._lock:
            try:
                # 检查表是否存在
                if "chapters" not in self.db.table_names():
                    return []
                
                table = self.db.open_table("chapters")
                
                # 向量检索
                results = table.search(query).limit(top_k).to_pandas()
                
                # 转换为结果对象
                search_results = []
                for _, row in results.iterrows():
                    search_results.append(VectorSearchResult(
                        id=row["chapter_id"],
                        content=row["content"],
                        score=row["_distance"],  # LanceDB返回的是距离，越小越相似
                        metadata=row.get("metadata", {})
                    ))
                
                return search_results
            except Exception as e:
                print(f"召回相似章节失败: {e}")
                return []
    
    # ========================================================================
    # 知识库向量管理
    # ========================================================================
    
    def add_knowledge(
        self,
        knowledge_id: str,
        category: str,
        domain: str,
        title: str,
        content: str,
        keywords: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        添加知识向量
        
        Args:
            knowledge_id: 知识点ID
            category: 分类（科幻/玄幻/历史）
            domain: 领域（物理/化学/生物/宗教/神话）
            title: 标题
            content: 内容
            keywords: 关键词列表
            metadata: 元数据
            
        Returns:
            是否成功
        """
        with self._lock:
            try:
                # 生成Embedding
                vector = self.embed_func.embed(content)
                
                # 准备数据
                data = [{
                    "knowledge_id": knowledge_id,
                    "category": category,
                    "domain": domain,
                    "title": title,
                    "content": content,
                    "vector": vector,
                    "keywords": keywords or [],
                    "metadata": metadata or {},
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }]
                
                # 创建或添加到表
                if "knowledge" not in self.db.table_names():
                    self.db.create_table("knowledge", data=data)
                    self._knowledge_table = self.db.open_table("knowledge")
                else:
                    table = self.db.open_table("knowledge")
                    
                    # 检查是否已存在
                    existing = table.search().where(f"knowledge_id = '{knowledge_id}'").to_pandas()
                    if len(existing) > 0:
                        table.delete(f"knowledge_id = '{knowledge_id}'")
                    
                    table.add(data)
                
                return True
            except Exception as e:
                print(f"添加知识向量失败: {e}")
                return False
    
    def recall_knowledge(
        self,
        query: str,
        category: Optional[str] = None,
        domain: Optional[str] = None,
        top_k: int = 10
    ) -> List[VectorSearchResult]:
        """
        召回相关知识（用于评分反馈）
        
        Args:
            query: 查询文本
            category: 分类过滤（可选）
            domain: 领域过滤（可选）
            top_k: 返回数量
            
        Returns:
            相关知识列表
        """
        with self._lock:
            try:
                # 检查表是否存在
                if "knowledge" not in self.db.table_names():
                    return []
                
                table = self.db.open_table("knowledge")
                
                # 向量检索
                search = table.search(query).limit(top_k)
                
                # 添加过滤条件
                if category:
                    search = search.where(f"category = '{category}'")
                if domain:
                    search = search.where(f"domain = '{domain}'")
                
                results = search.to_pandas()
                
                # 转换为结果对象
                search_results = []
                for _, row in results.iterrows():
                    search_results.append(VectorSearchResult(
                        id=row["knowledge_id"],
                        content=row["content"],
                        score=row["_distance"],
                        metadata={
                            "category": row["category"],
                            "domain": row["domain"],
                            "title": row["title"],
                            "keywords": row.get("keywords", []),
                            **row.get("metadata", {})
                        }
                    ))
                
                return search_results
            except Exception as e:
                print(f"召回知识失败: {e}")
                return []
    
    # ========================================================================
    # 风格向量管理
    # ========================================================================
    
    def add_style(
        self,
        style_id: str,
        author: str,
        content: str,
        style_features: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        添加风格向量
        
        Args:
            style_id: 风格ID
            author: 作者/风格流派
            content: 风格样本文本
            style_features: 风格特征
            metadata: 元数据
            
        Returns:
            是否成功
        """
        with self._lock:
            try:
                # 生成Embedding
                vector = self.embed_func.embed(content)
                
                # 准备数据
                data = [{
                    "style_id": style_id,
                    "author": author,
                    "content": content,
                    "vector": vector,
                    "style_features": style_features or {},
                    "metadata": metadata or {},
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }]
                
                # 创建或添加到表
                if "styles" not in self.db.table_names():
                    self.db.create_table("styles", data=data)
                    self._styles_table = self.db.open_table("styles")
                else:
                    table = self.db.open_table("styles")
                    
                    # 检查是否已存在
                    existing = table.search().where(f"style_id = '{style_id}'").to_pandas()
                    if len(existing) > 0:
                        table.delete(f"style_id = '{style_id}'")
                    
                    table.add(data)
                
                return True
            except Exception as e:
                print(f"添加风格向量失败: {e}")
                return False
    
    def recall_similar_styles(
        self,
        query: str,
        top_k: int = 5
    ) -> List[VectorSearchResult]:
        """
        召回相似风格（用于风格学习）
        
        Args:
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            相似风格列表
        """
        with self._lock:
            try:
                # 检查表是否存在
                if "styles" not in self.db.table_names():
                    return []
                
                table = self.db.open_table("styles")
                
                # 向量检索
                results = table.search(query).limit(top_k).to_pandas()
                
                # 转换为结果对象
                search_results = []
                for _, row in results.iterrows():
                    search_results.append(VectorSearchResult(
                        id=row["style_id"],
                        content=row["content"],
                        score=row["_distance"],
                        metadata={
                            "author": row["author"],
                            "style_features": row.get("style_features", {}),
                            **row.get("metadata", {})
                        }
                    ))
                
                return search_results
            except Exception as e:
                print(f"召回相似风格失败: {e}")
                return []
    
    # ========================================================================
    # 统计和管理
    # ========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取向量存储统计信息
        
        Returns:
            统计信息字典
        """
        stats = {
            "db_path": str(self.db_path),
            "vector_dim": self.vector_dim,
            "tables": {}
        }
        
        with self._lock:
            for table_name in self.db.table_names():
                try:
                    table = self.db.open_table(table_name)
                    # LanceDB 不同版本的API差异处理
                    try:
                        # 尝试新版本API
                        table_len = len(table)
                        # 尝试获取物理大小
                        try:
                            size_mb = table.size() / (1024 * 1024)
                        except AttributeError:
                            # size()方法不存在，使用文件系统统计
                            table_path = self.db_path / f"{table_name}.lance"
                            if table_path.exists():
                                import os
                                total_size = sum(
                                    os.path.getsize(f) 
                                    for f in table_path.rglob("*") 
                                    if f.is_file()
                                )
                                size_mb = total_size / (1024 * 1024)
                            else:
                                size_mb = 0
                    except Exception:
                        table_len = 0
                        size_mb = 0
                    
                    stats["tables"][table_name] = {
                        "count": table_len,
                        "size_mb": size_mb
                    }
                except Exception as e:
                    logger.warning(f"获取表 {table_name} 统计信息失败: {e}")
                    stats["tables"][table_name] = {
                        "count": 0,
                        "size_mb": 0
                    }
        
        return stats
    
    def clear_table(self, table_name: str) -> bool:
        """
        清空表
        
        Args:
            table_name: 表名（chapters/knowledge/styles）
            
        Returns:
            是否成功
        """
        with self._lock:
            try:
                if table_name in self.db.table_names():
                    self.db.drop_table(table_name)
                
                return True
            except Exception as e:
                print(f"清空表失败: {e}")
                return False


# ============================================================================
# 单例工厂模式
# ============================================================================


_vector_store_instance: Optional[NovelVectorStore] = None
_vector_store_lock = threading.Lock()


def get_vector_store(
    db_path: Optional[str] = None,
    embedding_type: str = "openai",
    embedding_model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    force_new: bool = False,
    config_path: Optional[str] = None
) -> NovelVectorStore:
    """
    获取向量存储单例实例
    
    Args:
        db_path: 数据库路径
        embedding_type: Embedding类型（"openai"、"deepseek" 或 "local"）
        embedding_model: Embedding模型名称
        api_key: API密钥（OpenAI/DeepSeek）
        base_url: API基础URL（OpenAI/DeepSeek）
        force_new: 是否强制创建新实例
        config_path: 配置文件路径（默认从config.yaml读取）
        
    Returns:
        NovelVectorStore实例
        
    V1.2版本更新（2026-03-28）：
    - 支持从config.yaml自动读取embedding配置
    - 支持DeepSeek embedding配置
    - 自动读取config.yaml中的memory.embedding_model字段
    """
    global _vector_store_instance
    
    with _vector_store_lock:
        if _vector_store_instance is None or force_new:
            # 从config.yaml读取配置
            if config_path or (embedding_type == "openai" and api_key is None):
                try:
                    import yaml
                    from pathlib import Path
                    
                    # 默认配置文件路径
                    if config_path is None:
                        workspace = Path.cwd()
                        config_path = str(workspace / "config.yaml")
                    
                    # 读取配置
                    if Path(config_path).exists():
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config = yaml.safe_load(f)
                        
                        # 读取记忆配置
                        memory_config = config.get("memory", {})
                        config_embedding_model = memory_config.get("embedding_model", "local")
                        
                        # 解析embedding_model配置
                        if config_embedding_model in ["deepseek", "openai"]:
                            embedding_type = config_embedding_model
                            # 读取API配置
                            api_key = api_key or config.get("api_key")
                            base_url = base_url or config.get("base_url")
                            
                            # DeepSeek特殊处理
                            if config_embedding_model == "deepseek":
                                base_url = base_url or "https://api.deepseek.com"
                                logger.info(f"[VectorStore] 使用DeepSeek Embedding配置")
                            else:
                                logger.info(f"[VectorStore] 使用OpenAI Embedding配置")
                        else:
                            # local模式
                            embedding_type = "local"
                            logger.info(f"[VectorStore] 使用本地Embedding模型")
                except Exception as e:
                    logger.warning(f"[VectorStore] 读取配置文件失败，使用默认配置: {e}")
            
            # 默认路径
            if db_path is None:
                from pathlib import Path
                workspace = Path.cwd()
                db_path = str(workspace / "data" / "vector_store")
            
            _vector_store_instance = NovelVectorStore(
                db_path=db_path,
                embedding_type=embedding_type,
                embedding_model=embedding_model,
                api_key=api_key,
                base_url=base_url
            )
        
        return _vector_store_instance


def reset_vector_store():
    """重置向量存储单例（用于测试）"""
    global _vector_store_instance
    
    with _vector_store_lock:
        _vector_store_instance = None
