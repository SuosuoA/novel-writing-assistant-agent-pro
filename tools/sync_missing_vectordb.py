#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库同步到向量数据库工具
将JSON知识库同步到LanceDB向量库
"""

import json
from pathlib import Path
from sentence_transformers import SentenceTransformer
import lancedb
import hashlib
import os

os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
cache_folder = r'F:\sentence_transformers_cache'

class KnowledgeSync:
    def __init__(self):
        self.knowledge_base_path = Path(r'E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\data\knowledge')
        self.vector_db_path = Path(r'E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\data\knowledge_base')
        
        print('[INFO] Loading sentence-transformers model...')
        self.model = SentenceTransformer('all-MiniLM-L6-v2', cache_folder=cache_folder)
        print('[OK] Model loaded')
        
        print(f'[INFO] Connecting to LanceDB at {self.vector_db_path}')
        self.db = lancedb.connect(str(self.vector_db_path))
        print('[OK] Connected')
    
    def create_embedding(self, kp):
        """为知识点创建向量嵌入"""
        text_parts = [
            kp.get('title', ''),
            kp.get('explanation') or '',
            kp.get('content') or '',
            kp.get('classic_cases') or '',
            ' '.join(kp.get('keywords', []) or [])
        ]
        combined_text = ' '.join([part for part in text_parts if part])
        embedding = self.model.encode(combined_text, convert_to_numpy=True)
        return embedding.tolist()
    
    def sync_file(self, json_file, category, domain):
        """同步单个知识文件到向量库"""
        table_name = f'{category}_{domain}'
        print(f'[Processing] {table_name}')
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if 'knowledge_points' not in data:
                print(f'  [SKIP] No knowledge_points field')
                return 0
            
            knowledge_points = data['knowledge_points']
            print(f'  - {len(knowledge_points)} knowledge points')
            
            records = []
            for kp in knowledge_points:
                title = kp.get('title', 'unknown')
                kp_id = kp.get('knowledge_id', '') or hashlib.md5(f'{category}_{domain}_{title}'.encode()).hexdigest()[:16]
                
                embedding = self.create_embedding(kp)
                
                record = {
                    'id': kp_id,
                    'category': category,
                    'domain': domain,
                    'title': kp.get('title', ''),
                    'explanation': kp.get('explanation') or '',
                    'content': kp.get('content') or '',
                    'classic_cases': kp.get('classic_cases') or '',
                    'examples': json.dumps(kp.get('examples', []) or [], ensure_ascii=False),
                    'common_mistakes': json.dumps(kp.get('common_mistakes', []) or [], ensure_ascii=False),
                    'references': json.dumps(kp.get('references', []) or [], ensure_ascii=False),
                    'keywords': json.dumps(kp.get('keywords', []) or [], ensure_ascii=False),
                    'vector': embedding
                }
                records.append(record)
            
            # 删除旧表（如果存在）
            existing_tables = list(self.db.table_names())
            if table_name in existing_tables:
                try:
                    self.db.drop_table(table_name)
                    print(f'  [DROP] Old table removed')
                except Exception as e:
                    print(f'  [WARN] Cannot drop old table: {e}')
            
            # 创建新表
            table = self.db.create_table(table_name, data=records)
            print(f'  [OK] Synced {len(records)} records')
            return len(records)
            
        except Exception as e:
            print(f'  [ERROR] {e}')
            return 0
    
    def sync_missing(self):
        """同步缺失的表"""
        print('=' * 60)
        print('SYNCING MISSING TABLES')
        print('=' * 60)
        
        existing_tables = list(self.db.table_names())
        print(f'Existing tables: {existing_tables}')
        
        total_synced = 0
        
        # 遍历所有知识库文件
        for category_dir in self.knowledge_base_path.iterdir():
            if not category_dir.is_dir():
                continue
            category = category_dir.name
            
            for json_file in category_dir.glob('*.json'):
                domain = json_file.stem
                table_name = f'{category}_{domain}'
                
                # 只同步缺失的表
                if table_name not in existing_tables:
                    count = self.sync_file(json_file, category, domain)
                    total_synced += count
        
        print('')
        print('=' * 60)
        print(f'TOTAL SYNCED: {total_synced}')
        print('=' * 60)
        
        return total_synced


if __name__ == '__main__':
    sync = KnowledgeSync()
    sync.sync_missing()
