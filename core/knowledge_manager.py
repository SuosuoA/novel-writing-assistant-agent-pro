"""
知识库CRUD管理模块 - OpenClaw 文件即真相

V1.0版本
创建日期：2026-03-25

特性：
- 知识点CRUD接口（创建/读取/更新/删除）
- 批量导入JSON文件
- 自动生成向量嵌入（集成LanceDB）
- 分类知识库支持（科幻/玄幻/历史/通用）
- JSON Schema验证
- 文件即真相源（Markdown格式持久化）
- EventBus事件发布

设计参考：
- OpenClaw mem9 文件即真相原则
- 升级方案 10.升级方案✅️.md
- 知识库Schema 10.6 知识库Schema设计✅️.md
- ADR-003: 知识库双层设计

使用示例：
    # 创建知识库管理器
    manager = KnowledgeManager(workspace_root=Path("E:/project"))
    
    # 创建知识点
    knowledge = manager.create_knowledge(
        category="scifi",
        domain="physics",
        title="时间膨胀效应",
        content="根据狭义相对论...",
        keywords=["相对论", "时间", "光速"]
    )
    
    # 批量导入
    result = manager.import_from_json("knowledge/scifi_physics.json")
    
    # 检索知识点
    results = manager.search_knowledge("时间膨胀", category="scifi", top_k=10)
"""

import json
import threading
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field, asdict

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ============================================================================
# Pydantic数据模型
# ============================================================================


class KnowledgePoint(BaseModel):
    """知识点数据模型 - 符合Schema定义"""
    
    model_config = ConfigDict(frozen=False)
    
    knowledge_id: str = Field(description="知识点唯一标识")
    category: str = Field(description="分类（xuanhuan/xianxia/urban/romance/history/scifi/suspense/military/wuxia/game/fantasy/lingyi/tongren/general/writing_technique/philosophy）")
    domain: str = Field(description="知识领域（physics/chemistry/religion等，写作技巧固定为narrative/description/rhetoric/structure）")
    title: str = Field(description="知识点标题")
    content: str = Field(description="知识点详细内容")
    keywords: List[str] = Field(default_factory=list, description="关键词列表")
    embedding: Optional[List[float]] = Field(default=None, description="向量嵌入")
    
    # 扩展字段 - 高质量知识详情
    explanation: Optional[str] = Field(default=None, description="核心概念解释")
    classic_cases: Optional[str] = Field(default=None, description="经典案例应用")
    examples: Optional[List[str]] = Field(default=None, description="示例列表")
    common_mistakes: Optional[Union[List[str], str]] = Field(default=None, description="常见写作误区")
    
    @field_validator("common_mistakes", mode="before")
    @classmethod
    def normalize_common_mistakes(cls, v):
        """
        将common_mistakes转换为字符串列表
        支持三种格式：
        1. 字符串 -> ["字符串"]
        2. 字符串列表 -> 保持不变
        3. 对象列表 [{"mistake": "...", "explanation": "..."}] -> ["mistake: explanation", ...]
        """
        if isinstance(v, str):
            return [v]
        
        if isinstance(v, list):
            # 检查是否为对象列表（包含mistake字段）
            if v and isinstance(v[0], dict) and "mistake" in v[0]:
                # 转换对象列表为字符串列表
                result = []
                for item in v:
                    mistake = item.get("mistake", "")
                    explanation = item.get("explanation", "")
                    if mistake and explanation:
                        result.append(f"{mistake}: {explanation}")
                    elif mistake:
                        result.append(mistake)
                return result
            # 已经是字符串列表，直接返回
            return v
        
        return v
    
    references: Optional[Union[List[str], str]] = Field(default=None, description="参考来源")
    
    @field_validator("references", mode="before")
    @classmethod
    def normalize_references(cls, v):
        """
        将references转换为字符串列表
        支持三种格式：
        1. 字符串 -> ["字符串"]
        2. 字符串列表 -> 保持不变
        3. 对象列表 [{"title": "...", "author": "...", ...}] -> ["《title》作者 (year)", ...]
        """
        if isinstance(v, str):
            return [v]
        
        if isinstance(v, list):
            # 检查是否为对象列表（包含title字段）
            if v and isinstance(v[0], dict) and "title" in v[0]:
                # 转换对象列表为字符串列表
                result = []
                for item in v:
                    title = item.get("title", "")
                    author = item.get("author", "")
                    year = item.get("year", "")
                    description = item.get("description", "")
                    
                    # 格式: 《title》作者 (year): description
                    ref_str = ""
                    if title:
                        ref_str = f"《{title}》"
                    if author:
                        ref_str += f" {author}"
                    if year:
                        ref_str += f" ({year})"
                    if description:
                        ref_str += f": {description}"
                    
                    if ref_str:
                        result.append(ref_str.strip())
                return result
            # 已经是字符串列表，直接返回
            return v
        
        return v
    
    difficulty: Optional[str] = Field(default="intermediate", description="知识难度")
    tags: Optional[List[str]] = Field(default=None, description="自定义标签")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="更新时间")
    
    @field_validator("knowledge_id")
    @classmethod
    def validate_knowledge_id(cls, v: str) -> str:
        """验证知识点ID格式：{category}-{domain}-{序号}"""
        # V5.3修复：支持category中的下划线（如writing_technique）
        pattern = r"^[a-z0-9_]+-[a-z0-9_]+-[0-9]{3,}$"
        if not re.match(pattern, v):
            raise ValueError(f"知识点ID格式错误: {v}，应为 {{category}}-{{domain}}-{{序号}}")
        return v
    
    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        """验证分类 - V1.19.0支持16种小说分类"""
        valid_categories = [
            # 小说类型分类
            "xuanhuan", "xianxia", "urban", "romance", "history",
            "scifi", "suspense", "military", "wuxia", "game",
            "fantasy", "lingyi", "tongren", "general",
            # 特殊分类
            "writing_technique", "philosophy"
        ]
        if v not in valid_categories:
            raise ValueError(f"分类错误: {v}，应为 {valid_categories}")
        return v
    
    @field_validator("domain")
    @classmethod
    def validate_domain_for_writing_technique(cls, v: str, values) -> str:
        """验证写作技巧题材的领域必须是固定值"""
        category = values.data.get("category")
        if category == "writing_technique":
            # V5.3修复：更新为六领域（按12.2文档规范）
            valid_domains = ["narrative", "description", "rhetoric", "structure", "special_sentence", "advanced"]
            if v not in valid_domains:
                raise ValueError(f"写作技巧题材的领域必须为 {valid_domains}，当前为 {v}")
        return v
    
    @field_validator("content")
    @classmethod
    def validate_content_length(cls, v: str) -> str:
        """验证内容长度"""
        if len(v) < 10:
            raise ValueError("知识点内容长度不能少于10字符")
        if len(v) > 5000:
            raise ValueError("知识点内容长度不能超过5000字符")
        return v


class KnowledgeCreateResult(BaseModel):
    """创建知识点结果"""
    
    model_config = ConfigDict(frozen=False)
    
    success: bool = Field(description="是否成功")
    knowledge_id: Optional[str] = Field(default=None, description="知识点ID")
    knowledge: Optional[KnowledgePoint] = Field(default=None, description="知识点对象")
    error: Optional[str] = Field(default=None, description="错误信息")


class KnowledgeSearchResult(BaseModel):
    """检索结果"""
    
    model_config = ConfigDict(frozen=False)
    
    knowledge_id: str = Field(description="知识点ID")
    title: str = Field(description="标题")
    content: str = Field(description="内容")
    category: str = Field(description="分类")
    domain: str = Field(description="领域")
    score: float = Field(default=1.0, description="相似度分数")
    keywords: List[str] = Field(default_factory=list, description="关键词")


class ImportResult(BaseModel):
    """批量导入结果"""
    
    model_config = ConfigDict(frozen=False)
    
    total: int = Field(description="总数")
    success: int = Field(description="成功数")
    failed: int = Field(description="失败数")
    errors: List[Dict[str, str]] = Field(default_factory=list, description="错误列表")
    knowledge_ids: List[str] = Field(default_factory=list, description="成功导入的知识点ID")


# ============================================================================
# 知识库管理器
# ============================================================================


class KnowledgeManager:
    """
    知识库CRUD管理器
    
    功能：
    - 创建/读取/更新/删除知识点
    - 批量导入JSON文件
    - 自动生成向量嵌入
    - 分类知识库管理
    - 文件即真相源（JSON持久化）
    
    存储结构：
    - data/knowledge/{category}/{domain}.json
      例如：data/knowledge/scifi/physics.json
            data/knowledge/xuanhuan/religion.json
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        workspace_root: Path,
        auto_embed: bool = True,
        embedding_model: str = "openai"  # "openai" 或 "local"
    ):
        """
        初始化知识库管理器
        
        Args:
            workspace_root: 工作区根目录
            auto_embed: 是否自动生成向量嵌入
            embedding_model: 嵌入模型类型
        """
        # 避免重复初始化
        if hasattr(self, "_initialized") and self._initialized:
            return
        
        self.workspace_root = Path(workspace_root)
        self.knowledge_dir = self.workspace_root / "data" / "knowledge"  # JSON源文件目录
        self.knowledge_base_dir = self.workspace_root / "data" / "knowledge_base"  # 向量库目录
        self.auto_embed = auto_embed
        self.embedding_model = embedding_model
        
        # 知识库缓存（分类 -> 领域 -> 知识点列表）
        self._cache: Dict[str, Dict[str, List[KnowledgePoint]]] = {}
        
        # 知识点计数器（用于生成ID）
        self._counters: Dict[str, Dict[str, int]] = {}
        
        # Embedding函数
        self._embed_func = None
        
        # EventBus（延迟导入）
        self._event_bus = None
        
        # VectorStore连接（延迟导入）
        self._vector_store = None
        
        # 创建目录结构
        self._ensure_directories()
        
        # 加载现有知识库到缓存
        self._load_all_knowledge()
        
        self._initialized = True
    
    def reload_cache(self):
        """重新加载知识库缓存（用于数据更新后刷新）"""
        self._cache.clear()
        self._counters.clear()
        self._load_all_knowledge()
        logger.info("Knowledge cache reloaded")
    
    def _ensure_directories(self):
        """确保目录结构存在"""
        categories = [
            # 小说类型分类
            "xuanhuan", "xianxia", "urban", "romance", "history",
            "scifi", "suspense", "military", "wuxia", "game",
            "fantasy", "lingyi", "tongren", "general",
            # 特殊分类
            "writing_technique", "philosophy"
        ]
        for category in categories:
            (self.knowledge_dir / category).mkdir(parents=True, exist_ok=True)
    
    def _load_all_knowledge(self):
        """加载所有知识库到缓存"""
        # V1.19.0修复：扩展支持16种小说分类
        categories = [
            # 小说类型分类
            "xuanhuan", "xianxia", "urban", "romance", "history",
            "scifi", "suspense", "military", "wuxia", "game",
            "fantasy", "lingyi", "tongren", "general",
            # 特殊分类
            "writing_technique", "philosophy"
        ]
        
        for category in categories:
            self._cache[category] = {}
            self._counters[category] = {}
            
            category_dir = self.knowledge_dir / category
            if not category_dir.exists():
                continue
            
            for json_file in category_dir.glob("*.json"):
                domain = json_file.stem
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # 支持两种JSON格式：
                    # 1. {"knowledge_points": [...]}
                    # 2. [...] (直接数组)
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        items = data.get("knowledge_points", [])
                    else:
                        items = []
                    
                    knowledge_list = []
                    for item in items:
                        try:
                            kp = KnowledgePoint(**item)
                            knowledge_list.append(kp)
                            
                            # 更新计数器
                            # 从knowledge_id提取序号
                            kid = kp.knowledge_id
                            if "-" in kid:
                                parts = kid.split("-")
                                if len(parts) >= 3:
                                    try:
                                        seq = int(parts[-1])
                                        if domain not in self._counters[category]:
                                            self._counters[category][domain] = 0
                                        self._counters[category][domain] = max(
                                            self._counters[category][domain], seq
                                        )
                                    except ValueError:
                                        pass
                        except Exception:
                            continue
                    
                    self._cache[category][domain] = knowledge_list
                    
                except Exception as e:
                    print(f"[KnowledgeManager] 加载知识库失败: {json_file} - {e}")
    
    def _get_event_bus(self):
        """延迟获取EventBus"""
        if self._event_bus is None:
            try:
                from core import get_event_bus
                self._event_bus = get_event_bus()
            except Exception:
                pass
        return self._event_bus
    
    def _get_embed_func(self):
        """延迟获取Embedding函数"""
        if self._embed_func is None and self.auto_embed:
            try:
                from infrastructure.vector_store import EmbeddingFunction
                self._embed_func = EmbeddingFunction(model_type=self.embedding_model)
            except Exception as e:
                print(f"[KnowledgeManager] 初始化Embedding函数失败: {e}")
                self.auto_embed = False
        return self._embed_func
    
    def _get_vector_store(self):
        """延迟获取VectorStore连接（用于向量检索）"""
        if self._vector_store is None:
            try:
                from infrastructure.vector_store import NovelVectorStore
                db_path = str(self.knowledge_base_dir)
                self._vector_store = NovelVectorStore(db_path=db_path)
            except Exception as e:
                print(f"[KnowledgeManager] 初始化VectorStore失败: {e}")
        return self._vector_store
    
    # ========================================================================
    # CRUD接口
    # ========================================================================
    
    def create_knowledge(
        self,
        category: str,
        domain: str,
        title: str,
        content: str,
        keywords: List[str],
        references: Optional[List[str]] = None,
        difficulty: Optional[str] = "intermediate",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        knowledge_id: Optional[str] = None
    ) -> KnowledgeCreateResult:
        """
        创建知识点
        
        Args:
            category: 分类（xuanhuan/xianxia/urban/romance/history/scifi/suspense/military/wuxia/game/fantasy/lingyi/tongren/general/writing_technique/philosophy）
            domain: 领域（physics/chemistry/religion等）
            title: 标题
            content: 内容
            keywords: 关键词列表
            references: 参考来源
            difficulty: 难度（basic/intermediate/advanced）
            tags: 自定义标签
            metadata: 元数据
            knowledge_id: 自定义知识点ID（可选）
        
        Returns:
            KnowledgeCreateResult: 创建结果
        """
        try:
            # 验证分类（V1.19.0修复：扩展支持16种小说分类）
            valid_categories = [
                # 小说类型分类
                "xuanhuan", "xianxia", "urban", "romance", "history",
                "scifi", "suspense", "military", "wuxia", "game",
                "fantasy", "lingyi", "tongren", "general",
                # 特殊分类
                "writing_technique", "philosophy"
            ]
            if category not in valid_categories:
                return KnowledgeCreateResult(
                    success=False,
                    error=f"无效的分类: {category}，支持的分类: {', '.join(valid_categories)}"
                )
            
            # 验证内容长度
            if len(content) < 50:
                return KnowledgeCreateResult(
                    success=False,
                    error="内容长度不能少于50字符"
                )
            
            # 生成知识点ID
            if knowledge_id is None:
                if domain not in self._counters[category]:
                    self._counters[category][domain] = 0
                self._counters[category][domain] += 1
                knowledge_id = f"{category}-{domain}-{self._counters[category][domain]:03d}"
            
            # 创建知识点对象
            kp = KnowledgePoint(
                knowledge_id=knowledge_id,
                category=category,
                domain=domain,
                title=title,
                content=content,
                keywords=keywords,
                references=references,
                difficulty=difficulty,
                tags=tags,
                metadata=metadata
            )
            
            # 自动生成向量嵌入
            if self.auto_embed:
                embed_func = self._get_embed_func()
                if embed_func:
                    try:
                        embedding = embed_func.embed(content)
                        kp.embedding = embedding
                    except Exception as e:
                        print(f"[KnowledgeManager] 生成向量嵌入失败: {e}")
            
            # 添加到缓存
            if domain not in self._cache[category]:
                self._cache[category][domain] = []
            
            # 检查是否已存在
            existing = self.get_knowledge(knowledge_id)
            if existing:
                return KnowledgeCreateResult(
                    success=False,
                    error=f"知识点已存在: {knowledge_id}"
                )
            
            self._cache[category][domain].append(kp)
            
            # 持久化到JSON文件
            self._save_to_file(category, domain)
            
            # 同步到向量库
            if self.auto_embed and kp.embedding:
                try:
                    vector_store = self._get_vector_store()
                    if vector_store:
                        # NovelVectorStore会自动生成embedding，不需要传入
                        vector_store.add_knowledge(
                            knowledge_id=kp.knowledge_id,
                            category=kp.category,
                            domain=kp.domain,
                            title=kp.title,
                            content=kp.content,
                            keywords=kp.keywords,
                            metadata={"difficulty": kp.difficulty, "tags": kp.tags}
                        )
                        print(f"[KnowledgeManager] 已同步到向量库: {kp.title[:30]}...")
                except Exception as e:
                    print(f"[KnowledgeManager] 同步到向量库失败: {e}")
            
            # 发布事件
            self._publish_event("knowledge.created", kp.model_dump())
            
            return KnowledgeCreateResult(
                success=True,
                knowledge_id=knowledge_id,
                knowledge=kp
            )
            
        except Exception as e:
            return KnowledgeCreateResult(
                success=False,
                error=str(e)
            )
    
    def get_knowledge(self, knowledge_id: str) -> Optional[KnowledgePoint]:
        """
        读取知识点
        
        Args:
            knowledge_id: 知识点ID
        
        Returns:
            KnowledgePoint 或 None
        """
        # 解析ID
        parts = knowledge_id.split("-")
        if len(parts) < 3:
            return None
        
        category = parts[0]
        domain = parts[1]
        
        if category not in self._cache:
            return None
        
        if domain not in self._cache[category]:
            return None
        
        for kp in self._cache[category][domain]:
            if kp.knowledge_id == knowledge_id:
                return kp
        
        return None
    
    def update_knowledge(
        self,
        knowledge_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        references: Optional[List[str]] = None,
        difficulty: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> KnowledgeCreateResult:
        """
        更新知识点
        
        Args:
            knowledge_id: 知识点ID
            title: 新标题
            content: 新内容
            keywords: 新关键词
            references: 新参考来源
            difficulty: 新难度
            tags: 新标签
            metadata: 新元数据
        
        Returns:
            KnowledgeCreateResult: 更新结果
        """
        try:
            kp = self.get_knowledge(knowledge_id)
            if not kp:
                return KnowledgeCreateResult(
                    success=False,
                    error=f"知识点不存在: {knowledge_id}"
                )
            
            # 更新字段
            if title is not None:
                kp.title = title
            if content is not None:
                if len(content) < 50:
                    return KnowledgeCreateResult(
                        success=False,
                        error="内容长度不能少于50字符"
                    )
                kp.content = content
                
                # 重新生成向量嵌入
                if self.auto_embed:
                    embed_func = self._get_embed_func()
                    if embed_func:
                        try:
                            kp.embedding = embed_func.embed(content)
                        except Exception:
                            pass
            if keywords is not None:
                kp.keywords = keywords
            if references is not None:
                kp.references = references
            if difficulty is not None:
                kp.difficulty = difficulty
            if tags is not None:
                kp.tags = tags
            if metadata is not None:
                kp.metadata = metadata
            
            kp.updated_at = datetime.now().isoformat()
            
            # 持久化
            parts = knowledge_id.split("-")
            category = parts[0]
            domain = parts[1]
            self._save_to_file(category, domain)
            
            # 发布事件
            self._publish_event("knowledge.updated", kp.model_dump())
            
            return KnowledgeCreateResult(
                success=True,
                knowledge_id=knowledge_id,
                knowledge=kp
            )
            
        except Exception as e:
            return KnowledgeCreateResult(
                success=False,
                error=str(e)
            )
    
    def sync_vector_store(self) -> Dict[str, int]:
        """
        同步向量库：清理JSON中已删除但向量库中还存在的"幽灵数据"
        
        Returns:
            Dict[str, int]: {"json_count": N, "vector_count": M, "deleted": K}
        """
        result = {"json_count": 0, "vector_count": 0, "deleted": 0}
        
        try:
            # 1. 统计JSON中的知识点ID
            json_ids = set()
            for category, domains in self._cache.items():
                for domain, knowledge_list in domains.items():
                    for kp in knowledge_list:
                        json_ids.add(kp.knowledge_id)
            
            result["json_count"] = len(json_ids)
            
            # 2. 统计向量库中的知识点ID
            vector_store = self._get_vector_store()
            if not vector_store:
                print("[KnowledgeManager] 向量库未初始化")
                return result
            
            if "knowledge" not in vector_store.db.table_names():
                print("[KnowledgeManager] 向量库中无knowledge表")
                return result
            
            table = vector_store.db.open_table("knowledge")
            df = table.to_pandas()
            
            vector_ids = set(df["knowledge_id"].tolist()) if "knowledge_id" in df.columns else set()
            result["vector_count"] = len(vector_ids)
            
            # 3. 找出幽灵数据（向量库有但JSON没有）
            ghost_ids = vector_ids - json_ids
            
            if ghost_ids:
                print(f"[KnowledgeManager] 发现 {len(ghost_ids)} 条幽灵数据，开始清理...")
                
                for ghost_id in ghost_ids:
                    try:
                        table.delete(f"knowledge_id = '{ghost_id}'")
                        print(f"[KnowledgeManager] 删除幽灵数据: {ghost_id}")
                        result["deleted"] += 1
                    except Exception as e:
                        print(f"[KnowledgeManager] 删除失败 {ghost_id}: {e}")
                
                print(f"[KnowledgeManager] 清理完成，删除 {result['deleted']} 条")
            else:
                print("[KnowledgeManager] 向量库与JSON同步，无需清理")
            
        except Exception as e:
            print(f"[KnowledgeManager] 同步向量库失败: {e}")
            import traceback
            traceback.print_exc()
        
        return result
    
    def delete_knowledge(self, knowledge_id: str) -> bool:
        """
        删除知识点（同时删除JSON缓存和向量库）
        
        Args:
            knowledge_id: 知识点ID
        
        Returns:
            bool: 是否成功
        """
        parts = knowledge_id.split("-")
        if len(parts) < 3:
            return False
        
        category = parts[0]
        domain = parts[1]
        
        if category not in self._cache:
            return False
        
        if domain not in self._cache[category]:
            return False
        
        for i, kp in enumerate(self._cache[category][domain]):
            if kp.knowledge_id == knowledge_id:
                # 1. 从缓存删除
                del self._cache[category][domain][i]
                
                # 2. 保存到JSON文件
                self._save_to_file(category, domain)
                
                # 3. 从向量库删除（新增）
                try:
                    vector_store = self._get_vector_store()
                    if vector_store:
                        # LanceDB delete方法
                        if "knowledge" in vector_store.db.table_names():
                            table = vector_store.db.open_table("knowledge")
                            table.delete(f"knowledge_id = '{knowledge_id}'")
                            print(f"[KnowledgeManager] 已从向量库删除: {knowledge_id}")
                except Exception as e:
                    print(f"[KnowledgeManager] 从向量库删除失败: {e}")
                
                # 4. 发布事件
                self._publish_event("knowledge.deleted", {"knowledge_id": knowledge_id})
                
                return True
        
        return False
    
    # ========================================================================
    # 批量导入
    # ========================================================================
    
    def import_from_json(
        self,
        json_path: Union[str, Path],
        category: Optional[str] = None,
        domain: Optional[str] = None
    ) -> ImportResult:
        """
        批量导入JSON文件
        
        Args:
            json_path: JSON文件路径
            category: 覆盖分类（可选）
            domain: 覆盖领域（可选）
        
        Returns:
            ImportResult: 导入结果
        
        JSON格式：
        {
            "category": "scifi",
            "domain": "physics",
            "knowledge_points": [
                {
                    "title": "时间膨胀效应",
                    "content": "...",
                    "keywords": ["相对论", "时间"],
                    ...
                }
            ]
        }
        """
        result = ImportResult(total=0, success=0, failed=0)
        
        try:
            json_path = Path(json_path)
            if not json_path.exists():
                result.errors.append({"file": str(json_path), "error": "文件不存在"})
                return result
            
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 获取分类和领域
            cat = category or data.get("category")
            dom = domain or data.get("domain")
            
            if not cat or not dom:
                result.errors.append({"file": str(json_path), "error": "缺少分类或领域"})
                return result
            
            knowledge_points = data.get("knowledge_points", [])
            result.total = len(knowledge_points)
            
            for idx, item in enumerate(knowledge_points):
                try:
                    # 创建知识点
                    create_result = self.create_knowledge(
                        category=cat,
                        domain=dom,
                        title=item.get("title", f"未命名知识点 {idx}"),
                        content=item.get("content", ""),
                        keywords=item.get("keywords", []),
                        references=item.get("references"),
                        difficulty=item.get("difficulty"),
                        tags=item.get("tags"),
                        metadata=item.get("metadata"),
                        knowledge_id=item.get("knowledge_id")
                    )
                    
                    if create_result.success:
                        result.success += 1
                        result.knowledge_ids.append(create_result.knowledge_id)
                    else:
                        result.failed += 1
                        result.errors.append({
                            "index": idx,
                            "title": item.get("title", "未知"),
                            "error": create_result.error
                        })
                        
                except Exception as e:
                    result.failed += 1
                    result.errors.append({
                        "index": idx,
                        "title": item.get("title", "未知"),
                        "error": str(e)
                    })
            
            return result
            
        except Exception as e:
            result.errors.append({"file": str(json_path), "error": str(e)})
            return result
    
    # ========================================================================
    # 检索接口
    # ========================================================================
    
    def search_knowledge(
        self,
        query: str,
        category: Optional[str] = None,
        domain: Optional[str] = None,
        top_k: int = 10,
        use_vector: bool = True
    ) -> List[KnowledgeSearchResult]:
        """
        检索知识点
        
        Args:
            query: 查询字符串
            category: 限制分类
            domain: 限制领域
            top_k: 返回数量
            use_vector: 是否使用向量检索（默认True）
        
        Returns:
            List[KnowledgeSearchResult]: 检索结果
        """
        # 优先使用向量检索
        if use_vector and self.auto_embed:
            try:
                vector_store = self._get_vector_store()
                if vector_store:
                    # NovelVectorStore会自动生成query embedding，直接传入query字符串
                    vector_results = vector_store.recall_knowledge(
                        query=query,
                        category=category,
                        domain=domain,
                        top_k=top_k
                    )

                    if vector_results:
                        # VectorSearchResult转KnowledgeSearchResult
                        return [
                            KnowledgeSearchResult(
                                knowledge_id=r.knowledge_id,
                                title=r.title,
                                content=r.content,
                                category=r.category,
                                domain=r.domain,
                                score=r.score,
                                keywords=r.keywords if hasattr(r, 'keywords') else []
                            )
                            for r in vector_results
                        ]
            except Exception as e:
                print(f"[KnowledgeManager] 向量检索失败，回退到关键词匹配: {e}")
        
        # 回退到关键词匹配
        results = []
        query_lower = query.lower()
        
        # 确定搜索范围
        categories = [category] if category else list(self._cache.keys())
        
        for cat in categories:
            if cat not in self._cache:
                continue
            
            domains = [domain] if domain else list(self._cache[cat].keys())
            
            for dom in domains:
                if dom not in self._cache[cat]:
                    continue
                
                for kp in self._cache[cat][dom]:
                    score = self._calculate_relevance(query_lower, kp)
                    
                    if score > 0:
                        results.append(KnowledgeSearchResult(
                            knowledge_id=kp.knowledge_id,
                            title=kp.title,
                            content=kp.content[:500] + "..." if len(kp.content) > 500 else kp.content,
                            category=kp.category,
                            domain=kp.domain,
                            score=score,
                            keywords=kp.keywords
                        ))
        
        # 按分数排序
        results.sort(key=lambda x: x.score, reverse=True)
        
        return results[:top_k]
    
    def _calculate_relevance(self, query: str, kp: KnowledgePoint) -> float:
        """
        计算相关性分数
        
        Args:
            query: 查询字符串
            kp: 知识点
        
        Returns:
            float: 相关性分数（0-1）
        """
        score = 0.0
        
        # 标题匹配
        if query in kp.title.lower():
            score += 0.5
        
        # 关键词匹配
        for keyword in kp.keywords:
            if query in keyword.lower():
                score += 0.3
        
        # 内容匹配
        if query in kp.content.lower():
            score += 0.2
        
        return min(score, 1.0)
    
    def search_by_vector(
        self,
        query: str,
        category: Optional[str] = None,
        top_k: int = 10
    ) -> List[KnowledgeSearchResult]:
        """
        向量检索知识点
        
        Args:
            query: 查询字符串
            category: 限制分类
            top_k: 返回数量
        
        Returns:
            List[KnowledgeSearchResult]: 检索结果
        """
        embed_func = self._get_embed_func()
        if not embed_func:
            # 降级为关键词检索
            return self.search_knowledge(query, category=category, top_k=top_k)
        
        try:
            # 生成查询向量
            query_vector = embed_func.embed(query)
            
            results = []
            
            # 确定搜索范围
            categories = [category] if category else list(self._cache.keys())
            
            for cat in categories:
                if cat not in self._cache:
                    continue
                
                for dom, knowledge_list in self._cache[cat].items():
                    for kp in knowledge_list:
                        if kp.embedding is None:
                            continue
                        
                        # 计算余弦相似度
                        similarity = self._cosine_similarity(query_vector, kp.embedding)
                        
                        if similarity > 0.5:  # 阈值
                            results.append(KnowledgeSearchResult(
                                knowledge_id=kp.knowledge_id,
                                title=kp.title,
                                content=kp.content[:500] + "..." if len(kp.content) > 500 else kp.content,
                                category=kp.category,
                                domain=kp.domain,
                                score=similarity,
                                keywords=kp.keywords
                            ))
            
            # 按分数排序
            results.sort(key=lambda x: x.score, reverse=True)
            
            return results[:top_k]
            
        except Exception as e:
            print(f"[KnowledgeManager] 向量检索失败: {e}")
            return self.search_knowledge(query, category=category, top_k=top_k)
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        import math
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    # ========================================================================
    # 统计接口
    # ========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取知识库统计信息（从所有向量表获取）"""
        # 尝试从向量库获取统计
        try:
            vector_store = self._get_vector_store()
            if vector_store:
                import pandas as pd
                
                # 遍历所有表统计
                total = 0
                categories = {}
                
                for table_name in vector_store.db.table_names():
                    try:
                        table = vector_store.db.open_table(table_name)
                        count = table.count_rows()
                        total += count
                        
                        # 获取分类统计
                        df = table.to_pandas()
                        if 'category' in df.columns:
                            cat_counts = df['category'].value_counts().to_dict()
                            for cat, cnt in cat_counts.items():
                                if cat not in categories:
                                    categories[cat] = 0
                                categories[cat] += cnt
                    except Exception as te:
                        print(f"[KnowledgeManager] 读取表 {table_name} 失败: {te}")
                
                return {
                    "total": total,
                    "categories": categories,
                    "source": "vector_store"
                }
        except Exception as e:
            print(f"[KnowledgeManager] 从向量库获取统计失败: {e}")
        
        # 回退到JSON缓存统计
        stats = {
            "total": 0,
            "categories": {},
            "domains": {},
            "source": "json_cache"
        }
        
        for category, domains in self._cache.items():
            cat_count = 0
            stats["categories"][category] = 0
            
            for domain, knowledge_list in domains.items():
                count = len(knowledge_list)
                cat_count += count
                
                if category not in stats["domains"]:
                    stats["domains"][category] = {}
                stats["domains"][category][domain] = count
            
            stats["categories"][category] = cat_count
            stats["total"] += cat_count
        
        return stats
    
    def list_knowledge(
        self,
        category: Optional[str] = None,
        domain: Optional[str] = None
    ) -> List[KnowledgePoint]:
        """列出知识点"""
        if category and domain:
            return self._cache.get(category, {}).get(domain, [])
        elif category:
            result = []
            for dom, knowledge_list in self._cache.get(category, {}).items():
                result.extend(knowledge_list)
            return result
        else:
            result = []
            for cat, domains in self._cache.items():
                for dom, knowledge_list in domains.items():
                    result.extend(knowledge_list)
            return result
    
    # ========================================================================
    # 持久化
    # ========================================================================
    
    def _save_to_file(self, category: str, domain: str):
        """保存到文件"""
        import shutil
        
        knowledge_list = self._cache.get(category, {}).get(domain, [])
        
        file_path = self.knowledge_dir / category / f"{domain}.json"
        
        # 确保父目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "category": category,
            "domain": domain,
            "knowledge_points": [kp.model_dump() for kp in knowledge_list],
            "updated_at": datetime.now().isoformat()
        }
        
        # 原子化写入（Windows兼容）
        temp_path = file_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Windows兼容：先删除目标文件，再重命名
            if file_path.exists():
                file_path.unlink()
            temp_path.rename(file_path)
            
        except Exception as e:
            print(f"[KnowledgeManager] 保存失败: {e}")
            if temp_path.exists():
                temp_path.unlink()
            raise
    
    def _publish_event(self, event_type: str, data: Dict[str, Any]):
        """发布事件"""
        event_bus = self._get_event_bus()
        if event_bus:
            try:
                event_bus.publish(
                    event_type=event_type,
                    data=data,
                    source="KnowledgeManager"
                )
            except Exception:
                pass


# ============================================================================
# 单例访问
# ============================================================================


_knowledge_manager: Optional[KnowledgeManager] = None
_knowledge_manager_lock = threading.RLock()


def get_knowledge_manager(
    workspace_root: Optional[Path] = None,
    auto_embed: bool = True,
    embedding_model: str = "openai"
) -> KnowledgeManager:
    """获取知识库管理器单例"""
    global _knowledge_manager
    
    if _knowledge_manager is None:
        with _knowledge_manager_lock:
            if _knowledge_manager is None:
                if workspace_root is None:
                    # 尝试从环境变量或当前目录推断
                    import os
                    workspace_root = Path(os.getcwd())
                
                _knowledge_manager = KnowledgeManager(
                    workspace_root=workspace_root,
                    auto_embed=auto_embed,
                    embedding_model=embedding_model
                )
    
    return _knowledge_manager


def reset_knowledge_manager():
    """重置知识库管理器（用于测试）"""
    global _knowledge_manager
    
    with _knowledge_manager_lock:
        _knowledge_manager = None


# ============================================================================
# 测试代码
# ============================================================================


if __name__ == "__main__":
    import sys
    import io
    
    # 设置 stdout 编码为 UTF-8
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("=" * 60)
    print("Knowledge Manager CRUD Test")
    print("=" * 60)
    
    # 获取工作区根目录
    workspace_root = Path(__file__).parent.parent
    
    # 创建管理器实例（禁用自动嵌入以加速测试）
    manager = KnowledgeManager(workspace_root, auto_embed=False)
    
    # 测试1: 创建知识点
    print("\n[Test 1] Create Knowledge Point...")
    result = manager.create_knowledge(
        category="scifi",
        domain="physics",
        title="测试知识点：时间膨胀",
        content="根据狭义相对论，当物体接近光速运动时，时间流速会变慢。这是一个非常重要的物理学概念，在科幻小说创作中经常被使用。",
        keywords=["相对论", "时间", "光速", "测试"]
    )
    print(f"  Result: success={result.success}, id={result.knowledge_id}")
    
    if result.success:
        # 测试2: 读取知识点
        print("\n[Test 2] Read Knowledge Point...")
        kp = manager.get_knowledge(result.knowledge_id)
        if kp:
            print(f"  Title: {kp.title}")
            print(f"  Content: {kp.content[:50]}...")
        
        # 测试3: 更新知识点
        print("\n[Test 3] Update Knowledge Point...")
        update_result = manager.update_knowledge(
            result.knowledge_id,
            title="测试知识点：时间膨胀效应（已更新）"
        )
        print(f"  Result: success={update_result.success}")
        
        # 测试4: 检索知识点
        print("\n[Test 4] Search Knowledge...")
        search_results = manager.search_knowledge("时间膨胀", top_k=5)
        print(f"  Found: {len(search_results)} results")
        for r in search_results[:3]:
            print(f"    - {r.title} (score: {r.score:.2f})")
        
        # 测试5: 删除知识点
        print("\n[Test 5] Delete Knowledge Point...")
        deleted = manager.delete_knowledge(result.knowledge_id)
        print(f"  Result: deleted={deleted}")
    
    # 测试6: 统计信息
    print("\n[Test 6] Get Statistics...")
    stats = manager.get_stats()
    print(f"  Total: {stats['total']}")
    print(f"  Categories: {stats['categories']}")
    
    print("\n[OK] Test Completed")
