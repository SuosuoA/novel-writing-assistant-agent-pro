#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试GUI启动"""

import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

print("测试1: 导入gui_main...")
try:
    import gui_main
    print("✅ 导入成功")
except Exception as e:
    print(f"✗ 导入失败: {e}")
    sys.exit(1)

print("\n测试2: 创建主窗口...")
try:
    root = tk.Tk()
    app = gui_main.MainWindow(root)
    print("✅ 主窗口创建成功")
except Exception as e:
    print(f"✗ 创建失败: {e}")
    sys.exit(1)

print("\n测试完成! 启动UI界面...")
root.mainloop()
