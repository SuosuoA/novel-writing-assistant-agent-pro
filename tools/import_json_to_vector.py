#!/usr/bin/env python3
"""
将JSON源文件导入到向量库（去重合并）
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.knowledge_manager import KnowledgeManager
from infrastructure.vector_store import NovelVectorStore


def load_json_knowledge(json_file: Path) -> list:
    """加载JSON文件中的知识点"""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 处理两种格式：字典（带knowledge_points字段）或列表
        if isinstance(data, dict):
            return data.get('knowledge_points', [])
        elif isinstance(data, list):
            return data
        else:
            print(f"  [WARN] 未知格式: {json_file.name}")
            return []
    except Exception as e:
        print(f"  [ERROR] 读取失败: {json_file.name} - {e}")
        return []


def get_existing_titles(vector_store: NovelVectorStore) -> set:
    """获取向量库中已有的知识点标题（用于去重）"""
    try:
        table = vector_store.db.open_table('knowledge')
        df = table.to_pandas()
        if 'title' in df.columns:
            return set(df['title'].tolist())
        return set()
    except Exception as e:
        print(f"[WARN] 获取已有标题失败: {e}")
        return set()


def main():
    print("=" * 80)
    print("JSON源文件导入向量库（去重合并）")
    print("=" * 80)
    
    # 初始化
    knowledge_dir = project_root / "data" / "knowledge"
    vector_store_dir = project_root / "data" / "knowledge_base"
    
    km = KnowledgeManager(workspace_root=project_root, auto_embed=True)
    vs = NovelVectorStore(db_path=str(vector_store_dir))
    
    # 获取已有知识点标题
    existing_titles = get_existing_titles(vs)
    print(f"\n[1] 向量库现有知识点: {len(existing_titles)}条")
    
    # 扫描JSON文件
    json_files = list(knowledge_dir.glob('**/*.json'))
    print(f"[2] 扫描到JSON文件: {len(json_files)}个\n")
    
    # 导入统计
    stats = {
        'total_json': 0,
        'duplicate': 0,
        'imported': 0,
        'failed': 0,
        'skipped_file': 0
    }
    
    # 逐个文件导入
    for json_file in json_files:
        print(f"[处理] {json_file.relative_to(knowledge_dir)}")
        
        knowledge_points = load_json_knowledge(json_file)
        if not knowledge_points:
            stats['skipped_file'] += 1
            continue
        
        print(f"  发现 {len(knowledge_points)} 条知识点")
        stats['total_json'] += len(knowledge_points)
        
        # 逐条导入
        for item in knowledge_points:
            title = item.get('title', '')
            if not title:
                stats['failed'] += 1
                continue
            
            # 去重检查
            if title in existing_titles:
                print(f"  [SKIP] 重复: {title[:40]}...")
                stats['duplicate'] += 1
                continue
            
            # 导入到向量库
            try:
                km.create_knowledge(
                    category=item.get('category', 'general'),
                    domain=item.get('domain', 'misc'),
                    title=title,
                    content=item.get('content', ''),
                    keywords=item.get('keywords', []),
                    difficulty=item.get('difficulty', 'basic'),
                    tags=item.get('tags', [])
                )
                existing_titles.add(title)  # 添加到已存在集合
                stats['imported'] += 1
                print(f"  [OK] 导入: {title[:40]}...")
            except Exception as e:
                print(f"  [ERROR] 导入失败: {title[:40]}... - {e}")
                stats['failed'] += 1
    
    # 最终统计
    print("\n" + "=" * 80)
    print("导入完成统计:")
    print(f"  JSON总知识点: {stats['total_json']}条")
    print(f"  重复跳过: {stats['duplicate']}条")
    print(f"  成功导入: {stats['imported']}条")
    print(f"  导入失败: {stats['failed']}条")
    print(f"  跳过文件: {stats['skipped_file']}个")
    
    # 验证最终结果
    table = vs.db.open_table('knowledge')
    final_count = table.count_rows()
    print(f"\n向量库最终知识点: {final_count}条")
    print("=" * 80)


if __name__ == '__main__':
    main()
