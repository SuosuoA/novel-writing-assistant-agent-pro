#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专家评估对话框

功能：
1. ExpertEvaluationDialog - 九维度评分结果展示
2. 优化建议显示（支持折叠）
3. 修改示例对比显示
4. 用户决策（采纳/保持）

设计原则：
- 清晰直观的评分可视化
- 切实可执行的优化建议
- 一键采纳并重新生成

作者：前端开发工程师
版本：V1.0.0
日期：2026-03-29
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
import logging

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class ExpertEvaluation:
    """专家评估结果数据类"""
    total_score: float  # 总分 0.0 - 1.0
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    analysis: Dict[str, str] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)


@dataclass
class OptimizationSuggestion:
    """优化建议数据类"""
    overall_suggestion: str
    dimension_suggestions: Dict[str, str] = field(default_factory=dict)
    examples: List[Dict[str, str]] = field(default_factory=list)
    priority: str = "medium"  # high/medium/low


class ExpertEvaluationDialog:
    """
    专家评估结果对话框
    
    功能：
    - 显示总分和各维度评分（进度条可视化）
    - 显示优化建议（可折叠）
    - 显示修改示例（原文 vs 建议）
    - 用户决策：采纳建议并重新生成 / 保持当前内容
    
    使用方式：
    ```python
    dialog = ExpertEvaluationDialog(parent, evaluation, suggestion)
    dialog.show()
    
    # 等待结果
    if dialog.accepted:
        # 用户选择采纳
        pass
    ```
    """
    
    # 维度权重配置（与设计方案一致）
    DIMENSION_WEIGHTS = {
        "世界观": 0.12,
        "人设": 0.19,
        "大纲": 0.13,
        "风格": 0.19,
        "知识库": 0.08,
        "写作技巧": 0.08,
        "字数": 0.08,
        "上下文衔接": 0.08,
        "AI感": 0.05
    }
    
    # 维度顺序（按权重降序）
    DIMENSION_ORDER = ["人设", "风格", "大纲", "世界观", "知识库", "写作技巧", "字数", "上下文衔接", "AI感"]
    
    def __init__(self, parent: tk.Widget, evaluation: ExpertEvaluation, suggestion: OptimizationSuggestion, on_regenerate: Callable = None):
        """
        初始化评估对话框
        
        Args:
            parent: 父窗口
            evaluation: 评估结果
            suggestion: 优化建议
            on_regenerate: 重新生成回调（可选）
        """
        self.parent = parent
        self.evaluation = evaluation
        self.suggestion = suggestion
        self.on_regenerate = on_regenerate
        
        # 状态变量
        self.accepted = False
        self.suggestion_frames: Dict[str, ttk.Frame] = {}
        
        # 创建对话框
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("专家评估结果")
        self.dialog.geometry("900x700")
        self.dialog.resizable(True, True)
        self.dialog.transient(parent)
        
        # 居中显示
        self._center_window()
        
        # 创建UI
        self._create_widgets()
        
        # 设置焦点
        self.dialog.focus_set()
    
    def _center_window(self):
        """窗口居中"""
        self.dialog.update_idletasks()
        width = 900
        height = 700
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
    
    def _create_widgets(self):
        """创建UI组件"""
        # 主框架
        main_frame = ttk.Frame(self.dialog, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 顶部：总分显示
        self._create_total_score_section(main_frame)
        
        # 中部：九维度评分（左侧）+ 问题/优势（右侧）
        middle_frame = ttk.Frame(main_frame)
        middle_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 10))
        
        self._create_dimensions_section(middle_frame)
        self._create_issues_strengths_section(middle_frame)
        
        # 底部：优化建议
        self._create_suggestions_section(main_frame)
        
        # 修改示例（如果有）
        if self.suggestion.examples:
            self._create_examples_section(main_frame)
        
        # 底部按钮
        self._create_buttons(main_frame)
    
    def _create_total_score_section(self, parent: ttk.Frame):
        """创建总分显示区域"""
        score_frame = ttk.Frame(parent)
        score_frame.pack(fill=tk.X)
        
        # 总分标签
        total_label = ttk.Label(
            score_frame,
            text=f"总分：{self.evaluation.total_score:.1%}",
            font=("Microsoft YaHei UI", 18, "bold")
        )
        total_label.pack(side=tk.LEFT)
        
        # 评级图标和文字
        if self.evaluation.total_score >= 0.9:
            rating_text = "优秀 ⭐⭐⭐⭐⭐"
            rating_color = "#28a745"  # 绿色
        elif self.evaluation.total_score >= 0.8:
            rating_text = "良好 ⭐⭐⭐⭐"
            rating_color = "#17a2b8"  # 蓝色
        elif self.evaluation.total_score >= 0.6:
            rating_text = "合格 ⭐⭐⭐"
            rating_color = "#ffc107"  # 黄色
        else:
            rating_text = "需改进 ⭐⭐"
            rating_color = "#dc3545"  # 红色
        
        rating_label = ttk.Label(
            score_frame,
            text=rating_text,
            font=("Microsoft YaHei UI", 14),
            foreground=rating_color
        )
        rating_label.pack(side=tk.LEFT, padx=(15, 0))
        
        # 质量状态
        if self.evaluation.total_score >= 0.8:
            status_text = "✓ 达标"
            status_color = "#28a745"
        else:
            status_text = "⚠ 低于阈值"
            status_color = "#dc3545"
        
        status_label = ttk.Label(
            score_frame,
            text=status_text,
            font=("Microsoft YaHei UI", 12),
            foreground=status_color
        )
        status_label.pack(side=tk.RIGHT)
    
    def _create_dimensions_section(self, parent: ttk.Frame):
        """创建九维度评分区域"""
        dims_frame = ttk.LabelFrame(parent, text="九维度评分", padding=10)
        dims_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # 创建画布，支持滚动
        canvas = tk.Canvas(dims_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(dims_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 添加各维度评分
        for dim in self.DIMENSION_ORDER:
            score = self.evaluation.dimension_scores.get(dim, 0.0)
            weight = self.DIMENSION_WEIGHTS.get(dim, 0.0)
            self._create_dimension_row(scrollable_frame, dim, score, weight)
    
    def _create_dimension_row(self, parent: ttk.Frame, dimension: str, score: float, weight: float):
        """创建单个维度评分行"""
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill=tk.X, pady=3)
        
        # 维度名称
        ttk.Label(
            row_frame,
            text=dimension,
            font=("Microsoft YaHei UI", 10),
            width=10,
            anchor=tk.W
        ).pack(side=tk.LEFT)
        
        # 进度条容器
        progress_frame = ttk.Frame(row_frame)
        progress_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # 进度条
        style = ttk.Style()
        style_name = f"Custom.Horizontal.TProgressbar.{dimension}"
        
        # 根据分数设置颜色
        if score >= 0.8:
            bar_color = "#28a745"  # 绿色
        elif score >= 0.6:
            bar_color = "#ffc107"  # 黄色
        else:
            bar_color = "#dc3545"  # 红色
        
        progress = ttk.Progressbar(
            progress_frame,
            length=200,
            mode='determinate',
            maximum=100
        )
        progress['value'] = score * 100
        progress.pack(side=tk.LEFT)
        
        # 分数文字
        score_label = ttk.Label(
            row_frame,
            text=f"{score:.1%}",
            font=("Microsoft YaHei UI", 10),
            width=8
        )
        score_label.pack(side=tk.LEFT)
        
        # 根据分数设置颜色
        if score >= 0.8:
            score_label.config(foreground="#28a745")
        elif score >= 0.6:
            score_label.config(foreground="#996600")
        else:
            score_label.config(foreground="#dc3545")
        
        # 权重提示
        ttk.Label(
            row_frame,
            text=f"({weight:.0%})",
            font=("Microsoft YaHei UI", 8),
            foreground="gray"
        ).pack(side=tk.LEFT, padx=(5, 0))
    
    def _create_issues_strengths_section(self, parent: ttk.Frame):
        """创建问题和优势区域"""
        right_frame = ttk.Frame(parent)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # 问题列表
        if self.evaluation.issues:
            issues_frame = ttk.LabelFrame(right_frame, text="⚠ 需要改进", padding=10)
            issues_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
            
            for issue in self.evaluation.issues[:5]:  # 最多显示5个
                ttk.Label(
                    issues_frame,
                    text=f"• {issue}",
                    font=("Microsoft YaHei UI", 9),
                    wraplength=250,
                    foreground="#dc3545"
                ).pack(anchor=tk.W, pady=2)
        
        # 优势列表
        if self.evaluation.strengths:
            strengths_frame = ttk.LabelFrame(right_frame, text="✓ 亮点", padding=10)
            strengths_frame.pack(fill=tk.BOTH, expand=True)
            
            for strength in self.evaluation.strengths[:5]:  # 最多显示5个
                ttk.Label(
                    strengths_frame,
                    text=f"• {strength}",
                    font=("Microsoft YaHei UI", 9),
                    wraplength=250,
                    foreground="#28a745"
                ).pack(anchor=tk.W, pady=2)
    
    def _create_suggestions_section(self, parent: ttk.Frame):
        """创建优化建议区域"""
        suggestions_frame = ttk.LabelFrame(parent, text="优化建议", padding=10)
        suggestions_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 总体建议
        if self.suggestion.overall_suggestion:
            overall_label = ttk.Label(
                suggestions_frame,
                text=self.suggestion.overall_suggestion,
                font=("Microsoft YaHei UI", 10),
                wraplength=800,
                justify=tk.LEFT
            )
            overall_label.pack(anchor=tk.W, pady=(0, 10))
        
        # 各维度建议（可折叠）
        if self.suggestion.dimension_suggestions:
            for dim, suggestion in self.suggestion.dimension_suggestions.items():
                self._create_collapsible_suggestion(suggestions_frame, dim, suggestion)
    
    def _create_collapsible_suggestion(self, parent: ttk.Frame, dimension: str, suggestion: str):
        """创建可折叠的建议行"""
        # 外层框架
        outer_frame = ttk.Frame(parent)
        outer_frame.pack(fill=tk.X, pady=2)
        
        # 折叠状态
        is_expanded = tk.BooleanVar(value=False)
        
        # 标题行
        title_frame = ttk.Frame(outer_frame)
        title_frame.pack(fill=tk.X)
        
        # 展开/折叠按钮
        expand_btn = ttk.Button(
            title_frame,
            text="▶",
            width=3,
            command=lambda: self._toggle_suggestion(expand_btn, content_frame, is_expanded)
        )
        expand_btn.pack(side=tk.LEFT)
        
        # 维度名称
        ttk.Label(
            title_frame,
            text=f"{dimension}:",
            font=("Microsoft YaHei UI", 10, "bold")
        ).pack(side=tk.LEFT, padx=5)
        
        # 简短预览
        preview = suggestion[:50] + "..." if len(suggestion) > 50 else suggestion
        ttk.Label(
            title_frame,
            text=preview,
            font=("Microsoft YaHei UI", 9),
            foreground="gray"
        ).pack(side=tk.LEFT)
        
        # 详细内容（初始隐藏）
        content_frame = ttk.Frame(outer_frame)
        content_frame.pack(fill=tk.X, padx=(20, 0), pady=(5, 0))
        
        content_label = ttk.Label(
            content_frame,
            text=suggestion,
            font=("Microsoft YaHei UI", 10),
            wraplength=750,
            justify=tk.LEFT
        )
        content_label.pack(anchor=tk.W)
        
        # 初始隐藏
        content_frame.pack_forget()
        
        # 保存引用
        self.suggestion_frames[dimension] = content_frame
    
    def _toggle_suggestion(self, btn: ttk.Button, frame: ttk.Frame, is_expanded: tk.BooleanVar):
        """切换建议的展开/折叠状态"""
        if is_expanded.get():
            frame.pack_forget()
            btn.config(text="▶")
            is_expanded.set(False)
        else:
            frame.pack(fill=tk.X, padx=(20, 0), pady=(5, 0))
            btn.config(text="▼")
            is_expanded.set(True)
    
    def _create_examples_section(self, parent: ttk.Frame):
        """创建修改示例区域"""
        examples_frame = ttk.LabelFrame(parent, text="修改示例", padding=10)
        examples_frame.pack(fill=tk.X, pady=(0, 10))
        
        for i, example in enumerate(self.suggestion.examples[:3], 1):  # 最多显示3个
            self._create_example_row(examples_frame, i, example)
    
    def _create_example_row(self, parent: ttk.Frame, index: int, example: Dict[str, str]):
        """创建单个示例行"""
        example_frame = ttk.Frame(parent)
        example_frame.pack(fill=tk.X, pady=5)
        
        # 序号
        ttk.Label(
            example_frame,
            text=f"示例{index}:",
            font=("Microsoft YaHei UI", 10, "bold")
        ).pack(anchor=tk.W)
        
        # 原文
        original_text = example.get("原文", "")
        if original_text:
            original_frame = ttk.Frame(example_frame)
            original_frame.pack(fill=tk.X, pady=(2, 0))
            
            ttk.Label(
                original_frame,
                text="原文：",
                font=("Microsoft YaHei UI", 9),
                foreground="gray"
            ).pack(side=tk.LEFT)
            
            ttk.Label(
                original_frame,
                text=original_text[:100] + ("..." if len(original_text) > 100 else ""),
                font=("Microsoft YaHei UI", 9),
                wraplength=700,
                foreground="#dc3545"
            ).pack(side=tk.LEFT)
        
        # 建议
        suggested_text = example.get("建议", "")
        if suggested_text:
            suggested_frame = ttk.Frame(example_frame)
            suggested_frame.pack(fill=tk.X, pady=(2, 0))
            
            ttk.Label(
                suggested_frame,
                text="建议：",
                font=("Microsoft YaHei UI", 9),
                foreground="gray"
            ).pack(side=tk.LEFT)
            
            ttk.Label(
                suggested_frame,
                text=suggested_text[:100] + ("..." if len(suggested_text) > 100 else ""),
                font=("Microsoft YaHei UI", 9),
                wraplength=700,
                foreground="#28a745"
            ).pack(side=tk.LEFT)
    
    def _create_buttons(self, parent: ttk.Frame):
        """创建底部按钮"""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 左侧：优先级提示
        if self.suggestion.priority == "high":
            priority_text = "🔴 高优先级"
            priority_color = "#dc3545"
        elif self.suggestion.priority == "medium":
            priority_text = "🟡 中优先级"
            priority_color = "#ffc107"
        else:
            priority_text = "🟢 低优先级"
            priority_color = "#28a745"
        
        ttk.Label(
            button_frame,
            text=priority_text,
            font=("Microsoft YaHei UI", 10),
            foreground=priority_color
        ).pack(side=tk.LEFT)
        
        # 右侧：操作按钮
        if self.evaluation.total_score < 0.8:
            # 不达标：显示采纳按钮
            ttk.Button(
                button_frame,
                text="采纳建议并重新生成",
                command=self._accept_and_regenerate,
                width=18
            ).pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(
            button_frame,
            text="保持当前内容",
            command=self._keep_current,
            width=15
        ).pack(side=tk.RIGHT, padx=5)
    
    def _accept_and_regenerate(self):
        """采纳建议并重新生成"""
        self.accepted = True
        self.dialog.destroy()
        
        # 调用重新生成回调
        if self.on_regenerate:
            self.on_regenerate(self.suggestion)
        
        logger.info("用户选择采纳建议并重新生成")
    
    def _keep_current(self):
        """保持当前内容"""
        self.accepted = False
        self.dialog.destroy()
        logger.info("用户选择保持当前内容")
    
    def show(self):
        """显示对话框"""
        self.dialog.wait_window()
        return self.accepted


# 导出
__all__ = ['ExpertEvaluationDialog', 'ExpertEvaluation', 'OptimizationSuggestion']
