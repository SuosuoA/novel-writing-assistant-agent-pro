"""
AsyncHandler 功能验证测试

测试内容：
1. 任务提交和执行
2. 优先级队列
3. 回调在主线程执行
4. UI按钮点击不阻塞
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from tkinter import ttk
import time
import threading
from core.async_handler import (
    AsyncHandler,
    TaskPriority,
    TaskState,
    get_async_handler,
    init_async_handler,
)


class AsyncHandlerDemo:
    """异步处理器演示窗口"""

    def __init__(self, root):
        self.root = root
        self.root.title("AsyncHandler 功能验证")
        self.root.geometry("600x500")

        # 统计变量（必须在init_async_handler之前初始化）
        self.task_count = 0
        self.completed_count = 0

        # 初始化异步处理器
        self.handler = init_async_handler(root=root, worker_count=4)

        # 创建UI
        self._create_ui()

    def _create_ui(self):
        """创建UI界面"""
        # 控制面板
        control_frame = ttk.LabelFrame(self.root, text="控制面板", padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        # 提交任务按钮
        ttk.Button(
            control_frame,
            text="提交普通任务",
            command=lambda: self.submit_task(TaskPriority.NORMAL),
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            control_frame,
            text="提交高优先级任务",
            command=lambda: self.submit_task(TaskPriority.HIGH),
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            control_frame,
            text="提交后台任务",
            command=lambda: self.submit_task(TaskPriority.BACKGROUND),
        ).pack(side=tk.LEFT, padx=5)

        # 阻塞测试按钮
        ttk.Button(
            control_frame,
            text="测试UI不阻塞",
            command=self.test_ui_responsive,
        ).pack(side=tk.LEFT, padx=5)

        # 日志区域
        log_frame = ttk.LabelFrame(self.root, text="执行日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = tk.Text(log_frame, height=20, state=tk.DISABLED)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 状态栏
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=10, pady=5)

        self.status_label = ttk.Label(status_frame, text="就绪")
        self.status_label.pack(side=tk.LEFT)

        self.stats_label = ttk.Label(status_frame, text="队列: 0 | 完成: 0")
        self.stats_label.pack(side=tk.RIGHT)

        # 定时更新统计
        self._update_stats()

    def log(self, message: str):
        """添加日志（线程安全）"""
        def _append():
            self.log_text.configure(state=tk.NORMAL)
            timestamp = time.strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        # 使用root.after确保在主线程执行
        self.root.after(0, _append)

    def submit_task(self, priority: TaskPriority):
        """提交任务"""
        self.task_count += 1
        task_num = self.task_count

        def long_running_task():
            """模拟耗时操作"""
            time.sleep(2)  # 模拟2秒耗时操作
            return f"任务#{task_num}完成"

        def on_success(result):
            """成功回调"""
            self.completed_count += 1
            self.log(f"✓ {result} [优先级: {priority.name}]")

        def on_error(error):
            """错误回调"""
            self.log(f"✗ 任务#{task_num}失败: {error}")

        task_id = self.handler.submit(
            func=long_running_task,
            callback=on_success,
            error_callback=on_error,
            priority=priority,
            timeout=5.0,
        )

        self.log(f"→ 提交任务#{task_num} [ID: {task_id[:12]}..., 优先级: {priority.name}]")

    def test_ui_responsive(self):
        """测试UI是否响应"""
        self.log("=" * 40)
        self.log("开始UI响应测试")
        self.log("快速点击下方按钮测试UI是否阻塞...")
        self.log("=" * 40)

        # 提交5个耗时任务
        for i in range(5):
            self.submit_task(TaskPriority.NORMAL)

        # 模拟UI操作提示
        def check_responsive():
            self.log("✓ UI保持响应！可以继续操作")

        # 0.5秒后检查UI响应
        self.root.after(500, check_responsive)

    def _update_stats(self):
        """更新统计信息"""
        stats = self.handler.get_statistics()
        self.stats_label.configure(
            text=f"队列: {stats['pending']} | 运行: {stats['running']} | 完成: {self.completed_count}"
        )
        # 每500ms更新一次
        self.root.after(500, self._update_stats)


def test_basic_functionality():
    """基本功能测试"""
    print("=" * 60)
    print("AsyncHandler 基本功能测试")
    print("=" * 60)

    # 创建测试用的Tkinter root
    root = tk.Tk()
    root.withdraw()  # 隐藏窗口

    # 初始化处理器（不使用root，直接执行回调）
    handler = init_async_handler(root=None, worker_count=3)

    results = []

    def task_func(n):
        time.sleep(0.5)
        return f"Task {n} result"

    def on_success(result):
        results.append(("success", result))
        print(f"成功: {result}")

    def on_error(error):
        results.append(("error", str(error)))
        print(f"失败: {error}")

    # 测试1: 基本任务提交
    print("\n1. 测试基本任务提交...")
    task_id = handler.submit(
        func=task_func,
        args=(1,),
        callback=on_success,
        error_callback=on_error,
    )
    print(f"   任务ID: {task_id}")

    # 测试2: 优先级队列
    print("\n2. 测试优先级队列...")
    low_id = handler.submit(
        func=task_func,
        args=(2,),
        callback=on_success,
        priority=TaskPriority.LOW,
    )
    high_id = handler.submit(
        func=task_func,
        args=(3,),
        callback=on_success,
        priority=TaskPriority.HIGH,
    )
    print(f"   低优先级: {low_id}, 高优先级: {high_id}")

    # 测试3: 任务状态查询
    print("\n3. 测试任务状态查询...")
    time.sleep(0.1)
    state = handler.get_task_state(task_id)
    print(f"   任务状态: {state.name if state else 'None'}")

    # 测试4: 统计信息
    print("\n4. 测试统计信息...")
    stats = handler.get_statistics()
    print(f"   统计: {stats}")

    # 等待任务完成
    print("\n5. 等待任务完成...")
    time.sleep(2)

    stats = handler.get_statistics()
    print(f"   完成后统计: {stats}")

    # 清理
    handler.shutdown()
    root.destroy()

    print("\n" + "=" * 60)
    print("基本功能测试完成!")
    print("=" * 60)


def main():
    """主函数"""
    # 先运行基本功能测试
    test_basic_functionality()

    # 启动GUI演示
    print("\n启动GUI演示...")
    root = tk.Tk()
    app = AsyncHandlerDemo(root)
    root.mainloop()


if __name__ == "__main__":
    main()
