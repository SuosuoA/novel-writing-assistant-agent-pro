"""
知识库向量存储初始化脚本

创建日期：2026-03-26

功能：
- 初始化LanceDB向量数据库
- 创建knowledge表
- 加载基础知识库数据（科幻/玄幻/通用）
- 验证向量检索功能

使用方法：
    python tools/init_knowledge_base.py
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.vector_store import NovelVectorStore


def load_knowledge_json(json_path: Path) -> List[Dict[str, Any]]:
    """加载JSON格式的知识库数据"""
    if not json_path.exists():
        print(f"Warning: {json_path} not found, skipping...")
        return []
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data


def init_vector_store():
    """初始化向量存储并加载知识库"""
    
    print("=" * 60)
    print("Knowledge Base Vector Store Initialization")
    print("=" * 60)
    
    # 1. 初始化向量存储
    db_path = project_root / "data" / "knowledge_base"
    print(f"\n[Step 1] Creating vector store: {db_path}")
    
    vector_store = NovelVectorStore(
        db_path=str(db_path),
        embedding_type="local",  # 使用本地模型
        embedding_model="all-MiniLM-L6-v2"
    )
    
    print("[OK] Vector store initialized successfully")
    
    # 2. 加载知识库数据
    data_dir = project_root / "data"
    knowledge_files = {
        "scifi": data_dir / "knowledge_scifi.json",
        "fantasy": data_dir / "knowledge_fantasy.json",
        "general": data_dir / "knowledge_general.json"
    }
    
    print("\n[Step 2] Loading knowledge data")
    total_knowledge = 0
    
    for category, file_path in knowledge_files.items():
        knowledge_list = load_knowledge_json(file_path)
        if knowledge_list:
            print(f"  - {category}: {len(knowledge_list)} items")
            total_knowledge += len(knowledge_list)
            
            # 添加到向量存储
            for idx, item in enumerate(knowledge_list):
                try:
                    knowledge_id = item.get('id', f"{category}_{idx}")
                    content = item.get('content', '')
                    keywords = item.get('keywords', [])
                    domain = item.get('domain', category)
                    
                    # 添加知识点向量
                    vector_store.add_knowledge(
                        knowledge_id=knowledge_id,
                        content=content,
                        keywords=keywords,
                        category=category,
                        metadata={
                            "domain": domain,
                            "difficulty": item.get('difficulty', 'intermediate'),
                            "title": item.get('title', '')
                        }
                    )
                except Exception as e:
                    print(f"    Warning: Failed to add knowledge {knowledge_id}: {e}")
    
    print(f"\n[OK] Knowledge loaded: {total_knowledge} items")
    
    # 3. 验证向量检索
    print("\n[Step 3] Testing vector search")
    
    test_queries = [
        "time dilation",
        "quantum entanglement",
        "cultivation realm"
    ]
    
    for query in test_queries:
        results = vector_store.recall_knowledge(query, top_k=3)
        print(f"\nQuery: {query}")
        for i, result in enumerate(results, 1):
            print(f"  {i}. {result.knowledge_id} (score: {result.score:.3f})")
    
    print("\n" + "=" * 60)
    print("[OK] Knowledge base vector store initialization completed")
    print("=" * 60)
    
    return vector_store


def quick_test():
    """快速测试向量检索"""
    
    db_path = project_root / "data" / "knowledge_base"
    
    if not db_path.exists():
        print("Vector store not found, please run initialization first")
        return
    
    print("\nQuick test vector search...")
    vector_store = NovelVectorStore(
        db_path=str(db_path),
        embedding_type="local"
    )
    
    # 测试检索
    query = "black hole event horizon"
    results = vector_store.recall_knowledge(query, top_k=5)
    
    print(f"\nQuery: {query}")
    for i, result in enumerate(results, 1):
        print(f"  {i}. {result.knowledge_id}")
        print(f"     Score: {result.score:.3f}")
        print(f"     Content: {result.content[:100]}...")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Knowledge base vector store initialization")
    parser.add_argument('--test', action='store_true', help='Quick test vector search')
    
    args = parser.parse_args()
    
    if args.test:
        quick_test()
    else:
        init_vector_store()
