#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识库知识点关联网络 - V1.0
创建日期: 2026-03-29

用途:
- 构建知识点之间的关联关系
- 支持相似知识点检索
- 增强知识库召回效果

核心功能:
1. 构建知识点关联网络
2. 计算知识点相似度
3. 检索相关知识点
"""

import json
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pydantic import BaseModel, Field, ConfigDict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================

class KnowledgeRelation(BaseModel):
    """知识点关联关系数据模型"""
    model_config = ConfigDict(frozen=False)
    
    source_id: str = Field(..., description="源知识点ID")
    target_id: str = Field(..., description="目标知识点ID")
    relation_type: str = Field("related", description="关系类型(related/similar/extends)")
    weight: float = Field(0.0, description="关联权重(0-1)")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class KnowledgeGraphNode(BaseModel):
    """知识点节点数据模型"""
    model_config = ConfigDict(frozen=False)
    
    knowledge_id: str = Field(..., description="知识点ID")
    title: str = Field(..., description="标题")
    category: str = Field("", description="分类")
    domain: str = Field("", description="领域")
    keywords: List[str] = Field(default_factory=list, description="关键词")
    connections: int = Field(0, description="关联数量")


# ============================================================================
# 知识图谱
# ============================================================================

class KnowledgeGraph:
    """
    知识库知识点关联网络
    
    用于构建和管理知识点之间的关联关系，
    支持相似度检索和关联推荐。
    """
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.data_dir = workspace / "data" / "knowledge"
        self.graph_file = workspace / "data" / "knowledge_graph.json"
        
        # 确保目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 图数据结构
        self.nodes: Dict[str, KnowledgeGraphNode] = {}
        self.relations: List[KnowledgeRelation] = []
        
        # 邻接表（用于快速查找关联）
        self.adjacency: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        
        # 加载数据
        self._load_graph()
        self._load_knowledge_nodes()
    
    def build_relationships(self, similarity_threshold: float = 0.5) -> int:
        """
        构建知识点关联关系
        
        Args:
            similarity_threshold: 相似度阈值(0-1)
        
        Returns:
            int: 创建的关联数量
        """
        logger.info("[KnowledgeGraph] 开始构建知识点关联关系...")
        
        all_knowledge = self._load_all_knowledge()
        
        if len(all_knowledge) < 2:
            logger.warning("[KnowledgeGraph] 知识点数量不足")
            return 0
        
        # 清空旧关联
        self.relations = []
        self.adjacency = defaultdict(list)
        
        # 计算两两相似度
        total_pairs = len(all_knowledge) * (len(all_knowledge) - 1) // 2
        processed = 0
        
        for i, kp1 in enumerate(all_knowledge):
            for kp2 in all_knowledge[i+1:]:
                # 计算相似度
                similarity = self._calculate_similarity(kp1, kp2)
                
                if similarity >= similarity_threshold:
                    relation = KnowledgeRelation(
                        source_id=kp1.get("knowledge_id", ""),
                        target_id=kp2.get("knowledge_id", ""),
                        relation_type="related",
                        weight=similarity
                    )
                    self.relations.append(relation)
                    
                    # 更新邻接表
                    self.adjacency[relation.source_id].append(
                        (relation.target_id, relation.weight)
                    )
                    self.adjacency[relation.target_id].append(
                        (relation.source_id, relation.weight)
                    )
                
                processed += 1
                if processed % 1000 == 0:
                    logger.info(f"[KnowledgeGraph] 处理进度: {processed}/{total_pairs}")
        
        # 更新节点的连接数
        for node_id, connections in self.adjacency.items():
            if node_id in self.nodes:
                self.nodes[node_id].connections = len(connections)
        
        # 保存图数据
        self._save_graph()
        
        logger.info(f"[KnowledgeGraph] 构建完成: {len(self.relations)} 条关联关系")
        return len(self.relations)
    
    def get_related_knowledge(
        self, 
        knowledge_id: str, 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        获取相关知识点
        
        Args:
            knowledge_id: 知识点ID
            top_k: 返回数量
        
        Returns:
            List: 相关知识点列表
        """
        if knowledge_id not in self.adjacency:
            return []
        
        # 获取关联节点并按权重排序
        related = sorted(
            self.adjacency[knowledge_id],
            key=lambda x: x[1],
            reverse=True
        )[:top_k]
        
        results = []
        for related_id, weight in related:
            if related_id in self.nodes:
                node = self.nodes[related_id]
                results.append({
                    "knowledge_id": related_id,
                    "title": node.title,
                    "category": node.category,
                    "domain": node.domain,
                    "similarity": weight
                })
        
        return results
    
    def find_knowledge_path(
        self, 
        start_id: str, 
        end_id: str, 
        max_depth: int = 3
    ) -> List[str]:
        """
        查找两个知识点之间的路径
        
        Args:
            start_id: 起点知识点ID
            end_id: 终点知识点ID
            max_depth: 最大搜索深度
        
        Returns:
            List: 路径上的知识点ID列表
        """
        if start_id not in self.adjacency or end_id not in self.adjacency:
            return []
        
        # BFS搜索
        from collections import deque
        
        queue = deque([(start_id, [start_id])])
        visited = {start_id}
        
        while queue:
            current, path = queue.popleft()
            
            if current == end_id:
                return path
            
            if len(path) > max_depth:
                continue
            
            for neighbor, _ in self.adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        
        return []  # 未找到路径
    
    def get_cluster_stats(self) -> Dict[str, Any]:
        """
        获取知识图谱聚类统计
        
        Returns:
            Dict: 统计信息
        """
        # 计算连通分量
        visited = set()
        clusters = []
        
        for node_id in self.nodes:
            if node_id not in visited:
                # BFS找连通分量
                cluster = []
                queue = [node_id]
                
                while queue:
                    current = queue.pop(0)
                    if current not in visited:
                        visited.add(current)
                        cluster.append(current)
                        queue.extend(
                            neighbor for neighbor, _ in self.adjacency[current]
                            if neighbor not in visited
                        )
                
                clusters.append(cluster)
        
        # 统计
        cluster_sizes = [len(c) for c in clusters]
        
        return {
            "total_nodes": len(self.nodes),
            "total_relations": len(self.relations),
            "cluster_count": len(clusters),
            "largest_cluster_size": max(cluster_sizes) if cluster_sizes else 0,
            "avg_cluster_size": sum(cluster_sizes) / len(clusters) if clusters else 0,
            "isolated_nodes": sum(1 for s in cluster_sizes if s == 1),
            "density": self._calculate_density()
        }
    
    def _calculate_density(self) -> float:
        """计算图密度"""
        n = len(self.nodes)
        if n < 2:
            return 0.0
        
        max_edges = n * (n - 1) / 2
        actual_edges = len(self.relations)
        
        return actual_edges / max_edges
    
    def _calculate_similarity(self, kp1: Dict, kp2: Dict) -> float:
        """
        计算两个知识点的相似度
        
        综合考虑：
        1. 关键词重叠度
        2. 领域相同
        3. 分类相同
        """
        # 1. 关键词相似度（Jaccard系数）
        keywords1 = set(kp1.get("keywords", []))
        keywords2 = set(kp2.get("keywords", []))
        
        if keywords1 or keywords2:
            keyword_sim = len(keywords1 & keywords2) / len(keywords1 | keywords2)
        else:
            keyword_sim = 0.0
        
        # 2. 领域相同加分
        domain_sim = 0.2 if kp1.get("domain") == kp2.get("domain") else 0.0
        
        # 3. 分类相同加分
        category_sim = 0.1 if kp1.get("category") == kp2.get("category") else 0.0
        
        # 4. 内容相似度（简化：基于关键词）
        # 如果关键词重叠度高，认为内容相似
        content_sim = keyword_sim * 0.5
        
        # 加权综合
        total_sim = keyword_sim * 0.5 + domain_sim + category_sim + content_sim
        
        return min(1.0, total_sim)
    
    def _load_all_knowledge(self) -> List[Dict]:
        """加载所有知识点"""
        all_knowledge = []
        
        if not self.data_dir.exists():
            return all_knowledge
        
        for category_dir in self.data_dir.iterdir():
            if not category_dir.is_dir():
                continue
            
            for json_file in category_dir.glob("*.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    for kp in data.get("knowledge_points", []):
                        all_knowledge.append(kp)
                        
                except Exception as e:
                    logger.warning(f"[KnowledgeGraph] 加载失败: {json_file}, {e}")
        
        logger.info(f"[KnowledgeGraph] 加载了 {len(all_knowledge)} 个知识点")
        return all_knowledge
    
    def _load_knowledge_nodes(self):
        """加载知识点节点信息"""
        all_knowledge = self._load_all_knowledge()
        
        for kp in all_knowledge:
            node_id = kp.get("knowledge_id", "")
            if node_id:
                self.nodes[node_id] = KnowledgeGraphNode(
                    knowledge_id=node_id,
                    title=kp.get("title", ""),
                    category=kp.get("category", ""),
                    domain=kp.get("domain", ""),
                    keywords=kp.get("keywords", [])
                )
    
    def _load_graph(self):
        """加载图数据"""
        if not self.graph_file.exists():
            return
        
        try:
            with open(self.graph_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 加载关联关系
            for rel_data in data.get("relations", []):
                relation = KnowledgeRelation(**rel_data)
                self.relations.append(relation)
                
                # 更新邻接表
                self.adjacency[relation.source_id].append(
                    (relation.target_id, relation.weight)
                )
                self.adjacency[relation.target_id].append(
                    (relation.source_id, relation.weight)
                )
            
            logger.info(f"[KnowledgeGraph] 加载了 {len(self.relations)} 条关联关系")
            
        except Exception as e:
            logger.warning(f"[KnowledgeGraph] 加载图数据失败: {e}")
    
    def _save_graph(self):
        """保存图数据"""
        data = {
            "updated_at": datetime.now().isoformat(),
            "total_nodes": len(self.nodes),
            "total_relations": len(self.relations),
            "relations": [r.model_dump() for r in self.relations]
        }
        
        with open(self.graph_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"[KnowledgeGraph] 图数据已保存: {self.graph_file}")


# ============================================================================
# 全局单例
# ============================================================================

_knowledge_graph_instance: Optional[KnowledgeGraph] = None


def get_knowledge_graph(workspace: Optional[Path] = None) -> KnowledgeGraph:
    """获取全局知识图谱实例"""
    global _knowledge_graph_instance
    
    if _knowledge_graph_instance is None:
        if workspace is None:
            workspace = project_root
        _knowledge_graph_instance = KnowledgeGraph(workspace)
    
    return _knowledge_graph_instance


# ============================================================================
# 主函数
# ============================================================================

def main():
    """测试入口"""
    kg = get_knowledge_graph(project_root)
    
    print("\n" + "="*60)
    print("知识图谱测试")
    print("="*60)
    
    # 构建关联关系
    if len(kg.nodes) > 1:
        count = kg.build_relationships(similarity_threshold=0.3)
        print(f"\n创建了 {count} 条关联关系")
    
    # 统计信息
    stats = kg.get_cluster_stats()
    print(f"\n图统计:")
    print(f"  节点数: {stats['total_nodes']}")
    print(f"  边数: {stats['total_relations']}")
    print(f"  聚类数: {stats['cluster_count']}")
    print(f"  最大聚类: {stats['largest_cluster_size']}")
    print(f"  孤立节点: {stats['isolated_nodes']}")
    print(f"  图密度: {stats['density']:.4f}")
    
    # 测试关联查询
    if kg.nodes:
        sample_id = list(kg.nodes.keys())[0]
        related = kg.get_related_knowledge(sample_id, top_k=3)
        if related:
            print(f"\n知识点 {sample_id} 的相关知识点:")
            for r in related:
                print(f"  - {r['title']} (相似度: {r['similarity']:.2f})")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    main()
