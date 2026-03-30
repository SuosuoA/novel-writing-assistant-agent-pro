"""
SESSION-STATE管理模块 - OpenClaw L1热记忆

V1.0版本
创建日期：2026-03-25

特性：
- 实时会话状态管理
- Markdown格式持久化（文件即真相源）
- WAL协议支持（AI调用前先写入状态）
- 线程安全（RLock）
- EventBus集成（发布状态变更事件）
- 单例工厂模式

设计参考：
- OpenClaw mem9 L1热记忆架构
- 升级方案10.1
"""

import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict

from .models import Event


# ============================================================================
# Pydantic数据模型
# ============================================================================


class ActiveTask(BaseModel):
    """活跃任务状态"""

    model_config = ConfigDict(frozen=False)

    current_function: str = Field("", description="当前功能（如：世界观编辑）")
    current_file: str = Field("", description="当前文件路径")
    last_operation: str = Field("", description="上次操作描述")
    last_operation_time: Optional[str] = Field(None, description="上次操作时间")
    task_id: Optional[str] = Field(None, description="任务ID")


class TempContext(BaseModel):
    """临时上下文"""

    model_config = ConfigDict(frozen=False)

    current_chapter: str = Field("", description="当前章节标题")
    word_count: int = Field(0, ge=0, description="当前字数")
    recent_generation: str = Field("", description="最近生成的内容摘要")
    outline_snippet: str = Field("", description="当前大纲片段")
    characters_involved: List[str] = Field(default_factory=list, description="涉及的人物")
    worldview_elements: List[str] = Field(default_factory=list, description="涉及的世界观元素")


class ErrorState(BaseModel):
    """异常状态"""

    model_config = ConfigDict(frozen=False)

    has_error: bool = Field(False, description="是否有异常")
    error_type: str = Field("", description="异常类型")
    error_message: str = Field("", description="异常消息")
    error_time: Optional[str] = Field(None, description="异常时间")
    stack_trace: str = Field("", description="堆栈追踪")
    recovery_hint: str = Field("", description="恢复提示")


class PendingData(BaseModel):
    """待持久化数据"""

    model_config = ConfigDict(frozen=False)

    latest_score: Optional[float] = Field(None, ge=0, le=1, description="最新评分")
    score_time: Optional[str] = Field(None, description="评分时间")
    memory_update_pending: str = Field("", description="待写入MEMORY的内容")
    archive_candidates: List[str] = Field(default_factory=list, description="归档候选")


class SessionState(BaseModel):
    """会话状态汇总"""

    model_config = ConfigDict(frozen=False)

    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="状态更新时间"
    )
    session_id: str = Field("", description="会话ID")
    active_task: ActiveTask = Field(default_factory=ActiveTask, description="活跃任务")
    temp_context: TempContext = Field(default_factory=TempContext, description="临时上下文")
    error_state: ErrorState = Field(default_factory=ErrorState, description="异常状态")
    pending_data: PendingData = Field(default_factory=PendingData, description="待持久化数据")

    def get_total_word_count(self) -> int:
        """获取总字数"""
        return self.temp_context.word_count

    def has_active_error(self) -> bool:
        """是否有活跃异常"""
        return self.error_state.has_error

    def is_task_active(self) -> bool:
        """是否有活跃任务"""
        return bool(self.active_task.current_function)


# ============================================================================
# SessionStateManager - 核心管理类
# ============================================================================


class SessionStateManager:
    """
    SESSION-STATE管理器
    
    实现OpenClaw L1热记忆：
    - 实时状态管理
    - Markdown持久化
    - WAL协议
    - 线程安全
    """

    # 默认文件路径
    DEFAULT_FILE_NAME = "session-state.md"
    DEFAULT_DIR = ".workbuddy"

    def __init__(self, workspace: Optional[Path] = None):
        """
        初始化管理器
        
        Args:
            workspace: 工作区路径，默认为项目根目录
        """
        self._lock = threading.RLock()
        
        # 确定工作区路径
        if workspace is None:
            workspace = Path(__file__).parent.parent
        self._workspace = Path(workspace)
        
        # 确定session-state文件路径
        self._state_file = self._workspace / self.DEFAULT_DIR / self.DEFAULT_FILE_NAME
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 内存状态缓存
        self._state: Optional[SessionState] = None
        
        # EventBus实例（延迟初始化避免循环依赖）
        self._event_bus = None
        
        # WAL锁（确保写入顺序）
        self._wal_lock = threading.Lock()
        
        # 导入日志
        import logging
        self._logger = logging.getLogger(__name__)
        
    # ==================== 核心读写方法 ====================
    
    def get_state(self) -> SessionState:
        """
        获取当前会话状态
        
        Returns:
            SessionState: 当前状态
        """
        with self._lock:
            if self._state is None:
                # 尝试从文件加载
                self._state = self._load_from_file()
            return self._state
    
    def get_current_state(self) -> Dict[str, Any]:
        """
        获取当前会话状态（V2.23新增：GUI兼容接口）
        
        返回字典格式，方便GUI使用
        
        Returns:
            Dict: 状态字典
        """
        state = self.get_state()
        return {
            "session_id": state.session_id,
            "timestamp": state.timestamp,
            "active_task": {
                "current_function": state.active_task.current_function,
                "current_file": state.active_task.current_file,
                "last_operation": state.active_task.last_operation,
                "last_operation_time": state.active_task.last_operation_time,
                "task_id": state.active_task.task_id,
            },
            "temp_context": {
                "current_chapter": state.temp_context.current_chapter,
                "word_count": state.temp_context.word_count,
                "recent_generation": state.temp_context.recent_generation,
                "outline_snippet": state.temp_context.outline_snippet,
                "characters_involved": state.temp_context.characters_involved,
                "worldview_elements": state.temp_context.worldview_elements,
            },
            "error_state": {
                "has_error": state.error_state.has_error,
                "error_type": state.error_state.error_type,
                "error_message": state.error_state.error_message,
                "error_time": state.error_state.error_time,
            },
            "pending_data": {
                "latest_score": state.pending_data.latest_score,
                "score_time": state.pending_data.score_time,
                "memory_update_pending": state.pending_data.memory_update_pending,
            },
        }
    
    def update_state(self, **updates) -> None:
        """
        更新会话状态
        
        Args:
            **updates: 状态更新字段
                - active_task: ActiveTask更新
                - temp_context: TempContext更新
                - error_state: ErrorState更新
                - pending_data: PendingData更新
        """
        with self._lock:
            state = self.get_state()
            
            # 更新时间戳
            state.timestamp = datetime.now().isoformat()
            
            # 应用更新
            if "active_task" in updates:
                task_data = updates["active_task"]
                if isinstance(task_data, dict):
                    for key, value in task_data.items():
                        if hasattr(state.active_task, key):
                            setattr(state.active_task, key, value)
                elif isinstance(task_data, ActiveTask):
                    state.active_task = task_data
                    
            if "temp_context" in updates:
                ctx_data = updates["temp_context"]
                if isinstance(ctx_data, dict):
                    for key, value in ctx_data.items():
                        if hasattr(state.temp_context, key):
                            setattr(state.temp_context, key, value)
                elif isinstance(ctx_data, TempContext):
                    state.temp_context = ctx_data
                    
            if "error_state" in updates:
                err_data = updates["error_state"]
                if isinstance(err_data, dict):
                    for key, value in err_data.items():
                        if hasattr(state.error_state, key):
                            setattr(state.error_state, key, value)
                elif isinstance(err_data, ErrorState):
                    state.error_state = err_data
                    
            if "pending_data" in updates:
                pend_data = updates["pending_data"]
                if isinstance(pend_data, dict):
                    for key, value in pend_data.items():
                        if hasattr(state.pending_data, key):
                            setattr(state.pending_data, key, value)
                elif isinstance(pend_data, PendingData):
                    state.pending_data = pend_data
            
            # 持久化
            self._save_to_file(state)
            
            # 发布事件
            self._publish_state_change_event(updates)
    
    def clear_state(self) -> None:
        """清除会话状态（新会话开始时调用）"""
        with self._lock:
            self._state = SessionState()
            self._save_to_file(self._state)
            
            self._logger.info("会话状态已清除")
            
    # ==================== WAL协议方法 ====================
    
    def write_before_ai_call(self, context: Dict[str, Any]) -> None:
        """
        WAL协议：在AI调用前写入状态
        
        确保中断后可恢复。必须在调用LLM API前调用此方法。
        
        Args:
            context: 调用上下文，包含：
                - task: 当前任务描述
                - file: 当前文件
                - operation: 操作类型
                - pending: 待持久化数据
        """
        with self._wal_lock:
            # 构建状态更新
            updates = {
                "active_task": {
                    "current_function": context.get("task", ""),
                    "current_file": context.get("file", ""),
                    "last_operation": context.get("operation", ""),
                    "last_operation_time": datetime.now().isoformat(),
                }
            }
            
            if "pending" in context:
                updates["pending_data"] = context["pending"]
            
            # 同步写入（阻塞式，确保落盘）
            self.update_state(**updates)
            
            self._logger.debug(f"WAL写入完成: {context.get('operation', 'unknown')}")
    
    def recover_on_startup(self) -> Optional[SessionState]:
        """
        启动时恢复上次会话状态
        
        Returns:
            SessionState: 恢复的状态，如果不存在则返回None
        """
        with self._lock:
            if not self._state_file.exists():
                self._logger.info("未找到SESSION-STATE文件，创建新会话")
                self._state = SessionState()
                return None
            
            try:
                state = self._load_from_file()
                self._state = state
                
                # 检查是否有活跃任务需要恢复
                if state.is_task_active():
                    self._logger.info(
                        f"检测到未完成任务: {state.active_task.current_function}"
                    )
                    return state
                    
                return None
            except Exception as e:
                self._logger.error(f"恢复会话状态失败: {e}")
                self._state = SessionState()
                return None
    
    # ==================== 便捷方法 ====================
    
    def set_active_task(
        self,
        function: str,
        file: str = "",
        operation: str = "",
        task_id: Optional[str] = None
    ) -> None:
        """
        设置活跃任务
        
        Args:
            function: 功能名称
            file: 文件路径
            operation: 操作描述
            task_id: 任务ID
        """
        self.update_state(
            active_task={
                "current_function": function,
                "current_file": file,
                "last_operation": operation,
                "last_operation_time": datetime.now().isoformat(),
                "task_id": task_id,
            }
        )
    
    def clear_active_task(self) -> None:
        """清除活跃任务"""
        self.update_state(
            active_task=ActiveTask()
        )
    
    def set_error(
        self,
        error_type: str,
        error_message: str,
        stack_trace: str = "",
        recovery_hint: str = ""
    ) -> None:
        """
        设置异常状态
        
        Args:
            error_type: 异常类型
            error_message: 异常消息
            stack_trace: 堆栈追踪
            recovery_hint: 恢复提示
        """
        self.update_state(
            error_state={
                "has_error": True,
                "error_type": error_type,
                "error_message": error_message,
                "error_time": datetime.now().isoformat(),
                "stack_trace": stack_trace,
                "recovery_hint": recovery_hint,
            }
        )
    
    def clear_error(self) -> None:
        """清除异常状态"""
        self.update_state(
            error_state=ErrorState()
        )
    
    def update_generation_context(
        self,
        chapter: str = "",
        word_count: int = 0,
        recent_generation: str = "",
        characters: Optional[List[str]] = None,
        worldview_elements: Optional[List[str]] = None
    ) -> None:
        """
        更新生成上下文
        
        Args:
            chapter: 章节标题
            word_count: 字数
            recent_generation: 最近生成内容
            characters: 涉及人物
            worldview_elements: 世界观元素
        """
        updates: Dict[str, Any] = {
            "temp_context": {
                "current_chapter": chapter,
                "word_count": word_count,
                "recent_generation": recent_generation[:500] if recent_generation else "",
            }
        }
        
        if characters is not None:
            updates["temp_context"]["characters_involved"] = characters
        if worldview_elements is not None:
            updates["temp_context"]["worldview_elements"] = worldview_elements
        
        self.update_state(**updates)
    
    def record_score(self, score: float) -> None:
        """
        记录评分
        
        Args:
            score: 评分值（0-1）
        """
        self.update_state(
            pending_data={
                "latest_score": score,
                "score_time": datetime.now().isoformat(),
            }
        )
    
    # ==================== 文件读写 ====================
    
    def _load_from_file(self) -> SessionState:
        """
        从Markdown文件加载状态
        
        Returns:
            SessionState: 加载的状态
        """
        if not self._state_file.exists():
            return SessionState()
        
        try:
            content = self._state_file.read_text(encoding="utf-8")
            return self._parse_markdown(content)
        except Exception as e:
            self._logger.error(f"读取SESSION-STATE文件失败: {e}")
            return SessionState()
    
    def _save_to_file(self, state: SessionState) -> None:
        """
        保存状态到Markdown文件
        
        Args:
            state: 会话状态
        """
        try:
            content = self._render_markdown(state)
            self._state_file.write_text(content, encoding="utf-8")
        except Exception as e:
            self._logger.error(f"保存SESSION-STATE文件失败: {e}")
            raise
    
    def _parse_markdown(self, content: str) -> SessionState:
        """
        解析Markdown内容为SessionState
        
        Args:
            content: Markdown内容
            
        Returns:
            SessionState: 解析的状态
        """
        state = SessionState()
        
        lines = content.split("\n")
        current_section = None
        
        for line in lines:
            line = line.strip()
            
            # 检测章节
            if line.startswith("## 🔄 活跃任务"):
                current_section = "active_task"
            elif line.startswith("## 📝 临时上下文"):
                current_section = "temp_context"
            elif line.startswith("## 🚨 异常状态"):
                current_section = "error_state"
            elif line.startswith("## 💾 待持久化数据"):
                current_section = "pending_data"
            elif line.startswith("# SESSION-STATE"):
                # 提取时间戳
                if "更新时间:" in line:
                    try:
                        timestamp_str = line.split("更新时间:")[1].strip().rstrip(")")
                        state.timestamp = timestamp_str
                    except:
                        pass
            elif line.startswith("- ") and current_section:
                # 解析键值对
                if ":" in line:
                    key_part, value_part = line[2:].split(":", 1)
                    key = key_part.strip()
                    value = value_part.strip()
                    
                    if current_section == "active_task":
                        if key == "当前功能":
                            state.active_task.current_function = value
                        elif key == "当前文件":
                            state.active_task.current_file = value
                        elif key == "上次操作":
                            state.active_task.last_operation = value
                        elif key == "上次操作时间":
                            state.active_task.last_operation_time = value
                        elif key == "任务ID":
                            state.active_task.task_id = value
                            
                    elif current_section == "temp_context":
                        if key == "当前章节":
                            state.temp_context.current_chapter = value
                        elif key == "字数":
                            try:
                                state.temp_context.word_count = int(value)
                            except:
                                pass
                        elif key == "最近生成":
                            state.temp_context.recent_generation = value
                        elif key == "涉及人物":
                            state.temp_context.characters_involved = [
                                c.strip() for c in value.split(",") if c.strip()
                            ]
                        elif key == "世界观元素":
                            state.temp_context.worldview_elements = [
                                e.strip() for e in value.split(",") if e.strip()
                            ]
                            
                    elif current_section == "error_state":
                        if key == "是否有异常":
                            state.error_state.has_error = value.lower() == "true"
                        elif key == "异常类型":
                            state.error_state.error_type = value
                        elif key == "异常消息":
                            state.error_state.error_message = value
                        elif key == "异常时间":
                            state.error_state.error_time = value
                        elif key == "堆栈追踪":
                            state.error_state.stack_trace = value
                        elif key == "恢复提示":
                            state.error_state.recovery_hint = value
                            
                    elif current_section == "pending_data":
                        if key == "最新评分":
                            try:
                                state.pending_data.latest_score = float(value)
                            except:
                                pass
                        elif key == "评分时间":
                            state.pending_data.score_time = value
                        elif key == "待写入MEMORY":
                            state.pending_data.memory_update_pending = value
                        elif key == "归档候选":
                            state.pending_data.archive_candidates = [
                                a.strip() for a in value.split(",") if a.strip()
                            ]
        
        return state
    
    def _render_markdown(self, state: SessionState) -> str:
        """
        渲染SessionState为Markdown
        
        Args:
            state: 会话状态
            
        Returns:
            Markdown内容
        """
        lines = [
            f"# SESSION-STATE - 当前会话状态",
            f"> 更新时间: {state.timestamp}",
            "",
            "## 🔄 活跃任务",
            f"- 当前功能: {state.active_task.current_function or '无'}",
            f"- 当前文件: {state.active_task.current_file or '无'}",
            f"- 上次操作: {state.active_task.last_operation or '无'}",
            f"- 上次操作时间: {state.active_task.last_operation_time or '无'}",
            f"- 任务ID: {state.active_task.task_id or '无'}",
            "",
            "## 📝 临时上下文",
            f"- 当前章节: {state.temp_context.current_chapter or '无'}",
            f"- 字数: {state.temp_context.word_count}",
            f"- 最近生成: {state.temp_context.recent_generation[:100] or '无'}",
            f"- 涉及人物: {', '.join(state.temp_context.characters_involved) or '无'}",
            f"- 世界观元素: {', '.join(state.temp_context.worldview_elements) or '无'}",
            "",
            "## 🚨 异常状态",
        ]
        
        if state.error_state.has_error:
            lines.extend([
                f"- 是否有异常: **True**",
                f"- 异常类型: {state.error_state.error_type}",
                f"- 异常消息: {state.error_state.error_message}",
                f"- 异常时间: {state.error_state.error_time or '未知'}",
                f"- 堆栈追踪: {state.error_state.stack_trace[:200] if state.error_state.stack_trace else '无'}",
                f"- 恢复提示: {state.error_state.recovery_hint or '无'}",
            ])
        else:
            lines.append("- 无")
        
        lines.extend([
            "",
            "## 💾 待持久化数据",
            f"- 最新评分: {state.pending_data.latest_score or '无'}",
            f"- 评分时间: {state.pending_data.score_time or '无'}",
            f"- 待写入MEMORY: {state.pending_data.memory_update_pending or '无'}",
            f"- 归档候选: {', '.join(state.pending_data.archive_candidates) or '无'}",
            "",
        ])
        
        return "\n".join(lines)
    
    # ==================== EventBus集成 ====================
    
    def _publish_state_change_event(self, updates: Dict[str, Any]) -> None:
        """
        发布状态变更事件
        
        Args:
            updates: 更新内容
        """
        # 延迟初始化EventBus
        if self._event_bus is None:
            try:
                from .event_bus import get_event_bus
                self._event_bus = get_event_bus()
            except Exception as e:
                self._logger.warning(f"EventBus初始化失败: {e}")
                return
        
        try:
            event_data = {
                "updates": updates,
                "timestamp": datetime.now().isoformat(),
                "session_id": self.get_state().session_id,
            }
            
            self._event_bus.publish(
                event_type="session.state_changed",
                data=event_data,
                source="SessionStateManager"
            )
        except Exception as e:
            self._logger.error(f"发布状态变更事件失败: {e}")


# ============================================================================
# 单例工厂
# ============================================================================

_session_state_manager_instance: Optional[SessionStateManager] = None
_session_state_manager_lock = threading.Lock()


def get_session_state_manager(workspace: Optional[Path] = None) -> SessionStateManager:
    """
    获取全局SessionStateManager实例
    
    Args:
        workspace: 工作区路径（仅首次调用时有效）
        
    Returns:
        SessionStateManager实例
    """
    global _session_state_manager_instance
    
    if _session_state_manager_instance is None:
        with _session_state_manager_lock:
            if _session_state_manager_instance is None:
                _session_state_manager_instance = SessionStateManager(workspace)
    
    return _session_state_manager_instance


def reset_session_state_manager() -> None:
    """
    重置全局SessionStateManager实例（仅用于测试）
    """
    global _session_state_manager_instance
    
    with _session_state_manager_lock:
        _session_state_manager_instance = None
