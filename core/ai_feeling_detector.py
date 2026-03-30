"""
AI感检测器 - 识别和量化文本中的"AI痕迹"

V1.0版本
创建日期：2026-03-26

核心目标：
降低生成文本的AI感，让小说更像人写的。

AI感特征（多维度检测）：
1. 机械感：重复句式、模板化开头结尾
2. 过度解释：不必要的背景交代、冗余说明
3. 情感空洞：形容词堆砌、缺乏真实感受
4. 逻辑生硬：转折突兀、因果关系牵强
5. 用词单调：高频使用AI常用词（"然而"、"但是"、"仿佛"、"似乎"）
6. 节奏呆板：句子长度均一、缺乏变化
7. 细节虚假：无法形成画面感的环境描写

评分标准：
- 0.0-0.2：几乎无AI感，读起来像人写的
- 0.3-0.5：有轻微AI感，但仍可接受
- 0.6-0.8：AI感明显，需要优化
- 0.9-1.0：AI感极强，完全不像人写的

设计参考：
- 经验文档/11.4Claw化实际运行说明✅️.md
- 《AI文本检测技术研究》
- 用户反馈数据
"""

import re
import logging
from typing import List, Dict, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AIFeelingIssue:
    """AI感问题"""
    issue_type: str  # 问题类型
    position: str    # 问题位置（原文片段）
    score: float     # 该问题严重程度 0.0-1.0
    suggestion: str  # 改进建议
    pattern: str     # 匹配的模式


@dataclass
class AIFeelingReport:
    """AI感检测报告"""
    total_score: float              # 总AI感评分（0.0-1.0，越低越好）
    naturalness_score: float        # 自然度评分（0.0-1.0，越高越好，与naturalness维度一致）
    issues: List[AIFeelingIssue]    # 检测到的问题列表
    dimension_scores: Dict[str, float]  # 各维度AI感评分
    improvement_suggestions: List[str]  # 整体改进建议
    word_count: int                 # 文本总字数
    sentence_count: int             # 句子数量
    avg_sentence_length: float      # 平均句子长度


class AIFeelingDetector:
    """AI感检测器"""
    
    # AI常用词汇（高频出现表示AI感强）
    AI_COMMON_WORDS = [
        "然而", "但是", "不过", "可是", "却",
        "仿佛", "似乎", "好像", "宛如", "如同",
        "不禁", "不由得", "忍不住", "情不自禁",
        "一股", "一种", "一阵", "一丝",
        "慢慢", "渐渐", "逐渐", "缓缓",
        "心中", "内心", "心底", "心间",
        "眼中", "眼底", "眼眸", "目光",
        "嘴角", "眉宇", "神情", "神色",
        "不知道", "不知道为什么", "莫名", "莫名其妙",
        "或许", "也许", "可能", "大概",
        "这样", "那样", "如此", "这般",
        "终于", "最终", "最后", "终究",
        "一切都", "所有", "全部", "整个"
    ]
    
    # 模板化开头
    TEMPLATE_OPENINGS = [
        r"^(这是一个|这是一|那是一个|那是一|在.*的.*里|在.*的.*中)",
        r"^(今天|明天|昨天|这天|那天).{0,5}(天气|阳光|风|雨)",
        r"^(当|随着|伴着).{0,10}(开始|结束|到来|离去)",
    ]
    
    # 模板化结尾
    TEMPLATE_ENDINGS = [
        r"(就这样|于是|因此|所以).{0,10}(结束|完结|过去|开始)$",
        r"(一切|所有|全部).{0,10}(都|都).{0,5}(了)$",
        r"(他|她|它).{0,10}(知道|明白|懂得|理解).{0,10}$",
    ]
    
    # 过度解释模式
    OVER_EXPLANATION_PATTERNS = [
        r"(因为|由于).{0,30}(所以|因此|于是).{0,30}(导致|使得|让)",
        r"(虽然|尽管).{0,30}(但是|可是|却).{0,30}(还是|仍然)",
        r"(不仅|不但).{0,30}(而且|还|并且).{0,30}(甚至|乃至)",
    ]
    
    # 情感空洞模式
    HOLLOW_EMOTION_PATTERNS = [
        r"(感到|觉得|感觉).{0,5}(一阵|一种|一股).{0,10}(涌上心头|涌上心间)",
        r"(心中|内心|心底).{0,5}(涌起|升起|升起).{0,10}(一股|一种|一阵)",
        r"(说不清|难以形容|无法言喻).{0,10}(感觉|感受|情绪)",
    ]
    
    # 机械句式
    MECHANICAL_SENTENCE_PATTERNS = [
        r"^(首先|第一).{0,20}(其次|第二).{0,20}(最后|最终)",
        r"^(不仅).{0,30}(而且).{0,30}(还)",
        r"^(一方面).{0,20}(另一方面)",
    ]
    
    def __init__(self, user_correction_history: List[Dict[str, Any]] = None):
        """
        初始化AI感检测器
        
        Args:
            user_correction_history: 用户修改历史，用于学习用户的写作偏好
        """
        self.user_correction_history = user_correction_history or []
        self.learned_patterns = self._learn_from_corrections()
        logger.info("AI感检测器初始化完成")
    
    def _learn_from_corrections(self) -> Dict[str, Any]:
        """从用户修改历史中学习"""
        learned = {
            "avoid_words": set(),
            "prefer_words": {},
            "avoid_patterns": [],
            "style_hints": []
        }
        
        if not self.user_correction_history:
            return learned
        
        # 分析用户修改模式
        for correction in self.user_correction_history:
            original = correction.get("original", "")
            corrected = correction.get("corrected", "")
            
            # 提取被删除的词汇（AI痕迹）
            original_words = set(original.split())
            corrected_words = set(corrected.split())
            removed_words = original_words - corrected_words
            
            # 记录被删除的高频词
            for word in removed_words:
                if word in self.AI_COMMON_WORDS:
                    learned["avoid_words"].add(word)
        
        logger.info(f"从用户修改中学习到 {len(learned['avoid_words'])} 个AI痕迹词汇")
        return learned
    
    def detect(self, text: str) -> AIFeelingReport:
        """
        检测文本的AI感
        
        Args:
            text: 待检测的文本
        
        Returns:
            AIFeelingReport: AI感检测报告
        """
        issues = []
        dimension_scores = {}
        
        # 1. 检测AI常用词频率
        word_score, word_issues = self._detect_ai_words(text)
        dimension_scores["词汇多样性"] = 1.0 - word_score
        issues.extend(word_issues)
        
        # 2. 检测模板化结构
        template_score, template_issues = self._detect_templates(text)
        dimension_scores["结构自然度"] = 1.0 - template_score
        issues.extend(template_issues)
        
        # 3. 检测过度解释
        explanation_score, explanation_issues = self._detect_over_explanation(text)
        dimension_scores["表达简洁性"] = 1.0 - explanation_score
        issues.extend(explanation_issues)
        
        # 4. 检测情感空洞
        emotion_score, emotion_issues = self._detect_hollow_emotions(text)
        dimension_scores["情感真实度"] = 1.0 - emotion_score
        issues.extend(emotion_issues)
        
        # 5. 检测机械句式
        mechanical_score, mechanical_issues = self._detect_mechanical_sentences(text)
        dimension_scores["句式变化度"] = 1.0 - mechanical_score
        issues.extend(mechanical_issues)
        
        # 6. 检测节奏呆板
        rhythm_score, rhythm_issues = self._detect_monotone_rhythm(text)
        dimension_scores["节奏流畅度"] = 1.0 - rhythm_score
        issues.extend(rhythm_issues)
        
        # 7. 应用用户学习模式
        if self.learned_patterns["avoid_words"]:
            user_score, user_issues = self._detect_user_learned_patterns(text)
            dimension_scores["用户偏好符合度"] = 1.0 - user_score
            issues.extend(user_issues)
        
        # 计算总体AI感评分
        weights = {
            "词汇多样性": 0.20,
            "结构自然度": 0.15,
            "表达简洁性": 0.15,
            "情感真实度": 0.20,
            "句式变化度": 0.10,
            "节奏流畅度": 0.10,
            "用户偏好符合度": 0.10
        }
        
        total_score = sum(
            (1.0 - dimension_scores.get(dim, 0.8)) * weight
            for dim, weight in weights.items()
        )
        
        # 自然度评分（与naturalness维度一致，越高越好）
        naturalness_score = 1.0 - total_score
        
        # 生成改进建议
        suggestions = self._generate_suggestions(issues, dimension_scores)
        
        # 统计信息
        sentences = re.split(r'[。！？\n]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        word_count = len(text.replace(" ", ""))
        sentence_count = len(sentences)
        avg_length = word_count / sentence_count if sentence_count > 0 else 0
        
        report = AIFeelingReport(
            total_score=min(1.0, total_score),
            naturalness_score=naturalness_score,
            issues=issues[:20],  # 只返回前20个问题，避免信息过载
            dimension_scores=dimension_scores,
            improvement_suggestions=suggestions,
            word_count=word_count,
            sentence_count=sentence_count,
            avg_sentence_length=avg_length
        )
        
        logger.info(f"AI感检测完成：总评分={total_score:.2f}, 自然度={naturalness_score:.2f}, 问题数={len(issues)}")
        
        return report
    
    def _detect_ai_words(self, text: str) -> Tuple[float, List[AIFeelingIssue]]:
        """检测AI常用词频率"""
        issues = []
        word_count = len(text.replace(" ", ""))
        
        # 统计AI常用词出现次数
        ai_word_freq = {}
        for word in self.AI_COMMON_WORDS:
            count = len(re.findall(re.escape(word), text))
            if count > 0:
                ai_word_freq[word] = count
        
        # 计算频率得分
        total_ai_words = sum(ai_word_freq.values())
        frequency = total_ai_words / (word_count / 100) if word_count > 0 else 0  # 每100字出现次数
        
        # 频率越高，AI感越强
        score = min(1.0, frequency / 3.0)  # 3次/100字为满分
        
        # 生成具体问题
        sorted_words = sorted(ai_word_freq.items(), key=lambda x: x[1], reverse=True)
        for word, count in sorted_words[:5]:  # 只报告前5个高频词
            if count >= 2:  # 至少出现2次才报告
                issues.append(AIFeelingIssue(
                    issue_type="高频AI词汇",
                    position=word,
                    score=min(1.0, count / 5.0),
                    suggestion=f'词汇"{word}"出现{count}次，建议用更丰富的表达替代',
                    pattern="高频词汇"
                ))
        
        return score, issues
    
    def _detect_templates(self, text: str) -> Tuple[float, List[AIFeelingIssue]]:
        """检测模板化结构"""
        issues = []
        scores = []
        
        # 检测开头
        for pattern in self.TEMPLATE_OPENINGS:
            if re.search(pattern, text[:100]):  # 只检查前100字
                issues.append(AIFeelingIssue(
                    issue_type="模板化开头",
                    position=text[:50],
                    score=0.7,
                    suggestion="建议用更自然的开场方式，避免套话",
                    pattern=pattern
                ))
                scores.append(0.7)
                break
        
        # 检测结尾
        for pattern in self.TEMPLATE_ENDINGS:
            if re.search(pattern, text[-100:]):  # 只检查后100字
                issues.append(AIFeelingIssue(
                    issue_type="模板化结尾",
                    position=text[-50:],
                    score=0.6,
                    suggestion="建议用更有力的收尾，避免总结性套话",
                    pattern=pattern
                ))
                scores.append(0.6)
                break
        
        avg_score = sum(scores) / len(scores) if scores else 0.0
        return avg_score, issues
    
    def _detect_over_explanation(self, text: str) -> Tuple[float, List[AIFeelingIssue]]:
        """检测过度解释"""
        issues = []
        scores = []
        
        for pattern in self.OVER_EXPLANATION_PATTERNS:
            matches = re.finditer(pattern, text)
            for match in matches:
                issues.append(AIFeelingIssue(
                    issue_type="过度解释",
                    position=match.group(),
                    score=0.6,
                    suggestion="建议简化因果关系，让读者自己领悟",
                    pattern=pattern
                ))
                scores.append(0.6)
        
        # 限制问题数量
        issues = issues[:3]
        avg_score = sum(scores[:3]) / len(scores[:3]) if scores else 0.0
        return min(1.0, avg_score * len(issues)), issues
    
    def _detect_hollow_emotions(self, text: str) -> Tuple[float, List[AIFeelingIssue]]:
        """检测情感空洞"""
        issues = []
        scores = []
        
        for pattern in self.HOLLOW_EMOTION_PATTERNS:
            matches = re.finditer(pattern, text)
            for match in matches:
                issues.append(AIFeelingIssue(
                    issue_type="情感空洞",
                    position=match.group(),
                    score=0.7,
                    suggestion="建议用具体细节和真实感受替代空洞的情感描述",
                    pattern=pattern
                ))
                scores.append(0.7)
        
        issues = issues[:3]
        avg_score = sum(scores[:3]) / len(scores[:3]) if scores else 0.0
        return min(1.0, avg_score * len(issues)), issues
    
    def _detect_mechanical_sentences(self, text: str) -> Tuple[float, List[AIFeelingIssue]]:
        """检测机械句式"""
        issues = []
        scores = []
        
        for pattern in self.MECHANICAL_SENTENCE_PATTERNS:
            if re.search(pattern, text):
                issues.append(AIFeelingIssue(
                    issue_type="机械句式",
                    position=re.search(pattern, text).group(),
                    score=0.8,
                    suggestion="建议打破固定句式结构，增加表达灵活性",
                    pattern=pattern
                ))
                scores.append(0.8)
        
        issues = issues[:2]
        avg_score = sum(scores[:2]) / len(scores[:2]) if scores else 0.0
        return avg_score, issues
    
    def _detect_monotone_rhythm(self, text: str) -> Tuple[float, List[AIFeelingIssue]]:
        """检测节奏呆板"""
        sentences = re.split(r'[。！？\n]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) < 3:
            return 0.0, []
        
        # 计算句子长度分布
        lengths = [len(s) for s in sentences]
        avg_length = sum(lengths) / len(lengths)
        
        # 计算标准差（标准差越小，节奏越呆板）
        variance = sum((l - avg_length) ** 2 for l in lengths) / len(lengths)
        std_dev = variance ** 0.5
        
        # 标准差小于平均长度的20%视为呆板
        monotonicity = max(0.0, 1.0 - (std_dev / (avg_length * 0.2 + 1)))
        
        issues = []
        if monotonicity > 0.5:
            issues.append(AIFeelingIssue(
                issue_type="节奏呆板",
                position=f"平均句长{avg_length:.1f}字，标准差{std_dev:.1f}",
                score=monotonicity,
                suggestion="建议增加句子长度变化，长短句结合营造节奏感",
                pattern="句式长度单一"
            ))
        
        return monotonicity, issues
    
    def _detect_user_learned_patterns(self, text: str) -> Tuple[float, List[AIFeelingIssue]]:
        """检测用户学习到的AI痕迹"""
        issues = []
        avoid_words = self.learned_patterns.get("avoid_words", set())
        
        if not avoid_words:
            return 0.0, []
        
        found_words = []
        for word in avoid_words:
            if word in text:
                found_words.append(word)
        
        if found_words:
            issues.append(AIFeelingIssue(
                issue_type="用户标记的AI痕迹",
                position=", ".join(found_words[:5]),
                score=0.8,
                suggestion="这些词汇是您之前修改过的，建议替换",
                pattern="用户学习模式"
            ))
        
        score = min(1.0, len(found_words) / 5.0)
        return score, issues
    
    def _generate_suggestions(self, issues: List[AIFeelingIssue], 
                            dimension_scores: Dict[str, float]) -> List[str]:
        """生成改进建议"""
        suggestions = []
        
        # 找出最薄弱的维度
        weak_dimensions = sorted(
            dimension_scores.items(),
            key=lambda x: x[1]
        )[:3]
        
        for dim, score in weak_dimensions:
            if score < 0.7:
                if dim == "词汇多样性":
                    suggestions.append("减少AI常用词使用，增加同义词替换和个性化表达")
                elif dim == "结构自然度":
                    suggestions.append("避免模板化开头结尾，用更自然的方式引入和收尾")
                elif dim == "表达简洁性":
                    suggestions.append("减少过度解释，让读者自己领悟因果关系")
                elif dim == "情感真实度":
                    suggestions.append("用具体细节替代空洞的情感描述，增加真实感受")
                elif dim == "句式变化度":
                    suggestions.append("打破固定句式结构，增加表达灵活性")
                elif dim == "节奏流畅度":
                    suggestions.append("增加句子长度变化，长短句结合营造节奏感")
        
        # 根据具体问题给出针对性建议
        high_score_issues = [i for i in issues if i.score > 0.7]
        if high_score_issues:
            suggestions.append(f"重点关注：{high_score_issues[0].suggestion}")
        
        return suggestions[:5]  # 最多返回5条建议
    
    def update_from_user_correction(self, original: str, corrected: str):
        """
        从用户修改中学习
        
        Args:
            original: 原始文本
            corrected: 用户修改后的文本
        """
        self.user_correction_history.append({
            "original": original,
            "corrected": corrected,
            "timestamp": str(datetime.now())
        })
        
        # 重新学习
        self.learned_patterns = self._learn_from_corrections()
        logger.info(f"已从用户修改中学习，当前AI痕迹词汇库：{len(self.learned_patterns['avoid_words'])}个")
    
    # 兼容性别名方法
    def get_ai_feeling_score(self, text: str) -> float:
        """
        获取AI感评分（兼容性别名）
        
        Args:
            text: 待检测文本
            
        Returns:
            AI感评分（0.0-1.0，越低越好）
        """
        report = self.detect(text)
        return report.total_score
    
    def get_ai_words(self, text: str) -> List[str]:
        """
        获取AI痕迹词汇列表（兼容性别名）
        
        Args:
            text: 待检测文本
            
        Returns:
            AI痕迹词汇列表
        """
        report = self.detect(text)
        ai_words = []
        for issue in report.issues:
            if issue.issue_type == "高频AI词汇":
                ai_words.append(issue.position)
        return ai_words


# 工具函数
def detect_ai_feeling(text: str, user_correction_history: List[Dict] = None) -> AIFeelingReport:
    """
    快速检测文本AI感
    
    Args:
        text: 待检测文本
        user_correction_history: 用户修改历史
    
    Returns:
        AIFeelingReport: 检测报告
    """
    detector = AIFeelingDetector(user_correction_history)
    return detector.detect(text)


if __name__ == "__main__":
    # 测试用例
    test_text = """
    这是一个阳光明媚的早晨，阳光洒进房间，仿佛给一切都镀上了金边。
    
    他心中涌起一股难以形容的情绪，仿佛有什么东西在心底慢慢升腾。
    他不知道为什么，莫名的感到一阵心酸，眼底闪过一丝复杂的神色。
    
    然而，他终究还是缓缓开口："我不由得想起了那个下雨的下午..."
    嘴角微微上扬，但眼神中却有一丝说不清的哀伤。
    """
    
    detector = AIFeelingDetector()
    report = detector.detect(test_text)
    
    print(f"\n=== AI感检测报告 ===")
    print(f"总AI感评分: {report.total_score:.2f} (越低越好)")
    print(f"自然度评分: {report.naturalness_score:.2f} (越高越好)")
    print(f"\n维度评分:")
    for dim, score in report.dimension_scores.items():
        print(f"  - {dim}: {score:.2f}")
    
    print(f"\n发现的问题 ({len(report.issues)}个):")
    for issue in report.issues:
        print(f"  [{issue.issue_type}] {issue.position}")
        print(f"    → {issue.suggestion}")
    
    print(f"\n改进建议:")
    for i, suggestion in enumerate(report.improvement_suggestions, 1):
        print(f"  {i}. {suggestion}")
