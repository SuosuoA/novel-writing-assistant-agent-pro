"""
报告生成器 - 定期生成系统优化报告

V1.0版本
创建日期: 2026-03-26

功能:
- 生成周报/月报
- 分析评分趋势
- 识别薄弱维度
- 生成模块升级建议

使用示例:
    from core.report_generator import ReportGenerator
    
    generator = ReportGenerator()
    
    # 生成周报
    report = generator.generate_weekly_report()
    
    # 生成月报
    report = generator.generate_monthly_report()
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class Report:
    """报告数据类"""
    report_type: str  # weekly / monthly / special
    period_start: str
    period_end: str
    metrics: Dict[str, Any]
    analysis: Dict[str, Any]
    recommendations: List[Dict[str, Any]]
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class ReportGenerator:
    """
    报告生成器
    
    功能:
    - 生成周报/月报
    - 分析评分趋势
    - 识别薄弱维度
    - 生成模块升级建议
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        初始化报告生成器
        
        Args:
            output_dir: 报告输出目录（默认为 reports/）
        """
        if output_dir is None:
            output_dir = Path("reports")
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"ReportGenerator initialized with output_dir: {self.output_dir}")
    
    def generate_weekly_report(self, score_history: List[Dict] = None,
                               feedback_stats: Dict = None,
                               knowledge_stats: Dict = None) -> Report:
        """
        生成周报
        
        Args:
            score_history: 评分历史数据
            feedback_stats: 反馈统计数据
            knowledge_stats: 知识库统计数据
        
        Returns:
            周报对象
        """
        # 计算报告周期
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        # 收集指标
        metrics = self._collect_metrics(score_history, feedback_stats, knowledge_stats)
        
        # 分析趋势
        analysis = self._analyze_trends(score_history)
        
        # 生成建议
        recommendations = self._generate_recommendations(analysis)
        
        report = Report(
            report_type="weekly",
            period_start=start_date.strftime("%Y-%m-%d"),
            period_end=end_date.strftime("%Y-%m-%d"),
            metrics=metrics,
            analysis=analysis,
            recommendations=recommendations
        )
        
        # 保存报告
        self._save_report(report)
        
        logger.info(f"Generated weekly report: {report.period_start} to {report.period_end}")
        return report
    
    def generate_monthly_report(self, score_history: List[Dict] = None,
                                feedback_stats: Dict = None,
                                knowledge_stats: Dict = None) -> Report:
        """
        生成月报
        
        Args:
            score_history: 评分历史数据
            feedback_stats: 反馈统计数据
            knowledge_stats: 知识库统计数据
        
        Returns:
            月报对象
        """
        # 计算报告周期
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # 收集指标
        metrics = self._collect_metrics(score_history, feedback_stats, knowledge_stats)
        
        # 分析趋势
        analysis = self._analyze_trends(score_history, detailed=True)
        
        # 生成建议
        recommendations = self._generate_recommendations(analysis, priority="medium")
        
        report = Report(
            report_type="monthly",
            period_start=start_date.strftime("%Y-%m-%d"),
            period_end=end_date.strftime("%Y-%m-%d"),
            metrics=metrics,
            analysis=analysis,
            recommendations=recommendations
        )
        
        # 保存报告
        self._save_report(report)
        
        logger.info(f"Generated monthly report: {report.period_start} to {report.period_end}")
        return report
    
    def generate_improvement_report(self) -> Optional[Dict[str, Any]]:
        """
        生成改进报告（GUI调用）
        
        收集数据并生成改进报告
        
        Returns:
            包含date和content的字典，或None（数据不足时）
        """
        try:
            # 尝试收集数据
            score_history = []
            feedback_stats = {}
            knowledge_stats = {}
            
            # 收集评分历史
            try:
                from core.score_history_analyzer import get_score_history_analyzer
                analyzer = get_score_history_analyzer()
                score_history = analyzer.get_recent_scores(limit=50)
            except Exception as e:
                logger.warning(f"获取评分历史失败: {e}")
            
            # 收集反馈统计
            try:
                from core.feedback_collector import get_feedback_collector
                collector = get_feedback_collector()
                feedback_stats = collector.get_statistics()
            except Exception as e:
                logger.warning(f"获取反馈统计失败: {e}")
            
            # 收集知识库统计
            try:
                from core.knowledge_manager import get_knowledge_manager
                km = get_knowledge_manager()
                knowledge_stats = km.get_statistics()
            except Exception as e:
                logger.warning(f"获取知识库统计失败: {e}")
            
            # 检查是否有足够数据
            if not score_history and not feedback_stats.get('total', 0):
                logger.warning("数据不足，无法生成改进报告")
                return None
            
            # 生成周报
            report = self.generate_weekly_report(
                score_history=score_history,
                feedback_stats=feedback_stats,
                knowledge_stats=knowledge_stats
            )
            
            # 生成Markdown内容
            content = self._generate_markdown(report)
            
            return {
                "date": datetime.now().strftime("%Y%m%d"),
                "content": content,
                "report": report
            }
            
        except Exception as e:
            logger.error(f"生成改进报告失败: {e}")
            return None
    
    def _collect_metrics(self, score_history: List[Dict],
                        feedback_stats: Dict,
                        knowledge_stats: Dict) -> Dict[str, Any]:
        """收集指标数据"""
        metrics = {
            "chapters_generated": 0,
            "avg_scores": {},
            "ai_feeling_score": 0.0,
            "knowledge_base_size": 0,
            "avg_iterations": 0.0,
            "feedback_count": 0
        }
        
        if score_history:
            metrics["chapters_generated"] = len(score_history)
            
            # 计算各维度平均分
            dimensions = ["字数", "知识点引用", "大纲", "风格", "人设", "世界观", "逆向反馈", "自然度"]
            for dim in dimensions:
                scores = [s.get(dim, 0) for s in score_history if dim in s]
                metrics["avg_scores"][dim] = sum(scores) / len(scores) if scores else 0
            
            # AI感评分
            ai_scores = [s.get("ai_feeling", 0) for s in score_history if "ai_feeling" in s]
            metrics["ai_feeling_score"] = sum(ai_scores) / len(ai_scores) if ai_scores else 0
            
            # 平均迭代次数
            iterations = [s.get("iterations", 0) for s in score_history if "iterations" in s]
            metrics["avg_iterations"] = sum(iterations) / len(iterations) if iterations else 0
        
        if feedback_stats:
            metrics["feedback_count"] = feedback_stats.get("total", 0)
        
        if knowledge_stats:
            metrics["knowledge_base_size"] = knowledge_stats.get("total", 0)
        
        return metrics
    
    def _analyze_trends(self, score_history: List[Dict],
                       detailed: bool = False) -> Dict[str, Any]:
        """分析评分趋势"""
        analysis = {
            "weak_dimensions": [],
            "improving_dimensions": [],
            "declining_dimensions": [],
            "ai_feeling_trend": "stable",
            "overall_trend": "stable"
        }
        
        if not score_history or len(score_history) < 2:
            return analysis
        
        # 识别薄弱维度（平均分<0.75）
        dimensions = ["字数", "知识点引用", "大纲", "风格", "人设", "世界观", "逆向反馈", "自然度"]
        for dim in dimensions:
            scores = [s.get(dim, 0) for s in score_history if dim in s]
            if scores:
                avg_score = sum(scores) / len(scores)
                if avg_score < 0.75:
                    analysis["weak_dimensions"].append({
                        "dimension": dim,
                        "avg_score": avg_score,
                        "samples": len(scores)
                    })
        
        # 分析趋势（简单实现：比较前后两半）
        if len(score_history) >= 4:
            mid = len(score_history) // 2
            first_half = score_history[:mid]
            second_half = score_history[mid:]
            
            for dim in dimensions:
                first_avg = sum(s.get(dim, 0) for s in first_half if dim in s) / len(first_half)
                second_avg = sum(s.get(dim, 0) for s in second_half if dim in s) / len(second_half)
                
                if second_avg > first_avg + 0.05:
                    analysis["improving_dimensions"].append(dim)
                elif second_avg < first_avg - 0.05:
                    analysis["declining_dimensions"].append(dim)
        
        return analysis
    
    def _generate_recommendations(self, analysis: Dict,
                                  priority: str = "high") -> List[Dict[str, Any]]:
        """生成优化建议"""
        recommendations = []
        
        # 薄弱维度建议
        for weak_dim in analysis.get("weak_dimensions", []):
            dim = weak_dim["dimension"]
            score = weak_dim["avg_score"]
            
            rec = {
                "type": "dimension_optimization",
                "priority": "high",
                "target": dim,
                "current_score": score,
                "suggested_actions": [
                    f"提升{dim}维度权重至{score + 0.1:.2f}",
                    f"在Prompt中增加{dim}相关约束",
                    f"召回更多{dim}相关知识"
                ]
            }
            recommendations.append(rec)
        
        # AI感优化建议
        if analysis.get("ai_feeling_trend") == "increasing":
            recommendations.append({
                "type": "ai_feeling_optimization",
                "priority": "high",
                "suggested_actions": [
                    "更新AI痕迹词库",
                    "加强自然度约束",
                    "优化对话生成策略"
                ]
            })
        
        # 模块升级建议
        if priority == "high":
            recommendations.append({
                "type": "module_upgrade",
                "priority": "medium",
                "module": "iterative_generator",
                "current_version": "V2.1",
                "suggested_version": "V2.2",
                "reason": "集成AI感检测"
            })
        
        return recommendations
    
    def _save_report(self, report: Report):
        """保存报告"""
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{report.report_type}_report_{timestamp}.md"
        filepath = self.output_dir / filename
        
        # 生成Markdown内容
        content = self._generate_markdown(report)
        
        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"Saved report to {filepath}")
    
    def _generate_markdown(self, report: Report) -> str:
        """生成Markdown格式的报告"""
        md = f"""# Claw化系统{report.report_type.title()}报告

**报告时间**: {report.period_start} 至 {report.period_end}
**生成时间**: {report.timestamp}

---

## 一、核心指标

| 指标 | 数值 |
|------|:----:|
| 生成章节数 | {report.metrics.get('chapters_generated', 0)} |
| 八大维度平均分 | {sum(report.metrics.get('avg_scores', {}).values()) / 8:.2f} |
| AI感评分 | {report.metrics.get('ai_feeling_score', 0):.2f} |
| 知识库条目 | {report.metrics.get('knowledge_base_size', 0)} |
| 平均迭代次数 | {report.metrics.get('avg_iterations', 0):.1f} |
| 用户反馈数 | {report.metrics.get('feedback_count', 0)} |

## 二、薄弱维度分析

"""
        
        # 薄弱维度
        for weak_dim in report.analysis.get('weak_dimensions', []):
            md += f"""**{weak_dim['dimension']}**: 平均分 {weak_dim['avg_score']:.2f}

"""
        
        # 优化建议
        md += """## 三、优化建议

"""
        for i, rec in enumerate(report.recommendations, 1):
            md += f"### {i}. {rec['type']} ({rec['priority']})\n\n"
            if 'target' in rec:
                md += f"**目标**: {rec['target']}\n\n"
            if 'suggested_actions' in rec:
                md += "**建议措施**:\n"
                for action in rec['suggested_actions']:
                    md += f"- {action}\n"
                md += "\n"
        
        md += f"""---

**报告生成时间**: {report.timestamp}
"""
        
        return md


# 全局单例
_report_generator_instance: Optional[ReportGenerator] = None


def get_report_generator(output_dir: Optional[Path] = None) -> ReportGenerator:
    """获取报告生成器单例"""
    global _report_generator_instance
    if _report_generator_instance is None:
        _report_generator_instance = ReportGenerator(output_dir)
    return _report_generator_instance
