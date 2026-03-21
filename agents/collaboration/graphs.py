"""
网状协作模式

V2.0版本
创建日期: 2026-03-21

特点:
- 复杂依赖，多路汇聚
- 任意DAG结构
- 适用于复杂场景，需要多个Agent协作
"""

from ..priority import AgentTask, TaskPriority
from typing import List, Dict, Any
import uuid


class GraphNode:
    """
    图节点

    表示协作图中的一个节点
    """

    def __init__(self, agent_type: str, payload: Dict[str, Any], node_id: str):
        """
        初始化图节点

        Args:
            agent_type: Agent类型
            payload: 任务载荷
            node_id: 节点ID
        """
        self.agent_type = agent_type
        self.payload = payload
        self.node_id = node_id
        self.dependencies: List[str] = []


class GraphCollaboration:
    """
    网状协作模式

    任务按DAG结构组织，支持复杂依赖关系
    适用于: 复杂生成流程、多阶段处理
    """

    @staticmethod
    def create_graph(nodes: List[GraphNode], prefix: str = "") -> List[AgentTask]:
        """
        将图结构转换为任务列表

        Args:
            nodes: 图节点列表
            prefix: 任务ID前缀

        Returns:
            AgentTask列表
        """
        tasks = []

        # 创建任务
        for node in nodes:
            task = AgentTask(
                task_id=f"{prefix}{node.node_id}",
                agent_type=node.agent_type,
                priority=TaskPriority.HIGH,
                payload=node.payload,
                dependencies=node.dependencies,
            )
            tasks.append(task)

        return tasks

    @staticmethod
    def validate_dag(nodes: List[GraphNode]) -> bool:
        """
        验证图是否为DAG（无循环依赖）

        Args:
            nodes: 图节点列表

        Returns:
            是否为有效DAG
        """
        # 构建邻接表
        graph: Dict[str, List[str]] = {}
        in_degree: Dict[str, int] = {}

        for node in nodes:
            graph[node.node_id] = node.dependencies
            in_degree[node.node_id] = 0

        # 计算入度
        for node in nodes:
            for dep_id in node.dependencies:
                if dep_id in in_degree:
                    in_degree[node.node_id] += 1

        # 拓扑排序
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited = 0

        while queue:
            current = queue.pop(0)
            visited += 1

            for node in nodes:
                if current in node.dependencies:
                    in_degree[node.node_id] -= 1
                    if in_degree[node.node_id] == 0:
                        queue.append(node.node_id)

        return visited == len(nodes)


def create_complex_generation_graph(generation_data: Dict) -> List[AgentTask]:
    """
    创建复杂生成任务图

    结构:
    - 第一层: 并行准备
      - 上下文构建
      - 风格检查
    - 第二层: 主生成（依赖第一层）
    - 第三层: 并行验证（依赖第二层）
      - 内容验证
      - 质量验证
    - 第四层: 聚合（依赖第三层）

    Args:
        generation_data: 生成数据

    Returns:
        任务图
    """
    # 节点定义
    nodes = [
        # 第一层: 并行准备
        GraphNode(
            agent_type="context_builder", payload=generation_data, node_id="context"
        ),
        GraphNode(
            agent_type="style_learner", payload=generation_data, node_id="style_check"
        ),
        # 第二层: 主生成
        GraphNode(
            agent_type="iterative_generator",
            payload=generation_data,
            node_id="main_gen",
        ),
        # 第三层: 并行验证
        GraphNode(
            agent_type="weighted_validator",
            payload={**generation_data, "aspect": "content"},
            node_id="content_valid",
        ),
        GraphNode(
            agent_type="weighted_validator",
            payload={**generation_data, "aspect": "quality"},
            node_id="quality_valid",
        ),
        # 第四层: 聚合
        GraphNode(
            agent_type="result_aggregator", payload=generation_data, node_id="aggregate"
        ),
    ]

    # 设置依赖关系
    nodes[2].dependencies = ["context", "style_check"]  # main_gen
    nodes[3].dependencies = ["main_gen"]  # content_valid
    nodes[4].dependencies = ["main_gen"]  # quality_valid
    nodes[5].dependencies = ["content_valid", "quality_valid"]  # aggregate

    return GraphCollaboration.create_graph(nodes, prefix="complex_")


def create_batch_generation_graph(batch_data: Dict) -> List[AgentTask]:
    """
    创建批量生成任务图

    结构:
    - 准备阶段
      - 大纲解析
      - 世界观解析
    - 并行生成（每个章节）
      - 章节生成1
      - 章节生成2
      - ...
    - 合并

    Args:
        batch_data: 批量数据

    Returns:
        任务图
    """
    chapters = batch_data.get("chapters", [])

    nodes = [
        # 准备阶段
        GraphNode(
            agent_type="outline_parser", payload=batch_data, node_id="outline_parse"
        ),
        GraphNode(
            agent_type="worldview_parser", payload=batch_data, node_id="worldview_parse"
        ),
    ]

    # 并行生成各章节
    chapter_ids = []
    for i, chapter_data in enumerate(chapters):
        chapter_id = f"chapter_{i}"
        chapter_ids.append(chapter_id)

        node = GraphNode(
            agent_type="iterative_generator",
            payload={**batch_data, "chapter": chapter_data},
            node_id=chapter_id,
        )
        node.dependencies = ["outline_parse", "worldview_parse"]
        nodes.append(node)

    # 合并
    aggregate_node = GraphNode(
        agent_type="result_aggregator", payload=batch_data, node_id="merge"
    )
    aggregate_node.dependencies = chapter_ids
    nodes.append(aggregate_node)

    return GraphCollaboration.create_graph(nodes, prefix="batch_")
