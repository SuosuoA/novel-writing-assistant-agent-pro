#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Novel Writing Assistant - Agent Pro
主GUI入口 - 现代科技玻璃风（Glass Morphism）

V2.1版本
创建日期：2026-03-22
更新日期：2026-03-22

特性：
- 无边框透明窗口（Windows Acrylic/Mica效果）
- 玻璃态UI设计（毛玻璃背景+发光边框）
- 响应式按钮（防抖+异步执行+加载状态）
- 侧边栏导航（无横向标签页）
- 线程安全的后端交互
"""

import os
import sys
import json
import yaml
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import logging
import queue
import ctypes
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from ctypes import c_int, byref, sizeof, windll

# 尝试导入sv_ttk
try:
    import sv_ttk
    SV_TTK_AVAILABLE = True
except ImportError:
    SV_TTK_AVAILABLE = False
    logging.warning("sv_ttk not available")

# 尝试导入核心模块
try:
    from core import (
        EventBus,
        PluginRegistry,
        ServiceLocator,
        ConfigManager,
        get_event_bus,
        get_plugin_registry,
        get_service_locator,
        get_config_manager,
        AsyncHandler,
        TaskPriority,
        init_async_handler,
        CoreServiceManager,
        initialize_core_services,
        dispose_core_services,
        get_logging_service,
    )
    CORE_AVAILABLE = True
except ImportError as e:
    CORE_AVAILABLE = False
    logging.warning(f"Core modules not available: {e}")

# 配置日志
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
if log_level not in valid_levels:
    # 使用print因为logger还未初始化
    print(f"[WARNING] Invalid LOG_LEVEL '{log_level}', using INFO")
    log_level = 'INFO'

logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============== Windows Acrylic效果实现 ==============

class DWM_BLURBEHIND(ctypes.Structure):
    """Windows DWM模糊效果结构"""
    _fields_ = [
        ("dwFlags", ctypes.c_ulong),
        ("fEnable", ctypes.c_bool),
        ("hRgnBlur", ctypes.c_void_p),
        ("fTransitionOnMaximized", ctypes.c_bool),
    ]


class AccentPolicy(ctypes.Structure):
    """Windows 10/11 Accent效果结构"""
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class WindowCompositionAttrData(ctypes.Structure):
    """窗口组合属性数据"""
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_int),
    ]


class GlassWindowManager:
    """
    玻璃态窗口管理器
    
    实现Windows 10/11的Acrylic/Mica效果
    """
    
    # Windows常量
    DWM_BB_BLURREGION = 0x2
    DWM_BB_ENABLE = 0x1
    WM_NCCALCSIZE = 0x83
    WM_NCHITTEST = 0x84
    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    WS_CAPTION = 0xC00000
    WS_THICKFRAME = 0x40000
    WS_MINIMIZEBOX = 0x20000
    WS_MAXIMIZEBOX = 0x10000
    WS_SYSMENU = 0x80000
    WS_BORDER = 0x800000
    WS_DLGFRAME = 0x400000
    WS_EX_LAYERED = 0x80000
    WS_EX_TRANSPARENT = 0x20
    
    # Accent状态
    ACCENT_DISABLED = 0
    ACCENT_ENABLE_BLURBEHIND = 3
    ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
    
    # 窗口组合属性
    WCA_ACCENT_POLICY = 19
    
    def __init__(self, root: tk.Tk):
        """
        初始化玻璃窗口管理器
        
        Args:
            root: Tkinter根窗口
        """
        self.root = root
        self.hwnd = None
        self._is_acrylic = False
        
        # 加载Windows DLL
        try:
            self.dwmapi = ctypes.windll.dwmapi
            self.user32 = ctypes.windll.user32
            self._dll_available = True
        except Exception:
            self._dll_available = False
            logger.warning("Windows DLL not available")
    
    def enable_acrylic(self, color: int = 0x99000000) -> bool:
        """
        启用Acrylic效果
        
        Args:
            color: ARGB颜色值（格式：0xAABBGGRR）
        
        Returns:
            是否成功启用
        """
        if not self._dll_available:
            logger.info("Windows DLL not available, using standard window mode")
            return False
        
        try:
            # 获取窗口句柄
            self.hwnd = self.user32.GetActiveWindow()
            if not self.hwnd:
                logger.warning("Failed to get window handle, using standard window mode")
                return False
            
            # 设置Accent策略
            accent = AccentPolicy()
            accent.AccentState = self.ACCENT_ENABLE_ACRYLICBLURBEHIND
            accent.AccentFlags = 2
            accent.GradientColor = color
            accent.AnimationId = 0
            
            data = WindowCompositionAttrData()
            data.Attribute = self.WCA_ACCENT_POLICY
            data.Data = ctypes.cast(ctypes.byref(accent), ctypes.c_void_p)
            data.SizeOfData = ctypes.sizeof(accent)
            
            # 应用效果
            result = self.user32.SetWindowCompositionAttribute(self.hwnd, ctypes.byref(data))
            
            if result:
                self._is_acrylic = True
                logger.info("Acrylic effect enabled")
            else:
                # 降级：尝试使用blur behind作为备选方案
                logger.warning("Acrylic not supported, trying blur behind fallback")
                if self.enable_blur_behind():
                    logger.info("Blur behind fallback enabled successfully")
                else:
                    logger.warning("Blur behind also failed, using standard window mode")
            
            return result != 0
        
        except Exception as e:
            logger.error(f"Error enabling Acrylic: {e}, using standard window mode")
            # 降级：设置基本透明度作为最终备选
            try:
                self.root.attributes('-alpha', 0.95)
                logger.info("Applied basic transparency as fallback")
            except Exception:
                pass
            return False
    
    def make_frameless(self, keep_resize_border: bool = True) -> None:
        """
        设置完全无边框窗口（移除系统边框和标题栏按钮）
        
        Args:
            keep_resize_border: 是否保留调整大小的边框
                - True: 保留透明调整边框（可拖拽调整大小，但有细微边框残留）
                - False: 完全无边框（无边框残留，但需自己实现调整大小）
        """
        if not self._dll_available:
            return
        
        try:
            # 确保窗口句柄存在（必须在 overrideredirect 之前获取）
            if not self.hwnd:
                self.hwnd = self.user32.GetActiveWindow()
            
            if not self.hwnd:
                logger.warning("Failed to get window handle for frameless mode")
                return
            
            # 先通过Windows API移除边框样式
            style = self.user32.GetWindowLongW(self.hwnd, self.GWL_STYLE)
            
            if keep_resize_border:
                # 模式1：保留调整边框（推荐）
                # 移除标题栏、系统菜单、边框线条，保留调整功能
                style &= ~(self.WS_CAPTION | self.WS_SYSMENU | self.WS_BORDER | self.WS_DLGFRAME)
                style |= self.WS_THICKFRAME | self.WS_MINIMIZEBOX | self.WS_MAXIMIZEBOX
            else:
                # 模式2：完全无边框
                # 移除所有边框和调整功能，纯净无边框
                style &= ~(self.WS_CAPTION | self.WS_SYSMENU | self.WS_THICKFRAME | self.WS_BORDER | self.WS_DLGFRAME)
                style |= self.WS_MINIMIZEBOX | self.WS_MAXIMIZEBOX
            
            self.user32.SetWindowLongW(self.hwnd, self.GWL_STYLE, style)
            
            # 强制重绘窗口
            self.user32.SetWindowPos(self.hwnd, None, 0, 0, 0, 0, 
                                     0x27)  # SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
            
            # 关键：使用 overrideredirect 完全移除系统标题栏按钮
            # 必须在Windows API设置之后调用，否则无法获取窗口句柄
            self.root.overrideredirect(True)
            
            logger.info(f"Frameless window enabled (keep_resize_border={keep_resize_border})")
        
        except Exception as e:
            logger.error(f"Error making frameless: {e}")
    
    def enable_blur_behind(self) -> bool:
        """
        启用DWM模糊效果（Windows 7+）
        
        Returns:
            是否成功启用
        """
        if not self._dll_available:
            return False
        
        try:
            self.hwnd = self.user32.GetActiveWindow()
            if not self.hwnd:
                return False
            
            bb = DWM_BLURBEHIND()
            bb.dwFlags = self.DWM_BB_ENABLE
            bb.fEnable = True
            bb.hRgnBlur = None
            bb.fTransitionOnMaximized = False
            
            self.dwmapi.DwmEnableBlurBehindWindow(self.hwnd, ctypes.byref(bb))
            
            logger.info("Blur behind enabled")
            return True
        
        except Exception as e:
            logger.error(f"Error enabling blur behind: {e}")
            return False
    
    def set_window_opacity(self, alpha: float) -> None:
        """
        设置窗口透明度
        
        Args:
            alpha: 透明度（0.0-1.0）
        """
        try:
            # Tkinter原生透明度设置
            self.root.attributes('-alpha', alpha)
        except Exception as e:
            logger.error(f"Error setting opacity: {e}")


# ============== 玻璃态主题配置 ==============

class GlassTheme:
    """
    现代科技玻璃态主题配置
    
    设计理念：毛玻璃效果 + 发光边框 + 悬浮卡片
    """
    
    # 主色调（科技蓝）
    PRIMARY = "#0078D4"          # Windows蓝
    PRIMARY_LIGHT = "#60CDFF"    # 浅蓝
    PRIMARY_DARK = "#003D6B"     # 深蓝
    
    # 强调色
    ACCENT = "#00BCF2"           # 青蓝
    ACCENT_PINK = "#FF6B9D"      # 粉红
    ACCENT_PURPLE = "#8B5CF6"    # 紫色
    ACCENT_GREEN = "#10B981"     # 绿色
    ACCENT_ORANGE = "#F59E0B"    # 橙色
    ACCENT_RED = "#EF4444"       # 红色
    
    # 背景色（玻璃态）
    GLASS_BG = "#1E1E1E"         # 玻璃背景色
    GLASS_SURFACE = "#2D2D2D"    # 玻璃表面色
    GLASS_BORDER = "#404040"     # 玻璃边框色
    GLASS_HOVER = "#383838"      # 悬停态
    
    # 文字色
    TEXT_PRIMARY = "#FFFFFF"     # 主文字
    TEXT_SECONDARY = "#B0B0B0"   # 次要文字
    TEXT_DISABLED = "#666666"    # 禁用文字
    TEXT_LINK = "#60CDFF"        # 链接文字
    
    # 语义色
    SUCCESS = "#10B981"
    WARNING = "#F59E0B"
    ERROR = "#EF4444"
    INFO = "#3B82F6"
    
    # 玻璃效果参数
    BLUR_RADIUS = 20
    GLASS_OPACITY = 0.85
    BORDER_RADIUS = 8
    
    # 字体配置
    FONT_FAMILY = "Microsoft YaHei UI"
    FONT_FAMILY_CODE = "Consolas"
    FONT_SIZE_TITLE = 18
    FONT_SIZE_SUBTITLE = 14
    FONT_SIZE_NORMAL = 10
    FONT_SIZE_SMALL = 9
    FONT_SIZE_TINY = 8
    
    @classmethod
    def apply_to_style(cls, style: ttk.Style) -> None:
        """应用玻璃态主题到ttk Style"""
        
        # 全局样式
        style.configure(".",
            background=cls.GLASS_BG,
            foreground=cls.TEXT_PRIMARY,
            fieldbackground=cls.GLASS_SURFACE,
            bordercolor=cls.GLASS_BORDER,
            lightcolor=cls.GLASS_HOVER,
            darkcolor=cls.GLASS_BG
        )
        
        # 标签
        style.configure("TLabel",
            background=cls.GLASS_BG,
            foreground=cls.TEXT_PRIMARY,
            font=(cls.FONT_FAMILY, cls.FONT_SIZE_NORMAL)
        )
        
        # 标题标签
        style.configure("Title.TLabel",
            font=(cls.FONT_FAMILY, cls.FONT_SIZE_TITLE, "bold"),
            foreground=cls.TEXT_PRIMARY
        )
        
        # 副标题标签
        style.configure("Subtitle.TLabel",
            font=(cls.FONT_FAMILY, cls.FONT_SIZE_SUBTITLE, "bold"),
            foreground=cls.TEXT_SECONDARY
        )
        
        # 按钮 - 玻璃态效果
        style.configure("TButton",
            font=(cls.FONT_FAMILY, cls.FONT_SIZE_NORMAL),
            padding=(16, 8),
            background=cls.GLASS_SURFACE,
            foreground=cls.TEXT_PRIMARY,
            borderwidth=1,
            relief="flat"
        )
        
        style.map("TButton",
            background=[("active", cls.GLASS_HOVER), ("pressed", cls.PRIMARY)],
            foreground=[("active", cls.TEXT_PRIMARY), ("pressed", cls.TEXT_PRIMARY)]
        )
        
        # 强调按钮
        style.configure("Accent.TButton",
            font=(cls.FONT_FAMILY, cls.FONT_SIZE_NORMAL),
            padding=(16, 8),
            background=cls.PRIMARY,
            foreground=cls.TEXT_PRIMARY,
            borderwidth=0
        )
        
        style.map("Accent.TButton",
            background=[("active", cls.PRIMARY_LIGHT), ("pressed", cls.PRIMARY_DARK)]
        )
        
        # 框架
        style.configure("TFrame",
            background=cls.GLASS_BG
        )
        
        # 玻璃卡片框架
        style.configure("Glass.TFrame",
            background=cls.GLASS_SURFACE,
            borderwidth=1,
            relief="solid"
        )
        
        # LabelFrame
        style.configure("TLabelframe",
            background=cls.GLASS_BG,
            foreground=cls.TEXT_PRIMARY,
            borderwidth=1,
            relief="solid"
        )
        
        style.configure("TLabelframe.Label",
            background=cls.GLASS_BG,
            foreground=cls.PRIMARY_LIGHT,
            font=(cls.FONT_FAMILY, cls.FONT_SIZE_NORMAL, "bold")
        )
        
        # 输入框
        style.configure("TEntry",
            fieldbackground=cls.GLASS_SURFACE,
            foreground=cls.TEXT_PRIMARY,
            insertcolor=cls.TEXT_PRIMARY,
            borderwidth=1,
            padding=5
        )
        
        # 下拉框
        style.configure("TCombobox",
            fieldbackground=cls.GLASS_SURFACE,
            foreground=cls.TEXT_PRIMARY,
            arrowcolor=cls.TEXT_PRIMARY,
            borderwidth=1,
            padding=5
        )
        
        # 进度条
        style.configure("TProgressbar",
            background=cls.PRIMARY,
            troughcolor=cls.GLASS_SURFACE,
            borderwidth=0
        )
        
        # 滚动条
        style.configure("TScrollbar",
            background=cls.GLASS_SURFACE,
            troughcolor=cls.GLASS_BG,
            arrowcolor=cls.TEXT_SECONDARY,
            borderwidth=0
        )
        
        # Treeview
        style.configure("Treeview",
            background=cls.GLASS_SURFACE,
            foreground=cls.TEXT_PRIMARY,
            fieldbackground=cls.GLASS_SURFACE,
            borderwidth=0
        )
        
        style.configure("Treeview.Heading",
            font=(cls.FONT_FAMILY, cls.FONT_SIZE_NORMAL, "bold"),
            background=cls.GLASS_BG,
            foreground=cls.TEXT_SECONDARY
        )
        
        style.map("Treeview",
            background=[("selected", cls.PRIMARY)],
            foreground=[("selected", cls.TEXT_PRIMARY)]
        )
        
        # 复选框
        style.configure("TCheckbutton",
            background=cls.GLASS_BG,
            foreground=cls.TEXT_PRIMARY,
            font=(cls.FONT_FAMILY, cls.FONT_SIZE_NORMAL)
        )
        
        # 单选按钮
        style.configure("TRadiobutton",
            background=cls.GLASS_BG,
            foreground=cls.TEXT_PRIMARY,
            font=(cls.FONT_FAMILY, cls.FONT_SIZE_NORMAL)
        )
        
        # 分隔线
        style.configure("TSeparator",
            background=cls.GLASS_BORDER
        )
        
        # Scale滑块
        style.configure("TScale",
            background=cls.GLASS_BG,
            troughcolor=cls.GLASS_SURFACE,
            borderwidth=0
        )


# ============== 响应式按钮 ==============

class ResponsiveButton(ttk.Button):
    """
    响应式按钮组件
    
    特性：
    - 500ms防抖保护
    - 异步执行耗时操作
    - 加载状态自动管理
    """
    
    DEBOUNCE_MS = 500
    LOADING_SUFFIX = "..."
    
    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable,
        async_handler: Optional[Any] = None,
        debounce_ms: int = DEBOUNCE_MS,
        auto_disable: bool = True,
        style: str = "TButton",
        **kwargs
    ):
        super().__init__(parent, text=text, style=style, **kwargs)
        
        self._original_text = text
        self._original_command = command
        self._async_handler = async_handler
        self._debounce_ms = debounce_ms
        self._auto_disable = auto_disable
        
        self._is_loading = False
        self._last_click_time = 0
        
        super().configure(command=self._on_clicked)
    
    def _on_clicked(self) -> None:
        if self._is_loading:
            return
        
        current_time = time.time() * 1000
        if current_time - self._last_click_time < self._debounce_ms:
            return
        
        self._last_click_time = current_time
        
        if self._async_handler:
            self._execute_async()
        else:
            self._execute_sync()
    
    def _execute_sync(self) -> None:
        """P1-8修复：按异常类型分类处理"""
        try:
            self._set_loading(True)
            self._original_command()
        except ValueError as e:
            logger.warning(f"输入验证失败: {e}")
            messagebox.showwarning("输入错误", f"请检查输入：{e}")
        except PermissionError as e:
            logger.error(f"权限不足: {e}")
            messagebox.showerror("权限错误", "您没有执行此操作的权限")
        except FileNotFoundError as e:
            logger.error(f"文件不存在: {e}")
            messagebox.showerror("文件错误", f"找不到文件：{e}")
        except Exception as e:
            logger.error(f"执行失败: {e}", exc_info=True)
            messagebox.showerror(
                "执行失败",
                f"操作失败：{type(e).__name__}\n详情：{str(e)[:200]}"
            )
        finally:
            self._set_loading(False)

    def _execute_async(self) -> None:
        self._set_loading(True)

        def task():
            return self._original_command()

        def on_success(result):
            self._set_loading(False)

        def on_error(error):
            self._set_loading(False)
            # P1-8修复：按异常类型分类处理
            error_str = str(error)
            if "permission" in error_str.lower():
                messagebox.showerror("权限错误", "您没有执行此操作的权限")
            elif "not found" in error_str.lower() or "找不到" in error_str:
                messagebox.showerror("文件错误", f"找不到资源：{error}")
            else:
                messagebox.showerror(
                    "执行失败",
                    f"操作失败\n详情：{error_str[:200]}"
                )

        self._async_handler.submit(
            func=task,
            callback=on_success,
            error_callback=on_error,
            priority=TaskPriority.HIGH
        )
    
    def _set_loading(self, loading: bool) -> None:
        self._is_loading = loading
        
        if self._auto_disable:
            self.configure(state="disabled" if loading else "normal")
        
        if loading:
            self.configure(text=self._original_text + self.LOADING_SUFFIX)
        else:
            self.configure(text=self._original_text)


# ============== 自定义标题栏 ==============

class ResizeGrip:
    """
    窗口调整大小的边框感知区域
    
    用于完全无边框窗口的调整大小功能
    """
    
    RESIZE_BORDER = 8  # 边框感知区域宽度
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self._resize_edge = None
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_start_width = 0
        self._drag_start_height = 0
        
        # 绑定事件
        self.root.bind("<Motion>", self._on_motion)
        self.root.bind("<ButtonPress-1>", self._on_resize_start)
        self.root.bind("<ButtonRelease-1>", self._on_resize_end)
        self.root.bind("<B1-Motion>", self._on_resize_motion)
    
    def _get_edge(self, x: int, y: int) -> str:
        """判断鼠标在哪个边缘"""
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        
        left = x < self.RESIZE_BORDER
        right = x > width - self.RESIZE_BORDER
        top = y < self.RESIZE_BORDER
        bottom = y > height - self.RESIZE_BORDER
        
        # 角落优先
        if top and left:
            return "top-left"
        elif top and right:
            return "top-right"
        elif bottom and left:
            return "bottom-left"
        elif bottom and right:
            return "bottom-right"
        elif left:
            return "left"
        elif right:
            return "right"
        elif top:
            return "top"
        elif bottom:
            return "bottom"
        return ""
    
    def _get_cursor(self, edge: str) -> str:
        """获取对应的鼠标光标"""
        cursors = {
            "top": "top_side",
            "bottom": "bottom_side",
            "left": "left_side",
            "right": "right_side",
            "top-left": "top_left_corner",
            "top-right": "top_right_corner",
            "bottom-left": "bottom_left_corner",
            "bottom-right": "bottom_right_corner"
        }
        return cursors.get(edge, "")
    
    def _on_motion(self, event: tk.Event) -> None:
        """鼠标移动时更新光标"""
        edge = self._get_edge(event.x, event.y)
        cursor = self._get_cursor(edge)
        self.root.configure(cursor=cursor if cursor else "arrow")
    
    def _on_resize_start(self, event: tk.Event) -> None:
        """开始调整大小"""
        self._resize_edge = self._get_edge(event.x, event.y)
        if self._resize_edge:
            self._drag_start_x = self.root.winfo_pointerx()
            self._drag_start_y = self.root.winfo_pointery()
            self._drag_start_width = self.root.winfo_width()
            self._drag_start_height = self.root.winfo_height()
            self._drag_start_root_x = self.root.winfo_rootx()
            self._drag_start_root_y = self.root.winfo_rooty()
    
    def _on_resize_end(self, event: tk.Event) -> None:
        """结束调整大小"""
        self._resize_edge = None
    
    def _on_resize_motion(self, event: tk.Event) -> None:
        """调整大小中"""
        if not self._resize_edge:
            return
        
        current_x = self.root.winfo_pointerx()
        current_y = self.root.winfo_pointery()
        dx = current_x - self._drag_start_x
        dy = current_y - self._drag_start_y
        
        new_width = self._drag_start_width
        new_height = self._drag_start_height
        new_x = self._drag_start_root_x
        new_y = self._drag_start_root_y
        
        min_width = 1000
        min_height = 700
        
        edge = self._resize_edge
        
        if "right" in edge:
            new_width = max(min_width, self._drag_start_width + dx)
        if "left" in edge:
            new_width = max(min_width, self._drag_start_width - dx)
            if new_width > min_width:
                new_x = self._drag_start_root_x + dx
        if "bottom" in edge:
            new_height = max(min_height, self._drag_start_height + dy)
        if "top" in edge:
            new_height = max(min_height, self._drag_start_height - dy)
            if new_height > min_height:
                new_y = self._drag_start_root_y + dy
        
        # 更新窗口
        if new_width >= min_width or new_height >= min_height:
            self.root.geometry(f"{new_width}x{new_height}+{new_x}+{new_y}")


class CustomTitleBar(tk.Frame):
    """
    自定义标题栏
    
    支持：拖动、最小化、最大化、关闭
    """
    
    def __init__(self, parent: tk.Tk, title: str = "Novel Writing Assistant-Agent Pro"):
        super().__init__(parent, bg=GlassTheme.GLASS_BG, height=40)
        
        self.parent = parent
        self.title_text = title
        
        self._drag_start_x = 0
        self._drag_start_y = 0
        
        self._create_widgets()
        self._bind_events()
    
    def _create_widgets(self) -> None:
        # 标题
        self.title_label = tk.Label(
            self,
            text=self.title_text,
            font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SUBTITLE, "bold"),
            fg=GlassTheme.TEXT_PRIMARY,
            bg=GlassTheme.GLASS_BG
        )
        self.title_label.pack(side=tk.LEFT, padx=15, pady=8)
        
        # 窗口控制按钮容器
        btn_frame = tk.Frame(self, bg=GlassTheme.GLASS_BG)
        btn_frame.pack(side=tk.RIGHT)
        
        # 按钮统一配置（等比例缩小）
        BTN_WIDTH = 36
        BTN_HEIGHT = 26
        
        # 使用Canvas绘制统一大小的图标
        def create_icon_canvas(parent, draw_func, bg_color):
            """创建图标Canvas"""
            canvas = tk.Canvas(
                parent,
                width=BTN_WIDTH,
                height=BTN_HEIGHT,
                bg=bg_color,
                highlightthickness=0
            )
            draw_func(canvas, BTN_WIDTH // 2, BTN_HEIGHT // 2)
            return canvas
        
        def draw_minimize(canvas, cx, cy):
            """绘制最小化图标 - 水平线"""
            canvas.create_line(cx - 6, cy, cx + 6, cy, fill=GlassTheme.TEXT_SECONDARY, width=2)
        
        def draw_maximize(canvas, cx, cy):
            """绘制最大化图标 - 空心方块"""
            canvas.create_rectangle(cx - 5, cy - 5, cx + 5, cy + 5, outline=GlassTheme.TEXT_SECONDARY, width=2)
        
        def draw_close(canvas, cx, cy):
            """绘制关闭图标 - X"""
            canvas.create_line(cx - 5, cy - 5, cx + 5, cy + 5, fill=GlassTheme.TEXT_SECONDARY, width=2)
            canvas.create_line(cx - 5, cy + 5, cx + 5, cy - 5, fill=GlassTheme.TEXT_SECONDARY, width=2)
        
        # 最小化按钮
        self.min_btn = create_icon_canvas(btn_frame, draw_minimize, GlassTheme.GLASS_BG)
        self.min_btn.pack(side=tk.LEFT)
        self.min_btn.cursor = "hand2"
        
        # 最大化按钮
        self.max_btn = create_icon_canvas(btn_frame, draw_maximize, GlassTheme.GLASS_BG)
        self.max_btn.pack(side=tk.LEFT)
        self.max_btn.cursor = "hand2"
        
        # 关闭按钮
        self.close_btn = create_icon_canvas(btn_frame, draw_close, GlassTheme.GLASS_BG)
        self.close_btn.pack(side=tk.LEFT)
        self.close_btn.cursor = "hand2"
        
        # 悬停效果
        for btn in [self.min_btn, self.max_btn]:
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=GlassTheme.GLASS_HOVER))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=GlassTheme.GLASS_BG))
        
        # Canvas悬停效果 - 使用不同的方法
        def on_min_enter(e):
            self.min_btn.configure(bg=GlassTheme.GLASS_HOVER)
        def on_min_leave(e):
            self.min_btn.configure(bg=GlassTheme.GLASS_BG)
        def on_max_enter(e):
            self.max_btn.configure(bg=GlassTheme.GLASS_HOVER)
        def on_max_leave(e):
            self.max_btn.configure(bg=GlassTheme.GLASS_BG)
        def on_close_enter(e):
            self.close_btn.configure(bg=GlassTheme.ERROR)
        def on_close_leave(e):
            self.close_btn.configure(bg=GlassTheme.GLASS_BG)
        
        self.min_btn.bind("<Enter>", on_min_enter)
        self.min_btn.bind("<Leave>", on_min_leave)
        self.max_btn.bind("<Enter>", on_max_enter)
        self.max_btn.bind("<Leave>", on_max_leave)
        self.close_btn.bind("<Enter>", on_close_enter)
        self.close_btn.bind("<Leave>", on_close_leave)
    
    def _bind_events(self) -> None:
        # 拖动窗口
        self.bind("<Button-1>", self._on_drag_start)
        self.bind("<B1-Motion>", self._on_drag_motion)
        self.title_label.bind("<Button-1>", self._on_drag_start)
        self.title_label.bind("<B1-Motion>", self._on_drag_motion)
        
        # 窗口控制
        self.min_btn.bind("<Button-1>", lambda e: self.parent.iconify())
        self.max_btn.bind("<Button-1>", self._toggle_maximize)
        self.close_btn.bind("<Button-1>", lambda e: self.parent.quit())
        
        # 双击标题栏最大化
        self.bind("<Double-Button-1>", lambda e: self._toggle_maximize(None))
    
    def _on_drag_start(self, event: tk.Event) -> None:
        self._drag_start_x = event.x
        self._drag_start_y = event.y
    
    def _on_drag_motion(self, event: tk.Event) -> None:
        x = self.parent.winfo_x() + event.x - self._drag_start_x
        y = self.parent.winfo_y() + event.y - self._drag_start_y
        self.parent.geometry(f"+{x}+{y}")
    
    def _toggle_maximize(self, event: Optional[tk.Event]) -> None:
        if self.parent.state() == "zoomed":
            self.parent.state("normal")
            self.max_btn.configure(text="□")
        else:
            self.parent.state("zoomed")
            self.max_btn.configure(text="❐")




# ============== 主窗口 ==============
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 创建Treeview
        columns = ("agent", "status", "duration", "result")
        self._agent_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=8
        )
        
        self._agent_tree.heading("agent", text="Agent")
        self._agent_tree.heading("status", text="状态")
        self._agent_tree.heading("duration", text="耗时")
        self._agent_tree.heading("result", text="结果")
        
        self._agent_tree.column("agent", width=150)
        self._agent_tree.column("status", width=100)
        self._agent_tree.column("duration", width=80)
        self._agent_tree.column("result", width=200)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._agent_tree.yview)
        self._agent_tree.configure(yscrollcommand=scrollbar.set)
        
        self._agent_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 日志输出
        log_frame = tk.LabelFrame(
            self.window,
            text="执行日志",
            font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL),
            fg=GlassTheme.TEXT_PRIMARY,
            bg=GlassTheme.GLASS_BG
        )
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self._log_text = tk.Text(
            log_frame,
            wrap=tk.WORD,
            height=6,
            font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL),
            bg=GlassTheme.GLASS_SURFACE,
            fg=GlassTheme.TEXT_PRIMARY
        )
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_scroll.set)
        
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 按钮区
        btn_frame = tk.Frame(self.window, bg=GlassTheme.GLASS_BG)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self._interrupt_btn = ttk.Button(
            btn_frame,
            text="⚠️ 中断生成",
            command=self._on_interrupt,
            state=tk.DISABLED
        )
        self._interrupt_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="清空日志",
            command=self._clear_log
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="关闭",
            command=self.window.destroy
        ).pack(side=tk.RIGHT, padx=5)
    
    def _subscribe_events(self):
        """订阅事件"""
        if not self._event_bus:
            return
        
        # 订阅生成事件
        events = [
            ("generation.started", self._on_generation_started),
            ("generation.completed", self._on_generation_completed),
            ("generation.failed", self._on_generation_failed),
            ("generation.progress", self._on_generation_progress),
            # 订阅流水线事件
            ("pipeline.stage_started", self._on_stage_started),
            ("pipeline.stage_completed", self._on_stage_completed),
            ("pipeline.iteration_started", self._on_iteration_started),
            ("pipeline.completed", self._on_pipeline_completed),
            # 订阅Agent事件
            ("agent.task.started", self._on_agent_task_started),
            ("agent.task.completed", self._on_agent_task_completed),
            ("agent.task.failed", self._on_agent_task_failed),
        ]
        
        for event_type, handler in events:
            try:
                sub_id = self._event_bus.subscribe(event_type, handler)
                self._subscription_ids.append(sub_id)
            except Exception as e:
                logger.warning(f"订阅事件失败 {event_type}: {e}")
    
    def _unsubscribe_events(self):
        """取消订阅事件"""
        if not self._event_bus:
            return
        
        for sub_id in self._subscription_ids:
            try:
                self._event_bus.unsubscribe(sub_id)
            except Exception:
                pass
        
        self._subscription_ids.clear()
    
    # === 事件处理器 ===
    
    def _on_generation_started(self, event):
        """生成开始事件"""
        def update():
            self._is_running = True
            self._current_pipeline_id = event.data.get("pipeline_id")
            self._status_var.set("🚀 生成任务已开始")
            self._title_var.set(f"🔍 生成过程监视器 - {self._current_pipeline_id}")
            self._interrupt_btn.configure(state=tk.NORMAL)
            self._progress_var.set(0)
            self._progress_label.configure(text="0%")
            self._log_insert(f"[{self._timestamp()}] 生成任务开始\n")
            self._clear_agent_tree()
        
        self.parent.after(0, update)
    
    def _on_generation_completed(self, event):
        """生成完成事件"""
        def update():
            self._is_running = False
            result = event.data.get("result", {})
            success = result.get("success", False)
            
            if success:
                self._status_var.set("✅ 生成完成")
                self._progress_var.set(100)
                self._progress_label.configure(text="100%")
                self._log_insert(f"[{self._timestamp()}] ✅ 生成成功完成\n")
            else:
                self._status_var.set("❌ 生成失败")
                self._log_insert(f"[{self._timestamp()}] ❌ 生成失败: {result.get('error', '未知错误')}\n")
            
            self._interrupt_btn.configure(state=tk.DISABLED)
        
        self.parent.after(0, update)
    
    def _on_generation_failed(self, event):
        """生成失败事件"""
        def update():
            self._is_running = False
            error = event.data.get("error", "未知错误")
            self._status_var.set(f"❌ 生成失败: {error}")
            self._log_insert(f"[{self._timestamp()}] ❌ 生成失败: {error}\n")
            self._interrupt_btn.configure(state=tk.DISABLED)
        
        self.parent.after(0, update)
    
    def _on_generation_progress(self, event):
        """生成进度事件"""
        def update():
            progress = event.data.get("progress", 0)
            stage = event.data.get("stage", "")
            message = event.data.get("message", "")
            
            self._progress_var.set(progress)
            self._progress_label.configure(text=f"{progress:.1f}%")
            if message:
                self._log_insert(f"[{self._timestamp()}] [{stage}] {message}\n")
        
        self.parent.after(0, update)
    
    def _on_stage_started(self, event):
        """流水线阶段开始事件"""
        def update():
            stage_name = event.data.get("stage_name", "")
            agent_type = event.data.get("agent_type", "")
            iteration = event.data.get("iteration", 1)
            
            self._log_insert(f"[{self._timestamp()}] 📌 阶段开始: {stage_name} (Agent: {agent_type}, 迭代: {iteration})\n")
            self._add_agent_row(agent_type, stage_name, "运行中", "-", "...")
        
        self.parent.after(0, update)
    
    def _on_stage_completed(self, event):
        """流水线阶段完成事件"""
        def update():
            stage_name = event.data.get("stage_name", "")
            success = event.data.get("success", False)
            duration = event.data.get("duration_seconds", 0)
            
            status = "✅ 成功" if success else "❌ 失败"
            self._log_insert(f"[{self._timestamp()}] {status} 阶段完成: {stage_name} (耗时: {duration:.2f}s)\n")
            self._update_agent_row(stage_name, status, f"{duration:.2f}s", "完成" if success else "失败")
        
        self.parent.after(0, update)
    
    def _on_iteration_started(self, event):
        """迭代开始事件"""
        def update():
            iteration = event.data.get("iteration", 1)
            max_iterations = event.data.get("max_iterations", 5)
            
            self._log_insert(f"\n{'='*40}\n")
            self._log_insert(f"[{self._timestamp()}] 🔄 开始迭代 {iteration}/{max_iterations}\n")
        
        self.parent.after(0, update)
    
    def _on_pipeline_completed(self, event):
        """流水线完成事件"""
        def update():
            result_data = event.data
            success = result_data.get("success", False)
            total_iterations = result_data.get("total_iterations", 0)
            total_duration = result_data.get("total_duration_seconds", 0)
            
            status = "✅ 成功" if success else "❌ 失败"
            self._log_insert(f"\n{'='*40}\n")
            self._log_insert(f"[{self._timestamp()}] {status} 流水线完成\n")
            self._log_insert(f"  总迭代次数: {total_iterations}\n")
            self._log_insert(f"  总耗时: {total_duration:.2f}秒\n")
            
            self._status_var.set(f"{status} 流水线完成")
            self._is_running = False
            self._interrupt_btn.configure(state=tk.DISABLED)
        
        self.parent.after(0, update)
    
    def _on_agent_task_started(self, event):
        """Agent任务开始事件"""
        def update():
            task_id = event.data.get("task_id", "")
            agent_type = event.data.get("agent_type", "")
            
            self._log_insert(f"[{self._timestamp()}] 🤖 Agent任务开始: {agent_type} ({task_id})\n")
        
        self.parent.after(0, update)
    
    def _on_agent_task_completed(self, event):
        """Agent任务完成事件"""
        def update():
            task_id = event.data.get("task_id", "")
            agent_type = event.data.get("agent_type", "")
            result = event.data.get("result", {})
            
            self._log_insert(f"[{self._timestamp()}] ✅ Agent任务完成: {agent_type}\n")
            
            # 存储结果
            self._agent_results[agent_type] = result
        
        self.parent.after(0, update)
    
    def _on_agent_task_failed(self, event):
        """Agent任务失败事件"""
        def update():
            task_id = event.data.get("task_id", "")
            agent_type = event.data.get("agent_type", "")
            error = event.data.get("error", "未知错误")
            retry_count = event.data.get("retry_count", 0)
            
            self._log_insert(f"[{self._timestamp()}] ❌ Agent任务失败: {agent_type}\n")
            self._log_insert(f"    错误: {error}\n")
            self._log_insert(f"    重试次数: {retry_count}\n")
        
        self.parent.after(0, update)
    
    # === 辅助方法 ===
    
    def _log_insert(self, text: str):
        """插入日志文本"""
        self._log_text.insert(tk.END, text)
        self._log_text.see(tk.END)
    
    def _clear_log(self):
        """清空日志"""
        self._log_text.delete("1.0", tk.END)
    
    def _clear_agent_tree(self):
        """清空Agent列表"""
        for item in self._agent_tree.get_children():
            self._agent_tree.delete(item)
    
    def _add_agent_row(self, agent_type: str, stage: str, status: str, duration: str, result: str):
        """添加Agent行"""
        self._agent_tree.insert("", tk.END, iid=stage, values=(
            agent_type,
            status,
            duration,
            result[:50] + "..." if len(result) > 50 else result
        ))
    
    def _update_agent_row(self, stage: str, status: str, duration: str, result: str):
        """更新Agent行"""
        try:
            item = self._agent_tree.item(stage)
            if item:
                values = list(item["values"])
                values[1] = status
                values[2] = duration
                values[3] = result[:50] + "..." if len(result) > 50 else result
                self._agent_tree.item(stage, values=values)
        except Exception:
            pass
    
    def _timestamp(self) -> str:
        """获取时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")
    
    def _on_interrupt(self):
        """中断生成"""
        if not self._is_running:
            return
        
        if messagebox.askyesno("确认", "确定要中断当前生成任务吗？"):
            try:
                from agents.novel_generation_service import get_generation_service
                service = get_generation_service()
                if service.cancel_generation():
                    self._status_var.set("⚠️ 已中断")
                    self._log_insert(f"[{self._timestamp()}] ⚠️ 用户中断生成\n")
                    self._is_running = False
                    self._interrupt_btn.configure(state=tk.DISABLED)
                else:
                    self._log_insert(f"[{self._timestamp()}] ❌ 中断失败\n")
            except Exception as e:
                self._log_insert(f"[{self._timestamp()}] ❌ 中断异常: {e}\n")
    
    def _on_close(self):
        """窗口关闭"""
        self._unsubscribe_events()
        self.window.destroy()
    
    def show(self):
        """显示窗口"""
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()
    
    def hide(self):
        """隐藏窗口"""
        self.window.withdraw()
    
    def log(self, message: str):
        """添加日志消息"""
        self._log_insert(f"[{self._timestamp()}] {message}\n")
    
    def clear_log(self):
        """清空日志（公开方法）"""
        self._clear_log()


# ============== 主窗口 ==============

class MainWindow:
    """
    主窗口类
    
    结构：
    - 自定义标题栏
    - 侧边栏（导航）
    - 主内容区（根据侧边栏选择显示）
    - 状态栏
    """
    
    VERSION = "V2.1.0"
    TITLE = "Novel Writing Assistant - Agent Pro"
    
    def __init__(self):
        """初始化主窗口"""
        # 创建根窗口
        self.root = tk.Tk()
        self.root.title(self.TITLE)
        self.root.geometry("1400x900")
        self.root.minsize(1000, 700)
        
        # 设置窗口背景
        self.root.configure(bg=GlassTheme.GLASS_BG)
        
        # 尝试启用玻璃效果
        self._enable_glass_effect()
        
        # 核心服务
        self._services: Optional[CoreServiceManager] = None
        self._async_handler: Optional[AsyncHandler] = None
        
        # UI组件
        self._content_frame: Optional[tk.Frame] = None
        self._status_var: Optional[tk.StringVar] = None
        self._title_bar: Optional[CustomTitleBar] = None
        self._resize_grip: Optional[ResizeGrip] = None  # 窗口调整大小边框感知
        
        # 当前显示的页面
        self._current_page: Optional[str] = None
        self._pages: Dict[str, tk.Frame] = {}
        
        # 项目状态
        self.current_project: Dict[str, Any] = {}
        self.project_file: Optional[str] = None
        self.project_info: Dict[str, Any] = {}
        
        # 结果队列（后台线程通信）
        self._result_queue = queue.Queue()
        
        # 线程安全锁（快捷创作模块）
        self._quick_lock = threading.Lock()
        
        # 缓存
        self._cache = {
            'outline': {},
            'style': {},
            'worldview': {},
            'characters': {},
            'file_mtime': {}
        }
        
        # 小说生成相关
        self._current_pipeline_id: Optional[str] = None
        self._outline_content: str = ""
        self._chapter_outlines: Dict[int, str] = {}
        self._style_profile: Dict[str, Any] = {}
        self._characters: List[Dict[str, Any]] = []
        self._worldview: Dict[str, Any] = {}
        self._llm_client = None
        
        # 事件订阅ID
        self._subscription_ids: List[str] = []
        
        # 初始化
        self._init_theme()
        self._init_async_handler()
        self._init_core_services()
        self._init_ui()
        self._init_bindings()
        
        # 启动结果队列处理
        self.root.after(100, self._process_result_queue)
        
        # 窗口关闭确认
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        logger.info("MainWindow initialized")
    
    def _enable_glass_effect(self) -> None:
        """启用玻璃效果"""
        try:
            glass_mgr = GlassWindowManager(self.root)
            
            # 尝试Acrylic效果
            if glass_mgr.enable_acrylic(0x80000000):
                logger.info("Acrylic glass effect enabled")
            else:
                logger.info("Acrylic effect not available, using alpha transparency")
            
            # 无论 Acrylic 是否成功，都应用完全无边框
            glass_mgr.make_frameless(keep_resize_border=False)
            
            # 如果 Acrylic 失败，降级到透明效果
            if not glass_mgr._is_acrylic:
                self.root.attributes('-alpha', 0.95)
            
            logger.info("Frameless window enabled")
        
        except Exception as e:
            logger.warning(f"Glass effect not available: {e}")
            self.root.attributes('-alpha', 0.98)
    
    def _init_theme(self) -> None:
        """初始化主题"""
        style = ttk.Style()
        
        # 使用sv_ttk主题
        if SV_TTK_AVAILABLE:
            try:
                sv_ttk.set_theme("dark")
            except Exception:
                pass
        
        # 应用玻璃态主题
        GlassTheme.apply_to_style(style)
    
    def _init_async_handler(self) -> None:
        """初始化异步处理器"""
        if CORE_AVAILABLE:
            self._async_handler = init_async_handler(
                root=self.root,
                worker_count=4,
                default_timeout=30.0
            )
            logger.info("AsyncHandler initialized")
    
    def _init_core_services(self) -> None:
        """初始化核心服务"""
        if not CORE_AVAILABLE:
            logger.warning("Core services not available")
            return
        
        try:
            self._services = CoreServiceManager(self.root)
            self._services.initialize(
                event_bus=get_event_bus(),
                registry=get_plugin_registry(),
                locator=get_service_locator(),
                config=get_config_manager()
            )
            
            # 订阅生成事件
            self._subscribe_generation_events()
            
            logger.info("Core services initialized")
        except Exception as e:
            logger.error(f"Failed to initialize core services: {e}")
    
    def _init_ui(self) -> None:
        """初始化UI"""
        # 自定义标题栏
        self._title_bar = CustomTitleBar(self.root, self.TITLE)
        self._title_bar.pack(fill=tk.X)
        
        # 窗口调整大小的边框感知（完全无边框模式需要）
        self._resize_grip = ResizeGrip(self.root)
        
        # 主容器
        main_container = ttk.Frame(self.root, style="TFrame")
        main_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        # 侧边栏
        self._create_sidebar(main_container)
        
        # 内容区
        self._create_content(main_container)
        
        # 状态栏
        self._create_status_bar()
        
        # 默认显示热榜页面
        self._switch_to_page("hot_ranking")
    
    def _create_sidebar(self, parent: tk.Widget) -> None:
        """创建侧边栏"""
        sidebar = ttk.Frame(parent, style="TFrame", width=200)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        sidebar.pack_propagate(False)
        
        # 导航按钮
        nav_buttons = [
            ("热榜", "hot_ranking", GlassTheme.ACCENT_PINK),
            ("工作台", "workbench", GlassTheme.PRIMARY_LIGHT),
            ("创作进度", "progress", GlassTheme.ACCENT_GREEN),
            ("项目管理", "project", GlassTheme.ACCENT_PURPLE),
            ("插件管理", "plugins", GlassTheme.ACCENT_ORANGE),
            ("设置", "settings", GlassTheme.WARNING),
        ]
        
        for text, page_id, color in nav_buttons:
            btn = tk.Label(
                sidebar,
                text=text,
                font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                fg=GlassTheme.TEXT_PRIMARY,
                bg=GlassTheme.GLASS_SURFACE,
                activeforeground=GlassTheme.TEXT_PRIMARY,
                activebackground=color,
                cursor="hand2",
                padx=20,
                pady=12,
                anchor="w"
            )
            btn.pack(fill=tk.X, pady=2)
            
            # 悬停效果
            btn.bind("<Enter>", lambda e, b=btn, c=color: b.configure(bg=c))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=GlassTheme.GLASS_SURFACE))
            btn.bind("<Button-1>", lambda e, pid=page_id: self._switch_to_page(pid))
        
        # 底部版本信息
        version_label = tk.Label(
            sidebar,
            text=f"Agent Pro {self.VERSION}",
            font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_TINY),
            fg=GlassTheme.TEXT_DISABLED,
            bg=GlassTheme.GLASS_BG
        )
        version_label.pack(side=tk.BOTTOM, pady=10)
    
    def _create_content(self, parent: tk.Widget) -> None:
        """创建内容区"""
        self._content_frame = ttk.Frame(parent, style="Glass.TFrame")
        self._content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    def _create_status_bar(self) -> None:
        """创建状态栏（增强版：项目名称、AI连接、字数统计、后台任务进度）"""
        status_frame = ttk.Frame(self.root, style="TFrame")
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 8))
        
        # 分隔线
        ttk.Separator(status_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 4))
        
        status_inner = ttk.Frame(status_frame, style="TFrame")
        status_inner.pack(fill=tk.X)
        
        # 项目名称
        self._project_var = tk.StringVar(value="项目: 未打开")
        ttk.Label(
            status_inner,
            textvariable=self._project_var,
            font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL)
        ).pack(side=tk.LEFT)
        
        # 分隔符
        ttk.Label(status_inner, text=" | ", font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL),
                 foreground=GlassTheme.TEXT_SECONDARY).pack(side=tk.LEFT, padx=5)
        
        # 字数统计
        self._word_count_var = tk.StringVar(value="字数: 0")
        ttk.Label(
            status_inner,
            textvariable=self._word_count_var,
            font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL)
        ).pack(side=tk.LEFT)
        
        # 分隔符
        ttk.Label(status_inner, text=" | ", font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL),
                 foreground=GlassTheme.TEXT_SECONDARY).pack(side=tk.LEFT, padx=5)
        
        # 状态文本
        self._status_var = tk.StringVar(value="就绪")
        ttk.Label(
            status_inner,
            textvariable=self._status_var,
            font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL)
        ).pack(side=tk.LEFT, padx=10)
        
        # 后台任务进度（右侧）
        self._background_task_var = tk.StringVar(value="")
        self._background_task_label = ttk.Label(
            status_inner,
            textvariable=self._background_task_var,
            font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL),
            foreground=GlassTheme.INFO
        )
        self._background_task_label.pack(side=tk.RIGHT, padx=10)
        
        # 分隔符
        ttk.Label(status_inner, text=" | ", font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL),
                 foreground=GlassTheme.TEXT_SECONDARY).pack(side=tk.RIGHT, padx=5)
        
        # AI连接状态
        self._ai_status_var = tk.StringVar(value="AI: 未连接")
        self._ai_status_label = ttk.Label(
            status_inner,
            textvariable=self._ai_status_var,
            font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL)
        )
        self._ai_status_label.pack(side=tk.RIGHT, padx=10)
    
    def _update_status_bar(self, project_name: str = None, word_count: int = None, 
                          ai_status: str = None, background_task: str = None) -> None:
        """更新状态栏信息"""
        if project_name is not None:
            self._project_var.set(f"项目: {project_name}")
        if word_count is not None:
            self._word_count_var.set(f"字数: {word_count:,}")
        if ai_status is not None:
            self._ai_status_var.set(f"AI: {ai_status}")
            # 更新颜色
            if ai_status == "在线":
                self._ai_status_label.configure(foreground=GlassTheme.SUCCESS)
            elif ai_status == "离线":
                self._ai_status_label.configure(foreground=GlassTheme.ERROR)
            else:
                self._ai_status_label.configure(foreground=GlassTheme.WARNING)
        if background_task is not None:
            self._background_task_var.set(background_task)
    
    def _init_bindings(self) -> None:
        """初始化快捷键绑定（增强版）"""
        # 页面切换
        self.root.bind("<Control-w>", lambda e: self._switch_to_page("workbench"))
        self.root.bind("<Control-p>", lambda e: self._switch_to_page("project"))
        self.root.bind("<Control-s>", lambda e: self._switch_to_page("settings"))
        self.root.bind("<Control-g>", lambda e: self._on_quick_generate_action())
        self.root.bind("<F5>", lambda e: self._refresh_current_page())
        
        # 新增快捷键
        self.root.bind("<Control-n>", lambda e: self._on_new_item())  # 新建
        self.root.bind("<Control-o>", lambda e: self._on_open_project())  # 打开项目
        self.root.bind("<Control-b>", lambda e: self._on_backup_project())  # 备份
        self.root.bind("<Escape>", lambda e: self._on_cancel_action())  # 取消
    
    def _on_quick_generate_action(self):
        """快速生成快捷键处理"""
        self._switch_to_page("workbench")
        self._switch_workbench_tab("quick")
    
    def _on_new_item(self):
        """新建项目快捷键处理"""
        self._switch_to_page("project")
        self._on_new_project()
    
    def _on_cancel_action(self):
        """取消操作"""
        self._set_status("操作已取消")
    
    # ============== 页面切换 ==============
    
    def _switch_to_page(self, page_id: str) -> None:
        """切换到指定页面"""
        # 隐藏当前页面
        if self._current_page and self._current_page in self._pages:
            self._pages[self._current_page].pack_forget()
        
        # 创建或显示新页面
        if page_id not in self._pages:
            self._pages[page_id] = self._create_page(page_id)
            logger.debug(f"Created new page: {page_id}")
        
        # pack页面到content_frame
        page = self._pages[page_id]
        page.pack(fill=tk.BOTH, expand=True, in_=self._content_frame)
        self._current_page = page_id
        
        # 等待页面pack完成后更新Canvas宽度
        self.root.after(100, self._update_canvas_widths)
        
        logger.debug(f"Switched to page: {page_id}, parent={page.master}, winfo_parent={page.winfo_parent()}")
    
    def _update_canvas_widths(self):
        """更新所有Canvas的窗口宽度"""
        for widget in self._content_frame.winfo_children():
            self._update_canvas_width_recursive(widget)
    
    def _update_canvas_width_recursive(self, widget):
        """递归更新所有Canvas的窗口宽度"""
        if widget.winfo_class() == 'Canvas':
            # 获取Canvas中的所有窗口
            for item_id in widget.find_withtag("all"):
                tags = widget.gettags(item_id)
                if "all" not in tags:
                    # 这是一个canvas window，更新其宽度
                    widget.itemconfig(item_id, width=widget.winfo_width())
        
        # 递归处理子控件
        for child in widget.winfo_children():
            self._update_canvas_width_recursive(child)
    
    def _create_page(self, page_id: str) -> tk.Frame:
        """创建页面"""
        page_creators = {
            "hot_ranking": self._create_hot_ranking_page,
            "workbench": self._create_workbench_page,
            "progress": self._create_progress_page,
            "project": self._create_project_page,
            "plugins": self._create_plugins_page,
            "settings": self._create_settings_page,
        }
        
        creator = page_creators.get(page_id)
        if creator:
            return creator()
        else:
            # 默认空白页面
            frame = ttk.Frame(self._content_frame, style="TFrame")
            ttk.Label(frame, text=f"页面: {page_id}", style="Title.TLabel").pack(padx=20, pady=20)
            return frame
    
    def _refresh_current_page(self) -> None:
        """刷新当前页面"""
        if self._current_page:
            # 销毁当前页面并重新创建
            if self._current_page in self._pages:
                self._pages[self._current_page].destroy()
                del self._pages[self._current_page]
            self._switch_to_page(self._current_page)
    
    # ============== 页面创建器 ==============
    
    def _create_hot_ranking_page(self) -> tk.Frame:
        """创建热榜页面（V5完整迁移）"""
        frame = ttk.Frame(self._content_frame, style="TFrame")
        
        # 创建滚动容器
        canvas = tk.Canvas(frame, bg=GlassTheme.GLASS_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="TFrame")
        
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
        
        scrollable_frame.bind("<Configure>", on_frame_configure)
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 鼠标滚轮绑定
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        def bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        def unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        
        canvas.bind("<Enter>", bind_mousewheel)
        canvas.bind("<Leave>", unbind_mousewheel)
        
        # Canvas和Scrollbar直接pack到frame中
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 标题栏
        title_frame = ttk.Frame(scrollable_frame, style="TFrame")
        title_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        tk.Label(
            title_frame,
            text="全网小说热度榜单",
            font=(GlassTheme.FONT_FAMILY, 24, "bold"),
            fg=GlassTheme.ACCENT_PINK,
            bg=GlassTheme.GLASS_BG
        ).pack(side=tk.LEFT)
        
        # 按钮区
        btn_frame = ttk.Frame(title_frame, style="TFrame")
        btn_frame.pack(side=tk.RIGHT)
        
        # 清缓存按钮
        self.clear_cache_btn = ResponsiveButton(
            btn_frame,
            text="清缓存",
            command=self._clear_hot_ranking_cache,
            async_handler=self._async_handler
        )
        self.clear_cache_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # 更新按钮
        self.update_hot_btn = ResponsiveButton(
            btn_frame,
            text="更新数据",
            command=self._update_hot_ranking_data,
            async_handler=self._async_handler,
            style="Accent.TButton"
        )
        self.update_hot_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        ttk.Separator(scrollable_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20, pady=10)
        
        # ========== 第一部分：三大网站榜单 ==========
        ttk.Label(
            scrollable_frame,
            text="三大热门小说网站排行榜 (前10名)",
            font=(GlassTheme.FONT_FAMILY, 16, "bold")
        ).pack(pady=(20, 10), anchor='w', padx=20)
        
        # 来源说明行
        src_desc_frame = ttk.Frame(scrollable_frame, style="TFrame")
        src_desc_frame.pack(fill=tk.X, padx=22, pady=(0, 8))
        
        site_badge_info = [
            ('🍅', '番茄', GlassTheme.ACCENT_RED),
            ('🚀', '起点', GlassTheme.INFO),
            ('🔷', '晋江', GlassTheme.ACCENT_PURPLE),
        ]
        for icon, name, color in site_badge_info:
            badge = tk.Label(
                src_desc_frame,
                text=f" {icon} {name} ",
                font=(GlassTheme.FONT_FAMILY, 9),
                fg='white', bg=color,
                padx=4, pady=2,
                relief='flat'
            )
            badge.pack(side=tk.LEFT, padx=(0, 6))
        
        # 网站榜单容器（V5原版：使用pack布局，三列并排）
        sites_frame = ttk.Frame(scrollable_frame, style="TFrame")
        sites_frame.pack(fill=tk.X, padx=20, pady=10)

        # 获取一次数据（避免重复调用）
        hot_data = self._get_hot_ranking_data()
        sites_data = hot_data.get('sites', [])
        for site_info in sites_data:
            site_column = ttk.Frame(sites_frame, relief='flat', style="TFrame")
            site_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8)
            
            # 网站标题
            site_header = tk.Label(
                site_column,
                text=site_info['name'],
                font=(GlassTheme.FONT_FAMILY, 13, 'bold'),
                fg='white',
                bg=site_info['color'],
                pady=10
            )
            site_header.pack(fill=tk.X)
            
            # 书籍列表
            books_frame = ttk.Frame(site_column, style="TFrame")
            books_frame.pack(fill=tk.X, pady=6)
            
            books = site_info.get('books', [])[:10]
            for idx, book in enumerate(books, 1):
                book_item = ttk.Frame(books_frame, style="TFrame")
                book_item.pack(fill=tk.X, pady=3)
                
                # 排名徽章
                rank_bg = site_info['color'] if idx <= 3 else '#CCCCCC'
                rank_label = tk.Label(
                    book_item,
                    text=str(idx),
                    font=(GlassTheme.FONT_FAMILY, 11, 'bold'),
                    fg='white',
                    bg=rank_bg,
                    width=3
                )
                rank_label.pack(side=tk.LEFT, padx=(0, 5))
                
                # 书籍信息
                info_frame = ttk.Frame(book_item, style="TFrame")
                info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
                
                title = book.get('title', '未知')
                author = book.get('author', '未知')
                category = book.get('category', '')
                heat = book.get('heat', 0)
                
                # 格式化热度
                if heat >= 100000000:
                    heat_str = f"{heat/100000000:.1f}亿"
                elif heat >= 10000:
                    heat_str = f"{heat/10000:.1f}万"
                elif heat > 0:
                    heat_str = str(heat)
                else:
                    heat_str = "-"
                
                # 书名
                ttk.Label(
                    info_frame,
                    text=f"《{title}》",
                    font=(GlassTheme.FONT_FAMILY, 10, 'bold')
                ).pack(anchor='w')
                
                # 作者/分类/热度
                detail_parts = [f"作者：{author}"]
                if category:
                    detail_parts.append(category)
                if heat_str != "-":
                    detail_parts.append(f"热度：{heat_str}")
                
                ttk.Label(
                    info_frame,
                    text="  ".join(detail_parts),
                    font=(GlassTheme.FONT_FAMILY, 8),
                    foreground='gray'
                ).pack(anchor='w')
        
        ttk.Separator(scrollable_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20, pady=20)
        
        # ========== 第二部分：题材热度榜 ==========
        ttk.Label(
            scrollable_frame,
            text="题材热度榜 (前5名)",
            font=(GlassTheme.FONT_FAMILY, 16, 'bold')
        ).pack(pady=(20, 10), anchor='w', padx=20)
        
        genre_frame = ttk.Frame(scrollable_frame, style="TFrame")
        genre_frame.pack(fill=tk.X, padx=20, pady=10)
        
        genres_data = hot_data.get('genres', {})
        for gender in ['male', 'female']:
            genre_info = genres_data.get(gender, {})
            if not genre_info:
                continue
            
            genre_column = ttk.Frame(genre_frame, style="TFrame")
            genre_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
            
            genre_header = tk.Label(
                genre_column,
                text=genre_info.get('title', ''),
                font=(GlassTheme.FONT_FAMILY, 13, 'bold'),
                fg='white',
                bg=genre_info.get('color', GlassTheme.PRIMARY),
                pady=10
            )
            genre_header.pack(fill=tk.X)
            
            chart_frame = ttk.Frame(genre_column, style="TFrame")
            chart_frame.pack(fill=tk.X, pady=10)
            
            genres = genre_info.get('genres', [])
            # 只过滤掉名称为未知的数据，保留热度为0的题材
            valid_genres = [(name, heat) for name, heat in genres if name and name != '未知']

            if valid_genres:
                max_hot = max([g[1] for g in valid_genres]) or 1

                for genre_name, hot_value in valid_genres:
                    chart_item = ttk.Frame(chart_frame, style="TFrame")
                    chart_item.pack(fill=tk.X, pady=8)
                    
                    ttk.Label(
                        chart_item,
                        text=genre_name,
                        font=(GlassTheme.FONT_FAMILY, 10),
                        width=10,
                        anchor='e'
                    ).pack(side=tk.LEFT, padx=(0, 8))
                    
                    bar_container = tk.Frame(chart_item, bg=GlassTheme.GLASS_BORDER, height=20)
                    bar_container.pack(side=tk.LEFT, fill=tk.X, expand=True)
                    
                    bar_canvas = tk.Canvas(bar_container, bg=GlassTheme.GLASS_BORDER, height=20, highlightthickness=0)
                    bar_canvas.pack(fill=tk.BOTH, expand=True)
                    
                    ratio = hot_value / max_hot
                    color = genre_info.get('color', GlassTheme.PRIMARY)
                    
                    # 绑定Configure事件绘制条形图（确保Canvas尺寸确定后再绘制）
                    def on_bar_configure(event, canvas=bar_canvas, c=color, r=ratio):
                        w = canvas.winfo_width()
                        h = canvas.winfo_height()
                        if w > 10 and h > 5:
                            canvas.delete("all")
                            canvas.create_rectangle(0, 0, int(w * r), h, fill=c, outline="")
                    
                    bar_canvas.bind("<Configure>", on_bar_configure)
                    
                    tk.Label(
                        chart_item,
                        text=f"{hot_value:.1f}分",
                        font=(GlassTheme.FONT_FAMILY, 9, 'bold'),
                        fg=color,
                        bg=GlassTheme.GLASS_BG,
                        width=8, anchor='w'
                    ).pack(side=tk.LEFT, padx=(8, 0))
        
        ttk.Separator(scrollable_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20, pady=20)
        
        # ========== 第三部分：设定类型/创作流派榜 ==========
        ttk.Label(
            scrollable_frame,
            text="设定类型/创作流派榜 (前5名)",
            font=(GlassTheme.FONT_FAMILY, 16, 'bold')
        ).pack(pady=(20, 10), anchor='w', padx=20)
        
        type_frame = ttk.Frame(scrollable_frame, style="TFrame")
        type_frame.pack(fill=tk.X, padx=20, pady=10)
        
        types_data = hot_data.get('types', {})
        for gender in ['male', 'female']:
            type_info = types_data.get(gender, {})
            if not type_info:
                continue
            
            type_column = ttk.Frame(type_frame, style="TFrame")
            type_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
            
            type_header = tk.Label(
                type_column,
                text=type_info.get('title', ''),
                font=(GlassTheme.FONT_FAMILY, 13, 'bold'),
                fg='white',
                bg=type_info.get('color', GlassTheme.ACCENT_GREEN),
                pady=10
            )
            type_header.pack(fill=tk.X)
            
            chart_frame = ttk.Frame(type_column, style="TFrame")
            chart_frame.pack(fill=tk.X, pady=10)
            
            types = type_info.get('types', [])
            # 只过滤掉名称为未知的数据，保留热度为0的类型
            valid_types = [(name, heat) for name, heat in types if name and name != '未知']

            if valid_types:
                max_hot = max([t[1] for t in valid_types]) or 1

                for type_name, hot_value in valid_types:
                    chart_item = ttk.Frame(chart_frame, style="TFrame")
                    chart_item.pack(fill=tk.X, pady=8)
                    
                    ttk.Label(
                        chart_item,
                        text=type_name,
                        font=(GlassTheme.FONT_FAMILY, 10),
                        width=10,
                        anchor='e'
                    ).pack(side=tk.LEFT, padx=(0, 8))
                    
                    bar_container = tk.Frame(chart_item, bg=GlassTheme.GLASS_BORDER, height=20)
                    bar_container.pack(side=tk.LEFT, fill=tk.X, expand=True)
                    
                    bar_canvas = tk.Canvas(bar_container, bg=GlassTheme.GLASS_BORDER, height=20, highlightthickness=0)
                    bar_canvas.pack(fill=tk.BOTH, expand=True)
                    
                    ratio = hot_value / max_hot
                    color = type_info.get('color', GlassTheme.ACCENT_GREEN)
                    
                    # 绑定Configure事件绘制条形图（确保Canvas尺寸确定后再绘制）
                    def on_bar_configure(event, canvas=bar_canvas, c=color, r=ratio):
                        w = canvas.winfo_width()
                        h = canvas.winfo_height()
                        if w > 10 and h > 5:
                            canvas.delete("all")
                            canvas.create_rectangle(0, 0, int(w * r), h, fill=c, outline="")
                    
                    bar_canvas.bind("<Configure>", on_bar_configure)
                    
                    tk.Label(
                        chart_item,
                        text=f"{hot_value:.1f}分",
                        font=(GlassTheme.FONT_FAMILY, 9, 'bold'),
                        fg=color,
                        bg=GlassTheme.GLASS_BG,
                        width=8, anchor='w'
                    ).pack(side=tk.LEFT, padx=(8, 0))
        
        ttk.Separator(scrollable_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20, pady=20)
        
        # ========== 第四部分：作家排行榜 ==========
        ttk.Label(
            scrollable_frame,
            text="全网最热网络作家排行榜 (前10名)",
            font=(GlassTheme.FONT_FAMILY, 16, 'bold')
        ).pack(pady=(20, 10), anchor='w', padx=20)
        
        author_outer_frame = ttk.Frame(scrollable_frame, style="TFrame")
        author_outer_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        author_table_frame = tk.Frame(author_outer_frame, bg=GlassTheme.GLASS_SURFACE)
        author_table_frame.pack(fill=tk.BOTH, expand=True)

        # 配置列权重，使表格填满宽度
        for idx in range(5):
            author_table_frame.grid_columnconfigure(idx, weight=1)

        headers = ['排名', '作家', '代表作品', '预估年收入', '粉丝数']
        col_weights = [0, 0, 1, 0, 0]  # 只有第3列（代表作品）自动扩展

        for idx, (header, weight) in enumerate(zip(headers, col_weights)):
            tk.Label(
                author_table_frame,
                text=header,
                font=(GlassTheme.FONT_FAMILY, 11, 'bold'),
                fg='white', bg=GlassTheme.PRIMARY,
                pady=8, padx=5, anchor='center',
                relief='flat'
            ).grid(row=0, column=idx, sticky='nsew', padx=1, pady=1)
        
        authors_data = hot_data.get('authors', [])
        for row_idx, author in enumerate(authors_data, start=1):
            rank = author.get('rank', row_idx)
            name = author.get('name', '未知')
            works = author.get('works', '暂无')
            income = author.get('income', '0')
            fans = author.get('fans', '0')
            
            if rank == 1:
                bg_color, fg_color = '#FFD700', 'black'
            elif rank == 2:
                bg_color, fg_color = '#C0C0C0', 'black'
            elif rank == 3:
                bg_color, fg_color = '#CD7F32', 'white'
            else:
                bg_color, fg_color = GlassTheme.GLASS_SURFACE, GlassTheme.TEXT_PRIMARY
            
            cells = [f"TOP{rank}", name, works[:25]+'...' if len(works) > 25 else works, f"¥{income}", fans]
            anchors = ['center', 'center', 'w', 'center', 'center']
            fonts = [
                (GlassTheme.FONT_FAMILY, 10, 'bold'),
                (GlassTheme.FONT_FAMILY, 10),
                (GlassTheme.FONT_FAMILY, 9),
                (GlassTheme.FONT_FAMILY, 10, 'bold'),
                (GlassTheme.FONT_FAMILY, 9),
            ]
            for col_idx, (text, anchor, font) in enumerate(zip(cells, anchors, fonts)):
                tk.Label(
                    author_table_frame,
                    text=text,
                    font=font,
                    fg=fg_color, bg=bg_color,
                    pady=6, padx=5, anchor=anchor,
                    relief='flat'
                ).grid(row=row_idx, column=col_idx, sticky='nsew', padx=1, pady=1)
        
        # 数据来源说明
        ttk.Label(
            scrollable_frame,
            text="收入和粉丝数为算法估算值，仅供参考",
            font=(GlassTheme.FONT_FAMILY, 9),
            foreground=GlassTheme.TEXT_SECONDARY
        ).pack(pady=(5, 15), anchor='w', padx=20)
        
        return frame
    
    def _create_workbench_page(self) -> tk.Frame:
        """创建工作台页面（上半部分按钮 + 下半部分内容区）"""
        frame = ttk.Frame(self._content_frame, style="TFrame")
        
        # 标题
        header = ttk.Frame(frame, style="TFrame")
        header.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        ttk.Label(header, text="工作台", style="Title.TLabel").pack(side=tk.LEFT)
        
        # ========== 上半部分：八个功能按钮 ==========
        buttons_frame = ttk.Frame(frame, style="TFrame")
        buttons_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        
        # 第一行四个按钮
        row1 = ttk.Frame(buttons_frame, style="TFrame")
        row1.pack(fill=tk.X, pady=5)
        
        # 第二行四个按钮
        row2 = ttk.Frame(buttons_frame, style="TFrame")
        row2.pack(fill=tk.X, pady=5)
        
        functions = [
            ("世界观", "worldview", GlassTheme.ACCENT_PURPLE),
            ("人物设定", "characters", GlassTheme.ACCENT_PINK),
            ("大纲管理", "outline", GlassTheme.PRIMARY_LIGHT),
            ("风格学习", "style", GlassTheme.ACCENT_GREEN),
            ("开始创作", "generation", GlassTheme.PRIMARY),
            ("逆向反馈", "reverse", GlassTheme.WARNING),
            ("快捷创作", "quick", GlassTheme.ACCENT_RED),
            ("续写功能", "continue", GlassTheme.INFO),
        ]
        
        self._workbench_buttons = {}
        self._current_workbench_tab = tk.StringVar(value="worldview")
        
        for i, (text, tab_id, color) in enumerate(functions):
            parent = row1 if i < 4 else row2
            
            btn = tk.Label(
                parent,
                text=text,
                font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL, "bold"),
                fg=GlassTheme.TEXT_PRIMARY,
                bg=GlassTheme.GLASS_SURFACE,
                activeforeground=GlassTheme.TEXT_PRIMARY,
                activebackground=color,
                cursor="hand2",
                padx=20,
                pady=15,
                width=18
            )
            btn.pack(side=tk.LEFT, padx=8, pady=5, expand=True, fill=tk.X)
            
            # 存储按钮引用
            self._workbench_buttons[tab_id] = btn
            
            # 悬停效果
            btn.bind("<Enter>", lambda e, b=btn, c=color: b.configure(bg=c))
            btn.bind("<Leave>", lambda e, b=btn, tid=tab_id: self._update_button_style(tid))
            btn.bind("<Button-1>", lambda e, tid=tab_id: self._switch_workbench_tab(tid))
        
        # ========== 下半部分：内容区域（支持滚动）==========
        # 创建Canvas和Scrollbar用于滚动
        content_canvas = tk.Canvas(frame, bg=GlassTheme.GLASS_BG, highlightthickness=0)
        content_scrollbar = ttk.Scrollbar(frame, orient="vertical", command=content_canvas.yview)
        
        self._workbench_content_frame = ttk.Frame(content_canvas, style="TFrame")
        
        def on_content_frame_configure(event):
            content_canvas.configure(scrollregion=content_canvas.bbox("all"))
            content_canvas.itemconfig(content_window, width=content_canvas.winfo_width())
        
        self._workbench_content_frame.bind("<Configure>", on_content_frame_configure)
        content_window = content_canvas.create_window((0, 0), window=self._workbench_content_frame, anchor="nw")
        content_canvas.configure(yscrollcommand=content_scrollbar.set)
        
        # 鼠标滚轮绑定
        def on_content_mousewheel(event):
            content_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        def bind_content_mousewheel(event):
            content_canvas.bind_all("<MouseWheel>", on_content_mousewheel)
        
        def unbind_content_mousewheel(event):
            content_canvas.unbind_all("<MouseWheel>")
        
        content_canvas.bind("<Enter>", bind_content_mousewheel)
        content_canvas.bind("<Leave>", unbind_content_mousewheel)
        
        content_canvas.pack(side="left", fill="both", expand=True, padx=20, pady=(0, 20))
        content_scrollbar.pack(side="right", fill="y", pady=(0, 20))
        
        # 初始化所有标签页内容（延迟创建）
        self._workbench_tabs = {}
        self._workbench_tabs_created = set()
        
        # 默认显示世界观页面
        self._create_all_workbench_tabs()
        self._switch_workbench_tab("worldview")
        
        return frame
    
    def _create_all_workbench_tabs(self):
        """预创建工作台标签页（延迟创建策略，仅初始化为None）"""
        # 所有标签页初始化为None，首次切换时才创建
        # 这样可以避免首次点击工作台时一次性创建所有标签页导致卡顿
        for tab_id in ["worldview", "characters", "outline", "style", 
                       "generation", "reverse", "quick", "continue"]:
            self._workbench_tabs[tab_id] = None
    
    def _switch_workbench_tab(self, tab_id: str):
        """切换工作台标签页（延迟创建）"""
        # 更新按钮样式
        self._current_workbench_tab.set(tab_id)
        for tid, btn in self._workbench_buttons.items():
            if tid == tab_id:
                # 激活状态：使用对应颜色
                color = self._get_button_color(tid)
                btn.configure(bg=color, fg="white")
            else:
                btn.configure(bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        
        # 隐藏所有标签页
        for tid, tab_frame in self._workbench_tabs.items():
            if tid != tab_id and tab_frame is not None:
                tab_frame.pack_forget()
        
        # 延迟创建：首次切换时才创建标签页内容
        if self._workbench_tabs.get(tab_id) is None:
            create_method = {
                "worldview": self._create_worldview_content,
                "characters": self._create_characters_content,
                "outline": self._create_outline_content,
                "style": self._create_style_content,
                "generation": self._create_generation_content,
                "reverse": self._create_reverse_content,
                "quick": self._create_quick_content,
                "continue": self._create_continue_content,
            }.get(tab_id)
            if create_method:
                self._workbench_tabs[tab_id] = create_method()
        
        # 显示当前标签页
        if self._workbench_tabs.get(tab_id) is not None:
            self._workbench_tabs[tab_id].pack(fill=tk.BOTH, expand=True, in_=self._workbench_content_frame)
    
    def _update_button_style(self, tab_id: str):
        """更新按钮样式（用于鼠标离开时）"""
        if self._current_workbench_tab.get() != tab_id:
            self._workbench_buttons[tab_id].configure(bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
    
    def _get_button_color(self, tab_id: str) -> str:
        """获取按钮对应的颜色"""
        colors = {
            "worldview": GlassTheme.ACCENT_PURPLE,
            "characters": GlassTheme.ACCENT_PINK,
            "outline": GlassTheme.PRIMARY_LIGHT,
            "style": GlassTheme.ACCENT_GREEN,
            "generation": GlassTheme.PRIMARY,
            "reverse": GlassTheme.WARNING,
            "quick": GlassTheme.ACCENT_RED,
            "continue": GlassTheme.INFO,
        }
        return colors.get(tab_id, GlassTheme.PRIMARY)
    
    def _create_worldview_content(self) -> tk.Frame:
        """创建世界观管理内容页面"""
        frame = ttk.Frame(self._workbench_content_frame, style="TFrame")
        
        # 上部：文件导入区
        file_frame = ttk.LabelFrame(frame, text="世界观文件导入", padding=10)
        file_frame.pack(fill=tk.X, padx=5, pady=5)
        
        path_frame = ttk.Frame(file_frame, style="TFrame")
        path_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(path_frame, text="选择文件：").pack(side=tk.LEFT)
        self._worldview_path_var = tk.StringVar()
        ttk.Entry(path_frame, textvariable=self._worldview_path_var, width=50).pack(side=tk.LEFT, padx=10)
        ttk.Button(path_frame, text="浏览", command=self._on_worldview_browse).pack(side=tk.LEFT)
        ttk.Button(path_frame, text="新建", command=self._on_worldview_new).pack(side=tk.LEFT, padx=5)
        
        # 支持格式说明
        ttk.Label(file_frame, text="支持格式：TXT / DOCX", 
                 font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL),
                 foreground=GlassTheme.TEXT_SECONDARY).pack(anchor=tk.W, pady=5)
        
        # 中部：世界观列表
        list_frame = ttk.LabelFrame(frame, text="世界观项目列表", padding=10)
        list_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 创建带滚动条的Treeview容器
        tree_container = ttk.Frame(list_frame)
        tree_container.pack(fill=tk.X, pady=5)
        
        # 滚动条
        worldview_scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL)
        worldview_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ("name", "category", "elements", "status", "modified")
        self._worldview_tree = ttk.Treeview(tree_container, columns=columns, show="headings", height=4, yscrollcommand=worldview_scrollbar.set)
        self._worldview_tree.heading("name", text="世界观名称")
        self._worldview_tree.heading("category", text="世界观类别")
        self._worldview_tree.heading("elements", text="核心元素")
        self._worldview_tree.heading("status", text="状态")
        self._worldview_tree.heading("modified", text="修改时间")
        self._worldview_tree.column("name", width=120)
        self._worldview_tree.column("category", width=80)
        self._worldview_tree.column("elements", width=160)
        self._worldview_tree.column("status", width=80)
        self._worldview_tree.column("modified", width=110)
        self._worldview_tree.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 配置滚动条
        worldview_scrollbar.config(command=self._worldview_tree.yview)
        
        # 鼠标滚轮支持
        def _on_worldview_mousewheel(event):
            self._worldview_tree.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        self._worldview_tree.bind("<MouseWheel>", _on_worldview_mousewheel)

        list_btn_frame = ttk.Frame(list_frame, style="TFrame")
        list_btn_frame.pack(fill=tk.X, pady=5)
        
        # 使用Grid布局，3列，确保按钮均匀分布
        list_buttons = [
            ("查看详情", self._on_worldview_view),
            ("编辑", self._on_worldview_edit),
            ("批量删除", self._on_worldview_delete),
        ]
        
        for i, (text, command) in enumerate(list_buttons):
            btn = ttk.Button(list_btn_frame, text=text, command=command)
            btn.grid(row=0, column=i, padx=5, pady=2, sticky="ew")
        
        # 配置列权重，确保按钮均匀分布
        for i in range(3):
            list_btn_frame.grid_columnconfigure(i, weight=1)

        # 下部：预览区
        preview_frame = ttk.LabelFrame(frame, text="世界观详情预览", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self._worldview_preview = tk.Text(preview_frame, wrap=tk.WORD, height=10,
                                         font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                                         bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        self._worldview_preview.pack(fill=tk.BOTH, expand=True)

        # 底部按钮
        btn_frame = ttk.Frame(frame, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        # 使用Grid布局，3列，确保按钮均匀分布
        bottom_buttons = [
            ("导入世界观", self._on_worldview_import),
            ("关联要素", self._on_worldview_link),
            ("清除", self._on_worldview_clear),
        ]
        
        for i, (text, command) in enumerate(bottom_buttons):
            btn = ttk.Button(btn_frame, text=text, command=command)
            btn.grid(row=0, column=i, padx=5, pady=2, sticky="ew")
        
        # 配置列权重，确保按钮均匀分布
        for i in range(3):
            btn_frame.grid_columnconfigure(i, weight=1)

        return frame
    
    def _create_characters_content(self) -> tk.Frame:
        """创建人物设定内容页面"""
        frame = ttk.Frame(self._workbench_content_frame, style="TFrame")
        
        # 上部：人物导入区
        file_frame = ttk.LabelFrame(frame, text="人物档案导入", padding=10)
        file_frame.pack(fill=tk.X, padx=5, pady=5)
        
        path_frame = ttk.Frame(file_frame, style="TFrame")
        path_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(path_frame, text="选择文件：").pack(side=tk.LEFT)
        self._character_path_var = tk.StringVar()
        ttk.Entry(path_frame, textvariable=self._character_path_var, width=50).pack(side=tk.LEFT, padx=10)
        ttk.Button(path_frame, text="浏览", command=self._on_character_browse).pack(side=tk.LEFT)
        ttk.Button(path_frame, text="新建人物", command=self._on_character_new).pack(side=tk.LEFT, padx=5)
        ttk.Button(path_frame, text="批量解析导入", command=self._on_character_batch_import).pack(side=tk.LEFT, padx=5)
        
        # 中部：人物列表区
        list_frame = ttk.LabelFrame(frame, text="人物列表", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 创建带滚动条的Treeview容器
        tree_container = ttk.Frame(list_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)
        
        # 滚动条
        character_scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL)
        character_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 列表（移除头像列，情绪改为情感状态）
        columns = ("name", "role", "status", "emotion", "chapters")
        self._character_tree = ttk.Treeview(tree_container, columns=columns, show="headings", height=8, yscrollcommand=character_scrollbar.set)
        self._character_tree.heading("name", text="姓名")
        self._character_tree.heading("role", text="角色类型")
        self._character_tree.heading("status", text="状态")
        self._character_tree.heading("emotion", text="情感状态")
        self._character_tree.heading("chapters", text="出场章节")
        self._character_tree.column("name", width=120)
        self._character_tree.column("role", width=100)
        self._character_tree.column("status", width=80)
        self._character_tree.column("emotion", width=100)
        self._character_tree.column("chapters", width=100)
        self._character_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 配置滚动条
        character_scrollbar.config(command=self._character_tree.yview)
        
        # 鼠标滚轮支持
        def _on_character_mousewheel(event):
            self._character_tree.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        self._character_tree.bind("<MouseWheel>", _on_character_mousewheel)
        
        # 列表操作按钮
        list_btn_frame = ttk.Frame(list_frame, style="TFrame")
        list_btn_frame.pack(fill=tk.X, pady=5)

        # 使用Grid布局，4列，确保按钮均匀分布
        list_buttons = [
            ("编辑人物", self._on_character_edit),
            ("人物详情", self._on_character_detail),
            ("关系图谱", self._on_character_relation),
            ("删除人物", self._on_character_delete),
        ]
        
        for i, (text, command) in enumerate(list_buttons):
            btn = ttk.Button(list_btn_frame, text=text, command=command)
            btn.grid(row=0, column=i, padx=5, pady=2, sticky="ew")
        
        # 配置列权重，确保按钮均匀分布
        for i in range(4):
            list_btn_frame.grid_columnconfigure(i, weight=1)

        # 下部：人物详情预览
        detail_frame = ttk.LabelFrame(frame, text="人物档案详情", padding=10)
        detail_frame.pack(fill=tk.X, padx=5, pady=5)

        self._character_detail = tk.Text(detail_frame, wrap=tk.WORD, height=6,
                                        font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                                        bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        self._character_detail.pack(fill=tk.BOTH, expand=True)

        return frame
    
    def _create_outline_content(self) -> tk.Frame:
        """创建大纲管理内容页面"""
        frame = ttk.Frame(self._workbench_content_frame, style="TFrame")
        
        # 上部：文件导入区
        file_frame = ttk.LabelFrame(frame, text="大纲文件导入", padding=10)
        file_frame.pack(fill=tk.X, padx=5, pady=5)
        
        path_frame = ttk.Frame(file_frame, style="TFrame")
        path_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(path_frame, text="当前大纲：").pack(side=tk.LEFT)
        self._outline_path_var = tk.StringVar(value="未导入")
        ttk.Label(path_frame, textvariable=self._outline_path_var, 
                 foreground=GlassTheme.TEXT_LINK).pack(side=tk.LEFT, padx=10)
        ttk.Button(path_frame, text="选择文件", command=self._on_outline_browse).pack(side=tk.LEFT)
        ttk.Button(path_frame, text="新建大纲", command=self._on_outline_new).pack(side=tk.LEFT, padx=5)
        ttk.Button(path_frame, text="导出", command=self._on_outline_export).pack(side=tk.RIGHT)
        
        # 中部：大纲树形结构
        tree_frame = ttk.LabelFrame(frame, text="大纲结构（可拖拽排序）", padding=10)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self._outline_tree = ttk.Treeview(tree_frame, show="tree", height=8)
        self._outline_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._outline_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._outline_tree.configure(yscrollcommand=scrollbar.set)
        
        # 树形结构操作按钮
        tree_btn_frame = ttk.Frame(tree_frame, style="TFrame")
        tree_btn_frame.pack(fill=tk.X, pady=5, side=tk.BOTTOM)
        
        # 使用Grid布局，4列，确保按钮均匀分布
        tree_buttons = [
            ("添加卷", self._on_outline_add_volume),
            ("添加章节", self._on_outline_add_chapter),
            ("编辑章节", self._on_outline_edit_chapter),
            ("删除", self._on_outline_delete),
        ]
        
        for i, (text, command) in enumerate(tree_buttons):
            btn = ttk.Button(tree_btn_frame, text=text, command=command)
            btn.grid(row=0, column=i, padx=5, pady=2, sticky="ew")
        
        # 配置列权重，确保按钮均匀分布
        for i in range(4):
            tree_btn_frame.grid_columnconfigure(i, weight=1)
        
        # 下部：章节编辑器
        editor_frame = ttk.LabelFrame(frame, text="章节编辑器", padding=10)
        editor_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 章节信息
        info_row = ttk.Frame(editor_frame, style="TFrame")
        info_row.pack(fill=tk.X, pady=5)
        ttk.Label(info_row, text="章节标题：").pack(side=tk.LEFT)
        self._chapter_title_var = tk.StringVar()
        ttk.Entry(info_row, textvariable=self._chapter_title_var, width=30).pack(side=tk.LEFT, padx=5)
        ttk.Label(info_row, text="目标字数：").pack(side=tk.LEFT, padx=(20, 0))
        self._chapter_words_var = tk.StringVar(value="2000")
        ttk.Spinbox(info_row, from_=500, to=5000, increment=100, width=10, textvariable=self._chapter_words_var).pack(side=tk.LEFT, padx=5)
        
        # 章节摘要
        ttk.Label(editor_frame, text="内容摘要：").pack(anchor=tk.W, pady=5)
        self._chapter_summary = tk.Text(editor_frame, wrap=tk.WORD, height=3,
                                       font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                                       bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        self._chapter_summary.pack(fill=tk.X)
        
        # 进度条
        progress_frame = ttk.Frame(frame, style="TFrame")
        progress_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(progress_frame, text="大纲完成进度：").pack(side=tk.LEFT)
        self._outline_progress = ttk.Progressbar(progress_frame, length=300, mode='determinate')
        self._outline_progress.pack(side=tk.LEFT, padx=10)
        ttk.Label(progress_frame, text="0/0 章节").pack(side=tk.LEFT)
        
        # 按钮
        btn_frame = ttk.Frame(frame, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        # 使用Grid布局，2列，确保按钮均匀分布
        outline_buttons = [
            ("解析大纲", self._on_outline_parse),
            ("清除大纲", self._on_outline_clear),
        ]
        
        for i, (text, command) in enumerate(outline_buttons):
            btn = ttk.Button(btn_frame, text=text, command=command)
            btn.grid(row=0, column=i, padx=5, pady=2, sticky="ew")
        
        # 配置列权重，确保按钮均匀分布
        for i in range(2):
            btn_frame.grid_columnconfigure(i, weight=1)

        return frame
    
    def _create_style_content(self) -> tk.Frame:
        """创建风格学习内容页面"""
        frame = ttk.Frame(self._workbench_content_frame, style="TFrame")
        
        # 上部：范文管理区
        file_frame = ttk.LabelFrame(frame, text="范文管理", padding=10)
        file_frame.pack(fill=tk.X, padx=5, pady=5)
        
        path_frame = ttk.Frame(file_frame, style="TFrame")
        path_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(path_frame, text="当前风格：").pack(side=tk.LEFT)
        self._style_path_var = tk.StringVar(value="未导入")
        ttk.Label(path_frame, textvariable=self._style_path_var,
                 foreground=GlassTheme.TEXT_LINK).pack(side=tk.LEFT, padx=10)
        ttk.Button(path_frame, text="上传范文", command=self._on_style_browse).pack(side=tk.LEFT)
        ttk.Button(path_frame, text="删除范文", command=self._on_style_delete).pack(side=tk.LEFT, padx=5)
        ttk.Button(path_frame, text="解析风格", command=self._on_style_analyze).pack(side=tk.LEFT, padx=5)
        ttk.Button(path_frame, text="导出风格", command=self._on_style_export).pack(side=tk.RIGHT)
        
        # 中部左：风格档案库
        library_frame = ttk.LabelFrame(frame, text="风格档案库", padding=10)
        library_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5, side=tk.LEFT)
        
        columns = ("name", "vocabulary", "sentence", "rhetoric", "emotion", "rhythm", "structure", "detail")
        self._style_tree = ttk.Treeview(library_frame, columns=columns, show="headings", height=8)
        self._style_tree.heading("name", text="风格名称")
        self._style_tree.heading("vocabulary", text="词汇")
        self._style_tree.heading("sentence", text="句式")
        self._style_tree.heading("rhetoric", text="修辞")
        self._style_tree.heading("emotion", text="情感")
        self._style_tree.heading("rhythm", text="节奏")
        self._style_tree.heading("structure", text="结构")
        self._style_tree.heading("detail", text="细节")
        self._style_tree.column("name", width=100)
        for col in columns[1:]:
            self._style_tree.column(col, width=50)
        self._style_tree.pack(fill=tk.BOTH, expand=True)
        
        # 档案库按钮
        lib_btn_frame = ttk.Frame(library_frame, style="TFrame")
        lib_btn_frame.pack(fill=tk.X, pady=5)

        # 使用Grid布局，3列，确保按钮均匀分布
        lib_buttons = [
            ("切换风格", self._on_style_switch),
            ("编辑权重", self._on_style_edit_weight),
            ("删除风格", self._on_style_delete_profile),
        ]
        
        for i, (text, command) in enumerate(lib_buttons):
            btn = ttk.Button(lib_btn_frame, text=text, command=command)
            btn.grid(row=0, column=i, padx=5, pady=2, sticky="ew")
        
        # 配置列权重，确保按钮均匀分布
        for i in range(3):
            lib_btn_frame.grid_columnconfigure(i, weight=1)

        # 中部右：风格分析器结果
        analyzer_frame = ttk.LabelFrame(frame, text="风格分析器（七维度评分）", padding=10)
        analyzer_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5, side=tk.RIGHT)

        self._style_info = tk.Text(analyzer_frame, wrap=tk.WORD, height=10,
                                  font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                                  bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        self._style_info.pack(fill=tk.BOTH, expand=True)

        # 底部：创建风格按钮
        create_frame = ttk.Frame(frame, style="TFrame")
        create_frame.pack(fill=tk.X, padx=5, pady=5)

        # 使用Grid布局，4列，确保按钮均匀分布
        create_buttons = [
            ("深度学习", self._on_style_learn),
            ("创建风格模板", self._on_style_create),
            ("应用到生成器", self._on_style_apply),
            ("清除风格", self._on_style_clear),
        ]
        
        for i, (text, command) in enumerate(create_buttons):
            btn = ttk.Button(create_frame, text=text, command=command)
            btn.grid(row=0, column=i, padx=5, pady=2, sticky="ew")
        
        # 配置列权重，确保按钮均匀分布
        for i in range(4):
            create_frame.grid_columnconfigure(i, weight=1)

        return frame
    
    def _create_generation_content(self) -> tk.Frame:
        """创建开始创作内容页面"""
        frame = ttk.Frame(self._workbench_content_frame, style="TFrame")
        
        # 上部：生成配置
        config_frame = ttk.LabelFrame(frame, text="生成配置", padding=10)
        config_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 第一行：风格选择和章节范围
        row1 = ttk.Frame(config_frame, style="TFrame")
        row1.pack(fill=tk.X, pady=5)
        ttk.Label(row1, text="选择风格：").pack(side=tk.LEFT)
        self._gen_style_var = tk.StringVar(value="默认风格")
        ttk.Combobox(row1, textvariable=self._gen_style_var, width=20, values=["默认风格", "武侠风", "言情风", "科幻风"]).pack(side=tk.LEFT, padx=5)
        ttk.Label(row1, text="起始章节：").pack(side=tk.LEFT, padx=(20, 0))
        self._start_chapter_var = tk.StringVar(value="1")
        ttk.Spinbox(row1, from_=1, to=100, width=8, textvariable=self._start_chapter_var).pack(side=tk.LEFT, padx=5)
        ttk.Label(row1, text="结束章节：").pack(side=tk.LEFT)
        self._end_chapter_var = tk.StringVar(value="1")
        ttk.Spinbox(row1, from_=1, to=100, width=8, textvariable=self._end_chapter_var).pack(side=tk.LEFT, padx=5)
        
        # 第二行：字数和温度
        row2 = ttk.Frame(config_frame, style="TFrame")
        row2.pack(fill=tk.X, pady=5)
        ttk.Label(row2, text="目标字数/章：").pack(side=tk.LEFT)
        self._target_words_var = tk.StringVar(value="900")
        ttk.Spinbox(row2, from_=500, to=2000, increment=100, width=10, textvariable=self._target_words_var).pack(side=tk.LEFT, padx=5)
        ttk.Label(row2, text="生成温度：").pack(side=tk.LEFT, padx=(20, 0))
        self._gen_temp_var = tk.DoubleVar(value=0.7)
        ttk.Scale(row2, from_=0.0, to=1.0, variable=self._gen_temp_var, orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT, padx=5)
        ttk.Label(row2, textvariable=self._gen_temp_var).pack(side=tk.LEFT)
        
        # 第三行：出场人物
        row3 = ttk.Frame(config_frame, style="TFrame")
        row3.pack(fill=tk.X, pady=5)
        ttk.Label(row3, text="出场人物：").pack(side=tk.LEFT)
        self._gen_characters_var = tk.StringVar(value="自动设置")
        ttk.Entry(row3, textvariable=self._gen_characters_var, width=40).pack(side=tk.LEFT, padx=5)
        ttk.Label(row3, text="(可手动输入添加)", font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL),
                 foreground=GlassTheme.TEXT_SECONDARY).pack(side=tk.LEFT)
        
        # 第四行：生成模式
        row4 = ttk.Frame(config_frame, style="TFrame")
        row4.pack(fill=tk.X, pady=5)
        ttk.Label(row4, text="生成模式：").pack(side=tk.LEFT)
        self._gen_mode_var = tk.StringVar(value="auto")
        ttk.Radiobutton(row4, text="自动迭代", variable=self._gen_mode_var, value="auto").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(row4, text="手动迭代", variable=self._gen_mode_var, value="manual").pack(side=tk.LEFT, padx=10)
        
        # 中部：左右分栏（生成过程 + 生成结果）
        middle_split_frame = ttk.Frame(frame, style="TFrame")
        middle_split_frame.pack(fill=tk.BOTH, expand=False, padx=5, pady=5)  # 改为expand=False，给底部按钮留空间

        # 使用grid布局让左右等分宽度
        middle_split_frame.grid_columnconfigure(0, weight=1)
        middle_split_frame.grid_columnconfigure(1, weight=1)

        # 左侧：生成过程展示
        process_frame = ttk.LabelFrame(middle_split_frame, text="生成过程", padding=10)
        process_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # 进度状态
        status_frame = ttk.Frame(process_frame, style="TFrame")
        status_frame.pack(fill=tk.X, pady=5)
        self._gen_status_var = tk.StringVar(value="准备就绪")
        ttk.Label(status_frame, textvariable=self._gen_status_var, font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL, "bold")).pack(side=tk.LEFT)
        ttk.Label(status_frame, text="当前章节：第1章").pack(side=tk.RIGHT)

        # 进度条
        self._gen_progress = ttk.Progressbar(process_frame, length=400, mode='determinate')
        self._gen_progress.pack(fill=tk.X, pady=5)

        # Agent状态列表（新增）
        agent_frame = ttk.Frame(process_frame, style="TFrame")
        agent_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(agent_frame, text="Agent状态：", font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL)).pack(anchor=tk.W)
        
        # Agent状态树形视图
        agent_list_frame = ttk.Frame(agent_frame, style="TFrame")
        agent_list_frame.pack(fill=tk.X, pady=2)
        
        self._gen_agent_tree = ttk.Treeview(
            agent_list_frame,
            columns=("status", "info"),
            show="headings",
            height=3
        )
        self._gen_agent_tree.heading("status", text="状态")
        self._gen_agent_tree.heading("info", text="信息")
        self._gen_agent_tree.column("status", width=80)
        self._gen_agent_tree.column("info", width=300)
        self._gen_agent_tree.pack(fill=tk.X, side=tk.LEFT)
        
        # Agent状态滚动条
        agent_scroll = ttk.Scrollbar(agent_list_frame, orient=tk.VERTICAL, command=self._gen_agent_tree.yview)
        agent_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._gen_agent_tree.configure(yscrollcommand=agent_scroll.set)

        # 日志输出（带滚动条，固定高度）
        log_scroll = ttk.Scrollbar(process_frame, orient=tk.VERTICAL)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._gen_log = tk.Text(process_frame, wrap=tk.WORD, height=10,
                               font=(GlassTheme.FONT_FAMILY_CODE, GlassTheme.FONT_SIZE_SMALL),
                               bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY,
                               yscrollcommand=log_scroll.set)
        self._gen_log.pack(fill=tk.BOTH, expand=True)
        log_scroll.configure(command=self._gen_log.yview)

        # 右侧：生成结果展示（带滚动条，固定高度）
        result_frame = ttk.LabelFrame(middle_split_frame, text="生成结果预览", padding=10)
        result_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        result_scroll = ttk.Scrollbar(result_frame, orient=tk.VERTICAL)
        result_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._gen_result = tk.Text(result_frame, wrap=tk.WORD, height=10,
                                  font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                                  bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY,
                                  yscrollcommand=result_scroll.set)
        self._gen_result.pack(fill=tk.BOTH, expand=True)
        result_scroll.configure(command=self._gen_result.yview)

        # 底部按钮
        btn_frame = ttk.Frame(frame, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        # 使用Grid布局，5列，确保按钮均匀分布
        buttons = [
            ("保存结果", self._on_gen_save_result),
            ("开始生成", self._on_start_generation),
            ("停止生成", self._on_stop_generation),
            ("分章浏览", self._on_gen_browse),
            ("保存项目", self._on_gen_save),
        ]

        for i, (text, command) in enumerate(buttons):
            btn = ttk.Button(btn_frame, text=text, command=command)
            btn.grid(row=0, column=i, padx=5, pady=2, sticky="ew")

        # 配置列权重，确保按钮均匀分布
        for i in range(5):
            btn_frame.grid_columnconfigure(i, weight=1)

        return frame

    def _on_gen_save_result(self):
        """保存生成结果"""
        try:
            from tkinter import messagebox

            content = self._gen_result.get("1.0", tk.END).strip()

            if not content:
                messagebox.showwarning("提示", "没有可保存的内容！")
                return

            from tkinter import filedialog

            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
                title="保存生成结果"
            )

            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                messagebox.showinfo("成功", "生成结果已保存！")
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("错误", f"保存失败：{str(e)}")
        ttk.Button(btn_frame, text="导出TXT", command=self._on_gen_export_txt).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="导出DOCX", command=self._on_gen_export_docx).pack(side=tk.LEFT, padx=5)
        
        return frame
    
    def _create_reverse_content(self) -> tk.Frame:
        """创建逆向反馈内容页面（V2.5重构版）
        
        功能：
        - 章节上传区域（支持单个/批量上传文件或粘贴文本）
        - 章节列表显示（含字数、状态）
        - 删除按钮（从项目文件中删除章节）
        - "运行分析"按钮（调用逆向反馈分析插件）
        - 分析结果展示区（冲突列表，带修正建议）
        - "应用修正"按钮（调用设定修正生成器，更新当前项目设定）
        """
        frame = ttk.Frame(self._workbench_content_frame, style="TFrame")
        
        # 初始化章节数据存储
        self._reverse_chapters = {}  # 章节ID -> {title, content, words, status, file_path}
        self._reverse_analysis_result = None  # 分析结果缓存
        self._reverse_selected_issues = []  # 选中的冲突项
        
        # ==================== 上部：章节上传区域 ====================
        upload_frame = ttk.LabelFrame(frame, text="章节上传", padding=10)
        upload_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 上传方式说明
        ttk.Label(upload_frame, text="支持单个/批量上传TXT/DOCX文件，或直接粘贴文本：", 
                  font=('Microsoft YaHei UI', 9)).pack(anchor=tk.W, pady=2)
        
        # 上传按钮行
        upload_btn_row = ttk.Frame(upload_frame, style="TFrame")
        upload_btn_row.pack(fill=tk.X, pady=5)
        
        ttk.Button(upload_btn_row, text="📁 上传文件", command=self._on_reverse_upload_files, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(upload_btn_row, text="📁 批量上传", command=self._on_reverse_batch_upload, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(upload_btn_row, text="📋 粘贴文本", command=self._on_reverse_paste_text, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(upload_btn_row, text="🔄 刷新列表", command=self._on_reverse_refresh_chapters, width=12).pack(side=tk.LEFT, padx=2)
        
        # 粘贴文本区域（可折叠，默认隐藏）
        self._paste_text_frame = ttk.Frame(upload_frame, style="TFrame")
        self._paste_text_frame.pack(fill=tk.X, pady=5)
        
        paste_title_row = ttk.Frame(self._paste_text_frame, style="TFrame")
        paste_title_row.pack(fill=tk.X)
        
        ttk.Label(paste_title_row, text="章节标题：").pack(side=tk.LEFT)
        self._paste_title_var = tk.StringVar()
        ttk.Entry(paste_title_row, textvariable=self._paste_title_var, width=40).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(self._paste_text_frame, text="章节内容：").pack(anchor=tk.W)
        
        paste_content_frame = ttk.Frame(self._paste_text_frame, style="TFrame")
        paste_content_frame.pack(fill=tk.X, pady=2)
        
        self._paste_content_text = tk.Text(paste_content_frame, wrap=tk.WORD, height=4,
                                           font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                                           bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        self._paste_content_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        paste_scroll = ttk.Scrollbar(paste_content_frame, orient=tk.VERTICAL, command=self._paste_content_text.yview)
        paste_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._paste_content_text.configure(yscrollcommand=paste_scroll.set)
        
        ttk.Button(self._paste_text_frame, text="✅ 添加章节", command=self._on_reverse_add_pasted_chapter).pack(anchor=tk.E, pady=5)
        
        # 默认隐藏粘贴区域
        self._paste_text_frame.pack_forget()
        
        # ==================== 中部：左右分栏布局 ====================
        middle_frame = ttk.Frame(frame, style="TFrame")
        middle_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # ========== 中部左：章节列表 ==========
        chapters_frame = ttk.LabelFrame(middle_frame, text="章节列表", padding=10)
        chapters_frame.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=(0, 5))
        
        # 章节列表（带滚动条）
        chapters_list_frame = ttk.Frame(chapters_frame, style="TFrame")
        chapters_list_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ("id", "title", "words", "status", "source")
        self._completed_chapters_tree = ttk.Treeview(chapters_list_frame, columns=columns, show="headings", height=10)
        self._completed_chapters_tree.heading("id", text="序号")
        self._completed_chapters_tree.heading("title", text="标题")
        self._completed_chapters_tree.heading("words", text="字数")
        self._completed_chapters_tree.heading("status", text="状态")
        self._completed_chapters_tree.heading("source", text="来源")
        self._completed_chapters_tree.column("id", width=50)
        self._completed_chapters_tree.column("title", width=180)
        self._completed_chapters_tree.column("words", width=70)
        self._completed_chapters_tree.column("status", width=70)
        self._completed_chapters_tree.column("source", width=80)
        self._completed_chapters_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        # 滚动条
        chapters_scroll = ttk.Scrollbar(chapters_list_frame, orient=tk.VERTICAL, command=self._completed_chapters_tree.yview)
        chapters_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._completed_chapters_tree.configure(yscrollcommand=chapters_scroll.set)
        
        # 绑定选择事件
        self._completed_chapters_tree.bind("<<TreeviewSelect>>", self._on_reverse_chapter_select)
        
        # 右键菜单
        self._chapters_context_menu = tk.Menu(self._completed_chapters_tree, tearoff=0)
        self._chapters_context_menu.add_command(label="✅ 标记为完成", command=lambda: self._on_mark_chapter_completed())
        self._chapters_context_menu.add_command(label="⏳ 标记为未完成", command=lambda: self._on_mark_chapter_incomplete())
        self._chapters_context_menu.add_separator()
        self._chapters_context_menu.add_command(label="👁️ 查看内容", command=self._on_reverse_view_chapter)
        self._chapters_context_menu.add_command(label="🗑️ 删除章节", command=lambda: self._on_delete_completed_chapter())
        self._completed_chapters_tree.bind("<Button-3>", self._show_chapters_context_menu)
        
        # 章节列表按钮行
        chapters_btn_frame = ttk.Frame(chapters_frame, style="TFrame")
        chapters_btn_frame.pack(fill=tk.X, pady=5)
        
        chapters_buttons = [
            ("删除选中", self._on_delete_completed_chapter),
            ("全部标记完成", self._on_mark_all_completed),
            ("清空列表", self._on_reverse_clear_chapters),
        ]
        
        for i, (text, command) in enumerate(chapters_buttons):
            btn = ttk.Button(chapters_btn_frame, text=text, command=command, width=12)
            btn.grid(row=0, column=i, padx=3, pady=2, sticky="ew")
        
        for i in range(3):
            chapters_btn_frame.grid_columnconfigure(i, weight=1)
        
        # ========== 中部右：分析配置 ==========
        config_frame = ttk.LabelFrame(middle_frame, text="分析配置", padding=10)
        config_frame.pack(fill=tk.BOTH, expand=True, side=tk.RIGHT, padx=(5, 0))
        
        # 分析维度
        ttk.Label(config_frame, text="分析维度：", font=('Microsoft YaHei UI', 9, 'bold')).pack(anchor=tk.W, pady=5)
        
        self._reverse_check_consistency = tk.BooleanVar(value=True)
        self._reverse_check_logic = tk.BooleanVar(value=True)
        self._reverse_check_character = tk.BooleanVar(value=True)
        self._reverse_check_style = tk.BooleanVar(value=True)
        self._reverse_check_worldview = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(config_frame, text="✓ 一致性检查（章节间逻辑一致性）", 
                        variable=self._reverse_check_consistency).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(config_frame, text="✓ 逻辑漏洞检测（情节合理性）", 
                        variable=self._reverse_check_logic).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(config_frame, text="✓ 人设偏离检测（角色行为一致性）", 
                        variable=self._reverse_check_character).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(config_frame, text="✓ 风格匹配度（写作风格一致性）", 
                        variable=self._reverse_check_style).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(config_frame, text="✓ 世界观冲突（设定一致性）", 
                        variable=self._reverse_check_worldview).pack(anchor=tk.W, pady=2)
        
        ttk.Separator(config_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # 分析范围
        ttk.Label(config_frame, text="分析范围：", font=('Microsoft YaHei UI', 9, 'bold')).pack(anchor=tk.W, pady=5)
        
        self._reverse_scope_var = tk.StringVar(value="selected")
        ttk.Radiobutton(config_frame, text="仅分析选中章节", variable=self._reverse_scope_var, 
                        value="selected").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(config_frame, text="分析所有已完成章节", variable=self._reverse_scope_var, 
                        value="completed").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(config_frame, text="分析所有章节", variable=self._reverse_scope_var, 
                        value="all").pack(anchor=tk.W, pady=2)
        
        ttk.Separator(config_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # 运行分析按钮
        self._run_analysis_btn = ttk.Button(config_frame, text="🔍 运行分析", 
                                            command=self._on_reverse_run_analysis, width=15)
        self._run_analysis_btn.pack(anchor=tk.CENTER, pady=10)
        
        # 分析进度指示
        self._analysis_progress_frame = ttk.Frame(config_frame, style="TFrame")
        self._analysis_progress_frame.pack(fill=tk.X, pady=5)
        
        self._analysis_progress_label = ttk.Label(self._analysis_progress_frame, text="", 
                                                   foreground=GlassTheme.PRIMARY)
        self._analysis_progress_label.pack(anchor=tk.W)
        
        # ==================== 下部：分析结果展示 ====================
        result_frame = ttk.LabelFrame(frame, text="分析结果", padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 结果区域：左侧冲突列表，右侧修正建议
        result_paned = ttk.PanedWindow(result_frame, orient=tk.HORIZONTAL)
        result_paned.pack(fill=tk.BOTH, expand=True)
        
        # 左侧：冲突列表
        issues_frame = ttk.Frame(result_paned, style="TFrame")
        result_paned.add(issues_frame, weight=1)
        
        ttk.Label(issues_frame, text="冲突列表（双击查看详情）：", 
                  font=('Microsoft YaHei UI', 9)).pack(anchor=tk.W)
        
        issues_list_frame = ttk.Frame(issues_frame, style="TFrame")
        issues_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        issue_columns = ("type", "severity", "element", "chapter", "desc")
        self._issues_tree = ttk.Treeview(issues_list_frame, columns=issue_columns, show="headings", height=8)
        self._issues_tree.heading("type", text="类型")
        self._issues_tree.heading("severity", text="优先级")
        self._issues_tree.heading("element", text="元素")
        self._issues_tree.heading("chapter", text="章节")
        self._issues_tree.heading("desc", text="问题描述")
        self._issues_tree.column("type", width=80)
        self._issues_tree.column("severity", width=60)
        self._issues_tree.column("element", width=100)
        self._issues_tree.column("chapter", width=100)
        self._issues_tree.column("desc", width=200)
        self._issues_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        issues_scroll = ttk.Scrollbar(issues_list_frame, orient=tk.VERTICAL, command=self._issues_tree.yview)
        issues_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._issues_tree.configure(yscrollcommand=issues_scroll.set)
        
        # 绑定选择事件显示详情
        self._issues_tree.bind("<<TreeviewSelect>>", self._on_reverse_issue_select)
        self._issues_tree.bind("<Double-1>", self._on_reverse_issue_double_click)
        
        # 右侧：修正建议详情
        detail_frame = ttk.Frame(result_paned, style="TFrame")
        result_paned.add(detail_frame, weight=1)
        
        ttk.Label(detail_frame, text="修正建议：", 
                  font=('Microsoft YaHei UI', 9)).pack(anchor=tk.W)
        
        detail_text_frame = ttk.Frame(detail_frame, style="TFrame")
        detail_text_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self._issue_detail_text = tk.Text(detail_text_frame, wrap=tk.WORD, height=8,
                                          font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                                          bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        self._issue_detail_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        detail_scroll = ttk.Scrollbar(detail_text_frame, orient=tk.VERTICAL, command=self._issue_detail_text.yview)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._issue_detail_text.configure(yscrollcommand=detail_scroll.set)
        self._issue_detail_text.insert("1.0", "选择冲突项查看详细修正建议...")
        self._issue_detail_text.configure(state=tk.DISABLED)
        
        # ==================== 底部：操作按钮 ====================
        btn_frame = ttk.Frame(frame, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 操作按钮（4个核心按钮）
        action_buttons = [
            ("🔧 应用修正", self._on_reverse_apply_fix),
            ("📋 导出报告", self._on_reverse_export_report),
            ("🔄 重新分析", self._on_reverse_run_analysis),
            ("🗑️ 清除结果", self._on_reverse_clear_result),
        ]
        
        for i, (text, command) in enumerate(action_buttons):
            btn = ttk.Button(btn_frame, text=text, command=command, width=14)
            btn.grid(row=0, column=i, padx=5, pady=2, sticky="ew")
        
        for i in range(4):
            btn_frame.grid_columnconfigure(i, weight=1)
        
        return frame
    
    def _create_quick_content(self) -> tk.Frame:
        """创建快捷创作内容页面（一次性生成四个结果：世界观、大纲、人设、关键情节）"""
        # 直接在workbench内容区创建frame，不需要额外的Canvas
        frame = ttk.Frame(self._workbench_content_frame, style="TFrame")
        
        # 初始化上传文件列表
        self._quick_uploaded_files = []  # 存储上传的文件列表 [{path, type, content}]

        # 上部：参考文本上传区（增强版）
        upload_frame = ttk.LabelFrame(frame, text="参考文本上传（可选，支持多个文件）", padding=10)
        upload_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 说明文字
        ttk.Label(upload_frame, text="上传参考文本或已有设定，系统将分析并作为生成依据：", 
                 font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL)).pack(anchor=tk.W, pady=5)
        
        # 文件上传按钮组
        upload_btn_frame = ttk.Frame(upload_frame, style="TFrame")
        upload_btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(upload_btn_frame, text="📄 上传世界观参考", width=18,
                  command=lambda: self._on_quick_upload_file("worldview")).pack(side=tk.LEFT, padx=5)
        ttk.Button(upload_btn_frame, text="📋 上传大纲参考", width=18,
                  command=lambda: self._on_quick_upload_file("outline")).pack(side=tk.LEFT, padx=5)
        ttk.Button(upload_btn_frame, text="👤 上传人设参考", width=18,
                  command=lambda: self._on_quick_upload_file("characters")).pack(side=tk.LEFT, padx=5)
        ttk.Button(upload_btn_frame, text="📖 上传情节参考", width=18,
                  command=lambda: self._on_quick_upload_file("plot")).pack(side=tk.LEFT, padx=5)
        ttk.Button(upload_btn_frame, text="🗑️ 清空全部", width=12,
                  command=self._on_quick_clear_uploads).pack(side=tk.LEFT, padx=5)
        
        # 已上传文件列表（Treeview）
        upload_list_frame = ttk.Frame(upload_frame, style="TFrame")
        upload_list_frame.pack(fill=tk.X, pady=5)
        
        columns = ("文件名", "类型", "字数", "状态")
        self._quick_upload_tree = ttk.Treeview(upload_list_frame, columns=columns, show="headings", height=3)
        
        self._quick_upload_tree.heading("文件名", text="文件名")
        self._quick_upload_tree.heading("类型", text="类型")
        self._quick_upload_tree.heading("字数", text="字数")
        self._quick_upload_tree.heading("状态", text="状态")
        
        self._quick_upload_tree.column("文件名", width=200)
        self._quick_upload_tree.column("类型", width=80, anchor=tk.CENTER)
        self._quick_upload_tree.column("字数", width=80, anchor=tk.CENTER)
        self._quick_upload_tree.column("状态", width=80, anchor=tk.CENTER)
        
        # 添加滚动条
        tree_scroll = ttk.Scrollbar(upload_list_frame, orient="vertical", command=self._quick_upload_tree.yview)
        self._quick_upload_tree.configure(yscrollcommand=tree_scroll.set)
        
        self._quick_upload_tree.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 右键菜单（删除单个文件）
        self._quick_upload_menu = tk.Menu(self._quick_upload_tree, tearoff=0)
        self._quick_upload_menu.add_command(label="删除此文件", command=self._on_quick_remove_upload)
        self._quick_upload_tree.bind("<Button-3>", self._show_quick_upload_menu)
        
        # 中部：需求描述（关键词输入）
        input_frame = ttk.LabelFrame(frame, text="创作需求描述（关键词）", padding=10)
        input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 示例提示
        example_frame = ttk.Frame(input_frame, style="TFrame")
        example_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(example_frame, text="示例：", foreground=GlassTheme.TEXT_SECONDARY,
                 font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL)).pack(side=tk.LEFT)
        
        examples = ["修仙世界", "现代都市", "古代宫廷", "仙侠爱情", "科幻未来"]
        for example in examples:
            def set_example(e=example):
                self._quick_input.delete("1.0", tk.END)
                self._quick_input.insert("1.0", e)
            ttk.Button(example_frame, text=example, width=10,
                      command=set_example).pack(side=tk.LEFT, padx=2)
        
        # 关键词输入框
        self._quick_input = tk.Text(input_frame, wrap=tk.WORD, height=4,
                                   font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                                   bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        self._quick_input.pack(fill=tk.X, pady=5)
        self._quick_input.insert("1.0", "请输入关键词描述...")
        
        # 生成详细程度选择
        detail_frame = ttk.Frame(input_frame, style="TFrame")
        detail_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(detail_frame, text="生成详细程度：").pack(side=tk.LEFT)
        self._quick_detail_var = tk.StringVar(value="standard")
        ttk.Radiobutton(detail_frame, text="快速", variable=self._quick_detail_var, value="quick").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(detail_frame, text="标准", variable=self._quick_detail_var, value="standard").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(detail_frame, text="详细", variable=self._quick_detail_var, value="detailed").pack(side=tk.LEFT, padx=5)
        
        # 下部：结果展示区（可折叠）
        results_outer_frame = ttk.LabelFrame(frame, text="生成结果", padding=10)
        results_outer_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 创建可折叠的结果区域
        self._quick_result_frames = {}
        self._quick_result_texts = {}
        self._quick_result_expanded = {"worldview": True, "outline": True, "characters": True, "plot": True}
        
        result_types = [
            ("worldview", "🌍 世界观设定", "#4A90E2"),
            ("outline", "📋 章节大纲", "#50C878"),
            ("characters", "👤 人物设定", "#FF6B6B"),
            ("plot", "📖 关键情节", "#FFA500")
        ]
        
        for result_type, title, color in result_types:
            # 可折叠的标题栏
            header_frame = ttk.Frame(results_outer_frame, style="TFrame")
            header_frame.pack(fill=tk.X, pady=2)
            
            # 折叠按钮
            expand_btn = ttk.Button(header_frame, text="▼", width=3,
                                   command=lambda t=result_type: self._toggle_quick_result(t))
            expand_btn.pack(side=tk.LEFT)
            self._quick_result_frames[result_type] = {"header": header_frame, "expand_btn": expand_btn}
            
            # 标题标签
            ttk.Label(header_frame, text=title, 
                     font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL, "bold")).pack(side=tk.LEFT, padx=10)
            
            # 内容区域
            content_frame = ttk.Frame(results_outer_frame, style="TFrame")
            content_frame.pack(fill=tk.BOTH, expand=True, pady=2)
            
            # 文本框
            text_scroll = ttk.Scrollbar(content_frame, orient=tk.VERTICAL)
            text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            result_text = tk.Text(content_frame, wrap=tk.WORD, height=8,
                                 font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL),
                                 bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY,
                                 yscrollcommand=text_scroll.set, state=tk.NORMAL)
            result_text.pack(fill=tk.BOTH, expand=True)
            result_text.insert("1.0", f"{title}将在此显示...")
            text_scroll.configure(command=result_text.yview)
            
            self._quick_result_texts[result_type] = result_text
            self._quick_result_frames[result_type]["content"] = content_frame
        
        # 底部按钮区（两行布局）
        btn_frame = ttk.Frame(frame, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        # 第一行：生成按钮
        gen_btn_frame = ttk.Frame(btn_frame, style="TFrame")
        gen_btn_frame.pack(fill=tk.X, pady=2)
        
        self._quick_gen_all_btn = ttk.Button(gen_btn_frame, text="🚀 一键生成全部", 
                                            command=self._on_quick_generate_all, width=15)
        self._quick_gen_all_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(gen_btn_frame, text="🌍 仅世界观", width=12,
                  command=lambda: self._on_quick_generate_single("worldview")).pack(side=tk.LEFT, padx=5)
        ttk.Button(gen_btn_frame, text="📋 仅大纲", width=12,
                  command=lambda: self._on_quick_generate_single("outline")).pack(side=tk.LEFT, padx=5)
        ttk.Button(gen_btn_frame, text="👤 仅人设", width=12,
                  command=lambda: self._on_quick_generate_single("characters")).pack(side=tk.LEFT, padx=5)
        ttk.Button(gen_btn_frame, text="📖 仅情节", width=12,
                  command=lambda: self._on_quick_generate_single("plot")).pack(side=tk.LEFT, padx=5)
        
        # 第二行：保存和导入按钮
        save_btn_frame = ttk.Frame(btn_frame, style="TFrame")
        save_btn_frame.pack(fill=tk.X, pady=2)
        
        ttk.Button(save_btn_frame, text="💾 保存结果", width=12,
                  command=self._on_quick_save_results).pack(side=tk.LEFT, padx=5)
        ttk.Button(save_btn_frame, text="📤 导出Markdown", width=14,
                  command=lambda: self._on_quick_export_results("markdown")).pack(side=tk.LEFT, padx=5)
        ttk.Button(save_btn_frame, text="📤 导出JSON", width=12,
                  command=lambda: self._on_quick_export_results("json")).pack(side=tk.LEFT, padx=5)
        ttk.Button(save_btn_frame, text="📥 导入当前项目", width=14,
                  command=self._on_quick_import).pack(side=tk.LEFT, padx=5)
        
        # 延迟加载插件：首次使用时加载，避免启动卡顿
        # 插件将在 _on_quick_generate_all 或 _on_quick_generate_single 中加载
        
        return frame
    
    def _toggle_quick_result(self, result_type: str):
        """折叠/展开结果区域"""
        content = self._quick_result_frames[result_type]["content"]
        expand_btn = self._quick_result_frames[result_type]["expand_btn"]
        
        if self._quick_result_expanded[result_type]:
            content.pack_forget()
            expand_btn.configure(text="▶")
            self._quick_result_expanded[result_type] = False
        else:
            content.pack(fill=tk.BOTH, expand=True, pady=2)
            expand_btn.configure(text="▼")
            self._quick_result_expanded[result_type] = True
    
    def _load_quick_creator_plugin(self):
        """加载快捷创作插件"""
        try:
            from plugins.quick_creator_v1.plugin import QuickCreationPlugin
            self._quick_creator_plugin = QuickCreationPlugin()
            
            # 从服务定位器获取AI客户端
            if CORE_AVAILABLE:
                service_locator = get_service_locator()
                ai_service = service_locator.get_service("ai_service")
                if ai_service and hasattr(ai_service, 'get_client'):
                    client = ai_service.get_client()
                    if client:
                        self._quick_creator_plugin.set_api_client(client)
                        self._set_status("快捷创作插件加载成功")
                        logger.info("快捷创作插件加载成功")
                        return
            
            logger.warning("快捷创作插件未找到AI客户端")
        except Exception as e:
            logger.error(f"加载快捷创作插件失败: {e}")
            self._quick_creator_plugin = None
    
    # 别名方法，保持兼容性
    def _load_quick_creation_plugin(self):
        """加载快捷创作插件（别名方法）"""
        self._load_quick_creator_plugin()

    def _on_quick_save_results(self):
        """保存快捷创作结果"""
        try:
            # 获取所有结果内容
            content = {}
            for result_type, text_widget in self._quick_result_texts.items():
                content[result_type] = text_widget.get("1.0", tk.END).strip()
            
            # 检查是否有内容
            if not any(content.values()):
                messagebox.showwarning("提示", "没有可保存的内容！")
                return
            
            # 选择保存位置
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
                title="保存快捷创作结果"
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("===== 世界观设定 =====\n")
                    f.write(content.get("worldview", "") + "\n\n")
                    f.write("===== 章节大纲 =====\n")
                    f.write(content.get("outline", "") + "\n\n")
                    f.write("===== 人物设定 =====\n")
                    f.write(content.get("characters", "") + "\n\n")
                    f.write("===== 关键情节 =====\n")
                    f.write(content.get("plot", "") + "\n")
                
                self._set_status(f"已保存：{os.path.basename(file_path)}")
                messagebox.showinfo("成功", "快捷创作结果已保存！")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败：{e}")
    
    def _create_continue_content(self) -> tk.Frame:
        """创建续写功能内容页面"""
        frame = ttk.Frame(self._workbench_content_frame, style="TFrame")
        
        # 初始化版本管理器
        self._continue_versions = []  # 存储所有版本
        self._current_version_index = 0  # 当前显示的版本索引
        self._best_version_index = -1  # 最佳版本索引
        
        # 上部：原文区
        source_frame = ttk.LabelFrame(frame, text="原文内容（智能分析续写）", padding=10)
        source_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 原文操作按钮
        source_btn_frame = ttk.Frame(source_frame, style="TFrame")
        source_btn_frame.pack(fill=tk.X, pady=5)
        ttk.Label(source_btn_frame, text="续写起点：光标定位到末尾位置").pack(side=tk.LEFT)
        ttk.Button(source_btn_frame, text="选择文件", command=self._on_continue_browse).pack(side=tk.RIGHT)
        ttk.Button(source_btn_frame, text="选择章节", command=self._on_continue_select_chapter).pack(side=tk.RIGHT, padx=5)
        
        self._continue_source = tk.Text(source_frame, wrap=tk.WORD, height=8,
                                       font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                                       bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        self._continue_source.pack(fill=tk.BOTH, expand=True)
        self._continue_source.insert("1.0", "请在此粘贴或输入原文内容，或选择文件导入...")
        
        # 中部：续写设置
        settings_frame = ttk.LabelFrame(frame, text="续写设置", padding=10)
        settings_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 第一行：字数和方向
        row1 = ttk.Frame(settings_frame, style="TFrame")
        row1.pack(fill=tk.X, pady=5)
        
        # 字数选择（预设+自定义）
        ttk.Label(row1, text="续写字数：").pack(side=tk.LEFT)
        self._continue_words_var = tk.StringVar(value="1000")
        words_combo = ttk.Combobox(row1, textvariable=self._continue_words_var, 
                                   values=["500", "1000", "2000", "自定义"], width=10, state="readonly")
        words_combo.pack(side=tk.LEFT, padx=5)
        words_combo.bind("<<ComboboxSelected>>", self._on_words_selected)
        
        # 自定义字数输入框（默认隐藏）
        self._custom_words_entry = ttk.Entry(row1, width=8)
        
        # 续写方向
        ttk.Label(row1, text="续写方向：").pack(side=tk.LEFT, padx=(20, 0))
        self._continue_direction_var = tk.StringVar(value="自然续写")
        ttk.Combobox(row1, textvariable=self._continue_direction_var, 
                    values=["自然续写", "剧情推进", "高潮铺垫", "结局", "制造冲突", "引入新角色", "转折情节", "情感描写", "动作场景", "对话为主"], 
                    width=12, state="readonly").pack(side=tk.LEFT, padx=5)
        
        # 第二行：温度和模式
        row2 = ttk.Frame(settings_frame, style="TFrame")
        row2.pack(fill=tk.X, pady=5)
        
        ttk.Label(row2, text="创意温度：").pack(side=tk.LEFT)
        self._continue_temp_var = tk.DoubleVar(value=0.8)
        temp_scale = ttk.Scale(row2, from_=0.0, to=1.0, variable=self._continue_temp_var, 
                               orient=tk.HORIZONTAL, length=120)
        temp_scale.pack(side=tk.LEFT, padx=5)
        self._temp_label = ttk.Label(row2, text="0.8")
        self._temp_label.pack(side=tk.LEFT)
        temp_scale.bind("<Motion>", lambda e: self._temp_label.configure(text=f"{self._continue_temp_var.get():.1f}"))
        
        ttk.Label(row2, text="生成模式：").pack(side=tk.LEFT, padx=(20, 0))
        self._continue_mode_var = tk.StringVar(value="单次生成")
        ttk.Radiobutton(row2, text="单次", variable=self._continue_mode_var, value="单次生成").pack(side=tk.LEFT)
        ttk.Radiobutton(row2, text="多版本", variable=self._continue_mode_var, value="多版本生成").pack(side=tk.LEFT, padx=5)
        
        # 下部：分割为左侧版本列表 + 右侧结果预览
        bottom_frame = ttk.Frame(frame, style="TFrame")
        bottom_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 左侧：版本列表区域（20%宽度）
        version_list_frame = ttk.LabelFrame(bottom_frame, text="版本历史（最多5个）", padding=10)
        version_list_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        
        # 版本列表Treeview
        columns = ("版本", "温度", "字数", "评分", "状态")
        self._version_tree = ttk.Treeview(version_list_frame, columns=columns, show="headings", height=10)
        
        # 设置列宽和标题
        self._version_tree.heading("版本", text="版本")
        self._version_tree.heading("温度", text="温度")
        self._version_tree.heading("字数", text="字数")
        self._version_tree.heading("评分", text="评分")
        self._version_tree.heading("状态", text="状态")
        
        self._version_tree.column("版本", width=50, anchor=tk.CENTER)
        self._version_tree.column("温度", width=50, anchor=tk.CENTER)
        self._version_tree.column("字数", width=60, anchor=tk.CENTER)
        self._version_tree.column("评分", width=60, anchor=tk.CENTER)
        self._version_tree.column("状态", width=60, anchor=tk.CENTER)
        
        # 添加滚动条
        tree_scroll = ttk.Scrollbar(version_list_frame, orient="vertical", command=self._version_tree.yview)
        self._version_tree.configure(yscrollcommand=tree_scroll.set)
        
        self._version_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定选择事件
        self._version_tree.bind("<<TreeviewSelect>>", self._on_version_tree_select)
        self._version_tree.bind("<Double-1>", self._on_version_double_click)
        
        # 右侧：续写结果预览（80%宽度）
        result_frame = ttk.LabelFrame(bottom_frame, text="续写结果预览", padding=10)
        result_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 版本信息栏
        version_bar = ttk.Frame(result_frame, style="TFrame")
        version_bar.pack(fill=tk.X, pady=5)
        self._version_info_label = ttk.Label(version_bar, text="当前无版本")
        self._version_info_label.pack(side=tk.LEFT)
        
        # 版本切换按钮
        ttk.Label(version_bar, text="  快速切换：").pack(side=tk.LEFT)
        ttk.Button(version_bar, text="◀", width=3, command=lambda: self._switch_version(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(version_bar, text="▶", width=3, command=lambda: self._switch_version(1)).pack(side=tk.LEFT, padx=2)
        
        # 结果文本框
        self._continue_result = tk.Text(result_frame, wrap=tk.WORD, height=10,
                                       font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                                       bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        self._continue_result.pack(fill=tk.BOTH, expand=True)
        
        # 结果信息栏
        info_bar = ttk.Frame(result_frame, style="TFrame")
        info_bar.pack(fill=tk.X, pady=5)
        self._result_info_label = ttk.Label(info_bar, text="字数：0 | 耗时：0秒 | 模型：-")
        self._result_info_label.pack(side=tk.LEFT)
        self._score_label = ttk.Label(info_bar, text="评分：-")
        self._score_label.pack(side=tk.RIGHT)
        
        # 底部按钮
        btn_frame = ttk.Frame(frame, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 左侧按钮组
        left_btns = ttk.Frame(btn_frame, style="TFrame")
        left_btns.pack(side=tk.LEFT)
        
        self._start_btn = ttk.Button(left_btns, text="🚀 开始续写", command=self._on_continue_generate)
        self._start_btn.pack(side=tk.LEFT, padx=5)
        
        self._regenerate_btn = ttk.Button(left_btns, text="🔄 重新生成", command=self._on_continue_regenerate, state=tk.DISABLED)
        self._regenerate_btn.pack(side=tk.LEFT, padx=5)
        
        # 右侧按钮组
        right_btns = ttk.Frame(btn_frame, style="TFrame")
        right_btns.pack(side=tk.RIGHT)
        
        self._select_best_btn = ttk.Button(right_btns, text="⭐ 选择最佳版本", command=self._on_continue_select_best, state=tk.DISABLED)
        self._select_best_btn.pack(side=tk.LEFT, padx=5)
        
        self._save_btn = ttk.Button(right_btns, text="💾 保存结果", command=self._on_continue_save, state=tk.DISABLED)
        self._save_btn.pack(side=tk.LEFT, padx=5)
        
        # 加载续写插件
        self._load_continuation_plugin()
        
        return frame
    
    def _load_continuation_plugin(self):
        """加载续写插件"""
        try:
            from plugins.continuation_generator_v1.plugin import ContinuationGeneratorPlugin
            self._continuation_plugin = ContinuationGeneratorPlugin()
            
            # 从服务定位器获取AI客户端
            if CORE_AVAILABLE:
                service_locator = get_service_locator()
                ai_service = service_locator.get_service("ai_service")
                if ai_service and hasattr(ai_service, 'get_client'):
                    client = ai_service.get_client()
                    if client:
                        self._continuation_plugin.set_api_client(client)
                        self._set_status("续写插件加载成功")
                        logger.info("续写插件加载成功")
                        return
            
            # 如果无法获取AI服务，使用配置文件中的设置
            if hasattr(self, '_config_manager') and self._config_manager:
                ai_config = self._config_manager.get("ai_service", {})
                if ai_config:
                    from openai import OpenAI
                    api_key = ai_config.get("api_key", "")
                    base_url = ai_config.get("base_url", "https://api.deepseek.com/v1")
                    if api_key:
                        client = OpenAI(api_key=api_key, base_url=base_url)
                        self._continuation_plugin.set_api_client(client)
                        self._set_status("续写插件加载成功（使用配置文件）")
                        logger.info("续写插件加载成功（使用配置文件）")
                        return
            
            logger.warning("续写插件未找到AI客户端，请先配置AI服务")
        except Exception as e:
            logger.error(f"加载续写插件失败: {e}")
            self._continuation_plugin = None
    
    def _on_words_selected(self, event):
        """字数选择变更"""
        selected = self._continue_words_var.get()
        if selected == "自定义":
            self._custom_words_entry.pack(side=tk.LEFT, padx=5)
            self._custom_words_entry.focus()
        else:
            self._custom_words_entry.pack_forget()
    
    def _on_continue_select_chapter(self):
        """选择已生成章节作为续写起点"""
        if not hasattr(self, '_project_manager') or not self._project_manager:
            messagebox.showwarning("提示", "请先打开项目")
            return
        
        # 获取项目章节列表
        chapters = self._project_manager.list_chapters()
        if not chapters:
            messagebox.showinfo("提示", "当前项目没有章节")
            return
        
        # 创建选择对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("选择章节")
        dialog.geometry("500x400")
        dialog.configure(bg=GlassTheme.GLASS_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 500) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 400) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 章节列表
        list_frame = ttk.Frame(dialog, style="TFrame")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ttk.Label(list_frame, text="选择章节作为续写起点：").pack(anchor=tk.W)
        
        # 创建Treeview
        tree = ttk.Treeview(list_frame, columns=("章节", "字数"), show="headings", height=15)
        tree.heading("章节", text="章节名称")
        tree.heading("字数", text="字数")
        tree.column("章节", width=300)
        tree.column("字数", width=100)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 填充章节
        for chapter in chapters:
            tree.insert("", tk.END, values=(chapter.get("title", ""), chapter.get("word_count", 0)))
        
        # 按钮区
        btn_frame = ttk.Frame(dialog, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=20, pady=10)
        
        def on_confirm():
            selected = tree.selection()
            if selected:
                item = tree.item(selected[0])
                chapter_title = item["values"][0]
                # 读取章节内容
                content = self._project_manager.get_chapter_content(chapter_title)
                if content:
                    self._continue_source.delete("1.0", tk.END)
                    self._continue_source.insert("1.0", content)
                    self._set_status(f"已导入章节：{chapter_title}")
                dialog.destroy()
            else:
                messagebox.showwarning("提示", "请选择章节")
        
        ttk.Button(btn_frame, text="确定", command=on_confirm).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT)
    
    def _switch_version(self, direction: int):
        """切换版本
        
        Args:
            direction: 1为下一个版本，-1为上一个版本
        """
        if not self._continue_versions:
            return
        
        self._current_version_index = (self._current_version_index + direction) % len(self._continue_versions)
        self._display_version(self._current_version_index)
    
    def _on_version_tree_select(self, event):
        """版本列表选择事件"""
        selected = self._version_tree.selection()
        if selected:
            # 获取选中项的版本索引
            item_id = selected[0]
            item_data = self._version_tree.item(item_id)
            version_text = item_data["values"][0]  # 如 "V1"
            version_index = int(version_text.replace("V", "")) - 1
            
            if 0 <= version_index < len(self._continue_versions):
                self._current_version_index = version_index
                self._display_version(version_index)
    
    def _on_version_double_click(self, event):
        """版本列表双击事件 - 快速选择并提示保存"""
        selected = self._version_tree.selection()
        if not selected:
            return
        
        item_id = selected[0]
        item_data = self._version_tree.item(item_id)
        version_text = item_data["values"][0]
        version_index = int(version_text.replace("V", "")) - 1
        
        if 0 <= version_index < len(self._continue_versions):
            # 显示确认对话框
            if messagebox.askyesno("确认保存", f"是否选择版本 {version_text} 作为最终版本并保存？"):
                self._current_version_index = version_index
                self._display_version(version_index)
                # 直接触发保存
                self._on_continue_save()
    
    def _on_version_combo_changed(self, event):
        """版本下拉框选择变更（保留兼容性）"""
        # 已废弃，使用版本列表替代
        pass
    
    def _display_version(self, index: int):
        """显示指定版本"""
        if not self._continue_versions or index >= len(self._continue_versions):
            return
        
        version = self._continue_versions[index]
        
        # 更新文本框
        self._continue_result.delete("1.0", tk.END)
        self._continue_result.insert("1.0", version.get("text", ""))
        
        # 更新信息栏
        metadata = version.get("metadata", {})
        word_count = version.get("word_count", 0)
        gen_time = metadata.get("generation_time", 0)
        model = metadata.get("model_name", "-")
        
        self._result_info_label.configure(text=f"字数：{word_count} | 耗时：{gen_time:.1f}秒 | 模型：{model}")
        
        # 更新评分
        score = version.get("score", 0)
        self._score_label.configure(text=f"评分：{score:.2f}")
        
        # 更新版本信息
        total = len(self._continue_versions)
        is_best = index == self._best_version_index
        best_mark = " ⭐最佳" if is_best else ""
        self._version_info_label.configure(text=f"版本 {index + 1}/{total}{best_mark}")
        
        # 同步高亮版本列表
        self._highlight_version_in_tree(index)
        
        # 启用按钮
        self._regenerate_btn.configure(state=tk.NORMAL)
        self._select_best_btn.configure(state=tk.NORMAL)
        self._save_btn.configure(state=tk.NORMAL)
    
    def _highlight_version_in_tree(self, index: int):
        """高亮版本列表中的指定版本"""
        if not hasattr(self, '_version_tree'):
            return
        
        # 清除所有选择
        for item in self._version_tree.get_children():
            self._version_tree.selection_remove(item)
        
        # 选择指定版本
        children = self._version_tree.get_children()
        if 0 <= index < len(children):
            self._version_tree.selection_set(children[index])
            self._version_tree.see(children[index])  # 滚动到可见区域
    
    def _update_version_tree(self):
        """更新版本列表Treeview"""
        if not hasattr(self, '_version_tree'):
            return
        
        # 清空现有项
        for item in self._version_tree.get_children():
            self._version_tree.delete(item)
        
        if not self._continue_versions:
            return
        
        # 添加版本项（最多5个）
        for i, version in enumerate(self._continue_versions[:5]):
            temp = version.get("temperature", 0.8)
            score = version.get("score", 0)
            word_count = version.get("word_count", 0)
            
            # 确定状态
            is_best = i == self._best_version_index
            status = "⭐最佳" if is_best else ""
            
            # 插入到Treeview
            self._version_tree.insert("", tk.END, values=(
                f"V{i + 1}",
                f"{temp:.1f}",
                f"{word_count}",
                f"{score:.2f}",
                status
            ))
        
        # 高亮当前版本
        if self._continue_versions:
            self._highlight_version_in_tree(self._current_version_index)
    
    def _update_version_combo(self):
        """更新版本列表（重定向到Treeview方法）"""
        self._update_version_tree()
    
    # ============== 工作台子功能回调方法 ==============
    
    def _on_worldview_browse(self):
        """浏览世界观文件"""
        path = filedialog.askopenfilename(
            title="选择世界观文件",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx"), ("所有文件", "*.*")]
        )
        if path:
            self._worldview_path_var.set(path)
            self._preview_worldview(path)
    
    def _preview_worldview(self, path: str):
        """预览世界观文件"""
        try:
            self._worldview_preview.delete("1.0", tk.END)
            if path.lower().endswith('.docx'):
                from docx import Document
                doc = Document(path)
                text = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    text = f.read()
            self._worldview_preview.insert("1.0", text[:5000])
        except Exception as e:
            self._worldview_preview.insert("1.0", f"预览失败: {e}")
    
    def _on_worldview_new(self):
        """新建世界观（弹窗）"""
        dialog = tk.Toplevel(self.root)
        dialog.title("新建世界观")
        dialog.geometry("500x400")
        dialog.configure(bg=GlassTheme.GLASS_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 500) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 400) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 世界观名称
        name_frame = ttk.Frame(dialog, style="TFrame")
        name_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        ttk.Label(name_frame, text="世界观名称：").pack(side=tk.LEFT)
        name_var = tk.StringVar(value="新世界观")
        ttk.Entry(name_frame, textvariable=name_var, width=30).pack(side=tk.LEFT, padx=10)
        
        # 核心元素
        elements_frame = ttk.Frame(dialog, style="TFrame")
        elements_frame.pack(fill=tk.X, padx=20, pady=10)
        ttk.Label(elements_frame, text="核心元素：").pack(side=tk.LEFT)
        elements_var = tk.StringVar(value="魔法体系、势力分布、历史背景")
        ttk.Entry(elements_frame, textvariable=elements_var, width=30).pack(side=tk.LEFT, padx=10)
        
        # 世界观描述
        desc_frame = ttk.LabelFrame(dialog, text="世界观详细描述", padding=10)
        desc_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        desc_text = tk.Text(desc_frame, wrap=tk.WORD, height=10,
                           font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                           bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        desc_text.pack(fill=tk.BOTH, expand=True)
        desc_text.insert("1.0", "请在此描述世界观的核心设定、规则、势力分布等内容...")
        
        # 按钮
        btn_frame = ttk.Frame(dialog, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=20, pady=20)
        
        def create_worldview():
            name = name_var.get().strip()
            elements = elements_var.get().strip()
            desc = desc_text.get("1.0", tk.END).strip()
            
            if not name:
                messagebox.showwarning("警告", "请输入世界观名称！")
                return
            
            # 添加到列表
            self._worldview_tree.insert("", tk.END, values=(
                name,
                elements[:50] + "..." if len(elements) > 50 else elements,
                "新建",
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
            
            # 更新预览
            self._worldview_preview.delete("1.0", tk.END)
            self._worldview_preview.insert("1.0", f"【{name}】\n\n核心元素：{elements}\n\n{desc}")
            
            self._set_status(f"已创建世界观：{name}")
            dialog.destroy()
        
        ttk.Button(btn_frame, text="创建", command=create_worldview).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def _on_worldview_view(self):
        """查看世界观详情"""
        self._set_status("查看世界观详情功能开发中...")
    
    def _on_worldview_edit(self):
        """编辑世界观"""
        self._set_status("编辑世界观功能开发中...")
    
    def _on_worldview_delete(self):
        """批量删除世界观"""
        self._set_status("批量删除世界观功能开发中...")
    
    def _on_worldview_link(self):
        """关联要素"""
        self._set_status("关联要素功能开发中...")
    
    def _on_worldview_import(self):
        """导入世界观 - 调用WorldviewParserAdapter"""
        try:
            # 获取当前选中的世界观路径
            worldview_path = getattr(self, '_worldview_path_var', tk.StringVar()).get()
            if not worldview_path:
                messagebox.showwarning("提示", "请先选择世界观文件")
                return
            
            # 更新状态
            self._set_status("正在解析世界观...")
            
            # 导入适配器
            from agents.adapters.worldview_adapter import WorldviewParserAdapter
            from agents.priority import AgentTask
            from pathlib import Path
            
            # 读取文件内容
            content = Path(worldview_path).read_text(encoding='utf-8')
            
            # 创建适配器实例
            adapter = WorldviewParserAdapter()
            if not adapter.initialize():
                raise RuntimeError("WorldviewParserAdapter初始化失败")
            
            # 创建任务
            task = AgentTask(
                task_id=f"worldview_import_{int(time.time())}",
                agent_type="worldview_parser",
                payload={
                    "worldview_content": content,
                    "options": {}
                }
            )
            
            # 执行解析（异步）
            def run_parse():
                try:
                    result = adapter.execute(task)
                    self.root.after(0, lambda: self._on_worldview_import_complete(result))
                except Exception as e:
                    self.root.after(0, lambda: self._on_worldview_import_error(str(e)))
            
            threading.Thread(target=run_parse, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("错误", f"启动世界观解析失败: {str(e)}")
            self._set_status(f"世界观解析失败: {str(e)}")
    
    def _on_worldview_import_complete(self, result):
        """世界观解析完成回调"""
        try:
            # 存储世界观数据
            self._worldview = result.get("result", {})
            
            # 更新UI预览
            self._worldview_preview.delete("1.0", tk.END)
            elements = self._worldview.get("elements", [])
            rules = self._worldview.get("rules", [])
            
            self._worldview_preview.insert(tk.END, f"世界观解析完成！\n\n")
            self._worldview_preview.insert(tk.END, f"要素数量: {len(elements)}\n")
            self._worldview_preview.insert(tk.END, f"规则数量: {len(rules)}\n\n")
            
            # 显示要素列表
            for elem in elements[:10]:  # 只显示前10个
                self._worldview_preview.insert(tk.END, f"- {elem.get('name', '未命名')}: {elem.get('description', '')[:50]}...\n")
            
            self._set_status("世界观解析完成")
        except Exception as e:
            self._set_status(f"处理解析结果失败: {str(e)}")
    
    def _on_worldview_import_error(self, error: str):
        """世界观解析错误回调"""
        messagebox.showerror("世界观解析错误", error)
        self._set_status(f"世界观解析失败: {error}")
    
    def _on_worldview_clear(self):
        """清除世界观"""
        self._worldview_path_var.set("")
        self._worldview_preview.delete("1.0", tk.END)
    
    def _on_character_browse(self):
        """浏览人物档案文件"""
        path = filedialog.askopenfilename(
            title="选择人物档案文件",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx"), ("所有文件", "*.*")]
        )
        if path:
            self._character_path_var.set(path)
            self._set_status(f"已选择: {os.path.basename(path)}")
    
    def _on_character_batch_import(self):
        """批量解析导入人物 - 调用CharacterManagerAdapter"""
        try:
            # 获取当前选中的人物档案路径
            character_path = getattr(self, '_character_path_var', tk.StringVar()).get()
            if not character_path:
                messagebox.showwarning("提示", "请先选择人物档案文件")
                return
            
            # 更新状态
            self._set_status("正在解析人物档案...")
            
            # 导入适配器
            from agents.adapters.character_adapter import CharacterManagerAdapter
            from agents.priority import AgentTask
            from pathlib import Path
            
            # 读取文件内容
            content = Path(character_path).read_text(encoding='utf-8')
            
            # 创建适配器实例
            adapter = CharacterManagerAdapter()
            if not adapter.initialize():
                raise RuntimeError("CharacterManagerAdapter初始化失败")
            
            # 创建任务
            task = AgentTask(
                task_id=f"character_import_{int(time.time())}",
                agent_type="character_manager",
                payload={
                    "operation": "batch_import",
                    "character_data": {
                        "content": content,
                        "source_file": character_path
                    }
                }
            )
            
            # 执行解析（异步）
            def run_parse():
                try:
                    result = adapter.execute(task)
                    self.root.after(0, lambda: self._on_character_import_complete(result))
                except Exception as e:
                    self.root.after(0, lambda: self._on_character_import_error(str(e)))
            
            threading.Thread(target=run_parse, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("错误", f"启动人物解析失败: {str(e)}")
            self._set_status(f"人物解析失败: {str(e)}")
    
    def _on_character_import_complete(self, result):
        """人物解析完成回调"""
        try:
            # 存储人物数据
            characters = result.get("result", {}).get("characters", [])
            self._characters = characters
            
            # 更新人物列表
            self._character_list.delete(0, tk.END)
            for char in characters:
                name = char.get("name", "未命名")
                role = char.get("role", "未知")
                self._character_list.insert(tk.END, f"{name} ({role})")
            
            # 更新状态
            self._set_status(f"成功导入 {len(characters)} 个人物")
        except Exception as e:
            self._set_status(f"处理解析结果失败: {str(e)}")
    
    def _on_character_import_error(self, error: str):
        """人物解析错误回调"""
        messagebox.showerror("人物解析错误", error)
        self._set_status(f"人物解析失败: {error}")
    
    def _on_character_new(self):
        """新建人物（弹窗）"""
        dialog = tk.Toplevel(self.root)
        dialog.title("新建人物")
        dialog.geometry("600x700")
        dialog.configure(bg=GlassTheme.GLASS_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 600) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 700) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 创建滚动区域
        canvas = tk.Canvas(dialog, bg=GlassTheme.GLASS_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="TFrame")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 基本信息
        basic_frame = ttk.LabelFrame(scrollable_frame, text="基本信息", padding=10)
        basic_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # 姓名
        name_frame = ttk.Frame(basic_frame, style="TFrame")
        name_frame.pack(fill=tk.X, pady=5)
        ttk.Label(name_frame, text="姓名：").pack(side=tk.LEFT)
        name_var = tk.StringVar(value="新角色")
        ttk.Entry(name_frame, textvariable=name_var, width=30).pack(side=tk.LEFT, padx=10)
        
        # 角色类型
        role_frame = ttk.Frame(basic_frame, style="TFrame")
        role_frame.pack(fill=tk.X, pady=5)
        ttk.Label(role_frame, text="角色类型：").pack(side=tk.LEFT)
        role_var = tk.StringVar(value="主角")
        ttk.Combobox(role_frame, textvariable=role_var, values=["主角", "配角", "反派", "路人"], width=15).pack(side=tk.LEFT, padx=10)
        
        # 外貌描述
        appearance_frame = ttk.LabelFrame(scrollable_frame, text="外貌描述", padding=10)
        appearance_frame.pack(fill=tk.X, padx=20, pady=10)
        appearance_text = tk.Text(appearance_frame, wrap=tk.WORD, height=3,
                                 font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                                 bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        appearance_text.pack(fill=tk.X)
        
        # 性格特点
        personality_frame = ttk.LabelFrame(scrollable_frame, text="性格特点", padding=10)
        personality_frame.pack(fill=tk.X, padx=20, pady=10)
        personality_text = tk.Text(personality_frame, wrap=tk.WORD, height=3,
                                  font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                                  bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        personality_text.pack(fill=tk.X)
        
        # 背景故事
        background_frame = ttk.LabelFrame(scrollable_frame, text="背景故事", padding=10)
        background_frame.pack(fill=tk.X, padx=20, pady=10)
        background_text = tk.Text(background_frame, wrap=tk.WORD, height=5,
                                 font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                                 bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        background_text.pack(fill=tk.X)
        
        # 能力特长
        ability_frame = ttk.LabelFrame(scrollable_frame, text="能力特长", padding=10)
        ability_frame.pack(fill=tk.X, padx=20, pady=10)
        ability_text = tk.Text(ability_frame, wrap=tk.WORD, height=3,
                              font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                              bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        ability_text.pack(fill=tk.X)
        
        # 按钮
        btn_frame = ttk.Frame(scrollable_frame, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=20, pady=20)
        
        def create_character():
            name = name_var.get().strip()
            role = role_var.get()
            
            if not name:
                messagebox.showwarning("警告", "请输入人物姓名！")
                return
            
            # 添加到列表
            self._character_tree.insert("", tk.END, values=(
                "👤",  # 头像占位
                name,
                role,
                "新建",
                "平静",
                "第1章"
            ))
            
            # 更新详情
            appearance = appearance_text.get("1.0", tk.END).strip()
            personality = personality_text.get("1.0", tk.END).strip()
            background = background_text.get("1.0", tk.END).strip()
            ability = ability_text.get("1.0", tk.END).strip()
            
            self._character_detail.delete("1.0", tk.END)
            self._character_detail.insert("1.0", f"""【{name}】- {role}

外貌：{appearance}

性格：{personality}

背景：{background}

能力：{ability}
""")
            
            self._set_status(f"已创建人物：{name}")
            dialog.destroy()
        
        ttk.Button(btn_frame, text="创建", command=create_character).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def _on_character_edit(self):
        """编辑人物"""
        self._set_status("编辑人物功能开发中...")
    
    def _on_character_detail(self):
        """人物详情页"""
        self._set_status("人物详情页功能开发中...")
    
    def _on_character_relation(self):
        """关系网络图"""
        self._set_status("关系网络图功能开发中...")
    
    def _on_character_delete(self):
        """删除人物"""
        self._set_status("删除人物功能开发中...")
    
    def _on_outline_browse(self):
        """浏览大纲文件"""
        path = filedialog.askopenfilename(
            title="选择大纲文件",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx"), ("所有文件", "*.*")]
        )
        if path:
            self._outline_path_var.set(os.path.basename(path))
            self._set_status(f"已选择: {os.path.basename(path)}")
    
    def _on_outline_new(self):
        """新建大纲（弹窗）"""
        dialog = tk.Toplevel(self.root)
        dialog.title("新建大纲")
        dialog.geometry("500x300")
        dialog.configure(bg=GlassTheme.GLASS_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 500) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 300) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 大纲名称
        name_frame = ttk.Frame(dialog, style="TFrame")
        name_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        ttk.Label(name_frame, text="大纲名称：").pack(side=tk.LEFT)
        name_var = tk.StringVar(value="新小说大纲")
        ttk.Entry(name_frame, textvariable=name_var, width=30).pack(side=tk.LEFT, padx=10)
        
        # 小说类型
        type_frame = ttk.Frame(dialog, style="TFrame")
        type_frame.pack(fill=tk.X, padx=20, pady=10)
        ttk.Label(type_frame, text="小说类型：").pack(side=tk.LEFT)
        type_var = tk.StringVar(value="玄幻")
        ttk.Combobox(type_frame, textvariable=type_var, values=["玄幻", "仙侠", "都市", "历史", "科幻", "言情"], width=15).pack(side=tk.LEFT, padx=10)
        
        # 目标字数
        words_frame = ttk.Frame(dialog, style="TFrame")
        words_frame.pack(fill=tk.X, padx=20, pady=10)
        ttk.Label(words_frame, text="目标字数：").pack(side=tk.LEFT)
        words_var = tk.StringVar(value="500000")
        ttk.Entry(words_frame, textvariable=words_var, width=15).pack(side=tk.LEFT, padx=10)
        ttk.Label(words_frame, text="字").pack(side=tk.LEFT)
        
        # 简介
        intro_frame = ttk.LabelFrame(dialog, text="小说简介", padding=10)
        intro_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        intro_text = tk.Text(intro_frame, wrap=tk.WORD, height=4,
                            font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                            bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        intro_text.pack(fill=tk.BOTH, expand=True)
        
        # 按钮
        btn_frame = ttk.Frame(dialog, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=20, pady=20)
        
        def create_outline():
            name = name_var.get().strip()
            novel_type = type_var.get()
            target_words = words_var.get()
            intro = intro_text.get("1.0", tk.END).strip()
            
            if not name:
                messagebox.showwarning("警告", "请输入大纲名称！")
                return
            
            # 添加根节点到大纲树
            root_node = self._outline_tree.insert("", tk.END, text=f"📖 {name}", open=True)
            self._outline_tree.insert(root_node, tk.END, text="第一卷")
            self._outline_tree.insert(root_node, tk.END, text="第二卷")
            
            self._outline_path_var.set(name)
            self._set_status(f"已创建大纲：{name}")
            dialog.destroy()
        
        ttk.Button(btn_frame, text="创建", command=create_outline).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def _on_outline_export(self):
        """导出大纲"""
        self._set_status("导出大纲功能开发中...")
    
    def _on_outline_add_volume(self):
        """添加卷"""
        self._set_status("添加卷功能开发中...")
    
    def _on_outline_add_chapter(self):
        """添加章节"""
        self._set_status("添加章节功能开发中...")
    
    def _on_outline_edit_chapter(self):
        """编辑章节"""
        self._set_status("编辑章节功能开发中...")
    
    def _on_outline_delete(self):
        """删除"""
        self._set_status("删除功能开发中...")
    
    def _on_outline_parse(self):
        """解析大纲 - 调用OutlineAnalysisAgent"""
        try:
            # 获取当前选中的大纲路径
            outline_path = getattr(self, '_outline_path_var', tk.StringVar()).get()
            if not outline_path or outline_path == "未导入":
                messagebox.showwarning("提示", "请先选择大纲文件")
                return
            
            # 更新状态
            self._set_status("正在解析大纲...")
            
            # 导入Agent
            from agents.plugins.outline_analysis_agent import OutlineAnalysisAgent
            from agents.core.base_agent import AgentContext
            from pathlib import Path
            
            # 读取文件内容
            content = Path(outline_path).read_text(encoding='utf-8')
            
            # 创建Agent实例
            agent = OutlineAnalysisAgent()
            if not agent.initialize():
                raise RuntimeError("OutlineAnalysisAgent初始化失败")
            
            # 构建上下文
            context = AgentContext(
                task_id=f"outline_parse_{int(time.time())}",
                input_data={
                    "outline_content": content,
                    "extract_chapters": True,
                }
            )
            
            # 执行解析（异步）
            def run_parse():
                try:
                    result = agent.execute(context)
                    self.root.after(0, lambda: self._on_outline_parse_complete(result))
                except Exception as e:
                    self.root.after(0, lambda: self._on_outline_parse_error(str(e)))
            
            threading.Thread(target=run_parse, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("错误", f"启动大纲解析失败: {str(e)}")
            self._set_status(f"大纲解析失败: {str(e)}")
    
    def _on_outline_parse_complete(self, result):
        """大纲解析完成回调"""
        try:
            if result.success:
                # 存储大纲数据
                self._outline_content = result.data.get("outline_content", "")
                self._chapter_outlines = result.data.get("chapters", {})
                
                # 更新大纲树形结构
                self._outline_tree.delete(*self._outline_tree.get_children())
                chapters = result.data.get("chapters", [])
                for i, chapter in enumerate(chapters):
                    chapter_id = self._outline_tree.insert("", tk.END, text=f"第{i+1}章: {chapter.get('title', '未命名')}")
                    # 添加子节点
                    for key, value in chapter.items():
                        if key != "title":
                            self._outline_tree.insert(chapter_id, tk.END, text=f"{key}: {str(value)[:30]}")
                
                # 更新统计信息
                total_words = result.data.get("estimated_words", 0)
                self._set_status(f"大纲解析完成，预估{total_words}字")
            else:
                self._set_status(f"大纲解析失败: {result.error}")
        except Exception as e:
            self._set_status(f"处理解析结果失败: {str(e)}")
    
    def _on_outline_parse_error(self, error: str):
        """大纲解析错误回调"""
        messagebox.showerror("大纲解析错误", error)
        self._set_status(f"大纲解析失败: {error}")
    
    def _on_outline_clear(self):
        """清除大纲"""
        self._outline_path_var.set("未导入")
    
    def _on_style_browse(self):
        """浏览风格文件"""
        path = filedialog.askopenfilename(
            title="选择风格文件",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx"), ("所有文件", "*.*")]
        )
        if path:
            self._style_path_var.set(os.path.basename(path))
            self._set_status(f"已选择: {os.path.basename(path)}")
    
    def _on_style_delete(self):
        """删除范文"""
        self._set_status("删除范文功能开发中...")
    
    def _on_style_analyze(self):
        """解析风格 - 调用StyleLearningAgent"""
        try:
            # 获取当前选中的范文路径
            style_path = getattr(self, '_style_path_var', tk.StringVar()).get()
            if not style_path or style_path == "未导入":
                messagebox.showwarning("提示", "请先上传范文文件")
                return
            
            # 更新状态
            self._set_status("正在分析风格...")
            
            # 导入Agent
            from agents.plugins.style_learning_agent import StyleLearningAgent
            from pathlib import Path
            
            # 读取文件内容
            content = Path(style_path).read_text(encoding='utf-8')
            
            # 创建Agent实例
            agent = StyleLearningAgent()
            if not agent.initialize():
                raise RuntimeError("StyleLearningAgent初始化失败")
            
            # 构建上下文
            from agents.core.base_agent import AgentContext
            context = AgentContext(
                task_id=f"style_analyze_{int(time.time())}",
                input_data={
                    "text": content[:50000],  # 限制长度
                    "extract_patterns": True,
                }
            )
            
            # 执行分析（异步）
            def run_analysis():
                try:
                    result = agent.execute(context)
                    self.root.after(0, lambda: self._on_style_analyze_complete(result))
                except Exception as e:
                    self.root.after(0, lambda: self._on_style_analyze_error(str(e)))
            
            threading.Thread(target=run_analysis, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("错误", f"启动风格分析失败: {str(e)}")
            self._set_status(f"风格分析失败: {str(e)}")
    
    def _on_style_analyze_complete(self, result):
        """风格分析完成回调"""
        try:
            if result.success:
                # 存储风格档案
                self._style_profile = result.data.get("style_profile", {})
                
                # 更新UI
                self._style_info.delete("1.0", tk.END)
                self._style_info.insert("1.0", f"风格分析完成！\n\n")
                self._style_info.insert(tk.END, f"词汇特征: {len(result.data.get('vocabulary_features', []))}个\n")
                self._style_info.insert(tk.END, f"句式模式: {len(result.data.get('sentence_patterns', []))}个\n")
                self._style_info.insert(tk.END, f"修辞手法: {len(result.data.get('rhetorical_devices', []))}个\n")
                
                self._set_status("风格分析完成")
            else:
                self._set_status(f"风格分析失败: {result.error}")
        except Exception as e:
            self._set_status(f"处理分析结果失败: {str(e)}")
    
    def _on_style_analyze_error(self, error: str):
        """风格分析错误回调"""
        messagebox.showerror("风格分析错误", error)
        self._set_status(f"风格分析失败: {error}")
    
    def _on_style_export(self):
        """导出风格"""
        self._set_status("导出风格功能开发中...")
    
    def _on_style_switch(self):
        """切换风格"""
        self._set_status("切换风格功能开发中...")
    
    def _on_style_edit_weight(self):
        """编辑权重"""
        self._set_status("编辑权重功能开发中...")
    
    def _on_style_delete_profile(self):
        """删除风格档案"""
        self._set_status("删除风格档案功能开发中...")
    
    def _on_style_learn(self):
        """学习风格"""
        self._set_status("风格学习功能开发中...")
    
    def _on_style_create(self):
        """创建风格模板（弹窗）"""
        dialog = tk.Toplevel(self.root)
        dialog.title("创建风格模板")
        dialog.geometry("600x500")
        dialog.configure(bg=GlassTheme.GLASS_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 600) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 500) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 风格名称
        name_frame = ttk.Frame(dialog, style="TFrame")
        name_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        ttk.Label(name_frame, text="风格名称：").pack(side=tk.LEFT)
        name_var = tk.StringVar(value="自定义风格")
        ttk.Entry(name_frame, textvariable=name_var, width=30).pack(side=tk.LEFT, padx=10)
        
        # 七维度评分
        dimensions_frame = ttk.LabelFrame(dialog, text="七维度风格评分（0-10分）", padding=10)
        dimensions_frame.pack(fill=tk.X, padx=20, pady=10)
        
        dimensions = [
            ("词汇丰富度", "vocabulary"),
            ("句式复杂度", "sentence"),
            ("修辞使用", "rhetoric"),
            ("情感强度", "emotion"),
            ("节奏感", "rhythm"),
            ("结构完整性", "structure"),
            ("细节描写", "detail")
        ]
        
        dim_vars = {}
        for i, (label, key) in enumerate(dimensions):
            row = ttk.Frame(dimensions_frame, style="TFrame")
            row.pack(fill=tk.X, pady=3)
            ttk.Label(row, text=f"{label}：", width=15, anchor='e').pack(side=tk.LEFT)
            var = tk.DoubleVar(value=5.0)
            dim_vars[key] = var
            scale = ttk.Scale(row, from_=0.0, to=10.0, variable=var, orient=tk.HORIZONTAL, length=200)
            scale.pack(side=tk.LEFT, padx=10)
            ttk.Label(row, textvariable=var, width=5).pack(side=tk.LEFT)
        
        # 风格描述
        desc_frame = ttk.LabelFrame(dialog, text="风格描述（可选）", padding=10)
        desc_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        desc_text = tk.Text(desc_frame, wrap=tk.WORD, height=5,
                           font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
                           bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
        desc_text.pack(fill=tk.BOTH, expand=True)
        desc_text.insert("1.0", "描述这种风格的特点，如：华丽、简洁、幽默、严肃等...")
        
        # 按钮
        btn_frame = ttk.Frame(dialog, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=20, pady=20)
        
        def create_style():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("警告", "请输入风格名称！")
                return
            
            # 获取评分
            scores = {key: var.get() for key, var in dim_vars.items()}
            
            # 添加到风格档案库
            self._style_tree.insert("", tk.END, values=(
                name,
                f"{scores['vocabulary']:.1f}",
                f"{scores['sentence']:.1f}",
                f"{scores['rhetoric']:.1f}",
                f"{scores['emotion']:.1f}",
                f"{scores['rhythm']:.1f}",
                f"{scores['structure']:.1f}",
                f"{scores['detail']:.1f}"
            ))
            
            # 更新分析器显示
            self._style_info.delete("1.0", tk.END)
            self._style_info.insert("1.0", f"""【{name}】风格模板

词汇：{"█" * int(scores['vocabulary'])}{"░" * (10 - int(scores['vocabulary']))} {scores['vocabulary']:.1f}
句式：{"█" * int(scores['sentence'])}{"░" * (10 - int(scores['sentence']))} {scores['sentence']:.1f}
修辞：{"█" * int(scores['rhetoric'])}{"░" * (10 - int(scores['rhetoric']))} {scores['rhetoric']:.1f}
情感：{"█" * int(scores['emotion'])}{"░" * (10 - int(scores['emotion']))} {scores['emotion']:.1f}
节奏：{"█" * int(scores['rhythm'])}{"░" * (10 - int(scores['rhythm']))} {scores['rhythm']:.1f}
结构：{"█" * int(scores['structure'])}{"░" * (10 - int(scores['structure']))} {scores['structure']:.1f}
细节：{"█" * int(scores['detail'])}{"░" * (10 - int(scores['detail']))} {scores['detail']:.1f}

描述：{desc_text.get("1.0", tk.END).strip()}
""")
            
            self._set_status(f"已创建风格模板：{name}")
            dialog.destroy()
        
        ttk.Button(btn_frame, text="创建", command=create_style).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def _on_style_apply(self):
        """应用到生成器"""
        self._set_status("应用到生成器功能开发中...")
    
    def _on_style_clear(self):
        """清除风格"""
        self._style_path_var.set("未导入")
        self._style_info.delete("1.0", tk.END)
    
    def _on_start_generation(self):
        """开始生成 - 调用小说生成流水线"""
        try:
            # 导入生成服务
            from agents.novel_generation_service import get_generation_service
            
            # 获取生成配置
            chapter_number = int(self._start_chapter_var.get())
            end_chapter = int(self._end_chapter_var.get())
            target_words = int(self._target_words_var.get())
            temperature = self._gen_temp_var.get()
            
            # 获取大纲内容（从大纲管理页面获取或使用默认值）
            outline_content = self._get_outline_content()
            chapter_outline = self._get_chapter_outline(chapter_number)
            
            # 获取风格档案（从风格学习页面获取）
            style_profile = self._get_style_profile()
            
            # 获取人物设定
            characters = self._get_characters()
            
            # 获取世界观设定
            worldview = self._get_worldview()
            
            # 更新UI状态
            self._gen_status_var.set(f"正在生成第{chapter_number}章...")
            self._gen_progress['value'] = 0
            self._gen_log.delete("1.0", tk.END)
            self._gen_log.insert(tk.END, f"开始生成第{chapter_number}章...\n")
            self._gen_log.insert(tk.END, f"目标字数: {target_words}\n")
            self._gen_log.insert(tk.END, f"生成温度: {temperature}\n")
            self._gen_log.insert(tk.END, "-" * 40 + "\n")
            
            # 获取LLM客户端
            llm_client = self._get_llm_client()
            
            # 获取生成服务
            service = get_generation_service(
                event_bus=getattr(self, '_event_bus', None),
                llm_client=llm_client,
            )
            
            # 添加进度回调
            def on_progress(progress):
                # 使用root.after确保UI线程安全
                self.root.after(0, lambda: self._update_generation_progress(progress))
            
            service.add_progress_callback(on_progress)
            
            # 定义完成回调
            def on_complete(result):
                self.root.after(0, lambda: self._on_generation_complete(result))
            
            # 调用生成服务
            pipeline_id = service.generate_chapter(
                chapter_title=f"第{chapter_number}章",
                chapter_number=chapter_number,
                outline_content=outline_content,
                chapter_outline=chapter_outline,
                target_word_count=target_words,
                style_profile=style_profile,
                characters=characters,
                worldview=worldview,
                previous_chapter_text="",  # TODO: 从历史章节获取
                max_iterations=5,
                callback=on_complete,
            )
            
            self._current_pipeline_id = pipeline_id
            self._set_status(f"正在生成第{chapter_number}章...")
            
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("生成错误", f"启动生成失败: {str(e)}")
            self._gen_status_var.set("生成失败")
            self._set_status(f"生成失败: {str(e)}")
    
    def _on_stop_generation(self):
        """停止生成"""
        try:
            from agents.novel_generation_service import get_generation_service
            service = get_generation_service()
            if service.cancel_generation():
                self._gen_status_var.set("已取消生成")
                self._gen_log.insert(tk.END, "\n用户取消生成\n")
                self._set_status("已停止生成")
            else:
                self._set_status("没有正在进行的生成任务")
        except Exception as e:
            self._set_status(f"停止生成失败: {str(e)}")
    
    def _update_generation_progress(self, progress):
        """更新生成进度（UI线程安全）"""
        try:
            self._gen_progress['value'] = progress.progress_percent
            self._gen_log.insert(tk.END, f"[{progress.stage_name}] {progress.message}\n")
            self._gen_log.see(tk.END)  # 自动滚动到底部
        except Exception as e:
            pass  # 忽略UI更新错误
    
    def _on_generation_complete(self, result):
        """生成完成回调（UI线程安全）"""
        try:
            if result.success:
                self._gen_status_var.set("生成完成")
                self._gen_progress['value'] = 100
                self._gen_log.insert(tk.END, "\n" + "=" * 40 + "\n")
                self._gen_log.insert(tk.END, f"生成完成！总迭代次数: {result.total_iterations}\n")
                self._gen_log.insert(tk.END, f"总耗时: {result.total_duration_seconds:.1f}秒\n")
                
                # 显示生成结果
                if result.final_output:
                    content = result.final_output.get("content", str(result.final_output))
                    self._gen_result.delete("1.0", tk.END)
                    self._gen_result.insert("1.0", content)
                    
                    # 更新字数统计
                    word_count = len(content)
                    self._gen_log.insert(tk.END, f"实际字数: {word_count}\n")
                
                self._set_status(f"第{result.stages[0].iteration if result.stages else 1}章生成完成")
            else:
                self._gen_status_var.set("生成失败")
                self._gen_log.insert(tk.END, f"\n生成失败: {result.error}\n")
                self._set_status(f"生成失败: {result.error}")
            
            self._gen_log.see(tk.END)
            
        except Exception as e:
            self._gen_status_var.set("处理结果出错")
            self._gen_log.insert(tk.END, f"\n处理生成结果时出错: {str(e)}\n")
    
    def _get_outline_content(self) -> str:
        """获取大纲内容"""
        # TODO: 从大纲管理页面或文件获取
        return getattr(self, '_outline_content', "")
    
    def _get_chapter_outline(self, chapter_number: int) -> str:
        """获取指定章节的大纲"""
        # TODO: 从大纲管理页面获取
        return getattr(self, '_chapter_outlines', {}).get(chapter_number, "")
    
    def _get_style_profile(self) -> dict:
        """获取风格档案"""
        # TODO: 从风格学习页面获取
        return getattr(self, '_style_profile', {})
    
    def _get_characters(self) -> list:
        """获取人物设定"""
        # TODO: 从人物设定页面获取
        return getattr(self, '_characters', [])
    
    def _get_worldview(self) -> dict:
        """获取世界观设定"""
        # TODO: 从世界观页面获取
        return getattr(self, '_worldview', {})
    
    def _get_llm_client(self):
        """获取LLM客户端"""
        # 从配置或服务获取LLM客户端
        return getattr(self, '_llm_client', None)
    
    def _on_gen_browse(self):
        """分章浏览"""
        self._set_status("分章浏览功能开发中...")
    
    def _on_gen_save(self):
        """保存项目 - 完整实现"""
        if not self.current_project or not self.project_file:
            messagebox.showwarning("保存项目", "当前没有打开的项目")
            return
        
        try:
            self._set_status("正在保存项目...")
            
            # 更新修改时间
            self.current_project['modified_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 保存项目文件
            with open(self.project_file, 'w', encoding='utf-8') as f:
                json.dump(self.current_project, f, ensure_ascii=False, indent=2)
            
            self._set_status("项目保存完成")
            messagebox.showinfo("成功", "项目已保存！")
            
        except Exception as e:
            messagebox.showerror("错误", f"保存项目失败: {e}")
            self._set_status("保存项目失败")
    
    def _on_gen_export_txt(self):
        """导出TXT"""
        self._set_status("导出TXT功能开发中...")
    
    def _on_gen_export_docx(self):
        """导出DOCX"""
        self._set_status("导出DOCX功能开发中...")
    
    def _on_reverse_browse(self):
        """浏览逆向分析文件（已弃用，保留兼容）"""
        path = filedialog.askopenfilename(
            title="选择需要分析的文件",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx"), ("所有文件", "*.*")]
        )
        if path:
            self._on_reverse_add_chapter_from_file(path)
    
    def _on_reverse_upload_files(self):
        """上传单个或多个章节文件"""
        paths = filedialog.askopenfilenames(
            title="选择章节文件",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx"), ("所有文件", "*.*")]
        )
        if paths:
            for path in paths:
                self._on_reverse_add_chapter_from_file(path)
            self._set_status(f"已上传 {len(paths)} 个章节文件")
    
    def _on_reverse_batch_upload(self):
        """批量上传文件夹中的所有章节"""
        folder = filedialog.askdirectory(title="选择章节文件夹")
        if folder:
            count = 0
            for filename in os.listdir(folder):
                if filename.endswith(('.txt', '.docx')):
                    path = os.path.join(folder, filename)
                    self._on_reverse_add_chapter_from_file(path)
                    count += 1
            self._set_status(f"已从文件夹批量上传 {count} 个章节")
    
    def _on_reverse_paste_text(self):
        """切换粘贴文本区域的显示/隐藏"""
        if self._paste_text_frame.winfo_ismapped():
            self._paste_text_frame.pack_forget()
        else:
            self._paste_text_frame.pack(fill=tk.X, pady=5)
    
    def _on_reverse_add_pasted_chapter(self):
        """添加粘贴的章节"""
        title = self._paste_title_var.get().strip()
        content = self._paste_content_text.get("1.0", tk.END).strip()
        
        if not title:
            messagebox.showwarning("提示", "请输入章节标题")
            return
        if not content:
            messagebox.showwarning("提示", "请输入章节内容")
            return
        
        # 计算字数
        word_count = len(content.replace('\n', '').replace(' ', ''))
        
        # 生成唯一ID
        chapter_id = f"chapter_{int(time.time() * 1000)}"
        
        # 存储章节数据
        self._reverse_chapters[chapter_id] = {
            'title': title,
            'content': content,
            'words': word_count,
            'status': '未完成',
            'source': '粘贴'
        }
        
        # 添加到列表
        idx = len(self._completed_chapters_tree.get_children()) + 1
        self._completed_chapters_tree.insert("", tk.END, iid=chapter_id, values=(
            f"第{idx}章",
            title,
            f"{word_count}字",
            "未完成",
            "粘贴"
        ))
        
        # 清空输入
        self._paste_title_var.set("")
        self._paste_content_text.delete("1.0", tk.END)
        
        self._set_status(f"已添加章节：{title}")
    
    def _on_reverse_add_chapter_from_file(self, file_path: str):
        """从文件添加章节"""
        try:
            # 读取文件内容
            if file_path.endswith('.docx'):
                content = self._read_docx_file(file_path)
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            # 提取标题（从文件名或内容首行）
            title = os.path.basename(file_path).rsplit('.', 1)[0]
            if content.startswith('#') or content.startswith('第'):
                first_line = content.split('\n')[0]
                if len(first_line) < 50:
                    title = first_line.strip('# ')
            
            # 计算字数
            word_count = len(content.replace('\n', '').replace(' ', ''))
            
            # 生成唯一ID
            chapter_id = f"file_{int(time.time() * 1000)}_{len(self._reverse_chapters)}"
            
            # 存储章节数据
            self._reverse_chapters[chapter_id] = {
                'title': title,
                'content': content,
                'words': word_count,
                'status': '未完成',
                'source': os.path.basename(file_path),
                'file_path': file_path
            }
            
            # 添加到列表
            idx = len(self._completed_chapters_tree.get_children()) + 1
            self._completed_chapters_tree.insert("", tk.END, iid=chapter_id, values=(
                f"第{idx}章",
                title,
                f"{word_count}字",
                "未完成",
                os.path.basename(file_path)
            ))
            
        except Exception as e:
            self._set_status(f"读取文件失败：{str(e)}")
            logger.error(f"读取章节文件失败: {e}")
    
    def _read_docx_file(self, file_path: str) -> str:
        """读取DOCX文件内容"""
        try:
            from docx import Document
            doc = Document(file_path)
            return '\n'.join([para.text for para in doc.paragraphs])
        except ImportError:
            messagebox.showwarning("提示", "需要安装python-docx库才能读取DOCX文件")
            return ""
    
    def _on_reverse_refresh_chapters(self):
        """刷新章节列表"""
        # 重新统计并更新列表
        for item in self._completed_chapters_tree.get_children():
            if item in self._reverse_chapters:
                chapter_data = self._reverse_chapters[item]
                values = list(self._completed_chapters_tree.item(item, "values"))
                values[2] = f"{chapter_data['words']}字"
                values[3] = chapter_data['status']
                self._completed_chapters_tree.item(item, values=values)
        
        total_words = sum(c['words'] for c in self._reverse_chapters.values())
        self._set_status(f"已刷新列表，共 {len(self._reverse_chapters)} 章，{total_words} 字")
    
    def _on_reverse_clear_chapters(self):
        """清空章节列表"""
        if messagebox.askyesno("确认", "确定要清空所有章节吗？"):
            self._completed_chapters_tree.delete(*self._completed_chapters_tree.get_children())
            self._reverse_chapters.clear()
            self._set_status("已清空章节列表")
    
    def _on_reverse_chapter_select(self, event):
        """章节选择事件"""
        selected = self._completed_chapters_tree.selection()
        if selected:
            count = len(selected)
            total_words = 0
            for item in selected:
                if item in self._reverse_chapters:
                    total_words += self._reverse_chapters[item]['words']
            self._set_status(f"已选择 {count} 章，共 {total_words} 字")
    
    def _on_reverse_view_chapter(self):
        """查看章节内容"""
        selected = self._completed_chapters_tree.selection()
        if not selected:
            return
        
        item = selected[0]
        if item not in self._reverse_chapters:
            return
        
        chapter_data = self._reverse_chapters[item]
        
        # 创建查看窗口
        view_window = tk.Toplevel(self.root)
        view_window.title(f"查看章节：{chapter_data['title']}")
        view_window.geometry("600x400")
        
        text = tk.Text(view_window, wrap=tk.WORD, font=('Microsoft YaHei UI', 10))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text.insert("1.0", chapter_data['content'])
        text.configure(state=tk.DISABLED)
    
    def _on_reverse_run_analysis(self):
        """运行逆向分析"""
        # 获取要分析的章节
        scope = self._reverse_scope_var.get()
        chapters_to_analyze = []
        
        if scope == "selected":
            selected = self._completed_chapters_tree.selection()
            for item in selected:
                if item in self._reverse_chapters:
                    chapters_to_analyze.append({
                        'id': item,
                        **self._reverse_chapters[item]
                    })
            if not chapters_to_analyze:
                messagebox.showwarning("提示", "请先选择要分析的章节")
                return
        elif scope == "completed":
            for item_id, chapter in self._reverse_chapters.items():
                if chapter['status'] == '已完成':
                    chapters_to_analyze.append({
                        'id': item_id,
                        **chapter
                    })
            if not chapters_to_analyze:
                messagebox.showwarning("提示", "没有已完成的章节可供分析")
                return
        else:  # all
            for item_id, chapter in self._reverse_chapters.items():
                chapters_to_analyze.append({
                    'id': item_id,
                    **chapter
                })
            if not chapters_to_analyze:
                messagebox.showwarning("提示", "章节列表为空，请先上传章节")
                return
        
        # 获取分析维度
        analysis_options = {
            'consistency': self._reverse_check_consistency.get(),
            'logic': self._reverse_check_logic.get(),
            'character': self._reverse_check_character.get(),
            'style': self._reverse_check_style.get(),
            'worldview': self._reverse_check_worldview.get(),
        }
        
        # 更新进度提示
        self._analysis_progress_label.configure(text="正在分析中...")
        self._run_analysis_btn.configure(state=tk.DISABLED)
        self.root.update()
        
        # 异步执行分析
        def run_analysis():
            try:
                # 获取插件
                plugin = self._get_reverse_feedback_plugin()
                if not plugin:
                    self.root.after(0, lambda: self._analysis_progress_label.configure(
                        text="分析插件不可用"))
                    return
                
                # 获取项目设定
                settings = self._get_current_project_settings()
                
                # 分析结果
                all_issues = []
                
                for chapter in chapters_to_analyze:
                    result = plugin.analyze_chapter_vs_settings(
                        chapter_text=chapter['content'],
                        current_settings=settings,
                        chapter_id=chapter['title']
                    )
                    all_issues.extend(result.issues)
                
                # 保存结果
                self._reverse_analysis_result = {
                    'issues': all_issues,
                    'chapters_analyzed': len(chapters_to_analyze),
                    'analysis_options': analysis_options
                }
                
                # 更新UI
                self.root.after(0, lambda: self._update_analysis_result())
                
            except Exception as e:
                logger.error(f"分析失败: {e}")
                self.root.after(0, lambda: self._analysis_progress_label.configure(
                    text=f"分析失败: {str(e)}"))
            finally:
                self.root.after(0, lambda: self._run_analysis_btn.configure(state=tk.NORMAL))
        
        threading.Thread(target=run_analysis, daemon=True).start()
    
    def _load_reverse_feedback_plugin(self):
        """加载逆向反馈插件"""
        try:
            # 尝试从PluginRegistry获取
            registry = get_plugin_registry()
            if registry:
                plugin = registry.get_plugin("reverse-feedback-analyzer")
                if plugin:
                    self._reverse_feedback_plugin = plugin
                    self._set_status("逆向反馈插件加载成功")
                    logger.info("逆向反馈插件从Registry加载成功")
                    return
            
            # 动态导入插件
            from plugins.reverse_feedback_analyzer.reverse_feedback_analyzer import ReverseFeedbackAnalyzer
            from core.plugin_interface import PluginContext
            
            self._reverse_feedback_plugin = ReverseFeedbackAnalyzer()
            
            # 创建上下文并初始化
            context = PluginContext(
                config_manager=self._config_manager if hasattr(self, '_config_manager') else None,
                event_bus=None,
                service_locator=None,
                v5_modules=None
            )
            self._reverse_feedback_plugin.initialize(context)
            
            self._set_status("逆向反馈插件加载成功")
            logger.info("逆向反馈插件加载成功")
            
        except Exception as e:
            logger.error(f"加载逆向反馈插件失败: {e}")
            self._reverse_feedback_plugin = None
    
    def _get_reverse_feedback_plugin(self):
        """获取逆向反馈分析插件"""
        try:
            # 尝试从PluginRegistry获取
            registry = get_plugin_registry()
            if registry:
                plugin = registry.get_plugin("reverse-feedback-analyzer")
                if plugin:
                    return plugin
            
            # 动态创建插件实例
            from plugins.reverse_feedback_analyzer.reverse_feedback_analyzer import ReverseFeedbackAnalyzer
            from core.plugin_interface import PluginContext
            plugin = ReverseFeedbackAnalyzer()
            
            # 创建简化的上下文
            context = PluginContext(
                config_manager=self._config_manager if hasattr(self, '_config_manager') else None,
                event_bus=None,
                service_locator=None,
                v5_modules=None
            )
            plugin.initialize(context)
            return plugin
        except Exception as e:
            logger.error(f"获取逆向反馈插件失败: {e}")
            return None
    
    def _get_current_project_settings(self) -> Dict:
        """获取当前项目设定"""
        settings = {
            'project_name': getattr(self, '_current_project_name', '未命名项目'),
            'outline': getattr(self, '_outline_content', ''),
            'characters': getattr(self, '_character_data', []),
            'worldview': getattr(self, '_worldview_content', ''),
        }
        return settings
    
    def _update_analysis_result(self):
        """更新分析结果显示"""
        if not self._reverse_analysis_result:
            return
        
        # 清空冲突列表
        self._issues_tree.delete(*self._issues_tree.get_children())
        
        issues = self._reverse_analysis_result.get('issues', [])
        
        # 类型映射
        type_map = {
            'character': '人物',
            'outline': '大纲',
            'worldview': '世界观',
        }
        
        # 优先级映射
        severity_map = {
            'high': '🔴 高',
            'medium': '🟡 中',
            'low': '🟢 低',
        }
        
        for issue in issues:
            issue_type = getattr(issue, 'issue_type', 'outline')
            if hasattr(issue_type, 'value'):
                issue_type = issue_type.value
            
            severity = getattr(issue, 'severity', 'medium')
            if hasattr(severity, 'value'):
                severity = severity.value
            
            self._issues_tree.insert("", tk.END, values=(
                type_map.get(issue_type, issue_type),
                severity_map.get(severity, severity),
                getattr(issue, 'element_name', ''),
                getattr(issue, 'chapter_reference', ''),
                getattr(issue, 'description', '')[:50] + '...' if len(getattr(issue, 'description', '')) > 50 else getattr(issue, 'description', '')
            ))
        
        # 更新进度提示
        high_count = sum(1 for i in issues if getattr(i, 'severity', None) and 
                        (getattr(i.severity, 'value', i.severity) == 'high'))
        
        self._analysis_progress_label.configure(
            text=f"分析完成：共 {len(issues)} 个冲突，{high_count} 个高优先级"
        )
        self._set_status(f"分析完成，发现 {len(issues)} 个冲突项")
    
    def _on_reverse_issue_select(self, event):
        """冲突项选择事件"""
        selected = self._issues_tree.selection()
        if not selected or not self._reverse_analysis_result:
            return
        
        # 获取选中的问题索引
        idx = self._issues_tree.index(selected[0])
        issues = self._reverse_analysis_result.get('issues', [])
        
        if idx >= len(issues):
            return
        
        issue = issues[idx]
        
        # 显示详情
        self._issue_detail_text.configure(state=tk.NORMAL)
        self._issue_detail_text.delete("1.0", tk.END)
        
        detail = f"""【冲突详情】

类型：{getattr(issue, 'issue_type', '未知')}
严重程度：{getattr(issue, 'severity', '未知')}
涉及元素：{getattr(issue, 'element_name', '未知')}
章节引用：{getattr(issue, 'chapter_reference', '未知')}

【问题描述】
{getattr(issue, 'description', '无描述')}

【原始设定】
{getattr(issue, 'original_content', '无')}

【修正建议】
{getattr(issue, 'suggested_fix', '无建议')}

【置信度】
{getattr(issue, 'confidence', 0) * 100:.0f}%
"""
        self._issue_detail_text.insert("1.0", detail)
        self._issue_detail_text.configure(state=tk.DISABLED)
    
    def _on_reverse_issue_double_click(self, event):
        """双击冲突项，打开详情窗口"""
        self._on_reverse_issue_select(event)
        
        # 获取详情内容
        detail = self._issue_detail_text.get("1.0", tk.END)
        
        # 创建详情窗口
        detail_window = tk.Toplevel(self.root)
        detail_window.title("冲突详情")
        detail_window.geometry("500x400")
        
        text = tk.Text(detail_window, wrap=tk.WORD, font=('Microsoft YaHei UI', 10))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text.insert("1.0", detail)
        text.configure(state=tk.DISABLED)
    
    def _on_reverse_apply_fix(self):
        """应用修正"""
        if not self._reverse_analysis_result:
            messagebox.showwarning("提示", "请先运行分析")
            return
        
        issues = self._reverse_analysis_result.get('issues', [])
        if not issues:
            messagebox.showinfo("提示", "没有需要修正的冲突项")
            return
        
        # 确认对话框
        high_count = sum(1 for i in issues if getattr(i, 'severity', None) and 
                        (getattr(i.severity, 'value', i.severity) == 'high'))
        
        msg = f"发现 {len(issues)} 个冲突项（{high_count} 个高优先级）\n\n是否应用修正？"
        if not messagebox.askyesno("确认修正", msg):
            return
        
        # 获取插件
        plugin = self._get_reverse_feedback_plugin()
        if not plugin:
            messagebox.showerror("错误", "逆向反馈插件不可用")
            return
        
        # 生成修正
        settings = self._get_current_project_settings()
        
        # 创建简化的报告对象
        from core.plugin_interface import ConsistencyReport
        report = ConsistencyReport(project_name=settings.get('project_name', ''))
        report.issues = issues
        
        corrections = plugin.generate_corrections(report, settings)
        
        # 显示修正结果
        self._issue_detail_text.configure(state=tk.NORMAL)
        self._issue_detail_text.delete("1.0", tk.END)
        
        correction_text = "【修正完成】\n\n"
        for suggestion in corrections.get('suggestions', []):
            correction_text += f"• {suggestion}\n"
        
        correction_text += "\n【备份信息】\n"
        if corrections.get('backup'):
            correction_text += f"备份时间：{corrections['backup'].get('backup_time', '未知')}\n"
        
        self._issue_detail_text.insert("1.0", correction_text)
        self._issue_detail_text.configure(state=tk.DISABLED)
        
        # 更新项目设定（如果用户确认）
        if messagebox.askyesno("应用修正", "是否将修正应用到当前项目设定？"):
            self._apply_corrections_to_project(corrections)
        
        self._set_status("修正已应用")
    
    def _apply_corrections_to_project(self, corrections: Dict):
        """将修正应用到项目设定"""
        # 更新大纲
        if corrections.get('updated_outline'):
            self._outline_content = corrections['updated_outline']
        
        # 更新人物
        if corrections.get('updated_characters'):
            self._character_data = corrections['updated_characters']
        
        # 刷新项目管理器
        self._refresh_project_manager()
    
    def _refresh_project_manager(self):
        """刷新项目管理器"""
        # 切换到项目管理页面更新显示
        self._set_status("项目设定已更新")
    
    def _on_reverse_export_report(self):
        """导出分析报告"""
        if not self._reverse_analysis_result:
            messagebox.showwarning("提示", "没有分析结果可导出")
            return
        
        path = filedialog.asksaveasfilename(
            title="保存分析报告",
            defaultextension=".md",
            filetypes=[("Markdown文件", "*.md"), ("文本文件", "*.txt")]
        )
        
        if path:
            try:
                issues = self._reverse_analysis_result.get('issues', [])
                
                report = f"""# 逆向反馈分析报告

生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}
分析章节数：{self._reverse_analysis_result.get('chapters_analyzed', 0)}
冲突总数：{len(issues)}

## 冲突列表

"""
                for i, issue in enumerate(issues, 1):
                    severity = getattr(issue, 'severity', 'medium')
                    if hasattr(severity, 'value'):
                        severity = severity.value
                    
                    report += f"""### {i}. {getattr(issue, 'element_name', '未知')}

- **类型**：{getattr(issue, 'issue_type', '未知')}
- **严重程度**：{severity}
- **章节**：{getattr(issue, 'chapter_reference', '未知')}
- **描述**：{getattr(issue, 'description', '')}
- **修正建议**：{getattr(issue, 'suggested_fix', '')}

"""
                
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(report)
                
                self._set_status(f"报告已导出：{path}")
                
            except Exception as e:
                messagebox.showerror("错误", f"导出失败：{str(e)}")
    
    def _on_reverse_clear_result(self):
        """清除分析结果"""
        self._issues_tree.delete(*self._issues_tree.get_children())
        self._issue_detail_text.configure(state=tk.NORMAL)
        self._issue_detail_text.delete("1.0", tk.END)
        self._issue_detail_text.insert("1.0", "选择冲突项查看详细修正建议...")
        self._issue_detail_text.configure(state=tk.DISABLED)
        self._reverse_analysis_result = None
        self._analysis_progress_label.configure(text="")
        self._set_status("已清除分析结果")
    
    # 兼容旧方法
    def _on_reverse_run(self):
        """运行分析（兼容旧方法）"""
        self._on_reverse_run_analysis()
    
    def _on_reverse_analyze(self):
        """开始逆向分析（兼容旧方法）"""
        self._on_reverse_run_analysis()
    
    def _on_reverse_apply(self):
        """自动修正（兼容旧方法）"""
        self._on_reverse_apply_fix()
    
    def _on_reverse_outline(self):
        """调整大纲细节"""
        self._set_status("调整大纲细节功能开发中...")
    
    def _on_reverse_character(self):
        """修改人物性格"""
        self._set_status("修改人物性格功能开发中...")
    
    def _on_reverse_trajectory(self):
        """补充人物轨迹"""
        self._set_status("补充人物轨迹功能开发中...")
    
    def _on_reverse_worldview(self):
        """增减世界观设定"""
        self._set_status("增减世界观设定功能开发中...")
    
    def _on_quick_generate(self):
        """快捷生成（保留兼容）"""
        self._on_quick_generate_all()
    
    def _on_quick_generate_all(self):
        """一键生成全部四个结果"""
        # 延迟加载插件
        if not hasattr(self, '_quick_creator_plugin') or not self._quick_creator_plugin:
            self._load_quick_creator_plugin()
            if not self._quick_creator_plugin:
                messagebox.showerror("错误", "快捷创作插件未加载，请先配置AI服务")
                return
        
        # 获取关键词
        keywords = self._quick_input.get("1.0", tk.END).strip()
        if not keywords or keywords == "请输入关键词描述...":
            messagebox.showwarning("提示", "请输入创作关键词")
            return
        
        # 获取详细程度
        detail = self._quick_detail_var.get()
        
        # 线程安全：获取参考文本
        with self._quick_lock:
            reference_texts = {}
            for file_data in self._quick_uploaded_files:
                ref_type = file_data["type"]
                if ref_type not in reference_texts:
                    reference_texts[ref_type] = []
                reference_texts[ref_type].append(file_data["content"])
        
        # 禁用生成按钮
        self._quick_gen_all_btn.configure(state=tk.DISABLED)
        self._set_status("正在生成全部设定...")
        
        # 在后台线程执行
        def generate_task():
            try:
                from core.models import QuickCreationRequest
                
                # 创建请求
                request = QuickCreationRequest(
                    keywords=keywords,
                    detail_level=detail,
                    reference_worldview="\n\n".join(reference_texts.get("worldview", [])),
                    reference_outline="\n\n".join(reference_texts.get("outline", [])),
                    reference_characters="\n\n".join(reference_texts.get("characters", [])),
                    reference_plot="\n\n".join(reference_texts.get("plot", []))
                )
                
                # 调用插件生成
                result = self._quick_creator_plugin.generate_all(request)
                
                # 更新UI
                if result.success:
                    # 世界观
                    if result.worldview:
                        self.root.after(0, lambda: self._update_quick_result("worldview", result.worldview.content))
                    
                    # 大纲
                    if result.outline:
                        self.root.after(0, lambda: self._update_quick_result("outline", result.outline.content))
                    
                    # 人设
                    if result.characters:
                        self.root.after(0, lambda: self._update_quick_result("characters", result.characters.content))
                    
                    # 情节
                    if result.plot:
                        self.root.after(0, lambda: self._update_quick_result("plot", result.plot.content))
                    
                    self.root.after(0, lambda: self._set_status("生成完成"))
                else:
                    self.root.after(0, lambda: messagebox.showerror("错误", f"生成失败：{result.error}"))
                    self.root.after(0, lambda: self._set_status("生成失败"))
                
            except Exception as e:
                logger.error(f"快捷生成异常: {e}", exc_info=True)
                self.root.after(0, lambda: messagebox.showerror("错误", f"生成异常：{e}"))
                self.root.after(0, lambda: self._set_status("生成异常"))
            finally:
                # 恢复按钮
                self.root.after(0, lambda: self._quick_gen_all_btn.configure(state=tk.NORMAL))
        
        # 启动后台线程
        if CORE_AVAILABLE:
            self._async_handler.submit(generate_task, priority=TaskPriority.NORMAL)
        else:
            threading.Thread(target=generate_task, daemon=True).start()
    
    def _on_quick_generate_single(self, gen_type: str):
        """生成单个结果"""
        # 延迟加载插件
        if not hasattr(self, '_quick_creator_plugin') or not self._quick_creator_plugin:
            self._load_quick_creator_plugin()
            if not self._quick_creator_plugin:
                messagebox.showerror("错误", "快捷创作插件未加载")
                return
        
        # 获取关键词
        keywords = self._quick_input.get("1.0", tk.END).strip()
        if not keywords or keywords == "请输入关键词描述...":
            messagebox.showwarning("提示", "请输入创作关键词")
            return
        
        # 获取详细程度
        detail = self._quick_detail_var.get()
        
        # 线程安全：获取参考文本
        with self._quick_lock:
            reference_texts = {}
            for file_data in self._quick_uploaded_files:
                ref_type = file_data["type"]
                if ref_type not in reference_texts:
                    reference_texts[ref_type] = []
                reference_texts[ref_type].append(file_data["content"])
        
        type_names = {
            "worldview": "世界观",
            "outline": "大纲",
            "characters": "人设",
            "plot": "关键情节"
        }
        
        self._set_status(f"正在生成{type_names.get(gen_type, '')}...")
        
        # 在后台线程执行
        def generate_task():
            try:
                # 根据类型调用对应的生成方法
                if gen_type == "worldview":
                    result = self._quick_creator_plugin.generate_worldview(
                        keywords=keywords,
                        detail_level=detail,
                        reference_text="\n\n".join(reference_texts.get("worldview", []))
                    )
                    if result.success:
                        self.root.after(0, lambda: self._update_quick_result("worldview", result.content))
                
                elif gen_type == "outline":
                    result = self._quick_creator_plugin.generate_outline(
                        keywords=keywords,
                        detail_level=detail,
                        reference_text="\n\n".join(reference_texts.get("outline", []))
                    )
                    if result.success:
                        self.root.after(0, lambda: self._update_quick_result("outline", result.content))
                
                elif gen_type == "characters":
                    result = self._quick_creator_plugin.generate_character(
                        keywords=keywords,
                        detail_level=detail,
                        reference_text="\n\n".join(reference_texts.get("characters", []))
                    )
                    if result.success:
                        self.root.after(0, lambda: self._update_quick_result("characters", result.content))
                
                elif gen_type == "plot":
                    result = self._quick_creator_plugin.generate_plot(
                        keywords=keywords,
                        detail_level=detail,
                        reference_text="\n\n".join(reference_texts.get("plot", []))
                    )
                    if result.success:
                        self.root.after(0, lambda: self._update_quick_result("plot", result.content))
                
                self.root.after(0, lambda: self._set_status(f"{type_names.get(gen_type, '')}生成完成"))
                
            except Exception as e:
                logger.error(f"生成异常: {e}", exc_info=True)
                self.root.after(0, lambda: messagebox.showerror("错误", f"生成异常：{e}"))
                self.root.after(0, lambda: self._set_status("生成异常"))
        
        # 启动后台线程
        if CORE_AVAILABLE:
            self._async_handler.submit(generate_task, priority=TaskPriority.NORMAL)
        else:
            threading.Thread(target=generate_task, daemon=True).start()
    
    def _update_quick_result(self, result_type: str, content: str):
        """更新快捷创作结果"""
        if result_type in self._quick_result_texts:
            text_widget = self._quick_result_texts[result_type]
            text_widget.configure(state=tk.NORMAL)
            text_widget.delete("1.0", tk.END)
            text_widget.insert("1.0", content)
            text_widget.configure(state=tk.NORMAL)
    
    def _on_quick_upload_file(self, file_type: str):
        """上传参考文本文件
        
        Args:
            file_type: 文件类型（worldview/outline/characters/plot）
        """
        path = filedialog.askopenfilename(
            title=f"选择{file_type}参考文本",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx"), ("所有文件", "*.*")]
        )
        if not path:
            return
        
        try:
            # 读取文件内容
            if path.lower().endswith('.docx'):
                from docx import Document
                doc = Document(path)
                content = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            # 计算字数
            word_count = len(content.strip())
            
            # 线程安全：添加到上传列表
            file_data = {
                "path": path,
                "filename": os.path.basename(path),
                "type": file_type,
                "content": content,
                "word_count": word_count
            }
            with self._quick_lock:
                self._quick_uploaded_files.append(file_data)
            
            # 更新Treeview
            type_names = {
                "worldview": "世界观",
                "outline": "大纲",
                "characters": "人设",
                "plot": "情节"
            }
            self._quick_upload_tree.insert("", tk.END, values=(
                os.path.basename(path),
                type_names.get(file_type, file_type),
                f"{word_count}",
                "已上传"
            ))
            
            self._set_status(f"已上传：{os.path.basename(path)}（{word_count}字）")
            
        except Exception as e:
            messagebox.showerror("错误", f"上传失败：{e}")
    
    def _on_quick_remove_upload(self):
        """删除选中的上传文件"""
        selected = self._quick_upload_tree.selection()
        if not selected:
            return
        
        for item in selected:
            # 从Treeview删除
            self._quick_upload_tree.delete(item)
            
            # 从列表中删除（根据item索引）
            item_index = self._quick_upload_tree.get_children().index(item) if item in self._quick_upload_tree.get_children() else -1
            if 0 <= item_index < len(self._quick_uploaded_files):
                self._quick_uploaded_files.pop(item_index)
        
        self._set_status(f"已删除 {len(selected)} 个上传文件")
    
    def _on_quick_clear_uploads(self):
        """清空所有上传文件"""
        # 线程安全：清空列表
        with self._quick_lock:
            if not self._quick_uploaded_files:
                return
            self._quick_uploaded_files.clear()
        
        # 清空Treeview
        for item in self._quick_upload_tree.get_children():
            self._quick_upload_tree.delete(item)
        
        self._set_status("已清空所有上传文件")
    
    def _show_quick_upload_menu(self, event):
        """显示上传文件右键菜单"""
        item = self._quick_upload_tree.identify_row(event.y)
        if item:
            self._quick_upload_tree.selection_set(item)
            self._quick_upload_menu.post(event.x_root, event.y_root)
    
    def _show_chapters_context_menu(self, event):
        """显示已完成章节右键菜单"""
        # 选中点击项
        item = self._completed_chapters_tree.identify_row(event.y)
        if item:
            self._completed_chapters_tree.selection_set(item)
            self._chapters_context_menu.post(event.x_root, event.y_root)
    
    def _on_upload_chapter(self):
        """上传章节（兼容旧方法）"""
        self._on_reverse_upload_files()
    
    def _on_mark_chapter_completed(self):
        """标记章节为完成"""
        selected = self._completed_chapters_tree.selection()
        for item in selected:
            values = list(self._completed_chapters_tree.item(item, "values"))
            values[3] = "已完成"
            self._completed_chapters_tree.item(item, values=values)
        self._set_status(f"已标记 {len(selected)} 个章节为完成")
    
    def _on_mark_chapter_incomplete(self):
        """标记章节为未完成"""
        selected = self._completed_chapters_tree.selection()
        for item in selected:
            values = list(self._completed_chapters_tree.item(item, "values"))
            values[3] = "未完成"
            self._completed_chapters_tree.item(item, values=values)
        self._set_status(f"已标记 {len(selected)} 个章节为未完成")
    
    def _on_delete_completed_chapter(self):
        """删除已完成章节"""
        selected = self._completed_chapters_tree.selection()
        for item in selected:
            self._completed_chapters_tree.delete(item)
        self._set_status(f"已删除 {len(selected)} 个章节")
    
    def _on_mark_all_completed(self):
        """标记所有章节为完成"""
        for item in self._completed_chapters_tree.get_children():
            values = list(self._completed_chapters_tree.item(item, "values"))
            values[3] = "已完成"
            self._completed_chapters_tree.item(item, values=values)
        self._set_status("已标记所有章节为完成")
    
    def _on_quick_save_txt(self):
        """保存为TXT"""
        self._set_status("保存为TXT功能开发中...")
    
    def _on_quick_save_docx(self):
        """保存为DOCX"""
        self._set_status("保存为DOCX功能开发中...")
    
    def _on_quick_import(self):
        """导入当前项目"""
        if not hasattr(self, '_project_manager') or not self._project_manager:
            messagebox.showwarning("提示", "请先打开或创建项目")
            return
        
        # 获取所有结果内容
        content = {}
        for result_type, text_widget in self._quick_result_texts.items():
            content[result_type] = text_widget.get("1.0", tk.END).strip()
        
        # 检查是否有内容
        if not any(content.values()):
            messagebox.showwarning("提示", "没有可导入的内容")
            return
        
        # 创建导入确认对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("导入到当前项目")
        dialog.geometry("400x300")
        dialog.configure(bg=GlassTheme.GLASS_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 300) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 提示信息
        ttk.Label(dialog, text="选择要导入的内容：").pack(pady=10)
        
        # 复选框
        import_vars = {}
        for result_type, text in content.items():
            if text and not text.endswith("将在此显示..."):
                var = tk.BooleanVar(value=True)
                import_vars[result_type] = var
                type_names = {
                    "worldview": "🌍 世界观",
                    "outline": "📋 大纲",
                    "characters": "👤 人设",
                    "plot": "📖 情节"
                }
                ttk.Checkbutton(dialog, text=type_names.get(result_type, result_type), 
                               variable=var).pack(anchor=tk.W, padx=40, pady=5)
        
        # 按钮区
        btn_frame = ttk.Frame(dialog, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=20, pady=20)
        
        def on_import():
            try:
                imported_count = 0
                
                # 导入世界观
                if import_vars.get("worldview", tk.BooleanVar(value=False)).get():
                    self._project_manager.set_worldview(content["worldview"])
                    imported_count += 1
                
                # 导入大纲
                if import_vars.get("outline", tk.BooleanVar(value=False)).get():
                    self._project_manager.set_outline(content["outline"])
                    imported_count += 1
                
                # 导入人设
                if import_vars.get("characters", tk.BooleanVar(value=False)).get():
                    self._project_manager.set_characters(content["characters"])
                    imported_count += 1
                
                # 导入情节
                if import_vars.get("plot", tk.BooleanVar(value=False)).get():
                    self._project_manager.set_plot(content["plot"])
                    imported_count += 1
                
                self._set_status(f"已导入 {imported_count} 项设定到当前项目")
                messagebox.showinfo("成功", f"成功导入 {imported_count} 项设定")
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("错误", f"导入失败：{e}")
        
        ttk.Button(btn_frame, text="导入", command=on_import).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT)
    
    def _on_quick_export_results(self, export_format: str = "markdown"):
        """导出生成结果
        
        Args:
            export_format: 导出格式（markdown/json）
        """
        # 获取所有结果内容
        content = {}
        for result_type, text_widget in self._quick_result_texts.items():
            text = text_widget.get("1.0", tk.END).strip()
            # 过滤占位符文本
            if text and not text.endswith("将在此显示..."):
                content[result_type] = text
        
        # 检查是否有内容
        if not content:
            messagebox.showwarning("提示", "没有可导出的内容")
            return
        
        # 选择保存路径
        if export_format == "json":
            default_ext = ".json"
            filetypes = [("JSON文件", "*.json"), ("所有文件", "*.*")]
        else:
            default_ext = ".md"
            filetypes = [("Markdown文件", "*.md"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        
        save_path = filedialog.asksaveasfilename(
            title="选择保存位置",
            defaultextension=default_ext,
            filetypes=filetypes,
            initialfile="快捷创作结果"
        )
        
        if not save_path:
            return
        
        try:
            if export_format == "json":
                # JSON格式
                import json
                data = {
                    "生成时间": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "世界观设定": content.get("worldview", ""),
                    "章节大纲": content.get("outline", ""),
                    "人物设定": content.get("characters", ""),
                    "关键情节": content.get("plot", "")
                }
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                # Markdown格式
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write("# 快捷创作生成结果\n\n")
                    f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    
                    if "worldview" in content:
                        f.write("## 🌍 世界观设定\n\n")
                        f.write(content["worldview"] + "\n\n")
                    
                    if "outline" in content:
                        f.write("## 📋 章节大纲\n\n")
                        f.write(content["outline"] + "\n\n")
                    
                    if "characters" in content:
                        f.write("## 👤 人物设定\n\n")
                        f.write(content["characters"] + "\n\n")
                    
                    if "plot" in content:
                        f.write("## 📖 关键情节\n\n")
                        f.write(content["plot"] + "\n\n")
            
            self._set_status(f"已导出到：{os.path.basename(save_path)}")
            messagebox.showinfo("成功", f"导出成功！\n保存位置：{save_path}")
            
        except Exception as e:
            messagebox.showerror("错误", f"导出失败：{e}")
    
    def _on_continue_browse(self):
        """浏览续写原文文件"""
        path = filedialog.askopenfilename(
            title="选择原文文件",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx"), ("所有文件", "*.*")]
        )
        if path:
            try:
                if path.lower().endswith('.docx'):
                    from docx import Document
                    doc = Document(path)
                    text = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
                else:
                    with open(path, 'r', encoding='utf-8') as f:
                        text = f.read()
                self._continue_source.delete("1.0", tk.END)
                self._continue_source.insert("1.0", text)
                self._set_status(f"已导入: {os.path.basename(path)}")
            except Exception as e:
                self._set_status(f"导入失败: {e}")
    
    def _on_continue_generate(self):
        """开始续写"""
        # 检查插件
        if not hasattr(self, '_continuation_plugin') or not self._continuation_plugin:
            messagebox.showerror("错误", "续写插件未加载，请先配置AI服务")
            return
        
        # 获取原文
        source_text = self._continue_source.get("1.0", tk.END).strip()
        if not source_text or source_text == "请在此粘贴或输入原文内容，或选择文件导入...":
            messagebox.showwarning("提示", "请先输入或导入原文内容")
            return
        
        # 获取字数
        words_str = self._continue_words_var.get()
        if words_str == "自定义":
            try:
                word_count = int(self._custom_words_entry.get().strip())
                if word_count < 100 or word_count > 5000:
                    raise ValueError("字数超出范围")
            except ValueError as e:
                messagebox.showwarning("提示", f"请输入有效的字数（100-5000）\n错误：{e}")
                return
        else:
            word_count = int(words_str)
        
        # 获取续写方向
        direction_map = {
            "自然续写": "natural",
            "剧情推进": "action",
            "高潮铺垫": "action",
            "结局": "specific",
            "制造冲突": "specific",
            "引入新角色": "specific",
            "转折情节": "specific",
            "情感描写": "emotion",
            "动作场景": "action",
            "对话为主": "dialogue"
        }
        direction = direction_map.get(self._continue_direction_var.get(), "natural")
        
        # 获取温度
        temperature = self._continue_temp_var.get()
        
        # 获取生成模式
        is_multi_version = self._continue_mode_var.get() == "多版本生成"
        
        # 检查版本数量限制（最多5个版本）
        if is_multi_version and len(self._continue_versions) >= 5:
            messagebox.showwarning("提示", "已达到最大版本数量（5个），请先保存或清空版本")
            return
        
        # 清空历史版本（仅在首次生成时）
        if not self._continue_versions:
            self._continue_versions = []
            self._current_version_index = 0
            self._best_version_index = -1
        
        # 禁用按钮
        self._start_btn.configure(state=tk.DISABLED)
        self._regenerate_btn.configure(state=tk.DISABLED)
        self._select_best_btn.configure(state=tk.DISABLED)
        self._save_btn.configure(state=tk.DISABLED)
        
        # 清空结果框
        self._continue_result.delete("1.0", tk.END)
        self._version_info_label.configure(text="正在生成...")
        self._result_info_label.configure(text="字数：- | 耗时：- | 模型：-")
        self._score_label.configure(text="评分：-")
        
        # 在后台线程执行续写
        def generate_task():
            try:
                from core.models import ContinuationRequest
                
                # 获取上下文（如果有项目管理器）
                outline = None
                characters = None
                worldview = None
                style_profile = None
                previous_chapters = None
                
                if hasattr(self, '_project_manager') and self._project_manager:
                    # 从项目获取上下文
                    outline = self._project_manager.get_outline()
                    characters = self._project_manager.get_characters()
                    worldview = self._project_manager.get_worldview()
                    # 获取最近5章作为前文参考
                    previous_chapters = self._project_manager.get_recent_chapters(5)
                
                if is_multi_version:
                    # 多版本生成
                    self._set_status("正在生成多个版本...")
                    
                    # 计算可生成的版本数量（最多5个）
                    remaining_slots = 5 - len(self._continue_versions)
                    num_to_generate = min(3, remaining_slots)  # 每次最多生成3个
                    
                    if num_to_generate <= 0:
                        self.root.after(0, lambda: messagebox.showwarning("提示", "已达到最大版本数量（5个）"))
                        return
                    
                    # 根据剩余空间调整温度分布
                    if num_to_generate == 1:
                        temps = [temperature]
                    elif num_to_generate == 2:
                        temps = [max(0.5, temperature - 0.2), min(1.0, temperature + 0.2)]
                    else:
                        temps = [0.6, 0.8, 1.0]
                    
                    results = self._continuation_plugin.generate_multiple_versions(
                        request=ContinuationRequest(
                            starting_text=source_text,
                            word_count=word_count,
                            direction=direction,
                            outline=outline,
                            characters=characters,
                            worldview=worldview,
                            style_profile=style_profile,
                            previous_chapters=previous_chapters,
                            temperature=temperature
                        ),
                        num_versions=num_to_generate,
                        temperatures=temps
                    )
                    
                    # 存储所有版本
                    for i, result in enumerate(results):
                        if result.success:
                            version_data = {
                                "text": result.text,
                                "word_count": result.word_count,
                                "temperature": [0.6, 0.8, 1.0][i],
                                "metadata": result.metadata.model_dump(),
                                "score": 0
                            }
                            self._continue_versions.append(version_data)
                    
                    # 自动选择最佳版本
                    if self._continue_versions:
                        best_result, best_index, scores = self._continuation_plugin.select_best_version(
                            results[:len(self._continue_versions)]
                        )
                        self._best_version_index = best_index
                        
                        # 更新评分
                        for i, score_dict in enumerate(scores):
                            if i < len(self._continue_versions):
                                self._continue_versions[i]["score"] = score_dict.get("total", 0)
                        
                        # 显示最佳版本
                        self._current_version_index = best_index
                        self.root.after(0, lambda: self._display_version(best_index))
                    
                    self.root.after(0, lambda: self._set_status(f"已生成 {len(self._continue_versions)} 个版本"))
                else:
                    # 单次生成
                    self._set_status("正在生成续写...")
                    
                    request = ContinuationRequest(
                        starting_text=source_text,
                        word_count=word_count,
                        direction=direction,
                        outline=outline,
                        characters=characters,
                        worldview=worldview,
                        style_profile=style_profile,
                        previous_chapters=previous_chapters,
                        temperature=temperature
                    )
                    
                    result = self._continuation_plugin.generate_continuation(request)
                    
                    if result.success:
                        # 计算评分
                        scores = self._continuation_plugin._evaluate_version(result, request)
                        
                        version_data = {
                            "text": result.text,
                            "word_count": result.word_count,
                            "temperature": temperature,
                            "metadata": result.metadata.model_dump(),
                            "score": scores.get("total", 0)
                        }
                        self._continue_versions.append(version_data)
                        self._current_version_index = 0
                        self._best_version_index = 0
                        
                        # 显示结果
                        self.root.after(0, lambda: self._display_version(0))
                        self.root.after(0, lambda: self._set_status("续写生成完成"))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("错误", f"续写失败：{result.error}"))
                        self.root.after(0, lambda: self._set_status("续写生成失败"))
                
            except Exception as e:
                logger.error(f"续写生成异常: {e}", exc_info=True)
                self.root.after(0, lambda: messagebox.showerror("错误", f"续写生成异常：{e}"))
                self.root.after(0, lambda: self._set_status("续写生成异常"))
            finally:
                # 恢复按钮
                self.root.after(0, lambda: self._start_btn.configure(state=tk.NORMAL))
                self.root.after(0, lambda: self._update_version_combo())
        
        # 启动后台任务
        if CORE_AVAILABLE:
            self._async_handler.submit(generate_task, priority=TaskPriority.NORMAL)
        else:
            threading.Thread(target=generate_task, daemon=True).start()
    
    def _on_continue_regenerate(self):
        """重新生成续写"""
        if not hasattr(self, '_continuation_plugin') or not self._continuation_plugin:
            messagebox.showerror("错误", "续写插件未加载")
            return
        
        # 显示重新生成模式选择对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("重新生成模式")
        dialog.geometry("400x250")
        dialog.configure(bg=GlassTheme.GLASS_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 250) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 模式选择
        ttk.Label(dialog, text="选择重新生成模式：").pack(pady=20)
        
        mode_var = tk.StringVar(value="creative")
        ttk.Radiobutton(dialog, text="🎨 创意模式（温度1.0，更多创新）", variable=mode_var, value="creative").pack(anchor=tk.W, padx=40, pady=5)
        ttk.Radiobutton(dialog, text="⚖️ 平衡模式（温度0.8，平衡创新和连贯）", variable=mode_var, value="balanced").pack(anchor=tk.W, padx=40, pady=5)
        ttk.Radiobutton(dialog, text="🔒 保守模式（温度0.6，更连贯保守）", variable=mode_var, value="conservative").pack(anchor=tk.W, padx=40, pady=5)
        ttk.Radiobutton(dialog, text="🎯 聚焦模式（温度0.5，高度连贯）", variable=mode_var, value="focused").pack(anchor=tk.W, padx=40, pady=5)
        
        # 按钮区
        btn_frame = ttk.Frame(dialog, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=20, pady=20)
        
        def on_regenerate():
            dialog.destroy()
            
            # 获取模式对应的温度
            temp_map = {
                "creative": 1.0,
                "balanced": 0.8,
                "conservative": 0.6,
                "focused": 0.5
            }
            temperature = temp_map.get(mode_var.get(), 0.8)
            
            # 更新温度设置
            self._continue_temp_var.set(temperature)
            self._temp_label.configure(text=f"{temperature:.1f}")
            
            # 执行续写
            self._on_continue_generate()
        
        ttk.Button(btn_frame, text="确定", command=on_regenerate).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT)
    
    def _on_continue_select_best(self):
        """选择最佳版本并保存为新章节"""
        if not self._continue_versions:
            messagebox.showwarning("提示", "没有可选择的版本")
            return
        
        if self._best_version_index < 0:
            # 如果没有最佳版本索引，使用当前选中的版本
            best_index = self._current_version_index
        else:
            best_index = self._best_version_index
        
        # 切换到最佳版本
        self._current_version_index = best_index
        self._display_version(best_index)
        
        # 弹出章节命名窗口
        self._show_chapter_naming_dialog(best_index)
    
    def _show_chapter_naming_dialog(self, version_index: int):
        """显示章节命名对话框"""
        if not self._continue_versions or version_index >= len(self._continue_versions):
            return
        
        current_version = self._continue_versions[version_index]
        continuation_text = current_version.get("text", "")
        
        # 创建命名对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("保存为新章节")
        dialog.geometry("400x200")
        dialog.configure(bg=GlassTheme.GLASS_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 200) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 提示信息
        ttk.Label(dialog, text=f"正在保存版本 V{version_index + 1}（评分：{current_version.get('score', 0):.2f}）").pack(pady=10)
        
        # 章节名称输入
        name_frame = ttk.Frame(dialog, style="TFrame")
        name_frame.pack(fill=tk.X, padx=20, pady=10)
        
        ttk.Label(name_frame, text="章节名称：").pack(side=tk.LEFT)
        chapter_name_var = tk.StringVar(value=f"第X章 续写内容")
        chapter_name_entry = ttk.Entry(name_frame, textvariable=chapter_name_var, width=25)
        chapter_name_entry.pack(side=tk.LEFT, padx=5)
        chapter_name_entry.focus()
        
        # 字数统计
        word_count = current_version.get("word_count", 0)
        ttk.Label(dialog, text=f"字数：{word_count}").pack(pady=5)
        
        # 按钮区
        btn_frame = ttk.Frame(dialog, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=20, pady=20)
        
        def on_save():
            chapter_name = chapter_name_var.get().strip()
            if not chapter_name:
                messagebox.showwarning("提示", "请输入章节名称")
                return
            
            # 保存到项目
            if hasattr(self, '_project_manager') and self._project_manager:
                try:
                    self._project_manager.add_chapter(chapter_name, continuation_text)
                    self._set_status(f"已保存为新章节：{chapter_name}")
                    messagebox.showinfo("成功", f"已保存章节：{chapter_name}")
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("错误", f"保存失败：{e}")
            else:
                messagebox.showwarning("提示", "请先打开或创建项目")
        
        ttk.Button(btn_frame, text="保存", command=on_save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT)
    
    def _on_continue_save(self):
        """保存续写结果"""
        if not self._continue_versions:
            messagebox.showwarning("提示", "没有可保存的内容")
            return
        
        current_version = self._continue_versions[self._current_version_index]
        continuation_text = current_version.get("text", "")
        
        if not continuation_text:
            messagebox.showwarning("提示", "当前版本内容为空")
            return
        
        # 创建保存对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("保存续写结果")
        dialog.geometry("450x300")
        dialog.configure(bg=GlassTheme.GLASS_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 450) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 300) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 保存选项
        ttk.Label(dialog, text="保存方式：").pack(pady=10)
        
        save_mode = tk.StringVar(value="new")
        ttk.Radiobutton(dialog, text="📄 保存为新章节", variable=save_mode, value="new").pack(anchor=tk.W, padx=40, pady=5)
        ttk.Radiobutton(dialog, text="📝 追加到当前章节", variable=save_mode, value="append").pack(anchor=tk.W, padx=40, pady=5)
        ttk.Radiobutton(dialog, text="💾 导出为文件", variable=save_mode, value="export").pack(anchor=tk.W, padx=40, pady=5)
        
        # 章节名称（仅新章节模式）
        name_frame = ttk.Frame(dialog, style="TFrame")
        name_frame.pack(fill=tk.X, padx=40, pady=10)
        ttk.Label(name_frame, text="章节名称：").pack(side=tk.LEFT)
        chapter_name_var = tk.StringVar(value=f"第X章 续写内容")
        chapter_name_entry = ttk.Entry(name_frame, textvariable=chapter_name_var, width=25)
        chapter_name_entry.pack(side=tk.LEFT, padx=5)
        
        # 按钮区
        btn_frame = ttk.Frame(dialog, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=20, pady=20)
        
        def on_save():
            mode = save_mode.get()
            
            if mode == "export":
                # 导出为文件
                file_path = filedialog.asksaveasfilename(
                    title="保存续写结果",
                    defaultextension=".txt",
                    filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx"), ("Markdown", "*.md")]
                )
                if file_path:
                    try:
                        if file_path.endswith('.docx'):
                            from docx import Document
                            doc = Document()
                            doc.add_heading("续写内容", level=1)
                            doc.add_paragraph(continuation_text)
                            doc.save(file_path)
                        else:
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.write(continuation_text)
                        
                        self._set_status(f"已导出到：{os.path.basename(file_path)}")
                        dialog.destroy()
                    except Exception as e:
                        messagebox.showerror("错误", f"导出失败：{e}")
            
            elif mode == "new" or mode == "append":
                # 检查项目管理器
                if not hasattr(self, '_project_manager') or not self._project_manager:
                    messagebox.showwarning("提示", "请先打开或创建项目")
                    return
                
                try:
                    if mode == "new":
                        # 保存为新章节
                        chapter_name = chapter_name_var.get()
                        self._project_manager.add_chapter(chapter_name, continuation_text)
                        self._set_status(f"已保存为新章节：{chapter_name}")
                    else:
                        # 追加到当前章节
                        source_text = self._continue_source.get("1.0", tk.END).strip()
                        full_text = source_text + "\n\n" + continuation_text
                        # 更新当前章节内容（需要项目管理器支持）
                        if hasattr(self._project_manager, 'update_current_chapter'):
                            self._project_manager.update_current_chapter(full_text)
                        else:
                            # 如果不支持，保存为新章节
                            self._project_manager.add_chapter(f"第X章（续写）", full_text)
                        self._set_status("已追加到当前章节")
                    
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("错误", f"保存失败：{e}")
        
        ttk.Button(btn_frame, text="保存", command=on_save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT)
        
        # 根据保存模式切换章节名称输入框状态
        def on_mode_changed():
            if save_mode.get() == "new":
                chapter_name_entry.configure(state=tk.NORMAL)
            else:
                chapter_name_entry.configure(state=tk.DISABLED)
        
        save_mode.trace("w", lambda *args: on_mode_changed())
    
    def _create_progress_page(self) -> tk.Frame:
        """创建创作进度页面（支持滚动）"""
        frame = ttk.Frame(self._content_frame, style="TFrame")
        
        # 创建Canvas和Scrollbar用于滚动
        canvas = tk.Canvas(frame, bg=GlassTheme.GLASS_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="TFrame")
        
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
        
        scrollable_frame.bind("<Configure>", on_frame_configure)
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 鼠标滚轮绑定
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        def bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        def unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        
        canvas.bind("<Enter>", bind_mousewheel)
        canvas.bind("<Leave>", unbind_mousewheel)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 标题
        header = ttk.Frame(scrollable_frame, style="TFrame")
        header.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        ttk.Label(header, text="创作进度", style="Title.TLabel").pack(side=tk.LEFT)
        
        # 进度统计
        progress_frame = ttk.LabelFrame(scrollable_frame, text="当前项目状态", padding=20)
        progress_frame.pack(fill=tk.X, padx=20, pady=10)
        
        stats = [
            ("当前项目", "未打开项目"),
            ("已完成章节", "0 / 0"),
            ("总字数", "0 字"),
            ("今日目标", "0 / 3000 字"),
            ("大纲解析", "未完成"),
            ("人物录入", "0 人"),
            ("世界观条目", "0 个"),
            ("当前风格", "未设置"),
        ]
        
        for i, (label, value) in enumerate(stats):
            row_frame = ttk.Frame(progress_frame, style="TFrame")
            row_frame.pack(fill=tk.X, pady=3)
            
            ttk.Label(row_frame, text=f"{label}：", width=15, anchor='e').pack(side=tk.LEFT)
            ttk.Label(row_frame, text=value, foreground=GlassTheme.TEXT_SECONDARY).pack(side=tk.LEFT, padx=10)
        
        # 操作按钮
        btn_frame = ttk.Frame(scrollable_frame, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=20, pady=10)

        buttons = [
            ("刷新统计", self._on_refresh_progress),
            ("导出报告", self._on_export_progress),
            ("重置进度", self._on_reset_progress),
        ]

        for i, (text, command) in enumerate(buttons):
            ResponsiveButton(
                btn_frame,
                text=text,
                command=command,
                async_handler=self._async_handler
            ).grid(row=0, column=i, padx=5, pady=2, sticky="ew")

        # 配置列权重，确保按钮均匀分布
        for i in range(3):
            btn_frame.grid_columnconfigure(i, weight=1)
        
        return frame
    
    def _create_project_page(self) -> tk.Frame:
        """创建项目管理页面（支持滚动）"""
        frame = ttk.Frame(self._content_frame, style="TFrame")
        
        # 创建Canvas和Scrollbar用于滚动
        canvas = tk.Canvas(frame, bg=GlassTheme.GLASS_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="TFrame")
        
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
        
        scrollable_frame.bind("<Configure>", on_frame_configure)
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 鼠标滚轮绑定
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        def bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        def unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        
        canvas.bind("<Enter>", bind_mousewheel)
        canvas.bind("<Leave>", unbind_mousewheel)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 标题
        header = ttk.Frame(scrollable_frame, style="TFrame")
        header.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        ttk.Label(header, text="项目管理", style="Title.TLabel").pack(side=tk.LEFT)
        
        # 当前项目信息
        info_frame = ttk.LabelFrame(scrollable_frame, text="当前项目", padding=20)
        info_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # 项目名称
        name_frame = ttk.Frame(info_frame, style="TFrame")
        name_frame.pack(fill=tk.X, pady=5)
        ttk.Label(name_frame, text="项目名称：").pack(side=tk.LEFT)
        self._project_name_var = tk.StringVar(value="未打开项目")
        ttk.Label(name_frame, textvariable=self._project_name_var).pack(side=tk.LEFT, padx=10)
        
        # 项目路径
        path_frame = ttk.Frame(info_frame, style="TFrame")
        path_frame.pack(fill=tk.X, pady=5)
        ttk.Label(path_frame, text="项目路径：").pack(side=tk.LEFT)
        self._project_path_var = tk.StringVar(value="-")
        ttk.Label(path_frame, textvariable=self._project_path_var).pack(side=tk.LEFT, padx=10)
        
        # 操作按钮
        btn_frame = ttk.Frame(scrollable_frame, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=20, pady=10)

        buttons = [
            ("新建项目", self._on_new_project),
            ("打开项目", self._on_open_project),
            ("导出备份", self._on_backup_project),
        ]

        for i, (text, command) in enumerate(buttons):
            ResponsiveButton(
                btn_frame,
                text=text,
                command=command,
                async_handler=self._async_handler,
                style="Accent.TButton" if i == 0 else "TButton"
            ).grid(row=0, column=i, padx=5, pady=2, sticky="ew")

        # 配置列权重，确保按钮均匀分布
        for i in range(3):
            btn_frame.grid_columnconfigure(i, weight=1)

        return frame
    
    def _create_plugins_page(self) -> tk.Frame:
        """创建插件管理页面（支持滚动）- V2.2增强版
        
        功能：
        - 显示已安装插件列表（名称、版本、状态、类型、保护状态）
        - 启用/禁用插件（调用PluginRegistry）
        - 插件配置界面（通过PluginContext读取/保存配置）
        - V5保护模块标识（禁止操作）
        """
        frame = ttk.Frame(self._content_frame, style="TFrame")
        
        # 创建Canvas和Scrollbar用于滚动
        canvas = tk.Canvas(frame, bg=GlassTheme.GLASS_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="TFrame")
        
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
        
        scrollable_frame.bind("<Configure>", on_frame_configure)
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 鼠标滚轮绑定
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        def bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        def unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        
        canvas.bind("<Enter>", bind_mousewheel)
        canvas.bind("<Leave>", unbind_mousewheel)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 标题区域
        header = ttk.Frame(scrollable_frame, style="TFrame")
        header.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        ttk.Label(header, text="插件管理", style="Title.TLabel").pack(side=tk.LEFT)
        
        # 状态说明
        status_info = ttk.Label(
            header, 
            text="🔒 = V5核心保护模块（禁止禁用）", 
            font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_SMALL),
            foreground=GlassTheme.ACCENT_ORANGE
        )
        status_info.pack(side=tk.RIGHT)
        
        # 插件列表
        list_frame = ttk.LabelFrame(scrollable_frame, text="已安装插件", padding=15)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # V2.2新增：增加保护状态列
        columns = ("name", "version", "status", "type", "protected")
        self._plugin_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=15,
            selectmode="browse"  # 单选模式
        )

        # 配置字体
        style = ttk.Style()
        style.configure("Treeview",
                     font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL))
        style.configure("Treeview.Heading",
                     font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL, "bold"))
        
        # 配置列标题和宽度
        self._plugin_tree.heading("name", text="插件名称")
        self._plugin_tree.heading("version", text="版本")
        self._plugin_tree.heading("status", text="状态")
        self._plugin_tree.heading("type", text="类型")
        self._plugin_tree.heading("protected", text="保护")
        
        self._plugin_tree.column("name", width=200, minwidth=150)
        self._plugin_tree.column("version", width=80, minwidth=60)
        self._plugin_tree.column("status", width=80, minwidth=60)
        self._plugin_tree.column("type", width=100, minwidth=80)
        self._plugin_tree.column("protected", width=60, minwidth=50)
        
        # 添加滚动条
        tree_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self._plugin_tree.yview)
        self._plugin_tree.configure(yscrollcommand=tree_scroll.set)
        
        self._plugin_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定双击事件打开配置对话框
        self._plugin_tree.bind("<Double-1>", self._on_plugin_double_click)
        # 绑定选择事件更新按钮状态
        self._plugin_tree.bind("<<TreeviewSelect>>", self._on_plugin_select)
        
        # V2.3优化：异步加载插件数据
        self._load_plugins_async()
        
        # 插件详情区域
        detail_frame = ttk.LabelFrame(scrollable_frame, text="插件详情", padding=15)
        detail_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self._plugin_detail_var = tk.StringVar(value="请选择一个插件查看详情")
        detail_label = ttk.Label(
            detail_frame, 
            textvariable=self._plugin_detail_var,
            font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL),
            wraplength=800,
            justify=tk.LEFT
        )
        detail_label.pack(fill=tk.X, anchor=tk.W)
        
        # 操作按钮区域
        btn_frame = ttk.Frame(scrollable_frame, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=20, pady=10)

        # V2.2新增：启用/禁用/配置按钮
        buttons = [
            ("刷新列表", self._on_refresh_plugins, "TButton"),
            ("启用插件", self._on_enable_plugin, "TButton"),
            ("禁用插件", self._on_disable_plugin, "TButton"),
            ("插件配置", self._on_config_plugin, "Accent.TButton"),
            ("重新加载", self._on_reload_plugin, "TButton"),
        ]

        for i, (text, command, btn_style) in enumerate(buttons):
            ResponsiveButton(
                btn_frame,
                text=text,
                command=command,
                async_handler=self._async_handler,
                style=btn_style
            ).grid(row=0, column=i, padx=5, pady=2, sticky="ew")

        # 配置列权重
        for i in range(len(buttons)):
            btn_frame.grid_columnconfigure(i, weight=1)

        # 存储按钮引用以便更新状态
        self._plugin_buttons = {
            "enable": btn_frame.winfo_children()[1],
            "disable": btn_frame.winfo_children()[2],
            "config": btn_frame.winfo_children()
        }

        return frame
    
    def _create_settings_page(self) -> tk.Frame:
        """创建设置页面（支持滚动）"""
        frame = ttk.Frame(self._content_frame, style="TFrame")
        
        # 创建滚动容器
        canvas = tk.Canvas(frame, bg=GlassTheme.GLASS_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="TFrame")
        
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
        
        scrollable_frame.bind("<Configure>", on_frame_configure)
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 鼠标滚轮绑定
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        def bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        def unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        
        canvas.bind("<Enter>", bind_mousewheel)
        canvas.bind("<Leave>", unbind_mousewheel)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 标题
        ttk.Label(scrollable_frame, text="设置", style="Title.TLabel").pack(anchor=tk.W, padx=20, pady=(20, 10))
        
        # AI服务配置
        ai_frame = ttk.LabelFrame(scrollable_frame, text="AI服务配置", padding=15)
        ai_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # 服务模式
        mode_frame = ttk.Frame(ai_frame, style="TFrame")
        mode_frame.pack(fill=tk.X, pady=5)
        ttk.Label(mode_frame, text="服务模式：").pack(side=tk.LEFT)
        self._service_mode_var = tk.StringVar(value="online")
        mode_local = ttk.Radiobutton(mode_frame, text="本地大模型", variable=self._service_mode_var, value="local", command=self._on_service_mode_changed)
        mode_local.pack(side=tk.LEFT, padx=10)
        mode_online = ttk.Radiobutton(mode_frame, text="线上API", variable=self._service_mode_var, value="online", command=self._on_service_mode_changed)
        mode_online.pack(side=tk.LEFT)
        
        # API提供商
        provider_frame = ttk.Frame(ai_frame, style="TFrame")
        provider_frame.pack(fill=tk.X, pady=5)
        ttk.Label(provider_frame, text="提供商：").pack(side=tk.LEFT)
        self._provider_var = tk.StringVar(value="DeepSeek")
        provider_combo = ttk.Combobox(
            provider_frame,
            textvariable=self._provider_var,
            values=["DeepSeek", "OpenAI", "Anthropic", "Ollama"],
            state="readonly",
            width=20
        )
        provider_combo.pack(side=tk.LEFT, padx=10)
        
        # 模型选择
        model_frame = ttk.Frame(ai_frame, style="TFrame")
        model_frame.pack(fill=tk.X, pady=5)
        ttk.Label(model_frame, text="模型：").pack(side=tk.LEFT)
        self._model_var = tk.StringVar(value="deepseek-chat")
        model_combo = ttk.Combobox(
            model_frame,
            textvariable=self._model_var,
            values=["deepseek-chat", "deepseek-reasoner", "gpt-4", "gpt-3.5-turbo", "claude-3"],
            state="readonly",
            width=20
        )
        model_combo.pack(side=tk.LEFT, padx=10)
        
        # API Key / 本地部署地址（根据模式显示不同字段）
        key_frame = ttk.Frame(ai_frame, style="TFrame")
        key_frame.pack(fill=tk.X, pady=5)
        self._key_label = ttk.Label(key_frame, text="API Key：")
        self._key_label.pack(side=tk.LEFT)
        self._api_key_var = tk.StringVar()
        self._local_url_var = tk.StringVar(value="http://localhost:11434/v1")
        self._key_entry = ttk.Entry(key_frame, textvariable=self._api_key_var, width=40, show="*")
        self._key_entry.pack(side=tk.LEFT, padx=10)
        self._url_entry = ttk.Entry(key_frame, textvariable=self._local_url_var, width=40)
        # 默认隐藏本地地址输入框
        self._url_entry.pack_forget()
        
        # Temperature
        temp_frame = ttk.Frame(ai_frame, style="TFrame")
        temp_frame.pack(fill=tk.X, pady=5)
        ttk.Label(temp_frame, text="Temperature：").pack(side=tk.LEFT)
        self._temp_var = tk.DoubleVar(value=0.7)
        temp_scale = ttk.Scale(
            temp_frame,
            from_=0.0,
            to=2.0,
            variable=self._temp_var,
            orient=tk.HORIZONTAL,
            length=200
        )
        temp_scale.pack(side=tk.LEFT, padx=10)
        self._temp_label = ttk.Label(temp_frame, text="0.70")
        self._temp_label.pack(side=tk.LEFT)
        temp_scale.configure(command=lambda v: self._temp_label.configure(text=f"{float(v):.2f}"))
        

        # 文件路径设置
        # 文件路径设置
        path_frame = ttk.LabelFrame(scrollable_frame, text="文件路径设置", padding=15)
        path_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # 默认保存位置
        save_path_frame = ttk.Frame(path_frame, style="TFrame")
        save_path_frame.pack(fill=tk.X, pady=5)
        ttk.Label(save_path_frame, text="默认保存位置：").pack(side=tk.LEFT)
        self._save_path_var = tk.StringVar(value=os.getcwd())
        ttk.Entry(save_path_frame, textvariable=self._save_path_var, width=40).pack(side=tk.LEFT, padx=10)
        ttk.Button(save_path_frame, text="浏览", command=self._on_browse_save_path).pack(side=tk.LEFT)
        
        # 自动备份间隔
        backup_frame = ttk.Frame(path_frame, style="TFrame")
        backup_frame.pack(fill=tk.X, pady=5)
        ttk.Label(backup_frame, text="自动备份间隔：").pack(side=tk.LEFT)
        self._backup_interval_var = tk.StringVar(value="30")
        ttk.Spinbox(backup_frame, from_=10, to=120, textvariable=self._backup_interval_var, width=8).pack(side=tk.LEFT, padx=10)
        ttk.Label(backup_frame, text="分钟").pack(side=tk.LEFT)
        
        # 偏好学习设置
        learning_frame = ttk.LabelFrame(scrollable_frame, text="偏好学习设置", padding=15)
        learning_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # AI学习开关
        ai_learning_frame = ttk.Frame(learning_frame, style="TFrame")
        ai_learning_frame.pack(fill=tk.X, pady=5)
        ttk.Label(ai_learning_frame, text="AI偏好学习：").pack(side=tk.LEFT)
        self._ai_learning_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ai_learning_frame, text="启用（AI将学习您的写作偏好）", variable=self._ai_learning_var).pack(side=tk.LEFT, padx=10)
        
        # 数据清除
        clear_frame = ttk.Frame(learning_frame, style="TFrame")
        clear_frame.pack(fill=tk.X, pady=5)
        ttk.Label(clear_frame, text="偏好数据：").pack(side=tk.LEFT)
        ttk.Button(clear_frame, text="清除学习数据", command=self._on_clear_learning_data).pack(side=tk.LEFT, padx=10)
        ttk.Button(clear_frame, text="导出偏好配置", command=self._on_export_preferences).pack(side=tk.LEFT, padx=5)
        
        # 从config.yaml加载设置
        self._load_settings_from_config()
        
        # 保存按钮
        save_frame = ttk.Frame(scrollable_frame, style="TFrame")
        save_frame.pack(fill=tk.X, padx=20, pady=20)
        
        ResponsiveButton(
            save_frame,
            text="保存设置",
            command=self._on_save_settings,
            async_handler=self._async_handler,
            style="Accent.TButton"
        ).pack(side=tk.LEFT)
        
        return frame
    
    # ============== 辅助方法 ==============
    
    def _set_status(self, message: str) -> None:
        """设置状态栏消息"""
        if self._status_var:
            self._status_var.set(message)
    
    def _process_result_queue(self) -> None:
        """处理结果队列"""
        try:
            while True:
                result = self._result_queue.get_nowait()
                if isinstance(result, dict):
                    result_type = result.get('type')
                    if result_type == 'status':
                        self._set_status(result.get('message', ''))
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_result_queue)
    
    # ============== 功能方法 ==============
    
    def _get_hot_ranking_data(self) -> Dict:
        """获取热榜数据 - 调用HotRankingPlugin获取真实爬虫数据"""
        # 方式1: 尝试从插件注册表获取热榜插件
        if CORE_AVAILABLE:
            try:
                registry = get_plugin_registry()
                if registry:
                    hot_ranking_plugin = registry.get_plugin("hot-ranking-v1")
                    if hot_ranking_plugin:
                        # 调用插件获取真实数据（优先使用缓存）
                        result = hot_ranking_plugin.execute("get_data", {"force_fresh": False})
                        if result and isinstance(result, dict):
                            logger.info("[热榜] 成功从HotRankingPlugin获取数据（注册表）")
                            return result
            except Exception as e:
                logger.warning(f"[热榜] 插件注册表获取失败: {e}")
        
        # 方式2: 直接动态加载插件（当注册表中没有时）
        try:
            import importlib.util
            plugin_path = os.path.join(os.path.dirname(__file__), "plugins", "hot-ranking-v1", "plugin.py")
            spec = importlib.util.spec_from_file_location("hot_ranking_plugin", plugin_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            HotRankingPlugin = module.HotRankingPlugin
            
            # 创建插件实例（不需要上下文，插件内部自己初始化）
            plugin = HotRankingPlugin()
            
            # 创建简化的上下文（PluginContext是dataclass，需要正确的参数）
            from core.plugin_interface import PluginContext
            context = PluginContext(
                event_bus=get_event_bus() if CORE_AVAILABLE else None,
                service_locator=get_service_locator() if CORE_AVAILABLE else None,
                config_manager=None,
                plugin_registry=None,
                logger=None
            )
            
            if plugin.initialize(context):
                # 获取数据（优先使用缓存）
                result = plugin.execute("get_data", {"force_fresh": False})
                if result and isinstance(result, dict):
                    logger.info("[热榜] 成功从HotRankingPlugin获取数据（动态加载）")
                    return result
        except Exception as e:
            logger.warning(f"[热榜] 动态加载插件失败: {e}")
        
        # 降级：返回静态默认数据
        logger.info("[热榜] 使用静态默认数据")
        return self._get_default_hot_ranking_data()
    
    def _get_default_hot_ranking_data(self) -> Dict:
        """获取默认热榜数据（离线降级）"""
        return {
            'sites': [
                {
                    'name': '📚 起点中文网',
                    'color': '#457B9D',
                    'books': [
                        {'title': '诡秘之主', 'author': '爱潜水的乌贼', 'category': '玄幻', 'heat': 150000},
                        {'title': '大奉打更人', 'author': '卖报小郎君', 'category': '仙侠', 'heat': 120000},
                        {'title': '深空彼岸', 'author': '辰东', 'category': '科幻', 'heat': 100000},
                        {'title': '星门', 'author': '老鹰吃小鸡', 'category': '玄幻', 'heat': 80000},
                        {'title': '完美世界', 'author': '辰东', 'category': '玄幻', 'heat': 60000},
                        {'title': '遮天', 'author': '辰东', 'category': '玄幻', 'heat': 55000},
                        {'title': '斗破苍穹', 'author': '天蚕土豆', 'category': '玄幻', 'heat': 50000},
                        {'title': '凡人修仙传', 'author': '忘语', 'category': '仙侠', 'heat': 45000},
                        {'title': '一念永恒', 'author': '耳根', 'category': '仙侠', 'heat': 40000},
                        {'title': '牧神记', 'author': '宅猪', 'category': '玄幻', 'heat': 35000},
                    ]
                },
                {
                    'name': '🎭 晋江文学城',
                    'color': '#E63946',
                    'books': [
                        {'title': '天官赐福', 'author': '墨香铜臭', 'category': '纯爱', 'heat': 180000},
                        {'title': '魔道祖师', 'author': '墨香铜臭', 'category': '纯爱', 'heat': 150000},
                        {'title': '人渣反派自救系统', 'author': '墨香铜臭', 'category': '纯爱', 'heat': 120000},
                        {'title': '二哈和他的白猫师尊', 'author': '肉包不吃肉', 'category': '纯爱', 'heat': 90000},
                        {'title': '全球高考', 'author': '木苏里', 'category': '纯爱', 'heat': 70000},
                        {'title': '撒野', 'author': '巫哲', 'category': '纯爱', 'heat': 65000},
                        {'title': '默读', 'author': 'Priest', 'category': '纯爱', 'heat': 60000},
                        {'title': '镇魂', 'author': 'Priest', 'category': '纯爱', 'heat': 55000},
                        {'title': '杀破狼', 'author': 'Priest', 'category': '纯爱', 'heat': 50000},
                        {'title': '有兽焉', 'author': '鹤来', 'category': '纯爱', 'heat': 45000},
                    ]
                },
                {
                    'name': '🍅 番茄小说',
                    'color': '#FF6B6B',
                    'books': [
                        {'title': '我在精神病院学斩神', 'author': '三九音域', 'category': '都市', 'heat': 185000},
                        {'title': '星门', 'author': '老鹰吃小鸡', 'category': '玄幻', 'heat': 168000},
                        {'title': '斩神', 'author': '三九音域', 'category': '都市', 'heat': 152000},
                        {'title': '重生之都市修仙', 'author': '十里剑神', 'category': '都市', 'heat': 138000},
                        {'title': '全职法师', 'author': '乱', 'category': '玄幻', 'heat': 125000},
                        {'title': '万族之劫', 'author': '老鹰吃小鸡', 'category': '玄幻', 'heat': 110000},
                        {'title': '开局签到荒古圣体', 'author': '神牧', 'category': '玄幻', 'heat': 95000},
                        {'title': '神墓', 'author': '辰东', 'category': '玄幻', 'heat': 80000},
                        {'title': '仙逆', 'author': '耳根', 'category': '仙侠', 'heat': 70000},
                        {'title': '我欲封天', 'author': '耳根', 'category': '仙侠', 'heat': 60000},
                    ]
                }
            ],
            'genres': {
                'male': {'title': '👨 男频题材榜', 'color': '#457B9D', 'genres': [
                    ('玄幻', 25.5), ('都市', 22.3), ('仙侠', 18.7), ('历史', 15.2), ('科幻', 12.8)
                ]},
                'female': {'title': '👩 女频题材榜', 'color': '#E63946', 'genres': [
                    ('现代言情', 28.6), ('古代言情', 24.1), ('玄幻言情', 19.8), ('仙侠奇缘', 16.4), ('青春校园', 13.2)
                ]}
            },
            'types': {
                'male': {'title': '👨 男频类型榜', 'color': '#2A9D8F', 'types': [
                    ('系统流', 22.8), ('穿越', 20.5), ('重生', 18.2), ('修仙', 16.9), ('无敌流', 14.3)
                ]},
                'female': {'title': '👩 女频类型榜', 'color': '#F4A261', 'types': [
                    ('甜宠', 26.5), ('虐恋', 23.1), ('穿越', 20.8), ('重生', 18.4), ('宫斗', 16.2)
                ]}
            },
            'authors': [
                {'rank': 1, 'name': '唐家三少', 'works': '《斗罗大陆》《绝世唐门》', 'income': '3.2亿', 'fans': '1200万'},
                {'rank': 2, 'name': '辰东', 'works': '《遮天》《完美世界》', 'income': '2.8亿', 'fans': '980万'},
                {'rank': 3, 'name': '天蚕土豆', 'works': '《斗破苍穹》《武动乾坤》', 'income': '2.5亿', 'fans': '890万'},
                {'rank': 4, 'name': '我吃西红柿', 'works': '《盘龙》《星辰变》', 'income': '2.1亿', 'fans': '760万'},
                {'rank': 5, 'name': '猫腻', 'works': '《庆余年》《将夜》', 'income': '1.7亿', 'fans': '680万'},
                {'rank': 6, 'name': '顾漫', 'works': '《你是我的荣耀》', 'income': '1.5亿', 'fans': '650万'},
                {'rank': 7, 'name': '梦入神机', 'works': '《龙蛇演义》《永生》', 'income': '1.9亿', 'fans': '720万'},
                {'rank': 8, 'name': '烽火戏诸侯', 'works': '《雪中悍刀行》《剑来》', 'income': '9800万', 'fans': '560万'},
                {'rank': 9, 'name': '月关', 'works': '《回明》《锦衣夜行》', 'income': '1.3亿', 'fans': '620万'},
                {'rank': 10, 'name': '血红', 'works': '《升龙道》《邪风曲》', 'income': '1.1亿', 'fans': '590万'}
            ],
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
    
    def _load_plugins_async(self) -> None:
        """异步加载插件列表 - V2.3优化版
        
        使用AsyncHandler异步加载插件，避免UI卡顿
        """
        # 显示加载状态
        loading_item = self._plugin_tree.insert(
            "",
            tk.END,
            values=("正在加载插件...", "", "", "", "")
        )
        
        def load_task():
            """后台加载任务"""
            # 使用线程池执行加载
            from concurrent.futures import ThreadPoolExecutor
            import time
            
            # 模拟加载延迟（实际是文件IO）
            plugins_data = []
            plugins_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
            
            if os.path.exists(plugins_dir):
                protected_modules = {
                    "outline-parser-v3", "style-learner-v5", "character-manager-v1",
                    "worldview-parser-v1", "context-builder-v1", "iterative-generator-v2",
                    "quality-validator-v1", "novel-generator-v3", "hot-ranking-v1"
                }
                
                for plugin_name in sorted(os.listdir(plugins_dir)):
                    plugin_path = os.path.join(plugins_dir, plugin_name)
                    if os.path.isdir(plugin_path) and not plugin_name.startswith("__"):
                        plugin_json = os.path.join(plugin_path, "plugin.json")
                        if os.path.exists(plugin_json):
                            try:
                                with open(plugin_json, "r", encoding="utf-8") as f:
                                    data = json.load(f)
                                
                                is_protected = plugin_name in protected_modules
                                plugins_data.append({
                                    "id": plugin_name,
                                    "data": data,
                                    "is_protected": is_protected
                                })
                            except Exception as e:
                                logger.warning(f"Failed to load plugin.json for {plugin_name}: {e}")
            
            return plugins_data
        
        def on_success(plugins_data):
            """加载成功回调（在主线程执行）"""
            # 清空加载状态
            for item in self._plugin_tree.get_children():
                self._plugin_tree.delete(item)
            
            self._plugin_data = {}
            
            # 类型映射
            type_map = {
                "analyzer": "分析器",
                "generator": "生成器",
                "validator": "验证器",
                "tool": "工具",
                "storage": "存储",
                "ai": "AI服务",
                "protocol": "协议"
            }
            
            # 填充数据
            for plugin_info in plugins_data:
                plugin_id = plugin_info["id"]
                data = plugin_info["data"]
                is_protected = plugin_info["is_protected"]
                
                protected_text = "🔒" if is_protected else ""
                type_text = type_map.get(data.get("plugin_type", "tool").lower(), data.get("plugin_type", "工具"))
                status_text = "已启用" if data.get("enabled", True) else "已禁用"
                
                item_id = self._plugin_tree.insert(
                    "",
                    tk.END,
                    values=(
                        data.get("name", plugin_id),
                        data.get("version", "1.0.0"),
                        status_text,
                        type_text,
                        protected_text
                    )
                )
                
                self._plugin_data[item_id] = {
                    "id": plugin_id,
                    "name": data.get("name", plugin_id),
                    "version": data.get("version", "1.0.0"),
                    "description": data.get("description", ""),
                    "author": data.get("author", ""),
                    "type": data.get("plugin_type", "tool"),
                    "state": "active" if data.get("enabled", True) else "disabled",
                    "is_protected": is_protected,
                    "dependencies": data.get("dependencies", [])
                }
            
            self._set_status(f"已加载 {len(plugins_data)} 个插件")
            logger.info(f"Async loaded {len(plugins_data)} plugins")
        
        def on_error(error):
            """加载失败回调（在主线程执行）"""
            # 清空加载状态
            for item in self._plugin_tree.get_children():
                self._plugin_tree.delete(item)
            
            # 显示错误
            self._plugin_tree.insert(
                "",
                tk.END,
                values=(f"加载失败: {error}", "", "", "", "")
            )
            
            self._set_status("插件加载失败")
            logger.error(f"Failed to async load plugins: {error}")
        
        # 提交异步任务
        if self._async_handler:
            self._async_handler.submit(
                func=load_task,
                callback=on_success,
                error_callback=on_error,
                priority=TaskPriority.HIGH,
                timeout=10.0
            )
        else:
            # 回退到同步加载
            self._load_plugins()
    
    def _load_plugins(self) -> None:
        """加载插件列表 - V2.2重构版
        
        从PluginRegistry读取真实的插件数据，包括：
        - 插件元数据（名称、版本、类型）
        - 插件状态（active/loaded/error等）
        - V5保护模块标识
        """
        # 清空现有数据
        for item in self._plugin_tree.get_children():
            self._plugin_tree.delete(item)
        
        # 存储插件数据用于后续操作
        self._plugin_data: Dict[str, Dict[str, Any]] = {}
        
        # 尝试从PluginRegistry获取真实数据
        registry = None
        try:
            if CORE_AVAILABLE:
                registry = get_plugin_registry()
        except Exception as e:
            logger.warning(f"Failed to get PluginRegistry: {e}")
        
        if registry and registry._plugins:
            # 获取所有已注册的插件信息
            for plugin_id in registry._plugins.keys():
                plugin_info = registry.get_plugin_info(plugin_id)
                if plugin_info:
                    metadata = plugin_info.metadata
                    state = plugin_info.state
                    is_protected = registry.is_protected(plugin_id)
                    
                    # 状态显示映射
                    status_map = {
                        "active": "已启用",
                        "loaded": "已加载",
                        "error": "错误",
                        "unloaded": "未加载",
                        "unloading": "卸载中"
                    }
                    status_text = status_map.get(state, state)
                    
                    # 类型显示映射
                    type_map = {
                        "analyzer": "分析器",
                        "generator": "生成器",
                        "validator": "验证器",
                        "tool": "工具",
                        "storage": "存储",
                        "ai": "AI服务",
                        "protocol": "协议"
                    }
                    type_text = type_map.get(metadata.plugin_type.lower(), metadata.plugin_type)
                    
                    # 保护状态显示
                    protected_text = "🔒" if is_protected else ""
                    
                    # 插入到树形视图
                    item_id = self._plugin_tree.insert(
                        "", 
                        tk.END, 
                        values=(
                            metadata.name,
                            metadata.version,
                            status_text,
                            type_text,
                            protected_text
                        )
                    )
                    
                    # 存储插件数据
                    self._plugin_data[item_id] = {
                        "id": plugin_id,
                        "name": metadata.name,
                        "version": metadata.version,
                        "description": metadata.description,
                        "author": metadata.author,
                        "type": metadata.plugin_type,
                        "state": state,
                        "is_protected": is_protected,
                        "dependencies": metadata.dependencies,
                        "error_message": plugin_info.error_message if hasattr(plugin_info, 'error_message') else None
                    }
            
            logger.info(f"Loaded {len(self._plugin_data)} plugins from registry")
        else:
            # 回退：从plugins目录扫描plugin.json文件
            self._load_plugins_from_filesystem()
            logger.info(f"Loaded {len(self._plugin_data)} plugins from filesystem")
    
    def _load_plugins_from_filesystem(self) -> None:
        """从文件系统扫描插件并注册到PluginRegistry（修复版本）
        
        修复说明：
        匨修复前的流程：
        1. 只读取plugin.json文件
        2. 存储到self._plugin_data字典
        3. 显示在Treeview中
        ❌ 问题：插件未注册到PluginRegistry，导致启用/禁用操作失败
        
        @修复后的流程：
        1. 使用PluginLoader.discover_plugins()发现插件
        2. 使用PluginLoader.load_plugin()加载并注册插件
        3. 从PluginRegistry获取真实状态显示在UI
        """
        plugins_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
        
        if not os.path.exists(plugins_dir):
            return
        
        # V5保护模块列表
        protected_modules = {
            "outline-parser-v3", "style-learner-v2", "character-manager",
            "worldview-parser", "context-builder", "iterative-generator-v2",
            "weighted-validator", "optimized-generator-v2", "hot-ranking"
        }
        
        # 尝试使用PluginLoader来发现和注册插件
        try:
            from core.plugin_loader import get_plugin_loader
            from core.plugin_registry import get_plugin_registry, PluginState
            
            loader = get_plugin_loader()
            registry = get_plugin_registry()
            
            # 设置插件目录
            loader._plugin_directories = [plugins_dir]
            
            # 发现插件
            discovered_ids = loader.discover_plugins()
            logger.info(f"Discovered {len(discovered_ids)} plugins")
            
            # 按依赖顺序加载插件
            load_results = loader.load_all()
            logger.info(f"Loaded {sum(1 for r in load_results.values() if r.success)} plugins")
            
            # 清空现有数据
            for item in self._plugin_tree.get_children():
                self._plugin_tree.delete(item)
            self._plugin_data = {}
            
            # 从PluginRegistry获取插件信息并更新UI
            for plugin_id in discovered_ids:
                plugin_info = registry.get_plugin_info(plugin_id)
                if not plugin_info:
                    continue
                
                metadata = plugin_info.metadata
                state = plugin_info.state
                is_protected = plugin_id in protected_modules
                
                # 类型映射
                type_map = {
                    "analyzer": "分析器",
                    "generator": "生成器",
                    "validator": "验证器",
                    "tool": "工具",
                    "storage": "存储",
                    "ai": "AI服务",
                    "protocol": "协议"
                }
                type_text = type_map.get(metadata.plugin_type.lower(), metadata.plugin_type)
                protected_text = "🔒" if is_protected else ""
                
                # 状态映射
                state_map = {
                    "unloaded": "未加载",
                    "loaded": "已加载",
                    "active": "已激活",
                    "error": "错误",
                    "unloading": "卸载中"
                }
                state_text = state_map.get(state, state)
                
                item_id = self._plugin_tree.insert(
                    "",
                    tk.END,
                    values=(
                        metadata.name,
                        metadata.version,
                        state_text,
                        type_text,
                        protected_text
                    )
                )
                
                self._plugin_data[item_id] = {
                    "id": plugin_id,
                    "name": metadata.name,
                    "version": metadata.version,
                    "description": metadata.description,
                    "author": metadata.author,
                    "type": metadata.plugin_type,
                    "state": state,
                    "is_protected": is_protected,
                    "dependencies": metadata.dependencies,
                    "error_message": plugin_info.error_message
                }
                
        except Exception as e:
            logger.error(f"Failed to load plugins via PluginLoader: {e}")
            # 回退到旧的文件扫描方式
            self._load_plugins_from_filesystem_legacy()
    
    def _load_plugins_from_filesystem_legacy(self) -> None:
        """旧的文件扫描方式（作为回退方案）"""
        plugins_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
        
        if not os.path.exists(plugins_dir):
            return
        
        # V5保护模块列表
        protected_modules = {
            "outline-parser-v3", "style-learner-v2", "character-manager",
            "worldview-parser", "context-builder", "iterative-generator-v2",
            "weighted-validator", "optimized-generator-v2", "hot-ranking"
        }
        
        for plugin_name in os.listdir(plugins_dir):
            plugin_path = os.path.join(plugins_dir, plugin_name)
            if os.path.isdir(plugin_path) and not plugin_name.startswith("__"):
                plugin_json = os.path.join(plugin_path, "plugin.json")
                if os.path.exists(plugin_json):
                    try:
                        with open(plugin_json, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        
                        is_protected = plugin_name in protected_modules
                        protected_text = "🔒" if is_protected else ""
                        
                        # 类型映射
                        type_map = {
                            "analyzer": "分析器",
                            "generator": "生成器",
                            "validator": "验证器",
                            "tool": "工具",
                            "storage": "存储",
                            "ai": "AI服务",
                            "protocol": "协议"
                        }
                        type_text = type_map.get(data.get("plugin_type", "tool").lower(), data.get("plugin_type", "工具"))
                        
                        item_id = self._plugin_tree.insert(
                            "",
                            tk.END,
                            values=(
                                data.get("name", plugin_name),
                                data.get("version", "1.0.0"),
                                "已加载" if data.get("enabled", True) else "已禁用",
                                type_text,
                                protected_text
                            )
                        )
                        
                        self._plugin_data[item_id] = {
                            "id": plugin_name,
                            "name": data.get("name", plugin_name),
                            "version": data.get("version", "1.0.0"),
                            "description": data.get("description", ""),
                            "author": data.get("author", ""),
                            "type": data.get("plugin_type", "tool"),
                            "state": "loaded" if data.get("enabled", True) else "disabled",
                            "is_protected": is_protected,
                            "dependencies": data.get("dependencies", []),
                            "error_message": None
                        }
                    except Exception as e:
                        logger.warning(f"Failed to load plugin.json for {plugin_name}: {e}")
    
    def _load_settings_from_config(self) -> None:
        """从config.yaml加载设置到UI"""
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
        
        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f)
                
                if config_data:
                    self._service_mode_var.set(config_data.get("service_mode", "online"))
                    self._provider_var.set(config_data.get("provider", "DeepSeek"))
                    self._model_var.set(config_data.get("model", "deepseek-chat"))
                    self._api_key_var.set(config_data.get("api_key", ""))
                    self._temp_var.set(float(config_data.get("temperature", 0.7)))
                    if hasattr(self, '_theme_var'):
                        self._theme_var.set(config_data.get("theme", "dark"))
                    self._temp_label.configure(text=f"{self._temp_var.get():.2f}")
                    logger.info("Settings loaded from config.yaml")
        except Exception as e:
            logger.warning(f"Failed to load settings from config.yaml: {e}")
    
    # ============== 事件处理器 ==============
    
    def _clear_hot_ranking_cache(self) -> None:
        """清除热榜缓存 - 调用HotRankingPlugin"""
        # 方式1: 从插件注册表获取
        if CORE_AVAILABLE:
            try:
                registry = get_plugin_registry()
                if registry:
                    hot_ranking_plugin = registry.get_plugin("hot-ranking-v1")
                    if hot_ranking_plugin:
                        result = hot_ranking_plugin.execute("clear_cache")
                        if result:
                            messagebox.showinfo("成功", "热榜缓存已清除！")
                            return
            except Exception as e:
                logger.warning(f"[热榜] 插件注册表获取失败: {e}")
        
        # 方式2: 直接动态加载插件
        try:
            import importlib.util
            plugin_path = os.path.join(os.path.dirname(__file__), "plugins", "hot-ranking-v1", "plugin.py")
            spec = importlib.util.spec_from_file_location("hot_ranking_plugin", plugin_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            HotRankingPlugin = module.HotRankingPlugin
            from core.plugin_interface import PluginContext
            context = PluginContext(
                plugin_id="hot-ranking-v1",
                config={},
                event_bus=get_event_bus() if CORE_AVAILABLE else None,
                service_locator=get_service_locator() if CORE_AVAILABLE else None
            )
            
            plugin = HotRankingPlugin()
            if plugin.initialize(context):
                result = plugin.execute("clear_cache")
                if result:
                    messagebox.showinfo("成功", "热榜缓存已清除！")
                    return
        except Exception as e:
            logger.error(f"[热榜] 清除缓存失败: {e}")
        
        messagebox.showinfo("提示", "缓存已清除！")
    
    def _update_hot_ranking_data(self) -> None:
        """更新热榜数据 - 调用HotRankingPlugin爬取真实数据"""
        self._set_status("正在刷新热榜...")
        
        # 定义刷新完成回调
        def on_refresh_complete(data):
            # 回调到主线程刷新UI
            self.root.after(0, lambda: self._on_hot_ranking_refresh_complete(data))
        
        # 方式1: 从插件注册表获取
        if CORE_AVAILABLE:
            try:
                registry = get_plugin_registry()
                if registry:
                    hot_ranking_plugin = registry.get_plugin("hot-ranking-v1")
                    if hot_ranking_plugin:
                        # 使用异步刷新方法
                        hot_ranking_plugin.refresh_async(callback=on_refresh_complete, force_update=True)
                        return
            except Exception as e:
                logger.warning(f"[热榜] 插件注册表获取失败: {e}")
        
        # 方式2: 直接动态加载插件
        try:
            import importlib.util
            plugin_path = os.path.join(os.path.dirname(__file__), "plugins", "hot-ranking-v1", "plugin.py")
            spec = importlib.util.spec_from_file_location("hot_ranking_plugin", plugin_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            HotRankingPlugin = module.HotRankingPlugin
            from core.plugin_interface import PluginContext
            context = PluginContext(
                event_bus=get_event_bus() if CORE_AVAILABLE else None,
                service_locator=get_service_locator() if CORE_AVAILABLE else None,
                config_manager=None,
                plugin_registry=None,
                logger=None
            )
            
            plugin = HotRankingPlugin()
            if plugin.initialize(context):
                # 使用异步刷新
                plugin.refresh_async(callback=on_refresh_complete, force_update=True)
                return
        except Exception as e:
            logger.error(f"[热榜] 更新失败: {e}")
            self._set_status(f"热榜更新失败: {e}")
            return
        
        # 降级：静态刷新
        time.sleep(0.5)
        self._refresh_current_page()
        self._set_status("热榜已更新（离线数据）")
    
    def _on_hot_ranking_refresh_complete(self, data: Dict) -> None:
        """热榜刷新完成回调（主线程执行）"""
        if data:
            self._set_status("热榜已更新（真实数据）")
            # 刷新当前页面显示
            if self._current_page == "hot_ranking":
                self._refresh_current_page()
        else:
            self._set_status("热榜更新失败，请重试")
    
    # ============== 原有回调方法（保留兼容）==============
    
    def _on_worldview(self) -> None:
        """世界观管理"""
        self._switch_to_page("workbench")
        self._workbench_notebook.select(0)  # 切换到世界观标签
    
    def _on_characters(self) -> None:
        """人物设定"""
        self._switch_to_page("workbench")
        self._workbench_notebook.select(1)  # 切换到人物标签
    
    def _on_outline(self) -> None:
        """大纲管理"""
        self._switch_to_page("workbench")
        self._workbench_notebook.select(2)  # 切换到大纲标签
    
    def _on_style(self) -> None:
        """风格学习"""
        self._switch_to_page("workbench")
        self._workbench_notebook.select(3)  # 切换到风格标签
    
    def _on_generation(self) -> None:
        """开始创作"""
        self._switch_to_page("workbench")
        self._workbench_notebook.select(4)  # 切换到创作标签
    
    def _on_reverse(self) -> None:
        """逆向反馈"""
        self._switch_to_page("workbench")
        self._workbench_notebook.select(5)  # 切换到逆向标签
    
    def _on_quick_create(self) -> None:
        """快捷创作"""
        self._switch_to_page("workbench")
        self._workbench_notebook.select(6)  # 切换到快捷标签
    
    def _on_continue(self) -> None:
        """续写功能"""
        self._switch_to_page("workbench")
        self._workbench_notebook.select(7)  # 切换到续写标签
    
    def _on_refresh_progress(self) -> None:
        """刷新进度"""
        self._set_status("刷新进度...")
    
    def _on_export_progress(self) -> None:
        """导出报告"""
        self._set_status("导出报告...")
    
    def _on_reset_progress(self) -> None:
        """重置进度"""
        self._set_status("重置进度...")
    
    def _on_new_project(self) -> None:
        """新建项目 - 完整实现（参考V5版本）"""
        self._set_status("正在创建新项目...")
        
        # 创建弹窗
        dialog = tk.Toplevel(self.root)
        dialog.title("新建项目")
        dialog.geometry("600x550")
        dialog.configure(bg=GlassTheme.GLASS_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 600) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 550) // 2
        dialog.geometry(f"+{x}+{y}")
        
        main_frame = ttk.Frame(dialog, style="TFrame", padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        ttk.Label(main_frame, text="新建小说创作项目", font=('Microsoft YaHei UI', 16, 'bold')).pack(pady=(0, 5))
        ttk.Label(main_frame, text="填写项目信息，开始您的创作之旅", font=('Microsoft YaHei UI', 10), foreground='gray').pack(pady=(0, 20))
        
        # 创建滚动区域
        canvas = tk.Canvas(main_frame, bg=GlassTheme.GLASS_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="TFrame")
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 表单内容
        form_frame = ttk.Frame(scrollable_frame, style="TFrame")
        form_frame.pack(fill=tk.BOTH, expand=True, padx=5)
        
        # 项目名称
        ttk.Label(form_frame, text="项目名称 *", font=('Microsoft YaHei UI', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=8)
        name_entry = ttk.Entry(form_frame, width=40)
        name_entry.grid(row=0, column=1, sticky=tk.EW, pady=8)
        ttk.Label(form_frame, text="（必填）", font=('Microsoft YaHei UI', 9), foreground='gray').grid(row=0, column=2, sticky=tk.W, padx=10, pady=8)
        
        # 作者
        ttk.Label(form_frame, text="作者", font=('Microsoft YaHei UI', 10, 'bold')).grid(row=1, column=0, sticky=tk.W, pady=8)
        author_entry = ttk.Entry(form_frame, width=40)
        author_entry.grid(row=1, column=1, sticky=tk.EW, pady=8)
        ttk.Label(form_frame, text="（可选）", font=('Microsoft YaHei UI', 9), foreground='gray').grid(row=1, column=2, sticky=tk.W, padx=10, pady=8)
        
        # 作品类型
        ttk.Label(form_frame, text="作品类型 *", font=('Microsoft YaHei UI', 10, 'bold')).grid(row=2, column=0, sticky=tk.W, pady=8)
        genre_combo = ttk.Combobox(form_frame, width=37,
                                  values=["玄幻", "武侠", "科幻", "都市", "言情", "历史", "军事", "其他", "仙侠", "灵异", "同人"])
        genre_combo.grid(row=2, column=1, sticky=tk.EW, pady=8)
        genre_combo.current(0)
        ttk.Label(form_frame, text="（必填）", font=('Microsoft YaHei UI', 9), foreground='gray').grid(row=2, column=2, sticky=tk.W, padx=10, pady=8)
        
        # 项目路径
        ttk.Label(form_frame, text="项目路径 *", font=('Microsoft YaHei UI', 10, 'bold')).grid(row=3, column=0, sticky=tk.W, pady=8)
        path_frame = ttk.Frame(form_frame, style="TFrame")
        path_frame.grid(row=3, column=1, sticky=tk.EW, pady=8)
        ttk.Label(form_frame, text="（必填）", font=('Microsoft YaHei UI', 9), foreground='gray').grid(row=3, column=2, sticky=tk.W, padx=10, pady=8)
        
        default_path = os.getcwd()
        path_entry = ttk.Entry(path_frame, width=30)
        path_entry.insert(0, default_path)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        def browse_path():
            path = filedialog.askdirectory(title="选择项目路径", initialdir=default_path)
            if path:
                path_entry.delete(0, tk.END)
                path_entry.insert(0, path)
        
        ttk.Button(path_frame, text="浏览...", command=browse_path, width=8).pack(side=tk.LEFT, padx=(5, 0))
        
        # 目标字数
        ttk.Label(form_frame, text="目标字数 *", font=('Microsoft YaHei UI', 10, 'bold')).grid(row=4, column=0, sticky=tk.W, pady=8)
        words_frame = ttk.Frame(form_frame, style="TFrame")
        words_frame.grid(row=4, column=1, sticky=tk.W, pady=8)
        ttk.Label(form_frame, text="（必填）", font=('Microsoft YaHei UI', 9), foreground='gray').grid(row=4, column=2, sticky=tk.W, padx=10, pady=8)
        
        words_entry = ttk.Entry(words_frame, width=15)
        words_entry.insert(0, "100000")
        words_entry.pack(side=tk.LEFT)
        ttk.Label(words_frame, text="字", font=('Microsoft YaHei UI', 9)).pack(side=tk.LEFT, padx=5)
        
        # 预计章节数
        ttk.Label(form_frame, text="预计章节数", font=('Microsoft YaHei UI', 10, 'bold')).grid(row=5, column=0, sticky=tk.W, pady=8)
        chapters_frame = ttk.Frame(form_frame, style="TFrame")
        chapters_frame.grid(row=5, column=1, sticky=tk.W, pady=8)
        ttk.Label(form_frame, text="（可选）", font=('Microsoft YaHei UI', 9), foreground='gray').grid(row=5, column=2, sticky=tk.W, padx=10, pady=8)
        
        chapters_entry = ttk.Entry(chapters_frame, width=15)
        chapters_entry.insert(0, "50")
        chapters_entry.pack(side=tk.LEFT)
        ttk.Label(chapters_frame, text="章", font=('Microsoft YaHei UI', 9)).pack(side=tk.LEFT, padx=5)
        
        # 项目描述
        ttk.Label(form_frame, text="项目简介", font=('Microsoft YaHei UI', 10, 'bold')).grid(row=6, column=0, sticky=tk.NW, pady=8)
        desc_text = tk.Text(form_frame, width=40, height=6, font=('Microsoft YaHei UI', 10))
        desc_text.grid(row=6, column=1, sticky=tk.EW, pady=8)
        ttk.Label(form_frame, text="（可选）", font=('Microsoft YaHei UI', 9), foreground='gray').grid(row=6, column=2, sticky=tk.W, padx=10, pady=8)
        
        # 提示信息
        info_frame = ttk.LabelFrame(form_frame, text="说明", padding=10)
        info_frame.grid(row=7, column=0, columnspan=3, sticky=tk.EW, pady=15)
        info_text = "项目创建后，将在指定路径下自动创建以下目录结构：\n" \
                    "  • 大纲/ - 存放故事大纲文件（支持.docx和.txt格式）\n" \
                    "  • 人物/ - 存放人物设定文件\n" \
                    "  • 世界观/ - 存放世界观设定文件\n" \
                    "  • 小说/ - 存放生成的小说内容\n" \
                    "  • {项目名}.json - 项目配置文件"
        ttk.Label(info_frame, text=info_text, font=('Microsoft YaHei UI', 9), justify=tk.LEFT).pack(anchor=tk.W)
        
        def confirm_create():
            """确认创建项目"""
            name = name_entry.get().strip()
            author = author_entry.get().strip()
            genre = genre_combo.get()
            path = path_entry.get().strip()
            words = words_entry.get().strip()
            chapters = chapters_entry.get().strip()
            description = desc_text.get("1.0", tk.END).strip()
            
            # 验证必填字段
            if not name:
                messagebox.showwarning("输入错误", "请输入项目名称！", parent=dialog)
                name_entry.focus()
                return
            if not path:
                messagebox.showwarning("输入错误", "请选择项目路径！", parent=dialog)
                path_entry.focus()
                return
            if not os.path.exists(path):
                messagebox.showwarning("路径错误", f"项目路径不存在：{path}", parent=dialog)
                return
            if not words.isdigit() or int(words) <= 0:
                messagebox.showwarning("输入错误", "目标字数必须是大于0的数字！", parent=dialog)
                words_entry.focus()
                return
            
            # 验证项目名是否包含非法字符
            invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
            if any(char in name for char in invalid_chars):
                messagebox.showwarning("输入错误", f"项目名称不能包含以下字符：{' '.join(invalid_chars)}", parent=dialog)
                return
            
            # 检查项目是否已存在
            project_dir = os.path.join(path, name)
            if os.path.exists(project_dir):
                response = messagebox.askyesno("项目已存在", f"目录 '{name}' 已存在，是否覆盖？\n\n警告：这将删除现有项目！", parent=dialog)
                if not response:
                    return
            
            try:
                import shutil
                
                # 创建项目数据
                project_data = {
                    "name": name,
                    "author": author if author else "未设置",
                    "genre": genre,
                    "path": path,
                    "target_words": int(words),
                    "estimated_chapters": int(chapters) if chapters.isdigit() else 50,
                    "description": description,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "modified_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "outline": None,
                    "characters": [],
                    "worldview": [],
                    "generated_content": []
                }
                
                # 删除现有项目目录（如果存在）
                if os.path.exists(project_dir):
                    self._set_status("正在删除现有项目目录...")
                    try:
                        shutil.rmtree(project_dir)
                    except Exception as e:
                        messagebox.showerror("错误", f"无法删除现有项目目录: {e}", parent=dialog)
                        return
                
                # 创建项目主目录
                self._set_status("正在创建项目目录...")
                os.makedirs(project_dir, exist_ok=True)
                
                # 创建子目录
                subdirs = ["大纲", "人物", "世界观", "小说"]
                for subdir in subdirs:
                    subdir_path = os.path.join(project_dir, subdir)
                    os.makedirs(subdir_path, exist_ok=True)
                
                # 创建README文件
                readme_content = f"""# {name}

**作者**: {author if author else "未设置"}
**类型**: {genre}
**创建时间**: {datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}

## 项目简介

{description if description else "暂无简介"}

## 目录说明

- **大纲/**: 存放故事大纲文件（支持.docx和.txt格式）
- **人物/**: 存放人物设定文件
- **世界观/**: 存放世界观设定文件
- **小说/**: 存放生成的小说内容
- **{name}.json**: 项目配置文件

## 使用说明

1. 准备大纲文件（Word或TXT格式）放入"大纲"目录
2. 准备风格学习参考作品（可选）
3. 使用GUI的工作台功能进行创作

---
由 Novel Writing Assistant - Agent Pro 生成
"""
                readme_path = os.path.join(project_dir, "README.md")
                with open(readme_path, 'w', encoding='utf-8') as f:
                    f.write(readme_content)
                
                # 保存项目文件
                project_file = os.path.join(project_dir, f"{name}.json")
                with open(project_file, 'w', encoding='utf-8') as f:
                    json.dump(project_data, f, ensure_ascii=False, indent=2)
                
                # 设置当前项目
                self.current_project = project_data
                self.project_file = project_file
                
                # 更新UI显示
                self._project_name_var.set(name)
                self._project_path_var.set(project_dir)
                
                # 显示成功信息
                success_msg = f"项目创建成功！\n\n"
                success_msg += f"项目名称: {name}\n"
                success_msg += f"项目路径: {project_dir}\n"
                success_msg += f"目标字数: {int(words):,}字\n"
                success_msg += f"预计章节: {chapters if chapters.isdigit() else '50'}章\n\n"
                success_msg += "已创建的文件和目录:\n"
                success_msg += f"- {name}.json (项目配置文件)\n"
                success_msg += "- README.md (项目说明文件)\n"
                success_msg += "- 大纲/、人物/、世界观/、小说/ 目录\n\n"
                success_msg += "下一步：在工作台导入大纲文件，开始创作！"
                
                messagebox.showinfo("创建成功", success_msg, parent=dialog)
                self._set_status(f"项目 '{name}' 创建成功！")
                dialog.destroy()
                
            except Exception as e:
                import traceback
                messagebox.showerror("错误", f"创建项目失败：{e}", parent=dialog)
                self._set_status("创建项目失败")
                traceback.print_exc()
        
        # 按钮
        btn_frame = ttk.Frame(form_frame, style="TFrame")
        btn_frame.grid(row=8, column=0, columnspan=3, pady=20)
        
        ttk.Button(btn_frame, text="创建项目", command=confirm_create, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy, width=10).pack(side=tk.LEFT, padx=5)
        
        name_entry.focus()
    
    def _on_open_project(self) -> None:
        """打开项目 - 完整实现（参考V5版本）"""
        # 首先尝试打开项目JSON文件
        project_file = filedialog.askopenfilename(
            title="打开项目",
            filetypes=[("项目文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if not project_file:
            return
        
        self._set_status("正在加载项目...")
        
        def load_project_thread():
            """后台线程加载项目"""
            try:
                # 检查文件是否存在
                if not os.path.exists(project_file):
                    self.root.after(0, lambda: [
                        messagebox.showerror("错误", f"项目文件不存在: {project_file}"),
                        self._set_status("打开项目失败")
                    ])
                    return
                
                # 读取项目文件
                with open(project_file, 'r', encoding='utf-8') as f:
                    project_data = json.load(f)
                
                # 验证项目数据
                if not isinstance(project_data, dict):
                    raise ValueError("项目文件格式错误")
                
                project_name = project_data.get('name', '未命名项目')
                
                # 更新主线程UI
                def update_ui():
                    self.current_project = project_data
                    self.project_file = project_file
                    
                    # 更新显示
                    self._project_name_var.set(project_name)
                    project_dir = os.path.dirname(project_file)
                    self._project_path_var.set(project_dir)
                    
                    self._set_status(f"项目 '{project_name}' 已打开")
                    
                    # 显示成功信息
                    info_msg = f"项目加载成功！\n\n"
                    info_msg += f"项目名称: {project_name}\n"
                    info_msg += f"作者: {project_data.get('author', '未设置')}\n"
                    info_msg += f"类型: {project_data.get('genre', '未设置')}\n"
                    info_msg += f"目标字数: {project_data.get('target_words', 0):,}字\n"
                    
                    # 检查项目完整性
                    missing = []
                    if not project_data.get('outline'):
                        missing.append("大纲")
                    if not project_data.get('characters'):
                        missing.append("人物设定")
                    if not project_data.get('worldview'):
                        missing.append("世界观设定")
                    
                    if missing:
                        info_msg += f"\n\n提示：以下内容尚未设置：{', '.join(missing)}"
                    
                    messagebox.showinfo("项目已打开", info_msg)
                
                self.root.after(0, update_ui)
                
            except json.JSONDecodeError as e:
                self.root.after(0, lambda: [
                    messagebox.showerror("错误", f"项目文件格式错误: {e}"),
                    self._set_status("打开项目失败")
                ])
            except Exception as e:
                self.root.after(0, lambda: [
                    messagebox.showerror("错误", f"打开项目失败: {e}"),
                    self._set_status("打开项目失败")
                ])
        
        # 启动后台线程
        thread = threading.Thread(target=load_project_thread, daemon=True)
        thread.start()
    
    def _on_backup_project(self) -> None:
        """备份项目 - 完整实现"""
        if not self.current_project or not hasattr(self, 'project_file'):
            messagebox.showwarning("备份项目", "当前没有打开的项目")
            return
        
        try:
            self._set_status("正在创建备份...")
            
            # 获取备份目录
            project_dir = os.path.dirname(self.project_file)
            project_name = self.current_project.get('name', '未命名')
            
            # 创建备份目录
            backup_dir = os.path.join(project_dir, "backups")
            os.makedirs(backup_dir, exist_ok=True)
            
            # 生成备份文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(backup_dir, f"{project_name}_backup_{timestamp}.json")
            
            # 更新修改时间
            self.current_project['modified_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 保存备份
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(self.current_project, f, ensure_ascii=False, indent=2)
            
            messagebox.showinfo("备份成功", f"项目备份已创建！\n\n备份位置：{backup_file}")
            self._set_status("项目备份完成")
            
        except Exception as e:
            messagebox.showerror("错误", f"备份失败: {e}")
            self._set_status("备份失败")
    
    def _on_refresh_plugins(self) -> None:
        """刷新插件列表"""
        self._load_plugins()
        self._set_status("插件列表已刷新")
    
    def _on_plugin_select(self, event) -> None:
        """插件选择事件 - 更新详情显示"""
        selection = self._plugin_tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        plugin_data = self._plugin_data.get(item_id, {})
        
        # 更新详情显示
        details = [
            f"ID: {plugin_data.get('id', 'N/A')}",
            f"名称: {plugin_data.get('name', 'N/A')}",
            f"版本: {plugin_data.get('version', 'N/A')}",
            f"作者: {plugin_data.get('author', 'N/A')}",
            f"描述: {plugin_data.get('description', 'N/A')}",
            f"状态: {plugin_data.get('state', 'N/A')}",
        ]
        
        if plugin_data.get('is_protected'):
            details.append("⚠️ V5核心保护模块（禁止禁用）")
        
        if plugin_data.get('dependencies'):
            details.append(f"依赖: {', '.join(plugin_data['dependencies'])}")
        
        if plugin_data.get('error_message'):
            details.append(f"错误: {plugin_data['error_message']}")
        
        self._plugin_detail_var.set("\n".join(details))
    
    def _on_plugin_double_click(self, event) -> None:
        """双击插件打开配置对话框"""
        self._on_config_plugin()
    
    def _get_selected_plugin(self) -> Optional[Dict[str, Any]]:
        """获取当前选中的插件数据"""
        selection = self._plugin_tree.selection()
        if not selection:
            return None
        return self._plugin_data.get(selection[0])
    
    def _get_plugin_registry(self):
        """获取PluginRegistry实例"""
        if not CORE_AVAILABLE:
            return None
        try:
            return get_plugin_registry()
        except Exception as e:
            logger.warning(f"Failed to get PluginRegistry: {e}")
            return None
    
    def _get_config_manager(self):
        """获取ConfigManager实例"""
        if not CORE_AVAILABLE:
            return None
        try:
            return get_config_manager()
        except Exception as e:
            logger.warning(f"Failed to get ConfigManager: {e}")
            return None
    
    def _on_enable_plugin(self) -> None:
        """启用插件 - 调用PluginRegistry.activate()"""
        plugin_data = self._get_selected_plugin()
        if not plugin_data:
            messagebox.showwarning("提示", "请先选择一个插件")
            return
        
        plugin_id = plugin_data["id"]
        
        # 检查保护状态
        if plugin_data.get("is_protected"):
            messagebox.showwarning("警告", f"插件 '{plugin_id}' 是V5核心保护模块，无法禁用/启用操作")
            return
        
        # 检查当前状态
        if plugin_data.get("state") == "active":
            messagebox.showinfo("提示", f"插件 '{plugin_id}' 已经处于启用状态")
            return
        
        # 调用PluginRegistry激活插件
        registry = self._get_plugin_registry()
        if registry:
            try:
                success = registry.activate(plugin_id)
                if success:
                    self._set_status(f"插件 '{plugin_id}' 已启用")
                    self._load_plugins()  # 刷新列表
                    messagebox.showinfo("成功", f"插件 '{plugin_id}' 已成功启用")
                else:
                    messagebox.showerror("失败", f"插件 '{plugin_id}' 启用失败")
            except Exception as e:
                messagebox.showerror("错误", f"启用插件时发生错误：{e}")
        else:
            messagebox.showwarning("提示", "PluginRegistry不可用")
    
    def _on_disable_plugin(self) -> None:
        """禁用插件 - 调用PluginRegistry.deactivate()"""
        plugin_data = self._get_selected_plugin()
        if not plugin_data:
            messagebox.showwarning("提示", "请先选择一个插件")
            return
        
        plugin_id = plugin_data["id"]
        
        # 检查保护状态
        if plugin_data.get("is_protected"):
            messagebox.showwarning("警告", f"插件 '{plugin_id}' 是V5核心保护模块，禁止禁用")
            return
        
        # 检查当前状态
        if plugin_data.get("state") != "active":
            messagebox.showinfo("提示", f"插件 '{plugin_id}' 当前未启用")
            return
        
        # 确认对话框
        if not messagebox.askyesno("确认", f"确定要禁用插件 '{plugin_id}' 吗？\n禁用后相关功能将不可用。"):
            return
        
        # 调用PluginRegistry停用插件
        registry = self._get_plugin_registry()
        if registry:
            try:
                success = registry.deactivate(plugin_id)
                if success:
                    self._set_status(f"插件 '{plugin_id}' 已禁用")
                    self._load_plugins()  # 刷新列表
                    messagebox.showinfo("成功", f"插件 '{plugin_id}' 已成功禁用")
                else:
                    messagebox.showerror("失败", f"插件 '{plugin_id}' 禁用失败")
            except Exception as e:
                messagebox.showerror("错误", f"禁用插件时发生错误：{e}")
        else:
            messagebox.showwarning("提示", "PluginRegistry不可用")
    
    def _on_config_plugin(self) -> None:
        """打开插件配置对话框"""
        plugin_data = self._get_selected_plugin()
        if not plugin_data:
            messagebox.showwarning("提示", "请先选择一个插件")
            return
        
        plugin_id = plugin_data["id"]
        plugin_name = plugin_data.get("name", plugin_id)
        
        # 创建配置对话框
        self._show_plugin_config_dialog(plugin_id, plugin_name, plugin_data)
    
    def _show_plugin_config_dialog(self, plugin_id: str, plugin_name: str, plugin_data: Dict) -> None:
        """显示插件配置对话框
        
        Args:
            plugin_id: 插件ID
            plugin_name: 插件显示名称
            plugin_data: 插件数据字典
        """
        dialog = tk.Toplevel(self.root)
        dialog.title(f"插件配置 - {plugin_name}")
        dialog.geometry("500x400")
        dialog.configure(bg=GlassTheme.GLASS_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 500) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 400) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 主框架
        main_frame = ttk.Frame(dialog, style="TFrame", padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 插件信息
        info_frame = ttk.LabelFrame(main_frame, text="插件信息", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        info_text = f"""
ID: {plugin_id}
名称: {plugin_name}
版本: {plugin_data.get('version', 'N/A')}
作者: {plugin_data.get('author', 'N/A')}
类型: {plugin_data.get('type', 'N/A')}
状态: {plugin_data.get('state', 'N/A')}
保护: {'是 (V5核心模块)' if plugin_data.get('is_protected') else '否'}
        """.strip()
        
        info_label = ttk.Label(info_frame, text=info_text, justify=tk.LEFT)
        info_label.pack(anchor=tk.W)
        
        # 配置区域（根据插件类型动态生成）
        config_frame = ttk.LabelFrame(main_frame, text="插件配置", padding=10)
        config_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 存储配置变量
        config_vars: Dict[str, tk.Variable] = {}
        
        # 从ConfigManager加载插件配置
        plugin_config = {}
        config = self._get_config_manager()
        if config:
            # 插件配置路径: plugins.{plugin_id}.*
            config_keys = config.list_keys(f"plugins.{plugin_id}")
            for key in config_keys:
                value = config.get(key)
                plugin_config[key] = value
        
        # 如果没有配置，显示默认配置选项
        if not plugin_config:
            # 根据插件类型提供默认配置选项
            default_configs = self._get_default_plugin_config(plugin_id, plugin_data.get('type', 'tool'))
            
            for config_key, config_info in default_configs.items():
                row_frame = ttk.Frame(config_frame, style="TFrame")
                row_frame.pack(fill=tk.X, pady=5)
                
                ttk.Label(row_frame, text=config_info['label'] + "：").pack(side=tk.LEFT)
                
                if config_info['type'] == 'string':
                    var = tk.StringVar(value=config_info.get('default', ''))
                    entry = ttk.Entry(row_frame, textvariable=var, width=30)
                    entry.pack(side=tk.LEFT, padx=10)
                    config_vars[config_key] = var
                elif config_info['type'] == 'int':
                    var = tk.IntVar(value=config_info.get('default', 0))
                    spinbox = ttk.Spinbox(row_frame, from_=0, to=100, textvariable=var, width=10)
                    spinbox.pack(side=tk.LEFT, padx=10)
                    config_vars[config_key] = var
                elif config_info['type'] == 'boolean':
                    var = tk.BooleanVar(value=config_info.get('default', True))
                    ttk.Checkbutton(row_frame, variable=var).pack(side=tk.LEFT, padx=10)
                    config_vars[config_key] = var
                elif config_info['type'] == 'choice':
                    var = tk.StringVar(value=config_info.get('default', ''))
                    combo = ttk.Combobox(row_frame, textvariable=var, values=config_info.get('choices', []), width=25)
                    combo.pack(side=tk.LEFT, padx=10)
                    config_vars[config_key] = var
        else:
            # 显示已有配置
            for key, value in plugin_config.items():
                row_frame = ttk.Frame(config_frame, style="TFrame")
                row_frame.pack(fill=tk.X, pady=5)
                
                # 提取配置键名（去掉前缀）
                display_key = key.replace(f"plugins.{plugin_id}.", "")
                ttk.Label(row_frame, text=display_key + "：").pack(side=tk.LEFT)
                
                if isinstance(value, bool):
                    var = tk.BooleanVar(value=value)
                    ttk.Checkbutton(row_frame, variable=var).pack(side=tk.LEFT, padx=10)
                    config_vars[key] = var
                elif isinstance(value, int):
                    var = tk.IntVar(value=value)
                    spinbox = ttk.Spinbox(row_frame, from_=0, to=10000, textvariable=var, width=10)
                    spinbox.pack(side=tk.LEFT, padx=10)
                    config_vars[key] = var
                else:
                    var = tk.StringVar(value=str(value))
                    entry = ttk.Entry(row_frame, textvariable=var, width=30)
                    entry.pack(side=tk.LEFT, padx=10)
                    config_vars[key] = var
        
        # 如果是保护模块，显示警告
        if plugin_data.get('is_protected'):
            warning_label = ttk.Label(
                config_frame, 
                text="⚠️ 此插件为V5核心保护模块，部分配置修改可能导致系统不稳定",
                foreground=GlassTheme.WARNING
            )
            warning_label.pack(pady=10)
        
        # 按钮区域
        btn_frame = ttk.Frame(main_frame, style="TFrame")
        btn_frame.pack(fill=tk.X)
        
        def save_config():
            """保存配置到ConfigManager"""
            config = self._get_config_manager()
            if config:
                try:
                    for key, var in config_vars.items():
                        full_key = f"plugins.{plugin_id}.{key}" if not key.startswith("plugins.") else key
                        value = var.get()
                        config.set(full_key, value, source="user")
                    
                    # 保存到文件
                    config._save_config()
                    
                    messagebox.showinfo("成功", "配置已保存")
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("错误", f"保存配置失败：{e}")
            else:
                messagebox.showwarning("提示", "ConfigManager不可用，无法保存配置")
        
        def reset_config():
            """重置配置为默认值"""
            for key, var in config_vars.items():
                default_configs = self._get_default_plugin_config(plugin_id, plugin_data.get('type', 'tool'))
                if key in default_configs:
                    var.set(default_configs[key].get('default', ''))
        
        ttk.Button(btn_frame, text="保存", command=save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="重置", command=reset_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def _get_default_plugin_config(self, plugin_id: str, plugin_type: str) -> Dict[str, Dict]:
        """获取插件的默认配置选项
        
        Args:
            plugin_id: 插件ID
            plugin_type: 插件类型
            
        Returns:
            配置选项字典 {config_key: {label, type, default, choices}}
        """
        # 通用配置
        common_config = {
            "enabled": {
                "label": "启用插件",
                "type": "boolean",
                "default": True
            },
            "log_level": {
                "label": "日志级别",
                "type": "choice",
                "default": "INFO",
                "choices": ["DEBUG", "INFO", "WARNING", "ERROR"]
            }
        }
        
        # 根据插件类型添加特定配置
        type_specific_configs = {
            "analyzer": {
                "max_content_length": {
                    "label": "最大内容长度",
                    "type": "int",
                    "default": 100000
                },
                "cache_enabled": {
                    "label": "启用缓存",
                    "type": "boolean",
                    "default": True
                }
            },
            "generator": {
                "max_retries": {
                    "label": "最大重试次数",
                    "type": "int",
                    "default": 3
                },
                "timeout": {
                    "label": "超时时间(秒)",
                    "type": "int",
                    "default": 300
                }
            },
            "validator": {
                "strict_mode": {
                    "label": "严格模式",
                    "type": "boolean",
                    "default": False
                },
                "min_score": {
                    "label": "最低分数",
                    "type": "int",
                    "default": 60
                }
            },
            "tool": {
                "auto_start": {
                    "label": "自动启动",
                    "type": "boolean",
                    "default": True
                }
            }
        }
        
        # 合并配置
        config = common_config.copy()
        if plugin_type.lower() in type_specific_configs:
            config.update(type_specific_configs[plugin_type.lower()])
        
        # 插件特定配置（例如大纲解析器的编码设置）
        if plugin_id == "outline-parser-v3":
            config["encoding"] = {
                "label": "文件编码",
                "type": "choice",
                "default": "utf-8",
                "choices": ["utf-8", "gbk", "gb2312", "big5"]
            }
        
        return config
    
    def _on_reload_plugin(self) -> None:
        """重新加载插件"""
        plugin_data = self._get_selected_plugin()
        if not plugin_data:
            messagebox.showwarning("提示", "请先选择一个插件")
            return
        
        plugin_id = plugin_data["id"]
        
        # 检查保护状态
        if plugin_data.get("is_protected"):
            messagebox.showwarning("警告", f"插件 '{plugin_id}' 是V5核心保护模块，禁止重新加载")
            return
        
        # 确认对话框
        if not messagebox.askyesno("确认", f"确定要重新加载插件 '{plugin_id}' 吗？"):
            return
        
        # 调用PluginRegistry重新加载
        registry = self._get_plugin_registry()
        if registry:
            try:
                success, error = registry.reload_plugin_runtime(plugin_id)
                if success:
                    self._set_status(f"插件 '{plugin_id}' 已重新加载")
                    self._load_plugins()  # 刷新列表
                    messagebox.showinfo("成功", f"插件 '{plugin_id}' 已成功重新加载")
                else:
                    messagebox.showerror("失败", f"插件 '{plugin_id}' 重新加载失败：{error}")
            except Exception as e:
                messagebox.showerror("错误", f"重新加载插件时发生错误：{e}")
        else:
            messagebox.showwarning("提示", "PluginRegistry不可用")
    
    def _on_install_plugin(self) -> None:
        """安装插件"""
        # 选择插件包文件
        file_path = filedialog.askopenfilename(
            title="选择插件包",
            filetypes=[("Plugin Package", "*.zip;*.tar.gz"), ("All Files", "*.*")]
        )
        
        if not file_path:
            return
        
        self._set_status(f"正在安装插件：{os.path.basename(file_path)}")
        # TODO: 实现插件安装逻辑
        messagebox.showinfo("提示", "插件安装功能开发中...")
    
    def _on_uninstall_plugin(self) -> None:
        """卸载插件"""
        plugin_data = self._get_selected_plugin()
        if not plugin_data:
            messagebox.showwarning("提示", "请先选择一个插件")
            return
        
        plugin_id = plugin_data["id"]
        
        # 检查保护状态
        if plugin_data.get("is_protected"):
            messagebox.showwarning("警告", f"插件 '{plugin_id}' 是V5核心保护模块，禁止卸载")
            return
        
        # 确认对话框
        if not messagebox.askyesno("确认卸载", 
            f"确定要卸载插件 '{plugin_id}' 吗？\n\n此操作将移除插件及其配置，且不可恢复！"):
            return
        
        # 调用PluginRegistry卸载
        registry = self._get_plugin_registry()
        if registry:
            try:
                success, error = registry.unload_plugin_runtime(plugin_id)
                if success:
                    self._set_status(f"插件 '{plugin_id}' 已卸载")
                    self._load_plugins()  # 刷新列表
                    messagebox.showinfo("成功", f"插件 '{plugin_id}' 已成功卸载")
                else:
                    messagebox.showerror("失败", f"插件 '{plugin_id}' 卸载失败：{error}")
            except Exception as e:
                messagebox.showerror("错误", f"卸载插件时发生错误：{e}")
        else:
            messagebox.showwarning("提示", "PluginRegistry不可用")
    
    def _on_save_settings(self) -> None:
        """保存设置到config.yaml并应用"""
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
        
        config_data = {
            "service_mode": self._service_mode_var.get(),
            "provider": self._provider_var.get(),
            "model": self._model_var.get(),
            "api_key": self._api_key_var.get(),
            "local_url": self._local_url_var.get(),
            "temperature": self._temp_var.get(),
            "theme": self._theme_var.get() if hasattr(self, '_theme_var') else "dark",
            "ai_learning": self._ai_learning_var.get() if hasattr(self, '_ai_learning_var') else True,
            "auto_save": True,
            "backup_interval": self._backup_interval_var.get() if hasattr(self, '_backup_interval_var') else "30",
            "font_size": self._font_size_var.get() if hasattr(self, '_font_size_var') else "14",
            "window_size": self._window_size_var.get() if hasattr(self, '_window_size_var') else "1280x720",
            "save_path": self._save_path_var.get() if hasattr(self, '_save_path_var') else os.path.dirname(os.path.abspath(__file__))
        }
        
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False)
            
            if self._services and self._services.config:
                self._services.config.set("provider", self._provider_var.get())
                self._services.config.set("model", self._model_var.get())
                self._services.config.set("temperature", self._temp_var.get())
            
            # 应用设置
            self._apply_settings(config_data)
            
            self._set_status("设置已保存并应用")
            messagebox.showinfo("成功", "设置已保存并应用！\n部分设置可能需要重启程序才能完全生效。")
            
        except Exception as e:
            self._set_status(f"保存设置失败：{e}")
            messagebox.showerror("错误", f"保存设置失败：{e}")
    
    def _apply_settings(self, config_data: dict) -> None:
        """应用设置到界面"""
        # 应用主题（深色/浅色）
        theme = config_data.get("theme", "dark")
        if theme == "light":
            # 浅色主题配置
            GlassTheme.GLASS_BG = "#FFFFFF"
            GlassTheme.GLASS_SURFACE = "#F5F5F5"
            GlassTheme.TEXT_PRIMARY = "#333333"
            GlassTheme.TEXT_SECONDARY = "#666666"
        else:
            # 深色主题配置（默认）
            GlassTheme.GLASS_BG = "#1E1E1E"
            GlassTheme.GLASS_SURFACE = "#2D2D2D"
            GlassTheme.TEXT_PRIMARY = "#FFFFFF"
            GlassTheme.TEXT_SECONDARY = "#CCCCCC"
        
        # 应用字体大小
        font_size = int(config_data.get("font_size", 14))
        GlassTheme.FONT_SIZE_NORMAL = str(font_size)
        GlassTheme.FONT_SIZE_SMALL = str(max(10, font_size - 2))
        GlassTheme.FONT_SIZE_SUBTITLE = str(max(14, font_size - 2))
        GlassTheme.FONT_SIZE_TITLE = str(max(18, font_size + 4))
        
        # 应用窗口大小（需要重启才生效）
        window_size = config_data.get("window_size", "1280x720")
        # 保存到配置文件，下次启动时应用
        self.root.after(100, lambda: self._set_status(f"窗口大小将在重启后应用：{window_size}"))
    
    def _on_browse_save_path(self):
        """浏览默认保存路径"""
        path = filedialog.askdirectory(title="选择默认保存路径")
        if path:
            self._save_path_var.set(path)
    
    def _on_clear_learning_data(self):
        """清除学习数据"""
        if messagebox.askyesno("确认清除", "确定要清除所有AI学习数据吗？\n这将重置您的写作偏好配置。"):
            self._set_status("学习数据已清除")
    
    def _on_export_preferences(self):
        """导出偏好配置"""
        path = filedialog.asksaveasfilename(
            title="导出偏好配置",
            defaultextension=".yaml",
            filetypes=[("YAML文件", "*.yaml"), ("所有文件", "*.*")]
        )
        if path:
            self._set_status(f"偏好配置已导出到：{os.path.basename(path)}")
    
    def _on_service_mode_changed(self):
        """服务模式切换回调"""
        if self._service_mode_var.get() == "local":
            # 本地模式：显示部署地址，隐藏API Key
            self._key_label.config(text="本地部署地址：")
            self._key_entry.pack_forget()
            self._url_entry.pack(side=tk.LEFT, padx=10)
        else:
            # 线上模式：显示API Key，隐藏本地地址
            self._key_label.config(text="API Key：")
            self._url_entry.pack_forget()
            self._key_entry.pack(side=tk.LEFT, padx=10)
    
    def _on_theme_changed(self):
        """主题切换回调"""
        theme = self._theme_var.get()
        if theme == "light":
            # 浅色主题配置（使用半透明效果）
            GlassTheme.GLASS_BG = "#F0F0F0"
            GlassTheme.GLASS_SURFACE = "#FAFAFA"
            GlassTheme.TEXT_PRIMARY = "#333333"
            GlassTheme.TEXT_SECONDARY = "#666666"
        else:
            # 深色主题配置（默认）
            GlassTheme.GLASS_BG = "#1E1E1E"
            GlassTheme.GLASS_SURFACE = "#2D2D2D"
            GlassTheme.TEXT_PRIMARY = "#FFFFFF"
            GlassTheme.TEXT_SECONDARY = "#CCCCCC"
        # 立即刷新所有UI元素
        self._refresh_theme()
        self._set_status(f"主题已切换为：{'浅色' if theme == 'light' else '深色'}")

    def _refresh_theme(self):
        """刷新所有UI元素的主题"""
        # 更新主窗口背景
        self.root.configure(bg=GlassTheme.GLASS_BG)

        # 更新标题栏
        if hasattr(self, '_title_bar'):
            self._title_bar.configure(bg=GlassTheme.GLASS_SURFACE)

        # 更新侧边栏
        if hasattr(self, '_sidebar'):
            self._sidebar.configure(bg=GlassTheme.GLASS_SURFACE)

        # 更新所有Text组件
        for widget in self.root.winfo_children():
            self._update_widget_theme(widget)

    def _update_widget_theme(self, widget):
        """递归更新所有组件的主题"""
        try:
            if isinstance(widget, tk.Text):
                widget.configure(bg=GlassTheme.GLASS_SURFACE, fg=GlassTheme.TEXT_PRIMARY)
            elif isinstance(widget, tk.Label) and widget.cget("style") == "":
                widget.configure(bg=GlassTheme.GLASS_BG, fg=GlassTheme.TEXT_PRIMARY)
            elif isinstance(widget, tk.Label) and widget.cget("bg") == GlassTheme.GLASS_BG:
                widget.configure(bg=GlassTheme.GLASS_BG)
            elif isinstance(widget, tk.Label) and widget.cget("bg") == GlassTheme.GLASS_SURFACE:
                widget.configure(bg=GlassTheme.GLASS_SURFACE)

            # 递归处理子组件
            for child in widget.winfo_children():
                self._update_widget_theme(child)
        except Exception:
            pass
    
    def _on_font_size_changed(self):
        """字体大小改变回调"""
        try:
            font_size = int(self._font_size_var.get())
            # 更新GlassTheme字体大小
            GlassTheme.FONT_SIZE_NORMAL = str(font_size)
            GlassTheme.FONT_SIZE_SMALL = str(max(10, font_size - 2))
            GlassTheme.FONT_SIZE_SUBTITLE = str(max(14, font_size - 2))
            GlassTheme.FONT_SIZE_TITLE = str(max(18, font_size + 4))

            # 立即刷新所有字体
            self._refresh_fonts()
            self._set_status(f"字体大小已更新为：{font_size}px")
        except ValueError:
            messagebox.showerror("错误", "请输入有效的字体大小（10-20）")

    def _refresh_fonts(self):
        """刷新所有UI元素的字体"""
        # 更新所有Text组件字体
        for widget in self.root.winfo_children():
            self._update_widget_font(widget)

    def _update_widget_font(self, widget):
        """递归更新所有组件的字体"""
        try:
            if isinstance(widget, tk.Text):
                widget.configure(font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL))
            elif isinstance(widget, tk.Label) and widget.cget("font") != "":
                # 获取原有字体设置（粗体等）
                current_font = widget.cget("font")
                if isinstance(current_font, tuple) and len(current_font) >= 3:
                    # 保留字体族和粗体样式
                    widget.configure(font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL, current_font[2]))
                elif isinstance(current_font, tuple) and len(current_font) >= 2:
                    widget.configure(font=(GlassTheme.FONT_FAMILY, GlassTheme.FONT_SIZE_NORMAL))

            # 递归处理子组件
            for child in widget.winfo_children():
                self._update_widget_font(child)
        except Exception:
            pass

    # ============== 生成事件订阅 ==============
    
    def _subscribe_generation_events(self) -> None:
        """订阅生成相关事件，绑定到开始创作页面"""
        event_bus = get_event_bus()
        if not event_bus:
            return
        
        events = [
            ("generation.started", self._on_gen_event_started),
            ("generation.completed", self._on_gen_event_completed),
            ("generation.failed", self._on_gen_event_failed),
            ("generation.progress", self._on_gen_event_progress),
            ("pipeline.stage_started", self._on_gen_event_stage_started),
            ("pipeline.stage_completed", self._on_gen_event_stage_completed),
            ("pipeline.iteration_started", self._on_gen_event_iteration_started),
            ("pipeline.completed", self._on_gen_event_pipeline_completed),
            ("agent.task.started", self._on_gen_event_agent_started),
            ("agent.task.completed", self._on_gen_event_agent_completed),
            ("agent.task.failed", self._on_gen_event_agent_failed),
        ]
        
        for event_type, handler in events:
            try:
                sub_id = event_bus.subscribe(event_type, handler)
                self._subscription_ids.append(sub_id)
            except Exception as e:
                logger.warning(f"订阅事件失败 {event_type}: {e}")
        
        logger.info(f"Subscribed to {len(self._subscription_ids)} generation events")
    
    def _unsubscribe_generation_events(self) -> None:
        """取消订阅生成事件"""
        event_bus = get_event_bus()
        if not event_bus:
            return
        
        for sub_id in self._subscription_ids:
            try:
                event_bus.unsubscribe(sub_id)
            except Exception:
                pass
        
        self._subscription_ids.clear()
    
    def _gen_log_insert(self, message: str) -> None:
        """线程安全地向生成日志插入消息"""
        if hasattr(self, '_gen_log') and self._gen_log:
            self._gen_log.insert(tk.END, message)
            self._gen_log.see(tk.END)
    
    def _gen_update_status(self, status: str) -> None:
        """线程安全地更新生成状态"""
        if hasattr(self, '_gen_status_var') and self._gen_status_var:
            self._gen_status_var.set(status)
    
    def _gen_update_progress(self, value: float) -> None:
        """线程安全地更新进度条"""
        if hasattr(self, '_gen_progress') and self._gen_progress:
            self._gen_progress['value'] = value
    
    # === 事件处理器 ===
    
    def _on_gen_event_started(self, event) -> None:
        """生成开始事件"""
        def update():
            self._gen_update_status("🚀 生成任务已开始")
            self._gen_log_insert(f"[{self._timestamp()}] 🚀 生成任务已开始\n")
            pipeline_id = event.data.get("pipeline_id", "")
            if pipeline_id:
                self._gen_log_insert(f"[{self._timestamp()}] Pipeline ID: {pipeline_id}\n")
        
        self.root.after(0, update)
    
    def _on_gen_event_completed(self, event) -> None:
        """生成完成事件"""
        def update():
            self._gen_update_status("✅ 生成任务已完成")
            total_words = event.data.get("total_words", 0)
            self._gen_log_insert(f"[{self._timestamp()}] ✅ 生成任务已完成\n")
            self._gen_log_insert(f"[{self._timestamp()}] 总字数: {total_words}\n")
            self._gen_update_progress(100)
        
        self.root.after(0, update)
    
    def _on_gen_event_failed(self, event) -> None:
        """生成失败事件"""
        def update():
            self._gen_update_status("❌ 生成任务失败")
            error = event.data.get("error", "未知错误")
            self._gen_log_insert(f"[{self._timestamp()}] ❌ 生成失败: {error}\n")
        
        self.root.after(0, update)
    
    def _on_gen_event_progress(self, event) -> None:
        """生成进度事件"""
        def update():
            progress = event.data.get("progress", 0)
            message = event.data.get("message", "")
            self._gen_update_progress(progress)
            if message:
                self._gen_log_insert(f"[{self._timestamp()}] 📊 {message} ({progress}%)\n")
        
        self.root.after(0, update)
    
    def _on_gen_event_stage_started(self, event) -> None:
        """阶段开始事件"""
        def update():
            stage = event.data.get("stage", "Unknown")
            self._gen_log_insert(f"[{self._timestamp()}] 🔄 阶段开始: {stage}\n")
        
        self.root.after(0, update)
    
    def _on_gen_event_stage_completed(self, event) -> None:
        """阶段完成事件"""
        def update():
            stage = event.data.get("stage", "Unknown")
            success = event.data.get("success", False)
            status = "✅" if success else "❌"
            self._gen_log_insert(f"[{self._timestamp()}] {status} 阶段完成: {stage}\n")
        
        self.root.after(0, update)
    
    def _on_gen_event_iteration_started(self, event) -> None:
        """迭代开始事件"""
        def update():
            iteration = event.data.get("iteration", 0)
            max_iterations = event.data.get("max_iterations", 0)
            self._gen_log_insert(f"[{self._timestamp()}] 🔁 迭代 {iteration}/{max_iterations}\n")
        
        self.root.after(0, update)
    
    def _on_gen_event_pipeline_completed(self, event) -> None:
        """流水线完成事件"""
        def update():
            success = event.data.get("success", False)
            status = "✅ 成功" if success else "❌ 失败"
            self._gen_log_insert(f"[{self._timestamp()}] 🏁 流水线{status}\n")
        
        self.root.after(0, update)
    
    def _on_gen_event_agent_started(self, event) -> None:
        """Agent任务开始事件"""
        def update():
            agent_name = event.data.get("agent", "Unknown")
            task_id = event.data.get("task_id", "")
            self._gen_log_insert(f"[{self._timestamp()}] 🤖 Agent启动: {agent_name}\n")
            # 更新Agent状态树
            if hasattr(self, '_gen_agent_tree') and self._gen_agent_tree:
                self._gen_agent_tree.insert("", tk.END, iid=task_id or agent_name, values=("🔄 运行中", agent_name))
        
        self.root.after(0, update)
    
    def _on_gen_event_agent_completed(self, event) -> None:
        """Agent任务完成事件"""
        def update():
            agent_name = event.data.get("agent", "Unknown")
            success = event.data.get("success", False)
            task_id = event.data.get("task_id", "")
            status = "✅" if success else "❌"
            self._gen_log_insert(f"[{self._timestamp()}] {status} Agent完成: {agent_name}\n")
            # 更新Agent状态树
            if hasattr(self, '_gen_agent_tree') and self._gen_agent_tree:
                item_id = task_id or agent_name
                try:
                    self._gen_agent_tree.item(item_id, values=(f"{status} 完成", agent_name))
                except Exception:
                    pass  # 如果项目不存在，忽略错误
        
        self.root.after(0, update)
    
    def _on_gen_event_agent_failed(self, event) -> None:
        """Agent任务失败事件"""
        def update():
            agent_name = event.data.get("agent", "Unknown")
            error = event.data.get("error", "未知错误")
            task_id = event.data.get("task_id", "")
            self._gen_log_insert(f"[{self._timestamp()}] ❌ Agent失败: {agent_name} - {error}\n")
            # 更新Agent状态树
            if hasattr(self, '_gen_agent_tree') and self._gen_agent_tree:
                item_id = task_id or agent_name
                try:
                    self._gen_agent_tree.item(item_id, values=(f"❌ 失败", f"{agent_name}: {error[:30]}"))
                except Exception:
                    pass
        
        self.root.after(0, update)
    
    def _timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")

    
    def _on_close(self) -> None:
        """窗口关闭确认"""
        if messagebox.askokcancel("退出", "确定要退出吗？\n未保存的内容将会丢失。"):
            # 取消事件订阅
            self._unsubscribe_generation_events()
            logger.info("Application closed by user")
            self.root.destroy()
    
    def run(self) -> None:
        """运行主窗口"""
        logger.info("Starting main window")
        
        # 关键：在mainloop之前强制更新窗口，确保窗口句柄可用
        # 这样overrideredirect才能正确移除系统标题栏
        self.root.update()
        
        # 窗口显示后重新应用无边框效果
        try:
            glass_mgr = GlassWindowManager(self.root)
            # 直接设置overrideredirect，无需Windows API
            self.root.overrideredirect(True)
            logger.info("Frameless window applied after update")
        except Exception as e:
            logger.warning(f"Failed to apply frameless: {e}")
        
        self.root.mainloop()


# ============== 入口 ==============

def _global_exception_handler(exc_type, exc_value, exc_tb):
    """
    P1-12修复：全局异常处理器

    捕获未处理的异常，记录日志并显示友好的错误提示。
    """
    # 记录完整的异常信息
    logger.critical(
        "未捕获的异常",
        exc_info=(exc_type, exc_value, exc_tb)
    )

    # 显示友好的错误提示
    try:
        messagebox.showerror(
            "程序错误",
            f"发生未预期的错误：{exc_type.__name__}\n"
            f"详情：{str(exc_value)[:200]}\n\n"
            "请查看日志文件获取更多信息。"
        )
    except Exception:
        # 如果messagebox也失败了，打印到控制台
        print(f"CRITICAL ERROR: {exc_type.__name__}: {exc_value}")


def main():
    """主入口"""
    # P1-12修复：注册全局异常处理器
    import sys
    sys.excepthook = _global_exception_handler

    # 初始化核心服务（配置和日志）
    if CORE_AVAILABLE:
        try:
            init_results = initialize_core_services()
            if init_results.get("ConfigService") and init_results.get("LoggingService"):
                # 获取日志服务
                logging_service = get_logging_service()
                logging_service.log_system_event(
                    "startup", "应用程序启动 - 核心服务初始化完成"
                )
                logger.info("Core services initialized successfully")
            else:
                logger.warning(f"Core services initialization partial: {init_results}")
        except Exception as e:
            logger.error(f"Failed to initialize core services: {e}")

    try:
        app = MainWindow()
        app.run()
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise
    finally:
        # 释放核心服务
        if CORE_AVAILABLE:
            try:
                dispose_core_services()
                logger.info("Core services disposed")
            except Exception as e:
                logger.error(f"Failed to dispose core services: {e}")


if __name__ == "__main__":
    main()
