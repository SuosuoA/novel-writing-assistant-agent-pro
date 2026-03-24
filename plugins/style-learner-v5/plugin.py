"""
风格学习器插件 V5.0

版本: 5.0.0
创建日期: 2026-03-23
迁移来源: V5 scripts/enhanced_style_learner_v2.py

功能:
- 深度分析词汇特征（高频词、低频词、专有名词、情感词）
- 句式模式识别（倒装句、排比句、设问句等）
- 修辞手法识别（比喻、拟人、夸张、对偶等）
- 节奏风格分析（长短句交替、段落节奏）
- 视角分析（第一人称、第三人称）
- 时空特征分析（时空转换、场景描写）
- 情感色彩分析（情感倾向、情绪波动）
- 语言风格分类（文白、口语、雅俗等）

参考文档:
- 《项目总体架构设计说明书V1.3》第四章
- 《插件接口定义V2.1》
"""

import os
import re
import json
import yaml
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from collections import Counter, defaultdict

import sys
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.plugin_interface import AnalyzerPlugin, PluginMetadata, PluginType, PluginContext

# 可选依赖检测
try:
    import jieba
    import jieba.posseg as pseg
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False


@dataclass
class VocabularyDepth:
    """词汇深度分析"""
    high_frequency_words: List[Tuple[str, int]]
    low_frequency_words: List[Tuple[str, int]]
    proper_nouns: List[str]
    emotion_words: Dict[str, int]
    action_verbs: List[Tuple[str, int]]
    sensory_words: Dict[str, List[str]]


@dataclass
class SentencePatterns:
    """句式模式分析"""
    parallel_sentences: List[str]
    rhetorical_questions: List[str]
    inverted_sentences: List[str]
    conditional_sentences: List[str]
    short_sentences_ratio: float
    long_sentences_ratio: float
    sentence_rhythm: str


@dataclass
class RhetoricalDevices:
    """修辞手法识别"""
    metaphors: List[str]
    personifications: List[str]
    hyperboles: List[str]
    contrasts: List[str]
    parallelisms: List[str]
    rhetorical_total: int
    rhetorical_density: float


@dataclass
class NarrativeStyle:
    """叙事风格分析"""
    perspective: str
    tense: str
    scene_descriptions: List[str]
    temporal_markers: List[str]
    spatial_markers: List[str]
    narrative_pace: str


@dataclass
class EmotionalTone:
    """情感色彩分析"""
    overall_sentiment: str
    sentiment_distribution: Dict[str, float]
    emotional_intensity: float
    mood_changes: List[Tuple[int, str]]


@dataclass
class LanguageStyle:
    """语言风格分类"""
    register: str
    formality: float
    colloquialisms: List[str]
    archaisms: List[str]
    idioms: List[str]
    foreign_words: List[str]


@dataclass
class PacingStyle:
    """节奏风格分析"""
    overall_pace: str
    paragraph_rhythm: List[int]
    sentence_length_variance: float
    dialogue_intervals: List[int]
    action_intervals: List[int]


@dataclass
class EnhancedStyleProfile:
    """增强版风格档案"""
    author_name: str
    genre: str
    created_date: str
    sample_size_chars: int
    vocabulary_depth: Dict
    sentence_patterns: Dict
    rhetorical_devices: Dict
    narrative_style: Dict
    emotional_tone: Dict
    language_style: Dict
    pacing_style: Dict
    style_tags: List[str]
    writing_characteristics: List[str]
    similar_authors: List[str]
    prompt_suggestions: List[str]


class StyleLearnerPlugin(AnalyzerPlugin):
    """风格学习器插件 - V5核心模块迁移

    实现 AnalyzerPlugin 接口，提供深度风格分析功能。

    分析类型:
    - style: 完整风格分析
    - vocabulary: 词汇深度分析
    - sentence: 句式模式分析
    - rhetoric: 修辞手法识别
    - narrative: 叙事风格分析
    - emotion: 情感色彩分析

    支持格式:
    - txt: 纯文本
    - json: JSON格式风格档案
    """

    PLUGIN_ID = "style-learner-v5"
    PLUGIN_NAME = "风格学习器 V5"
    PLUGIN_VERSION = "5.0.0"

    def __init__(self):
        """初始化插件"""
        metadata = PluginMetadata(
            id=self.PLUGIN_ID,
            name=self.PLUGIN_NAME,
            version=self.PLUGIN_VERSION,
            description="深度风格分析，包括词汇特征、句式模式、修辞手法、情感色彩等",
            author="项目组",
            plugin_type=PluginType.ANALYZER,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=["style-learner-v1", "style-learner-v2"],
            permissions=["file.read"],
            min_platform_version="6.0.0",
            entry_class="StyleLearnerPlugin",
        )
        super().__init__(metadata)
        
        self._config = {}
        self._pos_tagger = None
        self._emotion_dict = {}
        self._idiom_patterns = []
        self._logger = logging.getLogger(__name__)

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据"""
        return PluginMetadata(
            id=cls.PLUGIN_ID,
            name=cls.PLUGIN_NAME,
            version=cls.PLUGIN_VERSION,
            description="深度风格分析，包括词汇特征、句式模式、修辞手法、情感色彩等",
            author="项目组",
            plugin_type=PluginType.ANALYZER,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=["style-learner-v1", "style-learner-v2"],
            permissions=["file.read"],
            min_platform_version="6.0.0",
            entry_class="StyleLearnerPlugin",
        )

    def initialize(self, context: PluginContext) -> bool:
        """初始化插件"""
        if not super().initialize(context):
            return False

        # 加载配置
        self._config = self._load_config()
        
        # 初始化词性标注
        if HAS_JIEBA:
            self._pos_tagger = pseg
        
        # 初始化情感词典
        self._init_emotion_dict()
        
        # 初始化成语词典
        self._init_idiom_dict()
        
        return True

    def _load_config(self) -> Dict:
        """加载配置"""
        default_config = {
            "min_sample_size": 5000,
            "max_sample_size": 200000,
            "emotion_dict_path": "配置/emotion_dict.txt",
            "idiom_dict_path": "配置/idiom_dict.txt",
            "stopwords_path": "配置/stopwords.txt"
        }
        
        if self._context and self._context.config_manager:
            user_config = self._context.config_manager.get("plugins.style_learner", {})
            default_config.update(user_config)
        
        return default_config

    def _init_emotion_dict(self):
        """初始化情感词典"""
        self._emotion_dict = {
            'positive': ['开心', '快乐', '幸福', '喜悦', '兴奋', '愉快', '满足', '舒适', 
                        '美好', '美丽', '优秀', '成功', '胜利', '辉煌', '精彩', '温馨',
                        '希望', '梦想', '自由', '轻松', '安宁', '平静', '祥和', '和谐'],
            'negative': ['痛苦', '悲伤', '沮丧', '失望', '绝望', '愤怒', '憎恨', '恐惧',
                        '焦虑', '担忧', '紧张', '压抑', '沉重', '黑暗', '恐怖', '残酷',
                        '痛苦', '折磨', '灾难', '毁灭', '死亡', '失败', '错误', '罪恶']
        }

    def _init_idiom_dict(self):
        """初始化成语词典"""
        self._idiom_patterns = [
            r'一[^的]{2,4}',
            r'三[^的]{2,4}',
            r'不[不有][^\s]{1,3}',
            r'[^\s]{4}',
        ]

    def analyze(self, content: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """分析风格

        Args:
            content: 待分析的文本或文件路径
            options: 分析选项
                - author_name: 作者名称
                - genre: 作品类型
                - analysis_type: 分析类型 (full/vocabulary/sentence/rhetoric/narrative/emotion)

        Returns:
            风格分析结果
        """
        options = options or {}
        
        # 检查是否是文件路径
        if os.path.exists(content) and content.endswith(('.txt', '.json')):
            return self._analyze_file(content, options)
        
        # 直接分析文本
        return self._analyze_text(content, options)

    def _analyze_text(self, text: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """分析文本风格"""
        author_name = options.get("author_name", "未知作者")
        genre = options.get("genre", "未知类型")
        analysis_type = options.get("analysis_type", "full")
        
        self._logger.info(f"开始风格分析: {author_name}")
        
        # 验证样本
        text_length = len(text)
        if text_length < self._config["min_sample_size"]:
            self._logger.warning(f"样本较小 ({text_length} 字符)，分析结果可能不准确")
        
        result = {
            "success": True,
            "author_name": author_name,
            "genre": genre,
            "sample_size_chars": text_length,
            "created_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        # 执行分析
        if analysis_type in ["full", "vocabulary"]:
            vocab_depth = self._analyze_vocabulary_depth(text)
            result["vocabulary_depth"] = self._dataclass_to_dict(vocab_depth)
        
        if analysis_type in ["full", "sentence"]:
            sentence_patterns = self._analyze_sentence_patterns(text)
            result["sentence_patterns"] = self._dataclass_to_dict(sentence_patterns)
        
        if analysis_type in ["full", "rhetoric"]:
            rhetorical_devices = self._analyze_rhetorical_devices(text)
            result["rhetorical_devices"] = self._dataclass_to_dict(rhetorical_devices)
        
        if analysis_type in ["full", "narrative"]:
            narrative_style = self._analyze_narrative_style(text)
            result["narrative_style"] = self._dataclass_to_dict(narrative_style)
        
        if analysis_type in ["full", "emotion"]:
            emotional_tone = self._analyze_emotional_tone(text)
            result["emotional_tone"] = self._dataclass_to_dict(emotional_tone)
        
        if analysis_type == "full":
            language_style = self._analyze_language_style(text)
            result["language_style"] = self._dataclass_to_dict(language_style)
            
            pacing_style = self._analyze_pacing_style(text)
            result["pacing_style"] = self._dataclass_to_dict(pacing_style)
            
            # 生成风格标签和特点
            result["style_tags"] = self._generate_style_tags(result)
            result["writing_characteristics"] = self._generate_writing_characteristics(result)
            result["similar_authors"] = self._find_similar_authors(result)
            result["prompt_suggestions"] = self._generate_prompt_suggestions(result)
        
        self._logger.info(f"风格分析完成: {author_name}")
        return result

    def _analyze_file(self, file_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """分析文件"""
        try:
            if file_path.endswith('.json'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            # 读取文本文件
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            # 从文件名提取作者
            if "author_name" not in options:
                filename = os.path.basename(file_path)
                name_without_ext = os.path.splitext(filename)[0]
                for separator in ['_-_', '___', '__', '_-', '-_', '_', '-']:
                    if separator in name_without_ext:
                        options["author_name"] = name_without_ext.split(separator)[0].strip()
                        break
                else:
                    options["author_name"] = name_without_ext
            
            return self._analyze_text(text, options)
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _dataclass_to_dict(self, obj) -> Dict:
        """转换dataclass为字典"""
        if hasattr(obj, '__dataclass_fields__'):
            result = {}
            for field_name in obj.__dataclass_fields__:
                value = getattr(obj, field_name)
                if isinstance(value, list):
                    result[field_name] = [
                        self._dataclass_to_dict(item) if hasattr(item, '__dataclass_fields__') else item
                        for item in value
                    ]
                elif isinstance(value, dict):
                    result[field_name] = {
                        k: self._dataclass_to_dict(v) if hasattr(v, '__dataclass_fields__') else v
                        for k, v in value.items()
                    }
                else:
                    result[field_name] = value
            return result
        return obj

    def _analyze_vocabulary_depth(self, text: str) -> VocabularyDepth:
        """深度分析词汇特征"""
        if not HAS_JIEBA:
            return VocabularyDepth(
                high_frequency_words=[],
                low_frequency_words=[],
                proper_nouns=[],
                emotion_words={},
                action_verbs=[],
                sensory_words={}
            )
        
        words = list(jieba.cut(text))
        words = [w for w in words if w.strip() and len(w) > 1]
        
        word_freq = Counter(words)
        total_words = len(words)
        
        # 高频词
        high_freq = word_freq.most_common(20)
        
        # 低频词
        low_freq = [(w, c) for w, c in word_freq.items() if c <= 2]
        low_freq.sort(key=lambda x: x[1], reverse=True)
        low_freq = low_freq[:20]
        
        # 专有名词
        proper_nouns = list(set([
            w for w in word_freq.keys() 
            if w[0].isupper() or len(w) == 3 or re.match(r'[A-Za-z]{2,}', w)
        ]))[:30]
        
        # 情感词统计
        emotion_words = {}
        for emotion_type, emotion_list in self._emotion_dict.items():
            emotion_count = sum([word_freq.get(w, 0) for w in emotion_list])
            if emotion_count > 0:
                emotion_words[emotion_type] = emotion_count
        
        # 动作动词
        action_verbs = [(w, c) for w, c in word_freq.items() 
                       if w.endswith('了') or w.endswith('着') or w.endswith('过')]
        action_verbs.sort(key=lambda x: x[1], reverse=True)
        action_verbs = action_verbs[:15]
        
        # 感官词汇
        sensory_words = {
            '视觉': ['看', '望', '瞧', '观', '视', '望见', '看见', '目光', '眼神'],
            '听觉': ['听', '闻', '声', '音', '响', '声音', '听见'],
            '嗅觉': ['闻', '嗅', '气味', '味道', '香味', '臭味'],
            '触觉': ['摸', '触', '感觉', '触觉', '温度', '热度', '冷', '热']
        }
        found_sensory = {}
        for sense_type, sense_list in sensory_words.items():
            found = [w for w in sense_list if word_freq.get(w, 0) > 0]
            if found:
                found_sensory[sense_type] = found
        
        return VocabularyDepth(
            high_frequency_words=high_freq,
            low_frequency_words=low_freq,
            proper_nouns=proper_nouns,
            emotion_words=emotion_words,
            action_verbs=action_verbs,
            sensory_words=found_sensory
        )

    def _analyze_sentence_patterns(self, text: str) -> SentencePatterns:
        """分析句式模式"""
        sentences = re.split(r'[。！？；\n]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return SentencePatterns([], [], [], [], 0.0, 0.0, "均匀")
        
        short_sentences = [s for s in sentences if len(s) < 10]
        long_sentences = [s for s in sentences if len(s) > 30]
        
        short_ratio = len(short_sentences) / len(sentences)
        long_ratio = len(long_sentences) / len(sentences)
        
        # 排比句
        parallel_sentences = []
        for i in range(len(sentences) - 2):
            if all(len(sentences[j]) > 0 for j in range(i, i+3)):
                lengths = [len(sentences[j]) for j in range(i, i+3)]
                if max(lengths) - min(lengths) < 5:
                    parallel_sentences.append(f"{sentences[i]} / {sentences[i+1]} / {sentences[i+2]}")
        
        # 设问句
        rhetorical_questions = [s for s in sentences if any(m in s for m in ['？', '吗？', '呢？', '难道', '岂'])]
        
        # 倒装句
        inverted_sentences = [s for s in sentences if s.startswith(('于是', '然而', '但是'))]
        
        # 条件句
        conditional_sentences = [s for s in sentences if any(m in s for m in ['如果', '若', '要是', '假如', '只要'])]
        
        # 句子节奏
        sentence_lengths = [len(s) for s in sentences]
        if len(sentence_lengths) > 1:
            avg = sum(sentence_lengths) / len(sentence_lengths)
            variance = sum((l - avg)**2 for l in sentence_lengths) / len(sentence_lengths)
            if variance < 10:
                rhythm = "均匀"
            elif variance < 30:
                rhythm = "交错"
            else:
                rhythm = "集中"
        else:
            rhythm = "均匀"
        
        return SentencePatterns(
            parallel_sentences=parallel_sentences[:10],
            rhetorical_questions=rhetorical_questions[:10],
            inverted_sentences=inverted_sentences[:10],
            conditional_sentences=conditional_sentences[:10],
            short_sentences_ratio=round(short_ratio, 2),
            long_sentences_ratio=round(long_ratio, 2),
            sentence_rhythm=rhythm
        )

    def _analyze_rhetorical_devices(self, text: str) -> RhetoricalDevices:
        """识别修辞手法"""
        sentences = re.split(r'[。！？；\n]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        metaphors = [s for s in sentences if any(m in s for m in ['像', '如', '似', '仿佛', '犹如', '宛如'])]
        
        personifications = []
        for s in sentences:
            if any(m in s for m in ['笑', '哭', '叹息', '欢呼', '低语']):
                if any(obj in s for obj in ['风', '月', '花', '树', '山', '水', '云', '雨']):
                    personifications.append(s)
        
        hyperboles = [s for s in sentences if any(m in s for m in ['极了', '万分', '无比', '绝对', '从来'])]
        contrasts = [s for s in sentences if any(m in s for m in ['但是', '然而', '却', '反而', '相反', '而'])]
        parallelisms = [s for s in sentences if s.count('，') >= 2][:10]
        
        rhetorical_total = len(metaphors) + len(personifications) + len(hyperboles) + len(contrasts) + len(parallelisms)
        text_length = len(text)
        rhetorical_density = (rhetorical_total / text_length * 1000) if text_length > 0 else 0
        
        return RhetoricalDevices(
            metaphors=metaphors[:10],
            personifications=personifications[:10],
            hyperboles=hyperboles[:10],
            contrasts=contrasts[:10],
            parallelisms=parallelisms,
            rhetorical_total=rhetorical_total,
            rhetorical_density=round(rhetorical_density, 2)
        )

    def _analyze_narrative_style(self, text: str) -> NarrativeStyle:
        """分析叙事风格"""
        first_person_markers = ['我', '我们', '我的', '我们的']
        third_person_markers = ['他', '她', '它', '他们', '她们', '它们']
        
        first_count = sum(text.count(m) for m in first_person_markers)
        third_count = sum(text.count(m) for m in third_person_markers)
        
        if first_count > third_count * 2:
            perspective = "第一人称"
        elif third_count > first_count * 2:
            perspective = "第三人称"
        else:
            perspective = "混合视角"
        
        past_markers = ['了', '过', '曾经', '那时', '当时']
        present_markers = ['现在', '目前', '正在', '此刻']
        
        past_count = sum(text.count(m) for m in past_markers)
        present_count = sum(text.count(m) for m in present_markers)
        
        if past_count > present_count:
            tense = "过去时态"
        elif present_count > past_count:
            tense = "现在时态"
        else:
            tense = "混合时态"
        
        temporal_markers = [m for m in ['昨天', '今天', '明天', '早晨', '中午', '晚上', '夜里', 
                       '忽然', '突然', '顿时', '随即', '紧接着'] if m in text]
        
        spatial_markers = [m for m in ['东', '西', '南', '北', '上', '下', '左', '右', 
                       '里', '外', '前', '后', '远', '近'] if m in text]
        
        sentences = re.split(r'[。！？；\n]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        scene_descriptions = []
        for s in sentences[:20]:
            if any(m in s for m in ['阳光', '月光', '风', '雨', '雪', '云', 
                                              '山', '水', '花', '树', '天空', '大地']):
                scene_descriptions.append(s.strip())
        
        avg_sentence_length = sum(len(s) for s in sentences) / len(sentences) if sentences else 0
        if avg_sentence_length < 15:
            narrative_pace = "快速"
        elif avg_sentence_length < 25:
            narrative_pace = "中等"
        else:
            narrative_pace = "缓慢"
        
        return NarrativeStyle(
            perspective=perspective,
            tense=tense,
            scene_descriptions=scene_descriptions[:5],
            temporal_markers=temporal_markers,
            spatial_markers=spatial_markers,
            narrative_pace=narrative_pace
        )

    def _analyze_emotional_tone(self, text: str) -> EmotionalTone:
        """分析情感色彩"""
        positive_count = sum(text.count(w) for w in self._emotion_dict['positive'])
        negative_count = sum(text.count(w) for w in self._emotion_dict['negative'])
        
        if positive_count > negative_count * 1.5:
            overall_sentiment = "积极"
        elif negative_count > positive_count * 1.5:
            overall_sentiment = "消极"
        else:
            overall_sentiment = "中性"
        
        sentiment_distribution = {
            'positive': positive_count,
            'negative': negative_count,
            'neutral': max(1, len(text) - positive_count - negative_count)
        }
        
        total_emotion_words = positive_count + negative_count
        emotional_intensity = min(1.0, total_emotion_words / len(text) * 100) if text else 0
        
        mood_changes = []
        chunk_size = 1000
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i+chunk_size]
            chunk_positive = sum(chunk.count(w) for w in self._emotion_dict['positive'])
            chunk_negative = sum(chunk.count(w) for w in self._emotion_dict['negative'])
            
            if chunk_positive > chunk_negative:
                mood = "积极"
            elif chunk_negative > chunk_positive:
                mood = "消极"
            else:
                mood = "中性"
            
            mood_changes.append((i, mood))
        
        return EmotionalTone(
            overall_sentiment=overall_sentiment,
            sentiment_distribution=sentiment_distribution,
            emotional_intensity=round(emotional_intensity, 2),
            mood_changes=mood_changes
        )

    def _analyze_language_style(self, text: str) -> LanguageStyle:
        """分析语言风格"""
        colloquial_markers = ['嘛', '呗', '哎', '嘿', '啧', '嗯', '啊', '噢']
        formal_markers = ['因此', '所以', '然而', '此外', '另外', '总之', '综上所述']
        
        colloquial_count = sum(text.count(m) for m in colloquial_markers)
        formal_count = sum(text.count(m) for m in formal_markers)
        
        if colloquial_count > formal_count * 2:
            register = "口语化"
        elif formal_count > colloquial_count * 2:
            register = "书面化"
        else:
            register = "雅俗共赏"
        
        formality = min(1.0, formal_count / (colloquial_count + 1))
        colloquialisms = [m for m in colloquial_markers if text.count(m) > 0]
        
        archaisms = ['于是', '乃', '之', '乎', '矣', '焉', '哉']
        archaisms_found = [w for w in archaisms if text.count(w) > 0]
        
        idioms_found = []
        if HAS_JIEBA:
            words = list(jieba.cut(text))
            for i in range(len(words) - 3):
                if all(len(words[j]) == 1 for j in range(i, i+4)):
                    idiom = ''.join(words[i:i+4])
                    if self._is_common_idiom(idiom):
                        idioms_found.append(idiom)
        
        foreign_words = []
        if HAS_JIEBA:
            words = list(jieba.cut(text))
            foreign_words = [w for w in words if re.search(r'[A-Za-z]', w)][:10]
        
        return LanguageStyle(
            register=register,
            formality=round(formality, 2),
            colloquialisms=colloquialisms,
            archaisms=archaisms_found,
            idioms=list(set(idioms_found))[:20],
            foreign_words=foreign_words[:10]
        )

    def _analyze_pacing_style(self, text: str) -> PacingStyle:
        """分析节奏风格"""
        paragraphs = text.split('\n\n')
        paragraph_rhythm = [len(p.strip()) for p in paragraphs if p.strip()]
        
        sentences = re.split(r'[。！？；\n]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) > 1:
            avg_length = sum(len(s) for s in sentences) / len(sentences)
            sentence_length_variance = sum((len(s) - avg_length)**2 for s in sentences) / len(sentences)
        else:
            sentence_length_variance = 0.0
        
        dialogue_markers = ['"', '"', '「', '」', '『', '』', '说：', '道：']
        dialogue_positions = [i for i, char in enumerate(text) if char in dialogue_markers]
        
        dialogue_intervals = [dialogue_positions[i] - dialogue_positions[i-1] 
                             for i in range(1, len(dialogue_positions))]
        
        action_markers = ['跳', '跑', '走', '飞', '冲', '撞', '击', '打', '踢']
        action_positions = []
        for marker in action_markers:
            pos = text.find(marker)
            while pos != -1:
                action_positions.append(pos)
                pos = text.find(marker, pos + 1)
        
        action_positions.sort()
        action_intervals = [action_positions[i] - action_positions[i-1] 
                          for i in range(1, len(action_positions))]
        
        avg_paragraph_length = sum(paragraph_rhythm) / len(paragraph_rhythm) if paragraph_rhythm else 0
        if avg_paragraph_length < 100:
            overall_pace = "快节奏"
        elif avg_paragraph_length < 200:
            overall_pace = "中等节奏"
        else:
            overall_pace = "慢节奏"
        
        return PacingStyle(
            overall_pace=overall_pace,
            paragraph_rhythm=paragraph_rhythm[:10],
            sentence_length_variance=round(sentence_length_variance, 2),
            dialogue_intervals=dialogue_intervals[:10],
            action_intervals=action_intervals[:10]
        )

    def _is_common_idiom(self, word: str) -> bool:
        """判断是否为常见成语"""
        return len(word) == 4 and word[0] in '一二三四五六七八九十百千万'

    def _generate_style_tags(self, result: Dict) -> List[str]:
        """生成风格标签"""
        tags = []
        
        rhetorical = result.get("rhetorical_devices", {})
        if rhetorical.get("rhetorical_density", 0) > 2:
            tags.append("修辞丰富")
        if len(rhetorical.get("metaphors", [])) > 5:
            tags.append("善用比喻")
        
        emotional = result.get("emotional_tone", {})
        if emotional.get("overall_sentiment") == "积极":
            tags.append("积极向上")
        elif emotional.get("overall_sentiment") == "消极":
            tags.append("深沉内敛")
        else:
            tags.append("情感中性")
        
        sentence = result.get("sentence_patterns", {})
        if sentence.get("short_sentences_ratio", 0) > 0.5:
            tags.append("短句为主")
        elif sentence.get("long_sentences_ratio", 0) > 0.5:
            tags.append("长句为主")
        
        vocab = result.get("vocabulary_depth", {})
        if vocab.get("sensory_words"):
            tags.append("感官描写丰富")
        
        return tags if tags else ["风格平实"]

    def _generate_writing_characteristics(self, result: Dict) -> List[str]:
        """生成写作特点总结"""
        characteristics = []
        
        narrative = result.get("narrative_style", {})
        characteristics.append(f"叙事视角: {narrative.get('perspective', '未知')}")
        
        sentence = result.get("sentence_patterns", {})
        if sentence.get("short_sentences_ratio", 0) > 0.4:
            characteristics.append("句式短促有力，节奏明快")
        elif sentence.get("long_sentences_ratio", 0) > 0.3:
            characteristics.append("句式绵长复杂，表达细腻")
        
        rhetorical = result.get("rhetorical_devices", {})
        if rhetorical.get("rhetorical_density", 0) > 1:
            characteristics.append(f"修辞手法丰富（密度: {rhetorical['rhetorical_density']}/千字）")
        
        language = result.get("language_style", {})
        characteristics.append(f"语言{language.get('register', '通用')}")
        
        return characteristics

    def _find_similar_authors(self, result: Dict) -> List[str]:
        """查找相似作家"""
        tags = result.get("style_tags", [])
        language = result.get("language_style", {})
        similar = []
        
        if "善用比喻" in tags and "感官描写丰富" in tags:
            similar.append("朱自清")
        if "短句为主" in tags:
            similar.append("鲁迅")
        if "修辞丰富" in tags and language.get("register") == "书面化":
            similar.append("莫言")
        if "情感中性" in tags and "长句为主" in tags:
            similar.append("余华")
        
        return similar if similar else ["暂无相似作家"]

    def _generate_prompt_suggestions(self, result: Dict) -> List[str]:
        """生成提示词建议"""
        suggestions = []
        
        for tag in result.get("style_tags", []):
            suggestions.append(f"风格: {tag}")
        
        language = result.get("language_style", {})
        suggestions.append(f"语体: {language.get('register', '通用')}")
        
        for char in result.get("writing_characteristics", [])[:3]:
            suggestions.append(char)
        
        return suggestions

    def get_supported_formats(self) -> List[str]:
        """获取支持的输入格式"""
        return ["txt", "json"]

    def get_analysis_types(self) -> List[str]:
        """获取支持的分析类型"""
        return ["style", "vocabulary", "sentence", "rhetoric", "narrative", "emotion"]

    def create_style_template(self, name: str, description: str = "",
                             dimensions: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """创建风格模板（适配UI创建模板功能）
        
        Args:
            name: 模板名称
            description: 风格描述
            dimensions: 七维度评分字典
                - vocabulary: 词汇丰富度 (0.0-1.0)
                - sentence: 句式多样性 (0.0-1.0)
                - rhetoric: 修辞密度 (0.0-1.0)
                - emotion: 情感强度 (0.0-1.0)
                - rhythm: 节奏感 (0.0-1.0)
                - structure: 结构完整性 (0.0-1.0)
                - detail: 细节描写 (0.0-1.0)
                
        Returns:
            创建结果字典
        """
        try:
            # 默认七维度评分
            default_dimensions = {
                "vocabulary": 0.5,
                "sentence": 0.5,
                "rhetoric": 0.5,
                "emotion": 0.5,
                "rhythm": 0.5,
                "structure": 0.5,
                "detail": 0.5
            }
            
            if dimensions:
                default_dimensions.update(dimensions)
            
            # 生成模板ID
            template_id = f"style_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # 创建模板数据
            template_data = {
                "id": template_id,
                "name": name,
                "description": description,
                "dimensions": default_dimensions,
                "created_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "modified_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "style_tags": self._generate_tags_from_dimensions(default_dimensions),
                "sample_texts": [],
                "is_template": True
            }
            
            # 生成风格提示词
            template_data["style_prompt"] = self._generate_style_prompt(template_data)
            
            self._logger.info(f"创建风格模板成功: {name}")
            
            return {
                "success": True,
                "template_id": template_id,
                "template_data": template_data,
                "message": f"风格模板 '{name}' 创建成功"
            }
            
        except Exception as e:
            self._logger.error(f"创建风格模板失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _generate_tags_from_dimensions(self, dimensions: Dict[str, float]) -> List[str]:
        """根据七维度评分生成风格标签"""
        tags = []
        
        if dimensions.get("vocabulary", 0.5) > 0.7:
            tags.append("词汇丰富")
        if dimensions.get("sentence", 0.5) > 0.7:
            tags.append("句式多变")
        if dimensions.get("rhetoric", 0.5) > 0.7:
            tags.append("修辞优美")
        if dimensions.get("emotion", 0.5) > 0.7:
            tags.append("情感充沛")
        if dimensions.get("rhythm", 0.5) > 0.7:
            tags.append("节奏明快")
        if dimensions.get("structure", 0.5) > 0.7:
            tags.append("结构严谨")
        if dimensions.get("detail", 0.5) > 0.7:
            tags.append("细节生动")
            
        return tags if tags else ["风格平实"]
    
    def _generate_style_prompt(self, template_data: Dict) -> str:
        """根据模板数据生成风格提示词"""
        dimensions = template_data.get("dimensions", {})
        tags = template_data.get("style_tags", [])
        
        prompt_parts = [f"写作风格：{template_data['name']}"]
        
        if tags:
            prompt_parts.append(f"风格特点：{'、'.join(tags)}")
        
        # 根据维度生成具体指导
        if dimensions.get("vocabulary", 0.5) > 0.6:
            prompt_parts.append("使用丰富多样的词汇，避免重复")
        if dimensions.get("sentence", 0.5) > 0.6:
            prompt_parts.append("句式长短结合，富有变化")
        if dimensions.get("rhetoric", 0.5) > 0.6:
            prompt_parts.append("善用比喻、拟人等修辞手法")
        if dimensions.get("emotion", 0.5) > 0.6:
            prompt_parts.append("注重情感表达，渲染氛围")
        if dimensions.get("detail", 0.5) > 0.6:
            prompt_parts.append("注重细节描写，增强画面感")
            
        return "\n".join(prompt_parts)
    
    def get_style_templates(self) -> List[Dict[str, Any]]:
        """获取所有风格模板（适配UI模板列表功能）"""
        # 返回预设模板列表
        preset_templates = [
            {
                "id": "style_natural",
                "name": "自然流畅",
                "description": "自然流畅的写作风格，适合大多数小说",
                "dimensions": {
                    "vocabulary": 0.5,
                    "sentence": 0.6,
                    "rhetoric": 0.4,
                    "emotion": 0.5,
                    "rhythm": 0.6,
                    "structure": 0.5,
                    "detail": 0.5
                }
            },
            {
                "id": "style_literary",
                "name": "文艺细腻",
                "description": "文艺细腻的写作风格，注重情感和细节",
                "dimensions": {
                    "vocabulary": 0.7,
                    "sentence": 0.6,
                    "rhetoric": 0.7,
                    "emotion": 0.8,
                    "rhythm": 0.5,
                    "structure": 0.6,
                    "detail": 0.8
                }
            },
            {
                "id": "style_fast",
                "name": "快节奏",
                "description": "快节奏的写作风格，适合爽文和动作场景",
                "dimensions": {
                    "vocabulary": 0.5,
                    "sentence": 0.8,
                    "rhetoric": 0.3,
                    "emotion": 0.5,
                    "rhythm": 0.9,
                    "structure": 0.7,
                    "detail": 0.4
                }
            }
        ]
        
        return preset_templates

    def shutdown(self) -> bool:
        """优雅关闭插件
        
        清理资源：
        1. 清理配置
        2. 清理情感词典和成语词典
        3. 调用父类shutdown
        """
        try:
            # 清理配置
            if hasattr(self, '_config'):
                self._config.clear()
            
            # 清理词典
            if hasattr(self, '_emotion_dict'):
                self._emotion_dict.clear()
            if hasattr(self, '_idiom_patterns'):
                self._idiom_patterns.clear()
            
            # 清理词性标注器引用
            self._pos_tagger = None
            
            self._logger.info(f"[{self.PLUGIN_ID}] 插件已关闭")
            return super().shutdown()
            
        except Exception as e:
            self._logger.error(f"[{self.PLUGIN_ID}] 关闭失败: {e}")
            return False


# 模块级函数
def get_plugin_class():
    return StyleLearnerPlugin

def register_plugin():
    return StyleLearnerPlugin


# 测试入口
if __name__ == "__main__":
    print("=" * 60)
    print("风格学习器插件 V5 测试")
    print("=" * 60)
    
    plugin = StyleLearnerPlugin()
    print(f"\n1. 插件元数据:")
    print(f"   ID: {plugin.metadata.id}")
    print(f"   名称: {plugin.metadata.name}")
    print(f"   版本: {plugin.metadata.version}")
    
    test_text = """
    今天阳光明媚，春风拂面，我感觉心情格外舒畅。
    看着窗外的柳树，仿佛看见了一位温柔的女神，轻轻地挥舞着她的长发。
    鸟儿在枝头欢快地歌唱，好像在为我演奏一首美妙的乐曲。
    
    我想起小时候，奶奶总是这样坐在院子里，一边纳鞋底，一边给我讲故事。
    那时天很蓝，云很白，日子过得很慢，却很快乐。
    
    如果时光能够倒流，我真想回到那个无忧无虑的年代。
    难道这就是成长必须付出的代价吗？
    
    风轻轻地吹，雨静静地落，花儿悄悄地开。
    生活就像一首诗，需要用心去品味，用情去感受。
    """
    
    result = plugin.analyze(test_text, {"author_name": "测试作者", "genre": "散文"})
    
    if result.get("success"):
        print(f"\n2. 分析结果:")
        print(f"   作者: {result['author_name']}")
        print(f"   类型: {result['genre']}")
        print(f"   样本大小: {result['sample_size_chars']} 字符")
        print(f"   风格标签: {', '.join(result['style_tags'])}")
        print(f"   写作特点: {', '.join(result['writing_characteristics'])}")
        print(f"   相似作家: {', '.join(result['similar_authors'])}")
    
    print(f"\n3. 支持的格式: {plugin.get_supported_formats()}")
    print(f"4. 分析类型: {plugin.get_analysis_types()}")
    
    print(f"\n" + "=" * 60)
    print("测试完成！")
