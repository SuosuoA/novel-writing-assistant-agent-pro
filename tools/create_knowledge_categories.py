#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建知识库分类文件夹
"""
from pathlib import Path

knowledge_dir = Path("E:/WorkBuddyworkspace/Novel Writing Assistant-Agent Pro/data/knowledge")

# 常见小说分类
categories = [
    "suspense",      # 悬疑
    "urban",         # 都市
    "wuxia",         # 武侠
    "romance",       # 言情
    "fantasy",       # 奇幻
    "military",      # 军事
    "game",          # 游戏
    "sports",        # 竞技
    "mystery",       # 推理
    "horror",        # 恐怖
    "scifi",         # 科幻（已存在）
    "xuanhuan",      # 玄幻（已存在）
    "history",       # 历史（已存在）
    "general",       # 通用（已存在）
    "writing_technique",  # 写作技巧（已存在）
    "philosophy",    # 哲学（已存在）
]

created = []
existing = []

for cat in categories:
    cat_dir = knowledge_dir / cat
    if cat_dir.exists():
        existing.append(cat)
    else:
        cat_dir.mkdir(parents=True, exist_ok=True)
        # 创建README.md
        readme = cat_dir / "README.md"
        if not readme.exists():
            readme.write_text(f"# {cat} 知识库\n\n存放{cat}相关的知识点。\n", encoding='utf-8')
        created.append(cat)

print(f"已创建: {created}")
print(f"已存在: {existing}")
print(f"\n总计: {len(created)} 个新建, {len(existing)} 个已存在, 共 {len(categories)} 个分类")
