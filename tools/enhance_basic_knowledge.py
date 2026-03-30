#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库全面增强脚本 - 批量版本
为基本常识知识库添加详细内容
"""

import json
from pathlib import Path
from datetime import datetime

# 基本常识知识库增强
BASIC_KNOWLEDGE_ENHANCEMENTS = {
    "general-economics-001": {
        "content": """重商主义是16-18世纪欧洲主流经济思想，强调国家通过贸易顺差积累财富。

**核心观点**：
- 金银是财富的唯一形式
- 国家应干预经济，促进出口、限制进口
- 贸易顺差是积累财富的关键
- 殖民地是原材料来源和市场

**历史背景**：
- 地理大发现带来全球贸易
- 民族国家形成，需要财政支持
- 贵金属流入欧洲引发通胀

**代表人物**：
- 托马斯·孟：英国重商主义代表
- 让-巴普蒂斯特·柯尔贝尔：法国财政大臣

**历史影响**：
- 推动了殖民扩张
- 建立了关税壁垒
- 为工业革命积累资本

**小说创作应用**：
- 历史小说：大航海时代的经济博弈
- 架空历史：重商主义帝国的兴衰
- 经济题材：贸易战的古代版本""",
        "examples": [
            "《白银资本》：大航海时代的经济史",
            "《大国的兴衰》：经济霸权的转移",
            "《香料之路》：重商主义时代的贸易",
            "《国富论》批判重商主义"
        ],
        "common_mistakes": [
            "误区：重商主义只是贪婪（实际有历史合理性）",
            "误区：贸易顺差永远有利（可能导致资源错配）",
            "误区：重商主义已经消失（新重商主义依然存在）"
        ],
        "references": [
            "《国富论》- 亚当·斯密",
            "《经济思想史》",
            "《大国的兴衰》- 保罗·肯尼迪",
            "Cambridge Economic History"
        ]
    },
    "general-economics-002": {
        "content": """重农学派是18世纪法国经济思想，认为农业是财富的唯一来源。

**核心观点**：
- 土地是财富的唯一来源
- 农业是生产性劳动
- 制造业只是转换农产品
- 自由放任，反对国家干预

**代表人物**：
- 弗朗索瓦·魁奈：学派创始人，《经济表》作者
- 安妮·罗伯特·雅克·图尔哥

**理论贡献**：
- 提出"自然秩序"概念
- 创立宏观经济分析框架
- 为古典经济学奠基

**历史意义**：
- 最早系统经济理论之一
- 对亚当·斯密有重要影响
- 推动法国经济改革

**小说创作应用**：
- 法国启蒙时代的历史背景
- 经济思想的演变过程
- 农业社会的经济逻辑""",
        "examples": [
            "《魁奈经济著作选》：重农学派代表作",
            "《经济表》：最早的宏观模型",
            "《国富论》：吸收重农思想",
            "法国启蒙运动小说"
        ],
        "common_mistakes": [
            "误区：重农学派只关心农业（实际是经济理论先驱）",
            "误区：重农主义落后（实际为现代经济学奠基）",
            "误区：忽视工业（当时工业确实不如农业重要）"
        ],
        "references": [
            "《魁奈经济著作选》",
            "《经济思想史》- 熊彼特",
            "《法国经济思想史》",
            "OECD农业经济报告"
        ]
    },
    "general-logic-mistake-001": {
        "content": """人身攻击谬误（Ad Hominem）是通过攻击对方人身而非观点来进行论证的错误。

**谬误形式**：
- 攻击对方品格而非论点
- 攻击对方动机而非论据
- 攻击对方身份而非论证

**典型例子**：
- "你又不是专家，凭什么发表意见？"
- "他是个骗子，他的理论不可信。"
- "你这么说是因为你有利益关系。"

**为什么是谬误**：
- 论证的真假与论证者无关
- 坏人也可以提出好论证
- 分散注意力，不解决实质问题

**识别方法**：
- 问：攻击的是人还是观点？
- 问：这个攻击与论证有什么关系？
- 问：如果换一个人说同样的话，论证是否成立？

**小说创作应用**：
- 辩论场景：反派使用谬误欺骗观众
- 法庭戏：律师揭露对方的人身攻击
- 政治小说：选举中的抹黑战术""",
        "examples": [
            "苏格拉底的辩护：被指控者的人身攻击",
            "《十二怒汉》：陪审员对被告的偏见",
            "政治辩论：选举中的人身攻击广告",
            "网络争论：喷子的人身攻击"
        ],
        "common_mistakes": [
            "误区：任何对人的批评都是谬误（如果与论证相关就不是）",
            "误区：指出对方利益冲突是谬误（有时确实影响可信度）",
            "误区：专家意见无关紧要（专业权威有价值）"
        ],
        "references": [
            "《逻辑学导论》- 柯匹",
            "《思考，快与慢》- 卡尼曼",
            "斯坦福哲学百科",
            "Critical Thinking教材"
        ]
    },
    "general-logic-mistake-002": {
        "content": """稻草人谬误是通过歪曲对方观点然后攻击这个歪曲版本来"反驳"的错误。

**谬误形式**：
- 极端化对方观点
- 选择性引用，断章取义
- 攻击对方从未持有的观点

**典型例子**：
- 原观点："我们应该减少军费。" 
  稻草人："你想让我们毫无防备，任人宰割！"
- 原观点："动物有权利。"
  稻草人："你认为动物和人完全平等？"

**为什么是谬误**：
- 攻击的不是对方的真实观点
- 制造假靶子来显示自己正确
- 没有进行真正的对话

**识别方法**：
- 问：对方真的说过这样的话吗？
- 问：这是对方观点的忠实呈现吗？
- 问：我是否在攻击一个更容易反驳的版本？

**小说创作应用**：
- 政治小说：媒体歪曲政客言论
- 辩论场景：一方制造稻草人
- 网络冲突：键盘侠的误解""",
        "examples": [
            "政治辩论：候选人的观点被媒体歪曲",
            "《1984》：真理部制造稻草人敌人",
            "社交媒体：网络争论中的误解",
            "学术争论：引用错误构建靶子"
        ],
        "common_mistakes": [
            "误区：任何简化都是稻草人（可以合理概括）",
            "误区：指出稻草人就赢了（还需说明真实观点）",
            "误区：对方一定没说过（可能是隐含观点）"
        ],
        "references": [
            "《逻辑学导论》- 柯匹",
            "《论证的艺术》",
            "YouAreNotSoSmart博客",
            "维基百科稻草人谬误"
        ]
    }
}

def enhance_basic_knowledge():
    """增强基本常识知识库"""
    base_path = Path(__file__).parent.parent / "data" / "knowledge"
    file_path = base_path / "general" / "basic_knowledge.json"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        knowledge_points = json.load(f)
    
    updated_count = 0
    for kp in knowledge_points:
        kp_id = kp.get('knowledge_id', '')
        if kp_id in BASIC_KNOWLEDGE_ENHANCEMENTS:
            enhancement = BASIC_KNOWLEDGE_ENHANCEMENTS[kp_id]
            
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
    
    print(f"基本常识知识增强: {updated_count} 条")
    return updated_count

if __name__ == "__main__":
    enhance_basic_knowledge()
