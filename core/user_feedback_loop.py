#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
用户反馈闭环系统 - V1.0
创建日期: 2026-03-28

用途:
- 收集用户对生成内容的反馈
- 分析反馈模式
- 触发实时优化
- 集成到GUI界面

反馈类型:
- positive: 正面反馈
- negative: 负面反馈
- suggestion: 改进建议

触发机制:
- 连续3个负面反馈 → 立即优化Prompt
- 累计10个反馈 → 生成分析报告
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

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

class UserFeedback(BaseModel):
    """用户反馈数据模型"""
    model_config = ConfigDict(frozen=False)
    
    feedback_id: str = Field(..., description="反馈ID")
    chapter_id: str = Field(..., description="章节ID")
    feedback_type: str = Field(..., description="反馈类型(positive/negative/suggestion)")
    details: str = Field(..., description="反馈详情")
    rating: Optional[float] = Field(None, description="评分(1-5)")
    user_id: str = Field("default", description="用户ID")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    processed: bool = Field(False, description="是否已处理")


class FeedbackAnalysis(BaseModel):
    """反馈分析结果数据模型"""
    model_config = ConfigDict(frozen=False)
    
    analysis_id: str = Field(..., description="分析ID")
    period_start: str = Field(..., description="统计周期开始")
    period_end: str = Field(..., description="统计周期结束")
    total_feedback: int = Field(0, description="总反馈数")
    positive_count: int = Field(0, description="正面反馈数")
    negative_count: int = Field(0, description="负面反馈数")
    suggestion_count: int = Field(0, description="建议数")
    positive_ratio: float = Field(0.0, description="正面比例")
    common_issues: List[str] = Field(default_factory=list, description="常见问题")
    improvements: List[str] = Field(default_factory=list, description="改进建议")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# 用户反馈闭环系统
# ============================================================================

class UserFeedbackLoop:
    """用户反馈闭环系统"""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.data_dir = workspace / "data"
        self.logs_dir = workspace / "logs" / "feedback"
        
        # 确保目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # 反馈存储
        self.feedback_file = self.data_dir / "user_feedback.json"
        self._init_feedback_storage()
        
        # 触发阈值
        self.negative_trigger_threshold = 3
        self.analysis_trigger_threshold = 10
    
    def collect_feedback(
        self,
        chapter_id: str,
        feedback_type: str,
        details: str,
        rating: Optional[float] = None
    ) -> str:
        """收集用户反馈"""
        
        feedback_id = f"fb-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        feedback = UserFeedback(
            feedback_id=feedback_id,
            chapter_id=chapter_id,
            feedback_type=feedback_type,
            details=details,
            rating=rating
        )
        
        # 保存反馈
        self._save_feedback(feedback)
        
        logger.info(f"[UserFeedbackLoop] 收到反馈: {feedback_id}, 类型: {feedback_type}")
        
        # 实时分析
        if feedback_type == "negative":
            self._check_negative_trigger()
        
        # 累计分析
        total_count = self._get_total_feedback_count()
        if total_count >= self.analysis_trigger_threshold:
            self._trigger_analysis()
        
        return feedback_id
    
    def analyze_feedback_patterns(self, period_days: int = 30) -> FeedbackAnalysis:
        """分析反馈模式"""
        logger.info(f"[UserFeedbackLoop] 开始分析最近{period_days}天的反馈...")
        
        # 加载反馈数据
        all_feedback = self._load_feedback()
        
        # 过滤时间范围
        period_start = (datetime.now() - timedelta(days=period_days)).isoformat()
        period_end = datetime.now().isoformat()
        
        recent_feedback = [
            fb for fb in all_feedback
            if fb["timestamp"] >= period_start
        ]
        
        # 按类型分组
        positive = [fb for fb in recent_feedback if fb["feedback_type"] == "positive"]
        negative = [fb for fb in recent_feedback if fb["feedback_type"] == "negative"]
        suggestions = [fb for fb in recent_feedback if fb["feedback_type"] == "suggestion"]
        
        # 提取高频问题
        common_issues = self._extract_common_issues(negative)
        
        # 生成改进建议
        improvements = self._generate_improvements(common_issues)
        
        # 创建分析结果
        analysis = FeedbackAnalysis(
            analysis_id=f"analysis-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            period_start=period_start,
            period_end=period_end,
            total_feedback=len(recent_feedback),
            positive_count=len(positive),
            negative_count=len(negative),
            suggestion_count=len(suggestions),
            positive_ratio=len(positive) / len(recent_feedback) if recent_feedback else 0,
            common_issues=common_issues,
            improvements=improvements
        )
        
        # 保存分析结果
        self._save_analysis(analysis)
        
        logger.info(f"[UserFeedbackLoop] 分析完成: 总反馈{analysis.total_feedback}, 正面比例{analysis.positive_ratio:.1%}")
        
        return analysis
    
    def get_recent_feedback(self, limit: int = 10) -> List[UserFeedback]:
        """获取最近反馈"""
        all_feedback = self._load_feedback()
        
        recent = sorted(all_feedback, key=lambda x: x["timestamp"], reverse=True)
        
        return [UserFeedback(**fb) for fb in recent[:limit]]
    
    # ========================================================================
    # 内部方法
    # ========================================================================
    
    def _init_feedback_storage(self):
        """初始化反馈存储"""
        if not self.feedback_file.exists():
            with open(self.feedback_file, 'w', encoding='utf-8') as f:
                json.dump({"feedback": []}, f, ensure_ascii=False, indent=2)
    
    def _save_feedback(self, feedback: UserFeedback):
        """保存反馈"""
        with open(self.feedback_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        data["feedback"].append(feedback.model_dump())
        
        with open(self.feedback_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _load_feedback(self) -> List[Dict]:
        """加载所有反馈"""
        with open(self.feedback_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return data.get("feedback", [])
    
    def _save_analysis(self, analysis: FeedbackAnalysis):
        """保存分析结果"""
        file = self.logs_dir / f"analysis_{analysis.analysis_id}.json"
        
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(analysis.model_dump(), f, ensure_ascii=False, indent=2)
    
    def _get_total_feedback_count(self) -> int:
        """获取总反馈数"""
        return len(self._load_feedback())
    
    def _check_negative_trigger(self):
        """检查负面反馈触发"""
        # 获取最近24小时的负面反馈
        recent_negative = [
            fb for fb in self._load_feedback()
            if fb["feedback_type"] == "negative"
            and datetime.fromisoformat(fb["timestamp"]) > datetime.now() - timedelta(hours=24)
        ]
        
        if len(recent_negative) >= self.negative_trigger_threshold:
            logger.warning(f"[UserFeedbackLoop] 连续{len(recent_negative)}个负面反馈，触发实时优化")
            self._trigger_immediate_optimization(recent_negative)
    
    def _trigger_immediate_optimization(self, negative_feedback: List[Dict]):
        """触发实时优化"""
        try:
            # 提取共同问题
            common_pattern = self._find_common_pattern(negative_feedback)
            
            # 调用Prompt优化器
            from .prompt_optimizer import get_prompt_optimizer
            
            optimizer = get_prompt_optimizer(self.workspace)
            
            # 找到相关模板并优化
            for template_id in ["main_generation", "chapter_generation"]:
                if template_id in optimizer.templates:
                    optimizer.optimize_prompt_template(
                        template_id=template_id,
                        issues=[common_pattern]
                    )
                    break
            
            # 记录到MEMORY.md
            self._log_immediate_action(common_pattern, negative_feedback)
            
        except Exception as e:
            logger.error(f"[UserFeedbackLoop] 实时优化失败: {e}")
    
    def _extract_common_issues(self, negative_feedback: List[Dict]) -> List[str]:
        """提取常见问题"""
        if not negative_feedback:
            return []
        
        # 简化版：提取关键词
        keywords = {}
        
        for fb in negative_feedback:
            words = fb.get("details", "").split()
            for word in words:
                if len(word) >= 2:
                    keywords[word] = keywords.get(word, 0) + 1
        
        # 返回频率最高的5个关键词
        sorted_keywords = sorted(keywords.items(), key=lambda x: x[1], reverse=True)
        
        return [word for word, count in sorted_keywords[:5]]
    
    def _generate_improvements(self, common_issues: List[str]) -> List[str]:
        """生成改进建议"""
        improvements = []
        
        issue_fixes = {
            "风格": "优化风格一致性检测，增加风格示例",
            "人设": "强化人物设定遵循机制，增加性格关键词检查",
            "知识": "增强知识库召回机制，提高知识点注入准确率",
            "连贯": "优化上下文记忆机制，增强情节连贯性检测",
            "AI感": "减少模式化表达，增加自然语言示例"
        }
        
        for issue in common_issues:
            for key, fix in issue_fixes.items():
                if key in issue:
                    improvements.append(fix)
                    break
        
        return improvements
    
    def _find_common_pattern(self, feedback_list: List[Dict]) -> str:
        """发现共同模式"""
        common_issues = self._extract_common_issues(feedback_list)
        
        if common_issues:
            return f"常见问题: {', '.join(common_issues[:3])}"
        
        return "用户反馈质量问题"
    
    def _log_immediate_action(self, pattern: str, feedback_list: List[Dict]):
        """记录实时优化行动"""
        log_entry = f"""
## 实时优化触发

**时间**: {datetime.now().isoformat()}
**触发原因**: 连续{len(feedback_list)}个负面反馈
**共同模式**: {pattern}

**涉及反馈**:
"""
        
        for fb in feedback_list[:5]:
            log_entry += f"- {fb.get('chapter_id')}: {fb.get('details')[:100]}\n"
        
        # 追加到MEMORY.md（Claw化L4档案记忆）
        memory_file = self.workspace / "Memory-Novel Writing Assistant-Agent Pro" / "MEMORY.md"
        
        # 确保目录存在
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(memory_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        logger.info(f"[UserFeedbackLoop] 实时优化记录已保存到Claw化记忆")


# ============================================================================
# 全局单例
# ============================================================================

_user_feedback_loop_instance: Optional[UserFeedbackLoop] = None


def get_user_feedback_loop(workspace: Optional[Path] = None) -> UserFeedbackLoop:
    """获取全局用户反馈闭环实例"""
    global _user_feedback_loop_instance
    
    if _user_feedback_loop_instance is None:
        if workspace is None:
            workspace = project_root
        _user_feedback_loop_instance = UserFeedbackLoop(workspace)
    
    return _user_feedback_loop_instance


# ============================================================================
# P2-建议6: 用户反馈情感分析
# ============================================================================

class FeedbackSentimentAnalyzer:
    """
    反馈情感分析器
    
    使用AI自动分析反馈文本的情感倾向，
    减少用户手动选择反馈类型的工作量。
    """
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.api_key = ""
        self.base_url = "https://api.deepseek.com"
        self.model = "deepseek-chat"
        self._load_config()
    
    def _load_config(self):
        """加载API配置"""
        try:
            import yaml
            config_file = self.workspace / "config.yaml"
            
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                
                # 获取API Key
                api_key = config.get("api_key", "")
                if api_key == "ENCRYPTED_IN_SECRETS_FILE":
                    try:
                        from core.api_key_encryption import get_api_key_encryption
                        encryption = get_api_key_encryption(self.workspace)
                        self.api_key = encryption.get_api_key("DeepSeek") or ""
                    except:
                        pass
                else:
                    self.api_key = api_key
                
                # 获取其他配置
                if "deepseek" in config and isinstance(config["deepseek"], dict):
                    self.base_url = config["deepseek"].get("base_url", self.base_url)
                
                self.model = config.get("model", self.model)
                
        except Exception as e:
            logger.warning(f"[SentimentAnalyzer] 配置加载失败: {e}")
    
    def analyze_sentiment(self, feedback_text: str) -> Dict[str, Any]:
        """
        分析反馈文本的情感倾向
        
        Args:
            feedback_text: 反馈文本
        
        Returns:
            Dict: 包含情感分析结果
        """
        if not self.api_key:
            logger.warning("[SentimentAnalyzer] API Key未配置，使用关键词分析")
            return self._keyword_based_analysis(feedback_text)
        
        try:
            from openai import OpenAI
            
            client = OpenAI(
                api_key=self.api_key,
                base_url=f"{self.base_url}/v1"
            )
            
            prompt = f"""分析以下用户反馈的情感倾向和关键问题。

反馈内容: {feedback_text}

请输出JSON格式的分析结果：
{{
  "sentiment": "positive|negative|neutral",
  "confidence": 0.95,
  "key_issues": ["风格", "连贯性"],
  "intensity": 0.8,
  "suggested_type": "positive|negative|suggestion"
}}

说明：
- sentiment: 情感倾向(正面/负面/中性)
- confidence: 置信度(0-1)
- key_issues: 提及的关键问题(最多3个)
- intensity: 情感强度(0-1)，负面情感越强值越高
- suggested_type: 建议的反馈类型

只输出JSON，不要其他内容。"""

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个情感分析专家，专门分析用户反馈的情感倾向。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            content = response.choices[0].message.content
            
            # 解析JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                result = json.loads(json_match.group(0))
                
                return {
                    "sentiment": result.get("sentiment", "neutral"),
                    "confidence": result.get("confidence", 0.5),
                    "key_issues": result.get("key_issues", []),
                    "intensity": result.get("intensity", 0.5),
                    "suggested_type": result.get("suggested_type", "suggestion"),
                    "method": "ai"
                }
            else:
                return self._keyword_based_analysis(feedback_text)
                
        except Exception as e:
            logger.warning(f"[SentimentAnalyzer] AI分析失败: {e}")
            return self._keyword_based_analysis(feedback_text)
    
    def _keyword_based_analysis(self, text: str) -> Dict[str, Any]:
        """
        基于关键词的情感分析（降级方案）
        
        当AI不可用时，使用关键词匹配进行情感分析。
        """
        # 正面关键词
        positive_keywords = [
            "好", "棒", "优秀", "满意", "喜欢", "完美", 
            "精彩", "出色", "不错", "赞", "优秀"
        ]
        
        # 负面关键词
        negative_keywords = [
            "差", "烂", "糟糕", "不满", "讨厌", "问题",
            "错误", "不好", "不行", "AI感", "生硬",
            "不一致", "矛盾", "不符合"
        ]
        
        # 建议关键词
        suggestion_keywords = [
            "建议", "希望", "能否", "可以", "如果",
            "最好", "应该", "改进", "优化"
        ]
        
        # 计算各类型得分
        positive_score = sum(1 for kw in positive_keywords if kw in text)
        negative_score = sum(1 for kw in negative_keywords if kw in text)
        suggestion_score = sum(1 for kw in suggestion_keywords if kw in text)
        
        # 提取关键问题
        key_issues = []
        issue_keywords = ["风格", "人设", "知识", "连贯", "AI感", "逻辑", "情节"]
        for kw in issue_keywords:
            if kw in text:
                key_issues.append(kw)
        
        # 判断情感类型
        if suggestion_score > 0 and positive_score == 0 and negative_score == 0:
            sentiment = "neutral"
            suggested_type = "suggestion"
        elif positive_score > negative_score:
            sentiment = "positive"
            suggested_type = "positive"
        elif negative_score > positive_score:
            sentiment = "negative"
            suggested_type = "negative"
        else:
            sentiment = "neutral"
            suggested_type = "suggestion"
        
        # 计算置信度
        total_score = positive_score + negative_score + suggestion_score
        confidence = min(0.9, 0.5 + total_score * 0.1)
        
        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "key_issues": key_issues[:3],
            "intensity": negative_score * 0.2 if sentiment == "negative" else 0.3,
            "suggested_type": suggested_type,
            "method": "keyword"
        }
    
    def batch_analyze(self, feedbacks: List[str]) -> List[Dict[str, Any]]:
        """
        批量分析反馈情感
        
        Args:
            feedbacks: 反馈文本列表
        
        Returns:
            List: 分析结果列表
        """
        results = []
        
        for i, feedback in enumerate(feedbacks):
            result = self.analyze_sentiment(feedback)
            result["index"] = i
            results.append(result)
            
            # 避免API限流
            if i > 0 and i % 5 == 0:
                import time
                time.sleep(0.5)
        
        return results
    
    def get_sentiment_summary(self, feedbacks: List[Dict]) -> Dict[str, Any]:
        """
        获取情感分析汇总
        
        Args:
            feedbacks: 反馈列表（包含details字段）
        
        Returns:
            Dict: 情感汇总统计
        """
        sentiments = {"positive": 0, "negative": 0, "neutral": 0}
        all_issues = []
        intensities = []
        
        for fb in feedbacks:
            text = fb.get("details", "")
            if not text:
                continue
            
            analysis = self.analyze_sentiment(text)
            
            sentiments[analysis["sentiment"]] += 1
            all_issues.extend(analysis["key_issues"])
            intensities.append(analysis["intensity"])
        
        # 统计关键问题频率
        issue_counts = {}
        for issue in all_issues:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
        
        # 排序
        sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "total_analyzed": sum(sentiments.values()),
            "sentiment_distribution": sentiments,
            "positive_ratio": sentiments["positive"] / sum(sentiments.values()) if sum(sentiments.values()) > 0 else 0,
            "top_issues": [issue for issue, count in sorted_issues[:5]],
            "avg_intensity": sum(intensities) / len(intensities) if intensities else 0
        }


# 全局情感分析器实例
_sentiment_analyzer_instance: Optional[FeedbackSentimentAnalyzer] = None


def get_sentiment_analyzer(workspace: Optional[Path] = None) -> FeedbackSentimentAnalyzer:
    """获取全局情感分析器实例"""
    global _sentiment_analyzer_instance
    
    if _sentiment_analyzer_instance is None:
        if workspace is None:
            workspace = project_root
        _sentiment_analyzer_instance = FeedbackSentimentAnalyzer(workspace)
    
    return _sentiment_analyzer_instance


# ============================================================================
# 主函数
# ============================================================================

def main():
    """测试入口"""
    feedback_loop = get_user_feedback_loop(project_root)
    
    print("\n" + "="*60)
    print("用户反馈闭环系统测试")
    print("="*60)
    
    # 模拟收集反馈
    feedback_id = feedback_loop.collect_feedback(
        chapter_id="chapter-001",
        feedback_type="negative",
        details="风格不一致，AI感太强",
        rating=3.0
    )
    
    print(f"\n反馈已收集: {feedback_id}")
    
    # 分析反馈
    analysis = feedback_loop.analyze_feedback_patterns()
    
    print(f"\n分析结果:")
    print(f"  总反馈: {analysis.total_feedback}")
    print(f"  正面比例: {analysis.positive_ratio:.1%}")
    print(f"  常见问题: {', '.join(analysis.common_issues)}")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    main()
