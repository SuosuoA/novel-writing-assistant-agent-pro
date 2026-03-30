#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库质量审查工具
检查已保存的知识点是否符合质量标准：
- content字段 ≥ 150字
- classic_cases字段 ≥ 100字
- 所有字段非空且非套话
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

class KnowledgeQualityChecker:
    def __init__(self, knowledge_base_path: str):
        self.knowledge_base_path = Path(knowledge_base_path)
        self.issues = []
        self.stats = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'categories': {}
        }
    
    def check_knowledge_point(self, kp: Dict, category: str, domain: str, index: int) -> Tuple[bool, List[str]]:
        """检查单个知识点质量"""
        issues = []
        
        # 检查必需字段
        required_fields = ['title', 'explanation', 'content', 'classic_cases', 
                          'examples', 'common_mistakes', 'references', 'keywords']
        
        for field in required_fields:
            if field not in kp or kp[field] is None:
                issues.append(f"字段缺失: {field}")
            elif isinstance(kp[field], str) and len(kp[field].strip()) == 0:
                issues.append(f"字段为空: {field}")
        
        # 检查content字段长度
        if 'content' in kp and kp['content']:
            content_len = len(kp['content'])
            if content_len < 150:
                issues.append(f"content字段长度不足: {content_len}字 (要求≥150字)")
        
        # 检查classic_cases字段长度
        if 'classic_cases' in kp and kp['classic_cases']:
            cases_len = len(kp['classic_cases'])
            if cases_len < 100:
                issues.append(f"classic_cases字段长度不足: {cases_len}字 (要求≥100字)")
        
        # 检查是否为套话（简单检测）
        content = kp.get('content', '')
        if any(phrase in content for phrase in ['这是一个', '这是关于', '这是一个重要的概念']):
            issues.append("content字段包含套话开头")
        
        passed = len(issues) == 0
        return passed, issues
    
    def check_file(self, file_path: Path, category: str, domain: str):
        """检查单个JSON文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if 'knowledge_points' not in data:
                print(f"[WARN] {file_path.name}: missing knowledge_points field")
                return
            
            knowledge_points = data['knowledge_points']
            file_passed = 0
            file_failed = 0
            
            for i, kp in enumerate(knowledge_points):
                self.stats['total'] += 1
                passed, issues = self.check_knowledge_point(kp, category, domain, i)
                
                if passed:
                    self.stats['passed'] += 1
                    file_passed += 1
                else:
                    self.stats['failed'] += 1
                    file_failed += 1
                    self.issues.append({
                        'file': str(file_path),
                        'category': category,
                        'domain': domain,
                        'index': i,
                        'title': kp.get('title', 'Unknown'),
                        'issues': issues
                    })
            
            print(f"[OK] {category}/{domain}: {file_passed} passed / {file_failed} failed / total {len(knowledge_points)}")
            
        except Exception as e:
            print(f"[ERROR] Failed to check file {file_path}: {e}")
    
    def check_all(self):
        """检查所有知识库文件"""
        print("=" * 80)
        print("知识库质量审查")
        print("=" * 80)
        
        # 遍历所有类别
        for category_dir in self.knowledge_base_path.iterdir():
            if not category_dir.is_dir():
                continue
            
            category = category_dir.name
            print(f"\n检查类别: {category}")
            print("-" * 80)
            
            if category not in self.stats['categories']:
                self.stats['categories'][category] = {
                    'total': 0, 'passed': 0, 'failed': 0, 'domains': {}
                }
            
            # 遍历该类别下的所有领域文件
            for domain_file in category_dir.glob("*.json"):
                domain = domain_file.stem
                self.check_file(domain_file, category, domain)
        
        # 输出统计报告
        self.print_report()
    
    def print_report(self):
        """打印质量审查报告"""
        print("\n" + "=" * 80)
        print("质量审查报告")
        print("=" * 80)
        
        pass_rate = (self.stats['passed'] / self.stats['total'] * 100) if self.stats['total'] > 0 else 0
        
        print(f"\n总计: {self.stats['total']}条知识点")
        print(f"通过: {self.stats['passed']}条 ({pass_rate:.1f}%)")
        print(f"失败: {self.stats['failed']}条")
        
        if self.stats['failed'] > 0:
            print(f"\n发现 {len(self.issues)}个问题:")
            print("-" * 80)
            
            # 只显示前20个问题
            for i, issue in enumerate(self.issues[:20], 1):
                print(f"\n{i}. [{issue['category']}/{issue['domain']}] #{issue['index']}: {issue['title']}")
                for problem in issue['issues']:
                    print(f"   - {problem}")
            
            if len(self.issues) > 20:
                print(f"\n... 还有 {len(self.issues) - 20}个问题未显示")
        
        # 保存详细报告到文件
        report_path = self.knowledge_base_path.parent.parent / "tests" / "quality_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({
                'stats': self.stats,
                'issues': self.issues
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n详细报告已保存到: {report_path}")


if __name__ == "__main__":
    knowledge_base_path = r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\data\knowledge"
    checker = KnowledgeQualityChecker(knowledge_base_path)
    checker.check_all()
