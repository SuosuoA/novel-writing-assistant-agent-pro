#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专家选择器组件

功能：
1. ExpertSelectorWidget - 专家选择下拉框
2. ExpertConfigDialog - 专家配置对话框

设计原则：
- 延迟加载，不影响启动速度
- 独立模块，最小侵入gui_main.py
- 完整降级方案，专家加载失败时回退

作者：前端开发工程师
版本：V1.0.0
日期：2026-03-29
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
import logging

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class ExpertInfo:
    """专家信息数据类"""
    expert_id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)


class ExpertSelectorWidget:
    """
    专家选择器组件
    
    功能：
    - 下拉框选择专家
    - 配置按钮打开配置对话框
    - 发布专家选择事件
    
    使用方式：
    ```python
    selector = ExpertSelectorWidget(parent_frame, plugin_registry)
    selector.pack(fill=tk.X)
    
    # 获取选择的专家
    expert = selector.get_selected_expert()
    config = selector.get_config()
    ```
    """
    
    def __init__(self, parent: tk.Widget, plugin_registry=None, on_expert_changed: Callable = None):
        """
        初始化专家选择器
        
        Args:
            parent: 父容器
            plugin_registry: 插件注册表（可选，用于获取可用专家列表）
            on_expert_changed: 专家选择变化回调（可选）
        """
        self.parent = parent
        self.plugin_registry = plugin_registry
        self.on_expert_changed = on_expert_changed
        
        # 状态变量
        self.expert_var = tk.StringVar(value="默认模式")
        self.current_expert: Optional[ExpertInfo] = None
        self.expert_configs: Dict[str, Dict[str, Any]] = {}
        
        # 可用专家列表（预定义）
        self.available_experts = [
            ExpertInfo(
                expert_id="expert-novel-v1",
                name="小说创作专家",
                description="专门优化小说质量，整合世界观/人设/大纲/风格/知识库/写作技巧",
                version="1.0.0",
                capabilities=[
                    "世界观整合",
                    "人设增强",
                    "大纲对齐",
                    "风格优化",
                    "知识库注入",
                    "写作技巧应用"
                ],
                config={
                    "enable_memory": True,
                    "enable_local_model": True,
                    "quality_threshold": 0.8,
                    "max_iterations": 5
                }
            )
        ]
        
        # 创建UI
        self.frame = ttk.Frame(parent)
        self._create_widgets()
        
        logger.info("专家选择器初始化完成")
    
    def _create_widgets(self):
        """创建UI组件"""
        # 专家选择标签
        ttk.Label(self.frame, text="创作模式：", font=("Microsoft YaHei UI", 10)).pack(side=tk.LEFT, padx=(0, 5))
        
        # 专家下拉框
        expert_names = ["默认模式"] + [e.name for e in self.available_experts]
        self.expert_combobox = ttk.Combobox(
            self.frame,
            textvariable=self.expert_var,
            values=expert_names,
            state="readonly",
            width=20,
            font=("Microsoft YaHei UI", 10)
        )
        self.expert_combobox.pack(side=tk.LEFT, padx=5)
        self.expert_combobox.bind("<<ComboboxSelected>>", self._on_expert_selected)
        
        # 配置按钮（齿轮图标）
        self.config_button = ttk.Button(
            self.frame,
            text="⚙",
            width=3,
            command=self._show_expert_config
        )
        self.config_button.pack(side=tk.LEFT, padx=5)
        
        # 专家信息提示（初始隐藏）
        self.info_label = ttk.Label(
            self.frame,
            text="",
            font=("Microsoft YaHei UI", 9),
            foreground="gray"
        )
        self.info_label.pack(side=tk.LEFT, padx=5)
    
    def _on_expert_selected(self, event=None):
        """专家选择事件处理"""
        selected_name = self.expert_var.get()
        
        if selected_name == "默认模式":
            self.current_expert = None
            self.info_label.config(text="")
            self.config_button.config(state=tk.DISABLED)
        else:
            # 查找选中的专家
            for expert in self.available_experts:
                if expert.name == selected_name:
                    self.current_expert = expert
                    self.info_label.config(text=f"v{expert.version}")
                    self.config_button.config(state=tk.NORMAL)
                    
                    # 初始化配置
                    if expert.expert_id not in self.expert_configs:
                        self.expert_configs[expert.expert_id] = expert.config.copy()
                    break
        
        # 调用回调
        if self.on_expert_changed:
            self.on_expert_changed(self.current_expert)
        
        logger.info(f"专家选择变化: {selected_name}")
    
    def _show_expert_config(self):
        """显示专家配置对话框"""
        if not self.current_expert:
            messagebox.showinfo("提示", "请先选择一个专家")
            return
        
        # 创建配置对话框
        dialog = ExpertConfigDialog(
            self.frame,
            self.current_expert,
            self.expert_configs.get(self.current_expert.expert_id, {})
        )
        
        # 等待对话框关闭
        self.frame.wait_window(dialog.dialog)
        
        # 获取配置结果
        if dialog.result:
            self.expert_configs[self.current_expert.expert_id] = dialog.result
            logger.info(f"专家配置已更新: {self.current_expert.expert_id}")
    
    def get_selected_expert(self) -> Optional[str]:
        """
        获取当前选择的专家ID
        
        Returns:
            str: 专家ID，如果选择默认模式则返回None
        """
        if self.current_expert:
            return self.current_expert.expert_id
        return None
    
    def get_config(self) -> Dict[str, Any]:
        """
        获取当前专家的配置
        
        Returns:
            dict: 专家配置字典
        """
        if self.current_expert:
            return self.expert_configs.get(self.current_expert.expert_id, self.current_expert.config.copy())
        return {}
    
    def get_expert_info(self) -> Optional[ExpertInfo]:
        """
        获取当前选择的专家信息
        
        Returns:
            ExpertInfo: 专家信息，如果选择默认模式则返回None
        """
        return self.current_expert
    
    def pack(self, **kwargs):
        """包装pack方法"""
        self.frame.pack(**kwargs)
    
    def grid(self, **kwargs):
        """包装grid方法"""
        self.frame.grid(**kwargs)


class ExpertConfigDialog:
    """
    专家配置对话框
    
    功能：
    - 配置专家模式参数
    - 启用/禁用记忆集成
    - 启用/禁用本地模型
    - 设置质量阈值和迭代上限
    """
    
    def __init__(self, parent: tk.Widget, expert: ExpertInfo, initial_config: Dict[str, Any]):
        """
        初始化配置对话框
        
        Args:
            parent: 父窗口
            expert: 专家信息
            initial_config: 初始配置
        """
        self.parent = parent
        self.expert = expert
        self.initial_config = initial_config.copy()
        self.result: Optional[Dict[str, Any]] = None
        
        # 创建对话框
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"{expert.name} - 配置")
        self.dialog.geometry("450x400")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # 居中显示
        self._center_window()
        
        # 创建UI
        self._create_widgets()
        
        # 加载初始配置
        self._load_config()
    
    def _center_window(self):
        """窗口居中"""
        self.dialog.update_idletasks()
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
    
    def _create_widgets(self):
        """创建UI组件"""
        # 主框架
        main_frame = ttk.Frame(self.dialog, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 专家信息
        info_frame = ttk.LabelFrame(main_frame, text="专家信息", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(info_frame, text=f"名称: {self.expert.name}", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"版本: {self.expert.version}", font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"描述: {self.expert.description}", font=("Microsoft YaHei UI", 9), wraplength=400).pack(anchor=tk.W, pady=(5, 0))
        
        # 能力列表
        if self.expert.capabilities:
            caps_frame = ttk.LabelFrame(main_frame, text="核心能力", padding=10)
            caps_frame.pack(fill=tk.X, pady=(0, 10))
            
            caps_text = " | ".join(self.expert.capabilities)
            ttk.Label(caps_frame, text=caps_text, font=("Microsoft YaHei UI", 9), wraplength=400, foreground="gray").pack(anchor=tk.W)
        
        # 配置选项
        config_frame = ttk.LabelFrame(main_frame, text="配置选项", padding=10)
        config_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 记忆集成开关
        self.memory_var = tk.BooleanVar(value=True)
        memory_frame = ttk.Frame(config_frame)
        memory_frame.pack(fill=tk.X, pady=5)
        ttk.Checkbutton(memory_frame, text="启用Claw记忆集成（越用越聪明）", variable=self.memory_var).pack(side=tk.LEFT)
        ttk.Label(memory_frame, text="存储评分历史，优化建议生成", font=("Microsoft YaHei UI", 8), foreground="gray").pack(side=tk.LEFT, padx=(10, 0))
        
        # 本地模型开关
        self.local_model_var = tk.BooleanVar(value=True)
        model_frame = ttk.Frame(config_frame)
        model_frame.pack(fill=tk.X, pady=5)
        ttk.Checkbutton(model_frame, text="启用本地模型辅助", variable=self.local_model_var).pack(side=tk.LEFT)
        ttk.Label(model_frame, text="语义评分，AI痕迹检测", font=("Microsoft YaHei UI", 8), foreground="gray").pack(side=tk.LEFT, padx=(10, 0))
        
        # 质量阈值
        threshold_frame = ttk.Frame(config_frame)
        threshold_frame.pack(fill=tk.X, pady=5)
        ttk.Label(threshold_frame, text="质量阈值:", font=("Microsoft YaHei UI", 10)).pack(side=tk.LEFT)
        self.threshold_var = tk.DoubleVar(value=0.8)
        threshold_spin = ttk.Spinbox(threshold_frame, from_=0.5, to=1.0, increment=0.05, textvariable=self.threshold_var, width=8)
        threshold_spin.pack(side=tk.LEFT, padx=5)
        ttk.Label(threshold_frame, text="(低于此分数触发优化)", font=("Microsoft YaHei UI", 8), foreground="gray").pack(side=tk.LEFT)
        
        # 迭代上限
        iter_frame = ttk.Frame(config_frame)
        iter_frame.pack(fill=tk.X, pady=5)
        ttk.Label(iter_frame, text="迭代上限:", font=("Microsoft YaHei UI", 10)).pack(side=tk.LEFT)
        self.iter_var = tk.IntVar(value=5)
        iter_spin = ttk.Spinbox(iter_frame, from_=1, to=10, increment=1, textvariable=self.iter_var, width=8)
        iter_spin.pack(side=tk.LEFT, padx=5)
        ttk.Label(iter_frame, text="(最多重新生成次数)", font=("Microsoft YaHei UI", 8), foreground="gray").pack(side=tk.LEFT)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="确定", command=self._on_ok, width=10).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="取消", command=self._on_cancel, width=10).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="恢复默认", command=self._reset_to_default, width=10).pack(side=tk.LEFT)
    
    def _load_config(self):
        """加载初始配置"""
        self.memory_var.set(self.initial_config.get("enable_memory", True))
        self.local_model_var.set(self.initial_config.get("enable_local_model", True))
        self.threshold_var.set(self.initial_config.get("quality_threshold", 0.8))
        self.iter_var.set(self.initial_config.get("max_iterations", 5))
    
    def _reset_to_default(self):
        """恢复默认配置"""
        if self.expert.config:
            self._load_config()
            messagebox.showinfo("提示", "已恢复默认配置")
    
    def _on_ok(self):
        """确定按钮"""
        self.result = {
            "enable_memory": self.memory_var.get(),
            "enable_local_model": self.local_model_var.get(),
            "quality_threshold": self.threshold_var.get(),
            "max_iterations": self.iter_var.get()
        }
        self.dialog.destroy()
    
    def _on_cancel(self):
        """取消按钮"""
        self.result = None
        self.dialog.destroy()


# 导出
__all__ = ['ExpertSelectorWidget', 'ExpertConfigDialog', 'ExpertInfo']
