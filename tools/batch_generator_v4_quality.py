"""
高质量知识库生成器 V4 - 参考路西法示例
目标: 5000+条高质量知识点
"""
import json
import os
import time
import hashlib
from datetime import datetime
from pathlib import Path
from openai import OpenAI
import yaml

# 配置
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
KNOWLEDGE_BASE_PATH = Path(r'E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\data\knowledge')
LOG_FILE = Path(r'E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\tests\batch_generation_v4.log')

# 加载配置
config_path = Path(r'E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\config.yaml')
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

client = OpenAI(
    api_key=config.get('api_key'),
    base_url='https://api.deepseek.com'
)

# 路西法示例（完整版）
LUCIFER_EXAMPLE = """{
  "title": "路西法（堕落晨星）",
  "core_concept": "路西法原为基督教神话中最高阶炽天使，因傲慢堕落成为地狱七君主之一，象征光明与黑暗的永恒对立。",
  "keywords": [
    "路西法",
    "晨星",
    "堕落天使",
    "基督教神话",
    "傲慢之罪",
    "地狱七君主",
    "撒旦",
    "炽天使",
    "路西菲尔",
    "天界战争"
  ],
  "content": "路西法（Lucifer），原名路西菲尔，意为'晨星'或'光明使者'，源自基督教神话体系，后经《神曲》《失乐园》等文学作品演化成为堕落天使的代名词。\\n\\n**神学起源**：\\n路西法最初出现于《以赛亚书》第14章，原指巴比伦王的隐喻。中世纪神学家将其解读为堕落天使的象征：曾是上帝座前最高阶的炽天使，掌管光明与音乐，因傲慢试图与上帝同等，被大天使米迦勒击败后坠入地狱。\\n\\n**地位与象征**：\\n- 地狱七君主之首，代表'傲慢'之罪\\n- 掌管地狱第一层'灵薄狱'（Limbo），收容未受洗礼的灵魂\\n- 象征'光明的背叛者'，代表堕落前的荣耀与堕落后的堕落\\n- 在《失乐园》中被描绘为'宁愿在地狱为王，不愿在天堂为奴'的叛逆者\\n\\n**能力体系**：\\n- 炽天使力量：维持堕落前的部分神圣力量，可操控光明与火焰\\n- 地狱权柄：统领地狱军团，拥有黑暗契约能力\\n- 堕落之翼：翅膀从纯白变为漆黑，象征堕落与背叛\\n- 傲慢光环：可诱发凡人的傲慢与骄傲之罪\\n\\n**与其他神话的关联**：\\n- 与希腊神话的普罗米修斯（盗火者）形成对应：都是为追求自由而反抗神权的英雄/叛逆者\\n- 与北欧神话的洛基（诡计之神）相似：都是神族中的异类与颠覆者\\n- 与埃及神话的赛特（混乱之神）呼应：都代表秩序的对立面\\n\\n**文学形象演变**：\\n1. 但丁《神曲》：被困于地狱第九层的冰湖中，三张脸咀嚼着犹大、布鲁图、卡西乌斯\\n2. 弥尔顿《失乐园》：悲剧英雄，代表反抗暴政的自由精神\\n3. 现代流行文化：《圣经》中的反派→反英雄→浪漫化的悲剧人物（如美剧《路西法》）",
  "classic_cases": "**案例一：《失乐园》中的路西法**\\n弥尔顿塑造的路西法是最具文学魅力的形象。在被上帝击败后，路西法对堕落天使发表演讲：'我们在这里仍然可以高傲地活着，虽然失去了天堂，但我们的意志、勇气、毅力不会消失。'这段话展现了他的傲慢与不屈，即使在地狱中也保持王者的尊严。\\n\\n**案例二：《神曲》中的路西法**\\n但丁将路西法描绘为地狱最底层的怪物，三张脸分别咀嚼着背叛耶稣的犹大、背叛凯撒的布鲁图和卡西乌斯。这象征路西法是'背叛者之王'，代表了最严重的罪行——背叛信任。路西法被困在冰湖中，扇动翅膀产生寒风，将自己冻结，体现了'自我折磨'的永恒惩罚。\\n\\n**案例三：现代玄幻小说《亵渎》**\\n小说中的路西法是深渊最强大的存在之一，拥有'堕落之翼'和'黑暗圣光'能力。他并非纯粹的邪恶，而是追求自由与自我的叛逆者，曾经是天堂最耀眼的炽天使，因质疑上帝的权威而堕落。在与主角的互动中，展现出复杂的性格：傲慢、孤独、对旧日的眷恋、对新秩序的渴望。\\n\\n**案例四：玄幻世界观中的应用**\\n某玄幻小说设定：路西法是'光明之神'的堕落形态，曾是天界最高统治者之一。他创造了'黑暗圣光'这一独特能量体系，可同时操控光明与黑暗力量。他的堕落原因不是傲慢，而是发现上帝（光明之神）在吞噬世界，为了拯救世界而选择背叛，成为'堕落的救世主'。这种设定颠覆了传统的'傲慢之罪'叙事，赋予路西法更复杂的动机。",
  "writing_applications": "**角色塑造建议**：\\n1. **傲慢与悲剧并存**：路西法型角色应该同时具备令人敬畏的傲慢和令人同情的悲剧性。例如：'他抬起头，眼神中没有悔恨，只有千年不变的骄傲——'我宁愿在地狱的废墟上称王，也不愿在天堂的谎言中苟活。''\\n\\n2. **光暗对立的内心冲突**：通过外貌描写体现堕落：'曾经纯白的六翼如今漆黑如墨，羽毛上还残留着燃烧后的焦痕。当他展开翅膀，黑暗中会浮现出微弱的光斑——那是他永远无法摆脱的圣光烙印。'\\n\\n3. **复杂的动机设计**：不要简化为'为了权力而堕落'。更好的设定：路西法发现上帝计划毁灭人类以创造新物种，他选择背叛以保护人类，却被诬陷为'骄傲自大'。这种设定让他成为'被误解的救世主'，增加角色的悲剧深度。\\n\\n**世界观构建应用**：\\n1. **地狱层级设计**：参考《神曲》，路西法统治的地狱可以设计为九层，每层对应一种罪行。路西法位于最底层的冰湖，既是地狱的统治者，也是永恒的囚徒。\\n\\n2. **堕天使军团**：路西法麾下的堕天使军团可以细分为：\\n   - 炽天使残党（最强战力，如别西卜、利维坦）\\n   - 能天使叛军（中坚力量，曾负责天界守卫）\\n   - 堕落人类英灵（被路西法力量转化的英雄灵魂）\\n\\n3. **光明与黑暗的哲学对立**：设计两套对立的力量体系——\\n   - 圣光：代表秩序、服从、牺牲、审判\\n   - 黑暗圣光：代表自由、欲望、个性、解放\\n   这种对立不仅是力量的对抗，更是价值观的冲突。\\n\\n**情节设计建议**：\\n1. **堕落的真相**：设置悬念——路西法真的是因为傲慢而堕落吗？随着剧情推进，主角发现真相：路西法发现了上帝的秘密（如上帝是外星生物、上帝在吞噬世界、上帝是虚假的幻象等），选择背叛以保护真相。\\n\\n2. **路西法的救赎/彻底堕落**：设计两条路线——\\n   - 救赎线：主角帮助路西法证明清白，恢复炽天使身份\\n   - 彻底堕落线：路西法为复仇彻底放弃光明，成为真正的黑暗之神，甚至超越地狱的范畴，成为多元宇宙的威胁\\n\\n3. **路西法与主角的关系**：可以设计为师徒、盟友、敌人的动态变化。初期路西法是强大的敌人，中期因共同目标（对抗上帝）成为盟友，后期因价值观分歧（路西法想毁灭一切，主角想拯救世界）再次成为敌人。",
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
      "explanation": "路西法不应只是'强大的黑暗魔法'。建议设计独特的能力体系：\\n- 黑暗圣光：同时具有光明和黑暗属性\\n- 堕落光环：可以诱发他人内心的傲慢\\n- 契约能力：可以与人类签订灵魂契约\\n- 音乐操控：曾掌管天界的音乐，堕落后用音乐蛊惑人心"
    }
  ],
  "references": [
    {
      "title": "《失乐园》",
      "author": "约翰·弥尔顿",
      "year": 1667,
      "description": "英国文学史上最伟大的史诗之一，塑造了路西法作为悲剧英雄的经典形象。书中的路西法因傲慢反抗上帝，被击败后坠入地狱，但即使在地狱中也保持王者的尊严。经典台词：'宁愿在地狱为王，不愿在天堂为奴。'"
    },
    {
      "title": "《神曲·地狱篇》",
      "author": "但丁·阿利吉耶里",
      "year": 1320,
      "description": "意大利文艺复兴时期的杰作，将路西法描绘为地狱第九层的统治者，被困在冰湖中，三张脸咀嚼着背叛者。象征路西法是'背叛者之王'。"
    },
    {
      "title": "《以赛亚书》第14章",
      "author": "未知（圣经经文）",
      "year": "公元前8世纪",
      "description": "路西法概念的原始出处，原指巴比伦王的隐喻：'明亮之星，早晨之子啊，你何竟从天坠落？'中世纪神学家将其解读为堕落天使的象征。"
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
      "description": "次经文献，详细描述了堕天使的等级和能力，是中世纪恶魔学的重要参考。其中记载路西法是堕天使的首领，带领三分之一天使背叛上帝。"
    }
  ]
}"""

# 完整知识库体系 - 参考13大学科门类 + 文学创作
KNOWLEDGE_STRUCTURE = {
    # ========== 新增类别（参考13大学科门类）==========
    "philosophy": {  # 哲学门类
        "target": 300,
        "domains": {
            "chinese_philosophy": {"target": 100, "focus": "儒家、道家、佛家、墨家、法家、名家"},
            "western_philosophy": {"target": 100, "focus": "古希腊哲学、中世纪哲学、近现代哲学、存在主义"},
            "aesthetics": {"target": 50, "focus": "美学理论、审美心理、艺术哲学"},
            "logic_philosophy": {"target": 50, "focus": "形式逻辑、辩证逻辑、逻辑悖论"}
        }
    },
    "economics": {  # 经济学门类
        "target": 300,
        "domains": {
            "microeconomics": {"target": 80, "focus": "供需理论、市场结构、博弈论"},
            "macroeconomics": {"target": 80, "focus": "GDP、通胀、货币政策、财政政策"},
            "financial": {"target": 80, "focus": "金融市场、投资理论、风险管理"},
            "international_trade": {"target": 60, "focus": "国际贸易、汇率、关税"}
        }
    },
    "law": {  # 法学门类
        "target": 250,
        "domains": {
            "civil_law": {"target": 80, "focus": "民法总则、合同法、侵权责任"},
            "criminal_law": {"target": 60, "focus": "刑法理论、罪名分析、刑罚制度"},
            "commercial_law": {"target": 60, "focus": "公司法、证券法、破产法"},
            "international_law": {"target": 50, "focus": "国际公法、国际私法、国际经济法"}
        }
    },
    "education": {  # 教育学门类
        "target": 200,
        "domains": {
            "pedagogy": {"target": 80, "focus": "教育理论、教学方法、课程设计"},
            "psychology_education": {"target": 60, "focus": "教育心理学、学习理论、发展心理学"},
            "special_education": {"target": 60, "focus": "特殊教育、职业教育、继续教育"}
        }
    },
    "literature": {  # 文学门类
        "target": 400,
        "domains": {
            "literary_techniques": {"target": 150, "focus": "叙事手法、描写技巧、修辞手法、象征隐喻"},
            "writing_skills": {"target": 150, "focus": "人物塑造、情节设计、对话技巧、场景描写"},
            "literary_theory": {"target": 50, "focus": "文学批评、叙事学、文体学"},
            "genre_writing": {"target": 50, "focus": "科幻写作、玄幻写作、悬疑写作、言情写作"}
        }
    },
    "history": {  # 历史学门类
        "target": 300,
        "domains": {
            "ancient_china": {"target": 100, "focus": "先秦、秦汉、魏晋南北朝、隋唐、宋元明清"},
            "world_history": {"target": 100, "focus": "古代文明、中世纪、近代革命、现代史"},
            "military_history": {"target": 60, "focus": "古代战争、近代战争、战略战术"},
            "cultural_history": {"target": 40, "focus": "文化史、社会史、经济史"}
        }
    },
    "science": {  # 理学门类
        "target": 400,
        "domains": {
            "mathematics": {"target": 100, "focus": "高等数学、线性代数、概率论、数论"},
            "physics": {"target": 100, "focus": "力学、电磁学、量子力学、相对论"},
            "chemistry": {"target": 100, "focus": "有机化学、无机化学、物理化学、材料化学"},
            "biology": {"target": 100, "focus": "分子生物学、遗传学、生态学、神经科学"}
        }
    },
    "engineering": {  # 工学门类
        "target": 300,
        "domains": {
            "computer_science": {"target": 100, "focus": "算法、数据结构、人工智能、网络安全"},
            "mechanical": {"target": 80, "focus": "机械设计、制造工艺、机器人技术"},
            "electrical": {"target": 70, "focus": "电路理论、电力系统、电子技术"},
            "civil_engineering": {"target": 50, "focus": "建筑结构、桥梁工程、城市规划"}
        }
    },
    "agriculture": {  # 农学门类
        "target": 150,
        "domains": {
            "plant_science": {"target": 60, "focus": "作物栽培、植物保护、育种技术"},
            "animal_science": {"target": 50, "focus": "畜牧养殖、兽医基础、动物营养"},
            "food_science": {"target": 40, "focus": "食品加工、食品安全、营养学"}
        }
    },
    "medicine": {  # 医学门类
        "target": 200,
        "domains": {
            "clinical_medicine": {"target": 80, "focus": "内科、外科、妇产科、儿科"},
            "traditional_chinese": {"target": 60, "focus": "中医理论、针灸推拿、中药学"},
            "pharmacology": {"target": 40, "focus": "药理学、药物化学、临床药学"},
            "public_health": {"target": 20, "focus": "流行病学、卫生统计、健康教育"}
        }
    },
    "military": {  # 军事学门类
        "target": 200,
        "domains": {
            "military_strategy": {"target": 80, "focus": "孙子兵法、战争论、现代战略"},
            "military_tactics": {"target": 60, "focus": "战术原则、兵种协同、特种作战"},
            "weapon_systems": {"target": 40, "focus": "冷兵器、火器、现代武器"},
            "military_history": {"target": 20, "focus": "著名战役、军事人物、军事改革"}
        }
    },
    "management": {  # 管理学门类
        "target": 200,
        "domains": {
            "business_management": {"target": 80, "focus": "企业管理、人力资源管理、市场营销"},
            "public_administration": {"target": 60, "focus": "公共管理、公共政策、行政管理"},
            "project_management": {"target": 60, "focus": "项目管理、运营管理、物流管理"}
        }
    },
    "arts": {  # 艺术学门类
        "target": 200,
        "domains": {
            "music": {"target": 60, "focus": "音乐理论、乐器知识、音乐史"},
            "fine_arts": {"target": 60, "focus": "绘画技法、艺术流派、美术史"},
            "drama": {"target": 40, "focus": "戏剧理论、表演艺术、戏剧史"},
            "film": {"target": 40, "focus": "电影理论、导演技法、影视制作"}
        }
    },
    
    # ========== 小说创作专属类别 ==========
    "wuxia": {  # 武侠
        "target": 400,
        "domains": {
            "martial_arts": {"target": 150, "focus": "内功心法、外功招式、轻功身法、点穴手法"},
            "jianghu": {"target": 100, "focus": "江湖规矩、武林门派、帮会组织、恩怨情仇"},
            "sect_system": {"target": 80, "focus": "门派体系、师徒传承、武学秘籍"},
            "weapon_treasure": {"target": 70, "focus": "神兵利器、奇门兵器、灵丹妙药"}
        }
    },
    "xianxia": {  # 仙侠
        "target": 400,
        "domains": {
            "cultivation": {"target": 150, "focus": "修仙境界、功法体系、渡劫飞升"},
            "immortal_world": {"target": 100, "focus": "仙界设定、仙官体系、仙家法宝"},
            "demon_way": {"target": 80, "focus": "魔修体系、妖兽设定、邪派功法"},
            "divine_beast": {"target": 70, "focus": "神兽、灵兽、坐骑、契约"}
        }
    },
    "scifi": {  # 科幻（扩展）
        "target": 500,
        "domains": {
            "physics": {"target": 100, "focus": "相对论、量子力学、高能物理"},
            "space": {"target": 100, "focus": "星际航行、外星文明、宇宙探索"},
            "technology": {"target": 100, "focus": "人工智能、纳米技术、生物工程"},
            "biology": {"target": 100, "focus": "基因工程、进化论、外星生物"},
            "time_travel": {"target": 50, "focus": "时间悖论、平行宇宙、因果律"},
            "cyberpunk": {"target": 50, "focus": "赛博空间、黑客技术、虚拟现实"}
        }
    },
    "xuanhuan": {  # 玄幻（扩展）
        "target": 400,
        "domains": {
            "mythology": {"target": 100, "focus": "中西神话、神话人物、神话故事"},
            "religion": {"target": 100, "focus": "佛道体系、宗教设定、神灵系统"},
            "magic_system": {"target": 100, "focus": "魔法体系、魔法元素、魔法阵"},
            "creature": {"target": 60, "focus": "精灵、矮人、龙族、魔兽"},
            "artifact": {"target": 40, "focus": "神器设定、魔法物品、遗迹宝藏"}
        }
    },
    "urban": {  # 都市
        "target": 300,
        "domains": {
            "modern_life": {"target": 100, "focus": "职场、社交、家庭、教育"},
            "business": {"target": 80, "focus": "商战、创业、金融、投资"},
            "entertainment": {"target": 60, "focus": "娱乐圈、网红、综艺、影视"},
            "supernatural": {"target": 60, "focus": "都市异能、灵异事件、都市传说"}
        }
    },
    "general": {  # 通用（扩展）
        "target": 500,
        "domains": {
            "writing_techniques": {"target": 150, "focus": "叙事手法、描写技巧、对话艺术、节奏控制"},
            "character_creation": {"target": 100, "focus": "人物塑造、人物弧光、群像刻画"},
            "plot_design": {"target": 100, "focus": "情节结构、冲突设计、伏笔悬念"},
            "worldbuilding": {"target": 80, "focus": "世界观构建、设定一致性、规则设计"},
            "emotion_writing": {"target": 70, "focus": "情感描写、心理刻画、氛围营造"}
        }
    }
}

def generate_knowledge_point(category: str, domain: str, focus: str) -> dict:
    """生成单条高质量知识点"""
    
    prompt = f"""你是一位专业的小说写作知识库编辑。请为【{category}】类别下的【{domain}】领域生成一条高质量知识点。

**重点方向**: {focus}

**严格要求**（必须达到以下标准）:

1. **title**: 核心概念名称（不超过15字）

2. **core_concept**: 核心概念（1句话概括来源、定位、象征意义，50-80字）

3. **keywords**: 10-15个关键词，**必须明确宗教/文化/科学归属**（如"基督教神话"、"地狱七君主"、"量子力学"、"相对论"等）

4. **content**: 详细内容（**至少500字**），**必须包含以下结构**：
   - **神学/历史/科学起源**：具体出处、原始含义、历史演变
   - **地位与象征**：在体系中的地位、象征意义、代表什么
   - **能力体系/核心原理**：具体能力描述/原理说明、力量来源/理论基础、使用方式/应用场景
   - **与其他概念的关联**：与其他相关概念的对应关系、对比分析
   - **文学/文化演变**：在不同作品/文化中的形象变化

5. **classic_cases**: **至少3个详细案例**（总计至少300字），**必须包含**：
   - 作品名称、作者/导演、年份
   - 具体情节描述（不是概括，要详细）
   - 在该作品中如何应用此概念
   - 原文引用（如果有，或关键对话）
   - 分析：为什么这样用效果好

6. **writing_applications**: 写作应用建议（**至少300字**），**必须包含3大板块**：
   - **角色塑造建议**：如何塑造此类角色，具体描写技巧（含示例对话或描写片段）
   - **世界观构建应用**：如何构建世界观，具体设定方法
   - **情节设计建议**：如何在情节中应用，具体情节走向

7. **common_mistakes**: **至少5个常见误区**（数组格式，每个对象包含mistake和explanation字段，每个至少50字），**必须包含**：
   - 误区名称
   - 问题分析：为什么这是误区
   - 改进建议：应该如何避免

8. **references**: **至少5个真实文献**（数组格式，每个对象包含title、author、year、description字段），**必须包含**：
   - 文献标题
   - 作者
   - 年份
   - 内容说明（至少30字，说明这个文献哪里有价值）

**质量标准**: 参考下方路西法示例，必须达到同等质量——内容详实、具体、可操作，不要模板化废话。

**路西法示例（完整版，供参考）**:
{LUCIFER_EXAMPLE}

**输出格式**: 纯JSON，不要markdown代码块包裹。

现在请生成知识点："""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是专业的小说写作知识库编辑，擅长生成高质量、内容详实、具体可操作的知识点。你必须严格按照要求生成，确保每个字段都达到字数要求和质量标准。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=3000  # 提高token上限
        )
        
        content = response.choices[0].message.content.strip()
        
        # 清理可能的markdown包裹
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        
        kp = json.loads(content)
        
        # 添加元数据
        kp["category"] = category
        kp["domain"] = domain
        kp["knowledge_id"] = f"{category}-{domain}-{hashlib.md5(kp['title'].encode()).hexdigest()[:16]}"
        kp["difficulty"] = "intermediate"
        kp["created_at"] = datetime.now().isoformat()
        kp["updated_at"] = datetime.now().isoformat()
        
        # 质量检查（更严格）
        if len(kp.get("content", "")) < 400:  # 提高到400字
            log(f"  [WARN] content字数不足: {len(kp.get('content', ''))}字")
            return None
        if len(kp.get("classic_cases", "")) < 200:  # 提高到200字
            log(f"  [WARN] classic_cases字数不足: {len(kp.get('classic_cases', ''))}字")
            return None
        if len(kp.get("writing_applications", "")) < 200:  # 提高到200字
            log(f"  [WARN] writing_applications字数不足: {len(kp.get('writing_applications', ''))}字")
            return None
        if len(kp.get("keywords", [])) < 8:  # 至少8个关键词
            log(f"  [WARN] keywords数量不足: {len(kp.get('keywords', []))}个")
            return None
        if len(kp.get("common_mistakes", [])) < 4:  # 至少4个误区
            log(f"  [WARN] common_mistakes数量不足: {len(kp.get('common_mistakes', []))}个")
            return None
        if len(kp.get("references", [])) < 4:  # 至少4个文献
            log(f"  [WARN] references数量不足: {len(kp.get('references', []))}个")
            return None
        
        return kp
        
    except Exception as e:
        log(f"  [ERROR] 生成失败: {e}")
        return None

def log(message: str):
    """写入日志"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_line = f"{timestamp} - {message}"
    print(log_line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_line + "\n")

def save_knowledge_points(category: str, domain: str, points: list):
    """保存知识点到JSON文件"""
    dir_path = KNOWLEDGE_BASE_PATH / category
    dir_path.mkdir(parents=True, exist_ok=True)
    
    file_path = dir_path / f"{domain}.json"
    
    # 读取现有数据
    existing = {"category": category, "domain": domain, "knowledge_points": []}
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except:
            pass
    
    # 合并新数据
    existing["knowledge_points"].extend(points)
    
    # 保存
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    
    return len(existing["knowledge_points"])

def main():
    log("=" * 80)
    log(f"高质量知识库生成器V4启动 - {datetime.now().isoformat()}")
    log("=" * 80)
    
    total_generated = 0
    total_target = 5000
    
    for category, cat_data in KNOWLEDGE_STRUCTURE.items():
        log("")
        log("=" * 80)
        log(f"开始生成 [{category}] 类别 (目标: {cat_data['target']}条)")
        log("=" * 80)
        
        cat_generated = 0
        
        for domain, domain_data in cat_data["domains"].items():
            target = domain_data["target"]
            focus = domain_data["focus"]
            
            log(f"\n[{category}/{domain}] 目标: {target}条, 重点: {focus}")
            
            batch = []
            generated = 0
            attempts = 0
            max_attempts = target * 3  # 最多尝试3倍次数（因为质量要求更高）
            
            while generated < target and attempts < max_attempts:
                attempts += 1
                
                kp = generate_knowledge_point(category, domain, focus)
                
                if kp:
                    batch.append(kp)
                    generated += 1
                    
                    if len(batch) >= 10:  # 每10条保存一次（减少IO）
                        total = save_knowledge_points(category, domain, batch)
                        log(f"  [SAVE] 保存 {len(batch)} 条，文件总计 {total} 条")
                        batch = []
                
                if generated % 5 == 0:
                    log(f"  [{generated}/{target}] 已生成 {generated} 条")
            
            # 保存剩余
            if batch:
                total = save_knowledge_points(category, domain, batch)
                log(f"  [SAVE] 最终保存 {len(batch)} 条，文件总计 {total} 条")
            
            cat_generated += generated
            log(f"  [DONE] {category}/{domain} 完成: {generated}/{target}")
        
        total_generated += cat_generated
        log(f"\n[CATEGORY DONE] {category} 完成: {cat_generated} 条")
        log(f"[TOTAL PROGRESS] 总计: {total_generated}/{total_target} ({total_generated*100//total_target}%)")
    
    log("")
    log("=" * 80)
    log(f"生成完成 - 总计: {total_generated} 条")
    log("=" * 80)

if __name__ == "__main__":
    main()
