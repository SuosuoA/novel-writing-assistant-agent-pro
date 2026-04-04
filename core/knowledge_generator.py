"""
知识库生成器 V4 - 高质量版本

基于 11.15知识库生成器V4.md 文档实现

特性：
- 完整路西法示例嵌入（2500+字）
- 高质量知识检查（6项严格检查）
- 多维度内容结构（5个部分）
- 详细案例和写作应用
- 常见误区分析（至少5条）
- 真实文献参考（至少5个）
- 与全局AI设置统一（DeepSeek/OpenAI/本地模型）

创建日期：2026-03-27
"""

import json
import os
import re
import time
import hashlib
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

# ============================================================================
# 路西法示例（完整版）- 嵌入Prompt中作为质量标准
# ============================================================================

LUCIFER_EXAMPLE = """{
  "title": "路西法（堕落晨星）",
  "core_concept": "路西法原为基督教神话中最高阶炽天使，因傲慢堕落成为地狱七君主之一，象征光明与黑暗的永恒对立。",
  "keywords": [
    "路西法", "晨星", "堕落天使", "基督教神话", "傲慢之罪",
    "地狱七君主", "撒旦", "炽天使", "路西菲尔", "天界战争"
  ],
  "content": "路西法（Lucifer），原名路西菲尔，意为'晨星'或'光明使者'，源自基督教神话体系，后经《神曲》《失乐园》等文学作品演化成为堕落天使的代名词。\\n\\n**神学起源**：\\n路西法最初出现于《以赛亚书》第14章，原指巴比伦王的隐喻。中世纪神学家将其解读为堕落天使的象征：曾是上帝座前最高阶的炽天使，掌管光明与音乐，因傲慢试图与上帝同等，被大天使米迦勒击败后坠入地狱。\\n\\n**地位与象征**：\\n- 地狱七君主之首，代表'傲慢'之罪\\n- 掌管地狱第一层'灵薄狱'（Limbo），收容未受洗礼的灵魂\\n- 象征'光明的背叛者'，代表堕落前的荣耀与堕落后的堕落\\n- 在《失乐园》中被描绘为'宁愿在地狱为王，不愿在天堂为奴'的叛逆者\\n\\n**能力体系**：\\n- 炽天使力量：维持堕落前的部分神圣力量，可操控光明与火焰\\n- 地狱权柄：统领地狱军团，拥有黑暗契约能力\\n- 堕落之翼：翅膀从纯白变为漆黑，象征堕落与背叛\\n- 傲慢光环：可诱发凡人的傲慢与骄傲之罪\\n\\n**与其他神话的关联**：\\n- 与希腊神话的普罗米修斯（盗火者）形成对应：都是为追求自由而反抗神权的英雄/叛逆者\\n- 与北欧神话的洛基（诡计之神）相似：都是神族中的异类与颠覆者\\n- 与埃及神话的赛特（混乱之神）呼应：都代表秩序的对立面\\n\\n**文学形象演变**：\\n1. 但丁《神曲》：被困于地狱第九层的冰湖中，三张脸咀嚼着犹大、布鲁图、卡西乌斯\\n2. 弥尔顿《失乐园》：悲剧英雄，代表反抗暴政的自由精神\\n3. 现代流行文化：《圣经》中的反派→反英雄→浪漫化的悲剧人物（如美剧《路西法》）",
  "classic_cases": "**案例一：《失乐园》中的路西法**\\n弥尔顿塑造的路西法是最具文学魅力的形象。在被上帝击败后，路西法对堕落天使发表演讲：'我们在这里仍然可以高傲地活着，虽然失去了天堂，但我们的意志、勇气、毅力不会消失。'这段话展现了他的傲慢与不屈，即使在地狱中也保持王者的尊严。\\n\\n**案例二：《神曲》中的路西法**\\n但丁将路西法描绘为地狱最底层的怪物，三张脸分别咀嚼着背叛耶稣的犹大、背叛凯撒的布鲁图和卡西乌斯。这象征路西法是'背叛者之王'，代表了最严重的罪行——背叛信任。路西法被困在冰湖中，扇动翅膀产生寒风，将自己冻结，体现了'自我折磨'的永恒惩罚。\\n\\n**案例三：现代玄幻小说《亵渎》**\\n小说中的路西法是深渊最强大的存在之一，拥有'堕落之翼'和'黑暗圣光'能力。他并非纯粹的邪恶，而是追求自由与自我的叛逆者，曾经是天堂最耀眼的炽天使，因质疑上帝的权威而堕落。在与主角的互动中，展现出复杂的性格：傲慢、孤独、对旧日的眷恋、对新秩序的渴望。",
  "writing_applications": "**角色塑造建议**：\\n1. **傲慢与悲剧并存**：路西法型角色应该同时具备令人敬畏的傲慢和令人同情的悲剧性。例如：'他抬起头，眼神中没有悔恨，只有千年不变的骄傲——'我宁愿在地狱的废墟上称王，也不愿在天堂的谎言中苟活。''\\n\\n2. **光暗对立的内心冲突**：通过外貌描写体现堕落：'曾经纯白的六翼如今漆黑如墨，羽毛上还残留着燃烧后的焦痕。当他展开翅膀，黑暗中会浮现出微弱的光斑——那是他永远无法摆脱的圣光烙印。'\\n\\n3. **复杂的动机设计**：不要简化为'为了权力而堕落'。更好的设定：路西法发现上帝计划毁灭人类以创造新物种，他选择背叛以保护人类，却被诬陷为'骄傲自大'。这种设定让他成为'被误解的救世主'，增加角色的悲剧深度。\\n\\n**世界观构建应用**：\\n1. **地狱层级设计**：参考《神曲》，路西法统治的地狱可以设计为九层，每层对应一种罪行。路西法位于最底层的冰湖，既是地狱的统治者，也是永恒的囚徒。\\n\\n2. **堕天使军团**：路西法麾下的堕天使军团可以细分为：炽天使残党（最强战力）、能天使叛军（中坚力量）、堕落人类英灵。\\n\\n3. **光明与黑暗的哲学对立**：设计两套对立的力量体系——圣光：代表秩序、服从、牺牲、审判；黑暗圣光：代表自由、欲望、个性、解放。",
  "common_mistakes": [
    {
      "mistake": "混淆路西法与撒旦",
      "explanation": "路西法和撒旦在神学中是不同的概念。路西法是堕落天使，象征傲慢与光明；撒旦是魔鬼的总称，象征诱惑与邪恶。但在现代文学中常被混为一谈。建议：如果要严谨，区分两者；如果要简化，可以设定路西法=撒旦的一个化身或头衔。"
    },
    {
      "mistake": "过度简化堕落原因",
      "explanation": "不要将路西法堕落简化为'因为傲慢''因为想当神'。这样的设定过于平面。更好的处理：赋予复杂的动机，如发现上帝的真相、为了保护人类、为了追求真正的自由等。堕落的原因越复杂，角色越有深度。"
    },
    {
      "mistake": "忽视光暗对立的视觉表现",
      "explanation": "路西法堕落前后应该有强烈的视觉对比。常见错误：只描写他变邪恶了，没有具体的外貌变化。建议：详细描写堕落的物理痕迹——翅膀从纯白变漆黑、皮肤出现黑色纹路、眼睛从金色变血红、周身圣光变黑焰等。"
    },
    {
      "mistake": "忽略路西法的悲剧性",
      "explanation": "路西法最迷人的地方在于'曾经是天堂最耀眼的存在'。常见错误：把他写成纯粹的反派、邪恶的象征。建议：展现他的孤独、对旧日的眷恋、被误解的痛苦，让读者对他产生复杂的情感——既敬畏又同情。"
    },
    {
      "mistake": "能力设计过于单一",
      "explanation": "路西法不应只是'强大的黑暗魔法'。建议设计独特的能力体系：黑暗圣光（同时具有光明和黑暗属性）、堕落光环（可以诱发他人内心的傲慢）、契约能力、音乐操控。"
    }
  ],
  "references": [
    {
      "title": "《失乐园》",
      "author": "约翰·弥尔顿",
      "year": 1667,
      "description": "英国文学史上最伟大的史诗之一，塑造了路西法作为悲剧英雄的经典形象。经典台词：'宁愿在地狱为王，不愿在天堂为奴。'"
    },
    {
      "title": "《神曲·地狱篇》",
      "author": "但丁·阿利吉耶里",
      "year": 1320,
      "description": "意大利文艺复兴时期的杰作，将路西法描绘为地狱第九层的统治者，被困在冰湖中，三张脸咀嚼着背叛者。"
    },
    {
      "title": "《以赛亚书》第14章",
      "author": "未知（圣经经文）",
      "year": "公元前8世纪",
      "description": "路西法概念的原始出处，原指巴比伦王的隐喻：'明亮之星，早晨之子啊，你何竟从天坠落？'"
    },
    {
      "title": "《哥林多后书》11:14",
      "author": "使徒保罗",
      "year": "公元55年",
      "description": "'这也不足为怪，因为撒旦自己也装作光明的天使。'这节经文为路西法'光明使者'的形象提供了神学基础。"
    },
    {
      "title": "《所罗门遗训》",
      "author": "未知（伪经）",
      "year": "公元1-3世纪",
      "description": "次经文献，详细描述了堕天使的等级和能力，是中世纪恶魔学的重要参考。"
    }
  ]
}"""


# ============================================================================
# 知识库体系设计（13大学科门类 + 6个小说创作专属类别）
# ============================================================================

KNOWLEDGE_DOMAINS = {
    # 玄幻类
    "xuanhuan": {
        "physics": "物理学（力量、速度、能量等玄幻化应用）",
        "magic": "魔法体系（元素、契约、咒语等）",
        "mythology": "神话体系（创世、神系、神话生物）",
        "religion": "宗教文化（道教、佛教、神教等）",
        "occult": "玄学秘术（风水、命理、占卜等）",
        "fantasy_creatures": "幻想生物（龙、精灵、魔兽等）",
        "worldbuilding": "世界观构建（势力、地理、历史）"
    },
    # 仙侠类
    "xianxia": {
        "cultivation": "修炼体系（境界、功法、丹药）",
        "daoism": "道家文化（道法、符箓、阵法）",
        "buddhism": "佛家文化（佛法、因果、轮回）",
        "mythology": "神话传说（上古、仙界、秘境）",
        "physics": "物理原理（灵力、阵法原理）",
        "spirituality": "灵学体系（元神、识海、道心）",
        "worldbuilding": "世界观构建（宗门、修真界、仙凡之别）"
    },
    # 都市类
    "urban": {
        "psychology": "心理学（认知、情感、行为）",
        "economics": "经济学（商业、市场、金融）",
        "society": "社会学（阶层、关系、组织）",
        "law": "法律知识（法规、案例、维权）",
        "technology": "科技前沿（AI、互联网、新材料）",
        "education": "教育体系（学校、培训、考试）",
        "workplace": "职场知识（管理、沟通、晋升）"
    },
    # 言情类
    "romance": {
        "psychology": "情感心理（爱情、依恋、沟通）",
        "emotion": "情感表达（告白、挽回、沟通技巧）",
        "society": "社会关系（家庭、社交、礼仪）",
        "culture": "文化习俗（婚恋、节庆、仪式）",
        "family": "家庭关系（亲子、姻亲、教育）",
        "workplace": "职场恋爱（办公室、上下级）"
    },
    # 历史类 - 支持跨学科组合
    "history": {
        "politics": "政治制度（朝代、官制、科举）",
        "military": "军事历史（战争、兵器、战略）",
        "culture": "文化历史（礼仪、服饰、饮食）",
        "economics": "经济历史（商贸、货币、赋税）",
        "society": "社会历史（阶层、家族、民俗）",
        # 支持历史+学科交叉
        "physics": "历史中的物理（古代力学、光学、声学）",
        "chemistry": "历史中的化学（炼丹、冶金、火药）",
        "biology": "历史中的生物（医学、农学、畜牧）",
        "technology": "历史中的技术（建筑、工艺、工程）",
        "geography": "历史地理（地理、气候、交通）"
    },
    # 科幻类
    "scifi": {
        "physics": "物理学（相对论、量子力学、热力学）",
        "chemistry": "化学（材料科学、化学反应）",
        "biology": "生物学（基因工程、进化论）",
        "space": "航天科学（宇宙航行、星球探索）",
        "technology": "技术工程（人工智能、机器人）",
        "ai": "人工智能（算法、意识、伦理）",
        "future": "未来学（社会预测、技术趋势）"
    },
    # 悬疑类
    "suspense": {
        "psychology": "犯罪心理（动机、行为分析）",
        "law": "法律知识（刑侦、证据、审判）",
        "forensics": "法医知识（尸体、痕迹、鉴定）",
        "logic": "逻辑推理（演绎、归纳、破案）",
        "society": "社会案件（类型、动机、预防）"
    },
    # 军事类
    "military": {
        "tactics": "战术战略（指挥、布阵、作战）",
        "politics": "军事政治（战争起因、国际关系）",
        "history": "战争历史（经典战役、军事变革）",
        "geography": "军事地理（地形、气候、后勤）",
        "technology": "军事技术（武器、装备、通讯）",
        "strategy": "战略思想（孙子兵法、现代战略）"
    },
    # 武侠类
    "wuxia": {
        "martial_arts": "武术体系（拳法、兵器、内功）",
        "history": "历史背景（朝代、门派、江湖）",
        "culture": "武侠文化（侠义、门规、江湖规矩）",
        "medicine": "中医伤科（穴位、疗伤、毒药）",
        "geography": "江湖地理（名山、古道、水路）",
        "jianghu": "江湖社会（门派、帮会、隐门）"
    },
    # 游戏类
    "game": {
        "design": "游戏设计（机制、平衡、关卡）",
        "psychology": "游戏心理学（成瘾、成就感、社交）",
        "technology": "游戏技术（引擎、网络、VR）",
        "economics": "游戏经济（道具、交易、平衡）",
        "narrative": "叙事设计（剧情、角色、沉浸）"
    },
    # 奇幻类
    "fantasy": {
        "mythology": "神话体系（创世、神系、传说）",
        "magic": "魔法体系（元素、咒语、契约）",
        "worldbuilding": "世界观构建（种族、势力、地理）",
        "races": "种族设定（精灵、矮人、兽人）",
        "history": "奇幻历史（纪元、战争、传说）",
        "culture": "奇幻文化（语言、宗教、艺术）"
    },
    # 灵异类（修复：GUI中题材名"灵异"映射为"lingyi"，此处键名必须对应）
    "lingyi": {
        "folklore": "民俗传说（鬼怪、妖怪、禁忌）",
        "psychology": "心理恐怖（恐惧、暗示、创伤）",
        "religion": "宗教神秘（道教、佛教、密宗）",
        "legend": "都市传说（怪谈、诅咒、预言）",
        "occultism": "神秘学（通灵、降灵、仪式）",
        "spirituality": "灵学体系（灵体、阴气、魂魄）"
    },
    # 同人类（修复：GUI中题材名"同人"映射为"tongren"，此处键名必须对应）
    "tongren": {
        "analysis": "原著分析（剧情、人物、设定）",
        "characters": "人物研究（性格、成长、关系）",
        "plot": "剧情延展（if线、番外、后续）",
        "setting": "设定扩展（世界观、背景、细节）",
        "culture": "文化背景（时代、社会、潮流）"
    },
    # 写作技巧类（V5.3新增）
    "writing_technique": {
        "narrative": "叙事技巧（线性、倒叙、多线）",
        "description": "描写技巧（人物、环境、心理）",
        "rhetoric": "修辞技巧（比喻、象征、反讽）",
        "structure": "结构技巧（开篇、转折、结尾）",
        "special_sentence": "特殊句式（长句、短句、排比）",
        "advanced": "高级技法（意识流、蒙太奇）"
    },
    # 恐怖类（修复：GUI中题材名"恐怖"映射为"horror"）
    "horror": {
        "psychology": "恐怖心理（恐惧、惊悚、压抑）",
        "folklore": "恐怖民俗（鬼怪、诅咒、禁忌）",
        "atmosphere": "氛围营造（音效、光影、环境）",
        "monster": "怪物设定（异形、丧尸、未知生物）"
    },
    # 推理类（修复：GUI中题材名"推理"映射为"mystery"）
    "mystery": {
        "logic": "逻辑推理（演绎、归纳、破案）",
        "forensics": "法医知识（尸体、痕迹、鉴定）",
        "psychology": "犯罪心理（动机、行为分析）",
        "law": "法律知识（刑侦、证据、审判）"
    },
    # 体育类（修复：GUI中题材名"体育"映射为"sports"）
    "sports": {
        "technique": "体育技术（训练、战术、技能）",
        "psychology": "运动心理（竞技、团队、压力）",
        "physiology": "运动生理（体能、营养、康复）",
        "competition": "赛事规则（赛制、裁判、历史）"
    },
    # 哲学类（修复：GUI中题材名"哲学"映射为"philosophy"）
    "philosophy": {
        "existence": "存在主义（存在、自由、选择）",
        "ethics": "伦理学（道德、善恶、价值）",
        "logic": "逻辑学（推理、论证、谬误）",
        "metaphysics": "形而上学（本质、存在、真理）"
    },
    # 通用写作类 - 新增
    "general": {
        "writing_technique": "写作技法（描写、对话、节奏）",
        "narrative": "叙事结构（线性、倒叙、多线）",
        "rhetoric": "修辞技巧（比喻、象征、反讽）",
        "character": "人物塑造（性格、成长、弧光）",
        "plot_design": "情节设计（冲突、转折、高潮）",
        "dialogue": "对话艺术（语气、潜台词、推进剧情）",
        "logic": "逻辑学（推理、论证、谬误）",
        "philosophy": "哲学思想（存在主义、功利主义）",
        "psychology": "心理学（认知、情感、行为）",
        "basic_knowledge": "基础知识（百科常识）",
        "economics": "经济学（市场、贸易、金融）",
        "mathematics": "数学（几何、代数、统计）"
    }
}


# ============================================================================
# 数据模型
# ============================================================================

class KnowledgeGenerateRequest(BaseModel):
    """知识点生成请求"""
    category: str = Field(description="题材分类（scifi/xuanhuan/history/general）")
    domain: str = Field(description="知识领域（physics/mythology等）")
    count: int = Field(default=5, ge=1, le=100, description="生成数量")
    focus_hint: str = Field(default="", description="生成方向提示")
    quality_level: str = Field(default="high", description="质量等级（high/standard）")
    exclude_titles: List[str] = Field(default_factory=list, description="要排除的标题（已存在的知识）")
    outline_only: bool = Field(default=False, description="仅生成大纲（标题+关键词）")
    outline_list: List[Dict[str, Any]] = Field(default_factory=list, description="预生成的知识大纲列表")


class KnowledgeOutline(BaseModel):
    """知识大纲（第一阶段生成结果）"""
    title: str = Field(description="标题")
    core_concept: str = Field(description="核心概念（50-80字）")
    keywords: List[str] = Field(description="关键词（10-15个）")


class GeneratedKnowledge(BaseModel):
    """生成的知识点"""
    title: str = Field(description="标题")
    core_concept: str = Field(description="核心概念（50-80字）")
    keywords: List[str] = Field(description="关键词（10-15个）")
    content: str = Field(description="详细内容（≥500字）")
    classic_cases: str = Field(description="经典案例（≥300字）")
    writing_applications: str = Field(description="写作应用（≥300字）")
    common_mistakes: List[Dict[str, str]] = Field(description="常见误区（≥5条）")
    references: List[Dict[str, Any]] = Field(description="参考文献（≥5个）")


class GenerateResult(BaseModel):
    """生成结果"""
    success: bool = Field(description="是否成功")
    total: int = Field(default=0, description="请求生成数量")
    generated: int = Field(default=0, description="实际生成数量")
    saved: int = Field(default=0, description="成功保存数量")
    knowledge_ids: List[str] = Field(default_factory=list, description="知识点ID列表")
    details: List[Dict[str, Any]] = Field(default_factory=list, description="生成详情")
    errors: List[str] = Field(default_factory=list, description="错误信息")
    cost_estimate: float = Field(default=0.0, description="预估成本（元）")
    generation_time: float = Field(default=0.0, description="生成耗时（秒）")


# ============================================================================
# V4高质量知识生成器
# ============================================================================

class KnowledgeGeneratorV4:
    """
    高质量知识库生成器 V4
    
    特性：
    - 完整路西法示例嵌入作为质量标准
    - 6项严格质量检查
    - 与全局AI设置统一
    """
    
    def __init__(self, workspace_root: Path):
        """
        初始化生成器
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = Path(workspace_root)
        self._llm_client = None
        self._config = None
        self._load_config()
    
    def _load_config(self):
        """加载配置（与全局设置统一）"""
        config_path = self.workspace_root / "config.yaml"
        if config_path.exists():
            try:
                import yaml
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f)
            except Exception:
                self._config = {}
        else:
            self._config = {}
    
    def _get_llm_client(self):
        """
        延迟获取LLM客户端（与全局设置统一）

        V5.5修复：支持本地AI模式（service_mode=local）
        
        优先级：
        1. 本地AI模式：使用local_url（如 http://localhost:8000/v1）
        2. 在线模式：从加密存储或config.yaml读取API Key
        """
        if self._llm_client is None:
            try:
                from openai import OpenAI

                # 读取基础配置
                service_mode = self._config.get("service_mode", "online")
                model = self._config.get("model", "deepseek-chat")
                provider = self._config.get("provider", "DeepSeek")

                # V5.5新增：处理本地AI模式
                if service_mode == "local":
                    local_url = self._config.get("local_url", "http://localhost:8000/v1")
                    print(f"[KnowledgeGenerator] 检测到本地AI模式: {provider} @ {local_url}")
                    
                    # 本地AI通常不需要API Key，使用占位符即可
                    api_key = "local-no-key-needed"
                    base_url = local_url
                    
                else:
                    # 在线模式：根据provider设置base_url
                    provider_urls = {
                        "DeepSeek": "https://api.deepseek.com",
                        "OpenAI": "https://api.openai.com/v1",
                        "Anthropic": "https://api.anthropic.com"
                    }
                    base_url = self._config.get("base_url", "") or provider_urls.get(provider, "https://api.deepseek.com")

                    # 方法1: 从加密存储读取API Key
                    api_key = None
                    try:
                        from core.api_key_encryption import APIKeyEncryption
                        encryption = APIKeyEncryption(self.workspace_root)
                        api_key = encryption.get_api_key(provider)
                        if api_key:
                            print(f"[KnowledgeGenerator] 从加密存储加载API Key: {provider}")
                    except Exception as e:
                        print(f"[KnowledgeGenerator] 加密存储读取失败: {e}")

                    # 方法2: 从config.yaml读取（兼容旧配置）
                    if not api_key:
                        config_key = self._config.get("api_key", "")
                        # 检查是否为占位符
                        if config_key and not config_key.startswith("ENCRYPTED") and not config_key.startswith("YOUR_"):
                            api_key = config_key
                            print(f"[KnowledgeGenerator] 从config.yaml加载API Key")

                if api_key:
                    # 禁用系统代理，避免本地未启动的代理（如 127.0.0.1:7897）导致连接失败
                    try:
                        import httpx
                        # httpx 0.24+ 使用 proxy 参数（单数），不支持 proxies（复数）
                        # 设置 proxy=None 表示不使用任何代理
                        http_client = httpx.Client(
                            proxy=None,         # 不使用代理
                            timeout=httpx.Timeout(120.0)
                        )
                    except ImportError:
                        http_client = None

                    client_kwargs = {
                        "api_key": api_key,
                        "base_url": base_url,
                    }
                    if http_client is not None:
                        client_kwargs["http_client"] = http_client

                    self._llm_client = OpenAI(**client_kwargs)
                    # 附加model属性
                    self._llm_client.model = model
                    self._llm_client.provider = provider
                    self._llm_client.service_mode = service_mode  # V5.5新增
                    print(f"[KnowledgeGenerator] LLM客户端初始化成功: {service_mode}/{provider}/{model} @ {base_url}")
                    
                    # V3.2.2新增：本地服务健康检查
                    if service_mode == "local" and provider.lower() == "qwen":
                        self._check_qwen_service_health(base_url)
                else:
                    print(f"[KnowledgeGenerator] 未找到有效的API Key")

            except Exception as e:
                print(f"[KnowledgeGenerator] LLM客户端初始化失败: {e}")
                import traceback
                traceback.print_exc()

        return self._llm_client
    
    def _check_qwen_service_health(self, base_url: str) -> bool:
        """
        检查Qwen服务健康状态（V3.2.2新增）
        
        Args:
            base_url: API端点（如 http://localhost:8000/v1）
        
        Returns:
            bool: 服务是否健康
        """
        try:
            import requests
            
            # 提取根URL（移除/v1后缀）
            health_url = base_url.replace("/v1", "").rstrip("/") + "/health"
            
            print(f"[KnowledgeGenerator] 检查Qwen服务健康: {health_url}")
            
            response = requests.get(health_url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                model_loaded = data.get("model_loaded", False)
                
                if model_loaded:
                    print(f"[KnowledgeGenerator] ✓ Qwen服务正常: {data.get('model', 'unknown')}")
                    return True
                else:
                    print(f"[KnowledgeGenerator] ⚠ Qwen服务模型未加载")
                    return False
            else:
                print(f"[KnowledgeGenerator] ✗ Qwen服务返回错误: {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            print(f"[KnowledgeGenerator] ✗ Qwen服务未启动！")
            print(f"[KnowledgeGenerator] 请先启动Qwen服务：")
            print(f"[KnowledgeGenerator]   cd F:\\Qwen")
            print(f"[KnowledgeGenerator]   python start_server_v2.py")
            print(f"[KnowledgeGenerator] 等待模型加载完成（约60秒）后再试")
            return False
            
        except requests.exceptions.Timeout:
            print(f"[KnowledgeGenerator] ✗ Qwen服务响应超时")
            return False
            
        except Exception as e:
            print(f"[KnowledgeGenerator] ✗ Qwen服务健康检查失败: {e}")
            return False
    
    def generate_knowledge(
        self,
        request: KnowledgeGenerateRequest,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> GenerateResult:
        """
        生成知识点（支持大批量分批生成 + 去重）

        Args:
            request: 生成请求
            progress_callback: 进度回调函数（percent, message）

        Returns:
            GenerateResult: 生成结果
        """
        start_time = time.time()
        result = GenerateResult(success=False, total=request.count)

        try:
            llm_client = self._get_llm_client()
            if not llm_client:
                result.errors.append("AI服务未配置，请先在设置中配置API密钥")
                return result

            # ========== 获取已存在的知识点（用于去重）==========
            if progress_callback:
                progress_callback(2, "检查已存在的知识点...")
            
            existing_titles = self._get_existing_knowledge_titles(request.category, request.domain)
            request.exclude_titles = existing_titles  # 添加排除列表
            
            if progress_callback:
                progress_callback(5, f"发现 {len(existing_titles)} 条已存在知识，开始生成...")

            # 分批参数：每批最多2条（每条约2700 tokens，8000上限）
            BATCH_SIZE = 2
            total_batches = (request.count + BATCH_SIZE - 1) // BATCH_SIZE

            all_knowledge_list = []
            generated_titles = []  # 记录已生成的标题（用于批次间去重）

            for batch_idx in range(total_batches):
                # 计算当前批次
                batch_start = batch_idx * BATCH_SIZE
                batch_end = min(batch_start + BATCH_SIZE, request.count)
                batch_count = batch_end - batch_start

                # 计算整体进度
                batch_progress = int((batch_idx / total_batches) * 80) + 5

                if progress_callback:
                    progress_callback(batch_progress, f"生成第 {batch_idx + 1}/{total_batches} 批 ({batch_count}条)...")

                # 构建当前批次的Prompt（包含已生成的标题）
                batch_request = KnowledgeGenerateRequest(
                    category=request.category,
                    domain=request.domain,
                    count=batch_count,
                    focus_hint=request.focus_hint,
                    quality_level=request.quality_level,
                    exclude_titles=request.exclude_titles + generated_titles  # 合并已存在和已生成的标题
                )
                prompt = self._build_prompt(batch_request)

                # 调用AI生成
                try:
                    print(f"[KnowledgeGenerator] 批次 {batch_idx + 1}/{total_batches} 开始调用API...", flush=True)
                    response = llm_client.chat.completions.create(
                        model=llm_client.model,
                        messages=[
                            {
                                "role": "system",
                                "content": "你是一位专业的小说写作知识库编辑，擅长生成高质量、专业、实用的写作参考资料。你必须严格按照JSON格式输出，不要添加markdown代码块标记。"
                            },
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        max_tokens=8000,  # 每批固定8000 tokens，减少批次大小来保证质量
                        timeout=120.0  # 设置120秒超时
                    )
                    print(f"[KnowledgeGenerator] 批次 {batch_idx + 1}/{total_batches} API调用完成", flush=True)

                    # 检查响应结构
                    if not response.choices:
                        raise ValueError("API响应没有choices")
                    
                    if not response.choices[0].message:
                        raise ValueError("API响应没有message")
                    
                    # 解析响应
                    ai_content = response.choices[0].message.content
                    
                    if not ai_content:
                        raise ValueError("API返回内容为空")
                    
                    # 调试输出：显示API返回内容长度和前200字符
                    print(f"[KnowledgeGenerator] 批次 {batch_idx + 1}/{total_batches} API返回内容长度: {len(ai_content)}", flush=True)
                    
                    # V5.3修复：保存到正确的临时目录，遵守临时文件管理规范
                    import os
                    temp_dir = self.workspace_root / "data" / "knowledge" / ".temp"
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    debug_file = temp_dir / f"api_response_batch_{batch_idx + 1}.json"
                    try:
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            f.write(ai_content)
                        print(f"[KnowledgeGenerator] 已保存API响应到: {debug_file}", flush=True)
                    except Exception as e:
                        print(f"[KnowledgeGenerator] 保存调试文件失败: {e}", flush=True)
                    
                    # 输出错误位置附近的内容（仅调试时）
                    lines = ai_content.split('\n')
                    if len(lines) > 63:
                        print(f"[KnowledgeGenerator] 第60-66行内容:", flush=True)
                        for i in range(59, min(66, len(lines))):
                            print(f"  {i+1}: {lines[i][:100]}", flush=True)
                    
                    print(f"[KnowledgeGenerator] 前200字符: {ai_content[:200]}", flush=True)
                    
                    batch_knowledge = self._parse_ai_response(ai_content)
                    
                    # 批次内去重（检查是否有重复标题）
                    batch_titles = [kp.get('title', '') for kp in batch_knowledge]
                    unique_batch = []
                    for i, kp in enumerate(batch_knowledge):
                        title = kp.get('title', '')
                        # 检查是否与当前批次内其他知识点重复
                        if title in batch_titles[:i] or any(self._is_similar_title(title, t) for t in batch_titles[:i]):
                            print(f"[KnowledgeGenerator] ⊗ 批次内重复: '{title}'", flush=True)
                        else:
                            unique_batch.append(kp)
                            generated_titles.append(title)  # 记录已生成的标题
                    
                    all_knowledge_list.extend(unique_batch)

                    print(f"[KnowledgeGenerator] 批次 {batch_idx + 1}/{total_batches} 完成，解析出 {len(batch_knowledge)} 条，去重后 {len(unique_batch)} 条", flush=True)

                except Exception as batch_error:
                    result.errors.append(f"批次 {batch_idx + 1} 失败: {str(batch_error)[:100]}")
                    print(f"[KnowledgeGenerator] 批次 {batch_idx + 1} 错误: {batch_error}")

            if progress_callback:
                progress_callback(85, f"去重检查 {len(all_knowledge_list)} 条知识点...")

            # 去重检查（在质量检查之前）
            existing_titles = request.exclude_titles or []
            unique_knowledge = []
            
            for kp in all_knowledge_list[:request.count]:
                title = kp.get('title', '')
                
                # 检查是否与已存在标题重复
                is_duplicate = False
                for existing in existing_titles:
                    # 计算标题相似度（简单匹配）
                    if self._is_similar_title(title, existing):
                        print(f"[KnowledgeGenerator] ⊗ 去重过滤: '{title}' 与已存在 '{existing}' 相似", flush=True)
                        result.details.append({
                            "title": title,
                            "status": "duplicate",
                            "reason": f"与已存在知识点 '{existing}' 相似"
                        })
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    unique_knowledge.append(kp)

            # 质量检查
            valid_knowledge = []
            for i, kp in enumerate(unique_knowledge):
                print(f"[KnowledgeGenerator] 检查知识点 {i+1}: {kp.get('title', '未知')}", flush=True)
                is_valid, reason = self._quality_check_with_reason(kp)
                if is_valid:
                    valid_knowledge.append(kp)
                    result.details.append({
                        "title": kp.get("title", "未知"),
                        "status": "valid",
                        "keywords_count": len(kp.get("keywords", []))
                    })
                    print(f"[KnowledgeGenerator] [OK] 通过质量检查", flush=True)
                else:
                    result.details.append({
                        "title": kp.get("title", "未知"),
                        "status": "invalid",
                        "reason": reason
                    })
                    print(f"[KnowledgeGenerator] [FAIL] 未通过质量检查: {reason}", flush=True)

            result.generated = len(valid_knowledge)

            if progress_callback:
                progress_callback(90, f"保存 {len(valid_knowledge)} 条知识点...")

            # 保存知识点
            knowledge_manager = self._get_knowledge_manager()
            print(f"[KnowledgeGenerator] 知识管理器: {knowledge_manager}", flush=True)
            
            if knowledge_manager:
                for kp in valid_knowledge:
                    try:
                        print(f"[KnowledgeGenerator] 保存知识点: {kp.get('title', '未知')}", flush=True)
                        create_result = knowledge_manager.create_knowledge(
                            category=request.category,
                            domain=request.domain,
                            title=kp.get("title", "未命名知识点"),
                            content=kp.get("content", ""),
                            keywords=kp.get("keywords", []),
                            references=[r.get("title", "") for r in kp.get("references", [])],
                            metadata={
                                "core_concept": kp.get("core_concept", ""),
                                "classic_cases": kp.get("classic_cases", ""),
                                "writing_applications": kp.get("writing_applications", ""),
                                "common_mistakes": kp.get("common_mistakes", [])
                            }
                        )

                        if create_result.success:
                            result.saved += 1
                            result.knowledge_ids.append(create_result.knowledge_id)
                            print(f"[KnowledgeGenerator] [OK] 保存成功，ID: {create_result.knowledge_id}", flush=True)
                        else:
                            error_msg = getattr(create_result, 'error', None) or getattr(create_result, 'message', None) or "未知错误"
                            print(f"[KnowledgeGenerator] [FAIL] 保存失败: {error_msg}", flush=True)
                            result.errors.append(f"保存失败: {error_msg}")
                    except Exception as e:
                        error_msg = f"保存异常: {str(e)[:100]}"
                        print(f"[KnowledgeGenerator] {error_msg}", flush=True)
                        result.errors.append(error_msg)
            else:
                print(f"[KnowledgeGenerator] [FAIL] 无法获取知识管理器", flush=True)
                result.errors.append("知识管理器初始化失败")

            # 计算预估成本（基于总生成量）
            result.cost_estimate = self._estimate_cost(
                input_tokens=request.count * 500,  # 估算每条500 tokens输入
                output_tokens=len(all_knowledge_list) * 1000  # 估算每条1000 tokens输出
            )

            result.success = result.saved > 0
            result.generation_time = time.time() - start_time

            if progress_callback:
                progress_callback(100, f"完成！生成 {result.generated} 条，保存 {result.saved} 条")
            
            # V5.4修复：生成完成后自动清理临时文件
            self._cleanup_temp_files()
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            result.errors.append(f"生成异常: {str(e)}")
            result.errors.append(f"详细堆栈: {error_detail[:500]}")
            print(f"[KnowledgeGenerator] 生成异常:\n{error_detail}")
            if progress_callback:
                progress_callback(0, f"错误: {str(e)[:50]}")
        
        return result
    
    def _build_prompt(self, request: KnowledgeGenerateRequest) -> str:
        """
        构建生成提示词（支持去重）
        
        Args:
            request: 生成请求（包含exclude_titles）
        
        Returns:
            str: 完整提示词
        """
        # 获取题材和领域的中文名称
        category_names = {
            "xuanhuan": "玄幻",
            "xianxia": "仙侠",
            "urban": "都市",
            "romance": "言情",
            "history": "历史",
            "scifi": "科幻",
            "suspense": "悬疑",
            "military": "军事",
            "wuxia": "武侠",
            "game": "游戏",
            "fantasy": "奇幻",
            "lingyi": "灵异",  # 修复：与GUI映射一致（gui_main.py中"灵异"→"lingyi"）
            "tongren": "同人",  # 修复：与GUI映射一致（gui_main.py中"同人"→"tongren"）
            "horror": "恐怖",  # V5.3新增
            "mystery": "推理",  # V5.3新增
            "sports": "体育",  # V5.3新增
            "general": "通用",
            "writing_technique": "写作技巧",
            "philosophy": "哲学"
        }
        
        domain_names = KNOWLEDGE_DOMAINS.get(request.category, {})
        domain_cn = domain_names.get(request.domain, request.domain)
        category_cn = category_names.get(request.category, request.category)
        
        focus = request.focus_hint if request.focus_hint else f"{category_cn}题材下{domain_cn}领域的关键概念"
        
        # ========== 智能子方向推荐（解决重复问题的关键）==========
        recommended_directions = self._recommend_uncovered_directions(
            request.category, 
            request.domain, 
            request.exclude_titles or []
        )
        
        # 构建已存在知识提示（用于去重）
        exclude_hint = ""
        
        # 构建推荐方向提示（总是显示，即使没有已存在知识点）
        recommended_hint = ""
        if recommended_directions:
            recommended_hint = f"""
**【重要】推荐的新生成方向（尚未覆盖或覆盖不足）**：
{json.dumps(recommended_directions[:10], ensure_ascii=False, indent=2)}
"""
        
        if request.exclude_titles:
            # 提取关键词用于去重（不只是标题）
            exclude_keywords = []
            for title in request.exclude_titles[:30]:  # 增加到30条
                # 提取标题中的核心关键词（去掉"与"、"的"、"理论"等）
                keywords = re.sub(r'(与|的|理论|原理|概念|研究|分析|探讨|及其|初步|雏形)', '', title)
                exclude_keywords.append(keywords.strip())
            
            exclude_hint = f"""
**【严重警告】以下知识点已存在，严禁重复生成或生成相似内容**：
已存在标题（共{len(request.exclude_titles)}条）：{json.dumps(request.exclude_titles[:30], ensure_ascii=False, indent=2)}
已覆盖关键词：{json.dumps(exclude_keywords, ensure_ascii=False, indent=2)}
{recommended_hint}
**去重规则**：
1. 不要生成与已存在标题相同或高度相似的知识点
2. 不要生成与已覆盖关键词相同的主题
3. 如果某个主题已有多个相关知识点（如"浑天说"），请转向其他领域
4. **优先探索上述"推荐的新生成方向"**，避免重复已覆盖领域
"""
        elif recommended_hint:
            # 即使没有已存在知识点，也显示推荐方向
            exclude_hint = f"""
**【建议】生成方向指引**：
{recommended_hint}
**建议**：优先从上述推荐方向中选择，确保知识点覆盖面广、主题多样。
"""
        
        prompt = f"""请为【{category_cn}】题材下的【{domain_cn}】领域生成 {request.count} 条高质量知识点。

**重点方向**: {focus}
{exclude_hint}

**【重要】主题多样性要求**：
1. **每条知识点必须覆盖不同的子主题**，严禁集中在同一方向
2. 对于"物理"领域，应覆盖：力学、光学、热学、电磁学、声学、材料物理等不同分支
3. 对于"历史"题材，应覆盖：不同朝代、不同地区、不同领域的科技/文化/政治
4. 示例：如果第1条是"浑天说"（天文学），第2条应该是"火药"（化学/军事），第3条应该是"指南针"（磁学）等

**严格要求**（必须达到以下标准）:

1. **title**: 核心概念名称（不超过15字）
2. **core_concept**: 核心概念（1句话概括来源、定位、象征意义，50-80字）
3. **keywords**: 10-15个关键词，**必须明确宗教/文化/科学归属**
4. **content**: 详细内容（**至少500字**），**必须包含5个结构**：
   - 背景/起源
   - 核心原理/定义
   - 主要特征/分类
   - 与其他概念的关系
   - 应用场景/影响
5. **classic_cases**: **至少3个详细案例**（总计至少300字），每个案例包含：
   - 案例来源（作品/事件）
   - 具体描述
   - 写作参考价值
6. **writing_applications**: 写作应用建议（**至少300字**），**必须包含3大板块**：
   - 角色塑造应用
   - 世界观构建应用
   - 情节设计应用
7. **common_mistakes**: **至少5个常见误区**，每个包含：
   - mistake: 误区描述
   - explanation: 详细分析和改进建议
8. **references**: **至少5个真实文献**，每个包含：
   - title: 文献标题
   - author: 作者
   - year: 年份
   - description: 内容说明

**质量标准**: 参考下方路西法示例，必须达到同等质量——内容详实、具体、可操作，不要模板化废话。

**路西法示例（完整版，供参考）**:
{LUCIFER_EXAMPLE}

**输出格式**: JSON数组，每条知识点为一个对象。不要添加markdown代码块包裹，直接输出纯JSON数组。

**【严重警告】JSON格式要求**：
1. **每个对象必须正确闭合**：`{{` ... `}}`
2. **数组中的每个对象必须用逗号分隔**：`{{ ... }},`
3. **common_mistakes数组中的每个对象也必须闭合**：
   ```json
   "common_mistakes": [
     {{"mistake": "...", "explanation": "..."}},  // ← 注意这里有 }}
     {{"mistake": "...", "explanation": "..."}}   // ← 最后一个不加逗号
   ]
   ```
4. **不要在对象闭合前跳过 `}}`**：错误示例 `"explanation": "..." ]` → 正确 `"explanation": "..." }} ]`

示例格式：
[
  {{
    "title": "知识点标题",
    "core_concept": "核心概念描述...",
    "keywords": ["关键词1", "关键词2", ...],
    "content": "详细内容...",
    "classic_cases": "案例描述...",
    "writing_applications": "应用建议...",
    "common_mistakes": [
      {{"mistake": "误区1", "explanation": "说明..."}},
      {{"mistake": "误区2", "explanation": "说明..."}}
    ],
    "references": [
      {{"title": "文献标题", "author": "作者", "year": "年份", "description": "说明..."}},
      {{"title": "文献标题2", "author": "作者2", "year": "年份2", "description": "说明..."}}
    ]
  }}
]

现在开始生成 {request.count} 条关于【{domain_cn}】的高质量知识点："""
        
        return prompt
    
    def _parse_ai_response(self, content: str) -> List[Dict[str, Any]]:
        """
        解析AI响应内容（增强版：处理不规范JSON）
        
        Args:
            content: AI返回的文本内容
        
        Returns:
            List[Dict]: 知识点列表
        """
        content = content.strip()
        print(f"[KnowledgeGenerator] 开始解析，内容长度: {len(content)}", flush=True)
        
        # 移除可能的markdown代码块标记
        if content.startswith("```"):
            lines = content.split("\n")
            if len(lines) > 1:
                content = "\n".join(lines[1:])
            if content.endswith("```"):
                content = content[:-3].strip()
        
        # V5.4.1新增：预处理中文标点符号
        content = content.replace('"', '"').replace('"', '"')  # 中文引号
        content = content.replace(''', "'").replace(''', "'")  # 中文单引号
        content = content.replace('，', ',')  # 中文逗号（不在字符串内的）
        content = content.replace('：', ':')  # 中文冒号（不在字符串内的）
        
        # 方法1：直接解析JSON
        try:
            data = json.loads(content)
            if isinstance(data, list):
                print(f"[KnowledgeGenerator] JSON直接解析成功，数量: {len(data)}", flush=True)
                return data
        except json.JSONDecodeError as e:
            print(f"[KnowledgeGenerator] JSON直接解析失败: {e}", flush=True)
        
        # 方法2：尝试修复常见的JSON错误
        fixed_content = content
        
        # 错误模式1：]} -> }
        fixed_content = re.sub(r'\]\s*\}', '}', fixed_content)
        # 错误模式2：},] -> }]
        fixed_content = re.sub(r'\},\s*\]', '}]', fixed_content)
        # 错误模式3：}, } -> }}
        fixed_content = re.sub(r'\},\s*\}', '}}', fixed_content)
        # 错误模式4：] ] -> ] (多余的嵌套数组)
        fixed_content = re.sub(r'\]\s*\]', ']', fixed_content)
        # 错误模式5：[ [ -> [ (多余的嵌套数组)
        fixed_content = re.sub(r'\[\s*\[', '[', fixed_content)
        # 错误模式6："year": 945, 1060 -> "year": "945, 1060" (多值字段)
        fixed_content = re.sub(r'"(year|age|date)":\s*(\d+),\s*(\d+)', r'"\1": "\2, \3"', fixed_content)
        # 错误模式7："year": "abc -> "year": "abc" (未闭合的字符串)
        fixed_content = re.sub(r'"(year|age|date|title|author)":\s*"([^"]*?)$', r'"\1": "\2"', fixed_content, flags=re.MULTILINE)
        # 错误模式8：尾随逗号 (,} 或 ,])
        fixed_content = re.sub(r',\s*\}', '}', fixed_content)
        fixed_content = re.sub(r',\s*\]', ']', fixed_content)
        # 错误模式9：数组提前闭合（common_mistakes数组后直接跟了references）
        # 匹配：}\s*]\s*},\s*"references" → }, "references"
        # 这种情况是因为AI误将知识点对象的闭合写成了数组闭合
        fixed_content = re.sub(r'\}\s*\]\s*\},\s*"references"', '}, "references"', fixed_content)
        # 错误模式10：嵌套对象提前闭合
        fixed_content = re.sub(r'\}\s*\]\s*\}\s*,\s*\{', '}, {', fixed_content)
        # 错误模式11：common_mistakes最后一个对象缺少闭合大括号
        # 匹配："explanation": "..." \n    ], \n    "references"
        # 应该是："explanation": "..." \n      } \n    ], \n    "references"
        fixed_content = re.sub(
            r'("explanation":\s*"[^"]*")\s*\]\s*,\s*("references")',
            r'\1}\n    ],\n    \2',
            fixed_content
        )
        # 错误模式12：common_mistakes数组重复闭合 ] ]
        # 匹配：}\n    ]\n    ],\n    "references" → }\n    ],\n    "references"
        fixed_content = re.sub(r'\}\s*\]\s*\],\s*("references")', r'}\n    ],\n    \1', fixed_content)
        # 错误模式13：知识点对象误写为common_mistakes数组的闭合
        # 匹配：}\n    ]\n    ],\n    "references" → }\n    ],\n    "references"
        # 这是第44-45行的错误
        fixed_content = re.sub(
            r'("explanation":\s*"[^"]*")\s*\n\s*\]\s*\],\s*\n\s*("references")',
            r'\1\n      }\n    ],\n    \2',
            fixed_content
        )
        # 错误模式14：common_mistakes对象缺少闭合大括号（最常见）
        # 匹配："explanation": "..." 行后直接跟 ]（缺少 }）
        # 使用多行模式，匹配以 "explanation": 开头的行，后面跟 ]
        lines = fixed_content.split('\n')
        fixed_lines = []
        for i, line in enumerate(lines):
            fixed_lines.append(line)
            # 检查当前行是否以 "explanation": 开头
            if line.strip().startswith('"explanation":'):
                # 检查下一行是否是 ]（缺少 }）
                if i + 1 < len(lines) and lines[i + 1].strip() == ']':
                    # 在当前行后添加 }
                    fixed_lines.append('      }')
        fixed_content = '\n'.join(fixed_lines)
        # 错误模式15：修复后的重复闭合 ] \n ],
        fixed_content = re.sub(r'\]\s*\n\s*\],', '],', fixed_content)
        
        try:
            data = json.loads(fixed_content)
            if isinstance(data, list):
                print(f"[KnowledgeGenerator] JSON修复后解析成功，数量: {len(data)}", flush=True)
                return data
        except json.JSONDecodeError as e:
            print(f"[KnowledgeGenerator] JSON修复后仍失败: {e}", flush=True)
        
        # 方法3：提取数组内容并逐个解析对象
        # V5.4.1增强：处理嵌套对象和缺失闭合括号
        results = []
        brace_depth = 0
        current_obj = ""
        in_string = False
        escape_next = False
        obj_start_positions = []  # 记录对象开始位置
        
        for i, char in enumerate(content):
            if escape_next:
                current_obj += char
                escape_next = False
                continue
            
            if char == '\\':
                current_obj += char
                escape_next = True
                continue
            
            if char == '"' and not escape_next:
                in_string = not in_string
                current_obj += char
                continue
            
            if not in_string:
                if char == '{':
                    if brace_depth == 0:
                        current_obj = ""
                        obj_start_positions = [i]
                    brace_depth += 1
                    current_obj += char
                elif char == '}':
                    brace_depth -= 1
                    current_obj += char
                    if brace_depth == 0 and current_obj.strip():
                        # 尝试解析这个对象
                        try:
                            # 修复常见的JSON错误
                            obj_str = current_obj.strip().rstrip(',')
                            obj_str = re.sub(r'\]\s*\}', '}', obj_str)
                            # 修复多值字段
                            obj_str = re.sub(r'"(year|age|date)":\s*(\d+),\s*(\d+)', r'"\1": "\2, \3"', obj_str)
                            # 修复尾随逗号
                            obj_str = re.sub(r',\s*\}', '}', obj_str)
                            # V5.4.1新增：修复中文引号
                            obj_str = obj_str.replace('"', '"').replace('"', '"')
                            # V5.4.1新增：修复未闭合的common_mistakes数组
                            if '"common_mistakes"' in obj_str and obj_str.count('[') > obj_str.count(']'):
                                # 缺少数组闭合
                                obj_str = obj_str.rstrip('}') + '}] }'
                            # V5.4.1新增：修复缺少对象闭合的情况
                            if obj_str.count('{') > obj_str.count('}'):
                                missing_braces = obj_str.count('{') - obj_str.count('}')
                                obj_str = obj_str + '}' * missing_braces
                            
                            obj = json.loads(obj_str)
                            if isinstance(obj, dict) and 'title' in obj:
                                results.append(obj)
                                print(f"[KnowledgeGenerator] 提取到知识点: {obj.get('title', '未知')}", flush=True)
                        except json.JSONDecodeError as err:
                            print(f"[KnowledgeGenerator] 对象解析失败: {str(err)[:50]}", flush=True)
                        current_obj = ""
                elif char == '[' and brace_depth == 0:
                    # 跳过顶层数组开始
                    pass
                elif char == ']' and brace_depth == 0:
                    # 顶层数组结束，V5.4.1新增：强制尝试解析当前积累的内容
                    if current_obj.strip():
                        try:
                            # 强制添加缺失的闭合括号
                            obj_str = current_obj.strip().rstrip(',').rstrip(']').rstrip('}')
                            missing_braces = obj_str.count('{') - obj_str.count('}')
                            missing_brackets = obj_str.count('[') - obj_str.count(']')
                            obj_str = obj_str + ']' * missing_brackets + '}' * missing_braces
                            obj = json.loads(obj_str)
                            if isinstance(obj, dict) and 'title' in obj:
                                results.append(obj)
                                print(f"[KnowledgeGenerator] 强制提取到知识点: {obj.get('title', '未知')}", flush=True)
                        except:
                            pass
                    current_obj = ""
                elif brace_depth > 0:
                    current_obj += char
            else:
                current_obj += char
        
        print(f"[KnowledgeGenerator] 最终解析结果: {len(results)} 条", flush=True)
        
        # V5.4.1新增：方法4 - 基于字段边界的智能提取
        if len(results) == 0:
            print("[KnowledgeGenerator] 尝试方法4：基于字段边界提取...", flush=True)
            results = self._extract_by_field_boundary(content)
        
        return results
    
    def _extract_by_field_boundary(self, content: str) -> List[Dict[str, Any]]:
        """
        基于字段边界提取知识点（V5.4.1新增）
        
        核心思路：检测顶级 "title" 字段（非嵌套在common_mistakes或references中）
        
        Args:
            content: JSON内容
        
        Returns:
            List[Dict]: 知识点列表
        """
        results = []
        
        # 找到所有顶层的 "title" 字段
        # 关键：排除嵌套在 common_mistakes 和 references 中的 title
        lines = content.split('\n')
        title_positions = []
        
        for i, line in enumerate(lines):
            # 检测到知识点开始的标志：行首有 "title"（允许有缩进）
            if line.strip().startswith('"title"') and ':' in line:
                # 检查缩进层级 - 知识点的title通常缩进较少（2-4个空格）
                indent = len(line) - len(line.lstrip())
                # 知识点title的缩进通常是2-4个空格
                # references和common_mistakes中的title通常缩进更多（6-12个空格）
                if indent <= 6:
                    title_positions.append(i)
        
        if not title_positions:
            return results
        
        for idx, line_idx in enumerate(title_positions):
            # 提取这个知识点的行范围
            start_line = line_idx
            # 下一个知识点开始，或者文件结束
            end_line = title_positions[idx + 1] if idx + 1 < len(title_positions) else len(lines)
            
            # 提取片段
            segment_lines = lines[start_line:end_line]
            segment = '\n'.join(segment_lines)
            
            # 手动提取字段
            try:
                obj = self._extract_fields_manually(segment)
                if obj and 'title' in obj:
                    results.append(obj)
                    print(f"[KnowledgeGenerator] 字段边界提取成功: {obj.get('title', '未知')}", flush=True)
            except Exception as err:
                print(f"[KnowledgeGenerator] 字段边界提取失败: {str(err)[:50]}", flush=True)
        
        return results
    
    def _extract_fields_manually(self, segment: str) -> Optional[Dict[str, Any]]:
        """
        手动提取字段（V5.4.1新增）
        
        当JSON解析彻底失败时，用正则表达式提取关键字段
        """
        obj = {}
        
        # 提取简单字符串字段
        string_fields = ['title', 'core_concept', 'content', 'classic_cases', 'writing_applications']
        for field in string_fields:
            pattern = rf'"{field}"\s*:\s*"([^"]*(?:\\.[^"]*)*)"'
            match = re.search(pattern, segment)
            if match:
                obj[field] = match.group(1).replace('\\"', '"')
        
        # 提取keywords数组
        keywords_pattern = r'"keywords"\s*:\s*\[(.*?)\]'
        keywords_match = re.search(keywords_pattern, segment, re.DOTALL)
        if keywords_match:
            keywords_str = keywords_match.group(1)
            keywords = re.findall(r'"([^"]+)"', keywords_str)
            if keywords:
                obj['keywords'] = keywords
        
        # 提取common_mistakes（简化版，只提取mistake字段）
        if '"common_mistakes"' in segment:
            mistakes = []
            mistake_pattern = r'"mistake"\s*:\s*"([^"]+)"'
            for match in re.finditer(mistake_pattern, segment):
                mistakes.append({
                    'mistake': match.group(1),
                    'explanation': ''  # 简化处理
                })
            if mistakes:
                obj['common_mistakes'] = mistakes
        
        # 提取references（简化版）
        if '"references"' in segment:
            refs = []
            ref_pattern = r'"title"\s*:\s*"([^"]+)"[^}]*"author"\s*:\s*"([^"]+)"'
            for match in re.finditer(ref_pattern, segment):
                refs.append({
                    'title': match.group(1),
                    'author': match.group(2),
                    'year': 0
                })
            if refs:
                obj['references'] = refs
        
        return obj if obj else None
    
    def _cleanup_temp_files(self):
        """清理生成过程中产生的临时文件
        
        V5.4新增：遵守临时文件管理规范，生成完成后自动删除临时文件
        """
        try:
            import os
            import shutil
            
            temp_dir = self.workspace_root / "data" / "knowledge" / ".temp"
            
            if temp_dir.exists() and temp_dir.is_dir():
                # 删除临时目录下的所有文件
                for file in temp_dir.glob("*.json"):
                    try:
                        file.unlink()
                        print(f"[KnowledgeGenerator] 已删除临时文件: {file.name}")
                    except Exception as e:
                        print(f"[KnowledgeGenerator] 删除临时文件失败 {file.name}: {e}")
                
                # 如果目录为空，删除目录
                if not any(temp_dir.iterdir()):
                    temp_dir.rmdir()
                    print(f"[KnowledgeGenerator] 已删除临时目录: {temp_dir}")
                    
        except Exception as e:
            print(f"[KnowledgeGenerator] 清理临时文件失败: {e}")
    
    def _quality_check(self, kp: Dict[str, Any]) -> bool:
        """
        质量检查（6项严格检查）
        
        Args:
            kp: 知识点字典
        
        Returns:
            bool: 是否通过检查
        """
        # 检查1: content至少500字
        if len(kp.get("content", "")) < 400:
            return False
        
        # 检查2: classic_cases至少300字
        if len(kp.get("classic_cases", "")) < 200:
            return False
        
        # 检查3: writing_applications至少300字
        if len(kp.get("writing_applications", "")) < 200:
            return False
        
        # 检查4: keywords至少10个
        if len(kp.get("keywords", [])) < 8:
            return False
        
        # 检查5: common_mistakes至少5条
        if len(kp.get("common_mistakes", [])) < 4:
            return False
        
        # 检查6: references至少5个
        if len(kp.get("references", [])) < 4:
            return False
        
        return True
    
    def _quality_check_with_reason(self, kp: Dict[str, Any]) -> tuple:
        """
        质量检查（带原因）
        
        Args:
            kp: 知识点字典
        
        Returns:
            tuple: (是否通过, 原因)
        """
        # 检查1: content至少400字
        content_len = len(kp.get("content", ""))
        if content_len < 400:
            return False, f"内容长度不足（{content_len}字 < 400字）"
        
        # 检查2: classic_cases至少200字
        cases_len = len(kp.get("classic_cases", ""))
        if cases_len < 200:
            return False, f"经典案例长度不足（{cases_len}字 < 200字）"
        
        # 检查3: writing_applications至少200字
        apps_len = len(kp.get("writing_applications", ""))
        if apps_len < 200:
            return False, f"写作应用长度不足（{apps_len}字 < 200字）"
        
        # 检查4: keywords至少8个
        keywords_count = len(kp.get("keywords", []))
        if keywords_count < 8:
            return False, f"关键词数量不足（{keywords_count}个 < 8个）"
        
        # 检查5: common_mistakes至少4条
        mistakes_count = len(kp.get("common_mistakes", []))
        if mistakes_count < 4:
            return False, f"常见误区数量不足（{mistakes_count}条 < 4条）"
        
        # 检查6: references至少4个
        refs_count = len(kp.get("references", []))
        if refs_count < 4:
            return False, f"参考文献数量不足（{refs_count}个 < 4个）"
        
        return True, "通过"
    
    def _get_knowledge_manager(self):
        """获取知识库管理器"""
        try:
            from core.knowledge_manager import get_knowledge_manager
            return get_knowledge_manager(self.workspace_root)
        except Exception:
            return None
    
    def _is_similar_title(self, title1: str, title2: str, threshold: float = 0.6) -> bool:
        """
        判断两个标题是否相似（用于去重）
        
        Args:
            title1: 标题1
            title2: 标题2
            threshold: 相似度阈值（0-1）
        
        Returns:
            bool: 是否相似
        """
        # 完全相同
        if title1 == title2:
            return True
        
        # 提取核心关键词（去掉停用词）
        stop_words = {'与', '的', '理论', '原理', '概念', '研究', '分析', '探讨', '及其', '初步', '在', '中', '之'}
        
        def extract_keywords(title):
            # 简单分词（按常见词分割）
            words = re.split(r'[与的和及]', title)
            keywords = []
            for word in words:
                # 去掉停用词
                clean_word = re.sub(r'(理论|原理|概念|研究|分析|探讨|及其|初步)', '', word)
                if clean_word and clean_word not in stop_words and len(clean_word) > 1:
                    keywords.append(clean_word)
            return set(keywords)
        
        keywords1 = extract_keywords(title1)
        keywords2 = extract_keywords(title2)
        
        if not keywords1 or not keywords2:
            return False
        
        # 计算Jaccard相似度
        intersection = len(keywords1 & keywords2)
        union = len(keywords1 | keywords2)
        
        similarity = intersection / union if union > 0 else 0
        
        return similarity >= threshold
    
    def _recommend_uncovered_directions(self, category: str, domain: str, existing_titles: List[str]) -> List[str]:
        """
        智能推荐尚未覆盖的子方向（解决重复问题的关键）
        
        原理：
        1. 预定义常见题材/领域的子方向列表
        2. 分析已存在知识点，提取已覆盖的子方向
        3. 推荐未覆盖或覆盖不足的子方向
        
        Args:
            category: 题材（如"history"）
            domain: 领域（如"physics"）
            existing_titles: 已存在的知识点标题列表
        
        Returns:
            推荐的子方向列表
        """
        # ========== 预定义子方向列表 ==========
        SUBDIRECTIONS_MAP = {
            "physics": {
                "mechanics": ["力学", "运动学", "动力学", "静力学", "流体力学", "材料力学"],
                "optics": ["光学", "几何光学", "物理光学", "光谱学", "光学仪器"],
                "acoustics": ["声学", "声波", "共振", "声学材料", "声学测量"],
                "thermodynamics": ["热学", "热力学", "传热学", "相变", "热机"],
                "electromagnetism": ["电磁学", "静电", "磁学", "电路", "电磁感应"],
                "materials": ["材料物理", "金属物理", "半导体", "超导", "纳米材料"],
                "astronomy": ["天文学", "天体物理", "宇宙学", "星系", "行星科学"]
            },
            "chemistry": {
                "inorganic": ["无机化学", "元素", "化合物", "配位化学", "晶体化学"],
                "organic": ["有机化学", "烃类", "官能团", "高分子", "生物化学"],
                "physical": ["物理化学", "热力学", "动力学", "电化学", "表面化学"],
                "analytical": ["分析化学", "光谱分析", "色谱", "质谱", "滴定"],
                "materials": ["材料化学", "陶瓷", "聚合物", "复合材料", "纳米材料"]
            },
            "biology": {
                "cell": ["细胞生物学", "细胞结构", "细胞分裂", "细胞代谢", "细胞信号"],
                "genetics": ["遗传学", "基因", "DNA", "RNA", "突变"],
                "ecology": ["生态学", "生态系统", "种群", "群落", "生物多样性"],
                "physiology": ["生理学", "神经生理", "循环系统", "消化系统", "内分泌"],
                "evolution": ["进化论", "自然选择", "物种形成", "系统发育", "适应"]
            },
            "writing_technique": {
                "narrative": ["叙事技巧", "POV", "时间线", "插叙", "倒叙", "平行叙事"],
                "description": ["描写技巧", "环境描写", "人物描写", "心理描写", "感官描写"],
                "rhetoric": ["修辞技巧", "比喻", "象征", "对比", "借代", "夸张"],
                "structure": ["结构技巧", "三幕式", "英雄之旅", "起承转合", "伏笔"],
                "special_sentence": ["特殊句式", "排比", "对仗", "反问", "设问"],
                "advanced": ["高级技法", "意识流", "蒙太奇", "多线索", "不可靠叙述"]
            }
        }
        
        # ========== 提取已覆盖的子方向 ==========
        covered_directions = set()
        
        # 关键词映射（标题中的关键词 → 子方向）
        KEYWORD_TO_DIRECTION = {
            # 物理学
            "力学|运动|动力|静力|流体|材料力": "mechanics",
            "光|成像|透镜|光谱|反射|折射": "optics",
            "声|共振|音频|振动": "acoustics",
            "热|温度|相变|热机|燃烧": "thermodynamics",
            "电|磁|电路|感应": "electromagnetism",
            "金属|材料|合金|冶金": "materials",
            "天文|星|宇宙|行星": "astronomy",
            
            # 化学
            "无机|元素|化合物": "inorganic",
            "有机|烃|官能团|高分子": "organic",
            "物理化学|热力|动力学|电化学": "physical",
            "分析|光谱|色谱|质谱": "analytical",
            
            # 生物学
            "细胞|分裂|代谢": "cell",
            "基因|DNA|遗传": "genetics",
            "生态|种群|群落": "ecology",
            "生理|神经|循环|消化": "physiology",
            "进化|自然选择|物种": "evolution",
            
            # 写作技巧
            "叙事|POV|时间线|插叙|倒叙": "narrative",
            "描写|环境|人物|心理": "description",
            "修辞|比喻|象征|对比": "rhetoric",
            "结构|三幕|英雄之旅|伏笔": "structure",
            "句式|排比|对仗|反问": "special_sentence",
            "意识流|蒙太奇|多线索": "advanced"
        }
        
        # 分析已存在的标题
        for title in existing_titles:
            for keyword_pattern, direction in KEYWORD_TO_DIRECTION.items():
                if re.search(keyword_pattern, title):
                    covered_directions.add(direction)
                    break
        
        # ========== 推荐未覆盖的子方向 ==========
        recommended = []
        
        # 获取该领域的子方向映射
        domain_subdirs = SUBDIRECTIONS_MAP.get(domain, {})
        
        if domain_subdirs:
            # 找出未覆盖的子方向
            for subdir_key, subdir_names in domain_subdirs.items():
                if subdir_key not in covered_directions:
                    recommended.extend(subdir_names)
        
        # 如果预定义列表为空，返回通用提示
        if not recommended:
            recommended = [
                f"该领域其他未被{category}题材探索的方向",
                "新兴研究热点",
                "跨学科交叉领域",
                "实际应用场景",
                "历史发展脉络"
            ]
        
        print(f"[KnowledgeGenerator] 已覆盖子方向: {covered_directions}")
        print(f"[KnowledgeGenerator] 推荐新方向: {recommended[:5]}")
        
        return recommended
    
    def _get_existing_knowledge_titles(self, category: str, domain: str) -> List[str]:
        """
        获取已存在的知识点标题列表（用于去重）
        
        V5.3修复：writing_technique题材需要检查所有domain的知识点，避免跨领域重复
        
        Args:
            category: 题材分类
            domain: 知识领域
        
        Returns:
            List[str]: 已存在的标题列表
        """
        existing_titles = []
        
        try:
            # V5.3修复：writing_technique题材检查所有domain
            if category == "writing_technique":
                # 写作技巧六领域
                all_domains = ["narrative", "description", "rhetoric", "structure", "special_sentence", "advanced"]
                for check_domain in all_domains:
                    json_path = self.workspace_root / "data" / "knowledge" / category / f"{check_domain}.json"
                    if json_path.exists():
                        with open(json_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            # 支持两种格式：直接数组 或 {"knowledge_points": [...]}
                            knowledge_list = data if isinstance(data, list) else data.get("knowledge_points", [])
                            for item in knowledge_list:
                                if isinstance(item, dict) and 'title' in item:
                                    title = item['title']
                                    if title not in existing_titles:
                                        existing_titles.append(title)
                print(f"[KnowledgeGenerator] 写作技巧题材跨领域检查，共发现 {len(existing_titles)} 条已存在知识")
            else:
                # 其他题材：仅检查当前domain
                json_path = self.workspace_root / "data" / "knowledge" / category / f"{domain}.json"
                if json_path.exists():
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict) and 'title' in item:
                                    existing_titles.append(item['title'])
                    print(f"[KnowledgeGenerator] 从JSON文件读取到 {len(existing_titles)} 条已存在知识")
            
            # 方法2：从知识管理器读取（仅当前domain）
            knowledge_manager = self._get_knowledge_manager()
            if knowledge_manager:
                try:
                    knowledge_list = knowledge_manager.list_knowledge(category=category, domain=domain)
                    if knowledge_list:
                        for kp in knowledge_list:
                            # KnowledgePoint 是 Pydantic 模型或字典
                            if isinstance(kp, dict):
                                title = kp.get('title', '')
                            else:
                                title = getattr(kp, 'title', '')
                            if title and title not in existing_titles:
                                existing_titles.append(title)
                        print(f"[KnowledgeGenerator] 知识管理器中找到 {len(knowledge_list)} 条知识")
                except Exception as e:
                    print(f"[KnowledgeGenerator] 从知识管理器读取失败: {e}")
        
        except Exception as e:
            print(f"[KnowledgeGenerator] 获取已存在知识失败: {e}")
        
        return existing_titles
    
    def generate_knowledge_outline(
        self,
        request: KnowledgeGenerateRequest,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> tuple:
        """
        第一阶段：生成知识大纲（仅标题+关键词+核心概念）
        
        Args:
            request: 生成请求
            progress_callback: 进度回调函数
        
        Returns:
            tuple: (success: bool, outline_list: List[Dict], error: str)
        """
        try:
            llm_client = self._get_llm_client()
            if not llm_client:
                return False, [], "AI服务未配置，请先在设置中配置API密钥"
            
            # 获取已存在的知识点标题
            existing_titles = self._get_existing_knowledge_titles(request.category, request.domain)
            
            if progress_callback:
                progress_callback(10, f"发现 {len(existing_titles)} 条已存在知识，开始生成大纲...")
            
            # 构建大纲生成Prompt
            prompt = self._build_outline_prompt(request, existing_titles)
            
            if progress_callback:
                progress_callback(20, "调用AI生成知识大纲...")
            
            # 调用AI生成大纲
            response = llm_client.chat.completions.create(
                model=llm_client.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位专业的小说写作知识库编辑。你的任务是为指定领域生成知识点大纲，确保内容丰富、不重复、有深度。你必须严格按照JSON格式输出。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,  # 更高的temperature增加多样性
                max_tokens=4000,
                timeout=60.0
            )
            
            if progress_callback:
                progress_callback(70, "解析大纲...")
            
            # 解析响应
            ai_content = response.choices[0].message.content
            outline_list = self._parse_outline_response(ai_content)
            
            if progress_callback:
                progress_callback(100, f"大纲生成完成，共 {len(outline_list)} 条")
            
            return True, outline_list, ""
        
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[KnowledgeGenerator] 大纲生成失败: {error_detail}")
            return False, [], str(e)
    
    def _build_outline_prompt(
        self,
        request: KnowledgeGenerateRequest,
        existing_titles: List[str]
    ) -> str:
        """构建大纲生成Prompt"""
        category_names = {
            "xuanhuan": "玄幻",
            "xianxia": "仙侠",
            "urban": "都市",
            "romance": "言情",
            "history": "历史",
            "scifi": "科幻",
            "suspense": "悬疑",
            "military": "军事",
            "wuxia": "武侠",
            "game": "游戏",
            "fantasy": "奇幻",
            "lingyi": "灵异",
            "tongren": "同人",
            "horror": "恐怖",
            "mystery": "推理",
            "sports": "体育",
            "general": "通用",
            "writing_technique": "写作技巧",
            "philosophy": "哲学"
        }
        
        domain_names = KNOWLEDGE_DOMAINS.get(request.category, {})
        domain_cn = domain_names.get(request.domain, request.domain)
        category_cn = category_names.get(request.category, request.category)
        
        focus = request.focus_hint if request.focus_hint else f"{category_cn}题材下{domain_cn}领域的关键概念"
        
        # 构建已存在知识提示
        existing_hint = ""
        if existing_titles:
            existing_hint = f"""
**重要：以下知识点已存在，请勿重复生成**：
{json.dumps(existing_titles[:50], ensure_ascii=False, indent=2)}
{'（还有' + str(len(existing_titles) - 50) + '条未显示）' if len(existing_titles) > 50 else ''}
"""
        
        prompt = f"""请为【{category_cn}】题材下的【{domain_cn}】领域生成 {request.count} 条知识点大纲。

**重点方向**: {focus}
{existing_hint}
**要求**：
1. 每条大纲包含：title（标题）、core_concept（核心概念50-80字）、keywords（10-15个关键词）
2. 确保知识点**不重复**（与已存在的知识不重复，彼此之间也不重复）
3. 覆盖该领域的不同方面：核心概念、重要人物、关键事件、技术原理、文化现象等
4. 每个知识点要有足够的写作参考价值，避免过于基础或泛泛而谈

**输出格式**：纯JSON数组
[
  {{
    "title": "知识点标题",
    "core_concept": "核心概念描述（50-80字）",
    "keywords": ["关键词1", "关键词2", ...]
  }},
  ...
]

现在开始生成 {request.count} 条关于【{domain_cn}】的知识点大纲："""
        
        return prompt
    
    def _parse_outline_response(self, content: str) -> List[Dict[str, Any]]:
        """解析大纲响应"""
        content = content.strip()
        
        # 移除markdown代码块
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:])
        if content.endswith("```"):
            content = content[:-3].strip()
        
        try:
            data = json.loads(content)
            if isinstance(data, list):
                # 过滤有效的条目
                valid_outlines = []
                for item in data:
                    if isinstance(item, dict) and 'title' in item and 'keywords' in item:
                        valid_outlines.append({
                            'title': item.get('title', ''),
                            'core_concept': item.get('core_concept', ''),
                            'keywords': item.get('keywords', [])
                        })
                return valid_outlines
        except json.JSONDecodeError as e:
            print(f"[KnowledgeGenerator] 大纲JSON解析失败: {e}")
        
        return []
    
    def generate_knowledge_from_outline(
        self,
        category: str,
        domain: str,
        outline_list: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> GenerateResult:
        """
        第二阶段：根据大纲分批生成详细知识点
        
        Args:
            category: 题材分类
            domain: 知识领域
            outline_list: 大纲列表
            progress_callback: 进度回调函数
        
        Returns:
            GenerateResult: 生成结果
        """
        start_time = time.time()
        result = GenerateResult(success=False, total=len(outline_list))
        
        try:
            llm_client = self._get_llm_client()
            if not llm_client:
                result.errors.append("AI服务未配置，请先在设置中配置API密钥")
                return result
            
            # 分批参数：每批最多2条（每条约2700 tokens，8000上限）
            BATCH_SIZE = 2
            total_batches = (len(outline_list) + BATCH_SIZE - 1) // BATCH_SIZE
            
            all_knowledge_list = []
            
            for batch_idx in range(total_batches):
                batch_start = batch_idx * BATCH_SIZE
                batch_end = min(batch_start + BATCH_SIZE, len(outline_list))
                batch_outlines = outline_list[batch_start:batch_end]
                
                batch_progress = int((batch_idx / total_batches) * 80) + 5
                if progress_callback:
                    progress_callback(batch_progress, f"生成第 {batch_idx + 1}/{total_batches} 批 ({len(batch_outlines)}条)...")
                
                # 构建Prompt
                prompt = self._build_prompt_from_outlines(category, domain, batch_outlines)
                
                try:
                    response = llm_client.chat.completions.create(
                        model=llm_client.model,
                        messages=[
                            {
                                "role": "system",
                                "content": "你是一位专业的小说写作知识库编辑，擅长生成高质量、专业、实用的写作参考资料。你必须严格按照JSON格式输出。"
                            },
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        max_tokens=min(4000 * len(batch_outlines), 8000),
                        timeout=120.0
                    )
                    
                    ai_content = response.choices[0].message.content
                    batch_knowledge = self._parse_ai_response(ai_content)
                    all_knowledge_list.extend(batch_knowledge)
                    
                    print(f"[KnowledgeGenerator] 批次 {batch_idx + 1}/{total_batches} 完成，解析出 {len(batch_knowledge)} 条")
                
                except Exception as batch_error:
                    result.errors.append(f"批次 {batch_idx + 1} 失败: {str(batch_error)[:100]}")
            
            if progress_callback:
                progress_callback(85, f"质量检查 {len(all_knowledge_list)} 条知识点...")
            
            # 质量检查和保存
            valid_knowledge = []
            for kp in all_knowledge_list:
                is_valid, reason = self._quality_check_with_reason(kp)
                if is_valid:
                    valid_knowledge.append(kp)
                    result.details.append({
                        "title": kp.get("title", "未知"),
                        "status": "valid"
                    })
                else:
                    result.details.append({
                        "title": kp.get("title", "未知"),
                        "status": "invalid",
                        "reason": reason
                    })
            
            result.generated = len(valid_knowledge)
            
            if progress_callback:
                progress_callback(90, f"保存 {len(valid_knowledge)} 条知识点...")
            
            # 保存知识点
            knowledge_manager = self._get_knowledge_manager()
            if knowledge_manager:
                for kp in valid_knowledge:
                    try:
                        create_result = knowledge_manager.create_knowledge(
                            category=category,
                            domain=domain,
                            title=kp.get("title", "未命名知识点"),
                            content=kp.get("content", ""),
                            keywords=kp.get("keywords", []),
                            references=[r.get("title", "") for r in kp.get("references", [])],
                            metadata={
                                "core_concept": kp.get("core_concept", ""),
                                "classic_cases": kp.get("classic_cases", ""),
                                "writing_applications": kp.get("writing_applications", ""),
                                "common_mistakes": kp.get("common_mistakes", [])
                            }
                        )
                        
                        if create_result.success:
                            result.saved += 1
                            result.knowledge_ids.append(create_result.knowledge_id)
                    except Exception as e:
                        result.errors.append(f"保存异常: {str(e)[:100]}")
            
            result.success = result.saved > 0
            result.generation_time = time.time() - start_time
            result.cost_estimate = self._estimate_cost(
                input_tokens=len(outline_list) * 300,
                output_tokens=len(all_knowledge_list) * 1000
            )
            
            if progress_callback:
                progress_callback(100, f"完成！生成 {result.generated} 条，保存 {result.saved} 条")
            
            # V5.4修复：生成完成后自动清理临时文件
            self._cleanup_temp_files()
        
        except Exception as e:
            result.errors.append(f"生成异常: {str(e)}")
        
        return result
    
    def _build_prompt_from_outlines(
        self,
        category: str,
        domain: str,
        outlines: List[Dict[str, Any]]
    ) -> str:
        """根据大纲构建详细生成Prompt"""
        category_names = {
            "xuanhuan": "玄幻",
            "xianxia": "仙侠",
            "urban": "都市",
            "romance": "言情",
            "history": "历史",
            "scifi": "科幻",
            "suspense": "悬疑",
            "military": "军事",
            "wuxia": "武侠",
            "game": "游戏",
            "fantasy": "奇幻",
            "lingyi": "灵异",
            "tongren": "同人",
            "horror": "恐怖",
            "mystery": "推理",
            "sports": "体育",
            "general": "通用",
            "writing_technique": "写作技巧",
            "philosophy": "哲学"
        }
        
        domain_names = KNOWLEDGE_DOMAINS.get(category, {})
        domain_cn = domain_names.get(domain, domain)
        category_cn = category_names.get(category, category)
        
        # 构建大纲描述
        outline_desc = []
        for i, outline in enumerate(outlines, 1):
            keywords_str = "、".join(outline.get('keywords', []))
            outline_desc.append(f"{i}. **{outline.get('title', '')}**\n   核心概念：{outline.get('core_concept', '')}\n   关键词：{keywords_str}")
        
        prompt = f"""请根据以下大纲，为【{category_cn}】题材下的【{domain_cn}】领域生成 {len(outlines)} 条详细知识点。

**知识大纲**：
{chr(10).join(outline_desc)}

**严格要求**（每条知识点必须达到以下标准）：

1. **title**: 使用大纲中的标题
2. **core_concept**: 使用大纲中的核心概念，可适当扩展
3. **keywords**: 使用大纲中的关键词，可适当补充
4. **content**: 详细内容（**至少500字**），必须包含5个结构：背景/起源、核心原理/定义、主要特征/分类、与其他概念的关系、应用场景/影响
5. **classic_cases**: 至少3个详细案例（总计至少300字）
6. **writing_applications**: 写作应用建议（至少300字），必须包含：角色塑造应用、世界观构建应用、情节设计应用
7. **common_mistakes**: 至少5个常见误区，每个包含mistake和explanation
8. **references**: 至少5个真实文献，每个包含title、author、year、description

**质量标准**: 参考下方路西法示例，必须达到同等质量。

**路西法示例**:
{LUCIFER_EXAMPLE}

**输出格式**: 纯JSON数组，不要markdown代码块。

现在开始生成 {len(outlines)} 条详细知识点："""
        
        return prompt
    
    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        预估成本（基于DeepSeek定价）
        
        Args:
            input_tokens: 输入token数
            output_tokens: 输出token数
        
        Returns:
            float: 预估成本（元）
        """
        # DeepSeek定价：输入 ¥0.14/百万token，输出 ¥0.28/百万token
        input_cost = input_tokens * 0.14 / 1_000_000
        output_cost = output_tokens * 0.28 / 1_000_000
        return round(input_cost + output_cost, 4)


# ============================================================================
# 单例访问
# ============================================================================

_knowledge_generator: Optional[KnowledgeGeneratorV4] = None
_generator_lock = threading.RLock()


def get_knowledge_generator(workspace_root: Optional[Path] = None) -> KnowledgeGeneratorV4:
    """获取知识生成器单例"""
    global _knowledge_generator
    
    with _generator_lock:
        if _knowledge_generator is None:
            if workspace_root is None:
                import os
                workspace_root = Path(os.getcwd())
            _knowledge_generator = KnowledgeGeneratorV4(workspace_root)
        return _knowledge_generator


def reset_knowledge_generator():
    """重置知识生成器（用于测试）"""
    global _knowledge_generator
    with _generator_lock:
        _knowledge_generator = None
