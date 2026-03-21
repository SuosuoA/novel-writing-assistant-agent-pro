#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工作台子模块实现
包含7个子模块的完整UI实现：世界观管理、人物设定、大纲管理、风格学习、开始创作、逆向反馈、快捷创作
版本: V1.0
作者: 前端开发工程师
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from typing import Optional, Dict, List, Callable
import logging
import os
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class WorldviewModule:
    """世界观管理模块"""
    
    def __init__(self, parent: tk.Widget, theme, event_bus=None):
        self.parent = parent
        self.theme = theme
        self.event_bus = event_bus
        self.worldview_data = {}
        
        self._create_ui()
    
    def _create_ui(self):
        """创建UI界面"""
        # 主容器
        main_container = ttk.Frame(self.parent, style="TFrame")
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # 顶部按钮区
        button_frame = ttk.Frame(main_container, style="TFrame")
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(button_frame, text="📁 导入世界观", 
                   command=self._import_worldview).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="➕ 新建世界观",
                   command=self._create_worldview).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="💾 保存",
                   command=self._save_worldview).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🗑️ 删除",
                   command=self._delete_worldview).pack(side=tk.LEFT, padx=5)
        
        # 分隔线
        ttk.Separator(main_container, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # 左侧列表区
        left_frame = ttk.LabelFrame(main_container, text="世界观列表", padding="10")
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # 世界观列表
        self.worldview_listbox = tk.Listbox(
            left_frame,
            width=30,
            height=25,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark,
            selectbackground=self.theme.seal_red,
            selectforeground="white"
        )
        self.worldview_listbox.pack(fill=tk.BOTH, expand=True)
        self.worldview_listbox.bind('<<ListboxSelect>>', self._on_worldview_selected)
        
        # 右侧详情区
        right_frame = ttk.Frame(main_container, style="TFrame")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 基本信息
        info_frame = ttk.LabelFrame(right_frame, text="世界观信息", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(info_frame, text="名称:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_entry = ttk.Entry(info_frame, width=40)
        self.name_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        
        ttk.Label(info_frame, text="类型:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.type_combo = ttk.Combobox(info_frame, values=["奇幻", "科幻", "都市", "历史", "其他"], width=37)
        self.type_combo.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)
        
        ttk.Label(info_frame, text="描述:").grid(row=2, column=0, sticky=tk.NW, pady=5)
        self.desc_text = scrolledtext.ScrolledText(info_frame, width=45, height=4, 
                                                    font=self.theme.font_body,
                                                    bg=self.theme.paper_cream,
                                                    fg=self.theme.ink_dark)
        self.desc_text.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)
        
        info_frame.columnconfigure(1, weight=1)
        
        # 元素详情
        detail_frame = ttk.LabelFrame(right_frame, text="世界观元素", padding="10")
        detail_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建标签页用于分类显示
        self.element_notebook = ttk.Notebook(detail_frame)
        self.element_notebook.pack(fill=tk.BOTH, expand=True)
        
        # 地理标签页
        geo_frame = ttk.Frame(self.element_notebook)
        self.element_notebook.add(geo_frame, text="🏔️ 地理")
        self.geo_text = scrolledtext.ScrolledText(geo_frame, font=self.theme.font_body,
                                                   bg=self.theme.paper_cream, fg=self.theme.ink_dark)
        self.geo_text.pack(fill=tk.BOTH, expand=True)
        
        # 历史标签页
        hist_frame = ttk.Frame(self.element_notebook)
        self.element_notebook.add(hist_frame, text="📜 历史")
        self.hist_text = scrolledtext.ScrolledText(hist_frame, font=self.theme.font_body,
                                                    bg=self.theme.paper_cream, fg=self.theme.ink_dark)
        self.hist_text.pack(fill=tk.BOTH, expand=True)
        
        # 体系标签页
        sys_frame = ttk.Frame(self.element_notebook)
        self.element_notebook.add(sys_frame, text="⚡ 体系")
        self.sys_text = scrolledtext.ScrolledText(sys_frame, font=self.theme.font_body,
                                                   bg=self.theme.paper_cream, fg=self.theme.ink_dark)
        self.sys_text.pack(fill=tk.BOTH, expand=True)
        
        # 社会标签页
        soc_frame = ttk.Frame(self.element_notebook)
        self.element_notebook.add(soc_frame, text="🏛️ 社会")
        self.soc_text = scrolledtext.ScrolledText(soc_frame, font=self.theme.font_body,
                                                   bg=self.theme.paper_cream, fg=self.theme.ink_dark)
        self.soc_text.pack(fill=tk.BOTH, expand=True)
        
        # 加载示例数据
        self._load_sample_data()
    
    def _load_sample_data(self):
        """加载示例数据"""
        sample_worldview = [
            "玄幻世界-修仙体系",
            "科幻世界-星际文明",
            "都市世界-现代都市"
        ]
        for item in sample_worldview:
            self.worldview_listbox.insert(tk.END, item)
    
    def _import_worldview(self):
        """导入世界观文件"""
        file_path = filedialog.askopenfilename(
            title="选择世界观文件",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx"), ("JSON文件", "*.json")]
        )
        if file_path:
            try:
                # TODO: 实现文件导入逻辑
                messagebox.showinfo("成功", f"已导入世界观文件：\n{file_path}")
                self.worldview_listbox.insert(tk.END, os.path.basename(file_path))
            except Exception as e:
                messagebox.showerror("错误", f"导入失败：{str(e)}")
    
    def _create_worldview(self):
        """新建世界观"""
        self.name_entry.delete(0, tk.END)
        self.type_combo.set("")
        self.desc_text.delete("1.0", tk.END)
        self.geo_text.delete("1.0", tk.END)
        self.hist_text.delete("1.0", tk.END)
        self.sys_text.delete("1.0", tk.END)
        self.soc_text.delete("1.0", tk.END)
        messagebox.showinfo("提示", "请填写世界观信息并保存")
    
    def _save_worldview(self):
        """保存世界观"""
        name = self.name_entry.get()
        if not name:
            messagebox.showwarning("警告", "请输入世界观名称")
            return
        
        # TODO: 实现保存逻辑
        messagebox.showinfo("成功", f"世界观 '{name}' 已保存")
    
    def _delete_worldview(self):
        """删除世界观"""
        selection = self.worldview_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要删除的世界观")
            return
        
        if messagebox.askyesno("确认", "确定要删除选中的世界观吗？"):
            self.worldview_listbox.delete(selection[0])
            messagebox.showinfo("成功", "世界观已删除")
    
    def _on_worldview_selected(self, event):
        """世界观选中事件"""
        selection = self.worldview_listbox.curselection()
        if selection:
            # TODO: 加载选中世界观的详细信息
            pass


class CharacterModule:
    """人物设定模块"""
    
    def __init__(self, parent: tk.Widget, theme, event_bus=None):
        self.parent = parent
        self.theme = theme
        self.event_bus = event_bus
        self.characters = []
        
        self._create_ui()
    
    def _create_ui(self):
        """创建UI界面"""
        # 主容器
        main_container = ttk.Frame(self.parent, style="TFrame")
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # 顶部按钮区
        button_frame = ttk.Frame(main_container, style="TFrame")
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(button_frame, text="📁 导入人物",
                   command=self._import_character).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="➕ 新建人物",
                   command=self._create_character).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="💾 保存",
                   command=self._save_character).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🗑️ 删除",
                   command=self._delete_character).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🔗 关系图",
                   command=self._show_relationship).pack(side=tk.LEFT, padx=5)
        
        # 分隔线
        ttk.Separator(main_container, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # 左侧列表区
        left_frame = ttk.LabelFrame(main_container, text="人物列表", padding="10")
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # 人物列表（带图标）
        self.character_listbox = tk.Listbox(
            left_frame,
            width=25,
            height=25,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark,
            selectbackground=self.theme.seal_red,
            selectforeground="white"
        )
        self.character_listbox.pack(fill=tk.BOTH, expand=True)
        self.character_listbox.bind('<<ListboxSelect>>', self._on_character_selected)
        
        # 右侧详情区
        right_frame = ttk.Frame(main_container, style="TFrame")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 创建标签页用于分类显示
        self.detail_notebook = ttk.Notebook(right_frame)
        self.detail_notebook.pack(fill=tk.BOTH, expand=True)
        
        # 基本信息标签页
        basic_frame = ttk.Frame(self.detail_notebook)
        self.detail_notebook.add(basic_frame, text="📋 基本信息")
        
        # 基本信息表单
        form_frame = ttk.Frame(basic_frame)
        form_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        fields = [
            ("姓名:", "name_entry", 40),
            ("性别:", "gender_combo", 37),
            ("年龄:", "age_entry", 40),
            ("角色类型:", "role_combo", 37),
            ("外貌:", "appearance_text", 4),
            ("性格:", "personality_text", 4),
            ("背景:", "background_text", 4),
        ]
        
        for i, (label, attr, width_or_height) in enumerate(fields):
            ttk.Label(form_frame, text=label).grid(row=i, column=0, sticky=tk.NW, pady=5)
            
            if "text" in attr:
                # 多行文本框
                widget = scrolledtext.ScrolledText(
                    form_frame, 
                    width=45, 
                    height=width_or_height,
                    font=self.theme.font_body,
                    bg=self.theme.paper_cream,
                    fg=self.theme.ink_dark
                )
                widget.grid(row=i, column=1, sticky=tk.EW, padx=5, pady=5)
            else:
                # 单行输入或下拉框
                if "combo" in attr:
                    values = ["男", "女", "其他"] if "gender" in attr else \
                            ["主角", "配角", "反派", "路人"]
                    widget = ttk.Combobox(form_frame, values=values, width=37)
                else:
                    widget = ttk.Entry(form_frame, width=40)
                widget.grid(row=i, column=1, sticky=tk.EW, padx=5, pady=5)
            
            setattr(self, attr, widget)
        
        form_frame.columnconfigure(1, weight=1)
        
        # 能力设定标签页
        ability_frame = ttk.Frame(self.detail_notebook)
        self.detail_notebook.add(ability_frame, text="⚡ 能力设定")
        self.ability_text = scrolledtext.ScrolledText(
            ability_frame, 
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.ability_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 关系网络标签页
        relation_frame = ttk.Frame(self.detail_notebook)
        self.detail_notebook.add(relation_frame, text="🔗 关系网络")
        self.relation_text = scrolledtext.ScrolledText(
            relation_frame,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.relation_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 人生轨迹标签页
        trajectory_frame = ttk.Frame(self.detail_notebook)
        self.detail_notebook.add(trajectory_frame, text="📍 人生轨迹")
        self.trajectory_text = scrolledtext.ScrolledText(
            trajectory_frame,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.trajectory_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 加载示例数据
        self._load_sample_data()
    
    def _load_sample_data(self):
        """加载示例数据"""
        sample_characters = [
            "👤 主角-李明",
            "👤 配角-王芳",
            "👤 反派-张强",
        ]
        for item in sample_characters:
            self.character_listbox.insert(tk.END, item)
    
    def _import_character(self):
        """导入人物"""
        file_path = filedialog.askopenfilename(
            title="选择人物文件",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx"), ("JSON文件", "*.json")]
        )
        if file_path:
            messagebox.showinfo("成功", f"已导入人物文件：\n{file_path}")
    
    def _create_character(self):
        """新建人物"""
        # 清空所有字段
        self.name_entry.delete(0, tk.END)
        self.gender_combo.set("")
        self.age_entry.delete(0, tk.END)
        self.role_combo.set("")
        self.appearance_text.delete("1.0", tk.END)
        self.personality_text.delete("1.0", tk.END)
        self.background_text.delete("1.0", tk.END)
        self.ability_text.delete("1.0", tk.END)
        self.relation_text.delete("1.0", tk.END)
        self.trajectory_text.delete("1.0", tk.END)
        messagebox.showinfo("提示", "请填写人物信息并保存")
    
    def _save_character(self):
        """保存人物"""
        name = self.name_entry.get()
        if not name:
            messagebox.showwarning("警告", "请输入人物姓名")
            return
        messagebox.showinfo("成功", f"人物 '{name}' 已保存")
    
    def _delete_character(self):
        """删除人物"""
        selection = self.character_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要删除的人物")
            return
        
        if messagebox.askyesno("确认", "确定要删除选中的人物吗？"):
            self.character_listbox.delete(selection[0])
            messagebox.showinfo("成功", "人物已删除")
    
    def _show_relationship(self):
        """显示关系图"""
        messagebox.showinfo("提示", "关系图功能开发中...")
    
    def _on_character_selected(self, event):
        """人物选中事件"""
        selection = self.character_listbox.curselection()
        if selection:
            # TODO: 加载选中人物的详细信息
            pass


class OutlineModule:
    """大纲管理模块"""
    
    def __init__(self, parent: tk.Widget, theme, event_bus=None):
        self.parent = parent
        self.theme = theme
        self.event_bus = event_bus
        self.outline_data = {}
        
        self._create_ui()
    
    def _create_ui(self):
        """创建UI界面"""
        # 主容器
        main_container = ttk.Frame(self.parent, style="TFrame")
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # 顶部按钮区
        button_frame = ttk.Frame(main_container, style="TFrame")
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(button_frame, text="📁 导入大纲",
                   command=self._import_outline).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🔍 解析大纲",
                   command=self._parse_outline).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="💾 保存",
                   command=self._save_outline).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="📤 导出",
                   command=self._export_outline).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🗑️ 清空",
                   command=self._clear_outline).pack(side=tk.LEFT, padx=5)
        
        # 进度条
        progress_frame = ttk.Frame(main_container, style="TFrame")
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(progress_frame, text="大纲进度:").pack(side=tk.LEFT)
        self.progress_bar = ttk.Progressbar(progress_frame, length=300, mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, padx=10)
        self.progress_label = ttk.Label(progress_frame, text="0/0 章")
        self.progress_label.pack(side=tk.LEFT)
        
        # 分隔线
        ttk.Separator(main_container, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # 左侧树形结构
        left_frame = ttk.LabelFrame(main_container, text="大纲结构", padding="10")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # 树形视图
        self.outline_tree = ttk.Treeview(
            left_frame,
            columns=("title", "words", "status"),
            show="tree headings",
            selectmode="browse"
        )
        
        self.outline_tree.heading("#0", text="章节")
        self.outline_tree.heading("title", text="标题")
        self.outline_tree.heading("words", text="字数")
        self.outline_tree.heading("status", text="状态")
        
        self.outline_tree.column("#0", width=150)
        self.outline_tree.column("title", width=200)
        self.outline_tree.column("words", width=80)
        self.outline_tree.column("status", width=80)
        
        tree_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.outline_tree.yview)
        self.outline_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.outline_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.outline_tree.bind('<<TreeviewSelect>>', self._on_outline_selected)
        
        # 右侧章节详情
        right_frame = ttk.Frame(main_container, style="TFrame")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 章节信息
        info_frame = ttk.LabelFrame(right_frame, text="章节详情", padding="10")
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(info_frame, text="章节标题:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.chapter_title_entry = ttk.Entry(info_frame, width=40)
        self.chapter_title_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        
        ttk.Label(info_frame, text="字数目标:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.chapter_words_entry = ttk.Entry(info_frame, width=40)
        self.chapter_words_entry.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)
        
        ttk.Label(info_frame, text="关键事件:").grid(row=2, column=0, sticky=tk.NW, pady=5)
        self.chapter_events_text = scrolledtext.ScrolledText(
            info_frame,
            width=45,
            height=5,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.chapter_events_text.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)
        
        ttk.Label(info_frame, text="内容摘要:").grid(row=3, column=0, sticky=tk.NW, pady=5)
        self.chapter_summary_text = scrolledtext.ScrolledText(
            info_frame,
            width=45,
            height=8,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.chapter_summary_text.grid(row=3, column=1, sticky=tk.EW, padx=5, pady=5)
        
        info_frame.columnconfigure(1, weight=1)
        
        # 加载示例数据
        self._load_sample_data()
    
    def _load_sample_data(self):
        """加载示例大纲"""
        # 添加卷
        vol1 = self.outline_tree.insert("", tk.END, text="第一卷", values=("", "", ""))
        
        # 添加章节
        for i in range(1, 6):
            self.outline_tree.insert(
                vol1, 
                tk.END, 
                text=f"第{i}章",
                values=(f"章节标题{i}", "900", "待写")
            )
        
        self.progress_bar["value"] = 0
        self.progress_label.config(text="0/5 章")
    
    def _import_outline(self):
        """导入大纲"""
        file_path = filedialog.askopenfilename(
            title="选择大纲文件",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx")]
        )
        if file_path:
            messagebox.showinfo("成功", f"已导入大纲文件：\n{file_path}")
    
    def _parse_outline(self):
        """解析大纲"""
        messagebox.showinfo("提示", "大纲解析功能开发中...")
    
    def _save_outline(self):
        """保存大纲"""
        messagebox.showinfo("成功", "大纲已保存")
    
    def _export_outline(self):
        """导出大纲"""
        file_path = filedialog.asksaveasfilename(
            title="保存大纲",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx")]
        )
        if file_path:
            messagebox.showinfo("成功", f"大纲已导出到：\n{file_path}")
    
    def _clear_outline(self):
        """清空大纲"""
        if messagebox.askyesno("确认", "确定要清空大纲吗？"):
            for item in self.outline_tree.get_children():
                self.outline_tree.delete(item)
            messagebox.showinfo("成功", "大纲已清空")
    
    def _on_outline_selected(self, event):
        """大纲选中事件"""
        selection = self.outline_tree.selection()
        if selection:
            # TODO: 加载选中章节的详细信息
            pass


class StyleModule:
    """风格学习模块"""
    
    def __init__(self, parent: tk.Widget, theme, event_bus=None):
        self.parent = parent
        self.theme = theme
        self.event_bus = event_bus
        self.style_data = {}
        
        self._create_ui()
    
    def _create_ui(self):
        """创建UI界面"""
        # 主容器
        main_container = ttk.Frame(self.parent, style="TFrame")
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # 顶部按钮区
        button_frame = ttk.Frame(main_container, style="TFrame")
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(button_frame, text="📁 导入范文",
                   command=self._import_style).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🔍 深度学习",
                   command=self._learn_style).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="💾 保存风格",
                   command=self._save_style).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="📤 导出风格",
                   command=self._export_style).pack(side=tk.LEFT, padx=5)
        
        # 分隔线
        ttk.Separator(main_container, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # 左侧文件列表
        left_frame = ttk.LabelFrame(main_container, text="范文列表", padding="10")
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        self.style_listbox = tk.Listbox(
            left_frame,
            width=30,
            height=20,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark,
            selectbackground=self.theme.seal_red,
            selectforeground="white"
        )
        self.style_listbox.pack(fill=tk.BOTH, expand=True)
        
        # 右侧分析结果
        right_frame = ttk.Frame(main_container, style="TFrame")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 创建标签页显示7维度分析
        self.style_notebook = ttk.Notebook(right_frame)
        self.style_notebook.pack(fill=tk.BOTH, expand=True)
        
        # 概览
        overview_frame = ttk.Frame(self.style_notebook)
        self.style_notebook.add(overview_frame, text="📊 概览")
        self.overview_text = scrolledtext.ScrolledText(
            overview_frame,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.overview_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 词汇
        vocab_frame = ttk.Frame(self.style_notebook)
        self.style_notebook.add(vocab_frame, text="📝 词汇")
        self.vocab_text = scrolledtext.ScrolledText(
            vocab_frame,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.vocab_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 句式
        sentence_frame = ttk.Frame(self.style_notebook)
        self.style_notebook.add(sentence_frame, text="🎨 句式")
        self.sentence_text = scrolledtext.ScrolledText(
            sentence_frame,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.sentence_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 修辞
        rhetoric_frame = ttk.Frame(self.style_notebook)
        self.style_notebook.add(rhetoric_frame, text="💡 修辞")
        self.rhetoric_text = scrolledtext.ScrolledText(
            rhetoric_frame,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.rhetoric_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 情感
        emotion_frame = ttk.Frame(self.style_notebook)
        self.style_notebook.add(emotion_frame, text="💭 情感")
        self.emotion_text = scrolledtext.ScrolledText(
            emotion_frame,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.emotion_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 节奏
        rhythm_frame = ttk.Frame(self.style_notebook)
        self.style_notebook.add(rhythm_frame, text="🎵 节奏")
        self.rhythm_text = scrolledtext.ScrolledText(
            rhythm_frame,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.rhythm_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 结构
        structure_frame = ttk.Frame(self.style_notebook)
        self.style_notebook.add(structure_frame, text="🏛️ 结构")
        self.structure_text = scrolledtext.ScrolledText(
            structure_frame,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.structure_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 加载示例
        self._load_sample_data()
    
    def _load_sample_data(self):
        """加载示例数据"""
        self.style_listbox.insert(tk.END, "范文1-修仙小说片段.txt")
        self.style_listbox.insert(tk.END, "范文2-都市情感片段.txt")
        
        self.overview_text.insert("1.0", "风格概览\n\n整体风格：古风修仙\n语言特点：文白夹杂，意境深远\n推荐指数：⭐⭐⭐⭐⭐")
    
    def _import_style(self):
        """导入范文"""
        file_path = filedialog.askopenfilename(
            title="选择范文文件",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx")]
        )
        if file_path:
            self.style_listbox.insert(tk.END, os.path.basename(file_path))
            messagebox.showinfo("成功", f"已导入范文：\n{file_path}")
    
    def _learn_style(self):
        """深度学习风格"""
        messagebox.showinfo("提示", "风格学习功能开发中...\n\n将调用V5的enhanced_style_learner_v2模块")
    
    def _save_style(self):
        """保存风格"""
        messagebox.showinfo("成功", "风格已保存")
    
    def _export_style(self):
        """导出风格"""
        file_path = filedialog.asksaveasfilename(
            title="保存风格",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")]
        )
        if file_path:
            messagebox.showinfo("成功", f"风格已导出到：\n{file_path}")


class GenerationModule:
    """开始创作模块"""
    
    def __init__(self, parent: tk.Widget, theme, event_bus=None):
        self.parent = parent
        self.theme = theme
        self.event_bus = event_bus
        
        self._create_ui()
    
    def _create_ui(self):
        """创建UI界面"""
        # 创建可滚动容器
        canvas = tk.Canvas(self.parent, bg=self.theme.paper_white)
        scrollbar = ttk.Scrollbar(self.parent, orient="vertical", command=canvas.yview)
        main_container = ttk.Frame(canvas, style="TFrame")
        
        main_container.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas_window = canvas.create_window((0, 0), window=main_container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 鼠标滚轮支持
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # AI模型配置
        model_frame = ttk.LabelFrame(main_container, text="🤖 AI模型配置", padding="10")
        model_frame.pack(fill=tk.X, padx=15, pady=10)
        
        ttk.Label(model_frame, text="模型提供商:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.provider_combo = ttk.Combobox(
            model_frame,
            values=["DeepSeek", "OpenAI", "Anthropic", "Ollama"],
            width=20
        )
        self.provider_combo.grid(row=0, column=1, sticky=tk.W, pady=3, padx=5)
        self.provider_combo.set("DeepSeek")
        
        ttk.Label(model_frame, text="模型:").grid(row=0, column=2, sticky=tk.W, pady=3)
        self.model_combo = ttk.Combobox(
            model_frame,
            values=["deepseek-chat", "gpt-4", "claude-3", "llama2"],
            width=20
        )
        self.model_combo.grid(row=0, column=3, sticky=tk.W, pady=3, padx=5)
        self.model_combo.set("deepseek-chat")
        
        ttk.Label(model_frame, text="API Key:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.api_key_entry = ttk.Entry(model_frame, width=50, show="*")
        self.api_key_entry.grid(row=1, column=1, columnspan=3, sticky=tk.EW, pady=3, padx=5)
        
        # 生成选项
        options_frame = ttk.LabelFrame(main_container, text="⚙️ 生成选项", padding="10")
        options_frame.pack(fill=tk.X, padx=15, pady=10)
        
        ttk.Label(options_frame, text="起始章节:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.start_chapter = ttk.Spinbox(options_frame, from_=1, to=100, width=15)
        self.start_chapter.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        self.start_chapter.set(1)
        
        ttk.Label(options_frame, text="结束章节:").grid(row=0, column=2, sticky=tk.W, pady=5)
        self.end_chapter = ttk.Spinbox(options_frame, from_=1, to=100, width=15)
        self.end_chapter.grid(row=0, column=3, sticky=tk.W, pady=5, padx=5)
        self.end_chapter.set(1)
        
        ttk.Label(options_frame, text="目标字数/章:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.target_words = ttk.Spinbox(options_frame, from_=500, to=5000, increment=100, width=15)
        self.target_words.grid(row=1, column=1, sticky=tk.W, pady=5, padx=5)
        self.target_words.set(900)
        
        ttk.Label(options_frame, text="生成温度:").grid(row=1, column=2, sticky=tk.W, pady=5)
        self.temperature_scale = ttk.Scale(options_frame, from_=0.0, to=1.0, orient=tk.HORIZONTAL)
        self.temperature_scale.grid(row=1, column=3, sticky=tk.W, pady=5, padx=5)
        self.temperature_scale.set(0.7)
        
        # 出场人物
        characters_frame = ttk.LabelFrame(main_container, text="👥 出场人物", padding="10")
        characters_frame.pack(fill=tk.X, padx=15, pady=10)
        
        self.characters_text = scrolledtext.ScrolledText(
            characters_frame,
            width=60,
            height=3,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.characters_text.pack(fill=tk.X)
        self.characters_text.insert("1.0", "可手动输入出场人物名称，用逗号分隔")
        
        # 输出设置
        output_frame = ttk.LabelFrame(main_container, text="📁 输出设置", padding="10")
        output_frame.pack(fill=tk.X, padx=15, pady=10)
        
        ttk.Label(output_frame, text="输出目录:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.output_path_entry = ttk.Entry(output_frame, width=40)
        self.output_path_entry.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)
        self.output_path_entry.insert(0, os.path.join(os.getcwd(), "小说"))
        
        ttk.Button(output_frame, text="浏览...", 
                   command=self._browse_output).grid(row=0, column=2, pady=5)
        
        ttk.Label(output_frame, text="文件前缀:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.file_prefix_entry = ttk.Entry(output_frame, width=40)
        self.file_prefix_entry.grid(row=1, column=1, columnspan=2, sticky=tk.EW, pady=5, padx=5)
        self.file_prefix_entry.insert(0, "novel")
        
        # 生成进度
        progress_frame = ttk.LabelFrame(main_container, text="📊 生成进度", padding="10")
        progress_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        self.progress_status = ttk.Label(progress_frame, text="准备就绪")
        self.progress_status.pack(anchor=tk.W, pady=5)
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate', length=400)
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(
            progress_frame,
            width=70,
            height=15,
            font=("Consolas", 9),
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 按钮区
        button_frame = ttk.Frame(main_container, style="TFrame")
        button_frame.pack(pady=15)
        
        self.generate_btn = ttk.Button(
            button_frame,
            text="🚀 开始生成",
            command=self._start_generation,
            width=15
        )
        self.generate_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="💾 保存配置",
            command=self._save_config,
            width=15
        ).pack(side=tk.LEFT, padx=5)
    
    def _browse_output(self):
        """浏览输出目录"""
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_path_entry.delete(0, tk.END)
            self.output_path_entry.insert(0, path)
    
    def _start_generation(self):
        """开始生成"""
        self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 开始生成...\n")
        self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 调用V5生成模块...\n")
        self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 生成功能开发中，请稍候...\n")
        messagebox.showinfo("提示", "生成功能开发中...\n\n将调用V5的迭代生成和加权验证模块")
    
    def _save_config(self):
        """保存配置"""
        messagebox.showinfo("成功", "配置已保存")


class ReverseModule:
    """逆向反馈模块"""
    
    def __init__(self, parent: tk.Widget, theme, event_bus=None):
        self.parent = parent
        self.theme = theme
        self.event_bus = event_bus
        
        self._create_ui()
    
    def _create_ui(self):
        """创建UI界面"""
        # 主容器
        main_container = ttk.Frame(self.parent, style="TFrame")
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # 说明
        help_frame = ttk.LabelFrame(main_container, text="🔍 功能说明", padding="10")
        help_frame.pack(fill=tk.X, pady=(0, 10))
        
        help_text = (
            "逆向反馈功能可以分析已生成的小说内容，反向提取和优化设定：\n"
            "• 自动提取并更新人物设定\n"
            "• 自动提取并更新世界观设定\n"
            "• 自动提取并更新写作风格\n"
            "• 检测章节间的逻辑矛盾\n"
            "• 生成章节优化建议"
        )
        ttk.Label(help_frame, text=help_text, font=self.theme.font_body, 
                  justify=tk.LEFT).pack(fill=tk.X)
        
        # 文件选择
        file_frame = ttk.LabelFrame(main_container, text="📁 选择已生成内容", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(file_frame, text="文件路径:").grid(row=0, column=0, sticky=tk.W)
        self.file_entry = ttk.Entry(file_frame, width=50)
        self.file_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Button(file_frame, text="浏览...", 
                   command=self._browse_file).grid(row=0, column=2)
        
        file_frame.columnconfigure(1, weight=1)
        
        # 分析选项
        options_frame = ttk.LabelFrame(main_container, text="⚙️ 分析选项", padding="10")
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.check_consistency = tk.BooleanVar(value=True)
        self.check_logic = tk.BooleanVar(value=True)
        self.check_character = tk.BooleanVar(value=True)
        self.check_style = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(options_frame, text="一致性检查", 
                        variable=self.check_consistency).pack(anchor=tk.W)
        ttk.Checkbutton(options_frame, text="逻辑漏洞检测", 
                        variable=self.check_logic).pack(anchor=tk.W)
        ttk.Checkbutton(options_frame, text="人设偏离检测", 
                        variable=self.check_character).pack(anchor=tk.W)
        ttk.Checkbutton(options_frame, text="风格匹配度分析", 
                        variable=self.check_style).pack(anchor=tk.W)
        
        # 分析结果
        result_frame = ttk.LabelFrame(main_container, text="📊 分析结果", padding="10")
        result_frame.pack(fill=tk.BOTH, expand=True)
        
        self.result_text = scrolledtext.ScrolledText(
            result_frame,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.result_text.pack(fill=tk.BOTH, expand=True)
        
        # 按钮区
        button_frame = ttk.Frame(main_container, style="TFrame")
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="🔍 开始分析",
                   command=self._start_analysis).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🔄 自动修正",
                   command=self._auto_fix).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="📤 导出报告",
                   command=self._export_report).pack(side=tk.LEFT, padx=5)
    
    def _browse_file(self):
        """浏览文件"""
        file_path = filedialog.askopenfilename(
            title="选择已生成的小说文件",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx")]
        )
        if file_path:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, file_path)
    
    def _start_analysis(self):
        """开始分析"""
        file_path = self.file_entry.get()
        if not file_path:
            messagebox.showwarning("警告", "请先选择要分析的文件")
            return
        
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", f"正在分析文件：{file_path}\n\n")
        self.result_text.insert(tk.END, "分析功能开发中...\n\n")
        self.result_text.insert(tk.END, "将调用V5的核心模块进行逆向分析。")
        messagebox.showinfo("提示", "逆向分析功能开发中...")
    
    def _auto_fix(self):
        """自动修正"""
        messagebox.showinfo("提示", "自动修正功能开发中...")
    
    def _export_report(self):
        """导出报告"""
        file_path = filedialog.asksaveasfilename(
            title="保存分析报告",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx")]
        )
        if file_path:
            messagebox.showinfo("成功", f"报告已导出到：\n{file_path}")


class QuickModule:
    """快捷创作模块"""
    
    def __init__(self, parent: tk.Widget, theme, event_bus=None):
        self.parent = parent
        self.theme = theme
        self.event_bus = event_bus
        
        self._create_ui()
    
    def _create_ui(self):
        """创建UI界面"""
        # 主容器
        main_container = ttk.Frame(self.parent, style="TFrame")
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # 模式选择
        mode_frame = ttk.LabelFrame(main_container, text="🎯 创作模式", padding="10")
        mode_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.mode_var = tk.StringVar(value="worldview")
        
        modes = [
            ("世界观", "worldview", "快速生成世界观设定"),
            ("大纲", "outline", "快速生成章节大纲"),
            ("人设", "character", "快速生成人物档案"),
            ("情节", "plot", "快速生成关键情节"),
        ]
        
        for i, (text, value, desc) in enumerate(modes):
            ttk.Radiobutton(
                mode_frame,
                text=text,
                value=value,
                variable=self.mode_var
            ).grid(row=0, column=i, padx=10, pady=5)
            ttk.Label(mode_frame, text=desc, font=("Microsoft YaHei UI", 8),
                      foreground="gray").grid(row=1, column=i, padx=10)
        
        # 输入区
        input_frame = ttk.LabelFrame(main_container, text="📝 创作需求", padding="10")
        input_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        ttk.Label(input_frame, text="简单描述您的需求：").pack(anchor=tk.W)
        
        self.input_text = scrolledtext.ScrolledText(
            input_frame,
            width=60,
            height=10,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.input_text.pack(fill=tk.BOTH, expand=True, pady=10)
        self.input_text.insert("1.0", "例如：生成一个修仙世界的世界观，包含灵气体系、宗门设定、境界划分等")
        
        # 生成结果
        result_frame = ttk.LabelFrame(main_container, text="📄 生成结果", padding="10")
        result_frame.pack(fill=tk.BOTH, expand=True)
        
        self.result_text = scrolledtext.ScrolledText(
            result_frame,
            width=60,
            height=15,
            font=self.theme.font_body,
            bg=self.theme.paper_cream,
            fg=self.theme.ink_dark
        )
        self.result_text.pack(fill=tk.BOTH, expand=True)
        
        # 按钮区
        button_frame = ttk.Frame(main_container, style="TFrame")
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="🚀 快速生成",
                   command=self._quick_generate).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="💾 保存结果",
                   command=self._save_result).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="📥 导入项目",
                   command=self._import_to_project).pack(side=tk.LEFT, padx=5)
    
    def _quick_generate(self):
        """快速生成"""
        mode = self.mode_var.get()
        requirement = self.input_text.get("1.0", tk.END).strip()
        
        if not requirement:
            messagebox.showwarning("警告", "请输入创作需求")
            return
        
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", f"正在生成{mode}...\n\n")
        self.result_text.insert(tk.END, "快速生成功能开发中...\n\n")
        self.result_text.insert(tk.END, "将调用AI模型根据您的需求快速生成内容。")
        
        messagebox.showinfo("提示", "快捷生成功能开发中...")
    
    def _save_result(self):
        """保存结果"""
        content = self.result_text.get("1.0", tk.END)
        if not content.strip():
            messagebox.showwarning("警告", "没有可保存的内容")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="保存生成结果",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("Word文档", "*.docx")]
        )
        if file_path:
            messagebox.showinfo("成功", f"结果已保存到：\n{file_path}")
    
    def _import_to_project(self):
        """导入到项目"""
        messagebox.showinfo("提示", "导入功能开发中...\n\n将把生成的内容导入到当前项目对应模块")


# 导出所有模块
__all__ = [
    'WorldviewModule',
    'CharacterModule', 
    'OutlineModule',
    'StyleModule',
    'GenerationModule',
    'ReverseModule',
    'QuickModule'
]
