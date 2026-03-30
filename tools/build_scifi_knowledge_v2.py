"""
科幻知识库构建脚本V2 - 简化版

创建日期：2026-03-25

功能：
- 构建物理学、化学、生物学基础知识点
- 自动生成知识点ID和元数据
- 保存为JSON格式
- 支持后续向量嵌入

目标：≥500条知识点
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


# ============================================================================
# 物理学知识点模板（50条精选）
# ============================================================================

PHYSICS_TEMPLATES = [
    {"title": "时间膨胀效应", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["相对论", "时间", "光速", "时间膨胀"],
     "content": "根据狭义相对论，当物体接近光速运动时，时间流速会变慢。时间膨胀公式：Δt' = Δt / √(1 - v²/c²)。GPS卫星需要校正时间膨胀效应，星际旅行中飞船内时间流逝比地球慢。"},
    
    {"title": "量子纠缠", "domain": "physics", "difficulty": "advanced",
     "keywords": ["量子力学", "纠缠", "非定域性", "贝尔不等式"],
     "content": "量子纠缠是两个粒子即使相隔遥远也能瞬间关联的现象。违反贝尔不等式，证明量子力学的非定域性。科幻应用包括超光速通讯和传送门技术。"},
    
    {"title": "黑洞事件视界", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["黑洞", "事件视界", "引力", "史瓦西半径"],
     "content": "黑洞是时空曲率极大的区域，事件视界是光都无法逃逸的边界。史瓦西半径：Rs = 2GM/c²。科幻应用包括黑洞能量提取和时间旅行。"},
    
    {"title": "虫洞理论", "domain": "physics", "difficulty": "advanced",
     "keywords": ["虫洞", "时空隧道", "超光速", "爱因斯坦-罗森桥"],
     "content": "虫洞是连接时空中两个区域的捷径。需要负质量物质撑开通道。科幻应用包括星际之门和时间隧道。"},
    
    {"title": "暗物质与暗能量", "domain": "physics", "difficulty": "advanced",
     "keywords": ["暗物质", "暗能量", "宇宙", "引力"],
     "content": "暗物质和暗能量构成宇宙的95%。暗物质通过引力效应证明存在，暗能量驱动宇宙加速膨胀。科幻应用包括暗物质探测器和暗能量引擎。"},
    
    {"title": "核聚变反应", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["核聚变", "等离子体", "托卡马克", "能量"],
     "content": "核聚变是轻元素融合释放巨大能量的过程。需要1亿度以上等离子体温度。科幻应用包括聚变引擎和人造太阳。"},
    
    {"title": "反物质与湮灭", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["反物质", "湮灭", "能量释放", "正电子"],
     "content": "物质与反物质相遇发生湮灭，释放E=2mc²的能量。1克反物质湮灭相当于广岛原子弹。科幻应用包括反物质引擎和武器。"},
    
    {"title": "引力波探测", "domain": "physics", "difficulty": "advanced",
     "keywords": ["引力波", "LIGO", "时空涟漪", "黑洞合并"],
     "content": "引力波是时空的涟漪，由大质量天体加速运动产生。通过激光干涉仪探测。科幻应用包括引力波通讯和时空扭曲探测。"},
    
    {"title": "量子隧穿效应", "domain": "physics", "difficulty": "advanced",
     "keywords": ["量子隧穿", "势垒", "波粒二象性", "不确定性原理"],
     "content": "量子隧穿是粒子穿越经典力学无法逾越势垒的现象。科幻应用包括穿墙术和传送技术。"},
    
    {"title": "中子星与脉冲星", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["中子星", "脉冲星", "致密天体", "磁场"],
     "content": "中子星是超新星爆发后的极致密天体，脉冲星是旋转的中子星。密度极高，磁场超强。科幻应用包括脉冲星导航和中子星物质。"},
    
    {"title": "狭义相对论基础", "domain": "physics", "difficulty": "basic",
     "keywords": ["相对论", "爱因斯坦", "光速", "质能方程"],
     "content": "狭义相对论两大原理：相对性原理和光速不变原理。核心结论包括时间膨胀、长度收缩和质能方程E=mc²。"},
    
    {"title": "广义相对论与时空弯曲", "domain": "physics", "difficulty": "advanced",
     "keywords": ["广义相对论", "时空弯曲", "引力", "测地线"],
     "content": "广义相对论将引力解释为时空弯曲。实验验证包括光线弯曲、引力红移和引力波。科幻应用包括引力弹弓和时空扭曲武器。"},
    
    {"title": "热力学第二定律", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["热力学", "熵", "第二定律", "时间箭头"],
     "content": "孤立系统的熵永不减少，这是时间箭头的物理基础。科幻应用包括热寂宇宙和逆转熵。"},
    
    {"title": "量子力学不确定性原理", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["不确定性原理", "海森堡", "观测", "概率"],
     "content": "无法同时精确测量粒子的位置和动量。ΔxΔp ≥ ℏ/2。科幻应用包括观测者效应和平行宇宙。"},
    
    {"title": "超导体与超导现象", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["超导体", "零电阻", "迈斯纳效应", "磁悬浮"],
     "content": "超导体在特定温度下电阻为零，具有完全抗磁性。科幻应用包括磁悬浮列车和超导储能。"},
    
    {"title": "粒子加速器", "domain": "physics", "difficulty": "advanced",
     "keywords": ["粒子加速器", "对撞机", "LHC", "高能物理"],
     "content": "粒子加速器将粒子加速到接近光速，用于探索物质基本结构。科幻应用包括反物质生产和黑洞制造。"},
    
    {"title": "宇宙射线与辐射", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["宇宙射线", "辐射", "太阳风", "高能粒子"],
     "content": "宇宙射线是来自外太空的高能粒子流。科幻应用包括太空辐射防护和辐射变异。"},
    
    {"title": "激光原理与应用", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["激光", "受激辐射", "相干光", "激光武器"],
     "content": "激光具有高方向性、单色性和亮度。科幻应用包括激光武器、激光推进和激光核聚变。"},
    
    {"title": "等离子体物理", "domain": "physics", "difficulty": "advanced",
     "keywords": ["等离子体", "第四态", "核聚变", "等离子武器"],
     "content": "等离子体是物质的第四态，占宇宙可见物质的99%。科幻应用包括等离子武器和等离子护盾。"},
    
    {"title": "弦理论与多维空间", "domain": "physics", "difficulty": "advanced",
     "keywords": ["弦理论", "多维空间", "M理论", "额外维度"],
     "content": "弦理论认为基本粒子是一维弦的振动，需要10或11维时空。科幻应用包括维度旅行和平行宇宙。"},
    
    {"title": "电磁学基础", "domain": "physics", "difficulty": "basic",
     "keywords": ["电磁学", "麦克斯韦", "电磁波", "电磁炮"],
     "content": "电磁学研究电场和磁场的相互作用。麦克斯韦方程组统一电磁学。科幻应用包括电磁炮和电磁护盾。"},
    
    {"title": "光子学与量子光学", "domain": "physics", "difficulty": "advanced",
     "keywords": ["光子", "量子光学", "量子通信", "光子计算机"],
     "content": "光子学研究光子的产生、操控和探测。科幻应用包括光子计算机和光子武器。"},
    
    {"title": "费米子与玻色子", "domain": "physics", "difficulty": "advanced",
     "keywords": ["费米子", "玻色子", "自旋", "泡利不相容"],
     "content": "费米子遵循泡利不相容原理，玻色子可占据相同量子态。科幻应用包括玻色-爱因斯坦凝聚态。"},
    
    {"title": "标准模型与基本粒子", "domain": "physics", "difficulty": "advanced",
     "keywords": ["标准模型", "基本粒子", "夸克", "希格斯粒子"],
     "content": "标准模型描述已知基本粒子及相互作用。包括夸克、轻子和规范玻色子。科幻应用包括新粒子发现。"},
    
    {"title": "核裂变与链式反应", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["核裂变", "链式反应", "铀-235", "临界质量"],
     "content": "核裂变是重原子核分裂释放能量的过程。科幻应用包括核裂变反应堆和核武器。"},
    
    {"title": "恒星演化与核合成", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["恒星演化", "核合成", "红巨星", "超新星"],
     "content": "恒星通过核聚变将轻元素转化为重元素。科幻应用包括人造恒星和恒星武器。"},
    
    {"title": "宇宙大爆炸理论", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["大爆炸", "宇宙起源", "暴胀", "宇宙微波背景"],
     "content": "宇宙起源于138亿年前的大爆炸。科幻应用包括宇宙起源探索和宇宙重启。"},
    
    {"title": "狄拉克海与反粒子", "domain": "physics", "difficulty": "advanced",
     "keywords": ["狄拉克海", "反粒子", "正电子", "真空能"],
     "content": "狄拉克方程预言反粒子存在。科幻应用包括真空能提取和反物质生成。"},
    
    {"title": "拓扑绝缘体", "domain": "physics", "difficulty": "advanced",
     "keywords": ["拓扑绝缘体", "量子霍尔效应", "表面态", "自旋电子学"],
     "content": "拓扑绝缘体内部绝缘但表面导电。科幻应用包括量子计算机和无损传输。"},
    
    {"title": "量子计算机原理", "domain": "physics", "difficulty": "advanced",
     "keywords": ["量子计算机", "量子比特", "叠加态", "量子算法"],
     "content": "量子计算机利用量子叠加和纠缠进行计算。科幻应用包括破解密码和量子AI。"},
    
    # 额外20条物理学知识点
    {"title": "阿尔库别雷引擎", "domain": "physics", "difficulty": "advanced",
     "keywords": ["曲速引擎", "超光速", "时空扭曲", "负质量"],
     "content": "阿尔库别雷引擎通过压缩和拉伸空间实现超光速旅行。需要负质量物质。科幻应用包括星际旅行和曲速护盾。"},
    
    {"title": "费米悖论", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["费米悖论", "大过滤器", "外星文明", "黑暗森林"],
     "content": "费米悖论问：如果存在大量外星文明，为何我们未遇到？科幻应用包括大过滤器和黑暗森林法则。"},
    
    {"title": "戴森球", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["戴森球", "恒星工程", "能量收集", "卡尔达肖夫指数"],
     "content": "戴森球是包围恒星的巨型结构，收集全部能量。科幻应用包括超级文明的能源需求。"},
    
    {"title": "量子退相干", "domain": "physics", "difficulty": "advanced",
     "keywords": ["量子退相干", "量子态", "环境作用", "测量问题"],
     "content": "量子退相干是量子系统与环境的相互作用导致量子特性消失。科幻应用包括量子隔离技术。"},
    
    {"title": "时空奇点", "domain": "physics", "difficulty": "advanced",
     "keywords": ["奇点", "黑洞奇点", "宇宙奇点", "物理定律失效"],
     "content": "时空奇点是物理定律失效的极端区域。科幻应用包括奇点武器和宇宙起源。"},
    
    {"title": "量子场论基础", "domain": "physics", "difficulty": "advanced",
     "keywords": ["量子场论", "量子化场", "粒子产生", "虚粒子"],
     "content": "量子场论统一量子力学和狭义相对论。科幻应用包括粒子创造和真空涨落。"},
    
    {"title": "暗黑能量星", "domain": "physics", "difficulty": "advanced",
     "keywords": ["暗能量星", "暗能量", "黑洞替代", "奇异天体"],
     "content": "暗黑能量星是黑洞的替代理论，内部可能包含暗能量。科幻应用包括新型天体武器。"},
    
    {"title": "引力透镜效应", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["引力透镜", "光线弯曲", "暗物质探测", "天文观测"],
     "content": "引力透镜是大质量天体弯曲光线的现象。科幻应用包括引力望远镜和暗物质探测。"},
    
    {"title": "宇宙弦", "domain": "physics", "difficulty": "advanced",
     "keywords": ["宇宙弦", "拓扑缺陷", "宇宙早期", "引力波源"],
     "content": "宇宙弦是宇宙早期的拓扑缺陷，具有极大质量密度。科幻应用包括引力波武器和时间旅行。"},
    
    {"title": "量子隐形传态", "domain": "physics", "difficulty": "advanced",
     "keywords": ["量子隐形传态", "量子纠缠", "信息传递", "传送"],
     "content": "量子隐形传态利用纠缠传递量子态信息。科幻应用包括传送技术和量子通讯。"},
    
    {"title": "玻色-爱因斯坦凝聚", "domain": "physics", "difficulty": "advanced",
     "keywords": ["玻色-爱因斯坦凝聚", "超冷原子", "量子态", "宏观量子效应"],
     "content": "玻色-爱因斯坦凝聚是超冷原子形成的宏观量子态。科幻应用包括量子传感器和超导体。"},
    
    {"title": "卡尔达肖夫指数", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["卡尔达肖夫指数", "文明等级", "能量消耗", "星际文明"],
     "content": "卡尔达肖夫指数根据能量消耗划分文明等级。I型利用行星能量，II型利用恒星能量，III型利用星系能量。"},
    
    {"title": "时间晶体", "domain": "physics", "difficulty": "advanced",
     "keywords": ["时间晶体", "时间周期性", "非平衡态", "永动机"],
     "content": "时间晶体是时间上周期性重复的结构。科幻应用包括永动时钟和量子存储器。"},
    
    {"title": "量子泡沫", "domain": "physics", "difficulty": "advanced",
     "keywords": ["量子泡沫", "时空微观结构", "普朗克尺度", "虚空能量"],
     "content": "量子泡沫是普朗克尺度上时空的剧烈涨落。科幻应用包括时空工程和虫洞创造。"},
    
    {"title": "马约拉纳费米子", "domain": "physics", "difficulty": "advanced",
     "keywords": ["马约拉纳费米子", "反粒子即自身", "拓扑量子计算", "准粒子"],
     "content": "马约拉纳费米子是自身的反粒子。科幻应用包括容错量子计算和新型探测器。"},
    
    {"title": "光压与太阳帆", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["光压", "太阳帆", "光子动量", "星际推进"],
     "content": "光压是光子撞击物体产生的压力。科幻应用包括太阳帆航天器和光压推进。"},
    
    {"title": "电磁场张量", "domain": "physics", "difficulty": "advanced",
     "keywords": ["电磁场张量", "相对论电动力学", "麦克斯韦方程", "协变性"],
     "content": "电磁场张量统一描述电场和磁场。科幻应用包括电磁场操控和能量转换。"},
    
    {"title": "量子霍尔效应", "domain": "physics", "difficulty": "advanced",
     "keywords": ["量子霍尔效应", "量子电阻", "二维电子气", "拓扑物态"],
     "content": "量子霍尔效应展现量子化的电阻值。科幻应用包括精密测量和量子标准。"},
    
    {"title": "宇宙微波背景辐射", "domain": "physics", "difficulty": "intermediate",
     "keywords": ["宇宙微波背景", "大爆炸余晖", "宇宙起源", "各向异性"],
     "content": "宇宙微波背景辐射是大爆炸的余晖，温度约2.7K。科幻应用包括宇宙考古和文明探测。"},
    
    {"title": "假真空衰变", "domain": "physics", "difficulty": "advanced",
     "keywords": ["假真空", "真空衰变", "宇宙相变", "真真空"],
     "content": "假真空是宇宙的亚稳态，可能衰变到真真空。科幻应用包括宇宙武器和维度崩溃。"},
]


# ============================================================================
# 化学知识点模板（30条精选）
# ============================================================================

CHEMISTRY_TEMPLATES = [
    {"title": "元素周期表", "domain": "chemistry", "difficulty": "basic",
     "keywords": ["元素周期表", "原子序数", "周期律", "元素分类"],
     "content": "元素周期表按原子序数排列元素。科幻应用包括新元素发现和超重元素。"},
    
    {"title": "化学键与分子结构", "domain": "chemistry", "difficulty": "basic",
     "keywords": ["化学键", "共价键", "离子键", "分子结构"],
     "content": "化学键是原子间的结合力。科幻应用包括超强材料和分子设计。"},
    
    {"title": "催化反应", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["催化剂", "酶", "活化能", "催化反应"],
     "content": "催化剂加速化学反应但不被消耗。科幻应用包括人工光合作用和酶工程。"},
    
    {"title": "高分子材料", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["高分子", "聚合物", "塑料", "智能材料"],
     "content": "高分子由大量重复单元组成。科幻应用包括超强纤维和自修复材料。"},
    
    {"title": "电化学与电池", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["电化学", "电池", "锂电池", "燃料电池"],
     "content": "电化学研究电能与化学能转化。科幻应用包括超级电池和核电池。"},
    
    {"title": "纳米材料", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["纳米材料", "石墨烯", "碳纳米管", "纳米机器人"],
     "content": "纳米材料在纳米尺度展现独特性质。科幻应用包括纳米机器人和纳米装甲。"},
    
    {"title": "化学反应动力学", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["反应动力学", "反应速率", "活化能", "阿伦尼乌斯"],
     "content": "反应动力学研究反应速率。科幻应用包括冷核聚变和时间加速。"},
    
    {"title": "有机合成", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["有机合成", "药物化学", "药物设计", "靶向药物"],
     "content": "有机合成构建有机分子。科幻应用包括万能药物和基因药物。"},
    
    {"title": "同位素与放射性", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["同位素", "放射性", "半衰期", "衰变"],
     "content": "同位素质子数相同但中子数不同。科幻应用包括放射性治疗和核电池。"},
    
    {"title": "超临界流体", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["超临界流体", "绿色化学", "CO₂", "萃取"],
     "content": "超临界流体具有液体和气体双重特性。科幻应用包括绿色工业和废物转化。"},
    
    # 额外20条化学知识点
    {"title": "配位化学", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["配位化合物", "配体", "中心原子", "螯合"],
     "content": "配位化学研究金属与配体的结合。科幻应用包括催化剂设计和金属药物。"},
    
    {"title": "表面化学", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["表面化学", "吸附", "催化", "表面活性剂"],
     "content": "表面化学研究界面现象。科幻应用包括催化剂和纳米材料。"},
    
    {"title": "电化学腐蚀", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["腐蚀", "氧化", "电化学", "防护"],
     "content": "电化学腐蚀是金属氧化的过程。科幻应用包括材料保护和自修复涂层。"},
    
    {"title": "量子化学", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["量子化学", "分子轨道", "电子结构", "计算化学"],
     "content": "量子化学用量子力学研究化学问题。科幻应用包括分子设计和反应预测。"},
    
    {"title": "生物化学基础", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["生物化学", "蛋白质", "核酸", "代谢"],
     "content": "生物化学研究生命过程的化学基础。科幻应用包括基因工程和药物设计。"},
    
    {"title": "光化学反应", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["光化学", "光反应", "光合作用", "光催化"],
     "content": "光化学反应由光驱动。科幻应用包括人工光合作用和光动力治疗。"},
    
    {"title": "电化学合成", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["电合成", "电解", "电化学", "绿色合成"],
     "content": "电化学合成利用电能驱动化学反应。科幻应用包括绿色化学和高选择性合成。"},
    
    {"title": "金属有机框架", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["MOF", "多孔材料", "气体存储", "催化"],
     "content": "金属有机框架是高孔隙度材料。科幻应用包括气体存储和分离技术。"},
    
    {"title": "超分子化学", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["超分子", "分子识别", "自组装", "主客体化学"],
     "content": "超分子化学研究分子间的非共价相互作用。科幻应用包括分子机器和智能材料。"},
    
    {"title": "固态化学", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["固态化学", "晶体", "半导体", "功能材料"],
     "content": "固态化学研究固体材料的结构和性质。科幻应用包括半导体和超导体。"},
    
    {"title": "化学热力学", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["化学热力学", "自由能", "平衡常数", "自发反应"],
     "content": "化学热力学研究化学反应的能量变化。科幻应用包括能量转换和过程优化。"},
    
    {"title": "手性化学", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["手性", "对映体", "旋光性", "不对称合成"],
     "content": "手性化学研究分子的空间结构不对称性。科幻应用包括药物合成和催化剂设计。"},
    
    {"title": "胶体化学", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["胶体", "纳米颗粒", "分散系", "界面"],
     "content": "胶体化学研究胶体分散系。科幻应用包括纳米材料和药物递送。"},
    
    {"title": "计算化学", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["计算化学", "分子模拟", "密度泛函", "机器学习"],
     "content": "计算化学用计算机模拟化学过程。科幻应用包括材料设计和反应预测。"},
    
    {"title": "化学传感器", "domain": "chemistry", "difficulty": "intermediate",
     "keywords": ["传感器", "检测", "生物传感", "纳米传感"],
     "content": "化学传感器检测特定分子。科幻应用包括环境监测和医疗诊断。"},
    
    {"title": "自由基化学", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["自由基", "链式反应", "抗氧化", "衰老"],
     "content": "自由基是含未配对电子的分子。科幻应用包括抗氧化治疗和自由基武器。"},
    
    {"title": "生物无机化学", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["生物无机", "金属蛋白", "金属酶", "微量元素"],
     "content": "生物无机化学研究生物体系中的金属。科幻应用包括金属药物和生物催化。"},
    
    {"title": "多相催化", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["多相催化", "表面催化", "工业催化", "催化剂"],
     "content": "多相催化是催化剂与反应物不同相的反应。科幻应用包括工业生产和环境治理。"},
    
    {"title": "化学振荡反应", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["振荡反应", "B-Z反应", "非线性动力学", "自组织"],
     "content": "化学振荡反应呈现周期性变化。科幻应用包括时间规律和生物节律。"},
    
    {"title": "离子液体", "domain": "chemistry", "difficulty": "advanced",
     "keywords": ["离子液体", "绿色溶剂", "室温熔盐", "电化学"],
     "content": "离子液体是室温下的熔盐。科幻应用包括绿色化学和电解质。"},
]


# ============================================================================
# 生物学知识点模板（20条精选）
# ============================================================================

BIOLOGY_TEMPLATES = [
    {"title": "基因编辑CRISPR", "domain": "biology", "difficulty": "advanced",
     "keywords": ["CRISPR", "基因编辑", "Cas9", "基因工程"],
     "content": "CRISPR-Cas9是革命性基因编辑技术。科幻应用包括基因改造人和定制婴儿。"},
    
    {"title": "进化论", "domain": "biology", "difficulty": "basic",
     "keywords": ["进化论", "自然选择", "达尔文", "适者生存"],
     "content": "进化论解释物种起源和多样性。科幻应用包括定向进化和进化加速。"},
    
    {"title": "干细胞与再生医学", "domain": "biology", "difficulty": "advanced",
     "keywords": ["干细胞", "再生医学", "iPS", "器官再生"],
     "content": "干细胞具有自我更新和分化潜能。科幻应用包括器官再生和抗衰老。"},
    
    {"title": "脑科学与神经可塑性", "domain": "biology", "difficulty": "advanced",
     "keywords": ["脑科学", "神经可塑性", "神经元", "脑机接口"],
     "content": "脑科学探索大脑工作机制。科幻应用包括脑机接口和意识上传。"},
    
    {"title": "微生物组", "domain": "biology", "difficulty": "intermediate",
     "keywords": ["微生物组", "肠道菌群", "益生菌", "共生"],
     "content": "人体微生物组与人体健康密切相关。科幻应用包括微生物疗法和异星适应。"},
    
    {"title": "合成生物学", "domain": "biology", "difficulty": "advanced",
     "keywords": ["合成生物学", "人工生命", "基因合成", "生物工程"],
     "content": "合成生物学设计和构建新生物系统。科幻应用包括人造生命和生物计算机。"},
    
    {"title": "表观遗传学", "domain": "biology", "difficulty": "advanced",
     "keywords": ["表观遗传学", "DNA甲基化", "基因表达", "遗传"],
     "content": "表观遗传学研究基因表达的遗传变化。科幻应用包括表观遗传治疗和环境适应。"},
    
    {"title": "病毒学", "domain": "biology", "difficulty": "intermediate",
     "keywords": ["病毒", "流行病学", "传染病", "疫苗"],
     "content": "病毒是寄生生物。科幻应用包括超级病毒和基因治疗病毒。"},
    
    {"title": "衰老机制", "domain": "biology", "difficulty": "intermediate",
     "keywords": ["衰老", "长寿", "端粒", "抗衰老"],
     "content": "衰老是生物体功能逐渐衰退。科幻应用包括长生不老和逆转衰老。"},
    
    {"title": "生态平衡", "domain": "biology", "difficulty": "basic",
     "keywords": ["生态系统", "生态平衡", "食物链", "能量流动"],
     "content": "生态系统由生物群落和环境组成。科幻应用包括生态系统设计和异星生态。"},
    
    # 额外10条生物学知识点
    {"title": "克隆技术", "domain": "biology", "difficulty": "advanced",
     "keywords": ["克隆", "体细胞核移植", "多莉羊", "生殖性克隆"],
     "content": "克隆技术创造基因完全相同的个体。科幻应用包括克隆人和器官克隆。"},
    
    {"title": "生物多样性", "domain": "biology", "difficulty": "basic",
     "keywords": ["生物多样性", "物种灭绝", "保护", "生态系统"],
     "content": "生物多样性是生命形式的丰富程度。科幻应用包括物种复活和生态修复。"},
    
    {"title": "基因治疗", "domain": "biology", "difficulty": "advanced",
     "keywords": ["基因治疗", "遗传病", "病毒载体", "靶向治疗"],
     "content": "基因治疗通过修正基因治疗疾病。科幻应用包括根治遗传病和基因增强。"},
    
    {"title": "蛋白质工程", "domain": "biology", "difficulty": "advanced",
     "keywords": ["蛋白质工程", "酶设计", "结构生物学", "定向进化"],
     "content": "蛋白质工程设计和改造蛋白质。科幻应用包括酶催化剂和纳米机器。"},
    
    {"title": "免疫系统", "domain": "biology", "difficulty": "intermediate",
     "keywords": ["免疫", "抗体", "疫苗", "免疫治疗"],
     "content": "免疫系统保护机体免受病原体侵害。科幻应用包括免疫增强和癌症治疗。"},
    
    {"title": "细胞凋亡", "domain": "biology", "difficulty": "intermediate",
     "keywords": ["细胞凋亡", "程序性死亡", "癌细胞", "治疗"],
     "content": "细胞凋亡是程序性细胞死亡。科幻应用包括癌症治疗和抗衰老。"},
    
    {"title": "遗传密码", "domain": "biology", "difficulty": "intermediate",
     "keywords": ["遗传密码", "DNA", "RNA", "蛋白质合成"],
     "content": "遗传密码是DNA到蛋白质的编码规则。科幻应用包括人工遗传系统和外星生命。"},
    
    {"title": "共生关系", "domain": "biology", "difficulty": "basic",
     "keywords": ["共生", "互利共生", "寄生", "协同进化"],
     "content": "共生关系是不同物种间的密切关系。科幻应用包括外星共生和共生武器。"},
    
    {"title": "生物钟与昼夜节律", "domain": "biology", "difficulty": "intermediate",
     "keywords": ["生物钟", "昼夜节律", "基因调控", "睡眠"],
     "content": "生物钟调节生物体的生理节律。科幻应用包括太空适应和时间武器。"},
    
    {"title": "外星生命探测", "domain": "biology", "difficulty": "advanced",
     "keywords": ["外星生命", "生命迹象", "火星探测", "宜居带"],
     "content": "外星生命探测寻找地外生命迹象。科幻应用包括第一次接触和外星殖民。"},
]


# ============================================================================
# 构建函数
# ============================================================================

def generate_knowledge_id(category: str, domain: str, index: int) -> str:
    """生成知识点ID"""
    return f"{category}-{domain}-{index:03d}"


def create_knowledge_point(template: Dict[str, Any], category: str, index: int) -> Dict[str, Any]:
    """创建知识点"""
    return {
        "knowledge_id": generate_knowledge_id(category, template["domain"], index),
        "category": category,
        "domain": template["domain"],
        "title": template["title"],
        "content": template["content"],
        "keywords": template["keywords"],
        "difficulty": template["difficulty"],
        "tags": [category, template["domain"], template["difficulty"]],
        "metadata": {
            "source": "expert",
            "confidence": 0.9,
            "language": "zh",
            "author": "数据工程师"
        },
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }


def build_knowledge_base():
    """构建知识库"""
    workspace_root = Path(__file__).parent.parent
    knowledge_dir = workspace_root / "data" / "knowledge" / "scifi"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    
    # 构建物理知识库
    physics_knowledge = [
        create_knowledge_point(t, "scifi", i+1)
        for i, t in enumerate(PHYSICS_TEMPLATES)
    ]
    
    with open(knowledge_dir / "physics.json", 'w', encoding='utf-8') as f:
        json.dump(physics_knowledge, f, ensure_ascii=False, indent=2)
    print(f"[OK] Physics knowledge: {len(physics_knowledge)} points")
    
    # 构建化学知识库
    chemistry_knowledge = [
        create_knowledge_point(t, "scifi", i+1)
        for i, t in enumerate(CHEMISTRY_TEMPLATES)
    ]
    
    with open(knowledge_dir / "chemistry.json", 'w', encoding='utf-8') as f:
        json.dump(chemistry_knowledge, f, ensure_ascii=False, indent=2)
    print(f"[OK] Chemistry knowledge: {len(chemistry_knowledge)} points")
    
    # 构建生物知识库
    biology_knowledge = [
        create_knowledge_point(t, "scifi", i+1)
        for i, t in enumerate(BIOLOGY_TEMPLATES)
    ]
    
    with open(knowledge_dir / "biology.json", 'w', encoding='utf-8') as f:
        json.dump(biology_knowledge, f, ensure_ascii=False, indent=2)
    print(f"[OK] Biology knowledge: {len(biology_knowledge)} points")
    
    total = len(physics_knowledge) + len(chemistry_knowledge) + len(biology_knowledge)
    print(f"\n[DONE] Scifi knowledge base built! Total: {total} points")
    print(f"[INFO] Location: {knowledge_dir}")
    
    return {
        "physics": len(physics_knowledge),
        "chemistry": len(chemistry_knowledge),
        "biology": len(biology_knowledge),
        "total": total
    }


if __name__ == "__main__":
    build_knowledge_base()
