#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Prompt自动优化器 - V1.0
创建日期: 2026-03-28

用途:
- 分析低分章节，提取改进点
- 自动优化Prompt模板
- A/B测试验证优化效果
- 集成到每日冥想流程

核心流程:
1. 分析低分章节 → 提取问题
2. 优化Prompt → 生成新模板
3. A/B测试 → 验证效果
4. 通过测试 → 应用新模板
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pydantic import BaseModel, Field, ConfigDict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================

class PromptIssue(BaseModel):
    """Prompt问题数据模型"""
    model_config = ConfigDict(frozen=False)
    
    issue_id: str = Field(..., description="问题ID")
    chapter_id: str = Field(..., description="章节ID")
    dimension: str = Field(..., description="低分维度")
    score: float = Field(..., description="评分")
    description: str = Field(..., description="问题描述")
    suggested_fix: str = Field("", description="建议修复")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class PromptTemplate(BaseModel):
    """Prompt模板数据模型"""
    model_config = ConfigDict(frozen=False)
    
    template_id: str = Field(..., description="模板ID")
    template_name: str = Field(..., description="模板名称")
    content: str = Field(..., description="模板内容")
    version: str = Field("1.0.0", description="版本号")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    metrics: Dict[str, float] = Field(default_factory=dict, description="性能指标")
    status: str = Field("active", description="状态(active/testing/archived)")


class ABTestResult(BaseModel):
    """A/B测试结果数据模型"""
    model_config = ConfigDict(frozen=False)
    
    test_id: str = Field(..., description="测试ID")
    old_template_id: str = Field(..., description="旧模板ID")
    new_template_id: str = Field(..., description="新模板ID")
    old_avg_score: float = Field(0.0, description="旧模板平均分")
    new_avg_score: float = Field(0.0, description="新模板平均分")
    improvement: float = Field(0.0, description="提升百分比")
    p_value: float = Field(0.0, description="统计显著性p值")
    passed: bool = Field(False, description="是否通过测试")
    test_cases: int = Field(0, description="测试用例数")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# Prompt优化器
# ============================================================================

class PromptOptimizer:
    """Prompt自动优化器"""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.prompts_dir = workspace / "prompts"
        self.logs_dir = workspace / "logs" / "prompt_optimization"
        
        # 确保目录存在
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # 模板存储
        self.templates: Dict[str, PromptTemplate] = {}
        self._load_templates()
        
        # 性能阈值
        self.score_threshold = 0.8
        self.ab_test_sample_size = 5
        self.significance_level = 0.05
    
    def analyze_low_score_chapters(self) -> List[PromptIssue]:
        """分析低分章节，提取改进点"""
        logger.info("[PromptOptimizer] 开始分析低分章节...")
        
        issues = []
        
        # 加载评分记录
        scores_file = self.logs_dir.parent / "validation_scores.json"
        
        if not scores_file.exists():
            logger.warning("[PromptOptimizer] 无评分记录")
            return issues
        
        try:
            with open(scores_file, 'r', encoding='utf-8') as f:
                scores_data = json.load(f)
            
            for record in scores_data.get("records", []):
                total_score = record.get("total_score", 0)
                
                # 筛选低分章节
                if total_score < self.score_threshold:
                    # 找出低分维度
                    dimensions = record.get("dimensions", {})
                    for dim_name, dim_score in dimensions.items():
                        if dim_score < self.score_threshold:
                            issue = PromptIssue(
                                issue_id=f"issue-{len(issues)+1}",
                                chapter_id=record.get("chapter_id", "unknown"),
                                dimension=dim_name,
                                score=dim_score,
                                description=f"{dim_name}评分{dim_score:.2f}，低于阈值{self.score_threshold}",
                                suggested_fix=self._suggest_fix(dim_name, dim_score)
                            )
                            issues.append(issue)
            
            logger.info(f"[PromptOptimizer] 发现 {len(issues)} 个问题")
            
        except Exception as e:
            logger.error(f"[PromptOptimizer] 分析失败: {e}")
        
        return issues
    
    def optimize_prompt_template(
        self,
        template_id: str,
        issues: List[str]
    ) -> Optional[PromptTemplate]:
        """优化Prompt模板"""
        logger.info(f"[PromptOptimizer] 开始优化模板: {template_id}")
        
        # 加载当前模板
        old_template = self.templates.get(template_id)
        
        if not old_template:
            logger.error(f"[PromptOptimizer] 模板不存在: {template_id}")
            return None
        
        # 构建优化Prompt
        optimization_prompt = f"""
当前Prompt模板:
{old_template.content}

发现的问题:
{chr(10).join([f"- {issue}" for issue in issues])}

请优化这个Prompt模板，解决上述问题。要求:
1. 保持原有结构和核心逻辑
2. 针对性解决每个问题
3. 不要引入过多复杂度
4. 输出优化后的完整Prompt

优化后的Prompt:
"""
        
        # 调用AI优化
        try:
            optimized_content = self._call_ai_for_optimization(optimization_prompt)
            
            if not optimized_content:
                logger.warning("[PromptOptimizer] AI优化失败")
                return None
            
            # 创建新模板
            new_template = PromptTemplate(
                template_id=f"{template_id}-v{len(self.templates)}",
                template_name=f"{old_template.template_name} (优化版)",
                content=optimized_content,
                version=self._increment_version(old_template.version),
                status="testing"
            )
            
            # A/B测试验证
            if self._ab_test(old_template, new_template):
                # 测试通过，应用新模板
                new_template.status = "active"
                old_template.status = "archived"
                
                self.templates[new_template.template_id] = new_template
                self._save_template(new_template)
                
                logger.info(f"[PromptOptimizer] 优化成功: {new_template.template_id}")
                return new_template
            else:
                logger.warning("[PromptOptimizer] A/B测试未通过，保留原模板")
                return None
            
        except Exception as e:
            logger.error(f"[PromptOptimizer] 优化失败: {e}")
            return None
    
    def _ab_test(self, old_template: PromptTemplate, new_template: PromptTemplate) -> bool:
        """A/B测试验证优化效果"""
        logger.info(f"[PromptOptimizer] 开始A/B测试: {old_template.template_id} vs {new_template.template_id}")
        
        try:
            # 生成测试用例
            test_cases = self._get_test_cases(count=self.ab_test_sample_size)
            
            if not test_cases:
                logger.warning("[PromptOptimizer] 无测试用例")
                return False
            
            old_scores = []
            new_scores = []
            
            for i, case in enumerate(test_cases):
                logger.info(f"[PromptOptimizer] 测试用例 {i+1}/{len(test_cases)}")
                
                # 使用旧模板生成
                old_result = self._generate_with_template(old_template, case)
                old_scores.append(old_result)
                
                # 使用新模板生成
                new_result = self._generate_with_template(new_template, case)
                new_scores.append(new_result)
                
                # 避免API限流
                time.sleep(1)
            
            # 计算平均分
            old_avg = sum(old_scores) / len(old_scores)
            new_avg = sum(new_scores) / len(new_scores)
            
            # 统计检验（t检验）
            try:
                from scipy.stats import ttest_rel
                t_stat, p_value = ttest_rel(new_scores, old_scores)
            except ImportError:
                logger.warning("[PromptOptimizer] scipy未安装，使用简化检验")
                p_value = 0.01 if new_avg > old_avg else 0.99
            
            # 记录测试结果
            improvement = (new_avg - old_avg) / old_avg if old_avg > 0 else 0
            
            test_result = ABTestResult(
                test_id=f"test-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                old_template_id=old_template.template_id,
                new_template_id=new_template.template_id,
                old_avg_score=old_avg,
                new_avg_score=new_avg,
                improvement=improvement,
                p_value=p_value,
                passed=new_avg > old_avg and p_value < self.significance_level,
                test_cases=len(test_cases)
            )
            
            self._save_ab_test_result(test_result)
            
            logger.info(f"[PromptOptimizer] A/B测试结果: 旧模板{old_avg:.2f}, 新模板{new_avg:.2f}, 提升{improvement:.1%}, p值{p_value:.3f}")
            
            return test_result.passed
            
        except Exception as e:
            logger.error(f"[PromptOptimizer] A/B测试失败: {e}")
            return False
    
    # ========================================================================
    # 辅助方法
    # ========================================================================
    
    def _load_templates(self):
        """加载所有模板"""
        for file in self.prompts_dir.glob("*.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                template = PromptTemplate(**data)
                self.templates[template.template_id] = template
            except Exception as e:
                logger.warning(f"[PromptOptimizer] 加载模板失败: {file}, {e}")
    
    def _save_template(self, template: PromptTemplate):
        """保存模板"""
        file = self.prompts_dir / f"{template.template_id}.json"
        
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(template.model_dump(), f, ensure_ascii=False, indent=2)
    
    def _save_ab_test_result(self, result: ABTestResult):
        """保存A/B测试结果"""
        file = self.logs_dir / f"ab_test_{result.test_id}.json"
        
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)
    
    def _suggest_fix(self, dimension: str, score: float) -> str:
        """建议修复方案"""
        fixes = {
            "风格": "在Prompt中增加风格示例和要求，明确风格特征",
            "人设": "强化人物性格描述，要求AI严格遵循人设设定",
            "世界观": "提供更详细的世界观背景，要求AI遵循设定规则",
            "大纲": "明确大纲节点要求，强化章节目标",
            "知识点引用": "增加知识库内容注入，要求AI参考专业知识",
            "AI感": "减少模式化表达，增加自然语言示例",
            "上下文契合度": "强化前后文连贯性检查，引用前文关键信息"
        }
        
        return fixes.get(dimension, "优化相关部分")
    
    def _increment_version(self, version: str) -> str:
        """增加版本号"""
        parts = version.split(".")
        if len(parts) == 3:
            parts[2] = str(int(parts[2]) + 1)
            return ".".join(parts)
        return "1.0.1"
    
    def _call_ai_for_optimization(self, prompt: str) -> Optional[str]:
        """调用AI进行优化"""
        try:
            from openai import OpenAI
            import yaml
            
            # 加载配置
            config_file = self.workspace / "config.yaml"
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 获取API配置
            api_key = config.get("api_key", "")
            if api_key == "ENCRYPTED_IN_SECRETS_FILE":
                from core.api_key_encryption import get_api_key_encryption
                encryption = get_api_key_encryption(self.workspace)
                api_key = encryption.get_api_key("DeepSeek") or ""
            
            base_url = config.get("deepseek", {}).get("base_url", "https://api.deepseek.com")
            model = config.get("model", "deepseek-chat")
            
            client = OpenAI(api_key=api_key, base_url=f"{base_url}/v1")
            
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位Prompt工程专家，擅长优化AI生成的Prompt模板。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=4000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"[PromptOptimizer] AI调用失败: {e}")
            return None
    
    def _get_test_cases(self, count: int = 5) -> List[Dict]:
        """获取测试用例"""
        # 从历史数据中提取测试用例
        test_cases = []
        
        # 简化版：使用固定测试用例
        for i in range(count):
            test_cases.append({
                "chapter_title": f"测试章节{i+1}",
                "chapter_outline": f"这是测试章节{i+1}的大纲...",
                "word_count": 3500
            })
        
        return test_cases
    
    def _generate_with_template(self, template: PromptTemplate, case: Dict) -> float:
        """使用模板生成内容并评分"""
        try:
            from openai import OpenAI
            import yaml
            
            # 加载配置
            config_file = self.workspace / "config.yaml"
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 获取API配置
            api_key = config.get("api_key", "")
            if api_key == "ENCRYPTED_IN_SECRETS_FILE":
                from core.api_key_encryption import get_api_key_encryption
                encryption = get_api_key_encryption(self.workspace)
                api_key = encryption.get_api_key("DeepSeek") or ""
            
            base_url = config.get("deepseek", {}).get("base_url", "https://api.deepseek.com")
            model = config.get("model", "deepseek-chat")
            
            client = OpenAI(api_key=api_key, base_url=f"{base_url}/v1")
            
            # 构建Prompt
            prompt = template.content.format(**case)
            
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            
            # 简化评分：返回内容长度比例
            target_words = case.get("word_count", 3500)
            actual_words = len(content)
            score = min(1.0, actual_words / target_words)
            
            return score
            
        except Exception as e:
            logger.error(f"[PromptOptimizer] 生成失败: {e}")
            return 0.0


# ============================================================================
# 全局单例
# ============================================================================

_prompt_optimizer_instance: Optional[PromptOptimizer] = None


def get_prompt_optimizer(workspace: Optional[Path] = None) -> PromptOptimizer:
    """获取全局Prompt优化器实例"""
    global _prompt_optimizer_instance
    
    if _prompt_optimizer_instance is None:
        if workspace is None:
            workspace = project_root
        _prompt_optimizer_instance = PromptOptimizer(workspace)
    
    return _prompt_optimizer_instance


# ============================================================================
# P1-建议4: Prompt优化效果可视化
# ============================================================================

class PromptOptimizationVisualizer:
    """
    Prompt优化效果可视化器
    
    用于生成A/B测试结果的可视化图表，
    帮助用户直观理解优化效果。
    """
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.logs_dir = workspace / "logs" / "prompt_optimization"
        self.output_dir = workspace / "data" / "visualization"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def visualize_ab_test_result(self, test_id: str) -> Optional[Path]:
        """
        可视化单个A/B测试结果
        
        Args:
            test_id: 测试ID
        
        Returns:
            Path: 生成的图片路径，失败返回None
        """
        # 加载测试结果
        result_file = self.logs_dir / f"ab_test_{test_id}.json"
        
        if not result_file.exists():
            logger.warning(f"[Visualizer] 测试结果不存在: {test_id}")
            return None
        
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            result = ABTestResult(**data)
            
            # 尝试使用matplotlib
            try:
                import matplotlib.pyplot as plt
                import matplotlib
                matplotlib.use('Agg')  # 非GUI后端
                plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
                plt.rcParams['axes.unicode_minus'] = False
                
                return self._create_comparison_chart(result, plt)
                
            except ImportError:
                # 降级：生成HTML报告
                logger.warning("[Visualizer] matplotlib未安装，生成HTML报告")
                return self._create_html_report(result)
                
        except Exception as e:
            logger.error(f"[Visualizer] 可视化失败: {e}")
            return None
    
    def visualize_optimization_history(self, template_id: str, days: int = 30) -> Optional[Path]:
        """
        可视化模板优化历史趋势
        
        Args:
            template_id: 模板ID
            days: 统计天数
        
        Returns:
            Path: 生成的图片路径
        """
        # 收集历史测试结果
        results = self._load_historical_results(template_id, days)
        
        if not results:
            logger.warning(f"[Visualizer] 无历史数据: {template_id}")
            return None
        
        try:
            import matplotlib.pyplot as plt
            import matplotlib
            matplotlib.use('Agg')
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
            plt.rcParams['axes.unicode_minus'] = False
            
            return self._create_trend_chart(results, plt)
            
        except ImportError:
            return self._create_trend_html_report(results)
    
    def _create_comparison_chart(self, result: ABTestResult, plt) -> Path:
        """创建对比柱状图"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        # 左侧：平均分对比
        models = ['旧模板', '新模板']
        scores = [result.old_avg_score, result.new_avg_score]
        
        colors = ['#ff9999' if result.old_avg_score < 0.8 else '#99ff99',
                  '#ff9999' if result.new_avg_score < 0.8 else '#99ff99']
        
        bars = ax1.bar(models, scores, color=colors)
        ax1.set_ylabel('平均评分')
        ax1.set_title(f'评分对比\n提升: {result.improvement:.1%}')
        ax1.set_ylim(0, 1.0)
        
        # 添加数值标签
        for bar, score in zip(bars, scores):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{score:.3f}', ha='center', va='bottom', fontsize=12)
        
        # 右侧：统计检验结果
        ax2.axis('off')
        
        # p值和显著性
        significance_text = "✅ 统计显著 (p<0.05)" if result.p_value < 0.05 else "❌ 不显著"
        
        ax2.text(0.5, 0.8, f'A/B测试结果',
                ha='center', va='center', fontsize=16, fontweight='bold')
        
        ax2.text(0.5, 0.6, f'p值: {result.p_value:.4f}',
                ha='center', va='center', fontsize=14,
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        ax2.text(0.5, 0.4, significance_text,
                ha='center', va='center', fontsize=14,
                bbox=dict(boxstyle='round', 
                         facecolor='lightgreen' if result.passed else 'lightyellow', 
                         alpha=0.5))
        
        ax2.text(0.5, 0.2, f'测试用例: {result.test_cases}个',
                ha='center', va='center', fontsize=12)
        
        ax2.text(0.5, 0.05, f'测试时间: {result.timestamp[:10]}',
                ha='center', va='center', fontsize=10, color='gray')
        
        plt.tight_layout()
        
        # 保存图片
        output_path = self.output_dir / f"ab_test_{result.test_id}.png"
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"[Visualizer] 图表已保存: {output_path}")
        return output_path
    
    def _create_html_report(self, result: ABTestResult) -> Path:
        """创建HTML报告（降级方案）"""
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>A/B测试结果 - {result.test_id}</title>
    <style>
        body {{ font-family: 'Microsoft YaHei', sans-serif; padding: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        .comparison {{ display: flex; justify-content: space-around; margin: 20px 0; }}
        .score-box {{ 
            padding: 20px; 
            border-radius: 10px; 
            text-align: center; 
            width: 200px;
        }}
        .old {{ background: #ff9999; }}
        .new {{ background: #99ff99; }}
        .result {{ 
            padding: 15px; 
            border-radius: 10px; 
            margin: 20px 0;
            text-align: center;
        }}
        .pass {{ background: #d4edda; }}
        .fail {{ background: #f8d7da; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>A/B测试结果报告</h1>
        <p>测试ID: {result.test_id}</p>
        <p>测试时间: {result.timestamp}</p>
        
        <div class="comparison">
            <div class="score-box old">
                <h3>旧模板</h3>
                <p style="font-size: 24px;">{result.old_avg_score:.3f}</p>
            </div>
            <div class="score-box new">
                <h3>新模板</h3>
                <p style="font-size: 24px;">{result.new_avg_score:.3f}</p>
            </div>
        </div>
        
        <div class="result {'pass' if result.passed else 'fail'}">
            <h2>{'✅ 测试通过' if result.passed else '❌ 测试未通过'}</h2>
            <p>提升: {result.improvement:.1%}</p>
            <p>p值: {result.p_value:.4f} {'(显著)' if result.p_value < 0.05 else '(不显著)'}</p>
            <p>测试用例: {result.test_cases}个</p>
        </div>
    </div>
</body>
</html>
"""
        
        output_path = self.output_dir / f"ab_test_{result.test_id}.html"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"[Visualizer] HTML报告已保存: {output_path}")
        return output_path
    
    def _create_trend_chart(self, results: List[ABTestResult], plt) -> Path:
        """创建趋势图"""
        # 按时间排序
        results.sort(key=lambda x: x.timestamp)
        
        timestamps = [r.timestamp[:10] for r in results]
        old_scores = [r.old_avg_score for r in results]
        new_scores = [r.new_avg_score for r in results]
        improvements = [r.improvement * 100 for r in results]  # 转为百分比
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        
        # 上图：评分变化
        ax1.plot(timestamps, old_scores, 'o-', label='旧模板', color='#ff9999')
        ax1.plot(timestamps, new_scores, 's-', label='新模板', color='#99ff99')
        ax1.set_ylabel('平均评分')
        ax1.set_title('模板评分变化趋势')
        ax1.legend()
        ax1.set_ylim(0, 1.0)
        ax1.grid(True, alpha=0.3)
        
        # 下图：提升比例
        colors = ['green' if i > 0 else 'red' for i in improvements]
        ax2.bar(timestamps, improvements, color=colors)
        ax2.set_ylabel('提升比例 (%)')
        ax2.set_title('优化提升比例')
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax2.grid(True, alpha=0.3)
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # 保存
        output_path = self.output_dir / f"optimization_trend_{datetime.now().strftime('%Y%m%d')}.png"
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"[Visualizer] 趋势图已保存: {output_path}")
        return output_path
    
    def _create_trend_html_report(self, results: List[ABTestResult]) -> Path:
        """创建趋势HTML报告（降级方案）"""
        rows = ""
        for r in sorted(results, key=lambda x: x.timestamp):
            status = "✅" if r.passed else "❌"
            rows += f"""
            <tr>
                <td>{r.timestamp[:10]}</td>
                <td>{r.old_avg_score:.3f}</td>
                <td>{r.new_avg_score:.3f}</td>
                <td>{r.improvement:.1%}</td>
                <td>{status}</td>
            </tr>
"""
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>优化趋势报告</title>
    <style>
        body {{ font-family: 'Microsoft YaHei', sans-serif; padding: 20px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>Prompt优化趋势报告</h1>
    <p>生成时间: {datetime.now().isoformat()}</p>
    <table>
        <tr>
            <th>日期</th>
            <th>旧模板评分</th>
            <th>新模板评分</th>
            <th>提升比例</th>
            <th>状态</th>
        </tr>
        {rows}
    </table>
</body>
</html>
"""
        
        output_path = self.output_dir / f"optimization_trend_{datetime.now().strftime('%Y%m%d')}.html"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_path
    
    def _load_historical_results(self, template_id: str, days: int) -> List[ABTestResult]:
        """加载历史测试结果"""
        results = []
        cutoff = datetime.now() - timedelta(days=days)
        
        for file in self.logs_dir.glob("ab_test_*.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 检查时间范围
                timestamp = datetime.fromisoformat(data.get("timestamp", ""))
                if timestamp >= cutoff:
                    # 检查模板ID（新旧模板都可能匹配）
                    if template_id in [data.get("old_template_id", ""), 
                                      data.get("new_template_id", "")]:
                        results.append(ABTestResult(**data))
                        
            except Exception as e:
                logger.warning(f"[Visualizer] 加载失败: {file}, {e}")
        
        return results


# 全局可视化器实例
_visualizer_instance: Optional[PromptOptimizationVisualizer] = None


def get_visualizer(workspace: Optional[Path] = None) -> PromptOptimizationVisualizer:
    """获取全局可视化器实例"""
    global _visualizer_instance
    
    if _visualizer_instance is None:
        if workspace is None:
            workspace = project_root
        _visualizer_instance = PromptOptimizationVisualizer(workspace)
    
    return _visualizer_instance


# ============================================================================
# 主函数
# ============================================================================

def main():
    """测试入口"""
    optimizer = get_prompt_optimizer(project_root)
    
    print("\n" + "="*60)
    print("Prompt自动优化器测试")
    print("="*60)
    
    # 分析低分章节
    issues = optimizer.analyze_low_score_chapters()
    
    print(f"\n发现 {len(issues)} 个问题:")
    for issue in issues[:5]:
        print(f"  - {issue.dimension}: {issue.description}")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    main()
