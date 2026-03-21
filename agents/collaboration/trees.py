"""
树状协作模式

V2.0版本
创建日期: 2026-03-21

特点:
- 并行分支，任务分解
- 父任务依赖子任务
- 适用于需要多个Agent同时处理子任务的场景
"""

from ..priority import AgentTask, TaskPriority
from typing import List, Dict, Any, Optional
import uuid


class TreeNode:
    """
    树节点

    表示协作树中的一个节点
    """

    def __init__(
        self,
        agent_type: str,
        payload: Dict[str, Any],
        children: List["TreeNode"] = None,
        node_id: str = None,
    ):
        """
        初始化树节点

        Args:
            agent_type: Agent类型
            payload: 任务载荷
            children: 子节点列表
            node_id: 节点ID
        """
        self.agent_type = agent_type
        self.payload = payload
        self.children = children or []
        self.node_id = node_id or f"node_{uuid.uuid4().hex[:8]}"


class TreeCollaboration:
    """
    树状协作模式

    任务按树状结构组织，父任务依赖所有子任务
    适用于: 并行分析、多角度评估
    """

    @staticmethod
    def create_tree(root: TreeNode, prefix: str = "") -> List[AgentTask]:
        """
        将树结构转换为任务列表

        Args:
            root: 树根节点
            prefix: 任务ID前缀

        Returns:
            AgentTask列表
        """
        tasks = []
        task_map = {}  # node_id -> task_id

        # 后序遍历构建任务（先子后父）
        def build_tasks(node: TreeNode):
            # 递归处理子节点
            for child in node.children:
                build_tasks(child)

            # 创建当前节点任务
            task_id = f"{prefix}{node.node_id}"

            # 依赖所有子任务
            dependencies = [
                task_map[child.node_id]
                for child in node.children
                if child.node_id in task_map
            ]

            task = AgentTask(
                task_id=task_id,
                agent_type=node.agent_type,
                priority=TaskPriority.HIGH,
                payload=node.payload,
                dependencies=dependencies,
            )

            task_map[node.node_id] = task_id
            tasks.append(task)

        build_tasks(root)
        return tasks


def create_analysis_tree(analysis_data: Dict) -> List[AgentTask]:
    """
    创建分析任务树

    结构:
    - 协调者
      - 风格分析
      - 人物分析
      - 世界观分析

    Args:
        analysis_data: 分析数据

    Returns:
        任务树
    """
    # 根节点: 分析协调者
    root = TreeNode(
        agent_type="analyzer_coordinator", payload=analysis_data, node_id="coordinator"
    )

    # 子节点: 并行分析
    root.children = [
        TreeNode(
            agent_type="style_learner",
            payload={**analysis_data, "aspect": "style"},
            node_id="style_analysis",
        ),
        TreeNode(
            agent_type="character_manager",
            payload={**analysis_data, "aspect": "character"},
            node_id="character_analysis",
        ),
        TreeNode(
            agent_type="worldview_parser",
            payload={**analysis_data, "aspect": "worldview"},
            node_id="worldview_analysis",
        ),
    ]

    return TreeCollaboration.create_tree(root, prefix="analysis_")


def create_validation_tree(validation_data: Dict) -> List[AgentTask]:
    """
    创建验证任务树

    结构:
    - 验证聚合
      - 内容验证
      - 风格验证
      - 人设验证
      - 世界观验证

    Args:
        validation_data: 验证数据

    Returns:
        任务树
    """
    root = TreeNode(
        agent_type="validation_aggregator",
        payload=validation_data,
        node_id="aggregator",
    )

    root.children = [
        TreeNode(
            agent_type="weighted_validator",
            payload={**validation_data, "aspect": "content"},
            node_id="content_validation",
        ),
        TreeNode(
            agent_type="style_learner",
            payload={**validation_data, "aspect": "style"},
            node_id="style_validation",
        ),
        TreeNode(
            agent_type="character_manager",
            payload={**validation_data, "aspect": "character"},
            node_id="character_validation",
        ),
        TreeNode(
            agent_type="worldview_parser",
            payload={**validation_data, "aspect": "worldview"},
            node_id="worldview_validation",
        ),
    ]

    return TreeCollaboration.create_tree(root, prefix="validation_")
