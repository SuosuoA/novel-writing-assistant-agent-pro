"""
知识点引用策略选择器

V1.0版本
创建日期：2026-03-27

功能：
- 区分传统知识库和写作技巧库
- 传统知识库：灵活引用（隐式/显式/约束）
- 写作技巧库：强制遵循（AI必须100%遵守）
- 根据知识点类型选择引用策略

设计参考：
- 灵活联动方案 13.知识库与创作灵活联动方案✅️.md
- 知识库Schema 10.6 知识库Schema设计✅️.md
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import logging

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ReferenceType(str, Enum):
    """引用类型枚举"""
    IMPLICIT = "implicit"        # 隐式引用：融入叙事
    EXPLICIT = "explicit"        # 显式引用：直接出现
    CONSTRAINT = "constraint"    # 约束检查：题材适配
    MANDATORY = "mandatory"      # 强制遵循：写作技巧必须遵守


class KnowledgeCategory(str, Enum):
    """知识库分类枚举"""
    SCIFI = "scifi"
    XUANHUAN = "xuanhuan"
    HISTORY = "history"
    GENERAL = "general"
    WRITING_TECHNIQUE = "writing_technique"


@dataclass
class ReferenceStrategy:
    """引用策略"""
    strategy_type: ReferenceType
    guidance: str
    priority: float  # 0-1
    is_mandatory: bool  # 是否强制遵循


class ReferenceStrategyResult(BaseModel):
    """引用策略选择结果"""
    
    strategy_type: str = Field(description="引用策略类型")
    guidance: str = Field(description="引用指导")
    priority: float = Field(description="优先级")
    is_mandatory: bool = Field(description="是否强制遵循")
    knowledge_id: str = Field(description="知识点ID")
    title: str = Field(description="知识点标题")


class KnowledgeReferenceSelector:
    """
    知识点引用策略选择器
    
    核心功能：
    1. 区分传统知识库和写作技巧库
    2. 为传统知识库选择灵活引用策略（隐式/显式/约束）
    3. 为写作技巧库返回强制遵循策略
    
    使用示例：
        selector = KnowledgeReferenceSelector()
        
        # 传统知识库
        strategy = selector.select_strategy(knowledge_point, context)
        # 可能返回：implicit/explicit/constraint
        
        # 写作技巧库
        strategy = selector.select_strategy(writing_technique_point, context)
        # 必定返回：mandatory
    """
    
    # 写作技巧固定领域
    WRITING_TECHNIQUE_DOMAINS = ["narrative", "description", "rhetoric", "structure"]
    
    def __init__(self):
        """初始化选择器"""
        pass
    
    def select_strategy(
        self,
        knowledge: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ReferenceStrategyResult:
        """
        选择知识点的引用策略
        
        Args:
            knowledge: 知识点数据（字典格式）
            context: 上下文（题材、剧情、风格等）
        
        Returns:
            ReferenceStrategyResult: 引用策略结果
        """
        category = knowledge.get("category", "")
        domain = knowledge.get("domain", "")
        metadata = knowledge.get("metadata", {})
        knowledge_id = knowledge.get("knowledge_id", "")
        title = knowledge.get("title", "")
        
        # 1. 写作技巧库：强制遵循
        if category == "writing_technique":
            return self._create_mandatory_strategy(knowledge)
        
        # 2. 传统知识库：根据metadata.reference_type选择
        reference_type = metadata.get("reference_type", "implicit")
        
        if reference_type == ReferenceType.EXPLICIT.value:
            return self._create_explicit_strategy(knowledge)
        elif reference_type == ReferenceType.CONSTRAINT.value:
            return self._create_constraint_strategy(knowledge)
        else:  # implicit 或未指定
            return self._create_implicit_strategy(knowledge)
    
    def _create_mandatory_strategy(self, knowledge: Dict[str, Any]) -> ReferenceStrategyResult:
        """
        创建强制遵循策略（写作技巧）
        
        特点：
        - 策略类型：mandatory
        - 优先级：1.0（最高）
        - is_mandatory: True
        - guidance：必须遵循的写作规则
        """
        content = knowledge.get("content", "")
        
        # 提取"AI强制遵循规则"部分
        mandatory_rules = self._extract_mandatory_rules(content)
        
        return ReferenceStrategyResult(
            strategy_type=ReferenceType.MANDATORY.value,
            guidance=f"【强制遵循】{mandatory_rules}",
            priority=1.0,
            is_mandatory=True,
            knowledge_id=knowledge.get("knowledge_id", ""),
            title=knowledge.get("title", "")
        )
    
    def _create_explicit_strategy(self, knowledge: Dict[str, Any]) -> ReferenceStrategyResult:
        """
        创建显式引用策略
        
        特点：
        - 策略类型：explicit
        - 优先级：根据importance_score
        - is_mandatory: False
        - guidance：如何直接引用
        """
        metadata = knowledge.get("metadata", {})
        priority = metadata.get("priority", 0.5)
        content = knowledge.get("content", "")
        
        return ReferenceStrategyResult(
            strategy_type=ReferenceType.EXPLICIT.value,
            guidance=f"可直接引用：{content[:200]}...",
            priority=priority,
            is_mandatory=False,
            knowledge_id=knowledge.get("knowledge_id", ""),
            title=knowledge.get("title", "")
        )
    
    def _create_implicit_strategy(self, knowledge: Dict[str, Any]) -> ReferenceStrategyResult:
        """
        创建隐式引用策略
        
        特点：
        - 策略类型：implicit
        - 优先级：根据importance_score × 0.8
        - is_mandatory: False
        - guidance：如何融入叙事
        """
        metadata = knowledge.get("metadata", {})
        priority = metadata.get("priority", 0.5) * 0.8
        content = knowledge.get("content", "")
        title = knowledge.get("title", "")
        
        return ReferenceStrategyResult(
            strategy_type=ReferenceType.IMPLICIT.value,
            guidance=f"可融入叙事：{title} - {content[:150]}...",
            priority=priority,
            is_mandatory=False,
            knowledge_id=knowledge.get("knowledge_id", ""),
            title=title
        )
    
    def _create_constraint_strategy(self, knowledge: Dict[str, Any]) -> ReferenceStrategyResult:
        """
        创建约束检查策略
        
        特点：
        - 策略类型：constraint
        - 优先级：1.0
        - is_mandatory: True（约束必须遵守）
        - guidance：不得违反的规则
        """
        content = knowledge.get("content", "")
        title = knowledge.get("title", "")
        
        return ReferenceStrategyResult(
            strategy_type=ReferenceType.CONSTRAINT.value,
            guidance=f"【约束】不得违反：{title} - {content[:150]}...",
            priority=1.0,
            is_mandatory=True,
            knowledge_id=knowledge.get("knowledge_id", ""),
            title=title
        )
    
    def _extract_mandatory_rules(self, content: str) -> str:
        """从知识点内容中提取AI强制遵循规则"""
        # 查找"AI强制遵循规则"部分
        marker = "**AI强制遵循规则**："
        if marker in content:
            start_idx = content.find(marker) + len(marker)
            # 提取到下一个段落结束（双换行）
            end_idx = content.find("\n\n", start_idx)
            if end_idx == -1:
                end_idx = len(content)
            rules = content[start_idx:end_idx].strip()
            return rules
        return content[:300]  # 如果没有标记，返回前300字符
    
    def batch_select_strategies(
        self,
        knowledge_list: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[ReferenceStrategyResult]:
        """
        批量选择引用策略
        
        Args:
            knowledge_list: 知识点列表
            context: 上下文
        
        Returns:
            List[ReferenceStrategyResult]: 引用策略列表
        """
        results = []
        for knowledge in knowledge_list:
            strategy = self.select_strategy(knowledge, context)
            results.append(strategy)
        
        # 按优先级排序
        results.sort(key=lambda x: x.priority, reverse=True)
        
        return results
    
    def filter_mandatory_strategies(
        self,
        strategies: List[ReferenceStrategyResult]
    ) -> List[ReferenceStrategyResult]:
        """
        过滤出强制遵循的策略（用于提示词构建）
        
        Args:
            strategies: 策略列表
        
        Returns:
            List[ReferenceStrategyResult]: 强制遵循的策略列表
        """
        return [s for s in strategies if s.is_mandatory]
    
    def filter_flexible_strategies(
        self,
        strategies: List[ReferenceStrategyResult]
    ) -> List[ReferenceStrategyResult]:
        """
        过滤出灵活引用的策略（用于上下文构建）
        
        Args:
            strategies: 策略列表
        
        Returns:
            List[ReferenceStrategyResult]: 灵活引用的策略列表
        """
        return [s for s in strategies if not s.is_mandatory]


# ============================================================================
# 便捷函数
# ============================================================================

def get_reference_selector() -> KnowledgeReferenceSelector:
    """获取引用策略选择器实例"""
    return KnowledgeReferenceSelector()
