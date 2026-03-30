#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统计知识库文件中的知识点数量"""

import json
from pathlib import Path

knowledge_dir = Path(r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\data\knowledge\writing_technique")

total = 0
for json_file in knowledge_dir.glob("*.json"):
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    count = len(data.get("knowledge_points", []))
    total += count
    print(f"{json_file.name}: {count} 条")

print(f"\n总计: {total} 条")
