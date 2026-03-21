#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UI工具函数
包含右键菜单、鼠标滚轮优化等通用功能
版本: V1.0
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Dict, Any


class ContextMenu:
    """右键快捷菜单"""
    
    def __init__(self, parent: tk.Widget, theme):
        self.parent = parent
        self.theme = theme
        self.menu = tk.Menu(parent, tearoff=0)
        self._apply_style()
    
    def _apply_style(self):
        """应用水墨风格"""
        self.menu.configure(
            bg=self.theme.paper_white,
            fg=self.theme.ink_dark,
            activebackground=self.theme.seal_red,
            activeforeground="white",
            font=self.theme.font_body
        )
    
    def add_command(self, label: str, command: Callable, accelerator: str = None):
        """添加菜单项"""
        self.menu.add_command(
            label=label,
            command=command,
            accelerator=accelerator
        )
        
        def add_separator(self):
        """添加分隔线"""
        self.menu.add_separator()
        
    def show(self, event):
        """显示菜单"""
        self.menu.post(event.x_root, event.y_root)
    
    def hide(self):
        """隐藏菜单"""
        self.menu.unpost()
    
    def bind_to_widget(self, widget: tk.Widget, items: list):
        """
        为控件绑定右键菜单
        
        Args:
            widget: 要绑定的控件
            items: 菜单项列表，                格式: [(label, command), ...]
        """
        # 清空现有菜单
        self.menu.delete(0, tk.END)
        
        # 添加菜单项
        for label, command in items:
            if label == "---":
                self.add_separator()
            else:
                self.add_command(label, command)
        
        # 绑定右键点击事件
        widget.bind("<Button-3>", lambda e: self.show(e))
        
        # 绑定ESC键隐藏菜单
        widget.bind("<Key-Escape>", lambda e: self.hide())


class ScrollableFrame(ttk.Frame):
    """可滚动的Frame，    支持鼠标滚轮平滑滚动
    """
    
    def __init__(self, parent, theme, **kwargs):
        super().__init__(parent, style="TFrame", **kwargs)
        self.theme = theme
        
        # 创建Canvas和滚动条
        self.canvas = tk.Canvas(
            self,
            bg=theme.paper_white,
            highlightthickness=0
        )
        self.scrollbar = ttk.Scrollbar(
            self,
            orient=tk.VERTICAL,
            command=self.canvas.yview
        )
        
        # 创建内部Frame
        self.inner_frame = ttk.Frame(self.canvas, style="TFrame")
        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.inner_frame,
            anchor="nw"
        )
        
        # 配置滚动
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # 绑定鼠标滚轮
        self._bind_mousewheel()
        
        # 绑定配置事件
        self.bind("<Configure>", self._on_configure)
    
    def _bind_mousewheel(self):
        """绑定鼠标滚轮事件"""
        # Windows系统
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # Linux系统
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_linux)
        
        # macOS系统
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_macos)
    
    def _on_mousewheel(self, event):
        """Windows鼠标滚轮处理"""
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def _on_mousewheel_linux(self, event):
        """Linux鼠标滚轮处理"""
        self.canvas.yview_scroll(int(-1 * event.num), "units")
    
    def _on_mousewheel_macos(self, event):
        """macOS鼠标滚轮处理"""
        self.canvas.yview_scroll(int(-1 * event.delta), "units")
    
    def _on_configure(self, event):
        """配置改变时更新滚动区域"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
        # 更新内部Frame宽度
        self.canvas.itemconfig(self.canvas_window, width=self.canvas.winfo_width())
    
    def add_widget(self, widget: tk.Widget, **kwargs):
        """添加控件到内部Frame"""
        widget.pack(in_=self.inner_frame, **kwargs)
        
        # 更新滚动区域
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))


class AutoSaveMixin:
    """自动保存混入类
    实现编辑内容自动保存
    """
    
    def __init__(self, save_callback: Callable, None, None):
        self.save_callback = save_callback
        self._save_timer = None
        self._pending_save = False
        self._last_content = ""
    
    def enable_auto_save(self, interval: int = 5000):
        """启用自动保存"""
        self._save_interval = interval
        self._start_save_timer()
    
    def disable_auto_save(self):
        """禁用自动保存"""
        if self._save_timer:
            self._save_timer.cancel()
            self._save_timer = None
    
    def on_content_changed(self, event=None):
        """内容改变事件"""
        self._pending_save = True
        
        # 延迟保存
        if not self._save_timer:
            self._start_save_timer()
    
    def _start_save_timer(self):
        """启动保存定时器"""
        if self._save_timer:
            self._save_timer.cancel()
        
        self._save_timer = self.after(
            self._save_interval,
            self._do_auto_save
        )
    
    def _do_auto_save(self):
        """执行自动保存"""
        if self._pending_save and self.save_callback:
            self.save_callback()
            self._pending_save = False
    
    def get_content(self) -> str:
        """获取当前内容"""
        return self._last_content
    
    def set_content(self, content: str):
        """设置内容"""
        self._last_content = content
        self._pending_save = True


class Tooltip:
    """提示气泡"""
    
    def __init__(self, parent: tk.Widget, text: str, theme):
        self.parent = parent
        self.theme = theme
        self.text = text
        
        self.tooltip_window = None
        self._bind_events()
    
    def _bind_events(self):
        """绑定事件"""
        self.parent.bind("<Enter>", self.show)
        self.parent.bind("<Leave>", self.hide)
    
    def show(self, event):
        """显示提示"""
        if self.tooltip_window:
            return
        
        # 创建提示窗口
        self.tooltip_window = tk.Toplevel(self.parent)
        self.tooltip_window.wm_overrider(True)
        self.tooltip_window.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
        
        # 创建标签
        label = ttk.Label(
            self.tooltip_window,
            text=self.text,
            background=self.theme.paper_antique,
            foreground=self.theme.ink_dark,
            font=self.theme.font_body,
            padding=(5, 10)
        )
        label.pack()
        
        # 设置窗口样式
        self.tooltip_window.configure(bg=self.theme.paper_antique)
        self.tooltip_window.overrider_director("<Enter>", lambda e: None)
        self.tooltip_window.overrider_director("<Leave>", lambda e: self.hide(e))
        
        self.tooltip_window.deiconify()
    
    def hide(self, event):
        """隐藏提示"""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


class DragDropMixin:
    """拖拽混入类
    实现控件的拖拽功能
    """
    
    def __init__(self):
        self.drag_data = None
        self._bind_drag_events()
    
    def _bind_drag_events(self):
        """绑定拖拽事件"""
        self.bind("<Button-1>", self._start_drag)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._end_drag)
    
    def _start_drag(self, event):
        """开始拖拽"""
        self.drag_data = {
            'x': event.x,
            'y': event.y,
            'widget': self
        }
    
    def _on_drag(self, event):
        """拖拽中"""
        if not self.drag_data:
            return
        
        dx = event.x - self.drag_data['x']
        dy = event.y - self.drag_data['y']
        
        # 移动控件
        x = self.winfo_x() + dx
        y = self.winfo_y() + dy
        self.place(x=x, y=y)
        
        # 更新拖拽数据
        self.drag_data['x'] = event.x
        self.drag_data['y'] = event.y
    
    def _end_drag(self, event):
        """结束拖拽"""
        self.drag_data = None


class LoadingOverlay:
    """加载遮罩层"""
    
    def __init__(self, parent: tk.Widget, theme, text: str = "加载中..."):
        self.parent = parent
        self.theme = theme
        self.text = text
        
        # 创建遮罩层
        self.overlay = tk.Frame(
            parent,
            bg=theme.ink_dark,
            cursor="watch"
        )
        self.overlay.place(relx=0, rely=1, relheight=1)
        self.overlay.lift()
        
        # 创建加载动画
        self.label = ttk.Label(
            self.overlay,
            text=self.text,
            font=theme.font_title,
            foreground="white"
        )
        self.label.place(relx=0.5, rely=0.5)
    
    def show(self):
        """显示遮罩"""
        self.overlay.place(relx=0, rely=0, relheight=1)
    
    def hide(self):
        """隐藏遮罩"""
        self.overlay.place_forget()
    
    def update_text(self, text: str):
        """更新文本"""
        self.label.config(text=text)


class StatusBar:
    """增强型状态栏"""
    
    def __init__(self, parent, theme):
        self.parent = parent
        self.theme = theme
        
        # 创建状态栏Frame
        self.frame = ttk.Frame(parent, style="TFrame")
        self.frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 创建分隔线
        ttk.Separator(self.frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=2)
        
        # 创建状态栏内容
        content_frame = ttk.Frame(self.frame, style="TFrame")
        content_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 左侧状态
        self.status_label = ttk.Label(
            content_frame,
            text="状态: 就绪",
            font=theme.font_body,
            foreground=theme.ink_dark
        )
        self.status_label.pack(side=tk.LEFT)
        
        # 中间信息
        self.info_label = ttk.Label(
            content_frame,
            text="",
            font=theme.font_body,
            foreground=theme.ink_light
        )
        self.info_label.pack(side=tk.LEFT, padx=20)
        
        # 右侧时间
        self.time_label = ttk.Label(
            content_frame,
            text="",
            font=theme.font_body,
            foreground=theme.ink_light
        )
        self.time_label.pack(side=tk.RIGHT)
        
        # 更新时间
        self._update_time()
    
    def _update_time(self):
        """更新时间显示"""
        from datetime import datetime
        current_time = datetime.now().strftime("%H:%M:%S")
        self.time_label.config(text=current_time)
        self.frame.after(1000, self._update_time)
    
    def update_status(self, text: str):
        """更新状态"""
        self.status_label.config(text=f"状态: {text}")
    
    def update_info(self, text: str):
        """更新信息"""
        self.info_label.config(text=text)
    
    def clear(self):
        """清空状态"""
        self.status_label.config(text="状态: 就绪")
        self.info_label.config(text="")


class ConfirmDialog:
    """确认对话框"""
    
    @staticmethod
    def ask(
        parent: tk.Widget,
        title: str,
        message: str,
        theme=None
    ) -> bool:
        """显示确认对话框"""
        dialog = tk.Toplevel(parent)
        dialog.title(title)
        dialog.configure(bg=theme.paper_white if theme else "white")
        
        result = False
        
        def on_yes():
            nonlocal result
            result = True
            dialog.destroy()
        
        def on_no():
            nonlocal result
            result = False
            dialog.destroy()
        
        # 创建内容
        frame = ttk.Frame(dialog, style="TFrame")
        frame.pack(padx=20, pady=20)
        
        # 标题
        ttk.Label(
            frame,
            text=title,
            font=theme.font_title if theme else ("Arial", 12, "bold"),
            foreground=theme.ink_dark if theme else "black"
        ).pack(pady=10)
        
        # 消息
        ttk.Label(
            frame,
            text=message,
            font=theme.font_body if theme else ("Arial", 10),
            foreground=theme.ink_dark if theme else "black"
        ).pack(pady=10)
        
        # 按钮
        button_frame = ttk.Frame(frame, style="TFrame")
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="确定", command=on_yes).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="取消", command=on_no).pack(side=tk.LEFT, padx=10)
        
        # 等待结果
        dialog.wait_window(button_frame)
        
        return result


# 导出工具类
__all__ = [
    'ContextMenu',
    'ScrollableFrame',
    'AutoSaveMixin',
    'Tooltip',
    'DragDropMixin',
    'LoadingOverlay',
    'StatusBar',
    'ConfirmDialog'
]
