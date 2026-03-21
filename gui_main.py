"""
Novel Writing Assistant - Agent Pro
主入口文件

V1.0版本
创建日期：2026-03-21

特性：
- 优化启动流程（<1秒）
- 隐藏窗口启动
- 异步加载非核心模块
- 启动完成后显示窗口
"""

import sys
import time
import logging
import tkinter as tk
from tkinter import ttk
from pathlib import Path

# 配置基础日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def create_main_window() -> tk.Tk:
    """创建主窗口"""
    root = tk.Tk()
    root.title("Novel Writing Assistant - Agent Pro")
    root.geometry("1200x800")
    root.minsize(800, 600)
    
    # 配置主题
    try:
        import sv_ttk
        sv_ttk.set_theme("dark")
        logger.info("sv_ttk theme applied")
    except ImportError:
        logger.warning("sv_ttk not available, using default theme")
    
    return root


def create_ui_components(root: tk.Tk, launcher) -> None:
    """创建UI组件"""
    # 主框架
    main_frame = ttk.Frame(root, padding="10")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # 标题栏
    title_frame = ttk.Frame(main_frame)
    title_frame.pack(fill=tk.X, pady=(0, 10))
    
    title_label = ttk.Label(
        title_frame,
        text="Novel Writing Assistant - Agent Pro",
        font=("Arial", 18, "bold")
    )
    title_label.pack(side=tk.LEFT)
    
    # 状态栏
    status_frame = ttk.Frame(main_frame)
    status_frame.pack(fill=tk.X, pady=(0, 10))
    
    status_label = ttk.Label(
        status_frame,
        text="准备就绪",
        font=("Arial", 10)
    )
    status_label.pack(side=tk.LEFT)
    
    # 主要内容区域
    content_frame = ttk.Frame(main_frame)
    content_frame.pack(fill=tk.BOTH, expand=True)
    
    # 左侧导航
    nav_frame = ttk.Frame(content_frame, width=200)
    nav_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
    nav_frame.pack_propagate(False)
    
    # 导航按钮
    nav_buttons = [
        ("📝 大纲管理", lambda: show_panel("outline")),
        ("👥 人物设定", lambda: show_panel("characters")),
        ("🌍 世界观", lambda: show_panel("worldview")),
        ("📊 风格学习", lambda: show_panel("style")),
        ("✍️ 章节生成", lambda: show_panel("generation")),
        ("📈 热榜功能", lambda: show_panel("ranking")),
        ("⚙️ 设置", lambda: show_panel("settings")),
    ]
    
    for text, command in nav_buttons:
        btn = ttk.Button(nav_frame, text=text, command=command)
        btn.pack(fill=tk.X, pady=2)
    
    # 右侧内容区
    right_frame = ttk.Frame(content_frame)
    right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    # 内容区标题
    content_title = ttk.Label(
        right_frame,
        text="欢迎使用 Novel Writing Assistant",
        font=("Arial", 14, "bold")
    )
    content_title.pack(pady=10)
    
    # 内容区文本
    content_text = tk.Text(
        right_frame,
        wrap=tk.WORD,
        font=("Arial", 11),
        padx=10,
        pady=10
    )
    content_text.pack(fill=tk.BOTH, expand=True)
    content_text.insert("1.0", """
欢迎使用 Novel Writing Assistant - Agent Pro！

这是一个智能小说写作辅助工具，基于 Agent 架构构建，
提供以下核心功能：

1. 📝 大纲管理
   - 支持大纲解析和管理
   - 章节结构可视化

2. 👥 人物设定
   - 人物卡管理
   - 人物关系图谱

3. 🌍 世界观
   - 世界观设定管理
   - 设定一致性检查

4. 📊 风格学习
   - 从样本文本学习写作风格
   - 风格特征分析

5. ✍️ 章节生成
   - AI智能生成章节内容
   - 多维度质量评分
   - 迭代优化

6. 📈 热榜功能
   - 追更热榜
   - 推荐热榜

点击左侧导航按钮开始使用。
""")
    content_text.config(state=tk.DISABLED)
    
    # 底部状态栏
    bottom_frame = ttk.Frame(root)
    bottom_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
    
    # 启动时间显示
    startup_time_label = ttk.Label(
        bottom_frame,
        text=f"启动时间: {launcher.get_startup_time():.3f}s",
        font=("Arial", 9)
    )
    startup_time_label.pack(side=tk.LEFT, padx=10)
    
    # 版本信息
    version_label = ttk.Label(
        bottom_frame,
        text="V1.0.0 | Agent Pro",
        font=("Arial", 9)
    )
    version_label.pack(side=tk.RIGHT, padx=10)
    
    # 存储状态标签引用
    root._status_label = status_label
    root._content_text = content_text
    root._content_title = content_title


def show_panel(panel_name: str) -> None:
    """显示面板（占位实现）"""
    logger.info(f"Show panel: {panel_name}")


def on_startup_complete(startup_time: float) -> None:
    """启动完成回调"""
    logger.info(f"Startup complete in {startup_time:.3f}s")


def main():
    """主入口"""
    start_time = time.time()
    logger.info("Starting Novel Writing Assistant...")
    
    # 导入启动器
    from core.app_launcher import OptimizedLauncher, LoadPriority
    
    # 创建主窗口
    root = create_main_window()
    
    # 创建启动器
    launcher = OptimizedLauncher()
    
    # 配置启动参数
    launcher.configure(
        show_splash=False,
        min_show_time=0.0,
        async_load=True,
        hide_window_on_start=True,
        target_startup_time=1.0
    )
    
    # 注册启动完成回调
    launcher.register_complete_callback(on_startup_complete)
    
    # 隐藏窗口
    root.withdraw()
    
    # 启动应用（加载核心层）
    core_startup_time = launcher.start(root)
    logger.info(f"Core startup time: {core_startup_time:.3f}s")
    
    # 创建UI组件
    create_ui_components(root, launcher)
    
    # 显示窗口
    root.deiconify()
    
    total_time = time.time() - start_time
    logger.info(f"Total startup time: {total_time:.3f}s")
    
    # 运行主循环
    root.mainloop()
    
    # 清理
    launcher.shutdown()


if __name__ == "__main__":
    main()
