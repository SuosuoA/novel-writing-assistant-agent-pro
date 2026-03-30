#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库全面优化脚本
为所有知识点添加详细内容、案例、误区和参考来源
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# 科幻-物理学知识增强
PHYSICS_ENHANCEMENTS = {
    "scifi-physics-001": {
        "content": """相对论是爱因斯坦创立的时空理论，包括狭义相对论和广义相对论。

**狭义相对论（1905年）**：
- 光速不变原理：光速在真空中恒定为299,792,458 m/s
- 时间膨胀：高速运动物体时间流逝变慢
- 长度收缩：高速运动物体长度缩短
- 质能方程：E=mc²，质量与能量等价

**广义相对论（1915年）**：
- 等效原理：加速度与引力等效
- 时空弯曲：质量弯曲时空
- 引力透镜：光线经过大质量天体弯曲
- 黑洞：时空曲率无限大的奇点

**科幻创作核心应用**：
- 时间膨胀效应：接近光速飞行，飞船内时间变慢，外部世界飞速流逝
- 引力时间 dilation：强引力场中时间变慢（如黑洞附近）
- 虫洞穿越：连接两个时空点的捷径
- 黑洞奇点：时间与空间的终结""",
        "examples": [
            "《星际穿越》：米勒星球1小时=地球7年（黑洞引力时间膨胀）",
            "《三体》：光速飞船导致的时间差异，程心与云天明的时间错位",
            "《星际迷航》：曲速引擎通过扭曲空间实现超光速",
            "《黑洞表面》：进入黑洞后的时空扭曲"
        ],
        "common_mistakes": [
            "错误：时间膨胀是时间变快（实际是变慢）",
            "错误：超光速航行直接实现（相对论禁止，需通过曲速/虫洞绕过）",
            "错误：黑洞只是大引力源（实际是时空奇点，连光都无法逃逸）",
            "错误：引力波可以推动飞船（实际是时空涟漪，无法直接利用）"
        ],
        "references": [
            "《时间简史》- 史蒂芬·霍金",
            "《相对论：狭义与广义理论》- 爱因斯坦",
            "NASA官方网站：黑洞与引力波",
            "《三体》科学顾问访谈"
        ]
    },
    "scifi-physics-002": {
        "content": """量子力学描述微观世界的物理规律，与经典力学截然不同。

**核心原理**：
- 波粒二象性：粒子同时具有波动性和粒子性
- 不确定性原理：无法同时精确测量位置和动量
- 量子纠缠：两个粒子状态关联，无论距离多远
- 量子隧穿：粒子可以穿越看似不可逾越的势垒
- 叠加态：粒子同时处于多种状态，测量时才坍缩

**重要实验**：
- 双缝实验：证明波粒二象性
- 薛定谔的猫：叠加态的思想实验
- 贝尔实验：验证量子纠缠

**科幻创作核心应用**：
- 量子通信：超距瞬时通信（基于纠缠）
- 量子计算：并行处理能力指数级提升
- 量子传送：量子态远程传输""",
        "examples": [
            "《星际迷航》：传送机利用量子态传输实现瞬间移动",
            "《量子破碎》：时间断裂与量子态操控",
            "《信条》：时间逆转（量子逆向运动）",
            "《三体》：智子利用量子纠缠实现实时通信"
        ],
        "common_mistakes": [
            "错误：量子纠缠可以传递信息（实际不能，只能产生关联）",
            "错误：观测改变现实（实际是测量导致波函数坍缩）",
            "错误：量子传送=瞬间移动（实际是复制+销毁，原体被破坏）",
            "错误：量子力学解释意识（这是伪科学说法）"
        ],
        "references": [
            "《量子力学概论》- Griffiths",
            "《上帝掷骰子吗》- 曹天元",
            "费曼物理学讲义第三卷",
            "Nature Physics期刊"
        ]
    },
    "scifi-physics-003": {
        "content": """黑洞是时空曲率无限大的区域，连光都无法逃逸。

**黑洞类型**：
- 恒星黑洞：大质量恒星坍缩形成（3-20太阳质量）
- 超大质量黑洞：星系中心（百万至十亿太阳质量）
- 原初黑洞：宇宙大爆炸形成（理论预测）
- 微型黑洞：量子尺度（理论预测）

**黑洞结构**：
- 事件视界：光无法逃逸的边界
- 奇点：密度无限大、体积无限小的中心
- 吸积盘：围绕黑洞旋转的物质盘
- 相对论喷流：两极喷出的高能粒子流

**黑洞效应**：
- 潮汐力：靠近黑洞时被拉伸（面条化）
- 时间膨胀：视界附近时间几乎静止
- 霍金辐射：黑洞缓慢蒸发

**科幻创作核心应用**：
- 黑洞作为能量源或时间机器
- 黑洞内部的时空结构探索
- 黑洞作为文明的终极武器""",
        "examples": [
            "《星际穿越》：卡冈图雅黑洞的视觉呈现与时间膨胀",
            "《黑洞表面》：穿越黑洞到达另一空间",
            "《三体》：黑域（光速飞船轨迹形成的光速黑洞）",
            "《星际迷航》：黑洞作为时间旅行通道"
        ],
        "common_mistakes": [
            "错误：黑洞是洞（实际是极高密度天体）",
            "错误：进入黑洞必死（理论上旋转黑洞可能存在可穿越通道）",
            "错误：黑洞永恒存在（实际会通过霍金辐射蒸发）",
            "错误：黑洞只吞噬不释放（实际有喷流和辐射）"
        ],
        "references": [
            "《黑洞与时间弯曲》- 基普·索恩",
            "霍金1974年论文《黑洞爆炸？》",
            "EHT合作组织首张黑洞照片",
            "《星际穿越》科学顾问报告"
        ]
    }
}

# 科幻-化学知识增强
CHEMISTRY_ENHANCEMENTS = {
    "scifi-chemistry-001": {
        "content": """元素周期表按原子序数排列所有已知元素，展现元素性质的周期性规律。

**周期表结构**：
- 周期：横行，共7个周期
- 族：纵列，共18个族
- 金属元素：左侧和中部（约80%元素）
- 非金属元素：右侧
- 稀有气体：最右侧第18族

**特殊区域**：
- 稀土元素：镧系和锕系，高科技关键材料
- 超重元素：原子序数>92的人工合成元素
- 岛屿稳定区：理论预测的超重稳定元素

**科幻创作核心应用**：
- 新元素发现：未知元素的神秘特性
- 超重元素：极其稳定或极其不稳定的新材料
- 反物质元素：反氢、反碳等""",
        "examples": [
            "《复仇者联盟》：振金（Vibranium）的特殊属性",
            "《阿凡达》：超导矿石Unobtanium",
            "《超人》：氪石对超人的影响",
            "《变形金刚》：能量块（Energon）"
        ],
        "common_mistakes": [
            "错误：新元素随意命名（需遵循IUPAC命名规则）",
            "错误：元素可以无限稳定存在（超重元素极不稳定）",
            "错误：反物质像普通物质一样存在（瞬间湮灭）"
        ],
        "references": [
            "《化学原理》- Atkins",
            "IUPAC官方网站",
            "《元素的故事》",
            "Nature Chemistry期刊"
        ]
    }
}

# 科幻-生物学知识增强
BIOLOGY_ENHANCEMENTS = {
    "scifi-biology-001": {
        "content": """CRISPR-Cas9是革命性的基因编辑技术，可以精确修改DNA序列。

**技术原理**：
- CRISPR：细菌的免疫系统，用于识别和切割入侵病毒DNA
- Cas9蛋白：分子剪刀，切割特定DNA序列
- gRNA：引导RNA，定位目标基因
- HDR/NHEJ：DNA修复机制，实现基因编辑

**编辑能力**：
- 基因敲除：删除特定基因
- 基因敲入：插入新基因
- 基因修复：修复突变基因
- 基因调控：控制基因表达

**技术限制**：
- 脱靶效应：误编辑非目标基因
- 伦理问题：人类胚胎编辑争议
- 技术门槛：需要专业实验室

**科幻创作核心应用**：
- 基因改造人：增强体能、智力、寿命
- 定制婴儿：父母选择后代特征
- 基因治疗：治愈遗传疾病
- 生物武器：针对性基因病毒""",
        "examples": [
            "《千钧一发》：基因决定社会地位的近未来",
            "《生化危机》：T病毒基因改造",
            "《银翼杀手》：复制人的基因设计",
            "《X战警》：变种人的基因突变"
        ],
        "common_mistakes": [
            "错误：基因编辑随心所欲（实际受复杂调控网络限制）",
            "错误：单一基因决定性状（多基因复杂作用）",
            "错误：基因改造立竿见影（需多代筛选）",
            "错误：编辑无副作用（脱靶风险）"
        ],
        "references": [
            "Jennifer Doudna《破天机》",
            "Nature Biotechnology期刊",
            "《基因传》- 悉达多·穆克吉",
            "WHO人类基因组编辑建议"
        ]
    },
    "scifi-biology-002": {
        "content": """进化论是达尔文创立的生物演化理论，解释物种起源和多样性。

**核心机制**：
- 自然选择：适者生存，不适者淘汰
- 变异：随机基因突变提供选择材料
- 遗传：有利性状传递给后代
- 隔离：地理或生殖隔离导致新物种形成

**现代综合论**：
- 基因突变是变异的来源
- 种群是进化的单位
- 自然选择是主要动力
- 遗传漂变和基因流也影响进化

**进化证据**：
- 化石记录：过渡物种化石
- 同源器官：不同物种相似结构
- 分子证据：DNA序列相似性
- 观察实例：细菌抗药性进化

**科幻创作核心应用**：
- 定向进化：人工加速有利突变
- 进化加速：快速获得新能力
- 外星生物：不同进化路径""",
        "examples": [
            "《普罗米修斯》：人类起源与外星基因工程",
            "《异形》：完美生物的进化设计",
            "《猩球崛起》：猿类加速进化",
            "《进化》：外星生物快速进化"
        ],
        "common_mistakes": [
            "错误：进化有方向（实际随机突变+环境筛选）",
            "错误：进化总是进步（实际是适应环境）",
            "错误：人类进化停止（实际仍在进行）",
            "错误：进化需要百万年（细菌等可快速进化）"
        ],
        "references": [
            "《物种起源》- 达尔文",
            "《自私的基因》- 道金斯",
            "《进化心理学》",
            "Science期刊进化专题"
        ]
    }
}

# 通用-哲学知识增强
PHILOSOPHY_ENHANCEMENTS = {
    "general-philosophy-001": {
        "content": """存在主义是20世纪重要哲学流派，强调个体存在、自由和选择。

**核心观点**：
- 存在先于本质：人先存在，后定义自己
- 绝对自由：人是自由的，必须做出选择
- 责任：自由选择意味着承担责任
- 焦虑：面对自由和死亡的焦虑
- 荒谬：人生本无意义，需自己创造

**代表人物**：
- 萨特：存在主义代表人物
- 加缪：荒谬哲学
- 海德格尔：存在与时间
- 尼采：上帝已死，重估价值

**核心概念**：
- 本真：真实地生活，不逃避责任
- 自欺：逃避自由和选择
- 向死而生：直面死亡赋予生命意义

**小说创作应用**：
- 人物内心冲突：自由与责任的矛盾
- 道德困境：没有标准答案的选择
- 存在危机：寻找生命意义的旅程""",
        "examples": [
            "《局外人》：加缪的荒谬哲学体现",
            "《恶心》：萨特的存在主义小说",
            "《变形记》：卡夫卡的存在焦虑",
            "《等待戈多》：人生的荒谬与等待"
        ],
        "common_mistakes": [
            "误解：存在主义=虚无主义（实际强调创造意义）",
            "误解：存在主义悲观（实际强调自由和责任）",
            "误解：存在先于本质=无约束（实际强调责任）"
        ],
        "references": [
            "《存在与虚无》- 萨特",
            "《西西弗神话》- 加缪",
            "《存在与时间》- 海德格尔",
            "斯坦福哲学百科"
        ]
    }
}

# 通用-逻辑知识增强
LOGIC_ENHANCEMENTS = {
    "general-logic-001": {
        "content": """逻辑谬误是推理中的错误，识别谬误有助于理性思考和论证。

**形式谬误**：
- 肯定后件：如果P则Q，有Q所以P（错误）
- 否定前件：如果P则Q，非P所以非Q（错误）
- 中项不周延：三段论推理错误

**非形式谬误**：
- 人身攻击：攻击对方而非观点
- 稻草人：歪曲对方观点后攻击
- 滑坡谬误：无根据的连锁推断
- 诉诸权威：以权威代替论证
- 循环论证：结论出现在前提中
- 虚假二分：只给出两个选项
- 诉诸无知：无法证伪即为真

**小说创作应用**：
- 人物辩论：反派使用谬误欺骗
- 悬疑推理：识别证词中的逻辑漏洞
- 哲学对话：展现理性与谬误的交锋""",
        "examples": [
            "夏洛克·福尔摩斯：演绎推理与谬误识别",
            "《十二怒汉》：陪审团辩论中的谬误",
            "《名侦探柯南》：推理中的逻辑运用",
            "政治小说：政客的谬误宣传"
        ],
        "common_mistakes": [
            "过度使用：把所有不同意见都归为谬误",
            "误判：正确推理被误认为谬误",
            "以谬制谬：用谬误反驳谬误"
        ],
        "references": [
            "《逻辑学导论》- 柯匹",
            "《思考，快与慢》- 卡尼曼",
            "维基百科逻辑谬误列表",
            "Critical Thinking教材"
        ]
    }
}

def enhance_knowledge_file(file_path: Path, enhancements: Dict[str, Dict[str, Any]]) -> int:
    """增强单个知识库文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        knowledge_points = json.load(f)
    
    updated_count = 0
    for kp in knowledge_points:
        kp_id = kp.get('knowledge_id', '')
        if kp_id in enhancements:
            enhancement = enhancements[kp_id]
            
            # 更新内容
            if 'content' in enhancement:
                kp['content'] = enhancement['content']
            
            # 添加案例
            if 'examples' in enhancement:
                kp['examples'] = enhancement['examples']
            
            # 添加常见误区
            if 'common_mistakes' in enhancement:
                kp['common_mistakes'] = enhancement['common_mistakes']
            
            # 添加参考来源
            if 'references' in enhancement:
                kp['references'] = enhancement['references']
            
            # 更新时间戳
            kp['updated_at'] = datetime.now().isoformat()
            updated_count += 1
    
    # 保存更新后的文件
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(knowledge_points, f, ensure_ascii=False, indent=2)
    
    return updated_count


def main():
    """主函数"""
    base_path = Path(__file__).parent.parent / "data" / "knowledge"
    
    total_updated = 0
    
    # 增强物理学知识
    physics_file = base_path / "scifi" / "physics.json"
    if physics_file.exists():
        count = enhance_knowledge_file(physics_file, PHYSICS_ENHANCEMENTS)
        print(f"物理学知识增强: {count} 条")
        total_updated += count
    
    # 增强化学知识
    chemistry_file = base_path / "scifi" / "chemistry.json"
    if chemistry_file.exists():
        count = enhance_knowledge_file(chemistry_file, CHEMISTRY_ENHANCEMENTS)
        print(f"化学知识增强: {count} 条")
        total_updated += count
    
    # 增强生物学知识
    biology_file = base_path / "scifi" / "biology.json"
    if biology_file.exists():
        count = enhance_knowledge_file(biology_file, BIOLOGY_ENHANCEMENTS)
        print(f"生物学知识增强: {count} 条")
        total_updated += count
    
    # 增强哲学知识
    philosophy_file = base_path / "general" / "philosophy.json"
    if philosophy_file.exists():
        count = enhance_knowledge_file(philosophy_file, PHILOSOPHY_ENHANCEMENTS)
        print(f"哲学知识增强: {count} 条")
        total_updated += count
    
    # 增强逻辑知识
    logic_file = base_path / "general" / "logic.json"
    if logic_file.exists():
        count = enhance_knowledge_file(logic_file, LOGIC_ENHANCEMENTS)
        print(f"逻辑知识增强: {count} 条")
        total_updated += count
    
    print(f"\n总计增强: {total_updated} 条知识点")


if __name__ == "__main__":
    main()
