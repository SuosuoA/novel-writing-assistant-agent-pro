#!/usr/bin/env python3
"""
临时文件自动清理脚本

功能：
- 清理项目根目录的临时测试文件
- 清理tools目录的临时调试脚本
- 保留必要的启动脚本和正式文件

使用方法：
    python tools/cleanup_temp_files.py
"""

import os
import re
from pathlib import Path
from typing import List, Tuple


def cleanup_temp_files(project_root: Path, dry_run: bool = False) -> Tuple[int, List[str]]:
    """
    清理项目根目录和tools目录的临时文件
    
    Args:
        project_root: 项目根目录
        dry_run: 是否只检查不删除
    
    Returns:
        (清理数量, 清理文件列表)
    """
    # 临时文件模式
    temp_patterns = [
        r'^temp_.*\.py$',
        r'^test_.*\.py$',
        r'^.*_test\.py$',
        r'^check_.*\.py$',
        r'^verify_.*\.py$',
        r'^fix_.*\.py$',
        r'^quick_.*\.py$',
        r'^clear_.*\.py$',
        r'^debug_.*\.py$',
        r'^find_.*\.py$',
        r'^temp_.*\.(txt|json|log)$',
        r'^test_output.*\.txt$',
        r'^test_result.*\.json$',
    ]
    
    # 排除列表
    exclude_files = {
        '一键启动.bat',
        'Novel Writing Assistant-Agent Pro启动.bat'
    }
    
    cleaned = []
    
    # 1. 清理项目根目录
    print("=" * 60)
    print("清理项目根目录临时文件")
    print("=" * 60)
    
    root_files = list(project_root.glob('*'))
    for file in root_files:
        if file.is_file() and file.name not in exclude_files:
            for pattern in temp_patterns:
                if re.match(pattern, file.name):
                    if dry_run:
                        print(f"[DRY-RUN] 将删除: {file.name}")
                        cleaned.append(file.name)
                    else:
                        try:
                            file.unlink()
                            print(f"✓ 已删除: {file.name}")
                            cleaned.append(file.name)
                        except Exception as e:
                            print(f"✗ 删除失败 {file.name}: {e}")
                    break
    
    # 2. 清理tools目录
    print("\n" + "=" * 60)
    print("清理tools目录临时文件")
    print("=" * 60)
    
    tools_dir = project_root / "tools"
    if tools_dir.exists():
        tools_files = list(tools_dir.glob('*'))
        for file in tools_files:
            if file.is_file():
                for pattern in temp_patterns:
                    if re.match(pattern, file.name):
                        if dry_run:
                            print(f"[DRY-RUN] 将删除: tools/{file.name}")
                            cleaned.append(f"tools/{file.name}")
                        else:
                            try:
                                file.unlink()
                                print(f"✓ 已删除: tools/{file.name}")
                                cleaned.append(f"tools/{file.name}")
                            except Exception as e:
                                print(f"✗ 删除失败 tools/{file.name}: {e}")
                        break
    
    # 3. 清理tests目录（保留正式测试文件）
    # 不清理tests/目录，保留正式测试
    
    print("\n" + "=" * 60)
    print(f"清理完成：共清理 {len(cleaned)} 个临时文件")
    print("=" * 60)
    
    return len(cleaned), cleaned


def main():
    """主函数"""
    import sys
    
    # 修复Windows控制台编码
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
    
    # 项目根目录
    project_root = Path(__file__).parent.parent
    
    print(f"项目根目录: {project_root}")
    print()
    
    # 检查是否有--dry-run参数
    dry_run = '--dry-run' in sys.argv or '-n' in sys.argv
    
    if dry_run:
        print("[DRY-RUN 模式] 只检查不删除")
        print()
    
    # 执行清理
    count, files = cleanup_temp_files(project_root, dry_run)
    
    if dry_run and count > 0:
        print("\n提示：运行 'python tools/cleanup_temp_files.py' 执行实际清理")
    
    return 0


if __name__ == '__main__':
    exit(main())
