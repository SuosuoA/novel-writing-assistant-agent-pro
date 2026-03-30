#!/usr/bin/env python3
"""知识库合并脚本 - 将data/knowledge的JSON源文件导入到data/knowledge_base向量库"""

import json
import os
import sys
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.knowledge_manager import KnowledgeManager

def main():
    print("=" * 80)
    print("知识库合并脚本 - 将JSON源文件导入到LanceDB向量库")
    print("=" * 80)
    
    # 初始化KnowledgeManager
    km = KnowledgeManager(workspace_root=project_root)
    
    # 统计JSON源文件
    json_dir = project_root / "data" / "knowledge"
    json_files = list(json_dir.rglob("*.json"))
    
    print(f"\n[INFO] 发现JSON源文件: {len(json_files)}个")
    for jf in json_files:
        print(f"  - {jf.relative_to(project_root)}")
    
    # 导入所有JSON文件到向量库
    print("\n[INFO] 开始导入到向量库...")
    
    total_imported = 0
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 处理数据格式
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = [data]
            else:
                print(f"  [WARNING] {json_file.name}: 未知格式，跳过")
                continue
            
            # 导入每个知识点
            for item in items:
                try:
                    # 确保必要字段
                    if 'knowledge_id' not in item:
                        item['knowledge_id'] = f"{item.get('category', 'unknown')}-{item.get('domain', 'misc')}-{hash(item.get('title', ''))}"
                    
                    # 添加知识点（使用create_knowledge）
                    km.create_knowledge(
                        category=item.get('category', 'general'),
                        domain=item.get('domain', 'misc'),
                        title=item['title'],
                        content=item['content'],
                        keywords=item.get('keywords', []),
                        difficulty=item.get('difficulty', 'basic'),
                        tags=item.get('tags', [])
                    )
                    total_imported += 1
                    print(f"  [OK] 导入: {item['title'][:50]}...")
                    
                except Exception as e:
                    print(f"  [ERROR] 导入知识点失败: {e}")
                    
        except Exception as e:
            print(f"  [ERROR] 读取文件失败 {json_file.name}: {e}")
    
    print(f"\n[SUCCESS] 导入完成！共导入 {total_imported} 条知识点")
    
    # 验证向量库最终状态
    print("\n[INFO] 验证向量库状态...")
    stats = km.get_stats()
    print(f"  总知识点: {stats.get('total', 0)}")
    print(f"  分类统计:")
    for cat, count in stats.get('categories', {}).items():
        print(f"    {cat}: {count}条")
    
    return total_imported

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[FATAL] 脚本执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
