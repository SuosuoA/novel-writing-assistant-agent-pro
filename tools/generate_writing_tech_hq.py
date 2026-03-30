#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
高质量写作技巧知识库生成器
按V5.3标准：每项技巧300-500字详细说明
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api_key_encryption import APIKeyEncryption
from openai import OpenAI


def init_api():
    """初始化API"""
    import yaml
    from pathlib import Path
    
    # 直接从config.yaml读取API Key
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # API Key在根级别
    api_key = config.get('api_key')
    if not api_key:
        raise ValueError("config.yaml中未找到api_key字段")
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )
    return client


def generate_technique_detail(client, technique_name: str, category: str) -> Dict:
    """生成单个技巧的详细知识点"""
    
    prompt = f"""你是一位资深文学创作教授。请为写作技巧"{technique_name}"（属于{category}分类）撰写一份详细的知识点说明。

要求：
1. 总字数：300-500字
2. 内容结构：
   - 核心定义（50-80字）：该技巧的本质定义与核心原理
   - 使用方法（100-150字）：具体操作步骤、技巧要点
   - 典型示例（80-120字）：举1-2个经典文学案例或原创示例
   - 注意事项（50-80字）：常见错误、使用限制
   - 适用场景（50-80字）：最适合的题材、风格、段落类型

输出格式（纯文本，不要markdown标记）：
【核心定义】...
【使用方法】...
【典型示例】...
【注意事项】...
【适用场景】...

技巧名称：{technique_name}
分类：{category}"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是资深文学创作教授，擅长讲解写作技巧。输出纯文本，不要markdown格式。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=800
        )
        
        content = response.choices[0].message.content.strip()
        
        return {
            "name": technique_name,
            "category": category,
            "content": content,
            "tags": [category, technique_name, "写作技巧"],
            "difficulty": "intermediate",
            "importance": "high"
        }
        
    except Exception as e:
        print(f"  ⚠️ 生成失败 {technique_name}: {e}")
        return None


def main():
    """主函数"""
    print("=" * 60)
    print("高质量写作技巧知识库生成器 V5.3")
    print("=" * 60)
    
    # 初始化API
    print("\n[1/4] 初始化API...")
    client = init_api()
    print("✅ API连接成功")
    
    # 定义所有技巧（按12.2文档规范）
    techniques = {
        "叙事技巧": [
            "第一人称叙事", "第三人称叙事", "多视角叙事", "倒叙", "插叙",
            "平行叙事", "螺旋叙事", "多线叙事", "意识流"
        ],
        "描写技巧": [
            "心理描写", "环境描写", "动作描写", "对话描写", "细节描写",
            "象征手法", "通感置换", "留白手法", "侧面烘托"
        ],
        "修辞技巧": [
            "比喻", "拟人", "夸张", "排比", "对比", "反讽", "对偶", "顶针",
            "否定句", "托心句", "双关", "通感"
        ],
        "结构技巧": [
            "悬念设置", "伏笔铺垫", "高潮设计", "节奏控制", "章节衔接",
            "主题升华", "反高潮设计", "时空折叠", "启承转合", "首尾呼应"
        ],
        "特殊句式": [
            "列锦句式", "倒装句式", "紧缩句式", "排比句式", "对偶句式",
            "反复句式", "设问句式", "反问句式", "感叹句式", "祈使句式",
            "省略句式", "独词句式", "意象组合"
        ],
        "高级技法": [
            "解剖句", "涟漪句", "幽灵句", "虫洞句", "叠影句", "羽毛句",
            "蒙太奇", "闪回闪前", "视角漂移", "叙事陷阱", "镜像对照", "元叙事"
        ]
    }
    
    # 统计
    total_techniques = sum(len(v) for v in techniques.values())
    print(f"\n[2/4] 待生成技巧总数: {total_techniques}项")
    
    # 生成每个分类的JSON文件
    output_dir = Path(__file__).parent.parent / "data" / "knowledge"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    fail_count = 0
    
    for category, tech_list in techniques.items():
        print(f"\n[3/4] 生成分类: {category} ({len(tech_list)}项)")
        
        knowledge_points = []
        
        for i, tech_name in enumerate(tech_list, 1):
            print(f"  [{i}/{len(tech_list)}] 生成: {tech_name}...", end="", flush=True)
            
            # 生成知识点
            kp = generate_technique_detail(client, tech_name, category)
            
            if kp:
                knowledge_points.append(kp)
                success_count += 1
                print(" ✅")
            else:
                fail_count += 1
                print(" ❌")
            
            # 避免API限流
            time.sleep(0.5)
        
        # 保存该分类的JSON文件
        filename = f"writing_technique_{category.replace('技巧', '').replace('句式', '_sentence').replace('技法', '_advanced')}.json"
        # 特殊映射
        filename_map = {
            "叙事技巧": "writing_technique_narrative.json",
            "描写技巧": "writing_technique_description.json",
            "修辞技巧": "writing_technique_rhetoric.json",
            "结构技巧": "writing_technique_structure.json",
            "特殊句式": "writing_technique_special_sentence.json",
            "高级技法": "writing_technique_advanced.json"
        }
        filename = filename_map.get(category, f"writing_technique_{category}.json")
        
        output_file = output_dir / filename
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(knowledge_points, f, ensure_ascii=False, indent=2)
        
        print(f"  💾 已保存: {output_file.name} ({len(knowledge_points)}条)")
    
    # 最终报告
    print("\n" + "=" * 60)
    print(f"[4/4] 生成完成")
    print(f"✅ 成功: {success_count}条")
    print(f"❌ 失败: {fail_count}条")
    print(f"📊 成功率: {success_count/total_techniques*100:.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
