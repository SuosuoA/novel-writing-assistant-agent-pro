"""
Agent基类定义 - 向后兼容层

V2.1版本 (向后兼容)
更新日期: 2026-03-23

重要说明:
- 此文件已废弃，仅作为向后兼容层
- 新代码请使用 agents.core.base_agent 中的 BaseAgent
- agents.core/ 是主要版本，包含完整功能
- agents/ 根目录是旧版本，仅保留向后兼容

迁移指南:
```python
# 旧代码 (已废弃)
from agents.base_agent import BaseAgent

# 新代码 (推荐)
from agents.core.base_agent import BaseAgent
```

版本差异:
- agents/core/base_agent.py: V1.0 (主要版本)
  - 支持 ServiceLocator 集成
  - 完整的 AgentMetadata/AgentContext/AgentResult 类型定义
  - 支持 get_service()/get_config()/get_logger()/get_event_bus()

- agents/base_agent.py: V2.0 (已废弃)
  - 不支持 ServiceLocator
  - execute 签名不同: execute(task: AgentTask) -> Any
"""

# 向后兼容: 从 core 导入所有类型
from agents.core.base_agent import (
    BaseAgent,
    AgentMetadata,
    AgentContext,
    AgentResult,
    AgentState,
    AgentStatus,
    AgentCapability,
)

# 向后兼容: 导入 AgentTask dataclass
from agents.priority import AgentTask, TaskPriority

# 模块版本标识
__all__ = [
    "BaseAgent",
    "AgentMetadata", 
    "AgentContext",
    "AgentResult",
    "AgentState",
    "AgentStatus",
    "AgentCapability",
    "AgentTask",
    "TaskPriority",
]

__version__ = "2.1.0"
__deprecated__ = True
__replacement__ = "agents.core.base_agent"
