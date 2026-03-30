"""
高质量知识库生成器
使用DeepSeek API生成符合11.14知识库样本标准的高质量知识点
"""

import json
import os
import sys
import time
from typing import List, Dict, Any
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from openai import OpenAI
import yaml

# 导入API Key解密模块
from core.api_key_encryption import APIKeyEncryption


class KnowledgeGenerator:
    """高质量知识库生成器"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """初始化生成器"""
        # 读取配置文件
        config_file = project_root / config_path
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 使用解密模块获取API Key
        encryption = APIKeyEncryption(project_root)
        provider = config.get('provider', 'DeepSeek')
        api_key = encryption.get_api_key(provider)
        
        if not api_key:
            raise ValueError(f"Failed to decrypt API Key for provider: {provider}")
        
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        self.model = config.get('model', 'deepseek-chat')
    
    def generate_knowledge_point(self, category: str, domain: str, topic: str) -> Dict[str, Any]:
        """生成单个高质量知识点"""
        
        prompt = f"""请严格按照以下标准生成一个高质量知识点。

**目标主题**: {topic}
**题材分类**: {category}
**领域分类**: {domain}

**质量标准**（参考11.14知识库样本.md）:
1. 详细内容（500+字）：包含起源/发展、地位与象征、能力体系、与其他概念的关联、演变历程
2. 经典案例应用（3-4个案例）：含具体引用、分析、应用方法
3. 写作应用建议（3大板块）：角色塑造建议、世界观构建应用、情节设计建议，每项有具体示例
4. 常见写作误区（5个）：每个误区有问题分析和改进建议
5. 参考文献（5个）：含作者、年份、内容说明
6. 相关概念（5个）：含ID、名称、关系说明

**JSON格式输出要求**:
```json
{{
  "knowledge_id": "{category}-{domain}-xxx-001",
  "category": "{category}",
  "domain": "{domain}",
  "title": "知识点标题",
  "content": "核心概念（1句话概括定位、来源、象征意义）",
  "detailed_content": "详细内容（500+字，包含起源发展、地位象征、能力体系、关联概念、演变历程）",
  "classic_cases": [
    {{
      "title": "案例标题",
      "source": "来源作品",
      "content": "案例详细描述（含原文引用）",
      "analysis": "案例分析"
    }}
  ],
  "writing_applications": {{
    "character_building": ["角色塑造建议1", "角色塑造建议2", "..."],
    "world_building": ["世界观构建建议1", "世界观构建建议2", "..."],
    "plot_design": ["情节设计建议1", "情节设计建议2", "..."]
  }},
  "common_mistakes": [
    {{
      "mistake": "误区描述",
      "problem": "问题分析",
      "suggestion": "改进建议"
    }}
  ],
  "references": [
    {{
      "title": "文献标题",
      "author": "作者",
      "year": "年份",
      "description": "内容说明"
    }}
  ],
  "related_concepts": [
    {{
      "id": "相关知识点ID",
      "name": "相关知识点名称",
      "relation": "关系说明"
    }}
  ],
  "keywords": ["关键词1", "关键词2", "...（10个）"],
  "references_list": ["参考文献1", "参考文献2", "参考文献3"],
  "difficulty": "basic/intermediate/advanced",
  "tags": ["标签1", "标签2", "标签3"],
  "metadata": {{
    "source": "知识来源",
    "confidence": 0.95,
    "reference_type": "implicit/explicit/constraint",
    "priority": 1.0
  }}
}}
```

请生成关于"{topic}"的高质量知识点，确保内容详实、具体、可操作，不要模板化废话。"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一位专业的科幻/玄幻小说知识库编辑，擅长创作高质量、详实、可操作的知识点内容。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4000
            )
            
            content = response.choices[0].message.content
            
            # 提取JSON部分
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            else:
                json_str = content.strip()
            
            knowledge = json.loads(json_str)
            return knowledge
            
        except Exception as e:
            print(f"生成失败: {e}")
            return None
    
    def batch_generate(self, topics: List[Dict[str, str]], output_dir: str):
        """批量生成知识点"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        results = []
        
        for i, topic_info in enumerate(topics):
            print(f"\n[{i+1}/{len(topics)}] 正在生成: {topic_info['topic']}")
            
            knowledge = self.generate_knowledge_point(
                category=topic_info['category'],
                domain=topic_info['domain'],
                topic=topic_info['topic']
            )
            
            if knowledge:
                results.append(knowledge)
                print(f"[OK] Generated: {knowledge['title']}")
                
                # 每生成5个知识点保存一次
                if len(results) % 5 == 0:
                    self._save_results(results, output_path / f"{topic_info['category']}_{topic_info['domain']}.json")
            else:
                print(f"[FAIL] Generation failed: {topic_info['topic']}")
            
            # 避免API限流
            time.sleep(1)
        
        # 最终保存
        if results:
            output_file = output_path / f"{topics[0]['category']}_{topics[0]['domain']}.json"
            self._save_results(results, output_file)
        
        return results
    
    def _save_results(self, results: List[Dict], output_file: Path):
        """保存结果到JSON文件"""
        # 如果文件已存在，读取并合并
        if output_file.exists():
            with open(output_file, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                if isinstance(existing, list):
                    results = existing + results
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"[SAVED] {len(results)} knowledge points saved to: {output_file}")


def main():
    """主函数"""
    generator = KnowledgeGenerator()
    
    # 定义要生成的知识点列表
    scifi_physics_topics = [
        {"category": "scifi", "domain": "physics", "topic": "牛顿运动定律"},
        {"category": "scifi", "domain": "physics", "topic": "狭义相对论"},
        {"category": "scifi", "domain": "physics", "topic": "广义相对论"},
        {"category": "scifi", "domain": "physics", "topic": "量子力学基础"},
        {"category": "scifi", "domain": "physics", "topic": "量子纠缠"},
        {"category": "scifi", "domain": "physics", "topic": "电磁波谱"},
        {"category": "scifi", "domain": "physics", "topic": "核裂变与核聚变"},
        {"category": "scifi", "domain": "physics", "topic": "暗物质与暗能量"},
        {"category": "scifi", "domain": "physics", "topic": "黑洞物理学"},
        {"category": "scifi", "domain": "physics", "topic": "热力学定律"},
    ]
    
    # 生成scifi/physics知识点
    print("=" * 60)
    print("开始生成scifi/physics知识点...")
    print("=" * 60)
    
    results = generator.batch_generate(
        topics=scifi_physics_topics,
        output_dir="data/knowledge/scifi"
    )
    
    print(f"\n[COMPLETE] Total {len(results)} high-quality knowledge points generated")


if __name__ == "__main__":
    main()
