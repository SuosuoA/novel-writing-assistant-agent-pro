"""
参考文本解析模块 V1.0
Reference Text Parser Module

功能：
1. 从参考文本中识别世界观元素（时代背景、力量体系、势力组织）
2. 从参考文本中识别人物元素（姓名、性格、外貌、能力）
3. 从参考文本中识别情节元素（关键事件、冲突、转折点）
4. 将解析结果融合到生成Prompt中

作者：数据工程师
日期：2026-03-24
"""

import re
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ReferenceType(Enum):
    """参考文本类型"""
    NOVEL = "novel"           # 小说文本
    OUTLINE = "outline"       # 大纲文本
    CHARACTER = "character"   # 人物设定
    WORLDVIEW = "worldview"   # 世界观设定
    MIXED = "mixed"           # 混合类型
    UNKNOWN = "unknown"       # 未知类型


@dataclass
class WorldviewElements:
    """世界观元素"""
    era: str = ""                                  # 时代背景
    world_structure: str = ""                      # 世界结构
    power_system: str = ""                         # 力量体系
    power_levels: List[str] = field(default_factory=list)  # 等级体系
    geography: List[str] = field(default_factory=list)     # 地理环境
    forces: List[Dict[str, str]] = field(default_factory=list)  # 势力组织
    rules: List[str] = field(default_factory=list)          # 世界规则
    special_elements: List[str] = field(default_factory=list)  # 特殊元素
    
    def is_empty(self) -> bool:
        """检查是否为空"""
        return (
            not self.era and 
            not self.world_structure and 
            not self.power_system and
            not self.power_levels and
            not self.geography and
            not self.forces and
            not self.rules and
            not self.special_elements
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "era": self.era,
            "world_structure": self.world_structure,
            "power_system": self.power_system,
            "power_levels": self.power_levels,
            "geography": self.geography,
            "forces": self.forces,
            "rules": self.rules,
            "special_elements": self.special_elements
        }


@dataclass
class CharacterElements:
    """人物元素"""
    name: str = ""                     # 姓名
    role: str = ""                     # 角色定位（主角/配角/反派）
    age: str = ""                      # 年龄
    gender: str = ""                   # 性别
    appearance: str = ""               # 外貌描述
    personality: List[str] = field(default_factory=list)  # 性格特点
    abilities: List[str] = field(default_factory=list)    # 能力技能
    background: str = ""               # 背景故事
    goals: List[str] = field(default_factory=list)        # 目标动机
    weaknesses: List[str] = field(default_factory=list)   # 弱点缺陷
    relationships: Dict[str, str] = field(default_factory=dict)  # 人物关系
    
    def is_empty(self) -> bool:
        """检查是否为空"""
        return not self.name
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "role": self.role,
            "age": self.age,
            "gender": self.gender,
            "appearance": self.appearance,
            "personality": self.personality,
            "abilities": self.abilities,
            "background": self.background,
            "goals": self.goals,
            "weaknesses": self.weaknesses,
            "relationships": self.relationships
        }


@dataclass
class PlotElements:
    """情节元素"""
    events: List[Dict[str, str]] = field(default_factory=list)  # 关键事件
    conflicts: List[str] = field(default_factory=list)          # 冲突点
    turning_points: List[str] = field(default_factory=list)     # 转折点
    foreshadowing: List[str] = field(default_factory=list)      # 伏笔
    climax: str = ""                                             # 高潮
    
    def is_empty(self) -> bool:
        """检查是否为空"""
        return (
            not self.events and 
            not self.conflicts and 
            not self.turning_points and
            not self.foreshadowing
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "events": self.events,
            "conflicts": self.conflicts,
            "turning_points": self.turning_points,
            "foreshadowing": self.foreshadowing,
            "climax": self.climax
        }


@dataclass
class ParsedReference:
    """解析后的参考文本"""
    reference_type: ReferenceType                # 文本类型
    worldview: WorldviewElements = None          # 世界观元素
    characters: List[CharacterElements] = None   # 人物元素列表
    plot: PlotElements = None                    # 情节元素
    style_keywords: List[str] = None             # 风格关键词
    raw_text: str = ""                           # 原始文本
    confidence: float = 0.0                      # 解析置信度
    
    def __post_init__(self):
        if self.worldview is None:
            self.worldview = WorldviewElements()
        if self.characters is None:
            self.characters = []
        if self.plot is None:
            self.plot = PlotElements()
        if self.style_keywords is None:
            self.style_keywords = []
    
    def has_worldview(self) -> bool:
        """是否包含世界观元素"""
        return self.worldview and not self.worldview.is_empty()
    
    def has_characters(self) -> bool:
        """是否包含人物元素"""
        return self.characters and len(self.characters) > 0
    
    def has_plot(self) -> bool:
        """是否包含情节元素"""
        return self.plot and not self.plot.is_empty()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "reference_type": self.reference_type.value,
            "worldview": self.worldview.to_dict() if self.worldview else {},
            "characters": [c.to_dict() for c in self.characters] if self.characters else [],
            "plot": self.plot.to_dict() if self.plot else {},
            "style_keywords": self.style_keywords,
            "confidence": self.confidence
        }


class ReferenceTextParser:
    """
    参考文本解析器
    
    核心功能：
    1. 识别文本类型（小说/大纲/人物设定/世界观设定）
    2. 提取世界观元素
    3. 提取人物元素
    4. 提取情节元素
    5. 提取风格关键词
    
    性能优化（V1.1）：
    - 预编译常用正则表达式，避免重复编译开销
    """
    
    # ==================== 预编译正则表达式（性能优化 V1.1）====================
    # 章节结构检测
    _CHAPTER_PATTERN = re.compile(r"第[一二三四五六七八九十百千\d]+章")
    
    # 力量等级模式
    _POWER_LEVEL_COMPILED = [
        re.compile(r"练气[一二三四五六七八九十]+层"),
        re.compile(r"筑基[初期中期后期巅峰]"),
        re.compile(r"金丹[初期中期后期巅峰]"),
        re.compile(r"元婴[初期中期后期巅峰]"),
        re.compile(r"化神[初期中期后期巅峰]"),
        re.compile(r"[一二三四五六七八九十]+阶"),
        re.compile(r"[一二三四五六七八九十]+级"),
        re.compile(r"[一二三四五六七八九十]+星"),
        re.compile(r"先天[一二三四五六七八九十]+重"),
        re.compile(r"后天[一二三四五六七八九十]+重")
    ]
    
    # 世界结构模式
    _WORLD_STRUCTURE_PATTERNS = [
        re.compile(r"世界[分为结构]+[：:]?\s*([^\n。]+)"),
        re.compile(r"(三界|六界|九界|人间|仙界|魔界|神界|冥界)")
    ]
    
    # 人物姓名模式
    _NAME_PATTERNS = [
        re.compile(r"姓名[：:]\s*([^\n，。]+)"),
        re.compile(r"名字[：:]\s*([^\n，。]+)"),
        re.compile(r"角色[：:]\s*([^\n，。]+)"),
        re.compile(r"([^\n，。]{2,4})[是为]?(主角|男主|女主|反派|配角)")
    ]
    
    # 性格模式
    _PERSONALITY_PATTERNS = [
        re.compile(r"性格[：:]\s*([^\n。]+)"),
        re.compile(r"性情[：:]\s*([^\n。]+)"),
        re.compile(r"气质[：:]\s*([^\n。]+)")
    ]
    
    # 事件模式
    _EVENT_PATTERNS = [
        re.compile(r"([^\n。！？]*(发生|遭遇|经历|遇到)[^\n。！？]*)"),
        re.compile(r"事件[：:]\s*([^\n。]+)")
    ]
    
    # 人物行为推断模式
    _NAME_FROM_DIALOGUE = re.compile(r"([^\n，。！？]{2,4})(说道|问道|答道|笑道|叫道|喊道|怒道|冷道)")
    
    # ========== 新增：通用键值提取模式（预编译）==========
    # 时代背景提取模式
    _ERA_PATTERNS = {
        "时代": re.compile(r"时代[：:是为]?\s*([^\n。！？]+)"),
        "年代": re.compile(r"年代[：:是为]?\s*([^\n。！？]+)"),
        "朝代": re.compile(r"朝代[：:是为]?\s*([^\n。！？]+)"),
        "世纪": re.compile(r"世纪[：:是为]?\s*([^\n。！？]+)"),
        "年份": re.compile(r"年份[：:是为]?\s*([^\n。！？]+)"),
        "古代": re.compile(r"古代[：:是为]?\s*([^\n。！？]+)"),
        "现代": re.compile(r"现代[：:是为]?\s*([^\n。！？]+)"),
        "未来": re.compile(r"未来[：:是为]?\s*([^\n。！？]+)"),
        "末世": re.compile(r"末世[：:是为]?\s*([^\n。！？]+)"),
        "洪荒": re.compile(r"洪荒[：:是为]?\s*([^\n。！？]+)")
    }
    
    # 力量体系提取模式
    _POWER_SYSTEM_PATTERNS = {
        "力量体系": re.compile(r"力量体系[：:]\s*([^\n]+)"),
        "修炼体系": re.compile(r"修炼体系[：:]\s*([^\n]+)"),
        "修炼": re.compile(r"修炼[：:是为]?\s*([^\n。！？]+)"),
        "灵力": re.compile(r"灵力[：:是为]?\s*([^\n。！？]+)"),
        "魔力": re.compile(r"魔力[：:是为]?\s*([^\n。！？]+)"),
        "斗气": re.compile(r"斗气[：:是为]?\s*([^\n。！？]+)"),
        "真气": re.compile(r"真气[：:是为]?\s*([^\n。！？]+)"),
        "元气": re.compile(r"元气[：:是为]?\s*([^\n。！？]+)"),
        "法力": re.compile(r"法力[：:是为]?\s*([^\n。！？]+)"),
        "神力": re.compile(r"神力[：:是为]?\s*([^\n。！？]+)"),
        "灵气": re.compile(r"灵气[：:是为]?\s*([^\n。！？]+)"),
        "异能": re.compile(r"异能[：:是为]?\s*([^\n。！？]+)"),
        "修仙": re.compile(r"修仙[：:是为]?\s*([^\n。！？]+)"),
        "修真": re.compile(r"修真[：:是为]?\s*([^\n。！？]+)"),
        "武道": re.compile(r"武道[：:是为]?\s*([^\n。！？]+)"),
        "魔法": re.compile(r"魔法[：:是为]?\s*([^\n。！？]+)"),
        "道法": re.compile(r"道法[：:是为]?\s*([^\n。！？]+)"),
        "功法": re.compile(r"功法[：:是为]?\s*([^\n。！？]+)"),
        "境界": re.compile(r"境界[：:是为]?\s*([^\n。！？]+)"),
        "等级": re.compile(r"等级[：:是为]?\s*([^\n。！？]+)")
    }
    
    # 外貌提取模式
    _APPEARANCE_PATTERNS = {
        "外貌": re.compile(r"外貌[：:是为]?\s*([^\n。]+)"),
        "长相": re.compile(r"长相[：:是为]?\s*([^\n。]+)"),
        "相貌": re.compile(r"相貌[：:是为]?\s*([^\n。]+)"),
        "容貌": re.compile(r"容貌[：:是为]?\s*([^\n。]+)"),
        "样子": re.compile(r"样子[：:是为]?\s*([^\n。]+)"),
        "身形": re.compile(r"身形[：:是为]?\s*([^\n。]+)"),
        "身材": re.compile(r"身材[：:是为]?\s*([^\n。]+)"),
        "五官": re.compile(r"五官[：:是为]?\s*([^\n。]+)"),
        "面容": re.compile(r"面容[：:是为]?\s*([^\n。]+)"),
        "颜值": re.compile(r"颜值[：:是为]?\s*([^\n。]+)")
    }
    
    # 能力提取模式
    _ABILITIES_PATTERNS = {
        "能力": re.compile(r"能力[：:]\s*([^\n。]+)"),
        "技能": re.compile(r"技能[：:]\s*([^\n。]+)"),
        "功法": re.compile(r"功法[：:]\s*([^\n。]+)"),
        "武技": re.compile(r"武技[：:]\s*([^\n。]+)"),
        "法术": re.compile(r"法术[：:]\s*([^\n。]+)"),
        "天赋": re.compile(r"天赋[：:]\s*([^\n。]+)"),
        "神通": re.compile(r"神通[：:]\s*([^\n。]+)"),
        "异能": re.compile(r"异能[：:]\s*([^\n。]+)"),
        "绝招": re.compile(r"绝招[：:]\s*([^\n。]+)")
    }
    
    # 背景提取模式
    _BACKGROUND_PATTERNS = {
        "背景": re.compile(r"背景[：:]\s*([^\n。]+)"),
        "身世": re.compile(r"身世[：:]\s*([^\n。]+)"),
        "来历": re.compile(r"来历[：:]\s*([^\n。]+)"),
        "经历": re.compile(r"经历[：:]\s*([^\n。]+)"),
        "往事": re.compile(r"往事[：:]\s*([^\n。]+)"),
        "过去": re.compile(r"过去[：:]\s*([^\n。]+)"),
        "出身": re.compile(r"出身[：:]\s*([^\n。]+)")
    }
    
    # 冲突提取模式（预编译）
    _CONFLICT_PATTERNS = {
        "冲突": re.compile(r"([^\n。！？]*冲突[^\n。！？]*)"),
        "矛盾": re.compile(r"([^\n。！？]*矛盾[^\n。！？]*)"),
        "对立": re.compile(r"([^\n。！？]*对立[^\n。！？]*)"),
        "争斗": re.compile(r"([^\n。！？]*争斗[^\n。！？]*)"),
        "对抗": re.compile(r"([^\n。！？]*对抗[^\n。！？]*)"),
        "仇恨": re.compile(r"([^\n。！？]*仇恨[^\n。！？]*)"),
        "恩怨": re.compile(r"([^\n。！？]*恩怨[^\n。！？]*)"),
        "纠纷": re.compile(r"([^\n。！？]*纠纷[^\n。！？]*)")
    }
    
    # 转折点提取模式（预编译）
    _TURNING_POINT_PATTERNS = {
        "转折": re.compile(r"([^\n。！？]*转折[^\n。！？]*)"),
        "变故": re.compile(r"([^\n。！？]*变故[^\n。！？]*)"),
        "意外": re.compile(r"([^\n。！？]*意外[^\n。！？]*)"),
        "突变": re.compile(r"([^\n。！？]*突变[^\n。！？]*)"),
        "反转": re.compile(r"([^\n。！？]*反转[^\n。！？]*)"),
        "逆袭": re.compile(r"([^\n。！？]*逆袭[^\n。！？]*)"),
        "突破": re.compile(r"([^\n。！？]*突破[^\n。！？]*)")
    }
    
    # 伏笔提取模式（预编译）
    _FORESHADOWING_PATTERNS = {
        "伏笔": re.compile(r"([^\n。！？]*伏笔[^\n。！？]*)"),
        "暗示": re.compile(r"([^\n。！？]*暗示[^\n。！？]*)"),
        "预兆": re.compile(r"([^\n。！？]*预兆[^\n。！？]*)"),
        "铺垫": re.compile(r"([^\n。！？]*铺垫[^\n。！？]*)"),
        "暗线": re.compile(r"([^\n。！？]*暗线[^\n。！？]*)"),
        "悬念": re.compile(r"([^\n。！？]*悬念[^\n。！？]*)")
    }
    
    # 地理环境通用提取模式（预编译）
    _GEOGRAPHY_GENERIC_PATTERN = re.compile(r"([^\n。！？]*(大陆|世界|帝国|王国|城|州|省|山脉|河流|海域|领域|位面|星域|州府|国都)[^\n。！？]*)")
    
    # 势力组织通用提取模式（预编译）
    _FORCES_GENERIC_PATTERN = re.compile(r"([^\n。！？]*(宗门|门派|家族|势力|组织|帮派|帝国|联盟|商会|学院)[^\n。！？]*)")
    
    # 世界观关键词
    WORLDVIEW_KEYWORDS = {
        "era": ["时代", "年代", "朝代", "世纪", "年份", "古代", "现代", "未来", "末世", "洪荒"],
        "power_system": ["修炼", "灵力", "魔力", "斗气", "真气", "元气", "法力", "神力", "灵气", "异能",
                        "修仙", "修真", "武道", "魔法", "道法", "功法", "境界", "等级"],
        "geography": ["大陆", "世界", "帝国", "王国", "城", "州", "省", "山脉", "河流", "海域", 
                     "领域", "位面", "星域", "州府", "国都"],
        "forces": ["宗门", "门派", "家族", "势力", "组织", "帮派", "帝国", "联盟", "商会", "学院"]
    }
    
    # 人物关键词
    CHARACTER_KEYWORDS = {
        "role": ["主角", "男主", "女主", "配角", "反派", "路人", "配角"],
        "appearance": ["外貌", "长相", "相貌", "容貌", "样子", "身形", "身材", "五官", "面容", "颜值"],
        "personality": ["性格", "脾气", "心性", "性情", "气质", "性格特点", "为人", "品格"],
        "abilities": ["能力", "技能", "功法", "武技", "法术", "天赋", "神通", "异能", "绝招"],
        "background": ["背景", "身世", "来历", "经历", "往事", "过去", "出身"]
    }
    
    # 情节关键词
    PLOT_KEYWORDS = {
        "events": ["事件", "事故", "变故", "发生", "遭遇", "经历", "历险", "冒险"],
        "conflicts": ["冲突", "矛盾", "对立", "争斗", "对抗", "仇恨", "恩怨", "纠纷"],
        "turning_points": ["转折", "变故", "意外", "突变", "反转", "逆袭", "突破"],
        "foreshadowing": ["伏笔", "暗示", "预兆", "铺垫", "暗线", "悬念"]
    }
    
    def __init__(self):
        """初始化解析器"""
        self._cache: Dict[str, ParsedReference] = {}
    
    def parse(self, text: str, reference_type: str = None) -> ParsedReference:
        """
        解析参考文本
        
        Args:
            text: 参考文本内容
            reference_type: 文本类型（可选，自动检测）
            
        Returns:
            解析结果
        """
        if not text or not text.strip():
            return ParsedReference(reference_type=ReferenceType.UNKNOWN)
        
        # 检查缓存
        cache_key = self._get_cache_key(text)
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # 检测文本类型
        detected_type = self._detect_type(text) if not reference_type else ReferenceType(reference_type)
        
        # 创建解析结果
        result = ParsedReference(
            reference_type=detected_type,
            raw_text=text[:1000]  # 保留前1000字符
        )
        
        # 根据类型解析
        if detected_type == ReferenceType.WORLDVIEW:
            result.worldview = self._extract_worldview(text)
        elif detected_type == ReferenceType.CHARACTER:
            result.characters = [self._extract_character(text)]
        elif detected_type == ReferenceType.OUTLINE:
            result.plot = self._extract_plot(text)
            result.worldview = self._extract_worldview(text)
        elif detected_type == ReferenceType.NOVEL or detected_type == ReferenceType.MIXED:
            # 小说或混合类型，提取所有元素
            result.worldview = self._extract_worldview(text)
            result.characters = self._extract_all_characters(text)
            result.plot = self._extract_plot(text)
        
        # 提取风格关键词
        result.style_keywords = self._extract_style_keywords(text)
        
        # 计算置信度
        result.confidence = self._calculate_confidence(result)
        
        # 缓存结果
        self._cache[cache_key] = result
        
        logger.info(f"参考文本解析完成: type={detected_type.value}, confidence={result.confidence:.2f}")
        return result
    
    def _detect_type(self, text: str) -> ReferenceType:
        """
        检测文本类型
        
        Args:
            text: 文本内容
            
        Returns:
            文本类型
        """
        text_lower = text.lower()
        
        # 检测世界观设定
        worldview_score = 0
        for keywords in self.WORLDVIEW_KEYWORDS.values():
            for kw in keywords:
                if kw in text:
                    worldview_score += 1
        
        # 检测人物设定
        character_score = 0
        for keywords in self.CHARACTER_KEYWORDS.values():
            for kw in keywords:
                if kw in text:
                    character_score += 1
        
        # 检测情节/大纲
        plot_score = 0
        for keywords in self.PLOT_KEYWORDS.values():
            for kw in keywords:
                if kw in text:
                    plot_score += 1
        
        # 检测章节结构（使用预编译正则）
        has_chapters = bool(self._CHAPTER_PATTERN.search(text))
        has_outline_structure = "大纲" in text or "章节" in text or "梗概" in text
        
        # 判断类型
        if worldview_score > 5 and worldview_score > character_score * 2:
            return ReferenceType.WORLDVIEW
        elif character_score > 5 and character_score > worldview_score * 2:
            return ReferenceType.CHARACTER
        elif has_chapters or has_outline_structure:
            return ReferenceType.OUTLINE
        elif plot_score > 3:
            return ReferenceType.PLOT
        elif worldview_score > 2 or character_score > 2 or plot_score > 2:
            return ReferenceType.MIXED
        else:
            return ReferenceType.NOVEL
    
    def _extract_worldview(self, text: str) -> WorldviewElements:
        """
        提取世界观元素
        
        Args:
            text: 文本内容
            
        Returns:
            世界观元素
        """
        elements = WorldviewElements()
        
        # 提取时代背景（使用预编译正则）
        for pattern in self._ERA_PATTERNS.values():
            match = pattern.search(text)
            if match:
                elements.era = match.group(1).strip()
                break
        
        # 提取力量体系（使用预编译正则）
        for pattern in self._POWER_SYSTEM_PATTERNS.values():
            match = pattern.search(text)
            if match:
                elements.power_system = match.group(1).strip()
                break
        
        # 提取力量等级（使用预编译正则）
        for pattern in self._POWER_LEVEL_COMPILED:
            matches = pattern.findall(text)
            elements.power_levels.extend(matches)
        
        # 去重
        elements.power_levels = list(set(elements.power_levels))
        
        # 提取地理环境（使用预编译通用模式）
        matches = self._GEOGRAPHY_GENERIC_PATTERN.findall(text)
        # findall返回元组列表，取第一个元素（完整匹配）
        geography_texts = [m[0] if isinstance(m, tuple) else m for m in matches[:5]]
        elements.geography.extend(geography_texts)
        elements.geography = list(set(elements.geography))[:10]
        
        # 提取势力组织（使用预编译通用模式）
        matches = self._FORCES_GENERIC_PATTERN.findall(text)
        for m in matches[:5]:
            # findall返回元组，取第一个元素（完整匹配）
            force_text = m[0] if isinstance(m, tuple) else m
            force_name = re.sub(r"[的地得]", "", force_text).strip()
            if force_name:
                elements.forces.append({
                    "name": force_name[:20],
                    "description": force_text[:50]
                })
        
        # 提取世界结构（使用预编译正则）
        for pattern in self._WORLD_STRUCTURE_PATTERNS:
            match = pattern.search(text)
            if match:
                elements.world_structure = match.group(1)
                break
        
        return elements
    
    def _extract_character(self, text: str) -> CharacterElements:
        """
        提取单个人物元素
        
        Args:
            text: 文本内容
            
        Returns:
            人物元素
        """
        elements = CharacterElements()
        
        # 提取姓名（使用预编译正则）
        for pattern in self._NAME_PATTERNS:
            match = pattern.search(text)
            if match:
                elements.name = match.group(1).strip()
                break
        
        # 提取角色定位
        for kw in self.CHARACTER_KEYWORDS["role"]:
            if kw in text:
                elements.role = kw
                break
        
        # 提取外貌（使用预编译正则）
        for pattern in self._APPEARANCE_PATTERNS.values():
            match = pattern.search(text)
            if match:
                elements.appearance = match.group(1).strip()
                break
        
        # 提取性格（使用预编译正则）
        for pattern in self._PERSONALITY_PATTERNS:
            match = pattern.search(text)
            if match:
                elements.personality.append(match.group(1).strip())
        
        # 提取能力（使用预编译正则）
        for pattern in self._ABILITIES_PATTERNS.values():
            match = pattern.search(text)
            if match:
                abilities_text = match.group(1).strip()
                # 按逗号或顿号分割
                elements.abilities.extend(re.split(r"[，、,]", abilities_text))
        
        # 提取背景（使用预编译正则）
        for pattern in self._BACKGROUND_PATTERNS.values():
            match = pattern.search(text)
            if match:
                elements.background = match.group(1).strip()
                break
        
        return elements
    
    def _extract_all_characters(self, text: str) -> List[CharacterElements]:
        """
        从文本中提取所有人物
        
        Args:
            text: 文本内容
            
        Returns:
            人物元素列表
        """
        characters = []
        
        # 查找人物设定块
        char_blocks = re.split(r"\n{2,}", text)
        
        for block in char_blocks:
            # 检测是否包含人物信息
            has_char_info = any(
                kw in block 
                for keywords in self.CHARACTER_KEYWORDS.values() 
                for kw in keywords
            )
            
            if has_char_info:
                char = self._extract_character(block)
                if char.name:
                    characters.append(char)
        
        # 如果没有找到结构化的人物信息，尝试从对话和行为推断（使用预编译正则）
        if not characters:
            matches = self._NAME_FROM_DIALOGUE.findall(text)
            names = list(set(m[0] for m in matches[:10]))
            
            for name in names[:5]:
                characters.append(CharacterElements(name=name))
        
        return characters[:10]  # 最多返回10个人物
    
    def _extract_plot(self, text: str) -> PlotElements:
        """
        提取情节元素
        
        Args:
            text: 文本内容
            
        Returns:
            情节元素
        """
        elements = PlotElements()
        
        # 提取关键事件（使用预编译正则）
        for pattern in self._EVENT_PATTERNS:
            matches = pattern.findall(text)
            for m in matches[:5]:
                event_text = m[0] if isinstance(m, tuple) else m
                elements.events.append({
                    "description": event_text.strip()[:100]
                })
        
        # 提取冲突（使用预编译正则）
        for pattern in self._CONFLICT_PATTERNS.values():
            matches = pattern.findall(text)
            elements.conflicts.extend(matches[:3])
        
        # 提取转折点（使用预编译正则）
        for pattern in self._TURNING_POINT_PATTERNS.values():
            matches = pattern.findall(text)
            elements.turning_points.extend(matches[:3])
        
        # 提取伏笔（使用预编译正则）
        for pattern in self._FORESHADOWING_PATTERNS.values():
            matches = pattern.findall(text)
            elements.foreshadowing.extend(matches[:3])
        
        return elements
    
    def _extract_style_keywords(self, text: str) -> List[str]:
        """
        提取风格关键词
        
        Args:
            text: 文本内容
            
        Returns:
            风格关键词列表
        """
        style_keywords = []
        
        # 常见风格关键词
        style_patterns = [
            "热血", "虐心", "轻松", "搞笑", "黑暗", "治愈", "爽文", "种田",
            "复仇", "逆袭", "穿越", "重生", "系统", "无敌", "后宫", "单女主",
            "快节奏", "慢热", "细腻", "大气", "幽默", "严肃", "温馨", "悲壮"
        ]
        
        for kw in style_patterns:
            if kw in text:
                style_keywords.append(kw)
        
        return style_keywords[:10]
    
    def _calculate_confidence(self, result: ParsedReference) -> float:
        """
        计算解析置信度
        
        Args:
            result: 解析结果
            
        Returns:
            置信度（0-1）
        """
        score = 0.0
        
        # 世界观元素
        if result.has_worldview():
            wv = result.worldview
            if wv.era:
                score += 0.1
            if wv.power_system:
                score += 0.15
            if wv.forces:
                score += 0.1
            if wv.geography:
                score += 0.05
        
        # 人物元素
        if result.has_characters():
            score += 0.2
            for char in result.characters:
                if char.name:
                    score += 0.05
                if char.personality:
                    score += 0.05
                if char.abilities:
                    score += 0.05
        
        # 情节元素
        if result.has_plot():
            score += 0.1
            if result.plot.events:
                score += 0.05
            if result.plot.conflicts:
                score += 0.05
        
        # 风格关键词
        if result.style_keywords:
            score += 0.1
        
        return min(score, 1.0)
    
    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        import hashlib
        return hashlib.md5(text.encode()).hexdigest()[:16]
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
        logger.info("解析缓存已清除")


class ReferenceFusion:
    """
    参考文本融合器
    
    将解析后的参考文本元素融合到生成Prompt中
    """
    
    @staticmethod
    def fusion_to_worldview_prompt(
        parsed: ParsedReference,
        variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        将参考文本融合到世界观生成Prompt
        
        Args:
            parsed: 解析后的参考文本
            variables: 原始Prompt变量
            
        Returns:
            融合后的Prompt变量
        """
        fused = variables.copy()
        
        if not parsed.has_worldview():
            return fused
        
        wv = parsed.worldview
        reference_context = []
        
        if wv.era:
            reference_context.append(f"参考时代背景：{wv.era}")
        if wv.power_system:
            reference_context.append(f"参考力量体系：{wv.power_system}")
        if wv.power_levels:
            reference_context.append(f"参考等级体系：{'、'.join(wv.power_levels[:5])}")
        if wv.forces:
            forces_text = "、".join(f.get("name", "") for f in wv.forces[:3])
            reference_context.append(f"参考势力组织：{forces_text}")
        if wv.geography:
            reference_context.append(f"参考地理环境：{'、'.join(wv.geography[:3])}")
        
        if reference_context:
            fused["reference_text"] = "\n".join(reference_context)
            fused["reference_type"] = "世界观设定"
        
        return fused
    
    @staticmethod
    def fusion_to_character_prompt(
        parsed: ParsedReference,
        variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        将参考文本融合到人物生成Prompt
        
        Args:
            parsed: 解析后的参考文本
            variables: 原始Prompt变量
            
        Returns:
            融合后的Prompt变量
        """
        fused = variables.copy()
        
        if not parsed.has_characters():
            return fused
        
        reference_context = []
        
        # 添加已有人物作为参考
        for i, char in enumerate(parsed.characters[:5]):
            char_info = []
            if char.name:
                char_info.append(f"姓名：{char.name}")
            if char.role:
                char_info.append(f"定位：{char.role}")
            if char.personality:
                char_info.append(f"性格：{'、'.join(char.personality[:3])}")
            if char.abilities:
                char_info.append(f"能力：{'、'.join(char.abilities[:3])}")
            
            if char_info:
                reference_context.append(f"参考人物{i+1}：" + "，".join(char_info))
        
        if reference_context:
            existing_ref = fused.get("reference_text", "")
            if existing_ref and existing_ref != "无":
                fused["reference_text"] = existing_ref + "\n\n" + "\n".join(reference_context)
            else:
                fused["reference_text"] = "\n".join(reference_context)
            fused["reference_type"] = "人物设定"
        
        return fused
    
    @staticmethod
    def fusion_to_outline_prompt(
        parsed: ParsedReference,
        variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        将参考文本融合到大纲生成Prompt
        
        Args:
            parsed: 解析后的参考文本
            variables: 原始Prompt变量
            
        Returns:
            融合后的Prompt变量
        """
        fused = variables.copy()
        
        reference_context = []
        
        # 添加世界观参考
        if parsed.has_worldview():
            wv = parsed.worldview
            if wv.era or wv.power_system:
                reference_context.append(f"参考世界观：{wv.era}，{wv.power_system}")
        
        # 添加情节参考
        if parsed.has_plot():
            plot = parsed.plot
            if plot.events:
                events_text = "、".join(e.get("description", "")[:20] for e in plot.events[:3])
                reference_context.append(f"参考关键事件：{events_text}")
            if plot.conflicts:
                reference_context.append(f"参考冲突：{'、'.join(plot.conflicts[:3])}")
        
        # 添加人物参考
        if parsed.has_characters():
            char_names = [c.name for c in parsed.characters[:5] if c.name]
            if char_names:
                reference_context.append(f"参考人物：{'、'.join(char_names)}")
        
        if reference_context:
            existing_ref = fused.get("reference_text", "")
            if existing_ref and existing_ref != "无":
                fused["reference_text"] = existing_ref + "\n\n" + "\n".join(reference_context)
            else:
                fused["reference_text"] = "\n".join(reference_context)
            fused["reference_type"] = "大纲设定"
        
        return fused
    
    @staticmethod
    def fusion_to_plot_prompt(
        parsed: ParsedReference,
        variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        将参考文本融合到情节生成Prompt
        
        Args:
            parsed: 解析后的参考文本
            variables: 原始Prompt变量
            
        Returns:
            融合后的Prompt变量
        """
        fused = variables.copy()
        
        reference_context = []
        
        # 添加情节参考
        if parsed.has_plot():
            plot = parsed.plot
            if plot.events:
                reference_context.append("参考关键事件：")
                for e in plot.events[:5]:
                    reference_context.append(f"  - {e.get('description', '')[:50]}")
            if plot.conflicts:
                reference_context.append(f"参考冲突：{'、'.join(plot.conflicts[:3])}")
            if plot.turning_points:
                reference_context.append(f"参考转折点：{'、'.join(plot.turning_points[:3])}")
            if plot.foreshadowing:
                reference_context.append(f"参考伏笔：{'、'.join(plot.foreshadowing[:3])}")
        
        # 添加人物参考
        if parsed.has_characters():
            char_info = []
            for c in parsed.characters[:3]:
                if c.name:
                    info = c.name
                    if c.abilities:
                        info += f"（{'、'.join(c.abilities[:2])}）"
                    char_info.append(info)
            if char_info:
                reference_context.append(f"参考人物：{'、'.join(char_info)}")
        
        if reference_context:
            existing_ref = fused.get("reference_text", "")
            if existing_ref and existing_ref != "无":
                fused["reference_text"] = existing_ref + "\n\n" + "\n".join(reference_context)
            else:
                fused["reference_text"] = "\n".join(reference_context)
            fused["reference_type"] = "情节设定"
        
        return fused
    
    @staticmethod
    def fusion_style_guidance(
        parsed: ParsedReference,
        variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        添加风格指导
        
        Args:
            parsed: 解析后的参考文本
            variables: 原始Prompt变量
            
        Returns:
            融合后的Prompt变量
        """
        fused = variables.copy()
        
        if parsed.style_keywords:
            style_guidance = f"建议风格：{'、'.join(parsed.style_keywords)}"
            
            existing_ref = fused.get("reference_text", "")
            if existing_ref and existing_ref != "无":
                fused["reference_text"] = existing_ref + "\n" + style_guidance
            else:
                fused["reference_text"] = style_guidance
        
        return fused
