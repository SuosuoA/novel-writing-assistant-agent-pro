#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""清理垃圾知识库文件（保留history目录）"""
import json
from pathlib import Path

knowledge_dir = Path(r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\data\knowledge")

print("清理垃圾知识库文件...")
print("=" * 60)

deleted_files = []
kept_files = []

for json_file in knowledge_dir.rglob("*.json"):
    rel_path = json_file.relative_to(knowledge_dir)
    
    # 保留history目录的所有文件
    if "history" in str(rel_path):
        kept_files.append(str(rel_path))
        print(f"保留: {rel_path}")
    else:
        # 删除其他所有文件
        json_file.unlink()
        deleted_files.append(str(rel_path))
        print(f"删除: {rel_path}")

print("=" * 60)
print(f"删除: {len(deleted_files)}个文件")
print(f"保留: {len(kept_files)}个文件")
print("清理完成！")
