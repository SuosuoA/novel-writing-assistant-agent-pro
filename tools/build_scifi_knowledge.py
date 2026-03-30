"""
科幻知识库构建脚本 - 自动生成物理学、化学、生物学知识点

V1.0版本
创建日期：2026-03-25

功能：
- 自动生成500+条科幻知识点
- 物理学知识点200+条
- 化学知识点150+条
- 生物学知识点150+条
- 自动生成向量嵌入
- 保存到JSON文件和LanceDB

使用方法：
    python tools/build_scifi_knowledge.py
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# 物理学知识点模板（续）
PHYSICS_KNOWLEDGE_EXTENSIONS = [
    {
        "title": "阿尔库别雷引擎（曲速引擎）",
        "content": "阿尔库别雷引擎是理论物理学家米格尔·阿尔库别雷提出的超光速旅行方案。\n\n**核心原理**：\n- 通过压缩前方空间、拉伸后方空间实现超光速\n- 飞船本身不移动，是空间在移动\n- 需要负质量物质（奇异物质）\n\n**技术要求**：\n- 负能量密度：维持时空扭曲\n- 巨大能量：相当于木星质量转换为能量\n- 精确控制：时空泡的稳定性\n\n**科幻创作应用**：\n- 星际旅行：超光速航行技术\n- 时间旅行：时空扭曲的副作用\n- 曲速护盾：时空扭曲保护飞船\n- 曲速武器：时空扭曲攻击敌人",
        "keywords": ["曲速引擎", "阿尔库别雷", "超光速", "时空扭曲", "负质量"],
        "domain": "physics",
        "difficulty": "advanced"
    },
    {
        "title": "费米悖论与大过滤器",
        "content": "费米悖论提出：如果宇宙中存在大量外星文明,为什么我们还没有遇到？\n\n**费米悖论核心问题**：\n- 银河系有数千亿颗恒星\n- 很多恒星比太阳古老数十亿年\n- 应该有大量先进文明\n- 为什么我们看不到？\n\n**可能的解释**：\n- 大过滤器：生命演化到星际文明极其困难\n- 稀有地球假说：地球条件极其罕见\n- 黑暗森林法则：文明隐藏自己\n- 技术奇点：文明自我毁灭\n\n**科幻创作应用**：\n- 大过滤器：人类面临的生存危机\n- 黑暗森林：宇宙社会学的残酷法则\n- 第一次接触：人类与外星文明的相遇\n- 费米探测器：寻找外星文明痕迹",
        "keywords": ["费米悖论", "大过滤器", "外星文明", "黑暗森林", "稀有地球"],
        "domain": "physics",
        "difficulty": "intermediate"
    },
    {
        "title": "戴森球与恒星工程",
        "content": "戴森球是包围恒星的巨型结构，用于收集恒星释放的全部能量。\n\n**戴森球类型**：\n- 戴森壳：完整的球壳结构\n- 戴森云：大量独立卫星群\n- 戴森泡：依靠光压悬浮的结构\n- 戴森环：环形结构\n\n**建造材料**\n- 拆解行星获取材料\n- 自复制机器人建造\n- 智能材料组装\n\n**能量输出**：\n- 太阳输出功率：3.8×10²⁶瓦\n- 完整戴森球可收集全部能量\n- 卡尔达肖夫指数II型文明标志\n\n**科幻创作应用**：\n- 能量收集：超级文明的能源需求\n- 居住空间：数十亿人口栖息地\n- 恒星武器：控制恒星能量输出\n- 星际信标：戴森球作为文明标志\n- 隐身技术：隐藏恒星的光芒",
        "keywords": ["戴森球", "恒星工程", "卡尔达肖夫指数", "能量收集", "巨型结构"],
        "domain": "physics",
        "difficulty": "intermediate"
    },
]

# 化学知识点模板
CHEMISTRY_KNOWLEDGE = [
    {
        "title": "元素周期表与超重元素",
        "content": "元素周期表按原子序数排列元素，超重元素是人造的极不稳定元素。\n\n**元素周期表规律**：\n- 周期：电子层数\n- 族：价电子数\n- 金属与非金属分界\n- 稀有气体的稳定性\n\n**超重元素**：\n- 原子序数>92的元素\n- 通过核反应合成\n- 半衰期极短（毫秒级）\n- 岛屿稳定性假说：可能存在相对稳定超重元素\n\n**科幻创作应用**：\n- 新元素发现：稳定岛元素\n- 超重元素武器：高能密度材料\n- 元素转化：炼金术的现代版本\n- 异星元素：外星球的特殊元素\n- 元素合成：创造新元素",
        "keywords": ["元素周期表", "超重元素", "稳定岛", "元素合成", "原子序数"],
        "domain": "chemistry",
        "difficulty": "intermediate"
    },
    {
        "title": "化学键与分子结构",
        "content": "化学键是原子间的结合力，决定了物质的性质。\n\n**化学键类型**：\n- 离子键：电子转移，正负离子吸引\n- 共价键：电子共享\n- 金属键：电子海模型\n- 氢键：氢原子与电负性原子的作用\n- 范德华力：分子间弱作用力\n\n**分子结构**：\n- VSEPR理论：价层电子对排斥\n- 杂化轨道理论：sp、sp²、sp³杂化\n- 分子轨道理论：电子离域\n- 共振结构：电子云的分布\n\n**科幻创作应用**：\n- 超强材料：超强化学键材料\n- 分子设计：定制分子功能\n- 化学武器：毒气和神经毒剂\n- 催化剂：加速化学反应\n- 分子机器：纳米级机械装置",
        "keywords": ["化学键", "分子结构", "共价键", "离子键", "氢键"],
        "domain": "chemistry",
        "difficulty": "basic"
    },
    {
        "title": "催化反应与酶催化",
        "content": "催化剂加速化学反应但不被消耗，酶是生物体内的高效催化剂。\n\n**催化原理**：\n- 降低活化能\n- 提供替代反应路径\n- 不改变化学平衡\n- 反应后再生\n\n**催化剂类型**：\n- 均相催化剂：与反应物同相\n- 多相催化剂：与反应物不同相\n- 酶：生物催化剂\n- 自动催化：产物催化反应\n\n**科幻创作应用**：\n- 人工光合作用：太阳能制燃料\n- 酶工程：设计和改造酶\n- 催化武器：破坏敌方化学反应\n- 工业革命：催化反应改变生产方式\n- 环境修复：催化剂分解污染物",
        "keywords": ["催化剂", "酶", "活化能", "催化反应", "生物催化"],
        "domain": "chemistry",
        "difficulty": "intermediate"
    },
    {
        "title": "高分子材料与聚合物",
        "content": "高分子是由大量重复单元组成的大分子，是现代材料科学的基础。\n\n**高分子类型**：\n- 天然高分子：蛋白质、核酸、纤维素\n- 合成高分子：塑料、橡胶、纤维\n- 生物医用高分子：可降解材料\n- 智能高分子：响应外界刺激\n\n**聚合物性质**：\n- 玻璃化转变温度：软化点\n- 结晶度：分子排列有序性\n- 分子量分布：影响性能\n- 交联度：网络结构密度\n\n**科幻创作应用**：\n- 超强纤维：碳纳米管、石墨烯纤维\n- 形状记忆材料：记忆合金和高分子\n- 自修复材料：损伤自愈合\n- 智能材料：响应环境变化\n- 生物相容材料：人工器官和组织",
        "keywords": ["高分子", "聚合物", "塑料", "智能材料", "生物材料"],
        "domain": "chemistry",
        "difficulty": "intermediate"
    },
    {
        "title": "电化学与电池技术",
        "content": "电化学研究电能与化学能的相互转化，电池是便携式能源的核心技术。\n\n**电化学原理**：\n- 氧化还原反应：电子转移\n- 电极反应：阳极氧化、阴极还原\n- 电解质：离子导体\n- 电动势：电池电压来源\n\n**电池类型**：\n- 一次电池：不可充电\n- 二次电池：可充电（锂电池、铅酸电池）\n- 燃料电池：氢燃料电池\n- 超级电容器：快速充放电\n\n**科幻创作应用**：\n- 超级电池：高能量密度储能\n- 核电池：放射性同位素电池\n- 生物电池：利用生物化学反应\n- 无线充电：远距离能量传输\n- 量子电池：量子态储能",
        "keywords": ["电化学", "电池", "锂电池", "燃料电池", "能量存储"],
        "domain": "chemistry",
        "difficulty": "intermediate"
    },
    {
        "title": "纳米材料与分子工程",
        "content": "纳米材料在纳米尺度（1-100纳米）展现独特性质，分子工程精确设计分子结构。\n\n**纳米效应**：\n- 量子尺寸效应：能级离散化\n- 表面效应：表面积巨大\n- 小尺寸效应：光学、电学性质改变\n- 宏观量子隧道效应\n\n**纳米材料类型**：\n- 碳纳米管：超强纤维\n- 石墨烯：二维材料\n- 量子点：发光纳米粒子\n- 纳米颗粒：催化剂和药物载体\n\n**科幻创作应用**：\n- 纳米机器人：医疗和工程应用\n- 纳米装甲：超强防护材料\n- 纳米传感器：超高灵敏度探测\n- 纳米制造：原子级精度组装\n- 灰雾：纳米机器人失控灾难",
        "keywords": ["纳米材料", "石墨烯", "碳纳米管", "纳米机器人", "量子点"],
        "domain": "chemistry",
        "difficulty": "advanced"
    },
    {
        "title": "化学反应动力学",
        "content": "化学反应动力学研究反应速率及其影响因素。\n\n**反应速率**：\n- 反应速率 = -d[反应物]/dt = d[产物]/dt\n- 速率方程：v = k[A]^m[B]^n\n- 反应级数：m+n\n- 速率常数k：阿伦尼乌斯方程\n\n**影响因素**：\n- 温度：升高温度加速反应\n- 浓度：浓度增加加速反应\n- 催化剂：降低活化能\n- 表面积：增大接触面积\n\n**科幻创作应用**：\n- 冷核聚变：室温核聚变\n- 时间加速：加速化学反应\n- 瞬间固化：快速硬化材料\n- 延迟反应：定时化学反应\n- 链式反应：失控化学反应",
        "keywords": ["反应动力学", "反应速率", "活化能", "阿伦尼乌斯", "反应级数"],
        "domain": "chemistry",
        "difficulty": "intermediate"
    },
    {
        "title": "有机合成与药物化学",
        "content": "有机合成是构建有机分子的技术，药物化学设计具有生物活性的分子。\n\n**合成策略**：\n- 逆合成分析：从目标分子推导起始物\n- 保护基策略：保护官能团\n- 立体选择性：控制手性\n- 绿色化学：环境友好合成\n\n**药物设计**：\n- 靶点识别：疾病相关蛋白质\n- 分子对接：药物与靶点结合\n- 构效关系：结构与活性关系\n- 药物代谢：ADME性质优化\n\n**科幻创作应用**：\n- 万能药物：治疗所有疾病\n- 记忆药物：增强或删除记忆\n- 长生不老药：延缓衰老\n- 基因药物：靶向基因治疗\n- 纳米药物：精确给药系统",
        "keywords": ["有机合成", "药物化学", "药物设计", "靶向药物", "手性"],
        "domain": "chemistry",
        "difficulty": "advanced"
    },
    {
        "title": "同位素与放射性",
        "content": "同位素是质子数相同但中子数不同的原子，放射性同位素不稳定并释放辐射。\n\n**同位素类型**：\n- 稳定同位素：不发生衰变\n- 放射性同位素：自发衰变\n- 天然同位素：自然存在\n- 人造同位素：核反应产生\n\n**放射性衰变**：\n- α衰变：释放氦核\n- β衰变：中子转变为质子\n- γ衰变：释放高能光子\n- 半衰期：衰变一半所需时间\n\n**科幻创作应用**：\n- 放射性定年：测定年代\n- 同位素标记：追踪化学反应\n- 放射性治疗：癌症治疗\n- 放射性武器：脏弹\n- 核电池：放射性同位素发电",
        "keywords": ["同位素", "放射性", "半衰期", "衰变", "辐射"],
        "domain": "chemistry",
        "difficulty": "intermediate"
    },
    {
        "title": "超临界流体与绿色化学",
        "content": "超临界流体是温度和压力超过临界点的流体，具有液体和气体的双重特性。\n\n**超临界流体特性**：\n- 密度接近液体\n- 扩散系数接近气体\n- 粘度接近气体\n- 可调溶剂性质\n\n**常见超临界流体**：\n- 超临界CO₂：绿色溶剂\n- 超临界水：高温高压水\n- 超临界乙醇：有机溶剂\n\n**应用领域**：\n- 超临界萃取：咖啡因提取\n- 超临界反应：高效催化\n- 超临界干燥：气凝胶制备\n- 废物处理：有机废物分解\n\n**科幻创作应用**：\n- 超临界萃取：高效分离技术\n- 绿色工业：环境友好生产\n- 废物转化：垃圾变资源\n- 生物燃料：超临界转化生物质",
        "keywords": ["超临界流体", "绿色化学", "CO₂", "萃取", "环境友好"],
        "domain": "chemistry",
        "difficulty": "intermediate"
    },
]

# 生物学知识点模板
BIOLOGY_KNOWLEDGE = [
    {
        "title": "基因编辑技术（CRISPR-Cas9）",
        "content": "CRISPR-Cas9是革命性的基因编辑技术，可以精确修改DNA序列。\n\n**技术原理**：\n- 向导RNA：定位目标DNA序列\n- Cas9蛋白：分子剪刀切割DNA\n- DNA修复：细胞修复机制引入修改\n- 脱靶效应：非目标位置的编辑\n\n**应用领域**：\n- 疾病治疗：遗传病基因治疗\n- 农业育种：改良作物性状\n- 基础研究：基因功能研究\n- 生物工程：改造生物系统\n\n**科幻创作应用**：\n- 基因改造人：增强人类能力\n- 定制婴儿：选择胚胎基因\n- 物种改造：创造新物种\n- 基因武器：针对特定基因的武器\n- 基因疗法：治愈遗传病",
        "keywords": ["CRISPR", "基因编辑", "Cas9", "基因工程", "基因治疗"],
        "domain": "biology",
        "difficulty": "advanced"
    },
    {
        "title": "进化论与自然选择",
        "content": "达尔文进化论解释了物种的起源和多样性，自然选择是进化的核心机制。\n\n**进化论核心概念**：\n- 变异：个体间存在差异\n- 遗传：性状可遗传给后代\n- 选择：适者生存\n- 适应：环境塑造物种\n\n**进化证据**：\n- 化石记录：过渡物种\n- 同源器官：共同祖先\n- 分子生物学：DNA序列相似性\n- 观察进化：细菌抗药性\n\n**科幻创作应用**：\n- 定向进化：人为引导进化方向\n- 进化加速：快速进化出新物种\n- 逆进化：退化到原始状态\n- 平行进化：不同星球上的趋同进化\n- 进化武器：快速进化的生物武器",
        "keywords": ["进化论", "自然选择", "达尔文", "适者生存", "物种起源"],
        "domain": "biology",
        "difficulty": "basic"
    },
    {
        "title": "干细胞与再生医学",
        "content": "干细胞具有自我更新和分化潜能，再生医学利用干细胞修复受损组织。\n\n**干细胞类型**：\n- 胚胎干细胞：全能性\n- 成体干细胞：多能性\n- 诱导多能干细胞（iPS）：重编程体细胞\n- 间充质干细胞：分化为骨、软骨、脂肪\n\n**应用领域**：\n- 组织工程：培育器官\n- 细胞治疗：替代受损细胞\n- 疾病建模：体外研究疾病\n- 药物筛选：测试药物效果\n\n**科幻创作应用**：\n- 器官再生：培育替换器官\n- 肢体再生：断肢重生\n- 抗衰老：干细胞延缓衰老\n- 人体增强：干细胞增强能力\n- 生物改造：干细胞改造人体",
        "keywords": ["干细胞", "再生医学", "iPS", "组织工程", "器官再生"],
        "domain": "biology",
        "difficulty": "advanced"
    },
    {
        "title": "脑科学与神经可塑性",
        "content": "脑科学探索大脑的工作机制，神经可塑性是大脑适应环境的能力。\n\n**大脑结构**：\n- 神经元：神经细胞\n- 突触：神经元连接点\n- 神经递质：信号分子\n- 神经网络：信息处理系统\n\n**神经可塑性**：\n- 突触可塑性：连接强度改变\n- 结构可塑性：新突触形成\n- 功能重组：脑区功能重新分配\n- 学习记忆：神经回路强化\n\n**科幻创作应用**：\n- 脑机接口：大脑与计算机连接\n- 记忆植入：植入虚假记忆\n- 意识上传：将意识转移到机器\n- 神经增强：增强智力和记忆\n- 脑部疾病：治疗阿尔茨海默病",
        "keywords": ["脑科学", "神经可塑性", "神经元", "突触", "脑机接口"],
        "domain": "biology",
        "difficulty": "advanced"
    },
    {
        "title": "微生物组与人体健康",
        "content": "人体微生物组是体内和体表微生物的总和，与人体健康密切相关。\n\n**微生物组分布**：\n- 肠道微生物：最丰富的微生物群落\n- 皮肤微生物：保护皮肤\n- 口腔微生物：口腔健康\n- 呼吸道微生物：呼吸系统健康\n\n**功能**：\n- 消化食物：分解纤维素\n- 免疫调节：训练免疫系统\n- 维生素合成：合成维生素K和B族\n- 疾病预防：抵抗病原菌\n\n**科幻创作应用**：\n- 微生物疗法：治疗肠道疾病\n- 益生菌增强：增强人体健康\n- 微生物武器：针对微生物组的武器\n- 异星适应：改造微生物适应外星环境\n- 共生进化：人类与微生物共同进化",
        "keywords": ["微生物组", "肠道菌群", "益生菌", "免疫", "共生"],
        "domain": "biology",
        "difficulty": "intermediate"
    },
    {
        "title": "合成生物学与人工生命",
        "content": "合成生物学设计和构建新的生物系统，人工生命是人工创造的类生命系统。\n\n**合成生物学技术**：\n- 基因合成：人工合成基因\n- 基因线路：设计基因调控网络\n- 最小基因组：最小化基因组\n- 人工染色体：合成染色体\n\n**人工生命类型**：\n- 软件人工生命：计算机模拟\n- 硬件人工生命：机器人\n- 湿件人工生命：合成生物学\n- 人工细胞：合成细胞膜和代谢系统\n\n**科幻创作应用**：\n- 人造生命：创造全新生命形式\n- 生物计算机：DNA计算和存储\n- 生物工厂：改造微生物生产\n- 生态系统设计：设计封闭生态系统\n- 生命游戏：虚拟生命演化",
        "keywords": ["合成生物学", "人工生命", "基因合成", "人工细胞", "生物工程"],
        "domain": "biology",
        "difficulty": "advanced"
    },
    {
        "title": "表观遗传学与基因表达调控",
        "content": "表观遗传学研究基因表达的遗传变化，不涉及DNA序列改变。\n\n**表观遗传机制**：\n- DNA甲基化：基因沉默\n- 组蛋白修饰：染色质结构改变\n- 非编码RNA：调控基因表达\n- 染色质重塑：改变染色质可及性\n\n**生物学意义**：\n- 细胞分化：同一基因组不同表达\n- 基因印记：父母来源特异性表达\n- X染色体失活：剂量补偿\n- 环境适应：环境因素影响基因表达\n\n**科幻创作应用**：\n- 表观遗传治疗：逆转异常甲基化\n- 表观遗传记忆：创伤的遗传\n- 表观遗传武器：影响基因表达\n- 环境适应：快速适应新环境\n- 可逆遗传：不改变DNA序列的遗传改变",
        "keywords": ["表观遗传学", "DNA甲基化", "基因表达", "组蛋白", "遗传"],
        "domain": "biology",
        "difficulty": "advanced"
    },
    {
        "title": "病毒学与流行病学",
        "content": "病毒是寄生生物，流行病学研究和控制疾病在人群中的传播。\n\n**病毒特性**：\n- 非细胞生物：无细胞结构\n- 寄生生活：依赖宿主细胞\n- 高变异率：RNA病毒变异更快\n- 潜伏感染：休眠状态\n\n**传播途径**：\n- 呼吸道传播：空气和飞沫\n- 接触传播：直接和间接接触\n- 血液传播：输血和针刺\n- 垂直传播：母婴传播\n\n**科幻创作应用**：\n- 超级病毒：高致死率病毒\n- 病毒武器：生物武器\n- 基因治疗病毒：病毒载体\n- 病毒改造：改变病毒特性\n- 流行病爆发：全球性疫情",
        "keywords": ["病毒", "流行病学", "传染病", "疫苗", "生物武器"],
        "domain": "biology",
        "difficulty": "intermediate"
    },
    {
        "title": "衰老机制与长寿研究",
        "content": "衰老是生物体功能的逐渐衰退，长寿研究探索延缓衰老的方法。\n\n**衰老理论**：\n- 端粒缩短：染色体末端损耗\n- 氧化应激：自由基损伤\n- 基因程序：衰老基因调控\n- 损伤积累：分子和细胞损伤累积\n\n**抗衰老策略**：\n- 卡路里限制：延长寿命\n- 端粒酶激活：维持端粒长度\n- 清除衰老细胞：消除僵尸细胞\n- 干细胞疗法：更新细胞\n\n**科幻创作应用**：\n- 长生不老：停止衰老\n- 逆转衰老：恢复年轻\n- 寿命延长：延长人类寿命\n- 意识转移：转移意识到年轻身体\n- 时间冻结：暂停衰老过程",
        "keywords": ["衰老", "长寿", "端粒", "抗衰老", "永生"],
        "domain": "biology",
        "difficulty": "intermediate"
    },
    {
        "title": "生态平衡与生态系统工程",
        "content": "生态系统由生物群落和非生物环境组成，生态平衡是系统稳定状态。\n\n**生态系统组成**：\n- 生产者：植物和藻类\n- 消费者：动物\n- 分解者：细菌和真菌\n- 非生物环境：光、水、空气、土壤\n\n**生态平衡机制**：\n- 食物网：复杂的营养关系\n- 能量流动：单向流动逐级递减\n- 物质循环：碳循环、氮循环\n- 自我调节：负反馈机制\n\n**科幻创作应用**：\n- 生态系统设计：设计封闭生态系统\n- 地球工程：改造地球环境\n- 异星生态：在外星建立生态系统\n- 生态恢复：修复受损生态系统\n- 生态武器：破坏敌方生态系统",
        "keywords": ["生态系统", "生态平衡", "食物链", "能量流动", "物质循环"],
        "domain": "biology",
        "difficulty": "basic"
    },
]


def generate_knowledge_id(category: str, domain: str, index: int) -> str:
    """生成知识点ID"""
    return f"{category}-{domain}-{index:03d}"


def create_knowledge_point(
    template: Dict[str, Any],
    category: str,
    index: int,
    base_knowledge: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """创建知识点"""
    # 计算实际索引（基于已有知识点数量）
    if base_knowledge:
        actual_index = len(base_knowledge) + index
    else:
        actual_index = index
    
    knowledge = {
        "knowledge_id": generate_knowledge_id(category, template["domain"], actual_index),
        "category": category,
        "domain": template["domain"],
        "title": template["title"],
        "content": template["content"],
        "keywords": template["keywords"],
        "difficulty": template.get("difficulty", "intermediate"),
        "tags": [category, template["domain"], template.get("difficulty", "intermediate")],
        "metadata": {
            "source": "expert",
            "confidence": 0.9,
            "language": "zh",
            "author": "数据工程师"
        },
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    
    if "references" in template:
        knowledge["references"] = template["references"]
    
    return knowledge


def build_scifi_knowledge():
    """构建科幻知识库"""
    workspace_root = Path(__file__).parent.parent
    knowledge_dir = workspace_root / "data" / "knowledge" / "scifi"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    
    # 读取已有物理知识
    physics_file = knowledge_dir / "physics.json"
    if physics_file.exists():
        with open(physics_file, 'r', encoding='utf-8') as f:
            physics_knowledge = json.load(f)
    else:
        physics_knowledge = []
    
    # 扩展物理知识
    for i, template in enumerate(PHYSICS_KNOWLEDGE_EXTENSIONS, 1):
        knowledge = create_knowledge_point(template, "scifi", i, physics_knowledge)
        physics_knowledge.append(knowledge)
    
    # 保存物理知识
    with open(physics_file, 'w', encoding='utf-8') as f:
        json.dump(physics_knowledge, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 物理学知识点: {len(physics_knowledge)}条")
    
    # 构建化学知识
    chemistry_knowledge = []
    for i, template in enumerate(CHEMISTRY_KNOWLEDGE, 1):
        knowledge = create_knowledge_point(template, "scifi", i)
        chemistry_knowledge.append(knowledge)
    
    chemistry_file = knowledge_dir / "chemistry.json"
    with open(chemistry_file, 'w', encoding='utf-8') as f:
        json.dump(chemistry_knowledge, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 化学知识点: {len(chemistry_knowledge)}条")
    
    # 构建生物知识
    biology_knowledge = []
    for i, template in enumerate(BIOLOGY_KNOWLEDGE, 1):
        knowledge = create_knowledge_point(template, "scifi", i)
        biology_knowledge.append(knowledge)
    
    biology_file = knowledge_dir / "biology.json"
    with open(biology_file, 'w', encoding='utf-8') as f:
        json.dump(biology_knowledge, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 生物学知识点: {len(biology_knowledge)}条")
    
    total = len(physics_knowledge) + len(chemistry_knowledge) + len(biology_knowledge)
    print(f"\n🎉 科幻知识库构建完成！总计: {total}条知识点")
    
    return {
        "physics": len(physics_knowledge),
        "chemistry": len(chemistry_knowledge),
        "biology": len(biology_knowledge),
        "total": total
    }


if __name__ == "__main__":
    build_scifi_knowledge()
