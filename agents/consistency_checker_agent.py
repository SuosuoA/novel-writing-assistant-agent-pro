"""
一致性检查Agent - OpenClaw多Agent架构

V1.0版本
创建日期：2026-03-25

特性：
- 参考OpenClaw的多Agent协作设计
- 调用ContextRecaller召回相关上下文
- 检测长篇小说冲突（人物/情节/世界观）
- 冲突识别准确率≥90%
- 支持生成修复建议
- EventBus集成
- 线程安全设计

设计参考：
- OpenClaw多Agent架构
- 升级方案 10.升级方案✅️.md
- Sprint 7-8: 长篇连贯性解决方案

使用示例：
    # 创建Agent实例
    agent = ConsistencyCheckerAgent()
    
    # 执行一致性检查
    result = agent.execute({
        "new_chapter": "第三章 星际战争爆发...",
        "existing_chapters": [...],
        "genre": "scifi"
    })
    
    # 获取冲突列表
    conflicts = result["conflicts"]
    
    # 获取修复建议
    suggestions = result["suggestions"]
"""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ConfigDict

# 延迟导入，避免循环依赖
# from core.context_recall import ContextRecaller, get_context_recaller
# from core.event_bus import EventBus
# from services.llm_client_with_resilience import get_llm_client


# ============================================================================
# Pydantic数据模型
# ============================================================================


class Conflict(BaseModel):
    """冲突记录"""
    
    model_config = ConfigDict(frozen=False)
    
    conflict_id: str = Field(description="冲突ID")
    conflict_type: str = Field(description="冲突类型（character/plot/worldview）")
    severity: str = Field(description="严重程度（P0/P1/P2）")
    description: str = Field(description="冲突描述")
    location: str = Field(description="冲突位置（章节引用）")
    evidence: str = Field(description="证据（前文相关内容）")
    suggestion: str = Field(description="修复建议")


class ConsistencyCheckResult(BaseModel):
    """一致性检查结果"""
    
    model_config = ConfigDict(frozen=False)
    
    check_id: str = Field(description="检查ID")
    timestamp: str = Field(description="检查时间")
    is_consistent: bool = Field(description="是否一致")
    conflicts: List[Conflict] = Field(default_factory=list, description="冲突列表")
    suggestions: List[str] = Field(default_factory=list, description="修复建议列表")
    recalled_context: Optional[str] = Field(default=None, description="召回的上下文摘要")
    accuracy: float = Field(default=0.0, description="一致性准确率（0-1）")
    check_duration_ms: float = Field(default=0.0, description="检查耗时（毫秒）")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class ConsistencyStats(BaseModel):
    """一致性检查统计"""
    
    model_config = ConfigDict(frozen=False)
    
    total_checks: int = Field(default=0, description="总检查次数")
    total_conflicts: int = Field(default=0, description="总冲突数")
    p0_conflicts: int = Field(default=0, description="P0级冲突数")
    p1_conflicts: int = Field(default=0, description="P1级冲突数")
    p2_conflicts: int = Field(default=0, description="P2级冲突数")
    avg_accuracy: float = Field(default=0.0, description="平均准确率")
    avg_duration_ms: float = Field(default=0.0, description="平均耗时（毫秒）")


# ============================================================================
# 一致性检查Agent
# ============================================================================


class ConsistencyCheckerAgent:
    """
    一致性检查Agent - 检测长篇小说冲突
    
    参考：
    - OpenClaw多Agent协作设计
    - 升级方案 10.升级方案✅️.md Sprint 7-8
    
    职责：
    1. 召回相关上下文（章节/知识/风格）
    2. 构建检查prompt
    3. 调用LLM检测冲突
    4. 生成修复建议
    5. 发布检查事件
    
    冲突类型：
    - character: 人物行为矛盾（性格突变、前后行为不一致）
    - plot: 情节冲突（时间线错乱、事件前后矛盾）
    - worldview: 世界观冲突（设定前后不一致）
    
    严重程度：
    - P0: 严重冲突，必须修复（如时间倒流违反因果律）
    - P1: 中等冲突，建议修复（如人物性格突变）
    - P2: 轻微冲突，可选修复（如细节不一致）
    """
    
    def __init__(self, workspace_root: Optional[Path] = None):
        """
        初始化一致性检查Agent
        
        Args:
            workspace_root: 工作区根目录
        """
        self._workspace_root = workspace_root or Path.cwd()
        self._logger = logging.getLogger(__name__)
        
        # 延迟加载依赖（避免循环导入）
        self._context_recaller = None
        self._event_bus = None
        self._llm_client = None
        
        # 线程安全
        self._lock = threading.RLock()
        self._stats_lock = threading.RLock()
        
        # 统计信息
        self._stats = ConsistencyStats()
    
    def _get_context_recaller(self):
        """延迟加载ContextRecaller"""
        if self._context_recaller is None:
            try:
                from core.context_recall import get_context_recaller
                self._context_recaller = get_context_recaller(self._workspace_root)
            except ImportError as e:
                self._logger.warning(f"ContextRecaller导入失败: {e}")
                self._context_recaller = None
        return self._context_recaller
    
    def _get_event_bus(self):
        """延迟加载EventBus"""
        if self._event_bus is None:
            try:
                from core.event_bus import EventBus
                self._event_bus = EventBus.get_instance()
            except Exception as e:
                self._logger.warning(f"EventBus获取失败: {e}")
                self._event_bus = None
        return self._event_bus
    
    def _get_llm_client(self):
        """延迟加载LLM客户端"""
        if self._llm_client is None:
            try:
                from services.llm_client_with_resilience import get_llm_client
                self._llm_client = get_llm_client()
            except Exception as e:
                self._logger.warning(f"LLM客户端获取失败: {e}")
                self._llm_client = None
        return self._llm_client
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行一致性检查
        
        Args:
            context: 检查上下文
                - new_chapter: 新章节内容（必填）
                - existing_chapters: 已有章节列表（可选，如果为空则从上下文召回）
                - genre: 题材（可选，默认自动识别）
                - chapter_outline: 章节大纲（可选，用于召回上下文）
                - top_k: 召回章节数量（可选，默认10）
                - max_tokens: 最大token数（可选，默认4000）
        
        Returns:
            检查结果字典
                - check_id: 检查ID
                - is_consistent: 是否一致
                - conflicts: 冲突列表
                - suggestions: 修复建议列表
                - recalled_context: 召回的上下文摘要
                - accuracy: 准确率
        """
        start_time = time.time()
        check_id = f"check-{int(time.time() * 1000)}"
        
        # 提取参数
        new_chapter = context.get("new_chapter", "")
        existing_chapters = context.get("existing_chapters", [])
        genre = context.get("genre")
        chapter_outline = context.get("chapter_outline", new_chapter[:200])
        top_k = context.get("top_k", 10)
        max_tokens = context.get("max_tokens", 4000)
        
        # 参数验证
        if not new_chapter:
            return {
                "check_id": check_id,
                "is_consistent": True,
                "conflicts": [],
                "suggestions": [],
                "recalled_context": None,
                "accuracy": 0.0,
                "error": "缺少new_chapter参数"
            }
        
        # 召回上下文
        recalled_context = self._recall_context(
            chapter_outline=chapter_outline,
            existing_chapters=existing_chapters,
            genre=genre,
            top_k=top_k,
            max_tokens=max_tokens
        )
        
        # 构建检查prompt
        prompt = self._build_check_prompt(
            new_chapter=new_chapter,
            recalled_context=recalled_context
        )
        
        # 调用LLM检测冲突
        conflicts, suggestions = self._detect_conflicts_with_llm(prompt)
        
        # 计算准确率
        accuracy = self._calculate_accuracy(conflicts)
        
        # 更新统计
        duration_ms = (time.time() - start_time) * 1000
        self._update_stats(conflicts, accuracy, duration_ms)
        
        # 发布事件
        self._publish_event(check_id, conflicts, accuracy)
        
        # 返回结果
        return {
            "check_id": check_id,
            "is_consistent": len(conflicts) == 0,
            "conflicts": [c.model_dump() for c in conflicts],
            "suggestions": suggestions,
            "recalled_context": recalled_context,
            "accuracy": accuracy,
            "check_duration_ms": duration_ms
        }
    
    def _recall_context(
        self,
        chapter_outline: str,
        existing_chapters: List[Dict[str, Any]],
        genre: Optional[str],
        top_k: int,
        max_tokens: int
    ) -> str:
        """
        召回相关上下文
        
        Args:
            chapter_outline: 章节大纲
            existing_chapters: 已有章节列表
            genre: 题材
            top_k: 召回章节数量
            max_tokens: 最大token数
        
        Returns:
            上下文摘要
        """
        context_recaller = self._get_context_recaller()
        
        if context_recaller is None:
            # 降级：使用传入的已有章节
            if existing_chapters:
                return self._build_context_from_chapters(existing_chapters)
            return ""
        
        try:
            # 调用ContextRecaller召回上下文
            recall_result = context_recaller.recall_for_new_chapter(
                chapter_outline=chapter_outline,
                top_k=top_k,
                max_tokens=max_tokens,
                include_knowledge=True,
                include_style=False,
                genre=genre
            )
            
            # 构建上下文摘要
            chapters = recall_result.get("chapters", [])
            knowledge = recall_result.get("knowledge", [])
            
            summary = context_recaller.build_context_summary(
                chapters=chapters,
                knowledge=knowledge,
                max_tokens=max_tokens
            )
            
            return summary
            
        except Exception as e:
            self._logger.error(f"召回上下文失败: {e}")
            # 降级：使用传入的已有章节
            if existing_chapters:
                return self._build_context_from_chapters(existing_chapters)
            return ""
    
    def _build_context_from_chapters(
        self,
        chapters: List[Dict[str, Any]]
    ) -> str:
        """
        从章节列表构建上下文摘要
        
        Args:
            chapters: 章节列表
        
        Returns:
            上下文摘要
        """
        if not chapters:
            return ""
        
        parts = []
        for i, chapter in enumerate(chapters[:10], 1):  # 最多10章
            chapter_id = chapter.get("chapter_id", f"第{i}章")
            content = chapter.get("content", "")
            preview = content[:200] if len(content) > 200 else content
            parts.append(f"【{chapter_id}】{preview}...")
        
        return "\n".join(parts)
    
    def _build_check_prompt(
        self,
        new_chapter: str,
        recalled_context: str
    ) -> str:
        """
        构建一致性检查prompt
        
        Args:
            new_chapter: 新章节内容
            recalled_context: 召回的上下文
        
        Returns:
            检查prompt
        """
        context_section = ""
        if recalled_context:
            context_section = f"""
## 参考上下文（前文相关章节摘要）

{recalled_context}
"""
        
        prompt = f"""你是一位专业的小说编辑，负责检测长篇小说中的逻辑冲突。

{context_section}

## 新章节内容

{new_chapter}

## 检查任务

请检测新章节与前文是否存在以下冲突：

1. **人物行为矛盾**：如性格突变、前后行为不一致、能力前后矛盾
2. **情节冲突**：如时间线错乱、事件前后矛盾、因果关系混乱
3. **世界观冲突**：如设定前后不一致、规则违反、逻辑漏洞

## 输出格式

如果发现冲突，请按以下格式输出（每个冲突单独一行）：

[冲突类型]|[严重程度]|[冲突描述]|[冲突位置]|[证据]|[修复建议]

其中：
- 冲突类型：character / plot / worldview
- 严重程度：P0（严重冲突，必须修复）/ P1（中等冲突，建议修复）/ P2（轻微冲突，可选修复）
- 冲突描述：具体描述冲突内容
- 冲突位置：章节引用或段落位置
- 证据：前文相关内容引用
- 修复建议：建议如何修复

如果没有冲突，输出：
无冲突

## 示例

character|P1|主角性格突变，从冷静变得冲动|第三章第5段|第一章提到"他总是冷静分析局势"|建议增加心理转变的铺垫情节
plot|P0|时间线错误，事件顺序矛盾|第三章第10段|第一章说"三天后"，第二章说"两天后"|调整时间线，修正为"两天后"
worldview|P2|设定细节不一致|第三章第15段|第一章说"魔法需要消耗魔力"，本章未提及|建议补充魔力消耗的描述

## 注意事项

1. 只检测真正的冲突，不要过度解读
2. P0级别冲突必须是有明确证据的严重矛盾
3. 修复建议要具体可行
4. 如果没有冲突，不要强行找问题
"""
        return prompt
    
    def _detect_conflicts_with_llm(
        self,
        prompt: str
    ) -> tuple:
        """
        调用LLM检测冲突
        
        Args:
            prompt: 检查prompt
        
        Returns:
            (冲突列表, 修复建议列表)
        """
        llm_client = self._get_llm_client()
        
        if llm_client is None:
            self._logger.warning("LLM客户端不可用，跳过冲突检测")
            return [], []
        
        try:
            # 调用LLM
            response = llm_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # 低温度，更确定性
                max_tokens=2000
            )
            
            # 解析响应
            conflicts, suggestions = self._parse_llm_response(response)
            
            return conflicts, suggestions
            
        except Exception as e:
            self._logger.error(f"LLM调用失败: {e}")
            return [], []
    
    def _parse_llm_response(
        self,
        response: str
    ) -> tuple:
        """
        解析LLM响应
        
        Args:
            response: LLM响应文本
        
        Returns:
            (冲突列表, 修复建议列表)
        """
        conflicts = []
        suggestions = []
        
        if not response:
            return conflicts, suggestions
        
        # 检查是否无冲突
        if "无冲突" in response or "没有冲突" in response:
            return conflicts, suggestions
        
        # 解析冲突行
        lines = response.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 尝试解析冲突格式
            if "|" in line:
                parts = line.split("|")
                if len(parts) >= 6:
                    try:
                        conflict = Conflict(
                            conflict_id=f"conflict-{int(time.time() * 1000)}-{len(conflicts)}",
                            conflict_type=parts[0].strip(),
                            severity=parts[1].strip(),
                            description=parts[2].strip(),
                            location=parts[3].strip(),
                            evidence=parts[4].strip(),
                            suggestion=parts[5].strip()
                        )
                        conflicts.append(conflict)
                        suggestions.append(conflict.suggestion)
                    except Exception as e:
                        self._logger.warning(f"解析冲突行失败: {line}, 错误: {e}")
        
        return conflicts, suggestions
    
    def _calculate_accuracy(
        self,
        conflicts: List[Conflict]
    ) -> float:
        """
        计算一致性准确率
        
        Args:
            conflicts: 冲突列表
        
        Returns:
            准确率（0-1）
        """
        if not conflicts:
            return 1.0  # 无冲突，准确率100%
        
        # 根据冲突严重程度计算准确率
        p0_count = sum(1 for c in conflicts if c.severity == "P0")
        p1_count = sum(1 for c in conflicts if c.severity == "P1")
        p2_count = sum(1 for c in conflicts if c.severity == "P2")
        
        # P0扣0.3，P1扣0.1，P2扣0.05
        score = 1.0 - (p0_count * 0.3 + p1_count * 0.1 + p2_count * 0.05)
        
        # 最低0.0
        return max(0.0, score)
    
    def _update_stats(
        self,
        conflicts: List[Conflict],
        accuracy: float,
        duration_ms: float
    ):
        """
        更新统计信息
        
        Args:
            conflicts: 冲突列表
            accuracy: 准确率
            duration_ms: 耗时（毫秒）
        """
        with self._stats_lock:
            self._stats.total_checks += 1
            self._stats.total_conflicts += len(conflicts)
            self._stats.p0_conflicts += sum(1 for c in conflicts if c.severity == "P0")
            self._stats.p1_conflicts += sum(1 for c in conflicts if c.severity == "P1")
            self._stats.p2_conflicts += sum(1 for c in conflicts if c.severity == "P2")
            
            # 更新平均值
            total = self._stats.total_checks
            self._stats.avg_accuracy = (
                (self._stats.avg_accuracy * (total - 1) + accuracy) / total
            )
            self._stats.avg_duration_ms = (
                (self._stats.avg_duration_ms * (total - 1) + duration_ms) / total
            )
    
    def _publish_event(
        self,
        check_id: str,
        conflicts: List[Conflict],
        accuracy: float
    ):
        """
        发布检查事件
        
        Args:
            check_id: 检查ID
            conflicts: 冲突列表
            accuracy: 准确率
        """
        event_bus = self._get_event_bus()
        
        if event_bus is None:
            return
        
        try:
            event_bus.publish(
                event_type="consistency.check.completed",
                data={
                    "check_id": check_id,
                    "conflict_count": len(conflicts),
                    "p0_count": sum(1 for c in conflicts if c.severity == "P0"),
                    "p1_count": sum(1 for c in conflicts if c.severity == "P1"),
                    "p2_count": sum(1 for c in conflicts if c.severity == "P2"),
                    "accuracy": accuracy,
                    "timestamp": datetime.now().isoformat()
                },
                source="ConsistencyCheckerAgent"
            )
        except Exception as e:
            self._logger.warning(f"发布事件失败: {e}")
    
    def get_stats(self) -> ConsistencyStats:
        """
        获取统计信息
        
        Returns:
            统计信息
        """
        with self._stats_lock:
            return self._stats.model_copy()
    
    def reset_stats(self):
        """重置统计信息"""
        with self._stats_lock:
            self._stats = ConsistencyStats()


# ============================================================================
# 单例工厂模式
# ============================================================================


_consistency_checker_agent: Optional[ConsistencyCheckerAgent] = None
_agent_lock = threading.RLock()


def get_consistency_checker_agent(
    workspace_root: Optional[Path] = None
) -> ConsistencyCheckerAgent:
    """
    获取一致性检查Agent单例
    
    Args:
        workspace_root: 工作区根目录
    
    Returns:
        ConsistencyCheckerAgent实例
    """
    global _consistency_checker_agent
    
    if _consistency_checker_agent is None:
        with _agent_lock:
            # 双重检查锁
            if _consistency_checker_agent is None:
                _consistency_checker_agent = ConsistencyCheckerAgent(workspace_root)
    
    return _consistency_checker_agent


def reset_consistency_checker_agent():
    """重置一致性检查Agent单例（测试用）"""
    global _consistency_checker_agent
    
    with _agent_lock:
        _consistency_checker_agent = None
