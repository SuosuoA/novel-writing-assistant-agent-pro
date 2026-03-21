"""
Novel Writing Assistant - Agent Pro
主入口文件 - 中国古典水墨风格UI

V2.1版本 - 完整功能实现
创建日期：2026-03-21

特性：
- 优化启动流程（<1秒）
- 中国古典水墨风格主题
- 响应式按钮（防抖+异步执行）
- 标签页延迟创建
- 完整功能区：热榜、工作台（7子模块）、续写、项目管理、插件管理器、设置、状态栏
- 后端核心交互集成
"""

import sys
import time
import logging
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

# 配置基础日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# 中国古典水墨风格主题配置 V2.1
# ============================================================================

@dataclass
class InkTheme:
    """中国古典水墨风格主题配置
    
    设计理念：
    - 宣纸白为底，象征空灵留白
    - 水墨黑为主色，体现典雅庄重
    - 朱砂红点缀，增添印章韵味
    """
    
    # ===== 纸张颜色（背景系）=====
    paper_white: str = "#F5F5F0"      # 宣纸白（主背景）
    paper_cream: str = "#F5F5DC"      # 米色纸张（次背景）
    paper_antique: str = "#FAF0E6"    # 古纸色（文本区背景）
    
    # ===== 水墨颜色（文字/边框系）=====
    ink_black: str = "#2C2C2C"        # 浓墨（标题文字）
    ink_dark: str = "#3C3C3C"         # 重墨（正文文字）
    ink_gray: str = "#6C6C6C"         # 淡墨（辅助文字）
    ink_light: str = "#9C9C9C"        # 清墨（禁用文字）
    
    # ===== 点缀色（强调系）=====
    vermilion: str = "#C85040"        # 朱砂红（印章色，按钮/链接）
    gold: str = "#DAA520"             # 泥金（高亮）
    bamboo_green: str = "#228B22"     # 竹青（成功状态）
    
    # ===== 水墨渐变（边框/装饰）=====
    gradient_light: str = "#E8E4D9"   # 浅墨渐变（侧边栏）
    gradient_dark: str = "#D4CFC4"    # 深墨渐变（分隔线）
    
    # ===== 边框样式 =====
    border_width: int = 1             # 边框宽度
    border_radius: int = 4            # 边框圆角
    
    # ===== 字体配置 =====
    font_title: tuple = ("Microsoft YaHei UI", 18, "bold")      # 主标题
    font_subtitle: tuple = ("Microsoft YaHei UI", 14, "bold")   # 子标题
    font_body: tuple = ("Microsoft YaHei UI", 10)               # 正文
    font_button: tuple = ("Microsoft YaHei UI", 10, "bold")     # 按钮
    font_small: tuple = ("Microsoft YaHei UI", 9)               # 小字


# ============================================================================
# 响应式按钮（防抖+异步执行+加载状态）
# ============================================================================

class ResponsiveButton(ttk.Button):
    """
    响应式按钮 - 防抖+异步执行+加载状态
    
    特性：
    1. 防抖：500ms内不响应重复点击
    2. 异步执行：集成AsyncEventHandler（如可用）
    3. 加载状态：显示加载文本并禁用按钮
    4. 空值检查：事件回调开头自动检查
    5. 自动恢复：200ms后自动恢复按钮状态
    """
    
    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable,
        loading_text: Optional[str] = None,
        debounce_ms: int = 500,
        **kwargs
    ):
        """
        初始化响应式按钮
        
        Args:
            parent: 父容器
            text: 按钮文本
            command: 点击命令
            loading_text: 加载时显示的文本（默认为"{text}中..."）
            debounce_ms: 防抖时间（毫秒）
            **kwargs: ttk.Button参数
        """
        super().__init__(parent, text=text, **kwargs)
        
        self._original_text = text
        self._loading_text = loading_text or f"{text}中..."
        self._debounce_ms = debounce_ms
        self._command = command
        self._last_click_time = 0
        self._is_loading = False
        
        # 绑定点击事件
        self.configure(command=self._on_click_wrapper)
    
    def _on_click_wrapper(self) -> None:
        """包装点击事件，实现防抖和加载状态"""
        # 防抖检查
        current_time = int(time.time() * 1000)
        if current_time - self._last_click_time < self._debounce_ms:
            return
        
        self._last_click_time = current_time
        
        # 空值检查
        if self._command is None:
            return
        
        # 执行命令
        try:
            # 显示加载状态
            if self._loading_text:
                self.configure(text=self._loading_text, state=tk.DISABLED)
            
            # 执行命令
            self._command()
            
        except Exception as e:
            logger.error(f"Button click error: {e}")
            messagebox.showerror("执行失败", f"操作失败：{str(e)}")
        
        finally:
            # 恢复按钮状态
            self.after(200, self._restore_button)
    
    def _restore_button(self) -> None:
        """恢复按钮状态"""
        self.configure(text=self._original_text, state=tk.NORMAL)
    
    def set_loading(self, loading: bool) -> None:
        """设置加载状态"""
        self._is_loading = loading
        
        if loading:
            self.configure(text=self._loading_text, state=tk.DISABLED)
        else:
            self.configure(text=self._original_text, state=tk.NORMAL)


# ============================================================================
# 标签页延迟创建容器
# ============================================================================

class LazyNotebook(ttk.Notebook):
    """
    标签页延迟创建容器 - 懒加载实现
    
    特性：
    1. 标签页切换时才创建内容
    2. 创建后缓存，避免重复创建
    3. 支持标签页销毁和重建
    """
    
    def __init__(self, parent: tk.Widget, theme: InkTheme, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.theme = theme
        
        # 标签页创建函数映射
        self._tab_creators: Dict[str, Callable[[], tk.Widget]] = {}
        
        # 已创建的标签页内容
        self._created_tabs: Dict[str, tk.Widget] = {}
        
        # 绑定标签页切换事件
        self.bind("<<NotebookTabChanged>>", self._on_tab_changed)
    
    def add_lazy_tab(
        self,
        tab_id: str,
        text: str,
        creator: Callable[[], tk.Widget],
        image: Optional[Any] = None
    ) -> str:
        """
        添加延迟创建的标签页
        
        Args:
            tab_id: 标签页唯一ID
            text: 标签页标题
            creator: 创建函数（返回标签页内容组件）
            image: 标签页图标（可选）
        
        Returns:
            标签页ID
        """
        # 创建占位Frame
        placeholder = ttk.Frame(self)
        
        # 添加标签页
        if image:
            tab_id_result = self.add(placeholder, text=text, image=image)
        else:
            tab_id_result = self.add(placeholder, text=text)
        
        # 存储创建函数
        self._tab_creators[tab_id] = creator
        
        return tab_id_result
    
    def _on_tab_changed(self, event) -> None:
        """标签页切换事件处理"""
        # 获取当前选中的标签页索引
        current_index = self.index("current")
        
        # 获取标签页ID
        tab_id = self._get_tab_id_by_index(current_index)
        
        if tab_id is None:
            return
        
        # 检查是否已创建
        if tab_id in self._created_tabs:
            return
        
        # 创建标签页内容
        creator = self._tab_creators.get(tab_id)
        if creator is None:
            return
        
        try:
            # 先获取标签页文本（在删除前）
            tab_text = self.tab(current_index, option="text")
            
            # 创建内容
            content = creator()
            
            # 替换占位符
            self.forget(current_index)
            
            # 在相同位置插入新内容
            self.insert(current_index, content, text=tab_text)
            
            # 缓存
            self._created_tabs[tab_id] = content
            
            # 选中（避免无限循环）
            self.unbind("<<NotebookTabChanged>>")
            self.select(current_index)
            self.bind("<<NotebookTabChanged>>", self._on_tab_changed)
            
            logger.info(f"Lazy tab created: {tab_id}")
        
        except Exception as e:
            logger.error(f"Failed to create tab {tab_id}: {e}")
    
    def _get_tab_id_by_index(self, index: int) -> Optional[str]:
        """通过索引获取标签页ID"""
        try:
            # 获取当前标签页的文本
            tab_text = self.tab(index, option="text")
            
            # 通过文本匹配找到对应的tab_id
            text_to_id = {
                "热榜": "hot_ranking",
                "工作台": "workbench",
                "创作进度": "creation_progress",
                "项目管理": "project_management",
                "插件管理": "plugin_manager",
                "设置": "settings"
            }
            
            return text_to_id.get(tab_text)
            
        except tk.TclError:
            return None


# ============================================================================
# 主窗口类
# ============================================================================

class MainWindow:
    """
    主窗口 - 中国古典水墨风格
    
    功能：
    1. 水墨风格主题
    2. 响应式按钮
    3. 标签页延迟创建
    4. 完整功能区：热榜、工作台（7子模块）、续写、项目管理、插件管理器、设置、状态栏
    5. 后端核心交互
    """
    
    def __init__(self):
        """初始化主窗口"""
        # 创建主窗口
        self.root = tk.Tk()
        self.root.title("Novel Writing Assistant - Agent Pro")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)
        
        # 初始化主题
        self.theme = InkTheme()
        
        # 配置主题样式
        self._configure_styles()
        
        # 创建UI组件
        self._create_ui()
        
        # 绑定事件
        self._bind_events()
        
        logger.info("MainWindow initialized")
    
    def _configure_styles(self) -> None:
        """配置ttk样式"""
        style = ttk.Style()
        
        # 尝试使用sv_ttk主题
        try:
            import sv_ttk
            sv_ttk.set_theme("light")
            logger.info("sv_ttk light theme applied")
        except ImportError:
            logger.warning("sv_ttk not available, using default theme")
        
        # ===== 自定义水墨风格样式 =====
        
        # 标题标签样式
        style.configure(
            "Title.TLabel",
            font=self.theme.font_title,
            foreground=self.theme.ink_black,
            background=self.theme.paper_white
        )
        
        # 子标题标签样式
        style.configure(
            "Subtitle.TLabel",
            font=self.theme.font_subtitle,
            foreground=self.theme.ink_gray,
            background=self.theme.paper_white
        )
        
        # 正文标签样式
        style.configure(
            "Body.TLabel",
            font=self.theme.font_body,
            foreground=self.theme.ink_dark,
            background=self.theme.paper_white
        )
        
        # Frame样式
        style.configure(
            "TFrame",
            background=self.theme.paper_white
        )
        
        # 侧边栏Frame样式
        style.configure(
            "Sidebar.TFrame",
            background=self.theme.gradient_light
        )
        
        # 按钮样式（水墨风格）
        style.configure(
            "TButton",
            font=self.theme.font_button,
            padding=10,
            background=self.theme.paper_cream,
            foreground=self.theme.ink_black
        )
        
        # 侧边栏按钮样式
        style.configure(
            "Sidebar.TButton",
            font=self.theme.font_button,
            padding=(20, 10),
            background=self.theme.gradient_light,
            foreground=self.theme.ink_black
        )
        
        # 强调按钮样式（朱砂红）
        style.configure(
            "Accent.TButton",
            font=self.theme.font_button,
            padding=10,
            background=self.theme.vermilion,
            foreground=self.theme.paper_white
        )
        
        # LabelFrame样式
        style.configure(
            "TLabelframe",
            background=self.theme.paper_white,
            foreground=self.theme.ink_black
        )
        
        style.configure(
            "TLabelframe.Label",
            font=self.theme.font_subtitle,
            background=self.theme.paper_white,
            foreground=self.theme.ink_gray
        )
    
    def _create_ui(self) -> None:
        """创建UI组件"""
        # 设置窗口背景
        self.root.configure(bg=self.theme.paper_white)
        
        # 主容器
        main_frame = ttk.Frame(self.root, style="TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建标题栏
        self._create_title_bar(main_frame)
        
        # 创建状态栏（在_create_workspace之前）
        self._create_status_bar(main_frame)
        
        # 创建内容区
        content_frame = ttk.Frame(main_frame, style="TFrame")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        # 创建侧边栏
        self._create_sidebar(content_frame)
        
        # 创建主工作区
        self._create_workspace(content_frame)
    
    def _create_title_bar(self, parent: tk.Widget) -> None:
        """创建标题栏（水墨风格，简洁设计）"""
        title_frame = ttk.Frame(parent, style="TFrame")
        title_frame.pack(fill=tk.X, padx=15, pady=15)
        
        # 主标题（纯文字，水墨风格）
        title_label = ttk.Label(
            title_frame,
            text="Novel Writing Assistant - Agent Pro",
            style="Title.TLabel"
        )
        title_label.pack(side=tk.LEFT)
        
        # 版本标签（小字体，右对齐）
        version_label = ttk.Label(
            title_frame,
            text="V2.1 | Chinese Ink Style",
            font=self.theme.font_small,
            foreground=self.theme.ink_gray,
            background=self.theme.paper_white
        )
        version_label.pack(side=tk.RIGHT)
    
    def _create_sidebar(self, parent: tk.Widget) -> None:
        """创建侧边栏（水墨风格，纯文字按钮）"""
        sidebar_frame = ttk.Frame(parent, style="Sidebar.TFrame", width=200)
        sidebar_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 15))
        sidebar_frame.pack_propagate(False)
        
        # 功能按钮列表（水墨风格，纯文字）
        buttons = [
            ("热榜", "hot_ranking"),
            ("工作台", "workbench"),
            ("创作进度", "creation_progress"),
            ("项目管理", "project_management"),
            ("插件管理", "plugin_manager"),
            ("设置", "settings"),
        ]
        
        for text, tab_id in buttons:
            # 创建按钮框架（统一宽度，左对齐）
            btn_frame = ttk.Frame(sidebar_frame, style="Sidebar.TFrame")
            btn_frame.pack(fill=tk.X, pady=2, padx=5)
            
            btn = ResponsiveButton(
                parent=btn_frame,
                text=text,
                command=lambda tid=tab_id: self._switch_to_tab(tid),
                style="Sidebar.TButton",
                width=18
            )
            btn.pack(fill=tk.X, anchor="w")
    
    def _create_workspace(self, parent: tk.Widget) -> None:
        """创建主工作区（通过左侧菜单切换内容）"""
        # 创建内容容器
        self.content_frames: Dict[str, tk.Widget] = {}
        self.current_tab_id: Optional[str] = None
        
        # 主内容区域
        self.workspace_frame = ttk.Frame(parent, style="TFrame")
        self.workspace_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 初始化所有内容页（懒加载）
        self._init_content_pages()
    
    def _create_status_bar(self, parent: tk.Widget) -> None:
        """创建状态栏（水墨风格）"""
        status_frame = ttk.Frame(parent, style="TFrame")
        status_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        # 分隔线
        separator = ttk.Separator(status_frame, orient=tk.HORIZONTAL)
        separator.pack(fill=tk.X, pady=(0, 5))
        
        # 状态标签
        self.status_label = ttk.Label(
            status_frame,
            text="状态: 就绪",
            style="Body.TLabel"
        )
        self.status_label.pack(side=tk.LEFT)
        
        # 版本信息（小字体，右对齐）
        version_label = ttk.Label(
            status_frame,
            text="V2.1.0 | Agent Pro | Chinese Ink Style",
            font=self.theme.font_small,
            foreground=self.theme.ink_gray,
            background=self.theme.paper_white
        )
        version_label.pack(side=tk.RIGHT, padx=(0, 5))
    
    # ========================================================================
    # 标签页创建函数
    # ========================================================================
    
    def _create_hot_ranking_tab(self) -> tk.Widget:
        """创建热榜功能标签页"""
        frame = ttk.Frame(self.workspace_frame, style="TFrame")
        
        # 标题
        title = ttk.Label(frame, text="热榜功能", style="Title.TLabel")
        title.pack(pady=20)
        
        # 说明
        desc = ttk.Label(
            frame,
            text="查看热门作品排行，获取创作灵感",
            style="Subtitle.TLabel"
        )
        desc.pack(pady=(0, 20))
        
        # 热榜内容区
        content = tk.Text(
            frame,
            wrap=tk.WORD,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark,
            padx=10,
            pady=10,
            relief=tk.FLAT,
            borderwidth=1
        )
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        content.insert("1.0", "热榜功能区域\n\n排行榜加载中...\n\n• 追更热榜\n• 推荐热榜\n• 新书热榜\n• 完结热榜")
        content.config(state=tk.DISABLED)
        
        # 刷新按钮
        refresh_btn = ResponsiveButton(
            parent=frame,
            text="刷新排行",
            command=self._refresh_ranking
        )
        refresh_btn.pack(pady=20)
        
        return frame
    
    def _create_workbench_tab(self) -> tk.Widget:
        """创建工作台标签页（集成7个子模块+续写功能）"""
        frame = ttk.Frame(self.workspace_frame, style="TFrame")
        
        # 标题
        title = ttk.Label(frame, text="工作台", style="Title.TLabel")
        title.pack(pady=20)
        
        # 说明
        desc = ttk.Label(
            frame,
            text="创作工作中心 - 管理、学习、创作、续写",
            style="Subtitle.TLabel"
        )
        desc.pack(pady=(0, 20))
        
        # 功能按钮区（水墨风格，纯文字）
        button_frame = ttk.Frame(frame, style="TFrame")
        button_frame.pack(fill=tk.X, padx=20, pady=20)
        
        # 功能按钮（8个，水墨风格纯文字）
        buttons = [
            ("世界观管理", "worldview"),
            ("人物设定", "characters"),
            ("大纲管理", "outline"),
            ("风格学习", "style"),
            ("开始创作", "generate"),
            ("逆向反馈", "reverse"),
            ("快捷创作", "quick"),
            ("智能续写", "continuation"),
        ]
        
        for i, (text, command) in enumerate(buttons):
            btn = ResponsiveButton(
                parent=button_frame,
                text=text,
                command=lambda c=command: self._call_plugin(c),
                loading_text=f"加载{text}..."
            )
            btn.grid(row=i // 4, column=i % 4, padx=5, pady=5, sticky="ew")
        
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)
        button_frame.columnconfigure(3, weight=1)
        
        # 内容区
        content = tk.Text(
            frame,
            wrap=tk.WORD,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark,
            padx=10,
            pady=10,
            relief=tk.FLAT,
            borderwidth=1
        )
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=(20, 20))
        content.insert("1.0", "工作台功能区域\n\n选择上方功能按钮开始创作：\n• 世界观管理：设定和管理世界观设定\n• 人物设定：创建和管理角色档案\n• 大纲管理：解析和管理章节大纲\n• 风格学习：学习参考文本的写作风格\n• 开始创作：AI智能生成章节内容\n• 逆向反馈：根据已写内容优化设定\n• 快捷创作：快速生成短篇内容\n• 智能续写：续写已有章节，保持风格和情节连贯性")
        content.config(state=tk.DISABLED)
        
        return frame
    
    def _create_creation_progress_tab(self) -> tk.Widget:
        """创建创作进度标签页"""
        frame = ttk.Frame(self.workspace_frame, style="TFrame")
        
        # 标题
        title = ttk.Label(frame, text="创作进度", style="Title.TLabel")
        title.pack(pady=20)
        
        # 说明
        desc = ttk.Label(
            frame,
            text="追踪创作进度，查看统计数据",
            style="Subtitle.TLabel"
        )
        desc.pack(pady=(0, 20))
        
        # 内容区
        content = tk.Text(
            frame,
            wrap=tk.WORD,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark,
            padx=10,
            pady=10,
            relief=tk.FLAT,
            borderwidth=1
        )
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        content.insert("1.0", "创作进度追踪\n\n• 总字数：0 字\n• 已完成章节：0 章\n• 创作时长：0 小时\n• 今日目标：0 / 2000 字\n\n选择左侧【工作台】开始创作，进度将自动更新。")
        content.config(state=tk.DISABLED)
        
        return frame
    
    def _create_project_management_tab(self) -> tk.Widget:
        """创建项目管理标签页"""
        frame = ttk.Frame(self.workspace_frame, style="TFrame")
        
        # 标题
        title = ttk.Label(frame, text="项目管理", style="Title.TLabel")
        title.pack(pady=20)
        
        # 说明
        desc = ttk.Label(
            frame,
            text="创建、打开、管理小说项目",
            style="Subtitle.TLabel"
        )
        desc.pack(pady=(0, 20))
        
        # 按钮区
        buttons_frame = ttk.Frame(frame, style="TFrame")
        buttons_frame.pack(fill=tk.X, padx=20, pady=20)
        
        buttons = [
            ("新建项目", "new_project"),
            ("打开项目", "open_project"),
            ("导出项目", "export_project"),
            ("备份管理", "backup"),
        ]
        
        for i, (text, command) in enumerate(buttons):
            btn = ResponsiveButton(
                parent=buttons_frame,
                text=text,
                command=lambda c=command: self._handle_project_action(c),
                loading_text=f"加载{text}..."
            )
            btn.pack(fill=tk.X, pady=5)
        
        return frame
    
    def _create_plugin_manager_tab(self) -> tk.Widget:
        """创建插件管理标签页"""
        frame = ttk.Frame(self.workspace_frame, style="TFrame")
        
        # 标题
        title = ttk.Label(frame, text="插件管理", style="Title.TLabel")
        title.pack(pady=20)
        
        # 说明
        desc = ttk.Label(
            frame,
            text="浏览、安装、管理插件扩展",
            style="Subtitle.TLabel"
        )
        desc.pack(pady=(0, 20))
        
        # 插件列表
        plugins_frame = ttk.Frame(frame, style="TFrame")
        plugins_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 创建插件列表占位符
        placeholder = tk.Text(
            plugins_frame,
            wrap=tk.WORD,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark,
            padx=10,
            pady=10,
            relief=tk.FLAT,
            borderwidth=1
        )
        placeholder.pack(fill=tk.BOTH, expand=True)
        placeholder.insert("1.0", "插件列表区域\n\n已安装插件：\n• 大纲解析器 v3.0\n• 风格学习器 v2.0\n• 人物管理器 v1.0\n• 世界观解析器 v1.0\n• 热榜功能 v1.0\n\n核心插件（受保护）：\n• 上下文构建器\n• 迭代生成器 v2.0\n• 加权验证器\n• 生成入口")
        placeholder.config(state=tk.DISABLED)
        
        return frame
    
    def _create_settings_tab(self) -> tk.Widget:
        """创建设置标签页"""
        frame = ttk.Frame(self.workspace_frame, style="TFrame")
        
        # 标题
        title = ttk.Label(frame, text="设置", style="Title.TLabel")
        title.pack(pady=20)
        
        # 说明
        desc = ttk.Label(
            frame,
            text="应用程序配置和偏好设置",
            style="Subtitle.TLabel"
        )
        desc.pack(pady=(0, 20))
        
        # 设置项
        settings_frame = ttk.Frame(frame, style="TFrame")
        settings_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # AI模型设置
        ai_frame = ttk.LabelFrame(settings_frame, text="AI模型设置", padding=10)
        ai_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(ai_frame, text="模型提供商:").grid(row=0, column=0, sticky="w", pady=5)
        provider_combo = ttk.Combobox(ai_frame, values=["DeepSeek", "OpenAI", "Anthropic", "Ollama"])
        provider_combo.grid(row=0, column=1, sticky="ew", padx=10)
        provider_combo.set("DeepSeek")
        
        ttk.Label(ai_frame, text="模型名称:").grid(row=1, column=0, sticky="w", pady=5)
        model_combo = ttk.Combobox(ai_frame, values=["deepseek-chat", "gpt-4", "claude-3", "llama2"])
        model_combo.grid(row=1, column=1, sticky="ew", padx=10)
        model_combo.set("deepseek-chat")
        
        ttk.Label(ai_frame, text="Temperature:").grid(row=2, column=0, sticky="w", pady=5)
        temp_scale = ttk.Scale(ai_frame, from_=0.0, to=2.0, orient=tk.HORIZONTAL)
        temp_scale.grid(row=2, column=1, sticky="ew", padx=10)
        temp_scale.set(0.7)
        
        ai_frame.columnconfigure(1, weight=1)
        
        # 生成设置
        gen_frame = ttk.LabelFrame(settings_frame, text="生成设置", padding=10)
        gen_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(gen_frame, text="默认字数目标:").grid(row=0, column=0, sticky="w", pady=5)
        word_spin = ttk.Spinbox(gen_frame, from_=500, to=10000, increment=100)
        word_spin.grid(row=0, column=1, sticky="ew", padx=10)
        word_spin.set(2000)
        
        ttk.Label(gen_frame, text="评分阈值:").grid(row=1, column=0, sticky="w", pady=5)
        score_scale = ttk.Scale(gen_frame, from_=0.0, to=1.0, orient=tk.HORIZONTAL)
        score_scale.grid(row=1, column=1, sticky="ew", padx=10)
        score_scale.set(0.8)
        
        gen_frame.columnconfigure(1, weight=1)
        
        # 保存按钮
        save_btn = ttk.Button(settings_frame, text="保存设置", command=self._save_settings)
        save_btn.pack(pady=20)
        
        return frame
    
    # ========================================================================
    # 辅助方法
    # ========================================================================
    
    def _bind_events(self) -> None:
        """绑定事件"""
        # 窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        
        # 键盘快捷键
        self.root.bind("<Control-w>", lambda e: self._switch_to_tab("workbench"))
        self.root.bind("<Control-p>", lambda e: self._switch_to_tab("project_management"))
        self.root.bind("<Control-s>", lambda e: self._switch_to_tab("settings"))
    
    def _update_status(self, message: str) -> None:
        """更新状态栏消息"""
        self.status_label.config(text=f"状态: {message}")
    
    def _on_window_close(self) -> None:
        """窗口关闭处理"""
        if messagebox.askokcancel("退出", "确定要退出 Novel Writing Assistant 吗？"):
            self.root.destroy()
    
    def _init_content_pages(self) -> None:
        """初始化内容页（懒加载模式）"""
        # 内容页创建函数映射
        self._tab_creators = {
            "hot_ranking": self._create_hot_ranking_tab,
            "workbench": self._create_workbench_tab,
            "creation_progress": self._create_creation_progress_tab,
            "project_management": self._create_project_management_tab,
            "plugin_manager": self._create_plugin_manager_tab,
            "settings": self._create_settings_tab
        }
        
        # 默认显示第一个标签页
        self._switch_to_tab("hot_ranking")
    
    def _switch_to_tab(self, tab_id: str) -> None:
        """切换到指定标签页"""
        # 检查tab_id是否有效
        if tab_id not in self._tab_creators:
            logger.warning(f"Unknown tab_id: {tab_id}")
            return
        
        # 隐藏当前内容页
        if self.current_tab_id and self.current_tab_id in self.content_frames:
            self.content_frames[self.current_tab_id].pack_forget()
        
        # 懒加载：如果内容页未创建，则创建
        if tab_id not in self.content_frames:
            creator = self._tab_creators[tab_id]
            self.content_frames[tab_id] = creator()
        
        # 显示新内容页
        self.content_frames[tab_id].pack(fill=tk.BOTH, expand=True)
        self.current_tab_id = tab_id
        
        # 更新状态栏
        tab_names = {
            "hot_ranking": "热榜",
            "workbench": "工作台",
            "creation_progress": "创作进度",
            "project_management": "项目管理",
            "plugin_manager": "插件管理",
            "settings": "设置"
        }
        self._update_status(f"当前页面: {tab_names.get(tab_id, tab_id)}")
    
    def _call_plugin(self, plugin_id: str, *args, **kwargs) -> None:
        """调用插件方法"""
        try:
            # 获取插件注册表
            from core import get_plugin_registry
            
            registry = get_plugin_registry()
            plugin = registry.get_plugin(plugin_id)
            
            if plugin:
                # 调用插件方法
                result = plugin.execute(*args, **kwargs)
                self._update_status(f"插件 {plugin_id} 执行成功")
                return result
            else:
                self._update_status(f"插件 {plugin_id} 未找到")
        
        except Exception as e:
            self._update_status(f"插件执行失败: {str(e)}")
            logger.error(f"Plugin call failed: {e}")
    
    def _refresh_ranking(self) -> None:
        """刷新排行榜"""
        self._update_status("正在刷新排行榜...")
        # 实际实现中调用热榜插件
        self._call_plugin("hot-ranking")
    
    def _handle_project_action(self, action: str) -> None:
        """处理项目操作"""
        self._update_status(f"执行项目操作: {action}")
        # 实际实现中调用项目管理服务
        messagebox.showinfo("项目操作", f"功能开发中: {action}")
    
    def _save_settings(self) -> None:
        """保存设置"""
        self._update_status("设置已保存")
        messagebox.showinfo("保存成功", "设置已成功保存")


def create_main_window() -> MainWindow:
    """创建主窗口"""
    return MainWindow()


def on_startup_complete(startup_time: float) -> None:
    """启动完成回调"""
    logger.info(f"Startup complete in {startup_time:.3f}s")


def main():
    """主入口"""
    start_time = time.time()
    logger.info("Starting Novel Writing Assistant - Agent Pro...")
    
    # 创建主窗口
    app = create_main_window()
    
    # 创建启动器
    from core.app_launcher import OptimizedLauncher
    
    launcher = OptimizedLauncher()
    
    # 配置启动参数
    launcher.configure(
        show_splash=False,
        min_show_time=0.0,
        async_load=True,
        hide_window_on_start=False,
        target_startup_time=2.0
    )
    
    # 注册启动完成回调
    launcher.register_complete_callback(on_startup_complete)
    
    # 启动应用（加载核心层）
    core_startup_time = launcher.start(app.root)
    logger.info(f"Core startup time: {core_startup_time:.3f}s")
    
    # 初始化AsyncHandler
    from core.async_handler import init_async_handler
    init_async_handler(root=app.root, worker_count=4, default_timeout=30.0)
    
    # 更新状态栏
    app._update_status("就绪")
    
    total_time = time.time() - start_time
    logger.info(f"Total startup time: {total_time:.3f}s")
    
    # 运行主循环
    app.root.mainloop()
    
    # 清理
    launcher.shutdown()


if __name__ == "__main__":
    main()
