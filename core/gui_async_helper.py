"""
GUI异步任务辅助模块

提供GUI层异步任务提交的封装，确保线程安全的UI更新。

版本: V1.0
创建日期: 2026-03-28
作者: 后端架构师

使用方法:
    from core.gui_async_helper import GUIAsyncHelper
    
    # 在GUI类初始化时创建helper
    self._async_helper = GUIAsyncHelper(self.root)
    
    # 提交异步任务
    self._async_helper.submit_task(
        coro=generation_service.generate_chapter_async(...),
        on_complete=lambda result: self._update_result(result),
        on_error=lambda error: self._show_error(str(error)),
        on_progress=lambda status: self._update_status(status)
    )
"""

import threading
from typing import Any, Callable, Coroutine, Optional
import logging

logger = logging.getLogger(__name__)


class GUIAsyncHelper:
    """
    GUI异步任务辅助类
    
    核心职责：
    1. 封装ThreadPoolManager的任务提交
    2. 确保所有GUI更新通过root.after()回调主线程
    3. 提供任务取消功能
    4. 管理任务生命周期
    
    Tkinter线程安全规范：
    - 所有UI操作必须在主线程执行
    - 异步任务完成后通过root.after(0, callback)更新UI
    """
    
    def __init__(self, root):
        """
        初始化GUI异步助手
        
        Args:
            root: Tkinter根窗口
        """
        self._root = root
        self._current_task_future = None
        self._cancel_requested = threading.Event()
        self._lock = threading.RLock()
        
        logger.info("GUIAsyncHelper initialized")
    
    def submit_task(
        self,
        coro: Coroutine,
        on_complete: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        提交异步任务（线程安全）
        
        核心机制：
        1. 通过ThreadPoolManager提交任务
        2. 任务在统一线程池中执行
        3. 完成后通过root.after()回调主线程更新GUI
        
        Args:
            coro: 异步协程对象
            on_complete: 完成回调（在主线程执行）
            on_error: 错误回调（在主线程执行）
            on_progress: 进度回调（在主线程执行）
            
        Returns:
            str: 任务ID
        """
        from core.thread_pool_manager import thread_pool_manager
        
        # 重置取消标志
        self._cancel_requested.clear()
        
        # 任务ID
        task_id = f"task_{id(coro)}"
        
        def _on_task_complete(result):
            """任务完成回调（在主线程中执行）"""
            with self._lock:
                self._current_task_future = None
            
            # 检查是否已取消
            if self._cancel_requested.is_set():
                self._safe_callback(on_progress, "已取消")
                return
            
            # 在主线程中执行完成回调
            self._safe_callback(on_complete, result)
        
        def _on_task_error(error):
            """任务错误回调"""
            with self._lock:
                self._current_task_future = None
            
            # 在主线程中执行错误回调
            self._safe_callback(on_error, error)
        
        # 提交任务
        self._current_task_future = thread_pool_manager.submit_async(
            coro,
            on_complete=_on_task_complete,
            on_error=_on_task_error
        )
        
        logger.debug(f"Task submitted: {task_id}")
        return task_id
    
    def _safe_callback(self, callback: Optional[Callable], *args):
        """
        安全执行回调（确保在主线程）
        
        通过root.after(0, ...)确保回调在主线程执行
        """
        if callback:
            try:
                # 使用after(0, ...)确保在主线程执行
                self._root.after(0, lambda: callback(*args))
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def cancel_task(self) -> bool:
        """
        取消当前任务
        
        Returns:
            bool: 是否成功取消
        """
        with self._lock:
            if self._current_task_future:
                # 设置取消标志
                self._cancel_requested.set()
                
                # 尝试取消Future
                try:
                    cancelled = self._current_task_future.cancel()
                    logger.info(f"Task cancel requested: {cancelled}")
                    return cancelled
                except Exception as e:
                    logger.error(f"Cancel error: {e}")
                    return False
            return True
    
    def is_task_running(self) -> bool:
        """检查是否有任务正在运行"""
        with self._lock:
            return self._current_task_future is not None
    
    def shutdown(self):
        """关闭助手"""
        self.cancel_task()
        logger.info("GUIAsyncHelper shutdown")


# 便捷函数
def create_async_helper(root):
    """创建GUI异步助手"""
    return GUIAsyncHelper(root)
