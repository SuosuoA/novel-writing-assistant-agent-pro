#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库批量增强脚本
为所有知识点添加详细内容、案例、误区和参考来源
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# 科幻-物理学增强数据（扩展版）
PHYSICS_ENHANCEMENTS = {
    "scifi-physics-009": {
        "content": """暗物质是宇宙中不发光但产生引力的神秘物质，占宇宙物质的85%。

**暗物质证据**：
- 星系旋转曲线：外缘恒星速度异常
- 引力透镜：光线被不可见物质弯曲
- 宇宙微波背景：早期宇宙密度波动
- 大尺度结构：星系分布需要暗物质

**暗物质候选**：
- WIMPs：弱相互作用大质量粒子
- 轴子：假设的轻质量粒子
- 原初黑洞：宇宙早期的黑洞
- 中微子：已知粒子但质量太轻

**探测方法**：
- 直接探测：地下实验探测碰撞
- 间接探测：探测湮灭信号
- 对撞机：创造暗物质粒子

**科幻创作应用**：
- 暗物质能源：开发暗物质的能量
- 暗物质武器：隐形破坏力
- 暗物质生命：以暗物质为基础的生命""",
        "examples": [
            "《三体》：暗物质作为宇宙文明的能源",
            "《星际穿越》：暗物质维持虫洞稳定",
            "《质量效应》：暗物质作为FTL燃料",
            "《精英危险》：暗物质用于超光速引擎"
        ],
        "common_mistakes": [
            "错误：暗物质就是黑洞（实际是不同概念）",
            "错误：暗物质已被证实存在（实际只是理论假设）",
            "错误：暗物质可以轻易开发利用（实际无法直接探测）"
        ],
        "references": [
            "《暗物质与暗能量》- Lisa Randall",
            "LUX实验报告",
            "NASA暗物质研究",
            "Nature物理学刊"
        ]
    },
    "scifi-physics-010": {
        "content": """暗能量是推动宇宙加速膨胀的神秘能量，占宇宙总能量的68%。

**暗能量发现**：
- 1998年：超新星观测发现宇宙加速膨胀
- 诺贝尔物理学奖2011年授予相关研究

**暗能量理论**：
- 宇宙学常数：爱因斯坦的λ项
- 精质：动态标量场
- 修改引力：广义相对论的修正

**宇宙命运**：
- 大冻结：宇宙无限膨胀，温度趋近绝对零度
- 大撕裂：暗能量增强，撕裂一切结构
- 大挤压：暗能量减弱，宇宙重新坍缩

**科幻创作应用**：
- 暗能量引擎：宇宙级能源
- 空间折叠：操控暗能量弯曲空间
- 宇宙工程：改变宇宙命运""",
        "examples": [
            "《星际穿越》：暗能量维持人类生存",
            "《三体》：宇宙社会学与暗能量",
            "《最后的问题》：逆转熵增",
            "《银河系漫游指南》：宇宙的命运"
        ],
        "common_mistakes": [
            "错误：暗能量=暗物质（完全不同的概念）",
            "错误：暗能量可以被收集利用（理论不清楚）",
            "错误：暗能量是永久不变的（可能随时间演化）"
        ],
        "references": [
            "《暗能量》- Mario Livio",
            "暗能量巡天项目",
            "WMAP卫星数据",
            "ESO研究报告"
        ]
    }
}

# 科幻-化学增强数据（扩展版）
CHEMISTRY_ENHANCEMENTS = {
    "scifi-chemistry-004": {
        "content": """高分子是由大量重复单元组成的大分子化合物，是现代材料科学的基础。

**高分子类型**：
- 天然高分子：纤维素、蛋白质、DNA
- 合成塑料：聚乙烯、聚丙烯、PVC
- 合成纤维：尼龙、涤纶、腈纶
- 合成橡胶：丁苯橡胶、硅橡胶

**高分子特性**：
- 分子量：通常10,000-1,000,000
- 结构多样性：线性、支化、交联
- 相态变化：玻璃化转变、结晶
- 机械性能：强度、弹性、韧性

**智能高分子**：
- 形状记忆材料：温度触发恢复
- 自修复材料：损伤后自动修复
- 响应性材料：对环境变化敏感
- 导电高分子：塑料电子学

**科幻创作应用**：
- 超强纤维：太空电梯缆绳
- 自修复装甲：战斗损伤自动修复
- 智能服装：根据环境调节""",
        "examples": [
            "《星际穿越》：超强材料建造空间站",
            "《钢铁侠》：自修复战甲",
            "《火星救援》：高强度纤维",
            "《阿凡达》：生物工程材料"
        ],
        "common_mistakes": [
            "错误：塑料就是高分子（实际是高分子的一种）",
            "错误：高分子强度低（凯夫拉强度是钢的5倍）",
            "错误：自修复材料完美无缺（修复次数有限）"
        ],
        "references": [
            "《高分子化学》",
            "《材料科学基础》",
            "Nature Materials期刊",
            "智能材料研究进展"
        ]
    },
    "scifi-chemistry-005": {
        "content": """电化学研究电能与化学能的相互转化，是能源技术的核心。

**电化学基础**：
- 氧化还原反应：电子转移反应
- 电极过程：阳极氧化、阴极还原
- 电解质：离子导体
- 电动势：电池电压

**电池类型**：
- 锂离子电池：高能量密度，可充电
- 燃料电池：氢氧反应，零排放
- 固态电池：固态电解质，更安全
- 核电池：放射性衰变供能

**未来电池**：
- 锂空气电池：理论能量密度接近汽油
- 钠离子电池：资源丰富，成本低
- 多价离子电池：镁、铝离子电池
- 生物电池：酶催化发电

**科幻创作应用**：
- 超级电池：无限续航
- 核电池：千年寿命
- 反物质电池：终极能源""",
        "examples": [
            "《钢铁侠》：方舟反应堆",
            "《火星救援》：核电池RTG",
            "《星际迷航》：锂晶体电池",
            "《终结者》：核燃料电池"
        ],
        "common_mistakes": [
            "错误：电池可以无限能量（受限于化学储能）",
            "错误：核电池很危险（实际很安全）",
            "错误：燃料电池=氢气燃烧（实际是电化学反应）"
        ],
        "references": [
            "《电化学原理》",
            "《电池技术手册》",
            "Journal of Power Sources",
            "特斯拉电池技术白皮书"
        ]
    },
    "scifi-chemistry-008": {
        "content": """有机合成是构建有机分子的科学与艺术，是药物和材料研发的基础。

**合成方法**：
- 官能团转化：氧化、还原、取代
- 碳-碳键形成：偶联反应、加成反应
- 保护基策略：选择性反应
- 逆合成分析：从目标分子倒推

**药物合成**：
- 先导化合物：活性分子骨架
- 结构优化：提高活性、降低毒性
- 手性合成：单一对映体药物
- 绿色合成：环保高效路线

**前沿领域**：
- 自动化合成：AI辅助设计
- 生物合成：微生物生产药物
- 点击化学：模块化快速组装
- DNA编码化合物库：超大分子库筛选

**科幻创作应用**：
- 万能药物：治疗所有疾病
- 基因靶向药物：精准治疗
- 记忆药物：增强或删除记忆""",
        "examples": [
            "《永无止境》：NZT-48聪明药",
            "《生化危机》：T病毒解药合成",
            "《超体》：CPH4增强大脑",
            "《猩球崛起》：ALZ-113治疗阿尔茨海默"
        ],
        "common_mistakes": [
            "错误：万能药可以设计（疾病机理复杂）",
            "错误：合成可以创造任何分子（受限于反应可行性）",
            "错误：有机合成很简单（实际极具挑战性）"
        ],
        "references": [
            "《有机合成策略》",
            "《药物化学》",
            "Journal of Organic Chemistry",
            "诺贝尔化学奖有机合成领域"
        ]
    }
}

# 科幻-生物学增强数据（扩展版）
BIOLOGY_ENHANCEMENTS = {
    "scifi-biology-005": {
        "content": """人体微生物组是生活在我们体内外的微生物群落，影响健康与疾病。

**微生物组分布**：
- 肠道：100万亿细菌，最丰富的群落
- 皮肤：保护性屏障
- 口腔：消化起点
- 呼吸道：免疫防线

**微生物组功能**：
- 消化代谢：分解复杂碳水化合物
- 免疫调节：训练免疫系统
- 维生素合成：K族维生素、B族维生素
- 神经调节：肠-脑轴信号

**微生物组与疾病**：
- 肥胖：菌群组成影响能量吸收
- 抑郁：肠脑轴影响情绪
- 自身免疫病：菌群失衡
- 癌症：影响免疫治疗响应

**科幻创作应用**：
- 微生物疗法：工程化益生菌
- 异星适应：改造微生物适应外星
- 寄生控制：微生物操控宿主行为""",
        "examples": [
            "《异星觉醒》：外星微生物",
            "《普罗米修斯》：黑水改造DNA",
            "《湮灭》：微生物折射DNA",
            "《星际穿越》：植物枯萎病的微生物原因"
        ],
        "common_mistakes": [
            "错误：细菌都是有害的（实际大多数有益）",
            "错误：微生物组可以随意改造（生态系统复杂）",
            "错误：肠道菌群只影响消化（实际影响全身）"
        ],
        "references": [
            "《微生物组学》",
            "Human Microbiome Project",
            "Nature Microbiology期刊",
            "《脏脏更健康》"
        ]
    },
    "scifi-biology-008": {
        "content": """病毒是包裹在蛋白质外壳中的遗传物质，是生命边缘的存在。

**病毒特性**：
- 无细胞结构：仅DNA或RNA+蛋白质
- 必须寄生：依赖宿主复制
- 极小尺寸：20-300纳米
- 高变异率：快速进化

**病毒类型**：
- DNA病毒：疱疹、天花
- RNA病毒：流感、新冠、HIV
- 逆转录病毒：HIV整合基因组
- 噬菌体：感染细菌的病毒

**病毒传播**：
- 空气传播：飞沫、气溶胶
- 接触传播：体液、皮肤接触
- 媒介传播：蚊虫叮咬
- 垂直传播：母婴传播

**科幻创作应用**：
- 超级病毒：快速传播、高致死率
- 基因治疗病毒：病毒载体递送基因
- 进化病毒：赋予超能力的病毒
- 外星病毒：接触即感染""",
        "examples": [
            "《生化危机》：T病毒和G病毒",
            "《我是传奇》：KV病毒变异",
            "《传染病》：MEV-1病毒",
            "《王国》：丧尸病毒"
        ],
        "common_mistakes": [
            "错误：病毒是生命（科学界有争议）",
            "错误：病毒可以单独生存（必须依赖宿主）",
            "错误：抗生素治病毒（抗生素只杀菌）"
        ],
        "references": [
            "《病毒学原理》",
            "《逼近的瘟疫》",
            "WHO疫情报告",
            "CDC病毒数据库"
        ]
    },
    "scifi-biology-010": {
        "content": """生态系统是由生物群落与环境组成的统一整体，具有自我调节能力。

**生态系统组成**：
- 生产者：光合作用固定能量
- 消费者：异养生物获取能量
- 分解者：分解有机物回收营养
- 非生物环境：阳光、水、土壤

**能量流动**：
- 太阳能输入：能量来源
- 食物链传递：能量逐级递减
- 热量散失：能量最终耗散
- 10%定律：每级能量传递效率约10%

**物质循环**：
- 碳循环：光合作用与呼吸作用
- 氮循环：固氮、硝化、反硝化
- 水循环：蒸发、降水、径流
- 磷循环：岩石风化与沉积

**科幻创作应用**：
- 人造生态系统：太空殖民地设计
- 外星生态改造：地球化改造
- 生态系统崩溃：灾难性后果""",
        "examples": [
            "《火星救援》：火星种植生态系统",
            "《阿凡达》：潘多拉星球生态系统",
            "《后天》：气候变化生态崩溃",
            "《星际穿越》：地球生态恶化"
        ],
        "common_mistakes": [
            "错误：生态系统可以完美复制（实际极复杂）",
            "错误：外来物种无害（可能造成生态灾难）",
            "错误：生态系统永远平衡（实际动态变化）"
        ],
        "references": [
            "《生态学原理》",
            "《生物圈2号实验》",
            "Nature Ecology期刊",
            "IPCC气候变化报告"
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
            
            if 'content' in enhancement:
                kp['content'] = enhancement['content']
            if 'examples' in enhancement:
                kp['examples'] = enhancement['examples']
            if 'common_mistakes' in enhancement:
                kp['common_mistakes'] = enhancement['common_mistakes']
            if 'references' in enhancement:
                kp['references'] = enhancement['references']
            
            kp['updated_at'] = datetime.now().isoformat()
            updated_count += 1
    
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
    
    print(f"\n总计增强: {total_updated} 条知识点")


if __name__ == "__main__":
    main()
