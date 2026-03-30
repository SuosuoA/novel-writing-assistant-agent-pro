#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据GUI截图创建完整的知识库分类结构
"""
from pathlib import Path

knowledge_dir = Path("E:/WorkBuddyworkspace/Novel Writing Assistant-Agent Pro/data/knowledge")

# GUI截图中显示的完整分类
CATEGORIES = {
    # 小说类型分类
    "xuanhuan": "玄幻",
    "xianxia": "仙侠",
    "urban": "都市",
    "romance": "言情",
    "history": "历史",
    "scifi": "科幻",
    "suspense": "悬疑",
    "military": "军事",
    "wuxia": "武侠",
    "game": "游戏",
    "fantasy": "奇幻",
    "lingyi": "灵异",
    "tongren": "同人",
    "general": "通用",
    "writing_technique": "写作技巧",
    
    # 领域分类
    "philosophy": "哲学",
}

# 领域分类（domain）- 每个分类下可用的领域
DOMAINS = {
    # 科幻领域
    "scifi": [
        "physics", "chemistry", "biology", "mathematics", "geography",
        "astronomy", "psychology", "philosophy", "economics", "history",
        "aerospace", "ai", "futurescience"
    ],
    
    # 悬疑领域
    "suspense": [
        "psychology", "logic", "criminology", "forensics", "law",
        "investigation", "mystery"
    ],
    
    # 军事领域
    "military": [
        "military", "strategy", "weapons", "tactics", "history"
    ],
    
    # 武侠领域
    "wuxia": [
        "martialarts", "tcm", "jianghu", "history", "culture"
    ],
    
    # 游戏领域
    "game": [
        "gamedesign", "mechanics", "narrative", "worldbuilding"
    ],
    
    # 奇幻领域
    "fantasy": [
        "magic", "mythology", "religion", "metaphysics", "cultivation",
        "fantasy_creatures", "worldbuilding"
    ],
    
    # 灵异领域
    "lingyi": [
        "supernatural", "folklore", "legends", "mysticism"
    ],
    
    # 都市领域
    "urban": [
        "society", "law", "education", "workplace", "emotion", "family"
    ],
    
    # 言情领域
    "romance": [
        "emotion", "relationship", "psychology", "society"
    ],
    
    # 历史领域
    "history": [
        "history", "culture", "politics", "economy", "military"
    ],
    
    # 玄幻领域
    "xuanhuan": [
        "cultivation", "metaphysics", "magic", "worldbuilding", "fantasy_creatures"
    ],
    
    # 仙侠领域
    "xianxia": [
        "cultivation", "immortality", "daoism", "worldbuilding"
    ],
    
    # 同人领域
    "tongren": [
        "original_analysis", "character", "plot", "setting"
    ],
    
    # 通用领域
    "general": [
        "general", "philosophy", "culture", "technology"
    ],
    
    # 写作技巧领域（特殊）
    "writing_technique": [
        "narrative", "description", "rhetoric", "structure",
        "character_building", "plot_design", "dialogue_art",
        "pacing", "theme", "style"
    ],
    
    # 哲学领域
    "philosophy": [
        "philosophy", "ethics", "logic", "metaphysics", "aesthetics"
    ]
}

created_cats = []
created_domains = {}

# 创建分类文件夹
for cat in CATEGORIES:
    cat_dir = knowledge_dir / cat
    if not cat_dir.exists():
        cat_dir.mkdir(parents=True, exist_ok=True)
        # 创建README.md
        readme = cat_dir / "README.md"
        if not readme.exists():
            readme.write_text(f"# {CATEGORIES[cat]}知识库\n\n存放{CATEGORIES[cat]}相关的知识点。\n", encoding='utf-8')
        created_cats.append(cat)
    
    # 创建领域子文件夹
    if cat in DOMAINS:
        for domain in DOMAINS[cat]:
            domain_dir = cat_dir / domain
            if not domain_dir.exists():
                domain_dir.mkdir(parents=True, exist_ok=True)
                if cat not in created_domains:
                    created_domains[cat] = []
                created_domains[cat].append(domain)

print(f"新建分类: {created_cats}")
print(f"\n新建领域子文件夹:")
for cat, domains in created_domains.items():
    if domains:
        print(f"  {cat}({CATEGORIES[cat]}): {len(domains)}个领域")
        for domain in domains:
            print(f"    - {domain}")

print(f"\n总计: {len(created_cats)}个新分类, {sum(len(d) for d in created_domains.values())}个新领域")
