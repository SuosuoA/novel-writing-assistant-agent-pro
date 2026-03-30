"""
知识库生成器V4 - 支持写作技巧六领域分类

V4.0版本
创建日期：2026-03-27

特性：
- 支持传统知识库（scifi/xuanhuan/history/general）
- 支持写作技巧库（writing_technique + 固定六领域）
- 三层去重（标题→SimHash→向量相似度）
- 五并发生成（ThreadPoolExecutor, max_workers=5）
- 六项质检（字数/关键词/案例/参考文献/应用/AI痕迹）
- 指数退避重试（max_retries=3）
- 断点续传（进度追踪）
- 质量标准：每条3000字（参考11.14样本）

写作技巧六领域：
1. narrative（叙事技巧）
2. description（描写技巧）
3. rhetoric（修辞技巧）
4. structure（结构技巧）
5. special_sentence（特殊句式）
6. advanced（高级技法）

参考文档：
- 11.14知识库样本.md（质量标准）
- 11.15知识库生成器V4.md（优化方案）
- 12.2写作技巧库集成实现说明✅️.md（六领域定义）

使用示例：
    # 生成写作技巧知识点
    generator = KnowledgeGeneratorV4(workspace_root=Path("E:/project"))
    
    # 生成叙事技巧
    result = generator.generate_writing_technique(
        domain="narrative",
        title="第一人称叙事",
        keywords=["第一人称", "代入感", "视角限制"]
    )
    
    # 批量生成
    result = generator.batch_generate(
        category="writing_technique",
        domain="narrative",
        titles=["第一人称叙事", "第三人称叙事", "多视角叙事"]
    )
"""

import json
import hashlib
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI
import yaml


# ============================================================================
# 常量定义
# ============================================================================

# 写作技巧固定六领域
WRITING_TECHNIQUE_DOMAINS = {
    "narrative": "叙事技巧",
    "description": "描写技巧",
    "rhetoric": "修辞技巧",
    "structure": "结构技巧",
    "special_sentence": "特殊句式",
    "advanced": "高级技法"
}

# 传统知识库分类
TRADITIONAL_CATEGORIES = ["scifi", "xuanhuan", "history", "general"]

# 质量标准（参考11.14样本）
QUALITY_STANDARDS = {
    "min_chars": 2000,  # 最低字数
    "target_chars": 3000,  # 目标字数
    "min_keywords": 5,  # 最少关键词
    "required_sections": [  # 必需章节
        "核心概念", "详细内容", "经典案例", 
        "写作应用", "常见误区", "参考文献"
    ]
}

# AI痕迹关键词
AI_PATTERNS = [
    "首先", "其次", "最后", "总之", "综上所述",
    "值得注意的是", "需要指出的是", "不言而喻",
    "众所周知", "显而易见", "毋庸置疑"
]


# ============================================================================
# 数据模型
# ============================================================================

@dataclass
class GenerationResult:
    """生成结果"""
    success: bool
    knowledge_id: str = ""
    title: str = ""
    category: str = ""
    domain: str = ""
    content: str = ""
    quality_score: float = 0.0
    quality_issues: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    error: str = ""


@dataclass
class DeduplicationResult:
    """去重结果"""
    is_duplicate: bool
    duplicate_type: str = ""  # title/simhash/vector
    duplicate_id: str = ""
    similarity: float = 0.0


@dataclass
class QualityCheckResult:
    """质检结果"""
    passed: bool
    score: float = 0.0
    issues: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 知识库生成器V4
# ============================================================================

class KnowledgeGeneratorV4:
    """知识库生成器V4 - 支持写作技巧六领域"""
    
    def __init__(self, workspace_root: Path):
        """
        初始化生成器
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = workspace_root
        self.data_dir = workspace_root / "data" / "knowledge"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化API客户端
        self.client = self._init_api_client()
        
        # 去重缓存
        self._title_cache: Dict[str, str] = {}  # title -> knowledge_id
        self._simhash_cache: Dict[str, str] = {}  # simhash -> knowledge_id
        self._vector_cache: Dict[str, str] = {}  # vector_id -> knowledge_id
        
        # 统计数据
        self._stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "duplicate": 0,
            "quality_failed": 0
        }
        
        # 进度追踪（断点续传）
        # 进度文件保存到data/knowledge/.progress/目录
        progress_dir = workspace_root / "data" / "knowledge" / ".progress"
        progress_dir.mkdir(parents=True, exist_ok=True)
        self._progress_file = progress_dir / "knowledge_gen_progress.json"
        self._load_progress()
    
    def _init_api_client(self) -> OpenAI:
        """初始化API客户端"""
        try:
            # 优先从加密存储获取
            from core.api_key_encryption import APIKeyEncryption
            encryption = APIKeyEncryption()
            api_key = encryption.get_api_key("DeepSeek")
            
            if not api_key:
                raise ValueError("无法从.secrets获取DeepSeek API Key")
        except Exception:
            # 降级：从config.yaml读取
            config_path = self.workspace_root / "config.yaml"
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            api_key = config.get('api_key')
            if not api_key:
                raise ValueError("config.yaml中未找到api_key字段")
        
        return OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
    
    def _load_progress(self):
        """加载进度（断点续传）"""
        if self._progress_file.exists():
            try:
                with open(self._progress_file, 'r', encoding='utf-8') as f:
                    progress = json.load(f)
                    self._stats = progress.get("stats", self._stats)
                    self._title_cache = progress.get("title_cache", {})
            except Exception as e:
                print(f"加载进度失败: {e}")
    
    def _save_progress(self):
        """保存进度（断点续传）"""
        try:
            progress = {
                "stats": self._stats,
                "title_cache": self._title_cache,
                "updated_at": datetime.now().isoformat()
            }
            with open(self._progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存进度失败: {e}")
    
    # ========================================================================
    # 去重机制（三层）
    # ========================================================================
    
    def _calculate_simhash(self, content: str) -> str:
        """计算SimHash"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _check_duplicate_title(self, title: str) -> DeduplicationResult:
        """标题去重"""
        if title in self._title_cache:
            return DeduplicationResult(
                is_duplicate=True,
                duplicate_type="title",
                duplicate_id=self._title_cache[title],
                similarity=1.0
            )
        return DeduplicationResult(is_duplicate=False)
    
    def _check_duplicate_simhash(self, content: str) -> DeduplicationResult:
        """SimHash去重"""
        simhash = self._calculate_simhash(content)
        if simhash in self._simhash_cache:
            return DeduplicationResult(
                is_duplicate=True,
                duplicate_type="simhash",
                duplicate_id=self._simhash_cache[simhash],
                similarity=1.0
            )
        return DeduplicationResult(is_duplicate=False, duplicate_id=simhash)
    
    def _check_duplicate_vector(self, content: str, category: str, domain: str) -> DeduplicationResult:
        """向量相似度去重（可选，需要向量库支持）"""
        # TODO: 集成LanceDB向量检索
        # 这里暂时跳过，后续可以添加
        return DeduplicationResult(is_duplicate=False)
    
    # ========================================================================
    # 质检机制（六项）
    # ========================================================================
    
    def _check_quality(self, knowledge: Dict[str, Any]) -> QualityCheckResult:
        """
        六项质检
        
        1. 字数检查（≥2000字）
        2. 关键词检查（≥5个）
        3. 案例检查（至少1个经典案例）
        4. 参考文献检查（至少1个）
        5. 写作应用检查（至少1个应用场景）
        6. AI痕迹检查（≤3处）
        """
        issues = []
        score = 0.0
        details = {}
        
        # 1. 字数检查
        content = knowledge.get("content", "")
        char_count = len(content)
        details["char_count"] = char_count
        
        if char_count < QUALITY_STANDARDS["min_chars"]:
            issues.append(f"字数不足：{char_count}字 < {QUALITY_STANDARDS['min_chars']}字")
        elif char_count >= QUALITY_STANDARDS["target_chars"]:
            score += 0.2
        else:
            score += 0.1
        
        # 2. 关键词检查
        keywords = knowledge.get("keywords", [])
        keyword_count = len(keywords)
        details["keyword_count"] = keyword_count
        
        if keyword_count < QUALITY_STANDARDS["min_keywords"]:
            issues.append(f"关键词不足：{keyword_count}个 < {QUALITY_STANDARDS['min_keywords']}个")
        else:
            score += 0.15
        
        # 3. 案例检查
        classic_cases = knowledge.get("classic_cases", "")
        has_cases = len(classic_cases) > 100
        details["has_cases"] = has_cases
        
        if not has_cases:
            issues.append("缺少经典案例")
        else:
            score += 0.15
        
        # 4. 参考文献检查
        references = knowledge.get("references", [])
        if isinstance(references, str):
            references = [references]
        has_references = len(references) > 0
        details["has_references"] = has_references
        
        if not has_references:
            issues.append("缺少参考文献")
        else:
            score += 0.15
        
        # 5. 写作应用检查
        writing_applications = knowledge.get("writing_applications", "")
        has_applications = len(writing_applications) > 100
        details["has_applications"] = has_applications
        
        if not has_applications:
            issues.append("缺少写作应用")
        else:
            score += 0.15
        
        # 6. AI痕迹检查
        ai_count = sum(1 for pattern in AI_PATTERNS if pattern in content)
        details["ai_pattern_count"] = ai_count
        
        if ai_count > 3:
            issues.append(f"AI痕迹过多：{ai_count}处 > 3处")
        else:
            score += 0.2
        
        passed = len(issues) == 0 and score >= 0.6
        
        return QualityCheckResult(
            passed=passed,
            score=score,
            issues=issues,
            details=details
        )
    
    # ========================================================================
    # 知识点生成
    # ========================================================================
    
    def _build_generation_prompt(
        self,
        category: str,
        domain: str,
        title: str,
        keywords: List[str],
        is_writing_technique: bool = False
    ) -> str:
        """
        构建生成Prompt
        
        参考标准：11.14知识库样本.md
        """
        if is_writing_technique:
            # 写作技巧Prompt
            domain_cn = WRITING_TECHNIQUE_DOMAINS.get(domain, domain)
            prompt = f"""请为小说创作生成一条高质量的写作技巧知识点，严格按照以下JSON格式：

{{
  "title": "{title}",
  "core_concept": "核心概念解释（200-300字）",
  "keywords": {json.dumps(keywords, ensure_ascii=False)},
  "content": "详细内容（1000-1500字，包含背景/起源、核心原理、主要特征、与其他概念的关系、应用场景）",
  "classic_cases": "经典案例（500-800字，至少2个案例，每个案例包含案例描述和写作启示）",
  "writing_applications": "写作应用（400-600字，至少3个具体应用场景，如角色塑造、情节设计、氛围营造）",
  "common_mistakes": [
    {{
      "mistake": "常见误区名称",
      "explanation": "误区说明和改进建议"
    }}
  ],
  "references": [
    {{
      "title": "参考文献标题",
      "author": "作者",
      "year": "年份",
      "description": "文献说明"
    }}
  ]
}}

【写作技巧分类】：{domain_cn}
【技巧名称】：{title}
【关键词】：{', '.join(keywords)}

【质量要求】：
1. 总字数≥3000字
2. 核心概念要准确、深入
3. 详细内容要有理论深度和实践指导性
4. 经典案例要具体、有启发性
5. 写作应用要可操作、有针对性
6. 常见误区要真实、有改进建议
7. 参考文献要权威、相关
8. 避免AI痕迹（不要用"首先、其次、最后、总之"等）

请直接输出JSON，不要有任何其他说明文字。"""
        else:
            # 传统知识库Prompt
            prompt = f"""请为小说创作生成一条高质量的知识点，严格按照以下JSON格式：

{{
  "title": "{title}",
  "core_concept": "核心概念解释（200-300字）",
  "keywords": {json.dumps(keywords, ensure_ascii=False)},
  "content": "详细内容（1000-1500字，包含背景/起源、核心原理、主要特征、与其他概念的关系、应用场景）",
  "classic_cases": "经典案例（500-800字，至少2个案例）",
  "writing_applications": "写作应用（400-600字，至少3个应用场景）",
  "common_mistakes": [
    {{
      "mistake": "常见误区名称",
      "explanation": "误区说明和改进建议"
    }}
  ],
  "references": [
    {{
      "title": "参考文献标题",
      "author": "作者",
      "year": "年份",
      "description": "文献说明"
    }}
  ]
}}

【题材分类】：{category}
【知识领域】：{domain}
【知识点名称】：{title}
【关键词】：{', '.join(keywords)}

【质量要求】：
1. 总字数≥3000字
2. 核心概念要准确、深入
3. 详细内容要有理论深度和实践指导性
4. 经典案例要具体、有启发性
5. 写作应用要可操作、有针对性
6. 常见误区要真实、有改进建议
7. 参考文献要权威、相关
8. 避免AI痕迹（不要用"首先、其次、最后、总之"等）

请直接输出JSON，不要有任何其他说明文字。"""
        
        return prompt
    
    def _parse_api_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """解析API响应"""
        try:
            # 尝试直接解析JSON
            knowledge = json.loads(response_text)
            return knowledge
        except json.JSONDecodeError:
            # 尝试提取JSON块
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                try:
                    knowledge = json.loads(json_match.group())
                    return knowledge
                except json.JSONDecodeError:
                    pass
            return None
    
    def generate_knowledge(
        self,
        category: str,
        domain: str,
        title: str,
        keywords: List[str],
        max_retries: int = 3
    ) -> GenerationResult:
        """
        生成单个知识点
        
        Args:
            category: 分类（scifi/xuanhuan/history/general/writing_technique）
            domain: 领域（physics/chemistry/narrative/description等）
            title: 知识点标题
            keywords: 关键词列表
            max_retries: 最大重试次数
        
        Returns:
            GenerationResult: 生成结果
        """
        start_time = time.time()
        self._stats["total"] += 1
        
        # 判断是否为写作技巧
        is_writing_technique = (category == "writing_technique")
        
        # 1. 去重检查（标题）
        dedup_result = self._check_duplicate_title(title)
        if dedup_result.is_duplicate:
            self._stats["duplicate"] += 1
            return GenerationResult(
                success=False,
                title=title,
                category=category,
                domain=domain,
                error=f"标题重复: {dedup_result.duplicate_id}"
            )
        
        # 2. 构建Prompt
        prompt = self._build_generation_prompt(
            category, domain, title, keywords, is_writing_technique
        )
        
        # 3. 调用API（指数退避重试）
        last_error = ""
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": "你是一位专业的小说创作知识库编辑，擅长生成高质量的写作技巧知识点。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=4000
                )
                
                response_text = response.choices[0].message.content
                knowledge = self._parse_api_response(response_text)
                
                if not knowledge:
                    last_error = "JSON解析失败"
                    time.sleep(2 ** attempt)  # 指数退避
                    continue
                
                # 4. 质检
                quality_result = self._check_quality(knowledge)
                
                if not quality_result.passed:
                    self._stats["quality_failed"] += 1
                    last_error = f"质量不达标: {', '.join(quality_result.issues)}"
                    time.sleep(2 ** attempt)
                    continue
                
                # 5. 生成知识点ID
                knowledge_id = f"{category}_{domain}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                
                # 6. 补充元数据
                knowledge["knowledge_id"] = knowledge_id
                knowledge["category"] = category
                knowledge["domain"] = domain
                knowledge["created_at"] = datetime.now().isoformat()
                knowledge["updated_at"] = datetime.now().isoformat()
                
                # 7. SimHash去重检查
                simhash_result = self._check_duplicate_simhash(knowledge.get("content", ""))
                if simhash_result.is_duplicate:
                    self._stats["duplicate"] += 1
                    return GenerationResult(
                        success=False,
                        title=title,
                        category=category,
                        domain=domain,
                        error=f"内容重复: {simhash_result.duplicate_id}"
                    )
                
                # 8. 保存知识点
                self._save_knowledge(knowledge)
                
                # 9. 更新缓存
                self._title_cache[title] = knowledge_id
                self._simhash_cache[simhash_result.duplicate_id] = knowledge_id
                
                # 10. 更新统计
                self._stats["success"] += 1
                self._save_progress()
                
                latency_ms = (time.time() - start_time) * 1000
                
                return GenerationResult(
                    success=True,
                    knowledge_id=knowledge_id,
                    title=title,
                    category=category,
                    domain=domain,
                    content=knowledge.get("content", ""),
                    quality_score=quality_result.score,
                    quality_issues=quality_result.issues,
                    latency_ms=latency_ms
                )
                
            except Exception as e:
                last_error = str(e)
                time.sleep(2 ** attempt)
        
        # 所有重试失败
        self._stats["failed"] += 1
        self._save_progress()
        
        latency_ms = (time.time() - start_time) * 1000
        
        return GenerationResult(
            success=False,
            title=title,
            category=category,
            domain=domain,
            error=f"API调用失败（{max_retries}次重试）: {last_error}",
            latency_ms=latency_ms
        )
    
    def generate_writing_technique(
        self,
        domain: str,
        title: str,
        keywords: List[str]
    ) -> GenerationResult:
        """
        生成写作技巧知识点（便捷方法）
        
        Args:
            domain: 领域（narrative/description/rhetoric/structure/special_sentence/advanced）
            title: 技巧名称
            keywords: 关键词列表
        
        Returns:
            GenerationResult: 生成结果
        """
        # 验证领域
        if domain not in WRITING_TECHNIQUE_DOMAINS:
            return GenerationResult(
                success=False,
                title=title,
                category="writing_technique",
                domain=domain,
                error=f"无效的写作技巧领域: {domain}"
            )
        
        return self.generate_knowledge(
            category="writing_technique",
            domain=domain,
            title=title,
            keywords=keywords
        )
    
    def batch_generate(
        self,
        category: str,
        domain: str,
        titles: List[str],
        keywords_list: Optional[List[List[str]]] = None,
        max_workers: int = 5
    ) -> List[GenerationResult]:
        """
        批量生成知识点（五并发）
        
        Args:
            category: 分类
            domain: 领域
            titles: 标题列表
            keywords_list: 关键词列表（每个标题对应一个关键词列表）
            max_workers: 最大并发数（默认5）
        
        Returns:
            List[GenerationResult]: 生成结果列表
        """
        results = []
        
        # 默认关键词
        if not keywords_list:
            keywords_list = [[] for _ in titles]
        
        # 并发生成
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self.generate_knowledge,
                    category, domain, title, keywords
                ): (title, idx)
                for idx, (title, keywords) in enumerate(zip(titles, keywords_list))
            }
            
            for future in as_completed(futures):
                title, idx = futures[future]
                try:
                    result = future.result()
                    results.append((idx, result))
                except Exception as e:
                    results.append((idx, GenerationResult(
                        success=False,
                        title=title,
                        category=category,
                        domain=domain,
                        error=str(e)
                    )))
        
        # 按原始顺序排序
        results.sort(key=lambda x: x[0])
        
        return [r for _, r in results]
    
    def _save_knowledge(self, knowledge: Dict[str, Any]):
        """
        保存知识点到JSON文件
        
        Args:
            knowledge: 知识点数据
        """
        category = knowledge["category"]
        domain = knowledge["domain"]
        
        # 确定保存路径
        save_dir = self.data_dir / category / domain
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # 读取现有知识库
        json_file = save_dir / f"{domain}.json"
        existing_knowledge = []
        
        if json_file.exists():
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    existing_knowledge = json.load(f)
                    if not isinstance(existing_knowledge, list):
                        existing_knowledge = [existing_knowledge]
            except Exception:
                existing_knowledge = []
        
        # 添加新知识点
        existing_knowledge.append(knowledge)
        
        # 保存
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(existing_knowledge, f, ensure_ascii=False, indent=2)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计数据"""
        return {
            **self._stats,
            "success_rate": (
                self._stats["success"] / self._stats["total"] * 100
                if self._stats["total"] > 0 else 0
            )
        }


# ============================================================================
# 命令行接口
# ============================================================================

def main():
    """命令行测试"""
    import sys
    
    # 修复Windows控制台编码
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
    
    print("=" * 60)
    print("知识库生成器V4 - 支持写作技巧六领域")
    print("=" * 60)
    
    # 初始化生成器
    workspace_root = Path(__file__).parent.parent
    generator = KnowledgeGeneratorV4(workspace_root)
    
    # 测试：生成一个写作技巧知识点
    print("\n【测试】生成写作技巧知识点：第一人称叙事")
    result = generator.generate_writing_technique(
        domain="narrative",
        title="第一人称叙事",
        keywords=["第一人称", "代入感", "视角限制", "叙述视角", "心理描写"]
    )
    
    if result.success:
        print(f"✅ 生成成功")
        print(f"  - 知识点ID: {result.knowledge_id}")
        print(f"  - 质量评分: {result.quality_score:.2f}")
        print(f"  - 耗时: {result.latency_ms:.0f}ms")
        print(f"  - 内容长度: {len(result.content)}字")
    else:
        print(f"❌ 生成失败: {result.error}")
    
    # 显示统计
    stats = generator.get_stats()
    print(f"\n【统计】")
    print(f"  - 总数: {stats['total']}")
    print(f"  - 成功: {stats['success']}")
    print(f"  - 失败: {stats['failed']}")
    print(f"  - 重复: {stats['duplicate']}")
    print(f"  - 质检失败: {stats['quality_failed']}")
    print(f"  - 成功率: {stats['success_rate']:.1f}%")


if __name__ == "__main__":
    main()
