#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Claw优化集成 - 反馈闭环

功能：
- 将删除操作数据传输给Claw
- 生成优化报告
- 保存到记忆文件
- 发布EventBus事件
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
from collections import Counter

logger = logging.getLogger(__name__)


class ClawOptimizer:
    """Claw优化集成 - 反馈闭环"""
    
    def __init__(self, workspace_root: Path):
        """
        初始化Claw优化器
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = workspace_root
        self.memory_dir = workspace_root / ".workbuddy" / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("[CLAW_OPTIMIZER] 初始化完成")
    
    def report_cleanup(self, 
                    removed_knowledge: List[Dict],
                    reasons: Dict[str, str]) -> Dict[str, Any]:
        """
        报告清理操作给Claw
        
        Args:
            removed_knowledge: 被删除的知识点列表
            reasons: 删除原因映射 {id: reason}
        
        Returns:
            清理报告字典
        """
        try:
            # 构建优化报告
            report = self._build_cleanup_report(removed_knowledge, reasons)
            
            # 保存到记忆文件
            self._save_to_memory(report)
            
            # 触发EventBus事件
            self._publish_cleanup_event(report)
            
            logger.info(f"[CLAW_OPTIMIZER] 清理报告已保存，触发事件")
            
            return report
            
        except Exception as e:
            logger.error(f"[CLAW_OPTIMIZER] 报告失败: {e}")
            return {"error": str(e)}
    
    def _build_cleanup_report(self, 
                            removed_knowledge: List[Dict],
                            reasons: Dict[str, str]) -> Dict[str, Any]:
        """
        构建清理报告
        
        Args:
            removed_knowledge: 被删除的知识点列表
            reasons: 删除原因映射
        
        Returns:
            清理报告字典
        """
        # 统计删除原因
        reason_stats = {}
        for kp in removed_knowledge:
            reason = reasons.get(kp.get('knowledge_id', ''), 'unknown')
            reason_stats[reason] = reason_stats.get(reason, 0) + 1
        
        # 提取共性问题（用于优化Prompt）
        common_issues = self._extract_common_issues(removed_knowledge)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "removed_count": len(removed_knowledge),
            "reasons": reason_stats,
            "common_issues": common_issues,
            "optimization_suggestions": self._generate_suggestions(common_issues)
        }
    
    def _extract_common_issues(self, 
                            removed_knowledge: List[Dict]) -> List[str]:
        """
        提取共性问题
        
        用于优化AI生成的Prompt
        
        Args:
            removed_knowledge: 被删除的知识点列表
        
        Returns:
            共性问题列表（按频率排序）
        """
        issues = []
        
        for kp in removed_knowledge:
            content = kp.get('content', '')
            keywords = kp.get('keywords', [])
            references = kp.get('references', [])
            
            # 检测内容过短
            if len(content) < 500:
                issues.append("content_too_short")
            
            # 检测关键词过少
            if len(keywords) < 5:
                issues.append("keywords_too_few")
            
            # 检测参考作品过少
            if len(references) < 2:
                issues.append("references_too_few")
        
        # 统计高频问题
        counter = Counter(issues)
        return [f"{issue} ({count}次)" for issue, count in counter.most_common(5)]
    
    def _generate_suggestions(self, 
                              common_issues: List[str]) -> List[str]:
        """
        生成优化建议
        
        基于共性问题生成Prompt优化建议
        
        Args:
            common_issues: 共性问题列表
        
        Returns:
            优化建议列表
        """
        suggestions = []
        
        issues_str = ' '.join(common_issues)
        
        if "content_too_short" in issues_str:
            suggestions.append(
                "Prompt优化: 明确要求知识点内容长度≥2000字，提供详细示例"
            )
        
        if "keywords_too_few" in issues_str:
            suggestions.append(
                "Prompt优化: 强制要求关键词数量≥8个，提供关键词示例列表"
            )
        
        if "references_too_few" in issues_str:
            suggestions.append(
                "Prompt优化: 要求至少3个参考作品，提供参考作品格式示例"
            )
        
        if not suggestions:
            suggestions.append("知识库整体质量良好，无需特别优化")
        
        return suggestions
    
    def _save_to_memory(self, report: Dict[str, Any]) -> None:
        """
        保存到记忆文件
        
        Args:
            report: 清理报告
        """
        today = datetime.now().strftime("%Y-%m-%d")
        memory_file = self.memory_dir / f"{today}.md"
        
        try:
            # 追加模式
            with open(memory_file, 'a', encoding='utf-8') as f:
                f.write(f"\n## 知识库清理报告 ({report['timestamp']})\n\n")
                f.write(f"**删除数量**: {report['removed_count']}条\n\n")
                
                f.write(f"**删除原因统计**:\n")
                for reason, count in report['reasons'].items():
                    f.write(f"  - {reason}: {count}条\n")
                
                f.write(f"\n**共性问题**:\n")
                for issue in report['common_issues']:
                    f.write(f"  - {issue}\n")
                
                f.write(f"\n**优化建议**:\n")
                for suggestion in report['optimization_suggestions']:
                    f.write(f"  - {suggestion}\n")
                
                f.write("\n---\n")
            
            logger.info(f"[CLAW_OPTIMIZER] 报告已保存到: {memory_file}")
        except Exception as e:
            logger.error(f"[CLAW_OPTIMIZER] 保存记忆文件失败: {e}")
    
    def _publish_cleanup_event(self, report: Dict[str, Any]) -> None:
        """
        发布清理事件（通过EventBus）
        
        Args:
            report: 清理报告
        """
        try:
            from core.event_bus import EventBus
            
            event_bus = EventBus()
            event_bus.publish(
                event_type="knowledge.cleanup.completed",
                data={
                    "report": report,
                    "source": "KnowledgeVerifierPlugin"
                }
            )
            
            logger.info("[CLAW_OPTIMIZER] EventBus事件已发布")
            
        except ImportError:
            logger.warning("[CLAW_OPTIMIZER] EventBus未安装，跳过事件发布")
        except Exception as e:
            logger.warning(f"[CLAW_OPTIMIZER] 事件发布失败: {e}")
