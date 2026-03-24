"""
设定修正生成器

V1.0版本
创建日期: 2026-03-24

功能:
- 接收冲突列表和原始设定
- 调用大模型生成修正后的设定文本
- 支持单个冲突或批量生成修正方案
- 输出格式化为结构化数据
"""

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.plugin_interface import (
    ConsistencyIssue,
    ConsistencyIssueType,
    ConsistencySeverity,
)

logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================


@dataclass
class CorrectionResult:
    """单个冲突的修正结果"""
    
    issue_id: str                    # 对应的冲突ID
    issue_type: ConsistencyIssueType # 冲突类型
    element_name: str                # 修正的元素名称
    original_setting: str            # 原始设定
    corrected_setting: str           # 修正后的设定
    correction_reason: str           # 修正原因
    confidence: float                # 修正置信度
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type.value,
            "element_name": self.element_name,
            "original_setting": self.original_setting,
            "corrected_setting": self.corrected_setting,
            "correction_reason": self.correction_reason,
            "confidence": self.confidence,
        }


@dataclass
class CorrectionReport:
    """修正报告"""
    
    report_id: str = field(default_factory=lambda: f"corr-{hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]}")
    project_name: str = ""
    corrections: List[CorrectionResult] = field(default_factory=list)
    
    # 修正后的结构化数据
    updated_outline: str = ""
    updated_characters: List[Dict[str, Any]] = field(default_factory=list)
    updated_worldview: str = ""
    
    # 元数据
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    total_issues: int = 0
    corrected_count: int = 0
    failed_count: int = 0
    backup: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "project_name": self.project_name,
            "corrections": [c.to_dict() for c in self.corrections],
            "updated_outline": self.updated_outline,
            "updated_characters": self.updated_characters,
            "updated_worldview": self.updated_worldview,
            "generated_at": self.generated_at,
            "total_issues": self.total_issues,
            "corrected_count": self.corrected_count,
            "failed_count": self.failed_count,
            "backup": self.backup,
        }


# ============================================================================
# LLM修正生成器
# ============================================================================


class LLMCorrector:
    """
    LLM修正生成器
    
    调用大模型生成设定修正方案
    """
    
    def __init__(self, llm_client=None):
        self._llm_client = llm_client
        self._timeout = 60
        self._max_retries = 3
    
    def set_llm_client(self, llm_client) -> None:
        """设置LLM客户端"""
        self._llm_client = llm_client
    
    def correct_single_issue(
        self,
        issue: ConsistencyIssue,
        original_settings: Dict[str, Any],
    ) -> CorrectionResult:
        """
        修正单个冲突
        
        Args:
            issue: 冲突项
            original_settings: 原始设定（包含outline/characters/worldview）
            
        Returns:
            CorrectionResult: 修正结果
        """
        if not self._llm_client:
            # 无LLM客户端，使用规则修正
            return self._rule_based_correct(issue, original_settings)
        
        # 构建修正提示
        prompt = self._build_correction_prompt(issue, original_settings)
        
        try:
            response = self._call_llm(prompt)
            return self._parse_correction_response(issue, response)
        except Exception as e:
            logger.error(f"LLM修正调用失败: {e}")
            return self._rule_based_correct(issue, original_settings)
    
    def correct_batch(
        self,
        issues: List[ConsistencyIssue],
        original_settings: Dict[str, Any],
    ) -> List[CorrectionResult]:
        """
        批量修正冲突
        
        Args:
            issues: 冲突列表
            original_settings: 原始设定
            
        Returns:
            修正结果列表
        """
        results = []
        
        # 按类型分组处理
        issues_by_type: Dict[ConsistencyIssueType, List[ConsistencyIssue]] = {}
        for issue in issues:
            if issue.issue_type not in issues_by_type:
                issues_by_type[issue.issue_type] = []
            issues_by_type[issue.issue_type].append(issue)
        
        # 逐类型修正
        for issue_type, type_issues in issues_by_type.items():
            if issue_type == ConsistencyIssueType.CHARACTER:
                results.extend(self._correct_characters_batch(type_issues, original_settings))
            elif issue_type == ConsistencyIssueType.OUTLINE:
                results.extend(self._correct_outline_batch(type_issues, original_settings))
            elif issue_type == ConsistencyIssueType.WORLDVIEW:
                results.extend(self._correct_worldview_batch(type_issues, original_settings))
        
        return results
    
    def _build_correction_prompt(
        self,
        issue: ConsistencyIssue,
        original_settings: Dict[str, Any],
    ) -> str:
        """构建修正提示"""
        
        # 获取相关设定
        outline = original_settings.get("outline", "")
        characters = original_settings.get("characters", [])
        worldview = original_settings.get("worldview", "")
        
        if issue.issue_type == ConsistencyIssueType.CHARACTER:
            # 找到相关人物
            char_info = ""
            for char in characters:
                if char.get("name") == issue.element_name:
                    char_info = json.dumps(char, ensure_ascii=False, indent=2)
                    break
            
            prompt = f"""你是一个专业的小说设定编辑。请根据以下冲突信息，修正人物设定。

## 冲突信息
- 冲突类型: 人物设定冲突
- 涉及角色: {issue.element_name}
- 冲突描述: {issue.description}
- 建议修正: {issue.suggested_fix}

## 当前人物设定
{char_info or '未找到该角色设定'}

## 要求
1. 根据章节内容中角色的实际表现，调整人物设定
2. 保持人物设定的其他属性不变
3. 输出修正后的完整人物设定JSON

## 输出格式
```json
{{
  "corrected_setting": {{
    "name": "角色名",
    "personality": "修正后的性格",
    "ability": "修正后的能力",
    "background": "背景（保持不变）",
    ...
  }},
  "correction_reason": "修正原因说明",
  "confidence": 0.9
}}
```
"""
        
        elif issue.issue_type == ConsistencyIssueType.OUTLINE:
            prompt = f"""你是一个专业的小说设定编辑。请根据以下冲突信息，修正大纲设定。

## 冲突信息
- 冲突类型: 大纲冲突
- 涉及元素: {issue.element_name}
- 冲突描述: {issue.description}
- 建议修正: {issue.suggested_fix}

## 当前大纲
{outline[:1000] if outline else '未提供'}

## 要求
1. 根据章节实际内容，调整大纲中的相关章节
2. 保持大纲的整体结构和其他章节不变
3. 输出修正后的大纲文本

## 输出格式
```json
{{
  "corrected_setting": "修正后的大纲文本...",
  "correction_reason": "修正原因说明",
  "confidence": 0.85
}}
```
"""
        
        else:  # WORLDVIEW
            prompt = f"""你是一个专业的小说设定编辑。请根据以下冲突信息，修正世界观设定。

## 冲突信息
- 冲突类型: 世界观冲突
- 涉及元素: {issue.element_name}
- 冲突描述: {issue.description}
- 建议修正: {issue.suggested_fix}

## 当前世界观
{worldview[:1000] if worldview else '未提供'}

## 要求
1. 根据章节内容中的实际设定，调整世界观
2. 保持世界观的其他部分不变
3. 输出修正后的世界观文本

## 输出格式
```json
{{
  "corrected_setting": "修正后的世界观文本...",
  "correction_reason": "修正原因说明",
  "confidence": 0.8
}}
```
"""
        
        return prompt
    
    def _call_llm(self, prompt: str) -> str:
        """调用LLM"""
        if hasattr(self._llm_client, 'call'):
            return self._llm_client.call(prompt)
        elif hasattr(self._llm_client, 'generate'):
            return self._llm_client.generate(prompt)
        else:
            raise RuntimeError("不支持的LLM客户端类型")
    
    def _parse_correction_response(
        self,
        issue: ConsistencyIssue,
        response: str,
    ) -> CorrectionResult:
        """解析修正响应"""
        import re
        
        try:
            # 提取JSON
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                
                corrected = result.get("corrected_setting", "")
                reason = result.get("correction_reason", "")
                confidence = result.get("confidence", 0.8)
                
                if isinstance(corrected, dict):
                    corrected = json.dumps(corrected, ensure_ascii=False)
                
                return CorrectionResult(
                    issue_id=issue.issue_id,
                    issue_type=issue.issue_type,
                    element_name=issue.element_name,
                    original_setting=issue.original_content,
                    corrected_setting=corrected,
                    correction_reason=reason,
                    confidence=confidence,
                )
        except json.JSONDecodeError:
            logger.warning("修正响应JSON解析失败")
        
        # 解析失败，返回规则修正
        return self._rule_based_correct(issue, {})
    
    def _rule_based_correct(
        self,
        issue: ConsistencyIssue,
        original_settings: Dict[str, Any],
    ) -> CorrectionResult:
        """基于规则的修正（LLM不可用时的降级方案）"""
        
        # 根据建议生成简单修正
        corrected = issue.suggested_fix
        
        if issue.issue_type == ConsistencyIssueType.CHARACTER:
            # 人物修正：尝试从建议提取修正内容
            corrected = f"根据章节内容更新：{issue.suggested_fix}"
        
        elif issue.issue_type == ConsistencyIssueType.OUTLINE:
            # 大纲修正：添加说明
            corrected = f"[修正] {issue.suggested_fix}"
        
        else:  # WORLDVIEW
            # 世界观修正：添加规则说明
            corrected = f"规则更新：{issue.suggested_fix}"
        
        return CorrectionResult(
            issue_id=issue.issue_id,
            issue_type=issue.issue_type,
            element_name=issue.element_name,
            original_setting=issue.original_content,
            corrected_setting=corrected,
            correction_reason="规则自动修正（LLM不可用）",
            confidence=0.6,
        )
    
    def _correct_characters_batch(
        self,
        issues: List[ConsistencyIssue],
        original_settings: Dict[str, Any],
    ) -> List[CorrectionResult]:
        """批量修正人物冲突"""
        results = []
        characters = original_settings.get("characters", [])
        
        for issue in issues:
            # 单独处理每个人物冲突
            result = self.correct_single_issue(issue, original_settings)
            results.append(result)
        
        return results
    
    def _correct_outline_batch(
        self,
        issues: List[ConsistencyIssue],
        original_settings: Dict[str, Any],
    ) -> List[CorrectionResult]:
        """批量修正大纲冲突"""
        results = []
        
        # 合并所有大纲问题
        if self._llm_client:
            prompt = self._build_batch_outline_prompt(issues, original_settings)
            try:
                response = self._call_llm(prompt)
                # 解析批量修正结果
                results = self._parse_batch_correction(issues, response)
            except Exception as e:
                logger.error(f"批量大纲修正失败: {e}")
                for issue in issues:
                    results.append(self._rule_based_correct(issue, original_settings))
        else:
            for issue in issues:
                results.append(self._rule_based_correct(issue, original_settings))
        
        return results
    
    def _correct_worldview_batch(
        self,
        issues: List[ConsistencyIssue],
        original_settings: Dict[str, Any],
    ) -> List[CorrectionResult]:
        """批量修正世界观冲突"""
        results = []
        
        for issue in issues:
            result = self.correct_single_issue(issue, original_settings)
            results.append(result)
        
        return results
    
    def _build_batch_outline_prompt(
        self,
        issues: List[ConsistencyIssue],
        original_settings: Dict[str, Any],
    ) -> str:
        """构建批量大纲修正提示"""
        outline = original_settings.get("outline", "")
        
        issues_desc = "\n".join([
            f"- [{i.severity.value}] {i.description}"
            for i in issues
        ])
        
        return f"""你是一个专业的小说设定编辑。请根据以下多个冲突，修正大纲设定。

## 冲突列表
{issues_desc}

## 当前大纲
{outline[:1500] if outline else '未提供'}

## 要求
1. 根据所有冲突，综合调整大纲
2. 保持大纲整体结构
3. 输出修正后的大纲文本

## 输出格式
```json
{{
  "corrected_outline": "修正后的大纲...",
  "changes": [
    {{"element": "章节名", "change": "修改内容"}}
  ]
}}
```
"""
    
    def _parse_batch_correction(
        self,
        issues: List[ConsistencyIssue],
        response: str,
    ) -> List[CorrectionResult]:
        """解析批量修正响应"""
        import re
        
        results = []
        
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                
                corrected = result.get("corrected_outline", "")
                changes = result.get("changes", [])
                
                # 为每个冲突生成结果
                for i, issue in enumerate(issues):
                    change = changes[i] if i < len(changes) else {}
                    results.append(CorrectionResult(
                        issue_id=issue.issue_id,
                        issue_type=issue.issue_type,
                        element_name=change.get("element", issue.element_name),
                        original_setting=issue.original_content,
                        corrected_setting=corrected,
                        correction_reason=change.get("change", "批量修正"),
                        confidence=0.85,
                    ))
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(f"批量修正解析失败: {e}")
            for issue in issues:
                results.append(CorrectionResult(
                    issue_id=issue.issue_id,
                    issue_type=issue.issue_type,
                    element_name=issue.element_name,
                    original_setting=issue.original_content,
                    corrected_setting=issue.suggested_fix,
                    correction_reason="解析失败降级处理",
                    confidence=0.6,
                ))
        
        return results


# ============================================================================
# 设定修正器主类
# ============================================================================


class SettingsCorrector:
    """
    设定修正生成器
    
    接收冲突列表和原始设定，生成修正后的设定
    """
    
    def __init__(self, llm_client=None):
        self._llm_corrector = LLMCorrector(llm_client)
    
    def set_llm_client(self, llm_client) -> None:
        """设置LLM客户端"""
        self._llm_corrector.set_llm_client(llm_client)
    
    def correct_settings(
        self,
        issues: List[ConsistencyIssue],
        original_settings: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
    ) -> CorrectionReport:
        """
        修正设定
        
        Args:
            issues: 冲突列表
            original_settings: 原始设定
                - outline: 大纲文本
                - characters: 人物设定列表
                - worldview: 世界观设定文本
            options: 修正选项
                - auto_fix_low: 是否自动修正低优先级冲突
                - preserve_original: 是否保留原始设定备份
                - batch_mode: 是否批量处理
            
        Returns:
            CorrectionReport: 修正报告
        """
        options = options or {}
        auto_fix_low = options.get("auto_fix_low", True)
        preserve_original = options.get("preserve_original", True)
        batch_mode = options.get("batch_mode", False)
        
        # 创建报告
        report = CorrectionReport(
            project_name=original_settings.get("project_name", ""),
            total_issues=len(issues),
        )
        
        # 保存备份
        if preserve_original:
            report.backup = {
                "outline": original_settings.get("outline", ""),
                "characters": original_settings.get("characters", []),
                "worldview": original_settings.get("worldview", ""),
            }
        
        # 过滤需要修正的冲突
        issues_to_fix = [
            i for i in issues
            if i.severity != ConsistencySeverity.LOW or auto_fix_low
        ]
        
        # 执行修正
        if batch_mode:
            corrections = self._llm_corrector.correct_batch(issues_to_fix, original_settings)
        else:
            corrections = []
            for issue in issues_to_fix:
                result = self._llm_corrector.correct_single_issue(issue, original_settings)
                corrections.append(result)
        
        report.corrections = corrections
        report.corrected_count = len([c for c in corrections if c.confidence >= 0.7])
        report.failed_count = len(corrections) - report.corrected_count
        
        # 应用修正到结构化数据
        self._apply_corrections(report, original_settings)
        
        return report
    
    def _apply_corrections(
        self,
        report: CorrectionReport,
        original_settings: Dict[str, Any],
    ) -> None:
        """应用修正结果到结构化数据"""
        
        # 初始化为原始数据
        report.updated_outline = original_settings.get("outline", "")
        report.updated_characters = list(original_settings.get("characters", []))
        report.updated_worldview = original_settings.get("worldview", "")
        
        # 按类型分组应用修正
        for correction in report.corrections:
            if correction.issue_type == ConsistencyIssueType.OUTLINE:
                # 更新大纲
                report.updated_outline = correction.corrected_setting
            
            elif correction.issue_type == ConsistencyIssueType.CHARACTER:
                # 更新人物设定
                try:
                    corrected_char = json.loads(correction.corrected_setting)
                    # 找到并更新对应人物
                    for i, char in enumerate(report.updated_characters):
                        if char.get("name") == correction.element_name:
                            report.updated_characters[i] = corrected_char
                            break
                    else:
                        # 新人物，添加到列表
                        report.updated_characters.append(corrected_char)
                except json.JSONDecodeError:
                    # 非JSON格式，记录原始修正文本
                    for i, char in enumerate(report.updated_characters):
                        if char.get("name") == correction.element_name:
                            report.updated_characters[i]["notes"] = correction.corrected_setting
                            break
            
            elif correction.issue_type == ConsistencyIssueType.WORLDVIEW:
                # 更新世界观
                report.updated_worldview = correction.corrected_setting


# ============================================================================
# 便捷函数
# ============================================================================


def correct_single_issue(
    issue: ConsistencyIssue,
    original_settings: Dict[str, Any],
    llm_client=None,
) -> CorrectionResult:
    """
    修正单个冲突（便捷函数）
    
    Args:
        issue: 冲突项
        original_settings: 原始设定
        llm_client: LLM客户端（可选）
    
    Returns:
        CorrectionResult: 修正结果
    """
    corrector = LLMCorrector(llm_client)
    return corrector.correct_single_issue(issue, original_settings)


def correct_batch_issues(
    issues: List[ConsistencyIssue],
    original_settings: Dict[str, Any],
    llm_client=None,
    options: Optional[Dict[str, Any]] = None,
) -> CorrectionReport:
    """
    批量修正冲突（便捷函数）
    
    Args:
        issues: 冲突列表
        original_settings: 原始设定
        llm_client: LLM客户端（可选）
        options: 修正选项
    
    Returns:
        CorrectionReport: 修正报告
    """
    corrector = SettingsCorrector(llm_client)
    return corrector.correct_settings(issues, original_settings, options)


def settings_corrector(
    issues: List[ConsistencyIssue],
    original_settings: Dict[str, Any],
    llm_client=None,
    options: Optional[Dict[str, Any]] = None,
) -> CorrectionReport:
    """
    设定修正生成器（主入口函数）
    
    Args:
        issues: 冲突列表
        original_settings: 原始设定
            - outline: 大纲文本
            - characters: 人物设定列表
            - worldview: 世界观设定文本
            - project_name: 项目名称
        llm_client: LLM客户端（可选）
        options: 修正选项
            - auto_fix_low: 是否自动修正低优先级冲突（默认True）
            - preserve_original: 是否保留原始设定备份（默认True）
            - batch_mode: 是否批量处理（默认False）
    
    Returns:
        CorrectionReport: 修正报告，包含修正后的结构化数据
    
    示例:
        >>> issues = [ConsistencyIssue(...), ...]
        >>> settings = {
        ...     "outline": "第一章...",
        ...     "characters": [{"name": "张三", ...}],
        ...     "worldview": "修仙世界..."
        ... }
        >>> report = settings_corrector(issues, settings)
        >>> print(report.updated_outline)
        >>> print(report.updated_characters)
    """
    corrector = SettingsCorrector(llm_client)
    return corrector.correct_settings(issues, original_settings, options)
