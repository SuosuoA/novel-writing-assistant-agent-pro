"""
专家模式数据模型

定义专家评估和优化建议的数据结构
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
from datetime import datetime
import json


@dataclass
class ExpertEvaluation:
    """
    专家评估结果
    
    九维度评分体系:
    - 世界观(12%): 世界观一致性检查
    - 人设(19%): 人物性格、对话一致性
    - 大纲(13%): 情节推进符合大纲
    - 风格(19%): 写作风格匹配度
    - 知识库(8%): 知识点引用质量
    - 写作技巧(8%): 写作技巧应用
    - 字数(8%): 字数达标率
    - 上下文衔接(8%): 与前文衔接自然度
    - AI感(5%): 文本自然度（越低越好）
    """
    
    # 总分
    total_score: float  # 0.0 - 1.0
    
    # 各维度得分
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    
    # 详细分析
    analysis: Dict[str, str] = field(default_factory=dict)
    
    # 问题识别
    issues: List[str] = field(default_factory=list)
    
    # 优势识别
    strengths: List[str] = field(default_factory=list)
    
    # 元数据
    chapter_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "total_score": self.total_score,
            "dimension_scores": self.dimension_scores,
            "analysis": self.analysis,
            "issues": self.issues,
            "strengths": self.strengths,
            "chapter_id": self.chapter_id,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExpertEvaluation":
        """从字典创建"""
        return cls(
            total_score=data.get("total_score", 0.0),
            dimension_scores=data.get("dimension_scores", {}),
            analysis=data.get("analysis", {}),
            issues=data.get("issues", []),
            strengths=data.get("strengths", []),
            chapter_id=data.get("chapter_id"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )
    
    def is_passed(self, threshold: float = 0.8) -> bool:
        """判断是否通过质量阈值"""
        return self.total_score >= threshold
    
    def get_weak_dimensions(self, threshold: float = 0.7) -> List[str]:
        """获取低分维度"""
        return [
            dim for dim, score in self.dimension_scores.items()
            if score < threshold
        ]
    
    def get_strong_dimensions(self, threshold: float = 0.8) -> List[str]:
        """获取高分维度"""
        return [
            dim for dim, score in self.dimension_scores.items()
            if score >= threshold
        ]


@dataclass
class OptimizationSuggestion:
    """
    优化建议
    
    包含总体建议、各维度建议和具体修改示例
    """
    
    # 总体建议
    overall_suggestion: str
    
    # 各维度优化建议
    dimension_suggestions: Dict[str, str] = field(default_factory=dict)
    
    # 具体修改示例
    examples: List[Dict[str, str]] = field(default_factory=list)
    
    # 优先级: "high" / "medium" / "low"
    priority: str = "medium"
    
    # 元数据
    chapter_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "overall_suggestion": self.overall_suggestion,
            "dimension_suggestions": self.dimension_suggestions,
            "examples": self.examples,
            "priority": self.priority,
            "chapter_id": self.chapter_id,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptimizationSuggestion":
        """从字典创建"""
        return cls(
            overall_suggestion=data.get("overall_suggestion", ""),
            dimension_suggestions=data.get("dimension_suggestions", {}),
            examples=data.get("examples", []),
            priority=data.get("priority", "medium"),
            chapter_id=data.get("chapter_id"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )
    
    def get_high_priority_suggestions(self) -> Dict[str, str]:
        """获取高优先级建议"""
        return {
            dim: suggestion
            for dim, suggestion in self.dimension_suggestions.items()
            if self.priority == "high"
        }


@dataclass
class UserFeedback:
    """
    用户反馈
    
    用于记录用户对优化建议的采纳情况
    """
    
    chapter_id: str
    
    # 用户采纳的建议
    accepted_suggestions: List[str] = field(default_factory=list)
    
    # 用户拒绝的建议
    rejected_suggestions: List[str] = field(default_factory=list)
    
    # 用户评分（1-5）
    user_rating: float = 3.0
    
    # 用户评论
    comment: str = ""
    
    # 时间戳
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "chapter_id": self.chapter_id,
            "accepted_suggestions": self.accepted_suggestions,
            "rejected_suggestions": self.rejected_suggestions,
            "user_rating": self.user_rating,
            "comment": self.comment,
            "timestamp": self.timestamp
        }


@dataclass
class ExpertConfig:
    """
    专家配置
    
    从config.yaml加载的配置
    """
    
    # 质量控制
    quality_threshold: float = 0.8
    max_iterations: int = 5
    min_score: float = 0.0
    
    # 强制检查
    chapter_end_marker_enabled: bool = True
    chapter_end_marker_patterns: List[str] = field(default_factory=lambda: [
        "【本章完】", "[本章完]", "（本章完）", "(本章完)", "本章完"
    ])
    chapter_end_marker_range: int = 100
    
    # 记忆系统
    memory_enabled: bool = True
    memory_l1_ttl: int = 3600
    
    # 本地模型
    local_model_enabled: bool = True
    
    @classmethod
    def from_yaml(cls, config_dict: Dict[str, Any]) -> "ExpertConfig":
        """从YAML配置创建"""
        quality = config_dict.get("quality", {})
        mandatory = config_dict.get("mandatory_checks", {}).get("chapter_end_marker", {})
        memory = config_dict.get("memory", {})
        local_model = config_dict.get("local_model", {})
        
        return cls(
            quality_threshold=quality.get("threshold", 0.8),
            max_iterations=quality.get("max_iterations", 5),
            min_score=quality.get("min_score", 0.0),
            chapter_end_marker_enabled=mandatory.get("enabled", True),
            chapter_end_marker_patterns=mandatory.get("patterns", [
                "【本章完】", "[本章完]", "（本章完）", "(本章完)", "本章完"
            ]),
            chapter_end_marker_range=mandatory.get("check_range", 100),
            memory_enabled=memory.get("enabled", True),
            memory_l1_ttl=memory.get("l1_ttl", 3600),
            local_model_enabled=local_model.get("enabled", True)
        )
