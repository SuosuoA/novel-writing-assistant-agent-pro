#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
写作技巧知识库生成器
按照最高标准生成65项写作技巧的完整知识点
"""

import os
import sys
import json
import time
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

os.environ['DEV_MODE'] = '1'

from core.knowledge_generator import KnowledgeGeneratorV4, KnowledgeGenerateRequest

# 定义所有写作技巧（按领域）
TECHNIQUES = {
    'narrative': [
        '第一人称叙事', '第三人称叙事', '多视角叙事', '倒叙', '插叙',
        '平行叙事', '螺旋叙事', '多线叙事', '意识流'
    ],
    'description': [
        '心理描写', '环境描写', '动作描写', '对话描写', '细节描写',
        '象征手法', '通感置换', '留白手法', '侧面烘托'
    ],
    'rhetoric': [
        '比喻', '拟人', '夸张', '排比', '对比', '反讽', '对偶', '顶针',
        '否定句', '托心句', '双关', '通感'
    ],
    'structure': [
        '悬念设置', '伏笔铺垫', '高潮设计', '节奏控制', '章节衔接',
        '主题升华', '反高潮设计', '时空折叠', '启承转合', '首尾呼应'
    ],
    'special_sentence': [
        '列锦句式', '倒装句式', '紧缩句式', '排比句式', '对偶句式',
        '反复句式', '设问句式', '反问句式', '感叹句式', '祈使句式',
        '省略句式', '独词句式', '意象组合'
    ],
    'advanced': [
        '解剖句', '涟漪句', '幽灵句', '虫洞句', '叠影句', '羽毛句',
        '蒙太奇', '闪回闪前', '视角漂移', '叙事陷阱', '镜像对照', '元叙事'
    ]
}

# 技巧简短说明（用于生成提示）
TECHNIQUE_HINTS = {
    'narrative': {
        '第一人称叙事': '使用"我"作为叙述主体，增强代入感和心理亲密性',
        '第三人称叙事': '使用"他/她"叙述，视角灵活，可全知或有限',
        '多视角叙事': '多个角色的视角交替叙述，呈现多元真相',
        '倒叙': '先展示结果，再回溯过程，制造悬念',
        '插叙': '在叙述中插入回忆或背景，丰富信息层',
        '平行叙事': '多条线索同时推进，最后交汇',
        '螺旋叙事': '同一场景或情感反复回归、层层深入',
        '多线叙事': '多条情节线并行推进，最后交汇',
        '意识流': '内心意识连续流动的叙事，打破时空限制'
    },
    'description': {
        '心理描写': '刻画人物内心活动和情感变化',
        '环境描写': '描绘场景氛围、自然或社会环境',
        '动作描写': '通过动作展现人物性格和情感',
        '对话描写': '通过对话推动情节、展现人物',
        '细节描写': '捕捉细微之处，增强真实感',
        '象征手法': '用具体事物暗示抽象意义',
        '通感置换': '感官互通（视觉→听觉、触觉→视觉等）',
        '留白手法': '刻意省略部分细节，留给读者想象空间',
        '侧面烘托': '通过周围事物间接表现主体'
    },
    'rhetoric': {
        '比喻': '用具体事物说明抽象概念，分明喻、暗喻、借喻',
        '拟人': '赋予非人事物以人的特征',
        '夸张': '故意放大或缩小事物的特征',
        '排比': '三个以上结构相似的句子排列',
        '对比': '将相反的事物并列对照',
        '反讽': '说反话，言在此而意在彼',
        '对偶': '字数相等、结构对称的句子',
        '顶针': '前句结尾作后句开头',
        '否定句': '用否定形式表达肯定意义，增强语气',
        '托心句': '点明主旨的核心句，承载情感重心',
        '双关': '一语双关，表里两层含义',
        '通感': '感官互通的修辞手法'
    },
    'structure': {
        '悬念设置': '在情节中埋下未解之谜，激发阅读兴趣',
        '伏笔铺垫': '提前暗示后续情节的关键细节',
        '高潮设计': '情节发展的顶点，冲突最激烈的时刻',
        '节奏控制': '快慢张弛的叙事速度把控',
        '章节衔接': '章节之间的过渡与呼应',
        '主题升华': '从故事层面上升到哲学或情感层面',
        '反高潮设计': '铺垫后故意"泄气"，制造意外效果',
        '时空折叠': '过去/现在/未来交错并置',
        '启承转合': '开头、承接、转折、结尾的经典结构',
        '首尾呼应': '开头与结尾相互照应，形成闭环'
    },
    'special_sentence': {
        '列锦句式': '纯名词组合，意象叠加，如"鸡声茅店月，人迹板桥霜"',
        '倒装句式': '语序倒装，突出强调，如"香稻啄余鹦鹉粒"',
        '紧缩句式': '复句紧缩为单句形式，如"天高地厚"',
        '排比句式': '三个以上结构相似的句子',
        '对偶句式': '字数相等、结构对称',
        '反复句式': '相同词语或句子反复出现',
        '设问句式': '自问自答',
        '反问句式': '只问不答，答案在问句中',
        '感叹句式': '表达强烈感情',
        '祈使句式': '表示请求或命令',
        '省略句式': '省略某些成分',
        '独词句式': '单个词成句，如"火！"',
        '意象组合': '多个意象并置营造意境'
    },
    'advanced': {
        '解剖句': '将整体拆解为细节，逐层剖析',
        '涟漪句': '句意层层扩散，如涟漪般影响全文',
        '幽灵句': '悬而未决的句子，在读者心中萦绕不去',
        '虫洞句': '意外跳跃连接两个远距离意象',
        '叠影句': '同一意象反复出现，叠加情感厚度',
        '羽毛句': '轻盈一笔，却承载沉重情感',
        '蒙太奇': '镜头剪辑式跳跃组合',
        '闪回闪前': '快速闪回过去或预示未来',
        '视角漂移': '叙述视角在文中悄然转换',
        '叙事陷阱': '误导读者后揭示真相',
        '镜像对照': '人物/事件相互映照',
        '元叙事': '作者直接介入叙事，打破第四面墙'
    }
}


def generate_domain_techniques(gen: KnowledgeGeneratorV4, domain: str, techniques: list, hints: dict):
    """为一个领域的技巧生成知识点"""
    
    domain_names = {
        'narrative': '叙事技巧',
        'description': '描写技巧',
        'rhetoric': '修辞技巧',
        'structure': '结构技巧',
        'special_sentence': '特殊句式',
        'advanced': '高级技法'
    }
    
    print(f"\n{'='*60}")
    print(f"开始生成【{domain_names[domain]}】领域的 {len(techniques)} 项技巧")
    print(f"{'='*60}")
    
    # 为每个技巧生成知识点
    for i, tech in enumerate(techniques, 1):
        hint = hints.get(tech, '')
        print(f"\n[{i}/{len(techniques)}] 正在生成：{tech}")
        print(f"  说明：{hint}")
        
        # 构建生成提示
        focus_hint = f"{tech}：{hint}"
        
        request = KnowledgeGenerateRequest(
            category='writing_technique',
            domain=domain,
            count=1,
            focus_hint=focus_hint,
            quality_level='high'
        )
        
        try:
            result = gen.generate_knowledge(request)
            if result.success and result.generated > 0:
                print(f"  ✓ 生成成功，保存 {result.saved} 条")
            else:
                print(f"  ✗ 生成失败：{result.errors}")
        except Exception as e:
            print(f"  ✗ 异常：{e}")
        
        # 每生成一条后短暂休息，避免API限流
        time.sleep(1)


def main():
    """主函数"""
    workspace = Path(os.getcwd())
    gen = KnowledgeGeneratorV4(workspace_root=workspace)
    
    print("="*60)
    print("写作技巧知识库生成器")
    print("目标：生成65项写作技巧的完整知识点")
    print("="*60)
    
    # 统计
    total = sum(len(t) for t in TECHNIQUES.values())
    print(f"\n总计：{total} 项技巧待生成")
    
    # 按领域逐一生成
    for domain, techniques in TECHNIQUES.items():
        hints = TECHNIQUE_HINTS.get(domain, {})
        generate_domain_techniques(gen, domain, techniques, hints)
    
    print("\n" + "="*60)
    print("生成完成！")
    print("="*60)


if __name__ == '__main__':
    main()
