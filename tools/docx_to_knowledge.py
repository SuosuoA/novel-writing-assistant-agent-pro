#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Docx内容转知识点工具
将docx文件中的知识内容转换为知识点格式
"""

import json
import re
import yaml
from pathlib import Path
from typing import Dict, List
from openai import OpenAI

class DocxToKnowledgeConverter:
    def __init__(self, config_path: str):
        # 读取配置
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 初始化DeepSeek客户端
        self.client = OpenAI(
            api_key=config.get('api_key', ''),
            base_url=config.get('base_url', 'https://api.deepseek.com')
        )
        self.model = config.get('model', 'deepseek-chat')
        
        print(f"[OK] Initialized DeepSeek client")
    
    def extract_knowledge_sections(self, docx_text: str) -> List[Dict]:
        """从docx文本中提取知识章节"""
        sections = []
        
        # 按章节分割（基于标题格式）
        current_section = None
        lines = docx_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检测章节标题（包含"一、""二、"等编号）
            if re.match(r'^[一二三四五六七八九十]+、', line):
                if current_section:
                    sections.append(current_section)
                current_section = {
                    'title': line,
                    'content': []
                }
            elif current_section:
                current_section['content'].append(line)
        
        # 添加最后一个章节
        if current_section:
            sections.append(current_section)
        
        return sections
    
    def convert_section_to_knowledge_points(self, section: Dict, category: str) -> List[Dict]:
        """使用AI将章节内容转换为知识点格式"""
        title = section['title']
        content_text = '\n'.join(section['content'])
        
        prompt = f"""请将以下知识内容转换为知识点格式。

章节标题：{title}
章节内容：
{content_text[:2000]}

请提取其中的核心知识点，并按照以下JSON格式输出：
{{
    "knowledge_points": [
        {{
            "title": "知识点标题",
            "explanation": "简要解释（30-50字）",
            "content": "详细内容（≥150字）",
            "classic_cases": "经典案例应用（≥100字，说明在小说创作中的应用）",
            "examples": ["作品1", "作品2", "作品3"],
            "common_mistakes": ["误区1：...", "误区2：..."],
            "references": ["参考文献1", "参考文献2"],
            "keywords": ["关键词1", "关键词2", "关键词3"]
        }}
    ]
}}

要求：
1. 提取3-5个核心知识点
2. 每个知识点必须包含所有字段
3. content字段必须≥150字
4. classic_cases字段必须≥100字，且包含具体的小说创作应用案例
5. examples字段列出3-5部相关作品
6. common_mistakes字段列出2-3个常见写作误区
7. references字段列出2-3个权威来源
8. keywords字段列出3-5个关键词
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是专业的知识库编辑，擅长将复杂知识转换为结构化的知识点格式。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=3000
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # 解析JSON
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result = json.loads(json_match.group(0))
                return result.get('knowledge_points', [])
            else:
                print(f"[WARN] Failed to parse AI response for section: {title}")
                return []
                
        except Exception as e:
            print(f"[ERROR] Failed to convert section {title}: {e}")
            return []
    
    def convert_docx_to_knowledge(self, docx_text: str, output_file: str, category: str = "general"):
        """将docx内容转换为知识点并保存"""
        print(f"\n[Processing] Converting docx content to knowledge points...")
        
        # 提取章节
        sections = self.extract_knowledge_sections(docx_text)
        print(f"[OK] Extracted {len(sections)} sections")
        
        # 转换每个章节为知识点
        all_knowledge_points = []
        
        for i, section in enumerate(sections, 1):
            print(f"  Processing section [{i}/{len(sections)}]: {section['title'][:30]}...")
            
            knowledge_points = self.convert_section_to_knowledge_points(section, category)
            all_knowledge_points.extend(knowledge_points)
        
        # 保存结果
        output_data = {
            "category": category,
            "domain": "basic_knowledge",
            "description": "从基本常识.docx提取的知识点",
            "knowledge_points": all_knowledge_points
        }
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n[SUCCESS] Saved {len(all_knowledge_points)} knowledge points to {output_file}")
        return len(all_knowledge_points)


if __name__ == "__main__":
    config_path = r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\config.yaml"
    docx_text_path = r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\tests\basic_knowledge.txt"
    output_file = r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\data\knowledge\general\basic_knowledge.json"
    
    # 读取docx文本
    with open(docx_text_path, 'r', encoding='utf-8') as f:
        docx_text = f.read()
    
    converter = DocxToKnowledgeConverter(config_path)
    converter.convert_docx_to_knowledge(docx_text, output_file, category="general")
