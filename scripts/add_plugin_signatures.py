#!/usr/bin/env python3
"""为所有插件添加签名"""

import hashlib
import json
from pathlib import Path


def calculate_directory_hash(directory: Path) -> str:
    """计算目录的SHA256哈希"""
    hasher = hashlib.sha256()
    file_count = 0
    max_traversal_depth = 20
    max_file_size = 10 * 1024 * 1024  # 10MB
    max_total_size = 100 * 1024 * 1024  # 100MB
    total_size = 0
    
    def safe_walk(current_dir: Path, depth: int = 0):
        nonlocal file_count, total_size
        
        if depth > max_traversal_depth:
            return
        
        try:
            for item in current_dir.iterdir():
                # 跳过__pycache__目录
                if item.name == '__pycache__':
                    continue
                
                try:
                    if item.is_symlink():
                        continue
                    
                    if item.is_dir():
                        resolved = item.resolve()
                        try:
                            resolved.relative_to(directory.resolve())
                        except ValueError:
                            continue
                        safe_walk(item, depth + 1)
                    elif item.is_file():
                        if item.suffix == '.pyc':
                            continue
                        
                        file_size = item.stat().st_size
                        if file_size > max_file_size:
                            continue
                        
                        total_size += file_size
                        if total_size > max_total_size:
                            return
                        
                        try:
                            with open(item, 'rb') as f:
                                hasher.update(f.read())
                                file_count += 1
                        except Exception:
                            continue
                except OSError:
                    continue
        except Exception:
            pass
    
    safe_walk(directory)
    return hasher.hexdigest()


def main():
    # 处理所有插件（plugins在项目根目录）
    plugins_dir = Path(__file__).parent.parent / 'plugins'
    results = []
    
    for plugin_dir in sorted(plugins_dir.iterdir()):
        if plugin_dir.is_dir() and not plugin_dir.name.startswith('__'):
            plugin_json = plugin_dir / 'plugin.json'
            if plugin_json.exists():
                try:
                    # 读取plugin.json
                    with open(plugin_json, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 计算签名
                    signature = calculate_directory_hash(plugin_dir)
                    
                    # 添加签名
                    data['signature'] = signature
                    
                    # 保存
                    with open(plugin_json, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    results.append(f'[OK] {plugin_dir.name}: {signature[:16]}...')
                except Exception as e:
                    results.append(f'[FAIL] {plugin_dir.name}: {e}')
    
    print('\n'.join(results))


if __name__ == '__main__':
    main()
