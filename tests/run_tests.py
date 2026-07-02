"""运行单元测试并生成覆盖率报告

V2.1修复：原先硬编码运行不存在的 tests/test_core_modules.py（永远失败）。
改为运行 tests/ 目录下全部 test_*.py，并使用项目根目录的相对路径
（不再硬编码绝对盘符路径，便于迁移）。
"""

import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_tests():
    """运行测试"""
    env = dict(os.environ)
    # 离线运行，避免测试期间触发 HuggingFace 网络请求卡住
    env.setdefault("HF_HUB_OFFLINE", "1")
    env.setdefault("TRANSFORMERS_OFFLINE", "1")
    env.setdefault("DEV_MODE", "1")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "-v",
            "--tb=short",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )

    print("STDOUT:")
    print(result.stdout)
    print("\nSTDERR:")
    print(result.stderr)
    print("\nReturn Code:", result.returncode)

    return result.returncode


if __name__ == "__main__":
    sys.exit(run_tests())
