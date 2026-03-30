#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
查重引擎 - 三层查重机制

查重策略：
1. 完全匹配去重（快速） - 标题+关键词完全相同
2. 语义相似度去重（中等） - 使用向量检索，阈值0.85
3. 内容重叠度去重（慢速） - Jaccard相似度，阈值0.70

P2优化：
- SimHash算法优化O(n²)为O(n log n)
- 分桶策略减少比较次数
"""

import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


class DeduplicationEngine:
    """查重引擎 - 强查重能力"""
    
    def __init__(self, workspace_root: Optional[Path] = None, 
                 similarity_threshold: Optional[float] = None,
                 overlap_threshold: Optional[float] = None):
        """初始化查重引擎
        
        P3优化：支持配置化阈值
        
        Args:
            workspace_root: 工作区根目录（用于向量检索）
            similarity_threshold: 语义相似度阈值（可选，默认从配置读取）
            overlap_threshold: 内容重叠度阈值（可选，默认从配置读取）
        """
        self.workspace_root = workspace_root
        
        # P3优化：从配置文件读取阈值
        try:
            from .config_loader import get_similarity_threshold, get_overlap_threshold
            self.similarity_threshold = similarity_threshold or get_similarity_threshold()
            self.overlap_threshold = overlap_threshold or get_overlap_threshold()
        except ImportError:
            # 降级使用默认值
            self.similarity_threshold = similarity_threshold or 0.85
            self.overlap_threshold = overlap_threshold or 0.70
        
        self.exact_match_cache = {}       # 完全匹配缓存
        
        logger.info("[DEDUP_ENGINE] 初始化完成")
    
    def detect_duplicates(self, 
                        knowledge_list: List[Dict]) -> List[Dict]:
        """
        检测重复词条（主接口）
        
        Args:
            knowledge_list: 知识点列表
        
        Returns:
            [
                {
                    "group_id": 1,
                    "canonical_id": "kp_scifi_001",
                    "duplicate_ids": ["kp_scifi_002", "kp_scifi_003"],
                    "similarity_matrix": {"kp_scifi_002": 0.95, "kp_scifi_003": 0.88},
                    "reason": "title_and_content_high_similarity"
                }
            ]
        """
        groups = []
        all_duplicate_ids = set()
        
        # 1. 完全匹配去重
        exact_dups = self._exact_match_dedup(knowledge_list)
        if exact_dups:
            groups.append({
                "group_id": len(groups) + 1,
                "canonical_id": "exact_match_group",
                "duplicate_ids": list(exact_dups),
                "similarity_matrix": {id: 1.0 for id in exact_dups},
                "reason": "exact_match_title_keywords"
            })
            all_duplicate_ids.update(exact_dups)
        
        # 2. 语义相似度去重
        semantic_groups = self._semantic_similarity_dedup(knowledge_list)
        for group in semantic_groups:
            group["group_id"] = len(groups) + 1
            groups.append(group)
            all_duplicate_ids.update(group['duplicate_ids'])
        
        # 3. 内容重叠度去重
        overlap_groups = self._content_overlap_dedup(knowledge_list)
        for group in overlap_groups:
            # 跳过已经被语义相似度检测到的
            new_dup_ids = [id for id in group['duplicate_ids'] if id not in all_duplicate_ids]
            if new_dup_ids:
                group["group_id"] = len(groups) + 1
                group["duplicate_ids"] = new_dup_ids
                group["similarity_matrix"] = {k: v for k, v in group["similarity_matrix"].items() if k in new_dup_ids}
                groups.append(group)
        
        logger.info(f"[DEDUP_ENGINE] 检测到 {len(groups)} 组重复，共 {len(all_duplicate_ids)} 条")
        
        return groups
    
    def _exact_match_dedup(self, knowledge_list: List[Dict]) -> Set[str]:
        """
        完全匹配去重（标题+关键词完全相同）
        
        Args:
            knowledge_list: 知识点列表
        
        Returns:
            需要删除的词条ID集合
        """
        seen = {}
        duplicates = set()
        
        for kp in knowledge_list:
            # 标准化标题（小写、去除空格）
            title = kp.get('title', '').strip().lower()
            
            # 标准化关键词（排序、去重）
            keywords = tuple(sorted(set(
                kw.strip().lower() 
                for kw in kp.get('keywords', [])
            )))
            
            key = (title, keywords)
            
            if key in seen:
                # 保留最早的，删除后续的
                duplicates.add(kp.get('knowledge_id', ''))
            else:
                seen[key] = kp.get('knowledge_id', '')
        
        logger.info(f"[DEDUP_ENGINE] 完全匹配去重: 检测到 {len(duplicates)} 条重复")
        
        return duplicates
    
    def _semantic_similarity_dedup(self, 
                                  knowledge_list: List[Dict]) -> List[Dict]:
        """
        语义相似度去重（使用向量检索）
        
        Args:
            knowledge_list: 知识点列表
        
        Returns:
            重复组列表
        """
        if not self.workspace_root:
            logger.warning("[DEDUP_ENGINE] workspace_root未设置，跳过语义相似度去重")
            return []
        
        try:
            from infrastructure.vector_store import VectorStore
            
            # 1. 获取向量存储实例
            vector_store = VectorStore(self.workspace_root)
            
            # 2. 逐条检索相似词条
            duplicate_groups = []
            checked_ids = set()
            
            for kp in knowledge_list:
                kp_id = kp.get('knowledge_id', '')
                
                if kp_id in checked_ids:
                    continue
                
                # 使用标题+内容构建查询
                query = f"{kp.get('title', '')}\n{kp.get('content', '')}"
                
                # 检索Top 5相似词条
                try:
                    results = vector_store.search(
                        query, 
                        top_k=5, 
                        table_name="knowledge",
                        min_score=self.similarity_threshold
                    )
                except Exception as e:
                    logger.warning(f"[DEDUP_ENGINE] 向量检索失败: {e}")
                    continue
                
                # 筛选出相似词条（排除自身）
                similar_ids = []
                similarity_matrix = {}
                
                for r in results:
                    r_id = r.get('knowledge_id', '')
                    r_score = r.get('score', 0)
                    
                    if r_id != kp_id and r_score >= self.similarity_threshold:
                        similar_ids.append(r_id)
                        similarity_matrix[r_id] = r_score
                
                if similar_ids:
                    # 选择保留的词条（最早创建的）
                    all_ids = [kp_id] + similar_ids
                    canonical_id = min(all_ids, key=lambda x: self._get_creation_time(x, knowledge_list))
                    
                    # 构建重复ID列表（排除canonical）
                    dup_ids = [id for id in all_ids if id != canonical_id]
                    
                    if dup_ids:
                        duplicate_groups.append({
                            "group_id": 0,  # 后续分配
                            "canonical_id": canonical_id,
                            "duplicate_ids": dup_ids,
                            "similarity_matrix": {k: v for k, v in similarity_matrix.items() if k in dup_ids},
                            "reason": "semantic_similarity_above_threshold"
                        })
                        
                        # 标记已检查
                        checked_ids.update(all_ids)
            
            logger.info(f"[DEDUP_ENGINE] 语义相似度去重: 检测到 {len(duplicate_groups)} 组重复")
            
            return duplicate_groups
            
        except ImportError:
            logger.warning("[DEDUP_ENGINE] VectorStore未安装，跳过语义相似度去重")
            return []
        except Exception as e:
            logger.warning(f"[DEDUP_ENGINE] 向量检索失败，跳过语义查重: {e}")
            return []
    
    def _content_overlap_dedup(self, 
                              knowledge_list: List[Dict]) -> List[Dict]:
        """
        内容重叠度去重（Jaccard相似度）
        
        P2优化: 使用SimHash分桶策略，将O(n²)优化为O(n log n)
        
        Args:
            knowledge_list: 知识点列表
        
        Returns:
            重复组列表
        """
        # 1. 预处理（分词）+ SimHash计算
        simhash_map = {}  # {id: simhash}
        token_sets = {}
        
        for kp in knowledge_list:
            kp_id = kp.get('knowledge_id', '')
            content = kp.get('content', '')
            
            # 简单分词（按空格和标点）
            tokens = set()
            for char in [' ', '，', '。', '！', '？', '；', '：', '、']:
                content = content.replace(char, ' ')
            tokens.update(content.split())
            token_sets[kp_id] = tokens
            
            # 计算SimHash
            simhash_map[kp_id] = self._compute_simhash(tokens)
        
        # 2. 分桶策略（按SimHash前缀分组）
        buckets = defaultdict(list)  # {prefix: [(id, simhash), ...]}
        prefix_len = 8  # 使用前8位作为桶前缀
        
        for kp_id, simhash in simhash_map.items():
            prefix = bin(simhash >> (64 - prefix_len))[2:].zfill(prefix_len)
            buckets[prefix].append((kp_id, simhash))
        
        # 3. 只在桶内比较（大幅减少比较次数）
        duplicate_groups = []
        checked_pairs = set()
        
        for bucket_id, bucket_items in buckets.items():
            # 桶内两两比较
            for i, (id1, hash1) in enumerate(bucket_items):
                for id2, hash2 in bucket_items[i+1:]:
                    if (id1, id2) in checked_pairs or (id2, id1) in checked_pairs:
                        continue
                    
                    # 先用汉明距离快速过滤
                    hamming_dist = self._hamming_distance(hash1, hash2)
                    if hamming_dist > 10:  # 汉明距离>10，差异太大，跳过
                        continue
                    
                    # 精确计算Jaccard相似度
                    similarity = self._jaccard_similarity(
                        token_sets.get(id1, set()), 
                        token_sets.get(id2, set())
                    )
                    
                    if similarity >= self.overlap_threshold:
                        # 选择保留的词条（最早创建的）
                        canonical_id = min([id1, id2], 
                                         key=lambda x: self._get_creation_time(x, knowledge_list))
                        duplicate_id = id2 if canonical_id == id1 else id1
                        
                        duplicate_groups.append({
                            "group_id": 0,  # 后续分配
                            "canonical_id": canonical_id,
                            "duplicate_ids": [duplicate_id],
                            "similarity_matrix": {duplicate_id: similarity},
                            "reason": "content_overlap_above_threshold"
                        })
                        
                        checked_pairs.add((id1, id2))
        
        logger.info(f"[DEDUP_ENGINE] 内容重叠度去重(SimHash优化): 检测到 {len(duplicate_groups)} 组重复, 桶数={len(buckets)}")
        
        return duplicate_groups
    
    def _compute_simhash(self, tokens: Set[str]) -> int:
        """
        计算SimHash值
        
        SimHash是一种局部敏感哈希，可用于快速检测相似文本
        
        Args:
            tokens: 词集合
        
        Returns:
            64位SimHash值
        """
        if not tokens:
            return 0
        
        # 初始化64位向量
        v = [0] * 64
        
        for token in tokens:
            # 计算MD5哈希
            token_hash = int(hashlib.md5(token.encode('utf-8')).hexdigest(), 16)
            
            # 更新向量
            for i in range(64):
                bit = (token_hash >> i) & 1
                if bit:
                    v[i] += 1
                else:
                    v[i] -= 1
        
        # 生成SimHash
        simhash = 0
        for i in range(64):
            if v[i] > 0:
                simhash |= (1 << i)
        
        return simhash
    
    def _hamming_distance(self, hash1: int, hash2: int) -> int:
        """
        计算两个SimHash的汉明距离
        
        Args:
            hash1: SimHash值1
            hash2: SimHash值2
        
        Returns:
            汉明距离（不同位的数量）
        """
        xor = hash1 ^ hash2
        distance = 0
        while xor:
            distance += xor & 1
            xor >>= 1
        return distance
    
    def _jaccard_similarity(self, set1: set, set2: set) -> float:
        """
        计算Jaccard相似度
        
        公式: J(A,B) = |A∩B| / |A∪B|
        
        Args:
            set1: 词集合1
            set2: 词集合2
        
        Returns:
            Jaccard相似度 (0-1)
        """
        if not set1 and not set2:
            return 1.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def _get_creation_time(self, knowledge_id: str, knowledge_list: List[Dict]) -> float:
        """
        获取知识点创建时间（用于选择保留哪个）
        
        从knowledge_id中提取时间戳或创建时间
        
        Args:
            knowledge_id: 知识点ID
            knowledge_list: 知识点列表
        
        Returns:
            创建时间戳（越小越早）
        """
        # 尝试从知识点列表中查找created_at字段
        for kp in knowledge_list:
            if kp.get('knowledge_id') == knowledge_id:
                created_at = kp.get('created_at')
                if created_at:
                    try:
                        return datetime.fromisoformat(created_at).timestamp()
                    except:
                        pass
                break
        
        # 从ID提取序号（kp_scifi_001 -> 1）
        try:
            parts = knowledge_id.split('_')
            num_part = parts[-1] if parts else knowledge_id
            return float(num_part)
        except:
            return float('inf')
