#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识库质量验证工具

用于验证知识库数据质量和完整性。
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime


def validate_knowledge_point(kp: Dict) -> Tuple[bool, List[str]]:
    """
    验证单个知识点
    
    Args:
        kp: 知识点字典
        
    Returns:
        (是否通过, 错误列表)
    """
    errors = []
    
    # 1. 检查必需字段
    required_fields = ['knowledge_id', 'title', 'content', 'keywords', 'references']
    for field in required_fields:
        if field not in kp:
            errors.append(f"缺少字段: {field}")
    
    # 2. 检查内容长度（参考11.14知识库样本标准：约3000字）
    if 'content' in kp:
        content_len = len(kp['content'])
        if content_len < 200:
            errors.append(f"内容过短: {content_len}字 (要求≥200)")
        # 不设上限，高质量知识点可以很长
    
    # 3. 检查关键词数量（参考标准：10个关键词）
    if 'keywords' in kp:
        keyword_count = len(kp['keywords'])
        if keyword_count < 5:
            errors.append(f"关键词过少: {keyword_count}个 (要求≥5)")
    
    # 4. 检查参考作品数量
    if 'references' in kp:
        ref_count = len(kp['references'])
        if ref_count < 2:
            errors.append(f"参考作品过少: {ref_count}个 (要求≥2)")
    
    return len(errors) == 0, errors


def validate_sample(sample_size: int = 30) -> bool:
    """
    随机抽检知识点
    
    Args:
        sample_size: 抽检数量
        
    Returns:
        是否通过
    """
    workspace_root = Path(__file__).parent.parent
    knowledge_dir = workspace_root / "data" / "knowledge"
    
    all_knowledge = []
    
    # 收集所有知识点
    for json_file in knowledge_dir.rglob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'knowledge_points' in data:
                    all_knowledge.extend(data['knowledge_points'])
        except Exception as e:
            print(f"[警告] 读取文件失败: {json_file}, {e}")
    
    if len(all_knowledge) == 0:
        print("❌ 知识库为空，无法验证")
        return False
    
    # 随机抽检
    sample = random.sample(all_knowledge, min(sample_size, len(all_knowledge)))
    
    print(f"\n{'='*60}")
    print(f"知识库质量验证 - 随机抽检{len(sample)}条")
    print(f"{'='*60}\n")
    
    valid_count = 0
    for i, kp in enumerate(sample, 1):
        is_valid, errors = validate_knowledge_point(kp)
        
        print(f"第{i}条: {kp.get('title', '无标题')}")
        if is_valid:
            print(f"  ✅ 通过验证")
            valid_count += 1
        else:
            print(f"  ❌ 验证失败:")
            for error in errors:
                print(f"     - {error}")
        print()
    
    pass_rate = valid_count / len(sample)
    print(f"\n{'='*60}")
    print(f"验证结果: {valid_count}/{len(sample)} 通过 (通过率: {pass_rate*100:.1f}%)")
    print(f"{'='*60}\n")
    
    if pass_rate >= 0.85:
        print("✅ 质量验证通过！")
        return True
    else:
        print("❌ 质量验证未通过，通过率<85%")
        return False


def get_statistics() -> Dict:
    """
    获取知识库统计信息
    
    Returns:
        统计信息字典
    """
    workspace_root = Path(__file__).parent.parent
    knowledge_dir = workspace_root / "data" / "knowledge"
    
    stats = {
        "total": 0,
        "categories": {},
        "domains": {},
        "quality": {
            "avg_content_length": 0,
            "avg_keywords": 0,
            "avg_references": 0
        }
    }
    
    all_content_lengths = []
    all_keyword_counts = []
    all_reference_counts = []
    
    # 统计各分类
    for category_dir in knowledge_dir.iterdir():
        if not category_dir.is_dir():
            continue
        
        category = category_dir.name
        category_count = 0
        
        for json_file in category_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    kps = data.get('knowledge_points', [])
                    count = len(kps)
                    
                    category_count += count
                    
                    domain = data.get('domain', json_file.stem)
                    stats['domains'][f"{category}/{domain}"] = count
                    
                    # 收集质量指标
                    for kp in kps:
                        if 'content' in kp:
                            all_content_lengths.append(len(kp['content']))
                        if 'keywords' in kp:
                            all_keyword_counts.append(len(kp['keywords']))
                        if 'references' in kp:
                            all_reference_counts.append(len(kp['references']))
                            
            except Exception as e:
                print(f"[警告] 统计文件失败: {json_file}, {e}")
        
        stats['categories'][category] = category_count
        stats['total'] += category_count
    
    # 计算平均值
    if all_content_lengths:
        stats['quality']['avg_content_length'] = sum(all_content_lengths) / len(all_content_lengths)
    if all_keyword_counts:
        stats['quality']['avg_keywords'] = sum(all_keyword_counts) / len(all_keyword_counts)
    if all_reference_counts:
        stats['quality']['avg_references'] = sum(all_reference_counts) / len(all_reference_counts)
    
    return stats


def print_statistics():
    """打印统计信息"""
    stats = get_statistics()
    
    print(f"\n{'='*60}")
    print("知识库统计信息")
    print(f"{'='*60}\n")
    
    print(f"总知识点数: {stats['total']}\n")
    
    print("各分类数量:")
    for category, count in stats['categories'].items():
        print(f"  {category}: {count}")
    
    print("\n各领域数量:")
    for domain, count in sorted(stats['domains'].items()):
        print(f"  {domain}: {count}")
    
    print("\n质量指标:")
    print(f"  平均内容长度: {stats['quality']['avg_content_length']:.0f}字")
    print(f"  平均关键词数: {stats['quality']['avg_keywords']:.1f}个")
    print(f"  平均参考作品数: {stats['quality']['avg_references']:.1f}个")
    
    print(f"\n{'='*60}\n")


def check_completeness() -> Dict:
    """
    检查知识库完整性
    
    Returns:
        完整性报告
    """
    # 目标数据（参考文档）
    targets = {
        "scifi": {
            "physics": 209,
            "biology": 150,
            "space": 100,
            "technology": 100
        },
        "xuanhuan": {
            "magic": 120,
            "mythology": 114,
            "cultivation": 100
        },
        "general": {
            "writing": 80,
            "narrative": 77,
            "character": 80
        }
    }
    
    workspace_root = Path(__file__).parent.parent
    knowledge_dir = workspace_root / "data" / "knowledge"
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_target": 0,
        "total_actual": 0,
        "completion_rate": 0.0,
        "categories": {}
    }
    
    for category, domains in targets.items():
        category_report = {
            "target": sum(domains.values()),
            "actual": 0,
            "domains": {},
            "completion_rate": 0.0
        }
        
        category_dir = knowledge_dir / category
        if category_dir.exists():
            for domain, target_count in domains.items():
                domain_file = category_dir / f"{domain}.json"
                
                actual_count = 0
                if domain_file.exists():
                    try:
                        with open(domain_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            actual_count = len(data.get('knowledge_points', []))
                    except:
                        pass
                
                domain_rate = (actual_count / target_count) if target_count > 0 else 0
                
                category_report["domains"][domain] = {
                    "target": target_count,
                    "actual": actual_count,
                    "completion_rate": domain_rate
                }
                
                category_report["actual"] += actual_count
                print(f"  {category}/{domain}: {actual_count}/{target_count} ({domain_rate:.1%})")
        
        category_report["completion_rate"] = (
            category_report["actual"] / category_report["target"]
            if category_report["target"] > 0 else 0
        )
        
        report["categories"][category] = category_report
        report["total_target"] += category_report["target"]
        report["total_actual"] += category_report["actual"]
    
    report["completion_rate"] = (
        report["total_actual"] / report["total_target"]
        if report["total_target"] > 0 else 0
    )
    
    print(f"\n{'='*60}")
    print("知识库完整性检查")
    print(f"{'='*60}\n")
    
    print(f"总进度: {report['total_actual']}/{report['total_target']} ({report['completion_rate']:.1%})")
    print(f"\n各分类详情:\n")
    
    for category, cat_report in report["categories"].items():
        print(f"{category}: {cat_report['actual']}/{cat_report['target']} ({cat_report['completion_rate']:.1%})")
    
    # 保存报告
    report_path = workspace_root / "data" / "knowledge_completeness_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n报告已保存: {report_path}")
    print(f"\n{'='*60}\n")
    
    return report


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="知识库质量验证工具")
    parser.add_argument("--sample", type=int, default=30, help="抽检数量")
    parser.add_argument("--stats", action="store_true", help="显示统计信息")
    parser.add_argument("--check", action="store_true", help="检查完整性")
    parser.add_argument("--validate", action="store_true", help="执行质量验证")
    
    args = parser.parse_args()
    
    if args.stats:
        print_statistics()
    elif args.check:
        check_completeness()
    elif args.validate:
        validate_sample(args.sample)
    else:
        # 默认显示统计和完整性检查
        print_statistics()
        check_completeness()
        print("\n执行质量验证...")
        validate_sample(args.sample)
