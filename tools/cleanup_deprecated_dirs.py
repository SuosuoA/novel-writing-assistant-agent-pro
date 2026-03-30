"""
清理失效目录和缓存
删除：
1. 空目录（无文件的目录）
2. Python缓存（__pycache__）
3. 测试缓存（.pytest_cache）
"""

import shutil
from pathlib import Path

def main():
    project_root = Path(__file__).parent.parent
    
    print("=" * 80)
    print("清理失效目录和缓存")
    print("=" * 80)
    
    # 要删除的空目录列表
    empty_dirs = [
        "data/vector_store",
        ".benchmarks",
        "Qwen/offload",
        "sentence_transformers_cache/.locks",
        "经验文档/12-13打包、分发与自动更新评审结果",
        "经验文档/14-15测试、优化与发布评审结果",
        "经验文档/会议纪要"
    ]
    
    print("\n[STEP 1] 删除空目录")
    deleted_count = 0
    for dir_path in empty_dirs:
        full_path = project_root / dir_path
        if full_path.exists():
            try:
                if full_path.is_dir() and not any(full_path.iterdir()):
                    full_path.rmdir()
                    print(f"  [DELETE] {dir_path}")
                    deleted_count += 1
                elif full_path.is_dir() and any(full_path.iterdir()):
                    print(f"  [SKIP] {dir_path} (非空目录)")
            except Exception as e:
                print(f"  [ERROR] {dir_path}: {e}")
        else:
            print(f"  [NOT FOUND] {dir_path}")
    
    print(f"\n删除空目录: {deleted_count}个")
    
    # 删除所有__pycache__目录
    print("\n[STEP 2] 清理Python缓存")
    pycache_count = 0
    for pycache in project_root.rglob("__pycache__"):
        try:
            shutil.rmtree(pycache)
            print(f"  [DELETE] {pycache.relative_to(project_root)}")
            pycache_count += 1
        except Exception as e:
            print(f"  [ERROR] {pycache.relative_to(project_root)}: {e}")
    
    print(f"\n删除__pycache__: {pycache_count}个")
    
    # 删除.pytest_cache
    print("\n[STEP 3] 清理pytest缓存")
    pytest_cache = project_root / ".pytest_cache"
    if pytest_cache.exists():
        try:
            shutil.rmtree(pytest_cache)
            print(f"  [DELETE] .pytest_cache")
        except Exception as e:
            print(f"  [ERROR] .pytest_cache: {e}")
    
    print("\n" + "=" * 80)
    print(f"清理完成！共删除 {deleted_count + pycache_count + 1} 个目录")
    print("=" * 80)
    
    # 验证data目录状态
    print("\n[验证] data目录状态:")
    data_dir = project_root / "data"
    for subdir in data_dir.iterdir():
        if subdir.is_dir():
            file_count = len(list(subdir.rglob("*")))
            print(f"  {subdir.name}: {file_count} 个文件")

if __name__ == "__main__":
    main()
