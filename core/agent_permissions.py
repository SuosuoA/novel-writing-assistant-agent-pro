"""
Agent权限模型

V1.0 - P2-3安全修复
创建日期: 2026-03-24

功能:
- Agent权限定义与管理
- 权限检查与验证
- 权限级别控制
- 操作权限审计
"""

import logging
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

logger = logging.getLogger(__name__)


class Permission(Enum):
    """权限枚举"""
    # 文件系统权限
    FILE_READ = auto()          # 读取文件
    FILE_WRITE = auto()         # 写入文件
    FILE_DELETE = auto()        # 删除文件
    FILE_CREATE = auto()        # 创建文件
    
    # 网络权限
    NETWORK_REQUEST = auto()    # 网络请求
    NETWORK_LISTEN = auto()     # 网络监听
    
    # 系统权限
    SYSTEM_CONFIG = auto()      # 系统配置
    SYSTEM_COMMAND = auto()     # 系统命令执行
    SYSTEM_PROCESS = auto()     # 进程管理
    
    # 插件权限
    PLUGIN_LOAD = auto()        # 加载插件
    PLUGIN_UNLOAD = auto()      # 卸载插件
    PLUGIN_EXECUTE = auto()     # 执行插件
    
    # Agent权限
    AGENT_REGISTER = auto()     # 注册Agent
    AGENT_UNREGISTER = auto()   # 注销Agent
    AGENT_EXECUTE = auto()      # 执行Agent任务
    
    # 数据权限
    DATA_READ = auto()          # 读取数据
    DATA_WRITE = auto()         # 写入数据
    DATA_DELETE = auto()        # 删除数据
    
    # LLM权限
    LLM_CALL = auto()           # 调用LLM API
    LLM_STREAM = auto()         # 流式调用LLM


class PermissionLevel(Enum):
    """权限级别"""
    NONE = 0         # 无权限
    MINIMAL = 1      # 最小权限（只读）
    STANDARD = 2     # 标准权限
    ELEVATED = 3     # 提升权限
    ADMIN = 4        # 管理员权限
    SUPER = 5        # 超级权限（系统级）


# 权限级别对应的权限集
LEVEL_PERMISSIONS: Dict[PermissionLevel, Set[Permission]] = {
    PermissionLevel.NONE: set(),
    
    PermissionLevel.MINIMAL: {
        Permission.FILE_READ,
        Permission.DATA_READ,
    },
    
    PermissionLevel.STANDARD: {
        Permission.FILE_READ,
        Permission.FILE_WRITE,
        Permission.FILE_CREATE,
        Permission.NETWORK_REQUEST,
        Permission.PLUGIN_EXECUTE,
        Permission.AGENT_EXECUTE,
        Permission.DATA_READ,
        Permission.DATA_WRITE,
        Permission.LLM_CALL,
        Permission.LLM_STREAM,
    },
    
    PermissionLevel.ELEVATED: {
        Permission.FILE_READ,
        Permission.FILE_WRITE,
        Permission.FILE_DELETE,
        Permission.FILE_CREATE,
        Permission.NETWORK_REQUEST,
        Permission.PLUGIN_LOAD,
        Permission.PLUGIN_EXECUTE,
        Permission.AGENT_EXECUTE,
        Permission.DATA_READ,
        Permission.DATA_WRITE,
        Permission.DATA_DELETE,
        Permission.LLM_CALL,
        Permission.LLM_STREAM,
    },
    
    PermissionLevel.ADMIN: {
        Permission.FILE_READ,
        Permission.FILE_WRITE,
        Permission.FILE_DELETE,
        Permission.FILE_CREATE,
        Permission.NETWORK_REQUEST,
        Permission.NETWORK_LISTEN,
        Permission.SYSTEM_CONFIG,
        Permission.PLUGIN_LOAD,
        Permission.PLUGIN_UNLOAD,
        Permission.PLUGIN_EXECUTE,
        Permission.AGENT_REGISTER,
        Permission.AGENT_UNREGISTER,
        Permission.AGENT_EXECUTE,
        Permission.DATA_READ,
        Permission.DATA_WRITE,
        Permission.DATA_DELETE,
        Permission.LLM_CALL,
        Permission.LLM_STREAM,
    },
    
    PermissionLevel.SUPER: set(Permission),  # 所有权限
}


@dataclass
class AgentPermissionProfile:
    """
    Agent权限配置
    
    定义单个Agent的权限配置
    """
    agent_type: str                          # Agent类型
    level: PermissionLevel = PermissionLevel.STANDARD  # 权限级别
    granted: Set[Permission] = field(default_factory=set)  # 额外授予权限
    denied: Set[Permission] = field(default_factory=set)   # 明确拒绝权限
    path_restrictions: List[str] = field(default_factory=list)  # 路径限制
    rate_limits: Dict[str, int] = field(default_factory=dict)    # 速率限制
    
    def get_effective_permissions(self) -> Set[Permission]:
        """
        获取有效权限集
        
        Returns:
            有效权限集合
        """
        # 从级别权限开始
        effective = LEVEL_PERMISSIONS[self.level].copy()
        
        # 添加额外授权
        effective.update(self.granted)
        
        # 移除明确拒绝的权限
        effective.difference_update(self.denied)
        
        return effective
    
    def has_permission(self, permission: Permission) -> bool:
        """
        检查是否有指定权限
        
        Args:
            permission: 权限枚举值
            
        Returns:
            是否有权限
        """
        return permission in self.get_effective_permissions()
    
    def check_path_access(self, path: str, permission: Permission) -> bool:
        """
        检查路径访问权限
        
        Args:
            path: 文件路径
            permission: 权限类型
            
        Returns:
            是否有权限
        """
        # 先检查基本权限
        if not self.has_permission(permission):
            return False
        
        # 如果没有路径限制，允许所有路径
        if not self.path_restrictions:
            return True
        
        # 检查路径是否在允许范围内
        path_obj = Path(path).resolve()
        for allowed_path in self.path_restrictions:
            allowed_obj = Path(allowed_path).resolve()
            try:
                path_obj.relative_to(allowed_obj)
                return True
            except ValueError:
                continue
        
        return False


class PermissionManager:
    """
    权限管理器（P2-3安全修复）
    
    功能:
    - Agent权限配置管理
    - 权限检查与验证
    - 权限审计日志
    """
    
    # 默认权限配置
    DEFAULT_PROFILES: Dict[str, AgentPermissionProfile] = {
        "MasterAgent": AgentPermissionProfile(
            agent_type="MasterAgent",
            level=PermissionLevel.ADMIN,
        ),
        "ThinkerAgent": AgentPermissionProfile(
            agent_type="ThinkerAgent",
            level=PermissionLevel.STANDARD,
        ),
        "OptimizerAgent": AgentPermissionProfile(
            agent_type="OptimizerAgent",
            level=PermissionLevel.STANDARD,
        ),
        "ValidatorAgent": AgentPermissionProfile(
            agent_type="ValidatorAgent",
            level=PermissionLevel.STANDARD,
            denied={Permission.FILE_DELETE, Permission.DATA_DELETE},
        ),
        "PlannerAgent": AgentPermissionProfile(
            agent_type="PlannerAgent",
            level=PermissionLevel.ELEVATED,
        ),
        "WriterAgent": AgentPermissionProfile(
            agent_type="WriterAgent",
            level=PermissionLevel.STANDARD,
        ),
        "HotRankPlugin": AgentPermissionProfile(
            agent_type="HotRankPlugin",
            level=PermissionLevel.MINIMAL,
            granted={Permission.NETWORK_REQUEST},  # 允许网络请求
        ),
    }
    
    def __init__(self):
        """初始化权限管理器"""
        self._profiles: Dict[str, AgentPermissionProfile] = {}
        self._audit_log: List[Dict[str, Any]] = []
        self._initialized = False
    
    def initialize(self) -> bool:
        """
        初始化权限管理器
        
        Returns:
            是否初始化成功
        """
        try:
            # 加载默认配置
            self._profiles = self.DEFAULT_PROFILES.copy()
            self._initialized = True
            logger.info("权限管理器初始化成功")
            return True
        except Exception as e:
            logger.error(f"权限管理器初始化失败: {e}")
            return False
    
    def register_profile(self, profile: AgentPermissionProfile) -> bool:
        """
        注册Agent权限配置
        
        Args:
            profile: 权限配置
            
        Returns:
            是否注册成功
        """
        try:
            self._profiles[profile.agent_type] = profile
            
            # 记录审计日志
            self._audit_log.append({
                "action": "register_profile",
                "agent_type": profile.agent_type,
                "level": profile.level.name,
                "permissions": [p.name for p in profile.get_effective_permissions()],
            })
            
            logger.info(f"注册权限配置: {profile.agent_type} (级别: {profile.level.name})")
            return True
        except Exception as e:
            logger.error(f"注册权限配置失败: {e}")
            return False
    
    def get_profile(self, agent_type: str) -> Optional[AgentPermissionProfile]:
        """
        获取Agent权限配置
        
        Args:
            agent_type: Agent类型
            
        Returns:
            权限配置，如不存在返回None
        """
        return self._profiles.get(agent_type)
    
    def check_permission(
        self, 
        agent_type: str, 
        permission: Permission,
        context: Dict[str, Any] = None
    ) -> bool:
        """
        检查Agent权限
        
        Args:
            agent_type: Agent类型
            permission: 权限类型
            context: 上下文信息（如路径、操作参数等）
            
        Returns:
            是否有权限
        """
        profile = self._profiles.get(agent_type)
        
        if not profile:
            # 未知Agent，使用最小权限
            logger.warning(f"未知Agent类型: {agent_type}, 使用最小权限")
            profile = AgentPermissionProfile(
                agent_type=agent_type,
                level=PermissionLevel.MINIMAL
            )
        
        # 基本权限检查
        has_perm = profile.has_permission(permission)
        
        # 如果涉及路径访问，进行额外检查
        if has_perm and context and "path" in context:
            has_perm = profile.check_path_access(context["path"], permission)
        
        # 记录审计日志
        self._audit_log.append({
            "action": "check_permission",
            "agent_type": agent_type,
            "permission": permission.name,
            "result": has_perm,
            "context": context,
        })
        
        return has_perm
    
    def elevate_permission(
        self, 
        agent_type: str, 
        permissions: Set[Permission],
        reason: str = ""
    ) -> bool:
        """
        提升Agent权限（临时）
        
        Args:
            agent_type: Agent类型
            permissions: 要添加的权限集
            reason: 提升原因
            
        Returns:
            是否成功
        """
        profile = self._profiles.get(agent_type)
        if not profile:
            return False
        
        # 添加权限
        profile.granted.update(permissions)
        
        # 记录审计日志
        self._audit_log.append({
            "action": "elevate_permission",
            "agent_type": agent_type,
            "permissions": [p.name for p in permissions],
            "reason": reason,
        })
        
        logger.warning(
            f"权限提升: {agent_type} -> {[p.name for p in permissions]} "
            f"(原因: {reason})"
        )
        
        return True
    
    def revoke_permission(
        self, 
        agent_type: str, 
        permissions: Set[Permission],
        reason: str = ""
    ) -> bool:
        """
        撤销Agent权限
        
        Args:
            agent_type: Agent类型
            permissions: 要撤销的权限集
            reason: 撤销原因
            
        Returns:
            是否成功
        """
        profile = self._profiles.get(agent_type)
        if not profile:
            return False
        
        # 添加到拒绝列表
        profile.denied.update(permissions)
        
        # 从授权列表移除
        profile.granted.difference_update(permissions)
        
        # 记录审计日志
        self._audit_log.append({
            "action": "revoke_permission",
            "agent_type": agent_type,
            "permissions": [p.name for p in permissions],
            "reason": reason,
        })
        
        logger.warning(
            f"权限撤销: {agent_type} <- {[p.name for p in permissions]} "
            f"(原因: {reason})"
        )
        
        return True
    
    def get_audit_log(self, agent_type: str = None) -> List[Dict[str, Any]]:
        """
        获取审计日志
        
        Args:
            agent_type: Agent类型过滤（可选）
            
        Returns:
            审计日志列表
        """
        if agent_type:
            return [
                entry for entry in self._audit_log 
                if entry.get("agent_type") == agent_type
            ]
        return self._audit_log.copy()
    
    def get_all_profiles(self) -> Dict[str, AgentPermissionProfile]:
        """
        获取所有权限配置
        
        Returns:
            权限配置字典
        """
        return self._profiles.copy()
    
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized


def require_permission(permission: Permission):
    """
    权限检查装饰器（P2-3安全修复）
    
    Args:
        permission: 需要的权限
        
    Usage:
        @require_permission(Permission.FILE_WRITE)
        def write_file(self, path, content):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # 获取Agent类型
            agent_type = getattr(self, "agent_type", None)
            if not agent_type:
                raise PermissionError("无法确定Agent类型")
            
            # 获取权限管理器
            from core.service_locator import ServiceLocator
            try:
                perm_manager = ServiceLocator.get("permission_manager")
                if not perm_manager:
                    raise PermissionError("权限管理器不可用")
                
                # 检查权限
                if not perm_manager.check_permission(agent_type, permission):
                    raise PermissionError(
                        f"Agent [{agent_type}] 没有 [{permission.name}] 权限"
                    )
            except Exception as e:
                logger.error(f"权限检查失败: {e}")
                raise
            
            return func(self, *args, **kwargs)
        
        return wrapper
    return decorator


# 全局权限管理器实例
_permission_manager: Optional[PermissionManager] = None


def get_permission_manager() -> PermissionManager:
    """获取全局权限管理器"""
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = PermissionManager()
        _permission_manager.initialize()
    return _permission_manager
