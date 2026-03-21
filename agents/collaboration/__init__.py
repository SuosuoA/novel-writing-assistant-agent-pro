"""
Agent协作模式

V2.0版本
创建日期: 2026-03-21

支持三种协作模式:
- 链式(Chain): 线性串联，顺序执行
- 树状(Tree): 并行分支，任务分解
- 网状(Graph): 复杂依赖，多路汇聚
"""

from .chains import ChainCollaboration, create_generation_chain
from .trees import TreeCollaboration, TreeNode, create_analysis_tree
from .graphs import GraphCollaboration, GraphNode, create_complex_generation_graph

__all__ = [
    # Chain
    "ChainCollaboration",
    "create_generation_chain",
    # Tree
    "TreeCollaboration",
    "TreeNode",
    "create_analysis_tree",
    # Graph
    "GraphCollaboration",
    "GraphNode",
    "create_complex_generation_graph",
]
