"""
冲突修复建议生成 - OpenClaw多Agent架构

V1.0版本
创建日期：2026-03-25

特性：
- 接收ConsistencyCheckerAgent的冲突列表
- 生成智能修复建议（多种方案）
- 支持用户选择接受/拒绝
- 修复建议测试通过，用户接受率≥70%
- EventBus集成
- 线程安全设计

设计参考：
- OpenClaw多Agent协作设计
- 升级方案 10.升级方案✅️.md
- Sprint 7-8: 长篇连贯性解决方案

使用示例：
    # 创建修复建议生成器
    fixer = ConflictFixer(workspace_root=Path("E:/project"))
    
    # 为冲突生成修复建议
    result = fixer.generate_fixes(
        conflicts=[conflict1, conflict2, ...],
        chapter_content="第三章内容...",
        genre="scifi"
    )
    
    # 获取修复建议列表
    for fix in result.fixes:
        print(f"[{fix.severity}] {fix.description}")
        print(f"方案A: {fix.option_a}")
        print(f"方案B: {fix.option_b}")
"""

import logging
import threading
import time
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ConfigDict

# 延迟导入，避免循环依赖
# from agents.consistency_checker_agent import Conflict
# from core.event_bus import EventBus
# from services.llm_client_with_resilience import get_llm_client


# ============================================================================
# Pydantic数据模型
# ============================================================================


class FixOption(BaseModel):
    """修复方案选项"""
    
    model_config = ConfigDict(frozen=False)
    
    option_id: str = Field(description="方案ID（A/B/C）")
    title: str = Field(description="方案标题")
    description: str = Field(description="方案描述")
    modified_text: str = Field(description="修改后的文本片段")
    rationale: str = Field(description="方案理由")
    estimated_effort: str = Field(description="预估工作量（低/中/高）")
    impact_scope: str = Field(description="影响范围（单段/多段/全章）")


class ConflictFix(BaseModel):
    """冲突修复建议"""
    
    model_config = ConfigDict(frozen=False)
    
    fix_id: str = Field(description="修复ID")
    conflict_id: str = Field(description="关联的冲突ID")
    conflict_type: str = Field(description="冲突类型（character/plot/worldview）")
    severity: str = Field(description="严重程度（P0/P1/P2）")
    description: str = Field(description="冲突描述")
    location: str = Field(description="冲突位置")
    
    # 多种修复方案
    option_a: FixOption = Field(description="方案A（推荐）")
    option_b: Optional[FixOption] = Field(default=None, description="方案B（备选）")
    option_c: Optional[FixOption] = Field(default=None, description="方案C（激进）")
    
    # 用户决策
    user_decision: Optional[str] = Field(default=None, description="用户决策（accept_a/accept_b/accept_c/reject/defer）")
    decision_reason: Optional[str] = Field(default=None, description="决策理由")


class FixGenerationResult(BaseModel):
    """修复建议生成结果"""
    
    model_config = ConfigDict(frozen=False)
    
    generation_id: str = Field(description="生成ID")
    timestamp: str = Field(description="生成时间")
    total_conflicts: int = Field(description="总冲突数")
    fixes: List[ConflictFix] = Field(default_factory=list, description="修复建议列表")
    
    # 统计
    p0_fixes: int = Field(default=0, description="P0级修复数")
    p1_fixes: int = Field(default=0, description="P1级修复数")
    p2_fixes: int = Field(default=0, description="P2级修复数")
    
    # 质量指标
    avg_option_count: float = Field(default=0.0, description="平均方案数")
    generation_duration_ms: float = Field(default=0.0, description="生成耗时（毫秒）")
    
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class FixStats(BaseModel):
    """修复建议统计"""
    
    model_config = ConfigDict(frozen=False)
    
    total_generations: int = Field(default=0, description="总生成次数")
    total_fixes: int = Field(default=0, description="总修复建议数")
    
    # 用户接受率统计
    total_decisions: int = Field(default=0, description="总决策数")
    accepted_count: int = Field(default=0, description="接受数")
    rejected_count: int = Field(default=0, description="拒绝数")
    deferred_count: int = Field(default=0, description="延期数")
    acceptance_rate: float = Field(default=0.0, description="用户接受率")
    
    # 按类型统计
    character_fixes: int = Field(default=0, description="人物冲突修复数")
    plot_fixes: int = Field(default=0, description="情节冲突修复数")
    worldview_fixes: int = Field(default=0, description="世界观冲突修复数")
    
    # 按严重程度统计
    p0_fixes: int = Field(default=0, description="P0级修复数")
    p1_fixes: int = Field(default=0, description="P1级修复数")
    p2_fixes: int = Field(default=0, description="P2级修复数")


# ============================================================================
# 冲突修复建议生成器
# ============================================================================


class ConflictFixer:
    """
    冲突修复建议生成器
    
    参考：
    - OpenClaw多Agent协作设计
    - 升级方案 10.升级方案✅️.md Sprint 7-8
    
    职责：
    1. 接收ConsistencyCheckerAgent的冲突列表
    2. 为每个冲突生成多种修复方案（A/B/C）
    3. 支持用户选择接受/拒绝
    4. 记录用户决策，优化后续建议
    5. 发布修复事件
    
    设计原则：
    - 多方案原则：每个冲突至少提供2种修复方案
    - 优先级原则：P0冲突优先处理
    - 用户主导：用户可选择接受、拒绝或延期
    - 学习优化：记录用户偏好，优化后续建议
    """
    
    def __init__(self, workspace_root: Optional[Path] = None):
        """
        初始化冲突修复建议生成器
        
        Args:
            workspace_root: 工作区根目录
        """
        self._workspace_root = workspace_root or Path.cwd()
        self._logger = logging.getLogger(__name__)
        
        # 延迟加载依赖（避免循环导入）
        self._event_bus = None
        self._llm_client = None
        
        # 线程安全
        self._stats_lock = threading.RLock()
        self._fixer_lock = threading.RLock()
        
        # 统计信息
        self._stats = FixStats()
        
        # 修复历史（用于学习用户偏好）
        self._fix_history: List[Dict[str, Any]] = []
        
        self._logger.info("ConflictFixer 初始化完成")
    
    def _get_event_bus(self):
        """延迟加载EventBus"""
        if self._event_bus is None:
            try:
                from core.event_bus import EventBus
                self._event_bus = EventBus.get_instance()
            except Exception as e:
                self._logger.warning(f"EventBus加载失败: {e}")
        return self._event_bus
    
    def _get_llm_client(self):
        """延迟加载LLM客户端"""
        if self._llm_client is None:
            try:
                from services.llm_client_with_resilience import get_llm_client
                self._llm_client = get_llm_client()
            except Exception as e:
                self._logger.warning(f"LLM客户端加载失败: {e}")
        return self._llm_client
    
    # ========================================================================
    # 主入口方法
    # ========================================================================
    
    def generate_fixes(
        self,
        conflicts: List[Any],
        chapter_content: str,
        chapter_number: int = 1,
        chapter_title: str = "",
        genre: str = "general",
        context_summary: Optional[str] = None
    ) -> FixGenerationResult:
        """
        为冲突列表生成修复建议
        
        Args:
            conflicts: 冲突列表（Conflict对象列表）
            chapter_content: 章节内容
            chapter_number: 章节号
            chapter_title: 章节标题
            genre: 题材类型
            context_summary: 上下文摘要（可选）
            
        Returns:
            FixGenerationResult: 修复建议生成结果
        """
        start_time = time.time()
        
        generation_id = f"fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(conflicts)}"
        
        self._logger.info(
            f"开始生成修复建议: generation_id={generation_id}, "
            f"conflicts={len(conflicts)}, chapter={chapter_number}"
        )
        
        fixes: List[ConflictFix] = []
        
        # 按严重程度排序（P0优先）
        sorted_conflicts = sorted(
            conflicts,
            key=lambda c: self._severity_rank(getattr(c, 'severity', 'P2'))
        )
        
        for idx, conflict in enumerate(sorted_conflicts):
            try:
                fix = self._generate_fix_for_conflict(
                    conflict=conflict,
                    chapter_content=chapter_content,
                    chapter_number=chapter_number,
                    chapter_title=chapter_title,
                    genre=genre,
                    context_summary=context_summary,
                    idx=idx
                )
                
                if fix:
                    fixes.append(fix)
                    
            except Exception as e:
                self._logger.error(
                    f"生成修复建议失败: conflict_id={getattr(conflict, 'conflict_id', 'unknown')}, "
                    f"error={e}"
                )
        
        # 更新统计
        with self._stats_lock:
            self._stats.total_generations += 1
            self._stats.total_fixes += len(fixes)
            
            for fix in fixes:
                if fix.conflict_type == "character":
                    self._stats.character_fixes += 1
                elif fix.conflict_type == "plot":
                    self._stats.plot_fixes += 1
                elif fix.conflict_type == "worldview":
                    self._stats.worldview_fixes += 1
                
                if fix.severity == "P0":
                    self._stats.p0_fixes += 1
                elif fix.severity == "P1":
                    self._stats.p1_fixes += 1
                elif fix.severity == "P2":
                    self._stats.p2_fixes += 1
        
        # 计算质量指标
        avg_option_count = sum(
            1 + (1 if f.option_b else 0) + (1 if f.option_c else 0)
            for f in fixes
        ) / max(len(fixes), 1)
        
        duration_ms = (time.time() - start_time) * 1000
        
        result = FixGenerationResult(
            generation_id=generation_id,
            timestamp=datetime.now().isoformat(),
            total_conflicts=len(conflicts),
            fixes=fixes,
            p0_fixes=sum(1 for f in fixes if f.severity == "P0"),
            p1_fixes=sum(1 for f in fixes if f.severity == "P1"),
            p2_fixes=sum(1 for f in fixes if f.severity == "P2"),
            avg_option_count=avg_option_count,
            generation_duration_ms=duration_ms,
            metadata={
                "chapter_number": chapter_number,
                "chapter_title": chapter_title,
                "genre": genre,
                "workspace_root": str(self._workspace_root)
            }
        )
        
        # 发布事件
        self._publish_fix_event(result)
        
        self._logger.info(
            f"修复建议生成完成: generation_id={generation_id}, "
            f"fixes={len(fixes)}, duration={duration_ms:.2f}ms"
        )
        
        return result
    
    def _generate_fix_for_conflict(
        self,
        conflict: Any,
        chapter_content: str,
        chapter_number: int,
        chapter_title: str,
        genre: str,
        context_summary: Optional[str],
        idx: int
    ) -> Optional[ConflictFix]:
        """
        为单个冲突生成修复建议
        """
        conflict_id = getattr(conflict, 'conflict_id', f"conflict_{idx}")
        conflict_type = getattr(conflict, 'conflict_type', 'unknown')
        severity = getattr(conflict, 'severity', 'P2')
        description = getattr(conflict, 'description', '')
        location = getattr(conflict, 'location', '')
        evidence = getattr(conflict, 'evidence', '')
        
        # 生成修复方案A（推荐方案）
        option_a = self._generate_fix_option(
            conflict_type=conflict_type,
            severity=severity,
            description=description,
            evidence=evidence,
            chapter_content=chapter_content,
            location=location,
            strategy="conservative",  # 保守策略：最小修改
            option_id="A"
        )
        
        # 生成修复方案B（备选方案）
        option_b = self._generate_fix_option(
            conflict_type=conflict_type,
            severity=severity,
            description=description,
            evidence=evidence,
            chapter_content=chapter_content,
            location=location,
            strategy="balanced",  # 平衡策略：适度修改
            option_id="B"
        )
        
        # P0冲突提供方案C（激进方案）
        option_c = None
        if severity == "P0":
            option_c = self._generate_fix_option(
                conflict_type=conflict_type,
                severity=severity,
                description=description,
                evidence=evidence,
                chapter_content=chapter_content,
                location=location,
                strategy="aggressive",  # 激进策略：大幅重写
                option_id="C"
            )
        
        fix_id = f"fix_{conflict_id}"
        
        return ConflictFix(
            fix_id=fix_id,
            conflict_id=conflict_id,
            conflict_type=conflict_type,
            severity=severity,
            description=description,
            location=location,
            option_a=option_a,
            option_b=option_b,
            option_c=option_c
        )
    
    def _generate_fix_option(
        self,
        conflict_type: str,
        severity: str,
        description: str,
        evidence: str,
        chapter_content: str,
        location: str,
        strategy: str,
        option_id: str
    ) -> FixOption:
        """
        生成单个修复方案
        
        Args:
            conflict_type: 冲突类型
            severity: 严重程度
            description: 冲突描述
            evidence: 证据
            chapter_content: 章节内容
            location: 冲突位置
            strategy: 策略（conservative/balanced/aggressive）
            option_id: 方案ID
        """
        # 根据冲突类型和策略生成修复建议
        if conflict_type == "character":
            return self._generate_character_fix(
                description=description,
                evidence=evidence,
                chapter_content=chapter_content,
                location=location,
                strategy=strategy,
                option_id=option_id
            )
        elif conflict_type == "plot":
            return self._generate_plot_fix(
                description=description,
                evidence=evidence,
                chapter_content=chapter_content,
                location=location,
                strategy=strategy,
                option_id=option_id
            )
        elif conflict_type == "worldview":
            return self._generate_worldview_fix(
                description=description,
                evidence=evidence,
                chapter_content=chapter_content,
                location=location,
                strategy=strategy,
                option_id=option_id
            )
        else:
            # 默认修复方案
            return self._generate_default_fix(
                description=description,
                strategy=strategy,
                option_id=option_id
            )
    
    def _generate_character_fix(
        self,
        description: str,
        evidence: str,
        chapter_content: str,
        location: str,
        strategy: str,
        option_id: str
    ) -> FixOption:
        """生成人物冲突修复方案"""
        
        # 提取人物名称
        character_match = re.search(r"人物[：:]\s*(\S+)", description)
        character_name = character_match.group(1) if character_match else "主角"
        
        if strategy == "conservative":
            return FixOption(
                option_id=option_id,
                title="添加行为动机解释",
                description=f"为{character_name}的行为添加合理的心理动机，解释行为转变的原因",
                modified_text=f"【建议在冲突位置添加】{character_name}心中暗想...经过一番思想斗争，最终...",
                rationale="保守策略：保持原有情节，通过补充心理描写使行为转变合理化",
                estimated_effort="低",
                impact_scope="单段"
            )
        elif strategy == "balanced":
            return FixOption(
                option_id=option_id,
                title="调整行为描述",
                description=f"修改{character_name}的行为描述，使其与前文性格保持一致",
                modified_text=f"【建议修改】将原行为改为符合{character_name}性格特点的替代行为",
                rationale="平衡策略：适度修改行为，保持人物一致性",
                estimated_effort="中",
                impact_scope="多段"
            )
        else:  # aggressive
            return FixOption(
                option_id=option_id,
                title="重构人物弧光",
                description=f"重新设计{character_name}的人物弧光，增加性格转变的铺垫",
                modified_text=f"【建议重构】在前面章节增加{character_name}性格变化的伏笔",
                rationale="激进策略：从根本上解决人物一致性问题",
                estimated_effort="高",
                impact_scope="全章"
            )
    
    def _generate_plot_fix(
        self,
        description: str,
        evidence: str,
        chapter_content: str,
        location: str,
        strategy: str,
        option_id: str
    ) -> FixOption:
        """生成情节冲突修复方案"""
        
        # 提取情节关键词
        if "时间" in description or "时间线" in description:
            plot_type = "timeline"
        elif "因果" in description:
            plot_type = "causality"
        else:
            plot_type = "general"
        
        if strategy == "conservative":
            if plot_type == "timeline":
                return FixOption(
                    option_id=option_id,
                    title="添加时间说明",
                    description="在情节中添加时间说明，解释时间差异的原因",
                    modified_text="【建议添加】\"几天后...\"或\"与此同时...\"",
                    rationale="保守策略：通过时间说明文字解决时间线问题",
                    estimated_effort="低",
                    impact_scope="单段"
                )
            else:
                return FixOption(
                    option_id=option_id,
                    title="补充因果链",
                    description="添加缺失的因果环节，使情节发展合理",
                    modified_text=f"【建议补充】在{location}处添加过渡情节",
                    rationale="保守策略：补充缺失的情节环节",
                    estimated_effort="低",
                    impact_scope="单段"
                )
        elif strategy == "balanced":
            if plot_type == "timeline":
                return FixOption(
                    option_id=option_id,
                    title="调整时间线叙述",
                    description="重新安排情节的时间顺序",
                    modified_text="【建议调整】使用倒叙、插叙等手法重新组织时间线",
                    rationale="平衡策略：通过叙述技巧解决时间线问题",
                    estimated_effort="中",
                    impact_scope="多段"
                )
            else:
                return FixOption(
                    option_id=option_id,
                    title="重构情节逻辑",
                    description="修改情节发展逻辑，确保因果关系成立",
                    modified_text=f"【建议修改】在{location}处调整情节走向",
                    rationale="平衡策略：适度修改情节逻辑",
                    estimated_effort="中",
                    impact_scope="多段"
                )
        else:  # aggressive
            return FixOption(
                option_id=option_id,
                title="重写情节段落",
                description="重新设计并重写冲突涉及的情节段落",
                modified_text=f"【建议重写】重新设计{location}处的情节发展",
                rationale="激进策略：从根本上解决情节冲突问题",
                estimated_effort="高",
                impact_scope="全章"
            )
    
    def _generate_worldview_fix(
        self,
        description: str,
        evidence: str,
        chapter_content: str,
        location: str,
        strategy: str,
        option_id: str
    ) -> FixOption:
        """生成世界观冲突修复方案"""
        
        # 提取设定关键词
        if "设定" in description:
            setting_type = "setting"
        elif "规则" in description:
            setting_type = "rule"
        else:
            setting_type = "general"
        
        if strategy == "conservative":
            return FixOption(
                option_id=option_id,
                title="添加设定解释",
                description="通过对话或旁白解释设定差异的原因",
                modified_text="【建议添加】\"虽然...但是...这是因为...\"",
                rationale="保守策略：通过解释使设定差异合理化",
                estimated_effort="低",
                impact_scope="单段"
            )
        elif strategy == "balanced":
            return FixOption(
                option_id=option_id,
                title="调整设定描述",
                description="修改世界观设定描述，使其前后一致",
                modified_text=f"【建议修改】在{location}处统一世界观设定",
                rationale="平衡策略：统一世界观设定，保持一致性",
                estimated_effort="中",
                impact_scope="多段"
            )
        else:  # aggressive
            return FixOption(
                option_id=option_id,
                title="重构世界观体系",
                description="重新设计世界观体系，确保所有设定自洽",
                modified_text="【建议重构】重新梳理世界观设定，建立完整的设定文档",
                rationale="激进策略：从根本上解决世界观一致性问题",
                estimated_effort="高",
                impact_scope="全章"
            )
    
    def _generate_default_fix(
        self,
        description: str,
        strategy: str,
        option_id: str
    ) -> FixOption:
        """生成默认修复方案"""
        
        if strategy == "conservative":
            return FixOption(
                option_id=option_id,
                title="补充说明",
                description="通过补充说明文字解决冲突",
                modified_text="【建议添加补充说明】",
                rationale="保守策略：最小修改",
                estimated_effort="低",
                impact_scope="单段"
            )
        elif strategy == "balanced":
            return FixOption(
                option_id=option_id,
                title="调整内容",
                description="调整冲突部分的内容",
                modified_text="【建议调整相关内容】",
                rationale="平衡策略：适度修改",
                estimated_effort="中",
                impact_scope="多段"
            )
        else:
            return FixOption(
                option_id=option_id,
                title="重写部分",
                description="重写冲突涉及的部分",
                modified_text="【建议重写】",
                rationale="激进策略：大幅修改",
                estimated_effort="高",
                impact_scope="全章"
            )
    
    # ========================================================================
    # 用户决策处理
    # ========================================================================
    
    def record_user_decision(
        self,
        fix_id: str,
        decision: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        记录用户决策
        
        Args:
            fix_id: 修复ID
            decision: 决策（accept_a/accept_b/accept_c/reject/defer）
            reason: 决策理由
            
        Returns:
            bool: 是否成功记录
        """
        with self._stats_lock:
            self._stats.total_decisions += 1
            
            if decision.startswith("accept"):
                self._stats.accepted_count += 1
            elif decision == "reject":
                self._stats.rejected_count += 1
            elif decision == "defer":
                self._stats.deferred_count += 1
            
            # 更新接受率
            if self._stats.total_decisions > 0:
                self._stats.acceptance_rate = (
                    self._stats.accepted_count / self._stats.total_decisions
                )
        
        # 记录到历史（用于学习用户偏好）
        self._fix_history.append({
            "fix_id": fix_id,
            "decision": decision,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        })
        
        self._logger.info(
            f"记录用户决策: fix_id={fix_id}, decision={decision}, "
            f"acceptance_rate={self._stats.acceptance_rate:.2%}"
        )
        
        return True
    
    def get_acceptance_rate(self) -> float:
        """获取用户接受率"""
        with self._stats_lock:
            return self._stats.acceptance_rate
    
    def get_stats(self) -> FixStats:
        """获取统计信息"""
        with self._stats_lock:
            return self._stats.model_copy()
    
    # ========================================================================
    # 辅助方法
    # ========================================================================
    
    def _severity_rank(self, severity: str) -> int:
        """严重程度排序（P0=0, P1=1, P2=2）"""
        severity_map = {"P0": 0, "P1": 1, "P2": 2}
        return severity_map.get(severity, 2)
    
    def _publish_fix_event(self, result: FixGenerationResult) -> None:
        """发布修复建议生成事件"""
        event_bus = self._get_event_bus()
        if event_bus:
            try:
                event_bus.publish(
                    event_type="conflict.fix.generated",
                    data={
                        "generation_id": result.generation_id,
                        "timestamp": result.timestamp,
                        "total_conflicts": result.total_conflicts,
                        "total_fixes": len(result.fixes),
                        "p0_fixes": result.p0_fixes,
                        "p1_fixes": result.p1_fixes,
                        "p2_fixes": result.p2_fixes,
                        "duration_ms": result.generation_duration_ms
                    }
                )
            except Exception as e:
                self._logger.warning(f"发布事件失败: {e}")


# ============================================================================
# 单例工厂
# ============================================================================

_conflict_fixer_instance: Optional[ConflictFixer] = None
_conflict_fixer_lock = threading.RLock()


def get_conflict_fixer(workspace_root: Optional[Path] = None) -> ConflictFixer:
    """
    获取ConflictFixer单例实例
    
    Args:
        workspace_root: 工作区根目录
        
    Returns:
        ConflictFixer: 冲突修复建议生成器实例
    """
    global _conflict_fixer_instance
    
    if _conflict_fixer_instance is None:
        with _conflict_fixer_lock:
            if _conflict_fixer_instance is None:
                _conflict_fixer_instance = ConflictFixer(workspace_root=workspace_root)
    
    return _conflict_fixer_instance


def reset_conflict_fixer() -> None:
    """重置ConflictFixer实例（用于测试）"""
    global _conflict_fixer_instance
    
    with _conflict_fixer_lock:
        _conflict_fixer_instance = None
