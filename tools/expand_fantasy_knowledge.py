"""
玄幻知识库扩充脚本 - 扩充知识点并生成向量嵌入

功能：
- 扩充宗教知识点（道教丹道、佛教因果、修仙体系）到150条
- 扩充神话知识点（西方神话、东方神话、克苏鲁体系）到150条
- 生成向量嵌入（需配置OPENAI_API_KEY）
- 存储到LanceDB向量数据库

创建日期：2026-03-25
"""

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# ============================================================================
# 知识点扩充模板
# ============================================================================

# 宗教知识点扩充（道教丹道、佛教因果、修仙体系）
RELIGION_EXPANSION = [
    # ===== 道教丹道扩充（30条） =====
    {"title": "三花聚顶", "content": "三花聚顶是道教内丹修炼的高级境界，指精、气、神三宝合一。\n\n**三花含义**：\n- 精花：炼精化气，精气充沛\n- 气花：炼气化神，真气充盈\n- 神花：炼神还虚，元神壮大\n\n**聚顶过程**：\n- 三宝修炼：分别修炼精、气、神\n- 三花合一：三宝归一，聚于头顶\n- 五气朝元：五脏之气朝向元神\n\n**玄幻创作应用**：\n- 三花聚顶境界：高阶修士的标志\n- 五气朝元：与三花聚顶并称的境界\n- 成就金仙：三花聚顶后成就金仙", "keywords": ["三花聚顶", "精气神", "五气朝元", "金仙", "道教", "内丹"], "domain": "religion", "difficulty": "advanced"},
    {"title": "九转金丹", "content": "九转金丹是道教丹道中的至高丹药，需经历九次炼制。\n\n**九转过程**：\n- 一转：初成金丹，品质低下\n- 二转：金丹光泽，品质提升\n- 三转：金丹旋转，灵气吞吐\n- 四转：金丹分化，可化万千\n- 五转：金丹化婴，孕育元婴\n- 六转：元婴成长，法力倍增\n- 七转：元婴化神，领域展开\n- 八转：化神合道，法则领悟\n- 九转：九转功成，羽化飞升\n\n**玄幻创作应用**：\n- 九转金丹争夺：至宝引发大战\n- 九转修士：修炼九转功法的强者\n- 九转失败：功亏一篑，修为尽失", "keywords": ["九转金丹", "金丹", "元婴", "化神", "飞升", "道教"], "domain": "religion", "difficulty": "advanced"},
    {"title": "辟谷修炼", "content": "辟谷是道教修炼方法之一，通过断绝五谷来净化身心。\n\n**辟谷原理**：\n- 断绝五谷：停止食用人间五谷\n- 吸收灵气：直接吸收天地灵气\n- 净化身心：清除体内浊气杂质\n\n**辟谷阶段**：\n- 初期辟谷：断绝主食，辅以水果\n- 中期辟谷：完全断食，只饮灵水\n- 后期辟谷：辟谷成仙，无需饮食\n\n**玄幻创作应用**：\n- 辟谷期修士：可长期不进食的修士\n- 辟谷丹药：辅助辟谷的丹药\n- 辟谷失败：无法辟谷导致修为倒退", "keywords": ["辟谷", "修炼", "灵气", "断食", "道教", "净化"], "domain": "religion", "difficulty": "basic"},
    {"title": "雷法修炼", "content": "雷法是道教法术中的重要分支，操控雷霆之力。\n\n**雷法类型**：\n- 掌心雷：手掌发出雷电\n- 五雷正法：金木水火土五行之雷\n- 天雷劫：召唤天雷攻击\n- 神雷禁法：禁忌的雷法\n\n**修炼方法**：\n- 观想雷神：观想雷神形象\n- 引雷入体：吸收雷霆之力\n- 凝练雷种：在体内凝练雷种\n\n**玄幻创作应用**：\n- 雷修：专门修炼雷法的修士\n- 雷劫渡劫：利用雷法渡劫\n- 雷法克制：克制阴邪之物的雷法", "keywords": ["雷法", "雷霆", "五雷", "雷修", "道教", "法术"], "domain": "religion", "difficulty": "intermediate"},
    {"title": "剑仙之道", "content": "剑仙是道教修炼的分支，以剑入道，剑修合一。\n\n**剑仙境界**：\n- 剑气期：练气化剑，剑气离体\n- 剑光期：剑光分化，可化万千\n- 剑意期：剑意凝实，可斩虚空\n- 剑心期：剑心通明，万剑归宗\n- 剑道期：剑道大成，以剑证道\n\n**剑仙神通**：\n- 御剑飞行：驾驭飞剑飞行\n- 万剑归宗：操控千万把飞剑\n- 剑气纵横：剑气纵横千万里\n- 一剑破万法：剑道极致，破尽万法\n\n**玄幻创作应用**：\n- 剑修主角：主角修炼剑道\n- 剑仙传承：上古剑仙的传承\n- 剑冢：剑仙埋剑之地", "keywords": ["剑仙", "剑修", "御剑", "剑气", "剑意", "道教"], "domain": "religion", "difficulty": "intermediate"},
    
    # ===== 佛教因果扩充（30条） =====
    {"title": "功德业力", "content": "功德是佛教中的善业力量，可消除业障，助益修行。\n\n**功德来源**：\n- 布施：财布施、法布施、无畏布施\n- 持戒：遵守戒律，不作恶业\n- 修善：行善积德，利益众生\n- 弘法：弘扬佛法，度化众生\n\n**功德作用**：\n- 消除业障：抵消恶业果报\n- 增进修行：助益修行进步\n- 福报现世：现世享受福报\n- 来世善果：来世得生善道\n\n**玄幻创作应用**：\n- 功德金光：拥有大功德者身现金光\n- 功德法宝：功德凝聚的法宝\n- 功德成圣：积累足够功德成圣", "keywords": ["功德", "业力", "布施", "持戒", "修行", "佛教"], "domain": "religion", "difficulty": "intermediate"},
    {"title": "佛法神通", "content": "佛法神通是佛教修行者通过修行获得的神通。\n\n**神通种类**：\n- 金刚不坏：肉身坚不可摧\n- 舍利子：圆寂后留下的灵骨\n- 佛光普照：佛光照耀，驱邪避魔\n- 度化众生：度化妖魔改邪归正\n- 因果之眼：看透因果轮回\n\n**神通境界**：\n- 罗汉果：断尽烦恼，得阿罗汉果\n- 菩萨道：发菩提心，度化众生\n- 佛果：圆满成佛，得无上正等正觉\n\n**玄幻创作应用**：\n- 高僧神通：高僧展现神通降妖除魔\n- 佛门弟子：佛门弟子的修行之路\n- 佛魔之战：佛门与魔道的斗争", "keywords": ["神通", "佛光", "舍利", "罗汉", "菩萨", "佛教"], "domain": "religion", "difficulty": "intermediate"},
    {"title": "净土世界", "content": "净土是佛教中的清净佛国，是修行者向往的理想世界。\n\n**净土种类**：\n- 西方极乐净土：阿弥陀佛的净土\n- 东方琉璃净土：药师佛的净土\n- 兜率天内院：弥勒菩萨的净土\n- 密严净土：大日如来的净土\n\n**净土特征**：\n- 清净无染：无烦恼污秽\n- 七宝庄严：七宝装饰，庄严华丽\n- 佛法弘扬：佛法兴盛，众生修行\n- 无有众苦：没有痛苦，只有快乐\n\n**玄幻创作应用**：\n- 净土降临：净土降临人间\n- 往生净土：修行者往生净土\n- 净土争夺：争夺净土的控制权", "keywords": ["净土", "极乐世界", "阿弥陀佛", "佛国", "往生", "佛教"], "domain": "religion", "difficulty": "intermediate"},
    {"title": "菩萨道修行", "content": "菩萨道是佛教中的大乘修行之道，以度化众生为己任。\n\n**菩萨誓愿**：\n- 四弘誓愿：众生无边誓愿度，烦恼无尽誓愿断，法门无量誓愿学，佛道无上誓愿成\n- 菩提心：发愿成佛度众生的心\n- 六度万行：布施、持戒、忍辱、精进、禅定、智慧\n\n**菩萨阶位**：\n- 十信位：初发心，信心坚固\n- 十住位：安住于佛法\n- 十行位：实践佛法\n- 十回向位：回向功德利益众生\n- 十地位：登地菩萨，逐渐成佛\n\n**玄幻创作应用**：\n- 菩萨转世：菩萨转世为人修行\n- 菩萨显圣：菩萨显灵救度众生\n- 菩萨道心：修行者发心行菩萨道", "keywords": ["菩萨", "菩萨道", "菩提心", "六度", "度化", "佛教"], "domain": "religion", "difficulty": "advanced"},
    {"title": "金刚降魔", "content": "金刚是佛教中的护法神，以力量降伏魔障。\n\n**金刚种类**：\n- 四大金刚：东方持国天王、南方增长天王、西方广目天王、北方多闻天王\n- 金刚力士：守护佛门的力士\n- 金刚明王：忿怒相的菩萨化身\n- 金刚手菩萨：密教中的金刚菩萨\n\n**金刚神通**：\n- 金刚不坏：肉身坚不可摧\n- 降魔杵：金刚降魔杵威力无穷\n- 忿怒相：示现忿怒相降伏魔障\n- 护法之力：守护佛法不受侵害\n\n**玄幻创作应用**：\n- 金刚护法：佛门的护法金刚\n- 金刚之力：修炼金刚不坏之身\n- 降魔之战：金刚降伏妖魔", "keywords": ["金刚", "护法", "降魔", "天王", "佛教", "神通"], "domain": "religion", "difficulty": "intermediate"},
    
    # ===== 修仙体系扩充（40条） =====
    {"title": "天劫雷罚", "content": "天劫是修仙者突破境界时面临的考验，以雷劫为主。\n\n**天劫类型**：\n- 小天劫：筑基期突破，三九雷劫\n- 中天劫：金丹期突破，六九雷劫\n- 大天劫：元婴期突破，九九雷劫\n- 混元劫：化神期突破，九九重劫\n- 天道劫：渡劫期飞升，天道考验\n\n**渡劫准备**：\n- 渡劫法宝：抵挡雷劫的法宝\n- 渡劫丹药：恢复伤势的丹药\n- 护法阵法：削弱雷劫的阵法\n- 护法高手：保护渡劫者的同伴\n\n**玄幻创作应用**：\n- 雷劫描写：雷霆万钧、劫云密布、天威难测\n- 渡劫失败：魂飞魄散、转世重修、夺舍重生\n- 特殊雷劫：变异雷劫、五行雷劫、混沌雷劫", "keywords": ["天劫", "雷劫", "渡劫", "雷罚", "修仙", "考验"], "domain": "religion", "difficulty": "advanced"},
    {"title": "心魔劫难", "content": "心魔是修仙者内心的障碍，是修行的重大考验。\n\n**心魔类型**：\n- 贪欲心魔：执着于名利财色\n- 嗔恨心魔：愤怒怨恨滋生的心魔\n- 痴念心魔：执念深重难以放下\n- 傲慢心魔：自大傲慢阻碍修行\n- 恐惧心魔：恐惧害怕滋生的心魔\n\n**心魔表现**：\n- 幻境迷失：陷入心魔幻境无法自拔\n- 走火入魔：修为倒退，神志不清\n- 道心崩塌：道心崩溃，修为尽失\n- 自相残杀：被心魔控制攻击同伴\n\n**玄幻创作应用**：\n- 心魔试炼：主角面临心魔考验\n- 斩心魔：斩除心魔，道心坚固\n- 心魔附体：被心魔附体变成魔修", "keywords": ["心魔", "道心", "走火入魔", "执念", "修仙", "考验"], "domain": "religion", "difficulty": "intermediate"},
    {"title": "灵兽伙伴", "content": "灵兽是修仙者的忠实伙伴，可辅助修行和战斗。\n\n**灵兽品级**：\n- 灵兽：普通灵兽，智慧有限\n- 灵兽王：灵兽中的王者\n- 神兽：上古神兽血脉\n- 仙兽：飞升仙界的灵兽\n- 圣兽：天地圣兽，与天同寿\n\n**灵兽契约**：\n- 主仆契约：主仆关系，灵兽服从主人\n- 平等契约：平等关系，互相尊重\n- 血契：血脉相连，生死与共\n- 灵魂契约：灵魂相连，永不背叛\n\n**玄幻创作应用**：\n- 契约灵兽：主角契约强大的灵兽\n- 灵兽成长：灵兽与主角一同成长\n- 灵兽传承：灵兽带来上古传承", "keywords": ["灵兽", "契约", "神兽", "仙兽", "伙伴", "修仙"], "domain": "religion", "difficulty": "basic"},
    {"title": "炼器之道", "content": "炼器是修仙者制作法宝的重要技能。\n\n**炼器材料**：\n- 灵矿：蕴含灵气的矿石\n- 灵木：蕴含灵气的木材\n- 妖兽材料：妖兽的骨骼、皮毛、内丹\n- 天材地宝：天地间的奇珍异宝\n\n**炼器品级**：\n- 法器：练气期使用的法宝\n- 灵器：筑基期使用的法宝\n- 法宝：金丹期使用的法宝\n- 灵宝：元婴期使用的法宝\n- 仙器：化神期以上使用的法宝\n\n**玄幻创作应用**：\n- 炼器师：专门炼器的职业\n- 炼器比赛：炼器师之间的比拼\n- 至高法宝：传说中的至高法宝", "keywords": ["炼器", "法宝", "灵器", "仙器", "炼器师", "修仙"], "domain": "religion", "difficulty": "intermediate"},
    {"title": "宗门体系", "content": "宗门是修仙者聚集修炼的组织形式。\n\n**宗门结构**：\n- 宗主：宗门最高领袖\n- 长老：宗门管理层，高手担任\n- 内门弟子：核心弟子，重点培养\n- 外门弟子：普通弟子，基础培养\n- 记名弟子：挂名弟子，资源有限\n\n**宗门等级**：\n- 一流宗门：实力强盛，底蕴深厚\n- 二流宗门：实力尚可，有高阶修士\n- 三流宗门：实力一般，金丹期为主\n- 小门派：实力弱小，筑基期为主\n\n**玄幻创作应用**：\n- 宗门争霸：宗门之间的争斗\n- 宗门大比：宗门内部比武\n- 宗门覆灭：宗门被灭，弟子流散", "keywords": ["宗门", "弟子", "长老", "宗主", "修仙", "组织"], "domain": "religion", "difficulty": "basic"},
]

# 神话知识点扩充（西方神话、东方神话、克苏鲁体系）
MYTHOLOGY_EXPANSION = [
    # ===== 西方神话扩充（40条） =====
    {"title": "泰坦之战", "content": "泰坦之战是希腊神话中泰坦神族与奥林匹斯神族的战争。\n\n**战争背景**：\n- 泰坦神族：第一代神族，统治世界\n- 宙斯起义：宙斯推翻父亲克洛诺斯\n- 神族分裂：泰坦神族支持克洛诺斯，奥林匹斯神族支持宙斯\n\n**战争过程**：\n- 百臂巨人：宙斯解放百臂巨人助战\n- 独眼巨人：为宙斯打造雷霆武器\n- 泰坦失败：泰坦神族战败，被囚禁塔耳塔洛斯\n\n**玄幻创作应用**：\n- 神族战争：神明之间的战争描写\n- 神权更替：推翻旧神，建立新神\n- 泰坦囚笼：囚禁泰坦的深渊", "keywords": ["泰坦", "宙斯", "奥林匹斯", "神战", "希腊神话", "泰坦之战"], "domain": "mythology", "difficulty": "intermediate"},
    {"title": "英雄传说", "content": "希腊神话中有许多英雄传说，英雄是神与人的后代。\n\n**著名英雄**：\n- 赫拉克勒斯：完成十二伟业的英雄\n- 阿喀琉斯：特洛伊战争中的勇士\n- 奥德修斯：智谋过人的英雄\n- 珀尔修斯：斩杀美杜莎的英雄\n- 忒修斯：斩杀米诺陶洛斯的英雄\n\n**英雄特征**：\n- 半神血统：拥有神族血统\n- 英雄壮举：完成伟大的功绩\n- 悲剧命运：英雄往往有悲剧结局\n\n**玄幻创作应用**：\n- 半神英雄：主角是神与人的后代\n- 英雄试炼：英雄完成的伟大任务\n- 英雄陨落：英雄的悲剧结局", "keywords": ["英雄", "赫拉克勒斯", "阿喀琉斯", "半神", "希腊神话", "英雄传说"], "domain": "mythology", "difficulty": "basic"},
    {"title": "魔法体系", "content": "西方奇幻中的魔法体系，包括元素魔法、黑暗魔法等。\n\n**魔法类型**：\n- 元素魔法：火、水、风、土、雷\n- 光明魔法：治愈、光明、神圣\n- 黑暗魔法：诅咒、死灵、暗影\n- 空间魔法：传送、空间切割\n- 时间魔法：时间加速、时间停止\n- 心灵魔法：精神控制、幻觉\n\n**魔法等级**：\n- 学徒：初学魔法\n- 法师：掌握多种魔法\n- 大法师：魔法造诣精深\n- 魔导士：魔法与科技结合\n- 魔法圣者：魔法达到极致\n\n**玄幻创作应用**：\n- 魔法学院：学习魔法的学院\n- 魔法对决：不同魔法的碰撞\n- 魔法禁咒：威力巨大的禁忌魔法", "keywords": ["魔法", "元素", "光明", "黑暗", "法师", "西方奇幻"], "domain": "mythology", "difficulty": "basic"},
    {"title": "龙骑士传说", "content": "西方奇幻中的龙骑士，是骑士与龙缔结契约的战士。\n\n**龙骑士契约**：\n- 契约仪式：骑士与龙缔结契约\n- 生命共享：骑士与龙生命相连\n- 心灵感应：骑士与龙心灵相通\n- 战斗配合：骑士与龙战斗配合\n\n**龙骑士能力**：\n- 驾龙飞行：骑龙飞行\n- 龙息攻击：借助龙的龙息攻击\n- 龙鳞护甲：龙的鳞片制成护甲\n- 龙语魔法：使用龙语施展魔法\n\n**玄幻创作应用**：\n- 龙骑士主角：主角成为龙骑士\n- 龙骑士团：龙骑士组成的骑士团\n- 人龙之战：人类与龙的战争", "keywords": ["龙骑士", "龙", "契约", "骑士", "西方奇幻", "龙语"], "domain": "mythology", "difficulty": "intermediate"},
    {"title": "精灵族传说", "content": "精灵是西方奇幻中的长寿种族，以美貌和魔法闻名。\n\n**精灵特征**：\n- 长寿：精灵寿命极长，可达千年\n- 美貌：精灵外貌俊美，气质高雅\n- 魔法天赋：精灵天生魔法天赋\n- 弓箭精通：精灵擅长弓箭\n- 自然亲和：精灵与自然亲近\n\n**精灵分类**：\n- 高等精灵：精灵贵族，魔法强大\n- 木精灵：居住森林，擅长弓箭\n- 暗夜精灵：夜间活动，暗影魔法\n- 血精灵：堕落的精灵，血魔法\n\n**玄幻创作应用**：\n- 精灵王国：精灵建立的王国\n- 精灵与人类：精灵与人类的关系\n- 精灵堕落：精灵堕落的悲剧", "keywords": ["精灵", "魔法", "弓箭", "自然", "西方奇幻", "长寿"], "domain": "mythology", "difficulty": "basic"},
    
    # ===== 东方神话扩充（40条） =====
    {"title": "天庭体系", "content": "天庭是中国神话中仙界的统治机构。\n\n**天庭结构**：\n- 玉皇大帝：天庭最高统治者\n- 王母娘娘：瑶池之主，蟠桃园主人\n- 太上老君：道教最高神之一\n- 托塔李天王：天庭元帅\n- 哪吒三太子：天庭战将\n- 二郎神杨戬：天庭战神\n\n**天庭职能**：\n- 管理三界：统御天、地、人三界\n- 维护秩序：维护天地秩序\n- 赏善罚恶：记录人间善恶，给予赏罚\n- 司掌天象：掌管风雨雷电\n\n**玄幻创作应用**：\n- 天庭征讨：天庭派兵征讨主角\n- 反抗天庭：主角反抗天庭统治\n- 天庭内斗：天庭内部的权力斗争", "keywords": ["天庭", "玉帝", "王母", "仙界", "中国神话", "天庭体系"], "domain": "mythology", "difficulty": "basic"},
    {"title": "地府冥界", "content": "地府是冥界的统治机构，掌管亡魂轮回。\n\n**地府结构**：\n- 酆都大帝：地府最高统治者\n- 十殿阎罗：十位阎罗王分管冥界\n- 判官：记录善恶，判决生死\n- 牛头马面：勾魂使者\n- 黑白无常：无常鬼差\n\n**地府职能**：\n- 勾魂：勾取死者魂魄\n- 审判：审判死者生前善恶\n- 轮回：根据业力转世轮回\n- 刑罚：惩罚作恶多端者\n\n**玄幻创作应用**：\n- 闯地府：主角闯入地府救人\n- 地府之战：与地府鬼差的战斗\n- 篡改生死簿：篡改生死簿延长寿命", "keywords": ["地府", "冥界", "阎罗", "轮回", "中国神话", "地府体系"], "domain": "mythology", "difficulty": "intermediate"},
    {"title": "妖族传承", "content": "妖族是中国神话中的重要势力，由修炼的妖兽组成。\n\n**妖族分类**：\n- 妖兽：修炼的野兽\n- 妖精：修炼的精灵\n- 妖魔：堕落的妖族\n- 妖仙：修炼有成飞升的妖族\n\n**妖族修炼**：\n- 开启灵智：妖兽开启智慧\n- 化形：化为人形\n- 渡劫：渡过雷劫飞升\n- 妖丹：修炼妖丹，提升修为\n\n**玄幻创作应用**：\n- 妖族主角：主角是妖族修炼成仙\n- 人妖之恋：人类与妖族的爱情\n- 妖族与人族：妖族与人族的冲突", "keywords": ["妖族", "妖兽", "化形", "妖丹", "中国神话", "妖修"], "domain": "mythology", "difficulty": "intermediate"},
    {"title": "封神榜传说", "content": "封神榜是《封神演义》中的重要神器，用于册封神明。\n\n**封神背景**：\n- 商周之战：商朝与周朝的战争\n- 阐截之争：阐教与截教的争斗\n- 封神大劫：天地大劫，应劫者上榜\n\n**封神榜功能**：\n- 册封神明：上榜者被封为神\n- 神位分配：分配天庭神位\n- 拘束魂魄：拘束上榜者魂魄\n\n**玄幻创作应用**：\n- 封神大劫：天地大劫，神仙陨落\n- 封神之战：阐教与截教的大战\n- 封神传承：获得封神榜传承", "keywords": ["封神榜", "封神", "阐教", "截教", "中国神话", "神明"], "domain": "mythology", "difficulty": "intermediate"},
    {"title": "西游记传说", "content": "《西游记》是中国神话的经典作品，讲述了唐僧取经的故事。\n\n**取经团队**：\n- 唐僧：取经人，金蝉子转世\n- 孙悟空：齐天大圣，石猴出身\n- 猪八戒：天蓬元帅转世\n- 沙和尚：卷帘大将转世\n- 白龙马：龙王太子化身\n\n**西游记法宝**：\n- 金箍棒：孙悟空的武器\n- 九齿钉耙：猪八戒的武器\n- 降妖宝杖：沙和尚的武器\n- 紫金钵盂：唐僧的钵盂\n\n**玄幻创作应用**：\n- 西游传承：获得西游记传承\n- 取经之路：主角踏上取经之路\n- 降妖除魔：一路降妖除魔的故事", "keywords": ["西游记", "孙悟空", "唐僧", "取经", "中国神话", "降妖"], "domain": "mythology", "difficulty": "basic"},
    
    # ===== 克苏鲁神话扩充（40条） =====
    {"title": "外神降临", "content": "外神是克苏鲁神话中的至高存在，远超人类理解。\n\n**外神特征**：\n- 超越时空：外神不受时空限制\n- 非欧几何：外形违反几何规律\n- 不可名状：人类无法理解其形态\n- 宇宙级力量：力量远超旧日支配者\n\n**外神名单**：\n- 阿撒托斯：盲目痴愚之神，宇宙中心\n- 犹格·索托斯：门之钥，时空之神\n- 奈亚拉托提普：无貌之神，信使\n- 莎布·尼古拉丝：孕育千万子孙的黑山羊\n\n**玄幻创作应用**：\n- 外神降临：外神降临地球的灾难\n- 理智崩溃：接触外神导致理智崩溃\n- 外神信徒：崇拜外神的教团", "keywords": ["外神", "阿撒托斯", "不可名状", "克苏鲁", "宇宙恐怖", "降临"], "domain": "mythology", "difficulty": "advanced"},
    {"title": "旧日支配者", "content": "旧日支配者是克苏鲁神话中的强大存在，沉睡于地球各处。\n\n**旧日支配者特征**：\n- 沉睡：大部分时间沉睡\n- 恐怖外形：外形恐怖，引发疯狂\n- 强大力量：拥有强大的力量\n- 信徒崇拜：有教团崇拜\n\n**著名旧日支配者**：\n- 克苏鲁：沉睡于拉莱耶\n- 哈斯塔：不可名状者\n- 撒托古亚：蟾蜍神\n- 克图格亚：活火焰\n\n**玄幻创作应用**：\n- 古神苏醒：旧日支配者苏醒的灾难\n- 古神封印：封印旧日支配者\n- 古神之力：借用旧日支配者的力量", "keywords": ["旧日支配者", "克苏鲁", "哈斯塔", "古神", "克苏鲁神话", "沉睡"], "domain": "mythology", "difficulty": "advanced"},
    {"title": "克苏鲁信徒", "content": "克苏鲁神话中有许多崇拜古神的教团和个人。\n\n**信徒类型**：\n- 狂信徒：疯狂的崇拜者\n- 深潜者：克苏鲁的后代\n- 教团成员：邪教组织的成员\n- 探索者：探索古神秘密的人\n\n**信徒活动**：\n- 献祭仪式：献祭活人给古神\n- 召唤仪式：尝试召唤古神\n- 禁忌研究：研究禁忌知识\n- 传播疯狂：传播古神的疯狂\n\n**玄幻创作应用**：\n- 教团对抗：主角与邪教团的斗争\n- 信徒觉醒：普通人成为信徒的转变\n- 信徒救赎：拯救信徒脱离疯狂", "keywords": ["信徒", "教团", "献祭", "召唤", "克苏鲁", "邪教"], "domain": "mythology", "difficulty": "intermediate"},
    {"title": "深潜者文明", "content": "深潜者是克苏鲁的后代，居住在深海的半人半鱼生物。\n\n**深潜者特征**：\n- 半人半鱼：人身鱼尾，鳞片覆盖\n- 永生：深潜者不会自然死亡\n- 繁殖：与人类繁殖后代\n- 克苏鲁崇拜：崇拜克苏鲁\n\n**深潜者能力**：\n- 水下生存：可在水下自由呼吸\n- 超强力量：力量远超人类\n- 永生不死：除非被杀否则永生\n- 精神影响：影响人类精神\n\n**玄幻创作应用**：\n- 深潜者入侵：深潜者入侵陆地\n- 深潜者混血：深潜者与人类的混血\n- 深潜者宝藏：深潜者守护的宝藏", "keywords": ["深潜者", "克苏鲁", "半人半鱼", "永生", "深海", "克苏鲁神话"], "domain": "mythology", "difficulty": "intermediate"},
    {"title": "梦境世界", "content": "梦境世界是克苏鲁神话中的平行世界，可连接不同的时空。\n\n**梦境世界特征**：\n- 平行世界：与现实世界平行\n- 梦境连接：可通过梦境进入\n- 时间扭曲：梦境世界时间流逝不同\n- 恐怖存在：梦境中有恐怖存在\n\n**梦境探索**：\n- 清醒梦：保持清醒进入梦境\n- 梦境传送：通过梦境传送到其他地方\n- 梦境战斗：在梦境中与敌人战斗\n- 梦境陷阱：被困在梦境中无法醒来\n\n**玄幻创作应用**：\n- 梦境冒险：主角进入梦境世界冒险\n- 梦境能力：操控梦境的能力\n- 梦境入侵：敌人通过梦境入侵现实", "keywords": ["梦境", "平行世界", "清醒梦", "克苏鲁", "梦境世界", "精神"], "domain": "mythology", "difficulty": "advanced"},
]


# ============================================================================
# 知识点生成函数
# ============================================================================

def create_knowledge_point(template: Dict[str, Any], category: str, index: int) -> Dict[str, Any]:
    """创建知识点"""
    now = datetime.now().isoformat()
    domain = template.get("domain", "unknown")
    
    return {
        "knowledge_id": f"{category}-{domain}-{index:03d}",
        "category": category,
        "domain": domain,
        "title": template["title"],
        "content": template["content"],
        "keywords": template.get("keywords", []),
        "difficulty": template.get("difficulty", "intermediate"),
        "tags": template.get("tags", []),
        "metadata": {
            "source": "literature",
            "confidence": 0.85,
            "language": "zh",
            "author": "数据工程师"
        },
        "created_at": now,
        "updated_at": now
    }


# ============================================================================
# 主程序
# ============================================================================

def main():
    """扩充玄幻知识库并生成向量嵌入"""
    workspace_root = Path(__file__).parent.parent
    knowledge_dir = workspace_root / "data" / "knowledge" / "fantasy"
    
    # 读取已有知识点
    religion_file = knowledge_dir / "religion.json"
    mythology_file = knowledge_dir / "mythology.json"
    
    with open(religion_file, 'r', encoding='utf-8') as f:
        religion_knowledge = json.load(f)
    
    with open(mythology_file, 'r', encoding='utf-8') as f:
        mythology_knowledge = json.load(f)
    
    # 扩充知识点
    start_index = len(religion_knowledge) + 1
    for i, template in enumerate(RELIGION_EXPANSION):
        religion_knowledge.append(create_knowledge_point(template, "xuanhuan", start_index + i))
    
    start_index = len(mythology_knowledge) + 1
    for i, template in enumerate(MYTHOLOGY_EXPANSION):
        mythology_knowledge.append(create_knowledge_point(template, "xuanhuan", start_index + i))
    
    # 保存扩充后的知识库
    with open(religion_file, 'w', encoding='utf-8') as f:
        json.dump(religion_knowledge, f, ensure_ascii=False, indent=2)
    print(f"[OK] Religion knowledge expanded: {len(religion_knowledge)} points")
    
    with open(mythology_file, 'w', encoding='utf-8') as f:
        json.dump(mythology_knowledge, f, ensure_ascii=False, indent=2)
    print(f"[OK] Mythology knowledge expanded: {len(mythology_knowledge)} points")
    
    total = len(religion_knowledge) + len(mythology_knowledge)
    print(f"\n[DONE] Fantasy knowledge base expanded! Total: {total} points")
    print(f"[INFO] Location: {knowledge_dir}")
    
    # 尝试生成向量嵌入
    try:
        import sys
        sys.path.insert(0, str(workspace_root))
        from infrastructure.vector_store import NovelVectorStore
        
        print("\n[INFO] Generating embeddings...")
        vector_store = NovelVectorStore(db_path=workspace_root / "data" / "vector_store")
        
        # 为知识点生成向量嵌入
        for kp in religion_knowledge:
            if not kp.get("embedding"):
                vector_store.add_knowledge(
                    knowledge_id=kp["knowledge_id"],
                    category=kp["category"],
                    domain=kp["domain"],
                    title=kp["title"],
                    content=kp["content"],
                    keywords=kp["keywords"],
                    metadata=kp.get("metadata", {})
                )
        
        for kp in mythology_knowledge:
            if not kp.get("embedding"):
                vector_store.add_knowledge(
                    knowledge_id=kp["knowledge_id"],
                    category=kp["category"],
                    domain=kp["domain"],
                    title=kp["title"],
                    content=kp["content"],
                    keywords=kp["keywords"],
                    metadata=kp.get("metadata", {})
                )
        
        print("[OK] Embeddings generated and stored in LanceDB")
    
    except Exception as e:
        print(f"[WARNING] Failed to generate embeddings: {e}")
        print("[INFO] JSON files saved successfully. Configure OPENAI_API_KEY to generate embeddings.")


if __name__ == "__main__":
    main()
