"""
数据模型定义 - Pydantic v2模型

V1.2版本（最终修订版）
创建日期：2026-03-21
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class Event(BaseModel):
    """事件模型"""
    model_config = ConfigDict(frozen=False)
    
    type: str = Field(..., description="事件类型")
    data: Any = Field(None, description="事件数据")
    source: Optional[str] = Field(None, description="事件来源")
    timestamp: Optional[float] = Field(None, description="事件时间戳")
    event_id: Optional[str] = Field(None, description="事件ID")


class HandlerInfo(BaseModel):
    """处理器信息"""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(..., description="处理器ID")
    handler: Any = Field(..., description="处理器函数")
    priority: int = Field(20, description="优先级（数值越小越高）")
    is_async: bool = Field(False, description="是否异步执行")
    timeout: float = Field(30.0, description="超时时间（秒）")


class PluginMetadata(BaseModel):
    """插件元数据"""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(..., description="插件ID")
    name: str = Field(..., description="插件名称")
    version: str = Field(..., description="版本号")
    description: str = Field("", description="描述")
    author: str = Field("", description="作者")
    plugin_type: str = Field("TOOL", description="插件类型")
    api_version: str = Field("1.0", description="API版本")
    priority: int = Field(50, description="优先级")
    enabled: bool = Field(True, description="是否启用")
    dependencies: List[str] = Field(default_factory=list, description="依赖")
    conflicts: List[str] = Field(default_factory=list, description="冲突")
    permissions: List[str] = Field(default_factory=list, description="权限")
    min_platform_version: str = Field("1.0.0", description="最低平台版本")


class PluginInfo(BaseModel):
    """插件信息"""
    model_config = ConfigDict(frozen=False)
    
    metadata: PluginMetadata = Field(..., description="插件元数据")
    state: str = Field("LOADED", description="插件状态")
    instance: Optional[Any] = Field(None, description="插件实例")
    slot: Optional[str] = Field(None, description="插槽ID")
    error_message: Optional[str] = Field(None, description="错误信息")
    load_time: Optional[datetime] = Field(None, description="加载时间")
    load_count: int = Field(0, description="加载次数")
    error_count: int = Field(0, description="错误次数")


class ValidationScores(BaseModel):
    """验证评分"""
    model_config = ConfigDict(frozen=False)
    
    word_count_score: float = Field(0.0, ge=0, le=1, description="字数评分")
    outline_score: float = Field(0.0, ge=0, le=1, description="大纲评分")
    style_score: float = Field(0.0, ge=0, le=1, description="风格评分")
    character_score: float = Field(0.0, ge=0, le=1, description="人设评分")
    worldview_score: float = Field(0.0, ge=0, le=1, description="世界观评分")
    naturalness_score: float = Field(0.0, ge=0, le=1, description="自然度评分")
    total_score: float = Field(0.0, ge=0, le=1, description="总分")
    has_chapter_end: bool = Field(False, description="是否包含章节结束标记")
    
    def calculate_total(self) -> float:
        """计算总分（6维度加权）"""
        self.total_score = (
            self.word_count_score * 0.10 +
            self.outline_score * 0.15 +
            self.style_score * 0.25 +
            self.character_score * 0.25 +
            self.worldview_score * 0.20 +
            self.naturalness_score * 0.05
        )
        return self.total_score


class GenerationRequest(BaseModel):
    """生成请求"""
    model_config = ConfigDict(frozen=False)
    
    request_id: str = Field(..., description="请求ID")
    title: str = Field(..., description="章节标题")
    outline: str = Field(..., description="章节大纲")
    word_count: int = Field(2000, ge=500, le=10000, description="目标字数")
    max_iterations: int = Field(5, ge=1, le=10, description="最大迭代次数")
    context_chapters: int = Field(5, ge=0, le=10, description="上下文章节数")
    style_profile: Optional[Dict[str, Any]] = Field(None, description="风格配置")
    character_profiles: Optional[Dict[str, Any]] = Field(None, description="人物配置")
    worldview_config: Optional[Dict[str, Any]] = Field(None, description="世界观配置")


class GenerationResult(BaseModel):
    """生成结果"""
    model_config = ConfigDict(frozen=False)
    
    request_id: str = Field(..., description="请求ID")
    content: str = Field(..., description="生成内容")
    word_count: int = Field(0, description="实际字数")
    iteration_count: int = Field(0, description="迭代次数")
    validation_scores: Optional[ValidationScores] = Field(None, description="验证评分")
    error: Optional[str] = Field(None, description="错误信息")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")


class PluginEvent(BaseModel):
    """插件事件"""
    model_config = ConfigDict(frozen=False)
    
    event_type: str = Field(..., description="事件类型")
    plugin_id: str = Field(..., description="插件ID")
    data: Dict[str, Any] = Field(default_factory=dict, description="事件数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
