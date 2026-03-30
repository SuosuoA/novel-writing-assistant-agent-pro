#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识点迁移脚本 - 数组格式转分条存储

用途:
将现有的知识点JSON文件(数组格式)转换为分条存储格式

执行命令:
python tools/migrate_knowledge_to_files.py --dry-run  # 预览模式
python tools/migrate_knowledge_to_files.py           # 执行迁移
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.knowledge_file_manager import KnowledgeFileManager


def migrate_knowledge_files(dry_run: bool = True):
    """
    迁移知识点文件
    
    Args:
        dry_run: 是否为预览模式(不实际执行)
    """
    print("=" * 70)
    print("知识点迁移工具 - 数组格式转分条存储")
    print("=" * 70)
    
    workspace_root = Path(__file__).parent.parent
    knowledge_dir = workspace_root / "data" / "knowledge"
    
    # 初始化管理器
    manager = KnowledgeFileManager(knowledge_dir)
    
    # 查找所有JSON文件(排除子目录中的)
    source_dir = knowledge_dir
    json_files = list(source_dir.glob("*.json"))
    
    # 过滤掉临时文件和索引文件
    json_files = [
        f for f in json_files 
        if not f.name.startswith(".") 
        and f.name not in ["index.json", "knowledge_index.json"]
    ]
    
    if not json_files:
        print("\n❌ 未找到需要迁移的JSON文件")
        print(f"   搜索目录: {source_dir}")
        return
    
    print(f"\n找到 {len(json_files)} 个JSON文件需要迁移:")
    for f in json_files:
        print(f"  - {f.name}")
    
    if dry_run:
        print("\n⚠️  预览模式 - 不实际执行迁移")
        print("\n将执行以下操作:")
    else:
        print("\n开始迁移...")
    
    # 统计
    total_migrated = 0
    total_failed = 0
    
    for json_file in json_files:
        print(f"\n处理文件: {json_file.name}")
        
        try:
            # 读取源文件
            with open(json_file, 'r', encoding='utf-8') as f:
                knowledge_points = json.load(f)
            
            # 兼容不同格式
            if isinstance(knowledge_points, dict):
                if "knowledge_points" in knowledge_points:
                    knowledge_points = knowledge_points["knowledge_points"]
                else:
                    knowledge_points = [knowledge_points]
            
            print(f"  包含知识点: {len(knowledge_points)}条")
            
            # 确定分类和领域
            filename = json_file.stem
            if "_" in filename:
                parts = filename.split("_", 1)
                category = parts[0]
                domain = parts[1] if len(parts) > 1 else "general"
            else:
                category = filename
                domain = "general"
            
            print(f"  分类: {category}, 领域: {domain}")
            
            if dry_run:
                print(f"  ✅ 将迁移到: {category}/{domain}/ 目录")
                total_migrated += len(knowledge_points)
            else:
                # 执行迁移
                file_paths = manager.save_knowledge_batch(knowledge_points, category, domain)
                print(f"  ✅ 已保存 {len(file_paths)} 个文件")
                total_migrated += len(file_paths)
                
                # 备份原文件
                backup_dir = knowledge_dir / ".backup"
                backup_dir.mkdir(exist_ok=True)
                backup_file = backup_dir / f"{json_file.name}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy(json_file, backup_file)
                print(f"  💾 原文件已备份: {backup_file.name}")
                
                # 删除原文件
                json_file.unlink()
                print(f"  🗑️  原文件已删除")
        
        except Exception as e:
            print(f"  ❌ 迁移失败: {e}")
            total_failed += 1
    
    # 最终报告
    print("\n" + "=" * 70)
    print("迁移报告")
    print("=" * 70)
    print(f"✅ 成功迁移: {total_migrated}条知识点")
    print(f"❌ 失败: {total_failed}个文件")
    
    if dry_run:
        print("\n⚠️  这是预览模式,请运行以下命令执行实际迁移:")
        print("   python tools/migrate_knowledge_to_files.py")
    else:
        print("\n✅ 迁移完成!")
        print(f"   原文件备份位置: {knowledge_dir / '.backup'}")
        
        # 显示新结构
        print("\n新的目录结构:")
        for category_dir in knowledge_dir.iterdir():
            if category_dir.is_dir() and not category_dir.name.startswith("."):
                print(f"  {category_dir.name}/")
                for domain_dir in category_dir.iterdir():
                    if domain_dir.is_dir():
                        kp_count = len([f for f in domain_dir.glob("*.json") if f.name != "index.json"])
                        print(f"    └─ {domain_dir.name}/ ({kp_count}条知识点)")
    
    # 获取统计信息
    stats = manager.get_statistics()
    print(f"\n知识库总计: {stats['total_count']}条知识点")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="知识点迁移工具")
    parser.add_argument("--dry-run", action="store_true", help="预览模式,不实际执行")
    
    args = parser.parse_args()
    
    migrate_knowledge_files(dry_run=args.dry_run)
