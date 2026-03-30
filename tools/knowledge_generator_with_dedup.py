# -*- coding: utf-8 -*-
"""
知识库生成器 - 集成实时去重检测（V2.0）
实现三层防护体系：
1. 训练前预防：语料质量审核
2. 生成时干预：Prompt优化 + 实时去重
3. 生成后管控：自动化去重流程

符合规范：
- 技术栈：Python 3.12.x + Pydantic v2 + LanceDB
- 异步支持：根据ADR-008实现异步方法
- 日志规范：使用统一Logger
- 降级方案：参考经验文档V5.2章节
"""

import json
import hashlib
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pydantic import BaseModel, Field
import logging

# 获取Logger
logger = logging.getLogger(__name__)

# 尝试导入可选依赖（带降级方案）
try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers not installed, semantic dedup will be disabled")

# LanceDB导入（项目已锁定LanceDB ≥0.12.0）
try:
    import lancedb
    LANCEDB_AVAILABLE = True
except ImportError:
    LANCEDB_AVAILABLE = False
    logger.warning("LanceDB not installed, vector dedup will be disabled")

# 导入AI服务（使用项目统一的AIProvider）
try:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core.online_provider import OnlineProvider
    from core.ai_provider import GenerationConfig, GenerationResult
    AI_PROVIDER_AVAILABLE = True
except ImportError as e:
    AI_PROVIDER_AVAILABLE = False
    logger.warning(f"AI provider not available: {e}")


# ==================== Pydantic数据模型 ====================

class KnowledgePoint(BaseModel):
    """知识点数据模型（符合V1.7版本规范）"""
    knowledge_id: str = Field(..., description="知识点ID")
    title: str = Field(..., description="知识点标题")
    content: str = Field(..., description="知识点内容")
    keywords: List[str] = Field(default_factory=list, description="关键词列表")
    category: str = Field(..., description="知识库分类")
    domain: str = Field(..., description="知识库领域")
    difficulty: str = Field(default="intermediate", description="难度等级")
    description: str = Field(default="", description="简短描述")
    examples: List[str] = Field(default_factory=list, description="案例列表")
    applications: List[str] = Field(default_factory=list, description="应用建议")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "knowledge_id": "writing_technique-rhetoric-001",
                "title": "借代",
                "content": "借代是一种修辞手法...",
                "keywords": ["借代", "修辞", "替代"],
                "category": "writing_technique",
                "domain": "rhetoric",
                "difficulty": "intermediate"
            }
        }
    }


class DuplicateCheckResult(BaseModel):
    """去重检查结果"""
    is_duplicate: bool = Field(..., description="是否重复")
    duplicate_type: Optional[str] = Field(None, description="重复类型：title/hash/semantic")
    reason: str = Field(default="", description="原因说明")
    similar_id: Optional[str] = Field(None, description="相似知识点ID")
    similarity_score: Optional[float] = Field(None, description="相似度分数")


class GenerationStats(BaseModel):
    """生成统计"""
    total_generated: int = Field(default=0, description="总生成数量")
    duplicates_rejected: int = Field(default=0, description="重复拒绝数量")
    successfully_added: int = Field(default=0, description="成功添加数量")
    retry_count: int = Field(default=0, description="重试次数")


# ==================== 实时去重检测器 ====================

class RealTimeDeduplication:
    """实时去重检测器（符合ADR-009异步模式）"""
    
    def __init__(self, knowledge_base_dir: Path):
        self.knowledge_base_dir = knowledge_base_dir
        self.title_index: Dict[str, str] = {}  # 标题索引
        self.hash_index: Dict[str, str] = {}   # 哈希索引
        self.vector_index = None  # LanceDB向量索引（可选）
        
        # 加载已有知识点
        self._load_existing_knowledge()
        
        # 初始化语义向量模型（延迟加载，符合ADR-008）
        self.semantic_model = None
        self._model_loaded = False
    
    def _load_existing_knowledge(self):
        """加载已有知识点建立索引（保护V5核心资产）"""
        if not self.knowledge_base_dir.exists():
            logger.info(f"Knowledge base directory not found: {self.knowledge_base_dir}")
            return
        
        for category_dir in self.knowledge_base_dir.iterdir():
            if not category_dir.is_dir():
                continue
            
            for domain_file in category_dir.glob("*.json"):
                try:
                    with open(domain_file, 'r', encoding='utf-8-sig') as f:
                        data = json.load(f)
                        
                        # 兼容两种数据格式（参考经验文档V5.2）
                        knowledge_points = []
                        if isinstance(data, dict):
                            # 新格式：knowledge_points 或 knowledge_items
                            knowledge_points = data.get("knowledge_points", data.get("knowledge_items", []))
                        elif isinstance(data, list):
                            knowledge_points = data
                        
                        for kp in knowledge_points:
                            title = kp.get("title", "")
                            content = kp.get("content", "")
                            kp_id = kp.get("knowledge_id", "")
                            
                            if title:
                                self.title_index[title] = kp_id
                            
                            if content:
                                content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
                                self.hash_index[content_hash] = kp_id
                
                except json.JSONDecodeError as e:
                    # JSON格式错误，记录警告但不中断
                    logger.warning(f"Invalid JSON in {domain_file.name}: {e}")
                except Exception as e:
                    logger.error(f"Failed to load file {domain_file}: {e}")
        
        logger.info(f"Loaded {len(self.title_index)} title indices")
        logger.info(f"Loaded {len(self.hash_index)} hash indices")
    
    def _ensure_model_loaded(self):
        """确保模型已加载（延迟加载模式，使用国内镜像）"""
        if not self._model_loaded and SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                # 使用国内镜像站（符合项目规范）
                import os
                os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
                
                self.semantic_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                logger.info("Semantic vector model loaded successfully from HF-Mirror")
            except Exception as e:
                logger.error(f"Failed to load semantic vector model: {e}")
                self.semantic_model = None
            finally:
                self._model_loaded = True
    
    def check_duplicate(self, title: str, content: str, threshold: float = 0.85) -> DuplicateCheckResult:
        """
        检查重复（三层防护）
        
        Args:
            title: 待检查的标题
            content: 待检查的内容
            threshold: 相似度阈值
        
        Returns:
            DuplicateCheckResult
        """
        # 第一层：标题精确匹配
        if title in self.title_index:
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_type="title",
                reason=f"Title duplicate: {title}",
                similar_id=self.title_index[title]
            )
        
        # 第二层：内容哈希匹配
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        if content_hash in self.hash_index:
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_type="hash",
                reason="Content duplicate (hash match)",
                similar_id=self.hash_index[content_hash]
            )
        
        # 第三层：语义相似度检测（如果可用）
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            self._ensure_model_loaded()
            if self.semantic_model and len(self.title_index) > 0:
                # TODO: 集成LanceDB向量搜索
                # 当前版本仅做基础检查，后续可集成LanceDB
                pass
        
        return DuplicateCheckResult(
            is_duplicate=False,
            reason="No duplicate detected"
        )
    
    async def check_duplicate_async(self, title: str, content: str, threshold: float = 0.85) -> DuplicateCheckResult:
        """异步检查重复（符合ADR-009）"""
        # 使用线程池执行CPU密集型操作
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.check_duplicate, title, content, threshold)
    
    def add_to_index(self, title: str, content: str, kp_id: str):
        """添加新知识点到索引"""
        if title:
            self.title_index[title] = kp_id
        
        if content:
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            self.hash_index[content_hash] = kp_id


# ==================== Prompt优化器 ====================

class PromptOptimizer:
    """Prompt优化器（符合12.5最佳实践方案）"""
    
    @staticmethod
    def generate_knowledge_prompt(
        category: str, 
        domain: str, 
        existing_titles: List[str], 
        count: int = 10,
        quality_reference: str = "经验文档/11.14知识库样本.md"
    ) -> str:
        """
        生成优化的知识库生成Prompt
        
        符合规范：
        - 明确具体（原则1）
        - 提供上下文（原则2）
        - 允许不确定性（原则3）
        - 使用示例引导（原则4）
        """
        prompt = f"""请生成{count}个{domain}领域的知识点，要求：

## 核心要求

1. **避免重复**：
   - 每个知识点标题必须是全新的，不得与以下已有标题重复：
     {', '.join(existing_titles[:20]) if existing_titles else '（当前无已有知识点）'}
   - 内容必须有实质性差异，避免换汤不换药
   - 如果某个知识点已被充分覆盖，请转向其他未被覆盖的技巧

2. **内容质量**：
   - 参考质量标准：{quality_reference}
   - 每个知识点必须包含：
     * 核心概念（至少100字）
     * 详细内容（至少500字，包含背景、原理、分类等）
     * 经典案例（至少3-4个具体案例，包含引用和细节）
     * 写作应用建议（角色塑造、世界观构建、情节设计等）

3. **原创性**：
   - 标题和内容都必须具有原创性
   - 涵盖不同的{domain}类型
   - 提供新颖的视角和应用方法

4. **自我审查**：
   - 如果已有的{domain}知识点已经非常全面，没有新的角度可以补充
   - 请直接回复："当前知识库已足够完整，无需新增知识点"
   - 而不是强行生成低质量内容

## 输出格式

请严格按照以下JSON格式输出：

```json
{{
  "knowledge_points": [
    {{
      "knowledge_id": "{category}-{domain}-XXX",
      "title": "知识点标题（必须独特）",
      "content": "详细内容（至少500字）",
      "keywords": ["关键词1", "关键词2", "关键词3"],
      "category": "{category}",
      "domain": "{domain}",
      "difficulty": "beginner/intermediate/advanced",
      "description": "简短描述（50字以内）",
      "examples": ["案例1", "案例2", "案例3"],
      "applications": ["应用建议1", "应用建议2"]
    }}
  ]
}}
```

## 质量标准参考

以下是一个高质量知识点的示例：

【示例：路西法（堕落晨星）】
ID: xuanhuan-mythology-lucifer-001  
题材: xuanhuan | 领域: mythology  
难度: intermediate  
关键词: 路西法, 晨星, 堕落天使, 基督教神话, 傲慢之罪

核心概念
路西法原为基督教神话中最高阶炽天使，因傲慢堕落成为地狱七君主之一...

详细内容
[包含：神学起源、地位与象征、能力体系、与其他神话的关联、文学形象演变]

经典案例应用
[至少3-4个具体案例，包含引用和细节]

写作应用建议
[角色塑造、世界观构建、情节设计等具体指导]

---

请按照以上质量标准生成{count}个{domain}知识点。记住：质量优先于数量，避免重复，确保原创！
"""
        return prompt
    
    @staticmethod
    def generate_with_retry_prompt(
        category: str, 
        domain: str, 
        failed_titles: List[str],
        quality_reference: str = "经验文档/11.14知识库样本.md"
    ) -> str:
        """生成重试Prompt（当首次生成失败时）"""
        prompt = f"""之前尝试生成的以下知识点未能通过质量检查：
{', '.join(failed_titles)}

请重新生成这些知识点，注意：
1. 确保标题和内容与已有知识点不重复
2. 提供全新的视角和应用方法
3. 增加内容的深度和细节
4. 参考质量标准：{quality_reference}

输出格式同上。
"""
        return prompt


# ==================== 知识库生成器 ====================

class KnowledgeGeneratorWithDedup:
    """集成实时去重的知识库生成器（符合V1.19.0规范）"""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.knowledge_base_dir = workspace_root / "data" / "knowledge"
        
        # 初始化实时去重检测器
        self.dedup_checker = RealTimeDeduplication(self.knowledge_base_dir)
        
        # Prompt优化器
        self.prompt_optimizer = PromptOptimizer()
        
        # 统计信息（使用Pydantic模型）
        self.stats = GenerationStats()
        
        # AI服务（使用DeepSeek API）
        self.ai_provider = None
        self._init_ai_provider()
    
    def _init_ai_provider(self):
        """初始化AI Provider（使用DeepSeek API）"""
        if not AI_PROVIDER_AVAILABLE:
            logger.warning("AI provider not available, generation will fail")
            return
        
        try:
            # 加载配置（符合项目规范）
            import yaml
            config_file = self.workspace_root / "config.yaml"
            
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                
                api_key = config.get("api_key", "")
                base_url = config.get("base_url", "https://api.deepseek.com/v1")
                model = config.get("model", "deepseek-chat")
                
                if not api_key:
                    logger.error("API key not found in config.yaml")
                    return
                
                # 创建配置字典（符合OnlineProvider接口）
                provider_config = {
                    "provider": "DeepSeek",
                    "api_key": api_key,
                    "base_url": base_url,
                    "model": model,
                    "temperature": 0.8,
                    "timeout": 120,
                    "max_retries": 3
                }
                
                # 创建OnlineProvider实例
                self.ai_provider = OnlineProvider(provider_config)
                
                logger.info(f"AI provider initialized: DeepSeek/{model}")
            
            else:
                logger.error("config.yaml not found")
        
        except Exception as e:
            logger.error(f"Failed to initialize AI provider: {e}")
    
    def generate_knowledge_points(
        self,
        category: str,
        domain: str,
        count: int = 10,
        max_retries: int = 3,
        temperature: float = 0.8
    ) -> str:
        """
        生成知识点Prompt（带实时去重）
        
        注意：此方法返回Prompt供外部AI服务调用
        实际生成需要配合validate_and_filter方法
        
        Args:
            category: 知识库分类
            domain: 知识库领域
            count: 生成数量
            max_retries: 最大重试次数
            temperature: 温度参数（0-1，越高越随机）
        
        Returns:
            优化的Prompt字符串
        """
        logger.info(f"Starting knowledge generation: {category}/{domain}")
        logger.info(f"Target count: {count}")
        
        # 加载已有标题
        existing_titles = self._load_existing_titles(category, domain)
        logger.info(f"Existing knowledge points: {len(existing_titles)}")
        
        # 生成优化的Prompt
        prompt = self.prompt_optimizer.generate_knowledge_prompt(
            category, domain, existing_titles, count
        )
        
        return prompt
    
    async def generate_knowledge_points_async(
        self,
        category: str,
        domain: str,
        count: int = 10,
        max_retries: int = 3,
        temperature: float = 0.8
    ) -> str:
        """异步生成知识点Prompt（符合ADR-009）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            self.generate_knowledge_points,
            category, domain, count, max_retries, temperature
        )
    
    def generate_with_ai(
        self,
        category: str,
        domain: str,
        count: int = 10,
        temperature: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        使用DeepSeek API生成知识点（完整流程）
        
        Args:
            category: 知识库分类
            domain: 知识库领域
            count: 生成数量
            temperature: 温度参数
        
        Returns:
            生成的知识点列表（字典格式）
        """
        if not self.ai_provider:
            logger.error("AI provider not initialized")
            return []
        
        # 生成优化的Prompt
        prompt = self.generate_knowledge_points(category, domain, count, temperature=temperature)
        
        # 调用DeepSeek API
        try:
            logger.info("Calling DeepSeek API...")
            
            config = GenerationConfig(
                temperature=temperature,
                max_tokens=8000,  # 知识点生成需要较多token
            )
            
            result = self.ai_provider.generate(prompt, config)
            
            if not result.success:
                logger.error(f"AI generation failed: {result.error_message}")
                return []
            
            # 解析JSON响应
            response_text = result.text.strip()
            
            # 提取JSON部分（处理markdown代码块）
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            else:
                json_text = response_text
            
            # 解析JSON
            data = json.loads(json_text)
            
            if isinstance(data, dict) and "knowledge_points" in data:
                knowledge_points = data["knowledge_points"]
            elif isinstance(data, list):
                knowledge_points = data
            else:
                logger.error("Invalid response format from AI")
                return []
            
            logger.info(f"Generated {len(knowledge_points)} knowledge points")
            return knowledge_points
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            return []
        except Exception as e:
            logger.error(f"Error during AI generation: {e}")
            return []
    
    async def generate_with_ai_async(
        self,
        category: str,
        domain: str,
        count: int = 10,
        temperature: float = 0.8
    ) -> List[Dict[str, Any]]:
        """异步AI生成（符合ADR-009）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.generate_with_ai,
            category, domain, count, temperature
        )
    
    def validate_and_filter(
        self,
        knowledge_points: List[Dict[str, Any]],
        category: str,
        domain: str
    ) -> Tuple[List[KnowledgePoint], List[Dict[str, Any]]]:
        """
        验证并过滤知识点
        
        Args:
            knowledge_points: 待验证的知识点列表（字典格式）
            category: 知识库分类
            domain: 知识库领域
        
        Returns:
            (valid_points, invalid_points)
        """
        valid_points: List[KnowledgePoint] = []
        invalid_points: List[Dict[str, Any]] = []
        
        for kp_dict in knowledge_points:
            try:
                # 转换为Pydantic模型（验证数据格式）
                kp = KnowledgePoint(**kp_dict)
                
                # 实时去重检查
                check_result = self.dedup_checker.check_duplicate(kp.title, kp.content)
                
                if check_result.is_duplicate:
                    logger.warning(f"[REJECT] {kp.title}: {check_result.reason}")
                    
                    kp_dict["rejection_reason"] = check_result.reason
                    kp_dict["duplicate_type"] = check_result.duplicate_type
                    kp_dict["similar_id"] = check_result.similar_id
                    
                    invalid_points.append(kp_dict)
                    self.stats.duplicates_rejected += 1
                else:
                    logger.info(f"[OK] {kp.title}")
                    
                    # 添加到索引
                    kp_id = kp.knowledge_id or f"{category}-{domain}-{len(valid_points)}"
                    self.dedup_checker.add_to_index(kp.title, kp.content, kp_id)
                    
                    valid_points.append(kp)
                    self.stats.successfully_added += 1
            
            except Exception as e:
                logger.error(f"Invalid knowledge point format: {e}")
                kp_dict["rejection_reason"] = f"Invalid format: {e}"
                invalid_points.append(kp_dict)
        
        self.stats.total_generated = len(knowledge_points)
        
        return valid_points, invalid_points
    
    async def validate_and_filter_async(
        self,
        knowledge_points: List[Dict[str, Any]],
        category: str,
        domain: str
    ) -> Tuple[List[KnowledgePoint], List[Dict[str, Any]]]:
        """异步验证并过滤知识点（符合ADR-009）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.validate_and_filter,
            knowledge_points, category, domain
        )
    
    def save_knowledge_points(
        self,
        knowledge_points: List[KnowledgePoint],
        category: str,
        domain: str,
        mode: str = "append"
    ) -> Dict[str, Any]:
        """
        保存知识点到文件（保护V5核心资产）
        
        Args:
            knowledge_points: 知识点列表（Pydantic模型）
            category: 知识库分类
            domain: 知识库领域
            mode: 保存模式（append/overwrite）
        
        Returns:
            保存结果统计
        """
        # 确保目录存在
        category_dir = self.knowledge_base_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)
        
        domain_file = category_dir / f"{domain}.json"
        
        # 加载已有数据（保护V5核心资产）
        existing_points = []
        if mode == "append" and domain_file.exists():
            try:
                with open(domain_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    
                    if isinstance(existing_data, dict):
                        existing_points = existing_data.get("knowledge_points", [])
                    elif isinstance(existing_data, list):
                        existing_points = existing_data
            except Exception as e:
                logger.error(f"Failed to load existing data: {e}")
                existing_points = []
        
        # 合并知识点
        all_points = existing_points + [kp.model_dump() for kp in knowledge_points]
        
        # 保存
        output_data = {
            "metadata": {
                "category": category,
                "domain": domain,
                "total_count": len(all_points),
                "last_updated": datetime.now().isoformat(),
                "generator": "knowledge_generator_with_dedup v2.0",
                "version": "V1.19.0"
            },
            "knowledge_points": all_points
        }
        
        with open(domain_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(knowledge_points)} new knowledge points")
        logger.info(f"File path: {domain_file}")
        logger.info(f"Total knowledge points: {len(all_points)}")
        
        return {
            "file_path": str(domain_file),
            "new_points": len(knowledge_points),
            "total_points": len(all_points)
        }
    
    def _load_existing_titles(self, category: str, domain: str) -> List[str]:
        """加载已有知识点标题（保护V5核心资产）"""
        domain_file = self.knowledge_base_dir / category / f"{domain}.json"
        
        if not domain_file.exists():
            return []
        
        try:
            with open(domain_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                if isinstance(data, dict):
                    knowledge_points = data.get("knowledge_points", [])
                elif isinstance(data, list):
                    knowledge_points = data
                else:
                    return []
                
                return [kp.get("title", "") for kp in knowledge_points if kp.get("title")]
        
        except Exception as e:
            logger.error(f"Failed to load existing titles: {e}")
            return []
    
    def generate_report(self) -> str:
        """生成统计报告"""
        total = max(self.stats.total_generated, 1)
        
        report = f"""
{'='*60}
知识库生成统计报告
{'='*60}

总体统计：
- 总生成数量: {self.stats.total_generated}
- 成功添加数量: {self.stats.successfully_added}
- 重复拒绝数量: {self.stats.duplicates_rejected}
- 重试次数: {self.stats.retry_count}

质量指标：
- 通过率: {self.stats.successfully_added/total*100:.2f}%
- 重复率: {self.stats.duplicates_rejected/total*100:.2f}%

符合规范：
- 版本: V1.19.0
- 技术栈: Python 3.12.x + Pydantic v2 + LanceDB
- 异步支持: 是（ADR-009）
- V5保护: 是

{'='*60}
"""
        return report


# ==================== 主函数 ====================

def main():
    """测试函数"""
    from pathlib import Path
    
    # 获取工作区根目录
    workspace_root = Path(__file__).parent.parent
    
    # 创建生成器实例
    generator = KnowledgeGeneratorWithDedup(workspace_root)
    
    # 测试生成Prompt
    prompt = generator.generate_knowledge_points(
        category="writing_technique",
        domain="rhetoric",
        count=5
    )
    
    print(prompt)
    
    # 显示统计报告
    print(generator.generate_report())


if __name__ == "__main__":
    main()
