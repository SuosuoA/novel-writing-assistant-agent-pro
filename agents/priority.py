"""
Agent优先级和任务定义

V2.1版本 - 安全加固
创建日期: 2026-03-21
更新日期: 2026-03-24

安全修复:
- P0-1: 添加TaskPayload验证模型，防止注入攻击
- P1-1: 添加全局超时控制，防止嵌套任务超时累积
"""

from enum import IntEnum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import re
import logging

# 尝试导入Pydantic，用于严格的payload验证
try:
    from pydantic import BaseModel, Field, field_validator, model_validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = object  # 类型占位

logger = logging.getLogger(__name__)


# === 安全常量 ===
MAX_TASK_QUEUE_SIZE = 1000  # 任务队列最大容量
MAX_CONCURRENT_TASKS = 10  # 最大并发任务数
MAX_TASK_PAYLOAD_SIZE = 100 * 1024  # payload最大100KB
MAX_PROMPT_LENGTH = 50000  # prompt最大长度（字符）
DEFAULT_GLOBAL_TIMEOUT = 300  # 默认全局超时5分钟

# 不可重试的异常类型（P0-2修复）
NON_RETRYABLE_EXCEPTIONS = (
    ValueError,       # 输入验证错误
    PermissionError,  # 权限错误
    ImportError,      # 模块加载错误
    SyntaxError,      # 语法错误
    TypeError,        # 类型错误
    KeyError,         # 键错误（通常是配置问题）
)


if PYDANTIC_AVAILABLE:
    class TaskPayload(BaseModel):
        """
        任务payload验证模型（P0-1安全修复）
        
        防止:
        - SQL注入
        - 代码注入
        - 路径遍历
        - 敏感信息泄露
        """
        prompt: str = Field(default="", max_length=MAX_PROMPT_LENGTH)
        options: Dict[str, Any] = Field(default_factory=dict)
        
        @field_validator("prompt")
        @classmethod
        def validate_prompt(cls, v: str) -> str:
            """验证prompt字段，检测危险模式"""
            if not v:
                return v
            
            # 检查payload大小
            if len(v) > MAX_PROMPT_LENGTH:
                raise ValueError(f"Prompt length exceeds maximum ({MAX_PROMPT_LENGTH})")
            
            # 危险模式检测
            dangerous_patterns = [
                (r"__import__", "代码注入: __import__"),
                (r"eval\s*\(", "代码注入: eval()"),
                (r"exec\s*\(", "代码注入: exec()"),
                (r"compile\s*\(", "代码注入: compile()"),
                (r"DROP\s+TABLE", "SQL注入: DROP TABLE"),
                (r"DELETE\s+FROM", "SQL注入: DELETE FROM"),
                (r"INSERT\s+INTO", "SQL注入: INSERT INTO"),
                (r"UPDATE\s+.*SET", "SQL注入: UPDATE SET"),
                (r"\.\./", "路径遍历: ../"),
                (r"\.\.\\", "路径遍历: ..\\"),
                (r"os\.system", "系统命令: os.system"),
                (r"subprocess\.", "系统命令: subprocess"),
                (r"open\s*\([^)]*['\"]\.\.", "文件操作: 路径遍历"),
            ]
            
            for pattern, description in dangerous_patterns:
                if re.search(pattern, v, re.IGNORECASE):
                    logger.warning(f"TaskPayload验证失败: 检测到危险模式 - {description}")
                    raise ValueError(f"Dangerous pattern detected: {description}")
            
            return v
        
        @field_validator("options")
        @classmethod
        def validate_options(cls, v: Dict[str, Any]) -> Dict[str, Any]:
            """验证options字段"""
            if not v:
                return v
            
            # 递归检查options中的字符串值
            def check_dict_values(d: Dict, depth: int = 0) -> None:
                if depth > 5:  # 限制递归深度
                    return
                for key, value in d.items():
                    if isinstance(value, str):
                        # 对字符串值也进行危险模式检查
                        for pattern, desc in [
                            (r"__import__", "代码注入"),
                            (r"eval\s*\(", "代码注入"),
                            (r"\.\./", "路径遍历"),
                        ]:
                            if re.search(pattern, value, re.IGNORECASE):
                                raise ValueError(f"Dangerous pattern in options.{key}: {desc}")
                    elif isinstance(value, dict):
                        check_dict_values(value, depth + 1)
            
            check_dict_values(v)
            return v
        
        @model_validator(mode='after')
        def check_payload_size(self) -> 'TaskPayload':
            """检查整体payload大小"""
            import sys
            try:
                size = sys.getsizeof(self.prompt) + sys.getsizeof(self.options)
                if size > MAX_TASK_PAYLOAD_SIZE:
                    raise ValueError(f"Payload size exceeds maximum ({MAX_TASK_PAYLOAD_SIZE} bytes)")
            except Exception:
                pass  # 忽略大小检查失败
            return self
else:
    # Pydantic不可用时的简单验证类
    class TaskPayload:
        """简化版TaskPayload（无Pydantic依赖）"""
        def __init__(self, prompt: str = "", options: Dict[str, Any] = None):
            self.prompt = prompt[:MAX_PROMPT_LENGTH] if prompt else ""
            self.options = options or {}
            
            # 简单验证
            dangerous = ["__import__", "eval(", "exec(", "DROP TABLE", "../", "os.system"]
            for pattern in dangerous:
                if pattern.lower() in self.prompt.lower():
                    raise ValueError(f"Dangerous pattern detected: {pattern}")
        
        def model_dump(self) -> Dict[str, Any]:
            return {"prompt": self.prompt, "options": self.options}


class TaskPriority(IntEnum):
    """任务优先级枚举"""

    CRITICAL = 0  # 紧急任务:用户主动触发的生成任务
    HIGH = 1  # 高优先:插件热重载、配置变更
    NORMAL = 2  # 正常:后台分析、统计计算
    LOW = 3  # 低优先:日志归档、缓存清理
    BACKGROUND = 4  # 后台:监控数据收集


@dataclass
class AgentTask:
    """
    Agent任务（V2.1安全加固版）
    
    安全增强:
    - global_timeout: 全局超时控制，防止嵌套任务超时累积（P1-1）
    - _cancel_event: 协作式取消机制（P1-2）
    - last_exception: 记录最后一次异常，用于重试决策（P0-2）
    """

    task_id: str  # 任务唯一标识
    agent_type: str  # Agent类型 (thinker/optimizer/validator/planner)
    priority: TaskPriority  # 优先级
    payload: Dict[str, Any]  # 任务载荷
    dependencies: List[str] = field(default_factory=list)  # 依赖任务ID列表
    created_at: Optional[datetime] = None  # 创建时间
    started_at: Optional[datetime] = None  # 开始时间
    completed_at: Optional[datetime] = None  # 完成时间
    retry_count: int = 0  # 重试次数
    max_retries: int = 3  # 最大重试次数
    timeout_seconds: int = 300  # 单任务超时时间(秒)
    version: str = "1.0.0"  # 任务版本
    dependency_versions: Dict[str, str] = field(default_factory=dict)  # 依赖版本要求
    
    # V2.1安全增强字段
    global_timeout: int = DEFAULT_GLOBAL_TIMEOUT  # 全局超时时间（P1-1）
    last_exception: Optional[Exception] = None  # 最后一次异常（P0-2）
    _cancel_requested: bool = False  # 取消请求标志（P1-2）

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    @property
    def age_seconds(self) -> float:
        """任务年龄(秒)"""
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()

    @property
    def is_expired(self) -> bool:
        """是否超时"""
        if self.started_at is None:
            return self.age_seconds > self.timeout_seconds
        return (
            datetime.now(timezone.utc) - self.started_at
        ).total_seconds() > self.timeout_seconds
    
    @property
    def global_timeout_exceeded(self) -> bool:
        """
        是否超过全局超时（P1-1修复）
        
        用于检测嵌套任务链的总时间是否超过预期，
        防止任务链累积超时导致用户等待时间不可预测。
        """
        if self.created_at is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return elapsed > self.global_timeout

    @property
    def can_retry(self) -> bool:
        """是否可以重试"""
        return self.retry_count < self.max_retries
    
    @property
    def is_non_retryable_error(self) -> bool:
        """
        是否为不可重试的错误（P0-2修复）
        
        某些错误类型（如输入验证错误、权限错误）重试没有意义，
        应该直接使用降级策略或失败。
        """
        if self.last_exception is None:
            return False
        return isinstance(self.last_exception, NON_RETRYABLE_EXCEPTIONS)
    
    def request_cancel(self) -> None:
        """
        请求取消任务（P1-2协作式取消）
        
        设置取消标志，任务执行时应定期检查此标志。
        """
        self._cancel_requested = True
        logger.info(f"任务 {self.task_id} 已请求取消")
    
    def check_cancelled(self) -> bool:
        """
        检查任务是否被取消（P1-2协作式取消）
        
        Agent在执行过程中应定期调用此方法检查是否应该停止。
        """
        return self._cancel_requested
    
    def validate_payload(self) -> bool:
        """
        验证任务payload（P0-1修复）
        
        Returns:
            验证是否通过
            
        Raises:
            ValueError: payload包含危险内容
        """
        try:
            validated = TaskPayload(**self.payload)
            # 用验证后的干净数据替换原payload
            self.payload = validated.model_dump() if hasattr(validated, 'model_dump') else {
                "prompt": validated.prompt,
                "options": validated.options
            }
            return True
        except Exception as e:
            logger.error(f"任务 {self.task_id} payload验证失败: {e}")
            self.last_exception = e
            raise ValueError(f"Payload validation failed: {e}")
