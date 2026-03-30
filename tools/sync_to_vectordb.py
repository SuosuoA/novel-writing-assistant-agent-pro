#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库同步到向量数据库工具
将JSON知识库同步到LanceDB向量库
"""

import json
import yaml
from pathlib import Path
from typing import List, Dict
from sentence_transformers import SentenceTransformer
import lancedb
from lancedb.pydantic import LanceModel, Vector
from pydantic import Field
import hashlib

class KnowledgeSync:
    def __init__(self, config_path: str):
        # 读取配置
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        self.knowledge_base_path = Path(r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\data\knowledge")
        self.vector_db_path = Path(r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\data\knowledge_base")
        
        # 初始化embedding模型（使用本地缓存）
        print("[INFO] Loading sentence-transformers model from local cache...")
        import os
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        cache_folder = r"F:\sentence_transformers_cache"
        self.model = SentenceTransformer('all-MiniLM-L6-v2', cache_folder=cache_folder)
        
        # 连接LanceDB
        print(f"[INFO] Connecting to LanceDB at {self.vector_db_path}")
        self.db = lancedb.connect(str(self.vector_db_path))
        
        print("[OK] KnowledgeSync initialized")
    
    def create_knowledge_embedding(self, kp: Dict) -> List[float]:
        """为知识点创建向量嵌入"""
        # 组合所有文本字段
        text_parts = [
            kp.get('title', ''),
            kp.get('explanation', ''),
            kp.get('content', ''),
            kp.get('classic_cases', ''),
            ' '.join(kp.get('keywords', []))
        ]
        
        combined_text = ' '.join([part for part in text_parts if part])
        
        # 生成embedding
        embedding = self.model.encode(combined_text, convert_to_numpy=True)
        return embedding.tolist()
    
    def sync_knowledge_file(self, json_file: Path, category: str, domain: str):
        """同步单个知识文件到向量库"""
        print(f"\n[Processing] {category}/{domain}")
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if 'knowledge_points' not in data:
                print(f"[WARN] Missing knowledge_points field")
                return
            
            knowledge_points = data['knowledge_points']
            print(f"[INFO] Processing {len(knowledge_points)} knowledge points")
            
            # 准备数据
            records = []
            for kp in knowledge_points:
                # 生成ID
                kp_id = kp.get('knowledge_id', '')
                if not kp_id:
                    # 基于标题生成唯一ID
                    title = kp.get('title', 'unknown')
                    kp_id = hashlib.md5(f"{category}_{domain}_{title}".encode()).hexdigest()[:16]
                
                # 生成embedding
                embedding = self.create_knowledge_embedding(kp)
                
                # 创建记录
                record = {
                    'id': kp_id,
                    'category': category,
                    'domain': domain,
                    'title': kp.get('title', ''),
                    'explanation': kp.get('explanation', ''),
                    'content': kp.get('content', ''),
                    'classic_cases': kp.get('classic_cases', ''),
                    'examples': json.dumps(kp.get('examples', []), ensure_ascii=False),
                    'common_mistakes': json.dumps(kp.get('common_mistakes', []), ensure_ascii=False),
                    'references': json.dumps(kp.get('references', []), ensure_ascii=False),
                    'keywords': json.dumps(kp.get('keywords', []), ensure_ascii=False),
                    'vector': embedding
                }
                records.append(record)
            
            # 创建或更新表
            table_name = f"{category}_{domain}"
            
            if table_name in self.db.table_names():
                # 删除旧表
                self.db.drop_table(table_name)
            
            # 创建新表
            table = self.db.create_table(table_name, data=records)
            
            print(f"[OK] Synced {len(records)} knowledge points to {table_name}")
            
        except Exception as e:
            print(f"[ERROR] Failed to sync {json_file}: {e}")
    
    def sync_all(self):
        """同步所有知识库文件"""
        print("=" * 80)
        print("知识库向量同步")
        print("=" * 80)
        
        total_synced = 0
        
        # 遍历所有类别
        for category_dir in self.knowledge_base_path.iterdir():
            if not category_dir.is_dir():
                continue
            
            category = category_dir.name
            
            # 遍历该类别下的所有领域文件
            for domain_file in category_dir.glob("*.json"):
                domain = domain_file.stem
                self.sync_knowledge_file(domain_file, category, domain)
        
        print("\n" + "=" * 80)
        print("向量同步完成")
        print("=" * 80)


if __name__ == "__main__":
    config_path = r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\config.yaml"
    sync = KnowledgeSync(config_path)
    sync.sync_all()
