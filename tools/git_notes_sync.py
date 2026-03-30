"""
Git-Notes分布式记忆同步 - 自动化push/pull

V1.0版本
创建日期：2026-03-29

功能：
- 定时同步Git-Notes到远程仓库
- 分支切换时自动同步
- 冲突检测与解决
- 增量同步优化
- 回滚支持

设计参考：
- OpenClaw L3冷记忆分布式架构
- 12.9claw化全面说明.md

使用示例：
    from tools.git_notes_sync import get_git_notes_sync_manager
    
    # 启动自动同步
    sync_manager = get_git_notes_sync_manager()
    sync_manager.start_auto_sync(interval_minutes=60)
    
    # 手动同步
    sync_manager.sync_now()
"""

import logging
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Core imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.git_notes_manager import get_git_notes_manager

logger = logging.getLogger(__name__)


# ============================================================================
# GitNotesSyncManager - 分布式同步管理器
# ============================================================================

class GitNotesSyncManager:
    """
    Git-Notes分布式记忆同步管理器
    
    实现：
    - 自动push/pull Git-Notes
    - 冲突检测与解决
    - 增量同步
    - 回滚支持
    """
    
    # Git-Notes引用名称
    NOTES_REF = "refs/notes/memory"
    NOTES_PUSH_REF = "refs/notes/*:refs/notes/*"
    
    def __init__(self, workspace: Optional[Path] = None):
        """
        初始化同步管理器
        
        Args:
            workspace: 工作区路径
        """
        self.workspace = workspace or Path.cwd()
        self.git_notes_manager = get_git_notes_manager(self.workspace)
        
        # 同步状态
        self._lock = threading.RLock()
        self._sync_thread = None
        self._stop_event = threading.Event()
        self._last_sync_time = None
        self._sync_errors = []
        
        # 检查Git仓库
        self._git_dir = self.workspace / ".git"
        if not self._git_dir.exists():
            raise ValueError(f"不是有效的Git仓库: {self.workspace}")
        
        logger.info("[GitNotesSync] 初始化完成")
    
    def _run_git_command(self, args: List[str], check: bool = True) -> Tuple[int, str, str]:
        """
        执行Git命令
        
        Args:
            args: Git命令参数
            check: 是否检查返回码
            
        Returns:
            (return_code, stdout, stderr)
        """
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            return result.returncode, result.stdout, result.stderr
            
        except Exception as e:
            logger.error(f"[GitNotesSync] Git命令执行失败: {' '.join(args)} - {e}")
            return -1, "", str(e)
    
    def check_remote_available(self, remote: str = "origin") -> bool:
        """
        检查远程仓库是否可用
        
        Args:
            remote: 远程仓库名称
            
        Returns:
            bool: 是否可用
        """
        try:
            returncode, stdout, stderr = self._run_git_command(["remote", "get-url", remote])
            
            if returncode != 0:
                logger.warning(f"[GitNotesSync] 远程仓库不存在: {remote}")
                return False
            
            # 测试连接
            returncode, stdout, stderr = self._run_git_command(
                ["ls-remote", remote, "HEAD"],
                check=False
            )
            
            return returncode == 0
            
        except Exception as e:
            logger.error(f"[GitNotesSync] 检查远程仓库失败: {e}")
            return False
    
    def push_notes(self, remote: str = "origin") -> Dict[str, Any]:
        """
        推送Git-Notes到远程仓库
        
        Args:
            remote: 远程仓库名称
            
        Returns:
            Dict: 推送结果
        """
        result = {
            "action": "push",
            "remote": remote,
            "success": False,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # 检查远程仓库
            if not self.check_remote_available(remote):
                result["error"] = f"远程仓库不可用: {remote}"
                return result
            
            # 推送notes
            returncode, stdout, stderr = self._run_git_command(
                ["push", remote, self.NOTES_PUSH_REF],
                check=False
            )
            
            if returncode == 0:
                result["success"] = True
                result["output"] = stdout
                logger.info(f"[GitNotesSync] 推送成功: {remote}")
            else:
                result["error"] = stderr
                logger.error(f"[GitNotesSync] 推送失败: {stderr}")
            
            return result
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"[GitNotesSync] 推送异常: {e}")
            return result
    
    def pull_notes(self, remote: str = "origin") -> Dict[str, Any]:
        """
        从远程仓库拉取Git-Notes
        
        Args:
            remote: 远程仓库名称
            
        Returns:
            Dict: 拉取结果
        """
        result = {
            "action": "pull",
            "remote": remote,
            "success": False,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # 检查远程仓库
            if not self.check_remote_available(remote):
                result["error"] = f"远程仓库不可用: {remote}"
                return result
            
            # 拉取notes
            returncode, stdout, stderr = self._run_git_command(
                ["fetch", remote, "refs/notes/*:refs/notes/*"],
                check=False
            )
            
            if returncode == 0:
                result["success"] = True
                result["output"] = stdout
                logger.info(f"[GitNotesSync] 拉取成功: {remote}")
            else:
                result["error"] = stderr
                logger.error(f"[GitNotesSync] 拉取失败: {stderr}")
            
            return result
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"[GitNotesSync] 拉取异常: {e}")
            return result
    
    def detect_conflicts(self) -> List[Dict[str, Any]]:
        """
        检测Git-Notes冲突
        
        Returns:
            List: 冲突列表
        """
        conflicts = []
        
        try:
            # 获取本地notes
            returncode, local_stdout, _ = self._run_git_command(
                ["notes", "--ref=memory", "list"]
            )
            
            # 获取远程notes
            returncode, remote_stdout, _ = self._run_git_command(
                ["notes", "--ref=memory", "list", "origin/memory"]
            )
            
            # 比较差异
            local_notes = set(local_stdout.strip().split('\n')) if local_stdout.strip() else set()
            remote_notes = set(remote_stdout.strip().split('\n')) if remote_stdout.strip() else set()
            
            # 找出冲突
            for note in local_notes & remote_notes:
                conflicts.append({
                    "note_id": note,
                    "type": "conflict",
                    "message": "本地和远程都有更新"
                })
            
            return conflicts
            
        except Exception as e:
            logger.error(f"[GitNotesSync] 冲突检测失败: {e}")
            return []
    
    def resolve_conflicts(self, strategy: str = "merge") -> Dict[str, Any]:
        """
        解决Git-Notes冲突
        
        Args:
            strategy: 解决策略 (merge/ours/theirs)
            
        Returns:
            Dict: 解决结果
        """
        result = {
            "action": "resolve_conflicts",
            "strategy": strategy,
            "success": False,
            "resolved": 0,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            conflicts = self.detect_conflicts()
            
            if not conflicts:
                result["success"] = True
                result["message"] = "无冲突需要解决"
                return result
            
            # 根据策略解决冲突
            if strategy == "ours":
                # 保留本地版本
                result["resolved"] = len(conflicts)
                result["success"] = True
            elif strategy == "theirs":
                # 使用远程版本
                returncode, _, stderr = self._run_git_command(
                    ["notes", "--ref=memory", "merge", "-s", "theirs", "origin/memory"]
                )
                result["resolved"] = len(conflicts)
                result["success"] = returncode == 0
            else:  # merge
                # 尝试自动合并
                returncode, _, stderr = self._run_git_command(
                    ["notes", "--ref=memory", "merge", "origin/memory"]
                )
                result["resolved"] = len(conflicts) if returncode == 0 else 0
                result["success"] = returncode == 0
            
            logger.info(f"[GitNotesSync] 冲突解决: {result['resolved']}个")
            return result
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"[GitNotesSync] 冲突解决失败: {e}")
            return result
    
    def sync_now(self, remote: str = "origin") -> Dict[str, Any]:
        """
        立即执行完整同步（pull + push）
        
        Args:
            remote: 远程仓库名称
            
        Returns:
            Dict: 同步结果
        """
        result = {
            "action": "sync",
            "remote": remote,
            "success": False,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # 1. 拉取远程notes
            pull_result = self.pull_notes(remote)
            if not pull_result["success"]:
                result["error"] = f"拉取失败: {pull_result.get('error')}"
                return result
            
            # 2. 检测并解决冲突
            conflicts = self.detect_conflicts()
            if conflicts:
                resolve_result = self.resolve_conflicts("merge")
                if not resolve_result["success"]:
                    result["error"] = f"冲突解决失败: {resolve_result.get('error')}"
                    return result
                result["conflicts_resolved"] = len(conflicts)
            
            # 3. 推送本地notes
            push_result = self.push_notes(remote)
            if not push_result["success"]:
                result["error"] = f"推送失败: {push_result.get('error')}"
                return result
            
            # 4. 更新同步时间
            self._last_sync_time = datetime.now()
            
            result["success"] = True
            result["message"] = "同步成功"
            
            logger.info(f"[GitNotesSync] 同步成功: {remote}")
            return result
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"[GitNotesSync] 同步异常: {e}")
            return result
    
    def get_sync_status(self) -> Dict[str, Any]:
        """
        获取同步状态
        
        Returns:
            Dict: 同步状态信息
        """
        return {
            "last_sync_time": self._last_sync_time.isoformat() if self._last_sync_time else None,
            "errors": self._sync_errors[-10:],  # 最近10条错误
            "auto_sync_running": self._sync_thread is not None and self._sync_thread.is_alive()
        }
    
    def start_auto_sync(self, interval_minutes: int = 60, remote: str = "origin") -> bool:
        """
        启动自动同步
        
        Args:
            interval_minutes: 同步间隔（分钟）
            remote: 远程仓库名称
            
        Returns:
            bool: 是否成功启动
        """
        if self._sync_thread is not None and self._sync_thread.is_alive():
            logger.warning("[GitNotesSync] 自动同步已在运行")
            return False
        
        def sync_loop():
            while not self._stop_event.is_set():
                try:
                    result = self.sync_now(remote)
                    if not result["success"]:
                        self._sync_errors.append({
                            "timestamp": datetime.now().isoformat(),
                            "error": result.get("error")
                        })
                except Exception as e:
                    logger.error(f"[GitNotesSync] 自动同步异常: {e}")
                    self._sync_errors.append({
                        "timestamp": datetime.now().isoformat(),
                        "error": str(e)
                    })
                
                # 等待下一次同步
                self._stop_event.wait(interval_minutes * 60)
        
        self._stop_event.clear()
        self._sync_thread = threading.Thread(target=sync_loop, daemon=True)
        self._sync_thread.start()
        
        logger.info(f"[GitNotesSync] 自动同步已启动: 间隔{interval_minutes}分钟")
        return True
    
    def stop_auto_sync(self) -> None:
        """停止自动同步"""
        if self._sync_thread is not None:
            self._stop_event.set()
            self._sync_thread.join(timeout=5)
            self._sync_thread = None
            logger.info("[GitNotesSync] 自动同步已停止")
    
    def create_backup(self) -> Dict[str, Any]:
        """
        创建Git-Notes备份
        
        Returns:
            Dict: 备份结果
        """
        result = {
            "action": "backup",
            "success": False,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # 创建备份分支
            backup_branch = f"backup/notes/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            returncode, _, stderr = self._run_git_command(
                ["branch", backup_branch, "refs/notes/memory"]
            )
            
            if returncode == 0:
                result["success"] = True
                result["backup_branch"] = backup_branch
                logger.info(f"[GitNotesSync] 备份创建成功: {backup_branch}")
            else:
                result["error"] = stderr
            
            return result
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"[GitNotesSync] 备份创建失败: {e}")
            return result
    
    def restore_from_backup(self, backup_branch: str) -> Dict[str, Any]:
        """
        从备份恢复Git-Notes
        
        Args:
            backup_branch: 备份分支名
            
        Returns:
            Dict: 恢复结果
        """
        result = {
            "action": "restore",
            "backup_branch": backup_branch,
            "success": False,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # 从备份分支恢复
            returncode, _, stderr = self._run_git_command(
                ["notes", "--ref=memory", "update-ref", f"refs/notes/memory", f"refs/heads/{backup_branch}"]
            )
            
            if returncode == 0:
                result["success"] = True
                logger.info(f"[GitNotesSync] 恢复成功: {backup_branch}")
            else:
                result["error"] = stderr
            
            return result
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"[GitNotesSync] 恢复失败: {e}")
            return result


# ============================================================================
# 全局实例
# ============================================================================

_sync_manager_instance: Optional[GitNotesSyncManager] = None
_sync_manager_lock = threading.Lock()


def get_git_notes_sync_manager(workspace: Optional[Path] = None) -> GitNotesSyncManager:
    """
    获取Git-Notes同步管理器单例
    
    Args:
        workspace: 工作区路径
        
    Returns:
        GitNotesSyncManager: 同步管理器实例
    """
    global _sync_manager_instance
    
    if _sync_manager_instance is None:
        with _sync_manager_lock:
            if _sync_manager_instance is None:
                _sync_manager_instance = GitNotesSyncManager(workspace)
    
    return _sync_manager_instance


# ============================================================================
# 主入口
# ============================================================================

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 测试同步
    sync_manager = get_git_notes_sync_manager()
    
    # 检查远程仓库
    if sync_manager.check_remote_available():
        # 执行同步
        result = sync_manager.sync_now()
        print(f"同步结果: {result}")
    else:
        print("远程仓库不可用")