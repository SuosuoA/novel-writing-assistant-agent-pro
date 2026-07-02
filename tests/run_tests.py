"""运行 tests/ 下全部测试脚本并汇总结果

V2.2修复（2026-07-03）：tests/test_*.py 是历史自执行脚本
（import 即运行、部分无 __main__ 守卫、跑完 sys.exit），不是 pytest 风格测试——
pytest 收集时会因脚本顶层 sys.exit / 关闭流而崩溃且收集到 0 项。
改为按脚本设计方式逐个子进程执行，按退出码汇总（0=通过）。

用法: python tests/run_tests.py [脚本名过滤子串]
"""

import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_TIMEOUT_SECONDS = 180

# 需要人工操作的GUI验证脚本（tk.mainloop阻塞），不适合自动化——
# 显式SKIP并给出原因，而非跑到超时误报
INTERACTIVE_SCRIPTS = {
    "test_data_load_fix.py": "手动GUI验证工具（tk.mainloop），需人工操作",
}


def _build_env() -> dict:
    env = dict(os.environ)
    # 离线运行，避免测试期间触发 HuggingFace 网络请求卡住
    env.setdefault("HF_HUB_OFFLINE", "1")
    env.setdefault("TRANSFORMERS_OFFLINE", "1")
    env.setdefault("DEV_MODE", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def run_script(script: Path, env: dict) -> tuple:
    """运行单个测试脚本，返回 (状态, 耗时秒, 摘要)"""
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=SCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT", time.time() - start, f">{SCRIPT_TIMEOUT_SECONDS}s"

    elapsed = time.time() - start
    if result.returncode == 0:
        return "PASS", elapsed, ""

    # 失败时取输出末尾片段作摘要
    tail = (result.stderr or result.stdout or "").strip().splitlines()
    summary = tail[-1][:120] if tail else f"exit={result.returncode}"
    return "FAIL", elapsed, summary


def main() -> int:
    name_filter = sys.argv[1] if len(sys.argv) > 1 else ""
    scripts = sorted(
        s for s in (PROJECT_ROOT / "tests").glob("test_*.py")
        if name_filter in s.name
    )
    if not scripts:
        print(f"未找到匹配的测试脚本: {name_filter}")
        return 1

    env = _build_env()
    results = []
    for script in scripts:
        if script.name in INTERACTIVE_SCRIPTS:
            results.append((script.name, "SKIP", 0.0, INTERACTIVE_SCRIPTS[script.name]))
            print(f"[-] {script.name:45s} SKIP       0.0s  {INTERACTIVE_SCRIPTS[script.name]}",
                  flush=True)
            continue
        status, elapsed, summary = run_script(script, env)
        results.append((script.name, status, elapsed, summary))
        marker = {"PASS": "[OK]", "FAIL": "[X]", "TIMEOUT": "[T]"}[status]
        line = f"{marker} {script.name:45s} {status:7s} {elapsed:6.1f}s"
        if summary:
            line += f"  {summary}"
        print(line, flush=True)

    passed = sum(1 for r in results if r[1] == "PASS")
    skipped = sum(1 for r in results if r[1] == "SKIP")
    failed = [r for r in results if r[1] not in ("PASS", "SKIP")]
    print(f"\n===== 汇总: {passed}/{len(results)} 通过"
          f"{f'（跳过{skipped}个交互脚本）' if skipped else ''} =====")
    for name, status, _, summary in failed:
        print(f"  {status}: {name}  {summary}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
