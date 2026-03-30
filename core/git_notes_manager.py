"""
Git-Notes分支感知记忆管理 - OpenClaw L3冷记忆

V1.0版本
创建日期：2026-03-25

特性：
- 分支特定的决策记录（分支隔离）
- 里程碑事件存储（支持git log检索）
- Git-Notes命名空间管理
- 自动同步分支切换记忆
- 线程安全（RLock）
- EventBus集成（发布记忆事件）
- 单例工厂模式

设计参考：
- OpenClaw mem9 L3冷记忆架构
- 升级方案10.1

核心原则：
Git-Notes是Git的notes命名空间存储机制，用于：
1. 分支隔离：不同分支有独立的决策记录
2. 历史追溯：支持git log检索历史决策
3. 永久存储：与commit关联，不会丢失
4. 可推送：可以同步到远程仓库

使用示例：
    # 获取单例实例
    git_notes = get_git_notes_manager()

    # 记录决策
    git_notes.record_decision(
        title="采用LanceDB作为向量数据库",
        content="ADR-001: 零配置、嵌入式、Python友好",
        tags=["ADR", "vector-db"]
    )

    # 记录里程碑
    git_notes.record_milestone(
        title="V5.5人设评分修复完成",
        content="修复人设评分固定返回低分问题"
    )

    # 获取当前分支记忆
    memories = git_notes.get_branch_memories()

    # 切换分支时同步
    git_notes.sync_on_branch_switch(old_branch, new_branch)
"""

import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict

from .models import Event


# ============================================================================
# Pydantic数据模型
# ============================================================================


class GitNote(BaseModel):
    """Git笔记记录"""

    model_config = ConfigDict(frozen=False)

    note_id: str = Field("", description="笔记ID")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="记录时间"
    )
    note_type: str = Field("decision", description="类型：decision/milestone/lesson/context")
    title: str = Field("", description="标题")
    content: str = Field("", description="内容")
    tags: List[str] = Field(default_factory=list, description="标签")
    branch: str = Field("", description="所属分支")
    commit_hash: str = Field("", description="关联的commit hash")


class BranchMemory(BaseModel):
    """分支记忆汇总"""

    model_config = ConfigDict(frozen=False)

    branch_name: str = Field("", description="分支名称")
    last_sync: str = Field("", description="上次同步时间")
    decisions: List[GitNote] = Field(default_factory=list, description="决策记录")
    milestones: List[GitNote] = Field(default_factory=list, description="里程碑事件")
    lessons: List[GitNote] = Field(default_factory=list, description="经验教训")
    context: List[GitNote] = Field(default_factory=list, description="上下文记录")


class GitNotesState(BaseModel):
    """Git-Notes状态"""

    model_config = ConfigDict(frozen=False)

    current_branch: str = Field("", description="当前分支")
    total_notes: int = Field(0, ge=0, description="总笔记数")
    last_record_time: Optional[str] = Field(None, description="上次记录时间")
    refs_initialized: bool = Field(False, description="notes ref是否已初始化")


# ============================================================================
# GitNotesManager - 核心管理类
# ============================================================================


class GitNotesManager:
    """
    Git-Notes分支感知记忆管理器

    实现OpenClaw L3冷记忆：
    - 分支特定的决策记录
    - 里程碑事件存储
    - Git-Notes命名空间管理
    - 线程安全

    Git-Notes使用说明：
    - Git notes存储在.git/refs/notes/命名空间
    - 可以关联到任意commit
    - 支持push/pull同步
    - 使用自定义ref（如memory）避免冲突
    """

    # Git-Notes引用名称
    NOTES_REF = "memory"
    NOTES_NAMESPACE = "refs/notes/"

    def __init__(self, repo_root: Optional[Path] = None):
        """
        初始化Git-Notes管理器

        Args:
            repo_root: Git仓库根目录，默认为项目根目录
        """
        self._lock = threading.RLock()

        # 确定仓库根目录
        if repo_root is None:
            repo_root = Path(__file__).parent.parent
        self._repo_root = Path(repo_root)

        # 验证Git仓库
        self._git_dir = self._repo_root / ".git"
        if not self._git_dir.exists():
            raise ValueError(f"不是有效的Git仓库: {self._repo_root}")

        # 内存缓存
        self._state = GitNotesState()
        self._branch_memories: Dict[str, BranchMemory] = {}

        # EventBus实例（延迟初始化）
        self._event_bus = None

        # 导入日志
        import logging
        self._logger = logging.getLogger(__name__)

        # 初始化
        self._initialize()

    def _initialize(self) -> None:
        """初始化Git-Notes环境"""
        with self._lock:
            # 获取当前分支
            self._state.current_branch = self._get_current_branch()

            # 初始化notes ref
            self._ensure_notes_ref_exists()

            # 加载当前分支记忆
            self._load_branch_memory(self._state.current_branch)

            self._logger.info(f"GitNotesManager初始化完成，当前分支: {self._state.current_branch}")

    # ==================== 核心记录方法 ====================

    def record_decision(
        self,
        title: str,
        content: str,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        记录决策（ADR风格）

        Args:
            title: 决策标题
            content: 决策内容
            tags: 标签列表

        Returns:
            str: 笔记ID

        Example:
            git_notes.record_decision(
                title="采用LanceDB作为向量数据库",
                content="ADR-001: 零配置、嵌入式、Python友好",
                tags=["ADR", "vector-db"]
            )
        """
        return self._record_note(
            note_type="decision",
            title=title,
            content=content,
            tags=tags or []
        )

    def record_milestone(
        self,
        title: str,
        content: str,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        记录里程碑事件

        Args:
            title: 里程碑标题
            content: 里程碑内容
            tags: 标签列表

        Returns:
            str: 笔记ID

        Example:
            git_notes.record_milestone(
                title="V5.5人设评分修复完成",
                content="修复人设评分固定返回低分问题"
            )
        """
        return self._record_note(
            note_type="milestone",
            title=title,
            content=content,
            tags=tags or []
        )

    def record_lesson(
        self,
        title: str,
        content: str,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        记录经验教训

        Args:
            title: 教训标题
            content: 教训内容
            tags: 标签列表

        Returns:
            str: 笔记ID

        Example:
            git_notes.record_lesson(
                title="git restore误删用户成果",
                content="破坏性命令必须先确认，不可绕过用户"
            )
        """
        return self._record_note(
            note_type="lesson",
            title=title,
            content=content,
            tags=tags or []
        )

    def record_context(
        self,
        title: str,
        content: str,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        记录上下文信息

        Args:
            title: 上下文标题
            content: 上下文内容
            tags: 标签列表

        Returns:
            str: 笔记ID
        """
        return self._record_note(
            note_type="context",
            title=title,
            content=content,
            tags=tags or []
        )

    def _record_note(
        self,
        note_type: str,
        title: str,
        content: str,
        tags: List[str]
    ) -> str:
        """
        内部方法：记录笔记

        Args:
            note_type: 笔记类型
            title: 标题
            content: 内容
            tags: 标签

        Returns:
            str: 笔记ID
        """
        with self._lock:
            # 生成笔记ID
            note_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

            # 获取当前commit
            commit_hash = self._get_current_commit()

            # 创建笔记对象
            note = GitNote(
                note_id=note_id,
                timestamp=datetime.now().isoformat(),
                note_type=note_type,
                title=title,
                content=content,
                tags=tags,
                branch=self._state.current_branch,
                commit_hash=commit_hash
            )

            # 序列化为JSON
            note_json = note.model_dump_json()

            # 添加Git Note
            self._add_git_note(commit_hash, note_json)

            # 更新内存缓存
            self._cache_note(note)

            # 更新状态
            self._state.total_notes += 1
            self._state.last_record_time = note.timestamp

            # 发布事件
            self._publish_note_event("git_notes.recorded", note)

            self._logger.info(f"记录Git Note: [{note_type}] {title}")

            return note_id

    # ==================== 分支管理 ====================

    def sync_on_branch_switch(self, old_branch: str, new_branch: str) -> None:
        """
        分支切换时同步记忆

        Args:
            old_branch: 旧分支名
            new_branch: 新分支名

        此方法在检测到分支切换时调用，自动：
        1. 保存旧分支的记忆
        2. 加载新分支的记忆
        """
        with self._lock:
            self._logger.info(f"分支切换: {old_branch} → {new_branch}")

            # 保存旧分支记忆（如果有变更）
            if old_branch in self._branch_memories:
                # Git-Notes已经持久化，无需额外保存
                pass

            # 更新当前分支
            self._state.current_branch = new_branch

            # 加载新分支记忆
            self._load_branch_memory(new_branch)

            # 发布分支切换事件
            self._publish_event("git_notes.branch_switched", {
                "old_branch": old_branch,
                "new_branch": new_branch
            })

    def get_branch_memories(self, branch: Optional[str] = None) -> BranchMemory:
        """
        获取分支记忆

        Args:
            branch: 分支名，默认为当前分支

        Returns:
            BranchMemory: 分支记忆汇总
        """
        target_branch = branch or self._state.current_branch

        with self._lock:
            if target_branch not in self._branch_memories:
                self._load_branch_memory(target_branch)

            return self._branch_memories.get(target_branch, BranchMemory(branch_name=target_branch))

    def _load_branch_memory(self, branch: str) -> None:
        """
        加载分支记忆

        Args:
            branch: 分支名
        """
        memory = BranchMemory(
            branch_name=branch,
            last_sync=datetime.now().isoformat()
        )

        # 获取该分支的所有notes
        notes = self._get_branch_notes(branch)

        for note in notes:
            if note.note_type == "decision":
                memory.decisions.append(note)
            elif note.note_type == "milestone":
                memory.milestones.append(note)
            elif note.note_type == "lesson":
                memory.lessons.append(note)
            elif note.note_type == "context":
                memory.context.append(note)

        self._branch_memories[branch] = memory

    # ==================== Git操作封装 ====================

    def _get_current_branch(self) -> str:
        """获取当前分支名"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self._logger.error(f"获取当前分支失败: {e}")
            return "unknown"

    def _get_current_commit(self) -> str:
        """获取当前commit hash"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()[:8]  # 短hash
        except subprocess.CalledProcessError:
            return "unknown"

    def _ensure_notes_ref_exists(self) -> None:
        """确保notes ref存在"""
        try:
            # 检查ref是否存在
            result = subprocess.run(
                ["git", "notes", "--ref", self.NOTES_REF, "list"],
                cwd=self._repo_root,
                capture_output=True,
                text=True
            )

            # 如果ref不存在，创建一个空的
            if result.returncode != 0:
                # 初始化空的notes ref
                subprocess.run(
                    ["git", "notes", "--ref", self.NOTES_REF, "add", "-m", "# Git Notes初始化", "HEAD"],
                    cwd=self._repo_root,
                    capture_output=True,
                    check=False  # 忽略错误
                )

            self._state.refs_initialized = True

        except Exception as e:
            self._logger.warning(f"初始化notes ref失败: {e}")

    def _add_git_note(self, commit_hash: str, content: str) -> None:
        """
        添加Git Note

        Args:
            commit_hash: 关联的commit hash
            content: Note内容
        """
        try:
            subprocess.run(
                ["git", "notes", "--ref", self.NOTES_REF, "add", "-m", content, commit_hash],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            # 如果note已存在，尝试追加
            if "already exists" in e.stderr.lower():
                subprocess.run(
                    ["git", "notes", "--ref", self.NOTES_REF, "append", "-m", content, commit_hash],
                    cwd=self._repo_root,
                    capture_output=True,
                    text=True,
                    check=True
                )
            else:
                raise

    def _get_branch_notes(self, branch: str) -> List[GitNote]:
        """
        获取分支的所有notes

        Args:
            branch: 分支名

        Returns:
            List[GitNote]: 笔记列表
        """
        notes = []

        try:
            # 获取分支的所有commit
            result = subprocess.run(
                ["git", "log", branch, "--pretty=%H"],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
                check=True
            )

            commit_hashes = result.stdout.strip().split("\n")

            for commit_hash in commit_hashes:
                if not commit_hash:
                    continue

                # 获取该commit的notes
                note_result = subprocess.run(
                    ["git", "notes", "--ref", self.NOTES_REF, "show", commit_hash],
                    cwd=self._repo_root,
                    capture_output=True,
                    text=True
                )

                if note_result.returncode == 0 and note_result.stdout.strip():
                    # 解析notes
                    for line in note_result.stdout.strip().split("\n"):
                        if line.startswith("{"):
                            try:
                                note_data = json.loads(line)
                                note = GitNote(**note_data)
                                # 只返回当前分支的notes
                                if note.branch == branch or not note.branch:
                                    notes.append(note)
                            except json.JSONDecodeError:
                                continue

        except subprocess.CalledProcessError as e:
            self._logger.error(f"获取分支notes失败: {e}")

        return notes

    def search_notes(self, query: str, note_type: Optional[str] = None) -> List[GitNote]:
        """
        搜索笔记

        Args:
            query: 搜索关键词
            note_type: 笔记类型过滤（可选）

        Returns:
            List[GitNote]: 匹配的笔记列表
        """
        notes = self.get_branch_memories().decisions + \
                self.get_branch_memories().milestones + \
                self.get_branch_memories().lessons + \
                self.get_branch_memories().context

        results = []
        query_lower = query.lower()

        for note in notes:
            # 类型过滤
            if note_type and note.note_type != note_type:
                continue

            # 内容匹配
            if (query_lower in note.title.lower() or
                query_lower in note.content.lower() or
                any(query_lower in tag.lower() for tag in note.tags)):
                results.append(note)

        return results

    # ==================== 便捷方法 ====================

    def get_recent_decisions(self, limit: int = 10) -> List[GitNote]:
        """
        获取最近的决策记录

        Args:
            limit: 最大数量

        Returns:
            List[GitNote]: 决策列表
        """
        memory = self.get_branch_memories()
        return sorted(memory.decisions, key=lambda x: x.timestamp, reverse=True)[:limit]

    def get_milestones(self) -> List[GitNote]:
        """
        获取所有里程碑事件

        Returns:
            List[GitNote]: 里程碑列表
        """
        memory = self.get_branch_memories()
        return sorted(memory.milestones, key=lambda x: x.timestamp, reverse=True)

    def get_lessons(self) -> List[GitNote]:
        """
        获取所有经验教训

        Returns:
            List[GitNote]: 教训列表
        """
        memory = self.get_branch_memories()
        return sorted(memory.lessons, key=lambda x: x.timestamp, reverse=True)

    def export_to_markdown(self, branch: Optional[str] = None) -> str:
        """
        导出分支记忆为Markdown格式

        Args:
            branch: 分支名，默认当前分支

        Returns:
            str: Markdown内容
        """
        memory = self.get_branch_memories(branch)

        lines = [
            f"# Git-Notes记忆导出",
            f"> 分支: {memory.branch_name}",
            f"> 导出时间: {datetime.now().isoformat()}",
            "",
            "---",
            "",
            "## 📋 决策记录 (Decisions)",
            ""
        ]

        for note in memory.decisions:
            lines.extend([
                f"### {note.title}",
                f"> 时间: {note.timestamp}",
                f"> 标签: {', '.join(note.tags) or '无'}",
                "",
                note.content,
                ""
            ])

        lines.extend([
            "---",
            "",
            "## 🏆 里程碑 (Milestones)",
            ""
        ])

        for note in memory.milestones:
            lines.extend([
                f"### {note.title}",
                f"> 时间: {note.timestamp}",
                "",
                note.content,
                ""
            ])

        lines.extend([
            "---",
            "",
            "## 💡 经验教训 (Lessons)",
            ""
        ])

        for note in memory.lessons:
            lines.extend([
                f"### {note.title}",
                f"> 时间: {note.timestamp}",
                "",
                note.content,
                ""
            ])

        return "\n".join(lines)

    # ==================== 内部辅助方法 ====================

    def _cache_note(self, note: GitNote) -> None:
        """缓存笔记到内存"""
        branch = note.branch or self._state.current_branch

        if branch not in self._branch_memories:
            self._branch_memories[branch] = BranchMemory(branch_name=branch)

        memory = self._branch_memories[branch]

        if note.note_type == "decision":
            memory.decisions.append(note)
        elif note.note_type == "milestone":
            memory.milestones.append(note)
        elif note.note_type == "lesson":
            memory.lessons.append(note)
        elif note.note_type == "context":
            memory.context.append(note)

    def _publish_note_event(self, event_type: str, note: GitNote) -> None:
        """发布笔记事件"""
        if self._event_bus is None:
            try:
                from .event_bus import get_event_bus
                self._event_bus = get_event_bus()
            except Exception as e:
                self._logger.warning(f"EventBus初始化失败: {e}")
                return

        try:
            self._event_bus.publish(
                event_type=event_type,
                data=note.model_dump(),
                source="GitNotesManager"
            )
        except Exception as e:
            self._logger.error(f"发布事件失败: {e}")

    def _publish_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """发布通用事件"""
        if self._event_bus is None:
            try:
                from .event_bus import get_event_bus
                self._event_bus = get_event_bus()
            except Exception:
                return

        try:
            self._event_bus.publish(
                event_type=event_type,
                data=data,
                source="GitNotesManager"
            )
        except Exception as e:
            self._logger.error(f"发布事件失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        memory = self.get_branch_memories()

        return {
            "current_branch": self._state.current_branch,
            "total_notes": self._state.total_notes,
            "decisions_count": len(memory.decisions),
            "milestones_count": len(memory.milestones),
            "lessons_count": len(memory.lessons),
            "context_count": len(memory.context),
            "last_record_time": self._state.last_record_time,
            "refs_initialized": self._state.refs_initialized
        }


# ============================================================================
# 单例工厂
# ============================================================================

_git_notes_manager_instance: Optional[GitNotesManager] = None
_git_notes_manager_lock = threading.Lock()


def get_git_notes_manager(repo_root: Optional[Path] = None) -> GitNotesManager:
    """
    获取Git-Notes管理器单例实例

    Args:
        repo_root: Git仓库根目录（仅首次调用时有效）

    Returns:
        GitNotesManager: Git-Notes管理器实例
    """
    global _git_notes_manager_instance

    if _git_notes_manager_instance is None:
        with _git_notes_manager_lock:
            if _git_notes_manager_instance is None:
                _git_notes_manager_instance = GitNotesManager(repo_root)

    return _git_notes_manager_instance


def reset_git_notes_manager() -> None:
    """
    重置Git-Notes管理器单例（仅用于测试）
    """
    global _git_notes_manager_instance

    with _git_notes_manager_lock:
        _git_notes_manager_instance = None
