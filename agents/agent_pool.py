"""
Agent池管理器

V2.1版本 - 安全加固
创建日期: 2026-03-21
更新日期: 2026-03-24

特性:
- Agent注册与管理
- 热插拔支持
- 健康检查
- 审计日志（P2-1安全修复）
"""

import threading
import logging
import json
import os
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

from .base_agent import BaseAgent
from .agent_state import AgentState
from core.event_bus import EventBus

logger = logging.getLogger(__name__)


# === P2-1: 审计日志系统 ===

@dataclass
class AuditEntry:
    """审计日志条目"""
    timestamp: str
    action: str          # register, unregister, initialize, cleanup, reload
    agent_type: str
    success: bool
    details: Dict[str, Any]
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AgentAuditLogger:
    """
    Agent审计日志记录器（P2-1安全修复）
    
    功能:
    - 记录所有Agent注册/注销操作
    - 持久化到文件
    - 支持审计查询
    """
    
    def __init__(self, log_dir: str = None):
        """
        初始化审计日志记录器
        
        Args:
            log_dir: 日志目录，默认为项目根目录下的logs/audit
        """
        if log_dir is None:
            # 默认使用项目根目录
            project_root = Path(__file__).parent.parent
            log_dir = project_root / "logs" / "audit"
        
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        
        # 当日日志文件
        self._current_log_file = None
        self._current_date = None
        self._lock = threading.Lock()
    
    def _get_log_file(self) -> Path:
        """获取当日日志文件路径"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._current_date != today:
            self._current_date = today
            self._current_log_file = self._log_dir / f"agent_audit_{today}.log"
        return self._current_log_file
    
    def log(self, action: str, agent_type: str, success: bool, 
            details: Dict[str, Any] = None, error: str = None) -> None:
        """
        记录审计日志
        
        Args:
            action: 操作类型 (register, unregister, initialize, cleanup, reload)
            agent_type: Agent类型
            success: 是否成功
            details: 详细信息
            error: 错误信息（如有）
        """
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            agent_type=agent_type,
            success=success,
            details=details or {},
            error=error
        )
        
        with self._lock:
            log_file = self._get_log_file()
            try:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"写入审计日志失败: {e}")
    
    def query(self, agent_type: str = None, action: str = None, 
              start_date: str = None, end_date: str = None) -> List[Dict]:
        """
        查询审计日志
        
        Args:
            agent_type: Agent类型过滤
            action: 操作类型过滤
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            
        Returns:
            匹配的审计日志条目列表
        """
        results = []
        
        # 确定要查询的日志文件
        if start_date and end_date:
            # 查询日期范围
            from datetime import datetime, timedelta
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            date_range = []
            current = start
            while current <= end:
                date_range.append(current.strftime("%Y-%m-%d"))
                current += timedelta(days=1)
            log_files = [self._log_dir / f"agent_audit_{d}.log" for d in date_range]
        else:
            log_files = [self._get_log_file()]
        
        for log_file in log_files:
            if not log_file.exists():
                continue
            
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            # 应用过滤条件
                            if agent_type and entry.get("agent_type") != agent_type:
                                continue
                            if action and entry.get("action") != action:
                                continue
                            results.append(entry)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.error(f"读取审计日志失败: {e}")
        
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取审计统计信息
        
        Returns:
            统计信息字典
        """
        today_logs = self.query(start_date=self._current_date, end_date=self._current_date)
        
        stats = {
            "total_operations_today": len(today_logs),
            "successful_today": sum(1 for e in today_logs if e.get("success")),
            "failed_today": sum(1 for e in today_logs if not e.get("success")),
            "by_action": {},
            "by_agent": {},
        }
        
        for entry in today_logs:
            action = entry.get("action", "unknown")
            agent_type = entry.get("agent_type", "unknown")
            
            stats["by_action"][action] = stats["by_action"].get(action, 0) + 1
            stats["by_agent"][agent_type] = stats["by_agent"].get(agent_type, 0) + 1
        
        return stats


class AgentPool:
    """
    Agent池

    管理所有Agent实例，提供注册、注销、获取等功能
    
    V2.1安全加固:
    - P2-1: 添加审计日志
    """

    def __init__(self, event_bus: EventBus, audit_logger: AgentAuditLogger = None):
        """
        初始化Agent池

        Args:
            event_bus: 事件总线实例
            audit_logger: 审计日志记录器（可选，不提供则创建默认实例）
        """
        self._agents: Dict[str, BaseAgent] = {}
        self._event_bus = event_bus
        self._initialized = False
        self._lock = threading.RLock()
        
        # P2-1: 审计日志记录器
        self._audit_logger = audit_logger or AgentAuditLogger()

    def initialize(self) -> Dict[str, bool]:
        """
        初始化Agent池

        Returns:
            各Agent初始化结果 {agent_type: success}

        P1-6修复：增强部分失败时的状态一致性处理
        """
        if self._initialized:
            return {"already_initialized": True}

        results: Dict[str, bool] = {}
        failed_agents: List[str] = []
        partial_success = False  # P1-6修复：标记是否有部分成功

        with self._lock:
            # 初始化所有已注册的Agent
            for agent_type, agent in self._agents.items():
                if not agent.is_initialized:
                    try:
                        success = agent.initialize()
                        results[agent_type] = success
                        if success:
                            logger.info(f"Agent初始化成功: {agent_type}")
                            partial_success = True  # P1-6修复：有成功案例
                        else:
                            failed_agents.append(agent_type)
                            logger.error(f"Agent初始化失败 {agent_type}: 返回False")
                    except Exception as e:
                        results[agent_type] = False
                        failed_agents.append(agent_type)
                        logger.error(f"Agent初始化异常 {agent_type}: {e}", exc_info=True)

            # P1-6修复：只有全部成功才标记为已初始化
            # 但即使部分失败，已成功的Agent仍可使用
            self._initialized = len(failed_agents) == 0

            if failed_agents:
                # P1-6修复：发布部分失败事件
                self._event_bus.publish(
                    "agent.pool.partial_failure",
                    {
                        "failed_agents": failed_agents,
                        "successful_agents": [
                                a for a in self._agents.keys() 
                                if a not in failed_agents
                            ],
                        "can_continue": partial_success,  # 是否可以继续运行
                    },
                    source="AgentPool",
                )
                logger.warning(
                    f"部分Agent初始化失败: {failed_agents}, "
                    f"可用Agent: {[a for a in self._agents.keys() if a not in failed_agents]}"
                )
            else:
                # 发布Agent池就绪事件
                self._event_bus.publish(
                    "agent.pool.ready",
                    {"agents": list(self._agents.keys())},
                    source="AgentPool",
                )
                logger.info(f"Agent池初始化完成，共 {len(self._agents)} 个Agent")

        return results

    def register_agent(self, agent: BaseAgent) -> bool:
        """
        注册Agent

        Args:
            agent: Agent实例

        Returns:
            是否注册成功
            
        P2-1安全修复: 添加审计日志记录
        """
        with self._lock:
            is_overwrite = agent.agent_type in self._agents
            if is_overwrite:
                logger.warning(f"Agent已存在，将覆盖: {agent.agent_type}")

            try:
                # 如果Agent池已初始化，立即初始化新Agent
                if self._initialized:
                    if not agent.initialize():
                        error_msg = f"Agent初始化失败: {agent.agent_type}"
                        logger.error(error_msg)
                        
                        # P2-1: 记录审计日志
                        self._audit_logger.log(
                            action="register",
                            agent_type=agent.agent_type,
                            success=False,
                            details={"reason": "initialize_failed", "is_overwrite": is_overwrite},
                            error=error_msg
                        )
                        return False

                self._agents[agent.agent_type] = agent

                # 发布Agent注册事件
                self._event_bus.publish(
                    "agent.registered",
                    {"agent_type": agent.agent_type, "is_overwrite": is_overwrite},
                    source="AgentPool",
                )
                
                # P2-1: 记录审计日志
                self._audit_logger.log(
                    action="register",
                    agent_type=agent.agent_type,
                    success=True,
                    details={
                        "is_overwrite": is_overwrite,
                        "agent_class": agent.__class__.__name__,
                        "initialized": self._initialized
                    }
                )

                logger.info(f"Agent注册成功: {agent.agent_type}")
                return True

            except Exception as e:
                error_msg = f"Agent注册失败 {agent.agent_type}: {e}"
                logger.error(error_msg)
                
                # P2-1: 记录审计日志
                self._audit_logger.log(
                    action="register",
                    agent_type=agent.agent_type,
                    success=False,
                    details={"reason": "exception", "is_overwrite": is_overwrite},
                    error=str(e)
                )
                return False

    def unregister_agent(self, agent_type: str) -> bool:
        """
        注销Agent

        Args:
            agent_type: Agent类型

        Returns:
            是否注销成功
            
        P2-1安全修复: 添加审计日志记录
        """
        with self._lock:
            if agent_type not in self._agents:
                # P2-1: 记录审计日志
                self._audit_logger.log(
                    action="unregister",
                    agent_type=agent_type,
                    success=False,
                    details={"reason": "not_found"}
                )
                return False

            try:
                agent = self._agents[agent_type]
                agent_class = agent.__class__.__name__

                # 清理资源
                agent.cleanup()

                # 从池中移除
                del self._agents[agent_type]

                # 发布Agent注销事件
                self._event_bus.publish(
                    "agent.unregistered", {"agent_type": agent_type}, source="AgentPool"
                )
                
                # P2-1: 记录审计日志
                self._audit_logger.log(
                    action="unregister",
                    agent_type=agent_type,
                    success=True,
                    details={"agent_class": agent_class}
                )

                logger.info(f"Agent注销成功: {agent_type}")
                return True

            except Exception as e:
                error_msg = f"Agent注销失败 {agent_type}: {e}"
                logger.error(error_msg)
                
                # P2-1: 记录审计日志
                self._audit_logger.log(
                    action="unregister",
                    agent_type=agent_type,
                    success=False,
                    details={"reason": "exception"},
                    error=str(e)
                )
                return False

    def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        """
        获取Agent实例

        Args:
            agent_type: Agent类型

        Returns:
            Agent实例，不存在返回None
        """
        with self._lock:
            return self._agents.get(agent_type)

    def list_agents(self) -> List[str]:
        """
        列出所有Agent类型

        Returns:
            Agent类型列表
        """
        with self._lock:
            return list(self._agents.keys())

    def get_active_agents(self) -> List[str]:
        """
        获取所有活跃状态的Agent

        Returns:
            活跃Agent类型列表
        """
        with self._lock:
            return [
                agent_type
                for agent_type, agent in self._agents.items()
                if agent.status.state == AgentState.ACTIVE
            ]

    def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """
        检查所有Agent健康状态

        Returns:
            各Agent健康状态
        """
        results = {}
        with self._lock:
            for agent_type, agent in self._agents.items():
                try:
                    results[agent_type] = agent.health_check()
                except Exception as e:
                    results[agent_type] = {"status": "error", "error": str(e)}
        return results

    def cleanup_all(self) -> None:
        """清理所有Agent资源"""
        with self._lock:
            for agent_type, agent in self._agents.items():
                try:
                    agent.cleanup()
                except Exception as e:
                    logger.error(f"清理Agent失败 {agent_type}: {e}")

            self._agents.clear()
            self._initialized = False

            logger.info("Agent池已清理")

    def reload_agent(self, agent_type: str) -> bool:
        """
        重新加载Agent

        Args:
            agent_type: Agent类型

        Returns:
            是否重载成功
            
        P2-1安全修复: 添加审计日志记录
        """
        with self._lock:
            agent = self._agents.get(agent_type)
            if not agent:
                logger.warning(f"Agent不存在: {agent_type}")
                
                # P2-1: 记录审计日志
                self._audit_logger.log(
                    action="reload",
                    agent_type=agent_type,
                    success=False,
                    details={"reason": "not_found"}
                )
                return False

            try:
                agent_class = agent.__class__.__name__
                
                # 先清理
                agent.cleanup()

                # 重新初始化
                if agent.initialize():
                    # P2-1: 记录审计日志
                    self._audit_logger.log(
                        action="reload",
                        agent_type=agent_type,
                        success=True,
                        details={"agent_class": agent_class}
                    )
                    logger.info(f"Agent重载成功: {agent_type}")
                    return True
                else:
                    error_msg = f"Agent重载失败: {agent_type}"
                    logger.error(error_msg)
                    
                    # P2-1: 记录审计日志
                    self._audit_logger.log(
                        action="reload",
                        agent_type=agent_type,
                        success=False,
                        details={"reason": "initialize_failed", "agent_class": agent_class},
                        error="Agent.initialize() returned False"
                    )
                    return False

            except Exception as e:
                error_msg = f"Agent重载异常 {agent_type}: {e}"
                logger.error(error_msg)
                
                # P2-1: 记录审计日志
                self._audit_logger.log(
                    action="reload",
                    agent_type=agent_type,
                    success=False,
                    details={"reason": "exception"},
                    error=str(e)
                )
                return False

    def get_agent_count(self) -> int:
        """获取Agent数量"""
        with self._lock:
            return len(self._agents)

    def is_ready(self) -> bool:
        """Agent池是否就绪"""
        return self._initialized
    
    # P2-1: 审计日志接口
    def get_audit_statistics(self) -> Dict[str, Any]:
        """
        获取审计统计信息
        
        Returns:
            统计信息字典
        """
        return self._audit_logger.get_statistics()
    
    def query_audit_logs(self, agent_type: str = None, action: str = None,
                         start_date: str = None, end_date: str = None) -> List[Dict]:
        """
        查询审计日志
        
        Args:
            agent_type: Agent类型过滤
            action: 操作类型过滤
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            
        Returns:
            匹配的审计日志条目列表
        """
        return self._audit_logger.query(
            agent_type=agent_type,
            action=action,
            start_date=start_date,
            end_date=end_date
        )

    # P1-1修复：添加内置Agent注册方法
    def _register_builtin_agents(self) -> Dict[str, bool]:
        """
        注册内置Agent适配器

        将4个V5核心插件包装为Agent并注册到Agent池。

        Returns:
            各Agent注册结果 {agent_type: success}
        """
        from .plugins import (
            OutlineAnalysisAgent,
            StyleLearningAgent,
            NovelGenerationAgent,
            QualityValidationAgent,
        )

        results: Dict[str, bool] = {}
        adapters = [
            OutlineAnalysisAgent(),
            StyleLearningAgent(),
            NovelGenerationAgent(),
            QualityValidationAgent(),
        ]

        for agent in adapters:
            success = self.register_agent(agent)
            results[agent.agent_type] = success
            if success:
                logger.info(f"内置Agent注册成功: {agent.agent_type}")
            else:
                logger.error(f"内置Agent注册失败: {agent.agent_type}")

        # 发布内置Agent注册完成事件
        self._event_bus.publish(
            "agent.pool.builtin_registered",
            {
                "total": len(adapters),
                "success_count": sum(1 for v in results.values() if v),
                "results": results,
            },
            source="AgentPool",
        )

        logger.info(
            f"内置Agent注册完成: {sum(1 for v in results.values() if v)}/{len(adapters)} 成功"
        )
        return results
