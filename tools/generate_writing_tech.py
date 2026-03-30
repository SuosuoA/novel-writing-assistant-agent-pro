"""
重新生成写作技巧JSON文件（叙事、描写、修辞）
使用DeepSeek API生成高质量内容，确保JSON格式正确
"""
import json
import sys
from pathlib import Path
from openai import OpenAI

# 添加项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.api_key_encryption import APIKeyEncryption

# 初始化API
encryption = APIKeyEncryption(project_root)
api_key = encryption.get_api_key("DeepSeek")

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
    timeout=60.0
)

def generate_technique(tech_type: str, tech_name: str) -> dict:
    """生成单个写作技巧"""
    
    prompt = f"""生成一个高质量的写作技巧知识点。

**技巧类型**: {tech_type}
**技巧名称**: {tech_name}

**输出要求**：
1. 必须是有效的JSON格式
2. content字段不要包含中文引号"和"，使用英文单引号'代替
3. content字段要有详细说明（300字以上）

**JSON格式**:
```json
{{
  "knowledge_id": "writing_technique-{tech_type}-xxx",
  "category": "writing_technique",
  "domain": "{tech_type}",
  "title": "{tech_name}",
  "content": "详细说明（使用英文单引号'代替中文引号）",
  "keywords": ["关键词1", "关键词2"],
  "references": ["参考1", "参考2"],
  "difficulty": "basic",
  "tags": ["标签1", "标签2"],
  "metadata": {{
    "source": "literature",
    "confidence": 0.95,
    "language": "zh",
    "author": "后端架构师",
    "reference_type": "mandatory",
    "priority": 1.0
  }}
}}
```

直接输出JSON，不要其他内容。"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=2000
    )
    
    content = response.choices[0].message.content
    
    # 提取JSON
    json_start = content.find('{')
    json_end = content.rfind('}') + 1
    
    if json_start >= 0 and json_end > json_start:
        json_str = content[json_start:json_end]
        data = json.loads(json_str)
        return data
    
    return None


# 定义要生成的技巧
techniques_to_generate = {
    "narrative": ["第一人称叙事", "第三人称叙事", "多视角叙事", "倒叙", "插叙"],
    "description": ["心理描写", "环境描写", "动作描写", "对话描写", "细节描写"],
    "rhetoric": ["比喻", "拟人", "夸张", "排比", "对比"]
}

# 生成并保存
kb_dir = project_root / "data" / "knowledge"

for domain, techniques in techniques_to_generate.items():
    print(f"\n生成 {domain} 技巧...")
    
    results = []
    for i, tech_name in enumerate(techniques, 1):
        print(f"  [{i}/{len(techniques)}] {tech_name}...", end=" ")
        
        try:
            tech = generate_technique(domain, tech_name)
            if tech:
                tech['knowledge_id'] = f"writing_technique-{domain}-{i:03d}"
                results.append(tech)
                print("OK")
            else:
                print("FAIL")
        except Exception as e:
            print(f"ERROR: {e}")
    
    # 保存文件
    output_file = kb_dir / f"writing_technique_{domain}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"  保存到 {output_file.name} ({len(results)} items)")

print("\n完成！")
