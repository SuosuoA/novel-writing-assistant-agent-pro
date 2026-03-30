"""
知识库验证插件 V1.0

版本: 1.0.0
创建日期: 2026-03-25

功能:
- 知识库一致性验证（OpenClaw向量召回）
- 集成到ValidationScores评分维度
- 支持题材过滤（科幻/玄幻/历史/通用）
- 冲突检测与修复建议生成
- 向量检索召回top-10相关知识
- 召回准确率≥80%

设计参考:
- OpenClaw memory_search工具
- 升级方案 10.升级方案✅️.md
- 知识库Schema 10.6 知识库Schema设计✅️.md
- ADR-003: 知识库双层设计

使用示例:
    # 在iterative_generator_v2.py中集成
    from plugins.knowledge_validator.plugin import KnowledgeValidatorPlugin
    
    validator = KnowledgeValidatorPlugin()
    result = validator.validate({
        "content": generated_content,
        "genre": "科幻",
        "project_name": "星际文明"
    })
    
    # 更新ValidationScores
    scores.knowledge_consistency_score = result["score"]
    scores.knowledge_conflicts = result["conflicts"]
    scores.recalled_knowledge = result["recalled_knowledge"]
"""

import re
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.plugin_interface import ValidatorPlugin, PluginMetadata, PluginType, PluginContext
from core.models import ValidationScores

# 可选依赖检测
try:
    from core.knowledge_retriever import KnowledgeRetriever, RetrievalResult
    HAS_KNOWLEDGE_RETRIEVER = True
except ImportError:
    HAS_KNOWLEDGE_RETRIEVER = False
    KnowledgeRetriever = None
    RetrievalResult = None


# ============================================================================
# 数据模型
# ============================================================================


@dataclass
class KnowledgeConflict:
    """知识冲突记录"""
    conflict_type: str  # 冲突类型（physics/chemistry/biology/religion/mythology/history）
    description: str    # 冲突描述
    severity: str       # 严重程度（high/medium/low）
    knowledge_id: str   # 相关知识点ID
    knowledge_title: str  # 相关知识点标题
    suggestion: str     # 修复建议
    content_snippet: str  # 冲突内容片段


@dataclass
class ValidationResult:
    """知识库验证结果"""
    score: float  # 知识库一致性评分（0-1）
    conflicts: List[Dict[str, Any]]  # 检测到的冲突列表
    recalled_knowledge: List[Dict[str, Any]]  # 召回的相关知识列表
    stats: Dict[str, Any]  # 统计信息


# ============================================================================
# 知识库验证插件
# ============================================================================


class KnowledgeValidatorPlugin(ValidatorPlugin):
    """知识库验证插件 - OpenClaw向量召回

    实现知识库一致性验证，集成到ValidationScores评分维度。

    功能：
    - 题材识别：根据内容关键词识别题材（科幻/玄幻/历史）
    - 知识召回：向量检索召回top-10相关知识
    - 冲突检测：检测生成内容是否违反知识常识
    - 评分生成：生成知识库一致性评分（0-1）
    - 修复建议：为检测到的冲突提供修复建议

    设计参考：
    - OpenClaw memory_search工具
    - ADR-003: 知识库双层设计
    """

    # 类常量
    PLUGIN_ID = "knowledge-validator"
    PLUGIN_NAME = "知识库验证器 V1"
    PLUGIN_VERSION = "1.0.0"

    # 题材关键词映射
    GENRE_KEYWORDS = {
        "scifi": [
            "飞船", "星际", "宇宙", "光速", "虫洞", "黑洞", "量子", "基因",
            "机器人", "人工智能", "相对论", "时间膨胀", "引力波", "粒子",
            "原子", "核聚变", "纳米", "虚拟现实", "火星", "外星人", "太空"
        ],
        "fantasy": [
            "修仙", "炼丹", "飞剑", "灵气", "渡劫", "宗门", "道友", "因果",
            "轮回", "神通", "法宝", "元婴", "化神", "渡劫", "飞升", "天劫",
            "妖兽", "仙界", "魔界", "神兽", "功法"
        ],
        "history": [
            "皇帝", "将军", "朝代", "战争", "宫廷", "藩王", "御史", "翰林",
            "科举", "进士", "状元", "宰相", "尚书", "太守", "县令", "驿站",
            "驿站", "马匹", "战马", "铠甲", "刀剑"
        ]
    }

    # 冲突严重程度权重
    SEVERITY_WEIGHTS = {
        "high": 0.3,    # 严重冲突（如违反物理定律）
        "medium": 0.2,  # 中等冲突（如设定不一致）
        "low": 0.1      # 轻微冲突（如细节不准确）
    }

    def __init__(self):
        """初始化插件"""
        metadata = PluginMetadata(
            id=self.PLUGIN_ID,
            name=self.PLUGIN_NAME,
            version=self.PLUGIN_VERSION,
            description="知识库一致性验证器（OpenClaw向量召回）",
            author="高级项目工程师",
            plugin_type=PluginType.VALIDATOR,
            api_version="1.0",
            priority=90,  # 优先级较高，在质量验证器之前执行
            enabled=True,
            dependencies=[],  # 无依赖，独立运行
            conflicts=["knowledge-validator-v2"],
            permissions=["knowledge.read"],
            min_platform_version="6.0.0",
            entry_class="KnowledgeValidatorPlugin",
        )
        super().__init__(metadata)

        self._logger = logging.getLogger(__name__)
        self._knowledge_retriever: Optional[KnowledgeRetriever] = None

        # 缓存统计
        self._cache_stats = {
            "total_validations": 0,
            "total_conflicts": 0,
            "avg_score": 0.0,
        }

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据"""
        return PluginMetadata(
            id=cls.PLUGIN_ID,
            name=cls.PLUGIN_NAME,
            version=cls.PLUGIN_VERSION,
            description="知识库一致性验证器（OpenClaw向量召回）",
            author="高级项目工程师",
            plugin_type=PluginType.VALIDATOR,
            api_version="1.0",
            priority=90,
            enabled=True,
            dependencies=[],
            conflicts=["knowledge-validator-v2"],
            permissions=["knowledge.read"],
            min_platform_version="6.0.0",
            entry_class="KnowledgeValidatorPlugin",
        )

    def initialize(self, context: PluginContext) -> bool:
        """初始化插件

        Args:
            context: 插件上下文

        Returns:
            是否初始化成功
        """
        if not super().initialize(context):
            return False

        # 初始化知识库检索器
        if HAS_KNOWLEDGE_RETRIEVER:
            try:
                workspace_root = Path(context.config_manager.get("workspace_root", "."))
                self._knowledge_retriever = KnowledgeRetriever(workspace_root=workspace_root)
                self._logger.info(f"[{self.PLUGIN_ID}] 知识库检索器初始化成功")
            except Exception as e:
                self._logger.warning(f"[{self.PLUGIN_ID}] 知识库检索器初始化失败: {e}，将使用降级模式")
                self._knowledge_retriever = None
        else:
            self._logger.warning(f"[{self.PLUGIN_ID}] KnowledgeRetriever模块未找到，将使用降级模式")

        self._logger.info(f"[{self.PLUGIN_ID}] 插件初始化成功")
        return True

    def get_validation_dimensions(self) -> List[str]:
        """获取验证维度

        Returns:
            维度列表
        """
        return [
            "knowledge_consistency",  # 知识库一致性
            "genre_accuracy",  # 题材准确性
            "fact_correctness",  # 事实正确性
            "logic_coherence",  # 逻辑连贯性
        ]

    def validate(self, content: str, context: Optional[Dict[str, Any]] = None) -> ValidationScores:
        """验证内容并返回评分

        Args:
            content: 待验证内容
            context: 验证上下文
                - genre: 题材（scifi/fantasy/history）
                - project_name: 项目名称
                - chapter_id: 章节ID
                - custom_keywords: 自定义关键词列表

        Returns:
            ValidationScores对象（包含knowledge_consistency_score）
        """
        context = context or {}
        
        self._logger.info(f"[{self.PLUGIN_ID}] 开始知识库一致性验证")
        self._cache_stats["total_validations"] += 1

        # 1. 识别题材
        genre = context.get("genre") or self._detect_genre(content)
        self._logger.info(f"[{self.PLUGIN_ID}] 识别题材: {genre}")

        # 2. 提取知识点关键词
        keywords = self._extract_knowledge_keywords(content, context)
        self._logger.debug(f"[{self.PLUGIN_ID}] 提取知识点关键词: {keywords[:10]}...")

        # 3. 召回相关知识
        recalled_knowledge = self._recall_knowledge(keywords, genre)
        self._logger.info(f"[{self.PLUGIN_ID}] 召回相关知识: {len(recalled_knowledge)}条")

        # 4. 检测冲突
        conflicts = self._detect_conflicts(content, recalled_knowledge, genre)
        self._logger.info(f"[{self.PLUGIN_ID}] 检测到冲突: {len(conflicts)}个")

        # 5. 生成评分
        score = self._calculate_score(conflicts, recalled_knowledge)
        self._logger.info(f"[{self.PLUGIN_ID}] 知识库一致性评分: {score:.2f}")

        # 6. 更新统计
        self._cache_stats["total_conflicts"] += len(conflicts)
        self._cache_stats["avg_score"] = (
            (self._cache_stats["avg_score"] * (self._cache_stats["total_validations"] - 1) + score)
            / self._cache_stats["total_validations"]
        )

        # 7. 构建ValidationScores
        validation_scores = ValidationScores()
        validation_scores.knowledge_consistency_score = score
        validation_scores.knowledge_conflicts = [self._conflict_to_dict(c) for c in conflicts]
        validation_scores.recalled_knowledge = recalled_knowledge
        validation_scores.total_score = score  # 仅知识库维度的分数

        return validation_scores

    def _detect_genre(self, content: str) -> str:
        """识别题材

        Args:
            content: 内容文本

        Returns:
            题材标识（scifi/fantasy/history/general）
        """
        scores = {}
        
        for genre, keywords in self.GENRE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in content)
            scores[genre] = score
        
        if not scores or max(scores.values()) == 0:
            return "general"
        
        # 返回得分最高的题材
        return max(scores, key=scores.get)

    def _extract_knowledge_keywords(
        self, 
        content: str, 
        context: Dict[str, Any]
    ) -> List[str]:
        """提取知识点关键词

        Args:
            content: 内容文本
            context: 上下文

        Returns:
            关键词列表
        """
        keywords = set()
        
        # 1. 添加自定义关键词
        custom_keywords = context.get("custom_keywords", [])
        keywords.update(custom_keywords)
        
        # 2. 从内容中提取专业术语
        # 科幻术语
        scifi_patterns = [
            r'(\w+效应)', r'(\w+定律)', r'(\w+原理)',
            r'量子\w+', r'基因\w+', r'纳米\w+',
            r'(\w+反应)', r'(\w+辐射)', r'(\w+场)'
        ]
        
        # 玄幻术语
        fantasy_patterns = [
            r'(\w+丹)', r'(\w+剑)', r'(\w+诀)',
            r'\w+境', r'\w+期', r'\w+劫',
            r'元\w+', r'神\w+', r'灵\w+'
        ]
        
        # 历史术语
        history_patterns = [
            r'(\w+帝)', r'(\w+王)', r'(\w+侯)',
            r'(\w+军)', r'(\w+战)', r'(\w+役'
        ]
        
        # 提取所有术语
        all_patterns = scifi_patterns + fantasy_patterns + history_patterns
        for pattern in all_patterns:
            matches = re.findall(pattern, content)
            keywords.update(matches)
        
        # 3. 提取高频词（过滤停用词）
        stop_words = {'的', '了', '是', '在', '有', '和', '与', '或', '但', '这', '那'}
        words = re.findall(r'[\u4e00-\u9fff]{2,}', content)
        word_freq = {}
        for word in words:
            if word not in stop_words and len(word) >= 2:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # 取前20个高频词
        top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:20]
        keywords.update([w[0] for w in top_words])
        
        return list(keywords)

    def _recall_knowledge(
        self, 
        keywords: List[str], 
        genre: str
    ) -> List[Dict[str, Any]]:
        """召回相关知识

        Args:
            keywords: 关键词列表
            genre: 题材

        Returns:
            召回的知识列表
        """
        if not keywords:
            return []
        
        recalled = []
        
        # 使用知识库检索器
        if self._knowledge_retriever:
            try:
                # 构建查询
                query = " ".join(keywords[:10])  # 最多使用前10个关键词
                
                # 调用检索器
                results = self._knowledge_retriever.recall_knowledge(
                    query=query,
                    category=genre,
                    top_k=10,
                    min_score=0.5
                )
                
                # 转换为字典格式
                for result in results:
                    recalled.append({
                        "knowledge_id": result.knowledge_id,
                        "title": result.title,
                        "content": result.content[:200] + "...",  # 截取前200字
                        "category": result.category,
                        "domain": result.domain,
                        "keywords": result.keywords,
                        "score": result.score,
                        "vector_score": result.vector_score,
                        "keyword_score": result.keyword_score,
                    })
                
            except Exception as e:
                self._logger.warning(f"[{self.PLUGIN_ID}] 知识召回失败: {e}")
        
        return recalled

    def _detect_conflicts(
        self, 
        content: str, 
        recalled_knowledge: List[Dict[str, Any]], 
        genre: str
    ) -> List[KnowledgeConflict]:
        """检测知识冲突

        Args:
            content: 内容文本
            recalled_knowledge: 召回的知识列表
            genre: 题材

        Returns:
            冲突列表
        """
        conflicts = []
        
        # 如果没有召回知识，跳过冲突检测
        if not recalled_knowledge:
            self._logger.info(f"[{self.PLUGIN_ID}] 无召回知识，跳过冲突检测")
            return conflicts
        
        # 科幻题材冲突检测规则
        if genre == "scifi":
            conflicts.extend(self._detect_scifi_conflicts(content, recalled_knowledge))
        
        # 玄幻题材冲突检测规则
        elif genre == "fantasy":
            conflicts.extend(self._detect_fantasy_conflicts(content, recalled_knowledge))
        
        # 历史题材冲突检测规则
        elif genre == "history":
            conflicts.extend(self._detect_history_conflicts(content, recalled_knowledge))
        
        return conflicts

    def _detect_scifi_conflicts(
        self, 
        content: str, 
        recalled_knowledge: List[Dict[str, Any]]
    ) -> List[KnowledgeConflict]:
        """检测科幻题材冲突

        Args:
            content: 内容文本
            recalled_knowledge: 召回的知识列表

        Returns:
            冲突列表
        """
        conflicts = []
        
        # 规则1: 超光速但未提及相对论效应
        if "超光速" in content or "光速行驶" in content:
            if "相对论" not in content and "时间膨胀" not in content and "时间膨胀" not in content:
                # 查找相关知识
                relativity_knowledge = next(
                    (k for k in recalled_knowledge if "相对论" in k.get("title", "") or "时间膨胀" in k.get("title", "")),
                    None
                )
                
                if relativity_knowledge:
                    conflicts.append(KnowledgeConflict(
                        conflict_type="physics",
                        description="飞船以超光速行驶但未提及相对论时间膨胀效应",
                        severity="medium",
                        knowledge_id=relativity_knowledge["knowledge_id"],
                        knowledge_title=relativity_knowledge["title"],
                        suggestion="建议补充时间膨胀的描述，或设定特殊技术（如曲率引擎）规避该效应",
                        content_snippet=self._extract_snippet(content, "超光速")
                    ))
        
        # 规则2: 核聚变但未提及氘/氚
        if "核聚变" in content or "聚变反应" in content:
            if "氘" not in content and "氚" not in content and "氦" not in content:
                fusion_knowledge = next(
                    (k for k in recalled_knowledge if "核聚变" in k.get("title", "")),
                    None
                )
                
                if fusion_knowledge:
                    conflicts.append(KnowledgeConflict(
                        conflict_type="physics",
                        description="核聚变描述缺少燃料元素（氘/氚）说明",
                        severity="low",
                        knowledge_id=fusion_knowledge["knowledge_id"],
                        knowledge_title=fusion_knowledge["title"],
                        suggestion="建议补充核聚变燃料（氘/氚）的说明，提升科学性",
                        content_snippet=self._extract_snippet(content, "核聚变")
                    ))
        
        # 规则3: 基因编辑但未提及CRISPR或技术原理
        if "基因编辑" in content or "基因改造" in content:
            if "CRISPR" not in content and "基因剪刀" not in content and "基因编辑技术" not in content:
                gene_knowledge = next(
                    (k for k in recalled_knowledge if "基因" in k.get("title", "")),
                    None
                )
                
                if gene_knowledge:
                    conflicts.append(KnowledgeConflict(
                        conflict_type="biology",
                        description="基因编辑描述缺少技术原理说明",
                        severity="low",
                        knowledge_id=gene_knowledge["knowledge_id"],
                        knowledge_title=gene_knowledge["title"],
                        suggestion="建议补充基因编辑技术（如CRISPR-Cas9）的原理说明",
                        content_snippet=self._extract_snippet(content, "基因")
                    ))
        
        return conflicts

    def _detect_fantasy_conflicts(
        self, 
        content: str, 
        recalled_knowledge: List[Dict[str, Any]]
    ) -> List[KnowledgeConflict]:
        """检测玄幻题材冲突

        Args:
            content: 内容文本
            recalled_knowledge: 召回的知识列表

        Returns:
            冲突列表
        """
        conflicts = []
        
        # 规则1: 修仙等级混乱
        cultivation_levels = ["练气", "筑基", "金丹", "元婴", "化神", "渡劫", "大乘"]
        mentioned_levels = [lv for lv in cultivation_levels if lv in content]
        
        if len(mentioned_levels) >= 2:
            # 检查等级顺序是否正确
            for i in range(len(mentioned_levels) - 1):
                current_idx = cultivation_levels.index(mentioned_levels[i])
                next_idx = cultivation_levels.index(mentioned_levels[i + 1])
                
                if next_idx <= current_idx:
                    cultivation_knowledge = next(
                        (k for k in recalled_knowledge if "修仙" in k.get("title", "") or "境界" in k.get("title", "")),
                        None
                    )
                    
                    if cultivation_knowledge:
                        conflicts.append(KnowledgeConflict(
                            conflict_type="religion",
                            description=f"修仙境界顺序混乱：{mentioned_levels[i]} → {mentioned_levels[i+1]}",
                            severity="medium",
                            knowledge_id=cultivation_knowledge["knowledge_id"],
                            knowledge_title=cultivation_knowledge["title"],
                            suggestion="建议按照修仙境界顺序描写：练气 → 筑基 → 金丹 → 元婴 → 化神 → 渡劫 → 大乘",
                            content_snippet=self._extract_snippet(content, mentioned_levels[i])
                        ))
        
        # 规则2: 炼丹但未提及丹方
        if "炼丹" in content:
            if "丹方" not in content and "药材" not in content and "灵草" not in content:
                alchemy_knowledge = next(
                    (k for k in recalled_knowledge if "炼丹" in k.get("title", "") or "丹道" in k.get("title", "")),
                    None
                )
                
                if alchemy_knowledge:
                    conflicts.append(KnowledgeConflict(
                        conflict_type="religion",
                        description="炼丹描写缺少丹方/药材说明",
                        severity="low",
                        knowledge_id=alchemy_knowledge["knowledge_id"],
                        knowledge_title=alchemy_knowledge["title"],
                        suggestion="建议补充丹方、药材、炼丹过程等细节，增强真实感",
                        content_snippet=self._extract_snippet(content, "炼丹")
                    ))
        
        return conflicts

    def _detect_history_conflicts(
        self, 
        content: str, 
        recalled_knowledge: List[Dict[str, Any]]
    ) -> List[KnowledgeConflict]:
        """检测历史题材冲突

        Args:
            content: 内容文本
            recalled_knowledge: 召回的知识列表

        Returns:
            冲突列表
        """
        conflicts = []
        
        # 规则1: 朝代时间线冲突
        # 简化实现：检查是否有明显的历史常识错误
        # 如：唐朝出现火药武器、明朝出现蒸汽机等
        
        # 唐朝背景但出现火药武器
        if "唐" in content and ("火药" in content or "火枪" in content or "火炮" in content):
            conflicts.append(KnowledgeConflict(
                conflict_type="history",
                description="唐朝背景出现火药武器（火药发明于唐朝晚期，武器化在宋朝）",
                severity="high",
                knowledge_id="history-invention-001",
                knowledge_title="火药发明时间",
                suggestion="建议将背景调整为宋朝，或删除火药武器相关描写",
                content_snippet=self._extract_snippet(content, "火药")
            ))
        
        # 明朝背景但出现蒸汽机
        if "明" in content and "蒸汽" in content:
            conflicts.append(KnowledgeConflict(
                conflict_type="history",
                description="明朝背景出现蒸汽机（蒸汽机发明于18世纪，清朝中期）",
                severity="high",
                knowledge_id="history-invention-002",
                knowledge_title="蒸汽机发明时间",
                suggestion="建议将背景调整为清朝晚期，或删除蒸汽机相关描写",
                content_snippet=self._extract_snippet(content, "蒸汽")
            ))
        
        return conflicts

    def _extract_snippet(self, content: str, keyword: str, max_length: int = 50) -> str:
        """提取内容片段

        Args:
            content: 内容文本
            keyword: 关键词
            max_length: 最大长度

        Returns:
            内容片段
        """
        idx = content.find(keyword)
        if idx == -1:
            return ""
        
        start = max(0, idx - max_length // 2)
        end = min(len(content), idx + max_length // 2)
        
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        
        return snippet

    def _calculate_score(
        self, 
        conflicts: List[KnowledgeConflict], 
        recalled_knowledge: List[Dict[str, Any]]
    ) -> float:
        """计算知识库一致性评分

        Args:
            conflicts: 冲突列表
            recalled_knowledge: 召回的知识列表

        Returns:
            评分（0-1）
        """
        # 基础分：0.8（默认高分离）
        base_score = 0.8
        
        # 如果没有召回知识，返回基础分
        if not recalled_knowledge:
            return base_score
        
        # 根据冲突扣分
        penalty = 0.0
        for conflict in conflicts:
            penalty += self.SEVERITY_WEIGHTS.get(conflict.severity, 0.1)
        
        # 最终评分
        score = max(0.0, base_score - penalty)
        
        # 召回知识越多，评分越可信（轻微加分）
        recall_bonus = min(0.1, len(recalled_knowledge) * 0.01)
        score = min(1.0, score + recall_bonus)
        
        return round(score, 2)

    def _conflict_to_dict(self, conflict: KnowledgeConflict) -> Dict[str, Any]:
        """将冲突对象转换为字典

        Args:
            conflict: 冲突对象

        Returns:
            字典格式
        """
        return {
            "conflict_type": conflict.conflict_type,
            "description": conflict.description,
            "severity": conflict.severity,
            "knowledge_id": conflict.knowledge_id,
            "knowledge_title": conflict.knowledge_title,
            "suggestion": conflict.suggestion,
            "content_snippet": conflict.content_snippet,
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取插件统计信息

        Returns:
            统计信息字典
        """
        return {
            "plugin_id": self.PLUGIN_ID,
            "plugin_version": self.PLUGIN_VERSION,
            **self._cache_stats,
        }


# ============================================================================
# 插件注册
# ============================================================================


# 插件入口点
def create_plugin():
    """创建插件实例"""
    return KnowledgeValidatorPlugin()


# 插件元数据
PLUGIN_METADATA = {
    "id": "knowledge-validator",
    "name": "知识库验证器 V1",
    "version": "1.0.0",
    "description": "知识库一致性验证器（OpenClaw向量召回）",
    "author": "高级项目工程师",
    "plugin_type": "validator",
    "api_version": "1.0",
    "priority": 90,
    "enabled": True,
    "dependencies": [],
    "conflicts": ["knowledge-validator-v2"],
    "permissions": ["knowledge.read"],
    "min_platform_version": "6.0.0",
    "entry_class": "KnowledgeValidatorPlugin",
}
