#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识点质量增强工具
自动为不合格的知识点补充缺失字段
"""

import json
import yaml
from pathlib import Path
from typing import Dict, List
from openai import OpenAI

class KnowledgeEnhancer:
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
        print(f"     Model: {self.model}")
    
    def enhance_knowledge_point(self, kp: Dict, category: str, domain: str) -> Dict:
        """增强单个知识点，补充缺失字段"""
        
        # 检查哪些字段需要补充
        missing_fields = []
        required_fields = {
            'explanation': (30, 50),
            'classic_cases': (100, 200),
            'examples': (3, 5),  # 作品数量
            'common_mistakes': (2, 3),  # 误区数量
            'references': (2, 3)  # 参考文献数量
        }
        
        for field, (min_val, max_val) in required_fields.items():
            if field not in kp or kp[field] is None or len(str(kp[field]).strip()) == 0:
                missing_fields.append(field)
        
        # 检查content长度
        content_len = len(kp.get('content', ''))
        if content_len < 150:
            missing_fields.append('content_length')
        
        # 如果所有字段都合格，直接返回
        if not missing_fields:
            return kp
        
        # 使用AI补充缺失字段
        prompt = self._build_enhancement_prompt(kp, missing_fields, category, domain)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是专业的知识库内容编辑，擅长为小说创作提供专业知识支持。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # 解析AI返回的JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                enhancements = json.loads(json_match.group(0))
                
                # 合并补充字段
                enhanced_kp = kp.copy()
                for field, value in enhancements.items():
                    if field in missing_fields or field == 'content':
                        enhanced_kp[field] = value
                
                return enhanced_kp
            else:
                print(f"[WARN] Failed to parse AI response for {kp.get('title', 'Unknown')}")
                return kp
                
        except Exception as e:
            print(f"[ERROR] Failed to enhance {kp.get('title', 'Unknown')}: {e}")
            return kp
    
    def _build_enhancement_prompt(self, kp: Dict, missing_fields: List[str], category: str, domain: str) -> str:
        """构建补充提示词"""
        title = kp.get('title', 'Unknown')
        content = kp.get('content', '')
        keywords = kp.get('keywords', [])
        
        prompt = f"""请为以下知识点补充缺失的字段。

知识点标题：{title}
知识点类别：{category}/{domain}
当前内容：{content}
关键词：{', '.join(keywords) if keywords else '无'}

需要补充的字段：{', '.join(missing_fields)}

请严格按照以下要求补充：

1. **explanation** (30-50字)：简要解释这个概念的核心含义
2. **content** (≥150字)：如果当前内容不足150字，请扩写到至少150字，详细阐述定义、原理、实例
3. **classic_cases** (≥100字)：具体说明这个概念在小说创作中的应用案例，包含情节和效果
4. **examples** (3-5部作品)：列出具体的相关作品名称
5. **common_mistakes** (2-3个误区)：列出常见写作误区和正确做法
6. **references** (2-3个来源)：列出权威参考文献

请以JSON格式返回补充内容，格式如下：
{{
    "explanation": "简要解释...",
    "content": "详细内容（≥150字）...",
    "classic_cases": "经典案例应用（≥100字）...",
    "examples": ["作品1", "作品2", "作品3"],
    "common_mistakes": ["误区1：...", "误区2：..."],
    "references": ["参考文献1", "参考文献2"]
}}

注意：
- 内容必须充实具体，不要使用套话
- classic_cases必须包含具体的情节和效果分析
- examples必须列出具体的作品名称
- common_mistakes必须明确指出错误和正确做法
- references必须列出权威来源
"""
        return prompt
    
    def enhance_file(self, file_path: Path, category: str, domain: str):
        """增强单个文件中的知识点（无限制，增强所有不合格知识点）"""
        print(f"\n[Processing] {category}/{domain}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if 'knowledge_points' not in data:
                print(f"[WARN] Missing knowledge_points field")
                return
            
            knowledge_points = data['knowledge_points']
            enhanced_count = 0
            
            for i, kp in enumerate(knowledge_points):
                
                # 检查是否需要增强
                content_len = len(kp.get('content') or '')
                cases_len = len(kp.get('classic_cases') or '')
                missing_fields = [
                    field for field in ['explanation', 'classic_cases', 'examples', 'common_mistakes', 'references']
                    if field not in kp or kp[field] is None
                ]
                
                if content_len < 150 or cases_len < 100 or missing_fields:
                    print(f"  Enhancing [{i+1}/{len(knowledge_points)}]: {kp.get('title', 'Unknown')[:30]}...")
                    enhanced_kp = self.enhance_knowledge_point(kp, category, domain)
                    knowledge_points[i] = enhanced_kp
                    enhanced_count += 1
            
            # 保存增强后的文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"[OK] Enhanced {enhanced_count} knowledge points in {file_path.name}")
            
        except Exception as e:
            print(f"[ERROR] Failed to enhance file {file_path}: {e}")
    
    def enhance_all(self, knowledge_base_path: str):
        """增强所有知识库文件（无限制）"""
        knowledge_base_path = Path(knowledge_base_path)
        
        print("=" * 80)
        print("知识库质量增强")
        print("=" * 80)
        
        # 遍历所有类别
        for category_dir in knowledge_base_path.iterdir():
            if not category_dir.is_dir():
                continue
            
            category = category_dir.name
            
            # 遍历该类别下的所有领域文件
            for domain_file in category_dir.glob("*.json"):
                domain = domain_file.stem
                self.enhance_file(domain_file, category, domain)
        
        print("\n" + "=" * 80)
        print("知识库增强完成")
        print("=" * 80)


if __name__ == "__main__":
    config_path = r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\config.yaml"
    knowledge_base_path = r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\data\knowledge"
    
    enhancer = KnowledgeEnhancer(config_path)
    enhancer.enhance_all(knowledge_base_path)
