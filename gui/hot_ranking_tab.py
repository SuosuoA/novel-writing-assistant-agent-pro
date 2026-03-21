#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
热榜功能标签页实现
包含数据加载、展示、刷新等功能
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, List, Optional
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)


class HotRankingTab(ttk.Frame):
    """热榜功能标签页"""
    
    def __init__(self, parent, theme, event_bus=None):
        super().__init__(parent, style="TFrame")
        
        self.theme = theme
        self.event_bus = event_bus
        self.data_manager = None
        self.is_loading = False
        self.current_platform = None
        
        # 导入工具类
        from gui.utils import ContextMenu, ScrollableFrame, AutoSaveMixin
        
        self._create_ui()
        self._init_data_manager()
        self._setup_context_menus()
        self._setup_autosave()
    
    def _create_ui(self):
        """创建UI界面"""
        # 顶部工具栏
        toolbar = ttk.Frame(self, style="TFrame")
        toolbar.pack(fill=tk.X, padx=10, pady=5)
        
        # 平台选择
        ttk.Label(toolbar, text="平台:").pack(side=tk.LEFT, padx=5)
        self.platform_combo = ttk.Combobox(
            toolbar,
            values=["起点中文网", "晋江文学城", "红番茄小说", "起点中文网-男频", "起点中文网-女频"],
            width=20,
            state="readonly"
            style="TCombobox"
        )
        self.platform_combo.pack(side=tk.LEFT, padx=5)
        self.platform_combo.set("起点中文网")
        self.platform_combo.bind('<<ComboboxSelected>>', self._on_platform_changed)
        
        # 刷新按钮
        self.refresh_btn = ttk.Button(
            toolbar,
            text="🔄 刷新",
            command=self._refresh_data,
            style="Accent.TButton"
        )
        self.refresh_btn.pack(side=tk.RIGHT, padx=5)
        
        # 状态标签
        self.status_label = ttk.Label(
            toolbar,
            text="状态: 就绪",
            style="TLabel"
        )
        self.status_label.pack(side=tk.RIGHT, padx=10)
        
        # 标签页容器
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 创建4个榜单标签页
        self._create_ranking_tab("追更榜", "follow")
        self._create_ranking_tab("推荐榜", "recommend")
        self._create_ranking_tab("新书榜", "newbook")
        self._create_ranking_tab("完结榜", "finish")
    
    def _create_ranking_tab(self, tab_name: str, tab_id: str):
        """创建单个榜单标签页"""
        frame = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(frame, text=f"📊 {tab_name}")
        
        # 创建表格
        columns = ("rank", "title", "author", "category", "heat", "source")
        tree = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
            style="Treeview"
        )
        
        # 设置列宽
        tree.column("rank", width=60, anchor="center")
        tree.column("title", width=250, anchor="w")
        tree.column("author", width=120, anchor="w")
        tree.column("category", width=100, anchor="w")
        tree.column("heat", width=100, anchor="e")
        tree.column("source", width=100, anchor="w")
        
        # 滚动条
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # 布局
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 保存引用
        setattr(self, f"{tab_id}_tree", tree)
    
    def _init_data_manager(self):
        """初始化数据管理器"""
        try:
            from scripts.hot_ranking.data_manager import HotRankingDataManager
            self.data_manager = HotRankingDataManager()
            logger.info("热榜数据管理器初始化成功")
        except Exception as e:
            logger.error(f"初始化数据管理器失败: {e}")
            messagebox.showwarning("警告", f"数据管理器初始化失败: {str(e)}")
    
    def _on_platform_changed(self, event):
        """平台切换事件"""
        platform = self.platform_combo.get()
        self.current_platform = platform
        self._refresh_data()
    
    def _refresh_data(self):
        """刷新数据"""
        if self.is_loading:
            return
        
        self.is_loading = True
        self.refresh_btn.config(state="disabled")
        self.status_label.config(text="状态: 加载中...")
        
        # 在后台线程中加载数据
        def load_in_background():
            try:
                data = self._fetch_ranking_data()
                # 在主线程中更新UI
                self.after(0, lambda: self._update_ui_with_data(data))
            except Exception as e:
                logger.error(f"加载数据失败: {e}")
                self.after(0, lambda: self._handle_load_error(str(e)))
        
        thread = threading.Thread(target=load_in_background, daemon=True)
        thread.start()
    
    def _fetch_ranking_data(self) -> Dict:
        """获取热榜数据"""
        if not self.data_manager:
            return {}
        
        platform = self.current_platform or "起点中文网"
        
        # 尝试从缓存加载
        cached_data = self.data_manager.load_latest_data()
        if cached_data:
            logger.info("从缓存加载热榜数据")
            return cached_data
        
        # 如果缓存无效，尝试获取新数据
        logger.info("缓存无效，尝试获取新数据")
        
        # 这里可以调用爬虫或其他方式获取数据
        # 为了演示，使用默认数据
        default_data = self.data_manager.get_default_data()
        return default_data
    
    def _update_ui_with_data(self, data: Dict):
        """用数据更新UI"""
        self.is_loading = False
        self.refresh_btn.config(state="normal")
        self.status_label.config(text="状态: 数据已更新")
        
        platform = self.current_platform or "起点中文网"
        
        # 更新各个榜单标签页
        ranking_types = {
            "起点中文网": ["follow", "recommend", "newbook", "finish"],
            "晋江文学城": ["recommend", "newbook", "finish"],
            "红番茄小说": ["follow", "recommend", "newbook", "finish"],
        }
        
        tabs = ranking_types.get(platform, [])
        
        for i, tab_id in enumerate(tabs):
            tree = getattr(self, f"{tab_id}_tree", None)
            if tree:
                self._populate_tree(tree, data, tab_id)
        
        # 保存数据到缓存
        if self.data_manager:
            self.data_manager.save_ranking_data(data)
    
    def _populate_tree(self, tree: ttk.Treeview, data: Dict, ranking_type: str):
        """填充树形视图数据"""
        # 清空现有数据
        for item in tree.get_children():
            tree.delete(item)
        
        # 获取对应榜单的数据
        platform_data = data.get(self.current_platform or "起点中文网", [])
        
        # 根据榜单类型过滤数据
        type_mapping = {
            "follow": "追更榜",
            "recommend": "推荐榜",
            "newbook": "新书榜",
            "finish": "完结榜"
        }
        
        if isinstance(platform_data, list):
            # 挍热度排序
            sorted_data = sorted(platform_data, key=lambda x: x.get('heat', 0), reverse=True)
            
            # 巻加数据
            for item in sorted_data:
                rank = item.get('rank', 1)
                title = item.get('title', '未知"
                author = item.get('author', '未知'
                category = item.get('category', '未知'
                heat = item.get('heat', 0)
                source = item.get('source', '未知'
                
                tree.insert("", "end", values=(
                    str(rank),
                    title,
                    author,
                    category,
                    str(heat),
                    source
                )
        elif isinstance(platform_data, dict):
            # 字典格式数据
            ranking_data = platform_data.get(ranking_type, [])
            if ranking_data and isinstance(ranking_data, list):
                for item in ranking_data:
                    rank = item.get('rank', 1)
                    title = item.get('title', '未知'
                    author = item.get('author', '未知')
                    category = item.get('category', '未知'
                    heat = item.get('heat', 0)
                    source = item.get('source', '未知'
                    
                    tree.insert("", "end", values=(
                        str(rank),
                        title,
                        author,
                        category,
                        str(heat),
                        source
                    )
    
    def _handle_load_error(self, error: str):
        """处理加载错误"""
        self.is_loading = False
        self.refresh_btn.config(state="normal")
        self.status_label.config(text=f"状态: 错误 - {str(error)}")
        messagebox.showerror("错误", f"加载数据失败: {str(error)}")
    
    def load_initial_data(self):
        """加载初始数据"""
        self.current_platform = self.platform_combo.get()
        self._refresh_data()
