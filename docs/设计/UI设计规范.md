# UI设计规范 - Novel Writing Assistant-Agent Pro

> **版本**: V2.7  
> **更新日期**: 2026-03-26  
> **设计风格**: 现代科技玻璃态（Glass Morphism）

---

## 一、设计理念

### 1.1 核心原则

**现代科技玻璃态设计**：融合毛玻璃效果、发光边框、悬浮卡片，打造专业级桌面应用视觉体验。

**三大核心理念**：
1. **沉浸式体验**：无边框窗口 + 毛玻璃背景，让用户专注于创作内容
2. **科技感美学**：科技蓝主色调 + 发光边框，传达专业工具形象
3. **响应式交互**：防抖按钮 + 异步加载 + 即时反馈，提升用户体验

### 1.2 目标用户

- **主要用户**：网络小说作者、文学创作者
- **技术水平**：从新手到专业作者
- **使用场景**：大纲构建、人物设定、风格学习、章节生成、逆向反馈
- **使用频率**：每天数小时持续使用

---

## 二、色彩体系

### 2.1 主题色板

| 色彩名称 | HEX值 | RGB值 | 用途 |
|---------|-------|-------|------|
| 科技蓝 | #0078D4 | (0, 120, 212) | 主色调、按钮高亮、选中状态 |
| 玻璃黑 | #1E1E1E | (30, 30, 30) | 背景色、侧边栏 |
| 玻璃表面 | #2D2D2D | (45, 45, 45) | 卡片背景、内容区 |
| 边框发光 | #0078D4 (60% opacity) | - | 边框发光效果 |
| 文本主色 | #FFFFFF | (255, 255, 255) | 主文本 |
| 文本次要 | #B0B0B0 | (176, 176, 176) | 次要文本、说明文字 |
| 成功绿 | #10B981 | (16, 185, 129) | 成功状态、在线状态 |
| 警告橙 | #F59E0B | (245, 158, 11) | 警告状态、未连接状态 |
| 错误红 | #EF4444 | (239, 68, 68) | 错误状态、离线状态 |
| 强调青 | #06B6D4 | (6, 182, 212) | 长篇检测页面强调色 |
| 强调紫 | #8B5CF6 | (139, 92, 246) | 特殊功能强调色 |

### 2.2 色彩应用规则

**主色调使用**：
- 主要按钮背景
- 选中/激活状态
- 图标强调色
- 边框发光效果

**背景层次**：
- 第一层：玻璃黑（#1E1E1E）- 窗口背景、侧边栏
- 第二层：玻璃表面（#2D2D2D）- 卡片、内容区
- 第三层：深色透明层 - 毛玻璃效果

**状态颜色**：
- 成功/在线：成功绿（#10B981）
- 警告/未连接：警告橙（#F59E0B）
- 错误/离线：错误红（#EF4444）

---

## 三、字体规范

### 3.1 字体家族

| 用途 | 字体 | 大小 | 粗细 |
|------|------|------|------|
| 标题栏 | Microsoft YaHei UI | 12pt | Bold |
| 页面标题 | Microsoft YaHei UI | 14pt | Bold |
| 正文内容 | Microsoft YaHei UI | 10pt | Regular |
| 代码/路径 | Consolas | 9pt | Regular |
| 按钮文字 | Microsoft YaHei UI | 10pt | Regular |
| 状态栏 | Microsoft YaHei UI | 9pt | Regular |

### 3.2 字体层级

```
一级标题 (14pt Bold)
  └─ 二级标题 (12pt Bold)
      └─ 三级标题 (10pt Bold)
          └─ 正文内容 (10pt Regular)
              └─ 说明文字 (9pt Regular, #B0B0B0)
```

---

## 四、组件规范

### 4.1 响应式按钮 (ResponsiveButton)

**规范**：
- 高度：32px
- 最小宽度：80px
- 内边距：padx=12, pady=6
- 防抖延迟：500ms
- 加载状态：禁用 + 显示加载图标

**状态**：
- 默认：科技蓝背景 + 白色文字
- 悬停：亮度+10%
- 点击：亮度-10%
- 禁用：灰色背景 + 浅灰文字
- 加载中：禁用 + 显示动画

**示例代码**：
```python
button = ResponsiveButton(
    parent=frame,
    text="开始生成",
    command=self._on_generate,
    theme=GlassTheme
)
button.pack(pady=10)
```

### 4.2 输入框 (ttk.Entry)

**规范**：
- 高度：28px
- 内边距：padx=8
- 边框：1px solid #3D3D3D
- 背景：#2D2D2D
- 文字：#FFFFFF

**状态**：
- 默认：灰色边框
- 聚焦：科技蓝边框（发光效果）
- 禁用：深灰背景 + 浅灰文字

### 4.3 下拉框 (ttk.Combobox)

**规范**：
- 高度：28px
- 下拉图标：▼
- 选项高度：28px
- 悬停高亮：科技蓝背景（20% opacity）

### 4.4 Treeview列表

**规范**：
- 行高：28px
- 表头高度：32px
- 选中背景：科技蓝（30% opacity）
- 选中文字：白色
- 隔行变色：奇数行 #2A2A2A，偶数行 #2D2D2D

**列宽规则**：
- 名称列：150-200px
- 状态列：80px
- 时间列：120px
- 自动调整：其他列

### 4.5 滚动容器

**实现模式**：Canvas + Frame + Scrollbar

**规范**：
- 滚动条宽度：12px
- 滚动条颜色：#3D3D3D
- 滚动条滑块：#5D5D5D
- 鼠标滚轮：支持 Windows/Linux/macOS

**示例代码**：
```python
# Canvas滚动容器
canvas = tk.Canvas(parent, bg="#2D2D2D", highlightthickness=0)
scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
scrollable_frame = ttk.Frame(canvas)

canvas.configure(yscrollcommand=scrollbar.set)
canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
```

---

## 五、布局规范

### 5.1 页面结构

**六大主页面**：
1. 热榜功能
2. 工作台（8个子功能）
3. 创作进度
4. 项目管理
5. 插件管理
6. 设置

**布局层级**：
```
主窗口 (1200×800px)
├─ 自定义标题栏 (height=40px)
├─ 侧边栏 (width=200px)
│   └─ 导航按钮 (6个)
└─ 内容区 (1000×760px)
    └─ 动态页面容器
```

### 5.2 间距规范

| 元素 | 水平间距 | 垂直间距 |
|------|---------|---------|
| 按钮之间 | padx=5 | pady=5 |
| 输入框之间 | padx=0 | pady=5 |
| 标签与输入框 | padx=5 | pady=0 |
| 卡片内边距 | padx=20 | pady=20 |
| 区块间距 | padx=0 | pady=15 |

### 5.3 对齐规则

- 标签：左对齐
- 按钮：居中或右对齐
- 输入框：拉伸填充
- 列表：拉伸填充

---

## 六、交互规范

### 6.1 反馈机制

**即时反馈**：
- 按钮点击：防抖 + 加载状态
- 输入验证：实时提示错误
- 操作成功：绿色提示框
- 操作失败：红色提示框

**延迟加载**：
- 工作台子页面：首次切换时创建
- 插件列表：异步加载 + "加载中..."提示
- 大数据列表：虚拟滚动 + 分页

### 6.2 防抖机制

**按钮防抖**：
- 延迟时间：500ms
- 实现方式：Timer + 取消前一次

**事件防抖**：
- Configure事件：50ms延迟
- 搜索输入：300ms延迟

**示例代码**：
```python
# 按钮防抖
self._click_timer = None

def on_click():
    if self._click_timer:
        self.root.after_cancel(self._click_timer)
    self._click_timer = self.root.after(500, actual_handler)
```

### 6.3 加载状态

**异步操作流程**：
```
1. 禁用按钮
2. 显示加载动画/进度条
3. 启动后台线程执行任务
4. 任务完成后通过 root.after(0, callback) 更新UI
5. 恢复按钮状态
```

**示例代码**：
```python
def _on_generate(self):
    # 1. 禁用按钮
    self._generate_btn.configure(state="disabled")
    
    # 2. 显示加载状态
    self._status_label.configure(text="生成中...")
    
    # 3. 后台线程执行
    def task():
        result = generate_content()
        # 4. 主线程回调
        self.root.after(0, lambda: self._on_generate_complete(result))
    
    threading.Thread(target=task, daemon=True).start()

def _on_generate_complete(self, result):
    # 5. 恢复状态
    self._generate_btn.configure(state="normal")
    self._status_label.configure(text="生成完成")
```

---

## 七、动效规范

### 7.1 过渡动画

| 动画类型 | 持续时间 | 缓动函数 |
|---------|---------|---------|
| 按钮状态切换 | 150ms | ease-out |
| 页面切换 | 200ms | ease-in-out |
| 边框发光 | 300ms | ease-in-out |
| 进度条填充 | 500ms | linear |

### 7.2 发光效果

**边框发光**：
- 颜色：科技蓝（60% opacity）
- 模糊半径：4px
- 扩散半径：0px
- 偏移：(0, 0)

**实现方式**：
```python
# Windows平台使用Acrylic效果
from ctypes import windll

hwnd = windll.user32.GetParent(root.winfo_id())
accent_state = 4  # ACCENT_ENABLE_ACRYLICBLURBEHIND
accent_color = 0x99000000 | (0x1E1E1E << 32)  # 带透明度的玻璃黑
```

---

## 八、图标规范

### 8.1 图标风格

- **风格**：线性图标（Line Icons）
- **粗细**：2px
- **颜色**：单色，继承父元素颜色
- **大小**：
  - 导航图标：24×24px
  - 按钮图标：16×16px
  - 状态图标：12×12px

### 8.2 常用图标

| 功能 | Unicode | 图标 |
|------|---------|------|
| 热榜 | ☀ | 📊 |
| 工作台 | ⚙ | 🛠 |
| 进度 | ⏱ | 📈 |
| 项目 | 📁 | 📂 |
| 插件 | 🔌 | 🧩 |
| 设置 | ⚙ | ⚙ |

### 8.3 图标实现

**Unicode图标**：
```python
label = tk.Label(parent, text="📊", font=("Segoe UI Emoji", 16))
```

**Canvas绘制图标**：
```python
canvas = tk.Canvas(parent, width=24, height=24, bg="#2D2D2D", highlightthickness=0)
# 绘制路径
canvas.create_line(6, 12, 18, 12, fill="#FFFFFF", width=2)
canvas.create_line(12, 6, 12, 18, fill="#FFFFFF", width=2)
```

---

## 九、特殊组件

### 9.1 自定义标题栏

**高度**：40px  
**组件**：
- 标题文字：左对齐，距离左侧60px
- 最小化按钮：右上角，距离右侧60px
- 最大化按钮：右上角，距离右侧35px
- 关闭按钮：右上角，距离右侧10px

**按钮尺寸**：36×26px  
**悬停效果**：背景色变化（#3D3D3D）

**实现代码**：
```python
title_bar = tk.Frame(root, height=40, bg="#1E1E1E")
title_bar.pack(fill="x", side="top")

# 标题
title_label = tk.Label(title_bar, text="Novel Writing Assistant-Agent Pro",
                       bg="#1E1E1E", fg="#FFFFFF", font=("Microsoft YaHei UI", 12, "bold"))
title_label.pack(side="left", padx=(60, 0), pady=8)

# 按钮绘制（Canvas方式）
close_btn = tk.Canvas(title_bar, width=36, height=26, bg="#1E1E1E", highlightthickness=0)
close_btn.pack(side="right", padx=10, pady=7)
close_btn.create_text(18, 13, text="✕", fill="#FFFFFF", font=("Segoe UI", 10))
```

### 9.2 毛玻璃效果

**Windows平台**：
- Acrylic效果（Windows 10 1803+）
- 透明度：40%
- 模糊半径：20px

**实现方式**：
```python
from ctypes import windll, byref, sizeof
from ctypes.wintypes import HWND, DWORD

class ACCENT_POLICY(Structure):
    _fields_ = [
        ("AccentState", DWORD),
        ("AccentFlags", DWORD),
        ("GradientColor", DWORD),
        ("AnimationId", DWORD),
    ]

# 启用Acrylic效果
hwnd = windll.user32.GetParent(root.winfo_id())
accent = ACCENT_POLICY(4, 0, 0x99000000 | (0x1E1E1E << 32), 0)
windll.user32.SetWindowCompositionAttribute(hwnd, byref(accent))
```

### 9.3 无边框窗口

**实现方式**：
```python
# 完全移除系统边框
root.overrideredirect(True)

# 通过Windows API保留调整大小功能
style = windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
style |= WS_THICKFRAME  # 保留调整边框
windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
```

**ResizeGrip实现**：
- 8像素边框感知区域
- 支持8个方向调整：上、下、左、右、左上、右上、左下、右下
- 自动切换光标：↔ ↕ ↖ ↗ ↙ ↘

---

## 十、响应式设计

### 10.1 窗口尺寸

- **最小窗口**：1000×700px
- **默认窗口**：1200×800px
- **最大窗口**：无限制（全屏支持）

### 10.2 布局适配

**宽屏（宽度≥1400px）**：
- 工作台按钮：2行4列
- 卡片布局：左右分栏

**标准屏（1000px≤宽度<1400px）**：
- 工作台按钮：3行3列
- 卡片布局：上下分栏

### 10.3 字体缩放

**实现方式**：
```python
# 设置页面：字体大小配置
font_scale = config.get("ui.font_scale", 1.0)
base_size = 10
actual_size = int(base_size * font_scale)

# 应用字体
style = ttk.Style()
style.configure("TLabel", font=("Microsoft YaHei UI", actual_size))
```

---

## 十一、无障碍设计

### 11.1 键盘导航

**快捷键**：
- Ctrl+W：工作台
- Ctrl+P：项目管理
- Ctrl+S：设置
- Ctrl+G：快速生成
- Ctrl+N：新建项目
- Ctrl+O：打开项目
- Ctrl+B：备份项目
- F5：刷新
- Escape：取消

### 11.2 焦点管理

**Tab键顺序**：
1. 侧边栏导航按钮
2. 主内容区输入框
3. 主内容区按钮
4. 状态栏元素

**焦点高亮**：
- 边框：科技蓝发光
- 粗细：2px

### 11.3 屏幕阅读器支持

**标签规范**：
- 所有输入框必须有label属性
- 按钮必须有text属性
- 图标必须有tooltip提示

---

## 十二、性能优化

### 12.1 延迟加载

**页面缓存机制**：
```python
class MainWindow:
    def __init__(self):
        self._pages = {}  # 页面缓存字典
    
    def switch_page(self, page_name):
        # 检查缓存
        if page_name not in self._pages:
            # 首次创建
            self._pages[page_name] = self._create_page(page_name)
        
        # 显示页面
        self._show_page(self._pages[page_name])
```

### 12.2 虚拟滚动

**大数据列表优化**：
- 只渲染可见项
- 滚动时动态加载
- 最大缓存项数：100

### 12.3 异步更新

**UI更新规则**：
- 后台线程执行耗时操作
- 通过 `root.after(0, callback)` 调度UI更新
- 避免阻塞主线程

---

## 十三、主题切换

### 13.1 深色主题（默认）

```python
theme = {
    "bg": "#1E1E1E",
    "fg": "#FFFFFF",
    "surface": "#2D2D2D",
    "accent": "#0078D4",
    "border": "#3D3D3D"
}
```

### 13.2 浅色主题（可选）

```python
theme = {
    "bg": "#FFFFFF",
    "fg": "#1E1E1E",
    "surface": "#F5F5F5",
    "accent": "#0078D4",
    "border": "#E0E0E0"
}
```

### 13.3 主题切换实现

```python
def apply_theme(theme_name):
    if theme_name == "dark":
        GlassTheme.update(DARK_THEME)
    else:
        GlassTheme.update(LIGHT_THEME)
    
    # 重新应用样式
    apply_styles()
    
    # 刷新所有页面
    for page in self._pages.values():
        page.refresh_theme()
```

---

## 十四、设计检查清单

### 14.1 新功能开发前

- [ ] 确认设计风格与现有UI一致
- [ ] 使用标准组件（ResponsiveButton、Canvas滚动容器等）
- [ ] 遵循间距规范（padx=5, pady=5）
- [ ] 遵循色彩规范（主色调、背景层次）
- [ ] 实现响应式布局（不同窗口尺寸适配）

### 14.2 开发过程中

- [ ] 所有UI操作在主线程执行
- [ ] 耗时操作异步执行
- [ ] 按钮添加防抖机制
- [ ] 加载状态正确显示
- [ ] 错误处理友好提示

### 14.3 提交代码前

- [ ] 验证窗口缩放功能正常
- [ ] 验证滚动容器功能正常
- [ ] 验证主题切换功能正常
- [ ] 验证快捷键功能正常
- [ ] 验证内存泄漏问题

---

## 十五、设计资源

### 15.1 设计文件

- UI搭建说明：经验文档/4.1UI搭建说明✅️.md
- 最佳UI代码备份：经验文档/0.0✅️最佳UI代码备份.py

### 15.2 参考案例

**完整代码案例库**（见经验文档/4.1UI搭建说明✅️.md）：
1. 完整滚动容器模板
2. 工作台延迟创建机制
3. 页面切换与Canvas宽度更新
4. Treeview列表实现
5. 快捷创作单层滚动
6. 响应式按钮封装
7. 状态栏实现
8. 主窗口初始化

### 15.3 设计工具

- **色彩工具**：ColorZilla、Adobe Color
- **图标资源**：Lucide Icons、Font Awesome
- **原型工具**：Figma、Sketch

---

**最后更新**: 2026-03-26  
**维护者**: 技术文档工程师、前端开发工程师
