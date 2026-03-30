"""
Load existing knowledge JSON files into vector store

Usage:
    python tools/load_knowledge_to_vector.py
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.vector_store import NovelVectorStore


def load_json_files():
    """Load all knowledge JSON files and add to vector store"""
    
    print("=" * 60)
    print("Loading Knowledge into Vector Store")
    print("=" * 60)
    
    # Initialize vector store
    db_path = project_root / "data" / "knowledge_base"
    vector_store = NovelVectorStore(
        db_path=str(db_path),
        embedding_type="local"
    )
    
    print(f"\n[Step 1] Vector store ready: {db_path}")
    
    # Knowledge directories
    kb_root = project_root / "data" / "knowledge"
    categories = {
        "scifi": kb_root / "scifi",
        "fantasy": kb_root / "fantasy",
        "general": kb_root / "general",
        "xuanhuan": kb_root / "xuanhuan"
    }
    
    total_items = 0
    
    for category, dir_path in categories.items():
        if not dir_path.exists():
            print(f"  Skipping {category}: directory not found")
            continue
        
        json_files = list(dir_path.glob("*.json"))
        print(f"\n[{category}] Found {len(json_files)} JSON files")
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Handle different JSON structures
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get('knowledge_points', data.get('items', [data]))
                else:
                    items = [data]
                
                for idx, item in enumerate(items):
                    try:
                        knowledge_id = item.get('id', f"{category}_{json_file.stem}_{idx}")
                        content = item.get('content', '')
                        title = item.get('title', '')
                        domain = item.get('domain', category)
                        keywords = item.get('keywords', [])
                        
                        # Add to vector store
                        vector_store.add_knowledge(
                            knowledge_id=knowledge_id,
                            category=category,
                            domain=domain,
                            title=title,
                            content=content,
                            keywords=keywords
                        )
                        total_items += 1
                        
                    except Exception as e:
                        print(f"    Error adding item {idx}: {e}")
                
                print(f"  Loaded {json_file.name}: {len(items)} items")
                
            except Exception as e:
                print(f"  Error loading {json_file.name}: {e}")
    
    print(f"\n[OK] Total knowledge items loaded: {total_items}")
    
    # Test search
    print("\n[Step 2] Testing vector search")
    test_queries = ["time dilation", "quantum mechanics", "cultivation"]
    
    for query in test_queries:
        results = vector_store.recall_knowledge(query, top_k=3)
        print(f"\nQuery: {query}")
        for i, result in enumerate(results, 1):
            print(f"  {i}. {result.knowledge_id} (score: {result.score:.3f})")
    
    print("\n" + "=" * 60)
    print("[OK] Knowledge loading completed")
    print("=" * 60)


if __name__ == "__main__":
    load_json_files()
