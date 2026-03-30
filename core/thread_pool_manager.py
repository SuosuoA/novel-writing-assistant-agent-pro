"""
统一线程池管理器

核心职责：
1. 整合AsyncHandler的ThreadPoolExecutor
2. 整合threading.Thread的创建
3. 提供AsyncIO事件循环
4. 统一管理所有线程资源

解决问题：
- P1-3: AsyncHandler与AsyncLoopManager的冲突
- P1-4: 三套线程池并存风险

版本: V1.0
日期: 2026-03-28
"""
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional, Callable, Any, Coroutine, Dict
import logging
import atexit
import time

logger = logging.getLogger(__name__)


class ThreadPoolManager:
    """
    统一线程池管理器（单例模式）
    
    使用方式：
        # 初始化（在程序启动时调用一次）
        pool_manager = ThreadPoolManager()
        
        # 提交同步任务
        future = pool_manager.submit_sync(some_function, arg1, arg2)
        
        # 提交异步任务
        future = pool_manager.submit_async(some_async_function(arg1, arg2))
        
        # 在线程池中执行同步函数（异步接口）
        result = await pool_manager.run_in_executor(sync_function, arg1)
        
        # 关闭（在程序退出时自动调用）
        pool_manager.shutdown()
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """初始化线程资源"""
        self._initialized = False
        
        # 统一线程池（替代AsyncHandler的线程池）
        self._executor = ThreadPoolExecutor(
            max_workers=8,  # 可配置，推荐8
            thread_name_prefix="unified_worker"
        )
        
        # 统一事件循环（替代AsyncLoopManager的循环）
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="unified_event_loop"
        )
        self._loop_thread.start()
        
        # 任务追踪（用于状态监控）
        self._active_tasks: Dict[int, str] = {}
        self._task_counter = 0
        self._task_lock = threading.Lock()
        
        # 注册退出清理
        atexit.register(self.shutdown)
        
        self._initialized = True
        
        logger.info("ThreadPoolManager initialized with 8 workers and event loop")
    
    def _run_loop(self):
        """运行事件循环"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
    
    def submit_sync(self, func: Callable, *args, **kwargs) -> Future:
        """
        提交同步任务到线程池
        
        Args:
            func: 同步函数
            *args: 位置参数
            **kwargs: 关键字参数
        
        Returns:
            Future对象
        
        示例:
            future = pool_manager.submit_sync(time_consuming_task, data)
            result = future.result(timeout=30)
        """
        # 分配任务ID
        with self._task_lock:
            self._task_counter += 1
            task_id = self._task_counter
            self._active_tasks[task_id] = f"sync:{func.__name__}"
        
        # 包装任务以便追踪
        def wrapped_task():
            try:
                return func(*args, **kwargs)
            finally:
                with self._task_lock:
                    self._active_tasks.pop(task_id, None)
        
        return self._executor.submit(wrapped_task)
    
    def submit_async(
        self,
        coro: Coroutine,
        on_complete: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ) -> Future:
        """
        提交异步任务到事件循环
        
        Args:
            coro: 异步协程对象
            on_complete: 完成回调（可选）
            on_error: 错误回调（可选）
        
        Returns:
            Future对象
        
        示例:
            future = pool_manager.submit_async(
                api_call_async(data),
                on_complete=lambda r: print(r)
            )
        """
        # 分配任务ID
        with self._task_lock:
            self._task_counter += 1
            task_id = self._task_counter
            task_name = f"async:{coro.__name__ if hasattr(coro, '__name__') else 'coroutine'}"
            self._active_tasks[task_id] = task_name
        
        # 线程安全地向事件循环提交任务
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        
        # 添加完成回调
        def wrapper(f: Future):
            try:
                result = f.result()
                if on_complete:
                    on_complete(result)
            except Exception as e:
                if on_error:
                    on_error(e)
                else:
                    logger.error(f"Async task failed: {e}")
            finally:
                with self._task_lock:
                    self._active_tasks.pop(task_id, None)
        
        future.add_done_callback(wrapper)
        
        return future
    
    async def run_in_executor(self, func: Callable, *args, **kwargs) -> Any:
        """
        在线程池中执行同步函数（异步接口）
        
        核心用途：
        - 包装V5核心模块的同步方法
        - 不修改V5代码，仅包装调用
        
        Args:
            func: 同步函数
            *args: 位置参数
            **kwargs: 关键字参数
        
        Returns:
            函数执行结果
        
        示例:
            # 包装V5同步方法
            result = await pool_manager.run_in_executor(
                iterative_generate_sync,  # V5原方法
                context
            )
        """
        loop = asyncio.get_event_loop()
        if loop is None:
            # 如果当前没有事件循环，使用全局循环
            loop = self._loop
        
        return await loop.run_in_executor(
            self._executor,
            lambda: func(*args, **kwargs)
        )
    
    def shutdown(self):
        """关闭所有资源"""
        if not self._initialized:
            return
            
        try:
            # 停止事件循环
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            
            # 关闭线程池
            if self._executor:
                self._executor.shutdown(wait=True, cancel_futures=False)
            
            logger.info("ThreadPoolManager shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    @property
    def is_running(self) -> bool:
        """事件循环是否运行中"""
        return self._loop.is_running() if self._loop else False
    
    def get_status(self) -> dict:
        """获取线程池状态"""
        with self._task_lock:
            active_count = len(self._active_tasks)
            active_tasks = dict(self._active_tasks)
        
        return {
            "executor_workers": 8,
            "loop_running": self._loop.is_running() if self._loop else False,
            "loop_thread_alive": self._loop_thread.is_alive() if self._loop_thread else False,
            "active_tasks": active_count,
            "active_task_details": active_tasks,
            "total_tasks_submitted": self._task_counter
        }
    
    def cancel_all_tasks(self):
        """取消所有活跃任务（尽力而为）"""
        logger.warning("Attempting to cancel all active tasks")
        # 注意：Python的Future取消是尽力而为的
        # 正在执行的任务无法被强制中断
        self.shutdown()


class GUIAsyncHelper:
    """
    GUI异步任务辅助类
    
    为Tkinter GUI提供线程安全的异步任务提交和回调机制
    
    核心机制：
    1. 通过ThreadPoolManager提交任务
    2. 任务在统一线程池中执行
    3. 完成后通过root.after()回调主线程更新GUI
    
    参考：
    - deepinout: tkinter的after方法是线程安全的
    - runebook.dev: 所有GUI更新必须在主线程
    """
    
    def __init__(self, root, pool_manager: ThreadPoolManager = None):
        """
        初始化GUI异步辅助
        
        Args:
            root: Tkinter根窗口
            pool_manager: 线程池管理器实例（可选，默认使用全局单例）
        """
        self.root = root
        self._pool = pool_manager or thread_pool_manager
        self._current_task_future = None
        self._cancel_requested = threading.Event()
    
    def submit_async_task(
        self,
        coro: Coroutine,
        on_complete: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> Future:
        """
        提交异步任务（线程安全）
        
        Args:
            coro: 异步协程对象
            on_complete: 完成回调（在主线程执行）
            on_error: 错误回调（在主线程执行）
            on_progress: 进度回调（在主线程执行）
        
        Returns:
            Future对象
        """
        # 重置取消标志
        self._cancel_requested.clear()
        
        def on_task_complete(result):
            """任务完成回调（在主线程中执行）"""
            try:
                # 检查是否已取消
                if self._cancel_requested.is_set():
                    if on_progress:
                        self.root.after(0, lambda: on_progress("已取消"))
                    return
                
                # 在主线程中执行完成回调
                if on_complete:
                    self.root.after(0, lambda: on_complete(result))
                    
            except Exception as e:
                # 在主线程中执行错误回调
                if on_error:
                    self.root.after(0, lambda: on_error(e))
                else:
                    logger.error(f"Task completion error: {e}")
            
            finally:
                self._current_task_future = None
        
        def on_task_error(error):
            """任务错误回调"""
            if on_error:
                self.root.after(0, lambda: on_error(error))
            else:
                logger.error(f"Task error: {error}")
            self._current_task_future = None
        
        # 提交任务
        self._current_task_future = self._pool.submit_async(
            coro,
            on_complete=on_task_complete,
            on_error=on_task_error
        )
        
        return self._current_task_future
    
    def submit_sync_task(
        self,
        func: Callable,
        *args,
        on_complete: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        **kwargs
    ) -> Future:
        """
        提交同步任务（线程安全）
        
        Args:
            func: 同步函数
            *args: 位置参数
            on_complete: 完成回调（在主线程执行）
            on_error: 错误回调（在主线程执行）
            **kwargs: 关键字参数
        
        Returns:
            Future对象
        """
        # 重置取消标志
        self._cancel_requested.clear()
        
        future = self._pool.submit_sync(func, *args, **kwargs)
        self._current_task_future = future
        
        def on_done(f: Future):
            try:
                if self._cancel_requested.is_set():
                    if on_complete:
                        self.root.after(0, lambda: on_complete(None))
                    return
                
                result = f.result()
                if on_complete:
                    self.root.after(0, lambda: on_complete(result))
            except Exception as e:
                if on_error:
                    self.root.after(0, lambda: on_error(e))
                else:
                    logger.error(f"Sync task error: {e}")
            finally:
                self._current_task_future = None
        
        future.add_done_callback(on_done)
        return future
    
    def cancel_current_task(self) -> bool:
        """
        取消当前任务
        
        Returns:
            是否成功取消
        """
        if self._current_task_future:
            # 设置取消标志
            self._cancel_requested.set()
            
            # 尝试取消Future（如果任务还没开始）
            cancelled = self._current_task_future.cancel()
            
            return cancelled
        return False
    
    def is_task_running(self) -> bool:
        """是否有任务正在运行"""
        return self._current_task_future is not None and not self._current_task_future.done()
    
    def update_progress_on_main_thread(self, callback: Callable[[str], None], message: str):
        """
        在主线程中更新进度（线程安全）
        
        Args:
            callback: 进度回调函数
            message: 进度消息
        """
        self.root.after(0, lambda: callback(message))


# 全局单例
thread_pool_manager = ThreadPoolManager()
