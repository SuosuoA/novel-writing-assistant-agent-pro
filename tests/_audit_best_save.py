#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[审计用] 一键保存 = 评分最高内容 验证

需求：不论哪个生成板块、不论用户浏览到哪个版本，一键保存的都是评分最高的内容。
覆盖：
  1. 续写多版本：真跑 GUI 多版本路径（此前缺 request/enumerate dict 两处崩溃 →
     评分从未回填），断言不崩溃 + 各版本 score 被回填（非全 0）+ best 指向最高分。
  2. 一键保存锁定最高分：用户切到浏览低分版本，_get_best_continue_version_index
     仍返回最高分索引（且不盲信可能被误标的 _best_version_index）。
  3. 开始创作/专家模式：内部迭代 best_result/best_content 已保证输出最高分（源码断言）。
"""
import os
import sys
import time
import threading
import queue
import traceback

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("DEV_MODE", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def log(m=""):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        print(str(m).encode("ascii", "replace").decode(), flush=True)


RESULTS = []


def check(name, ok, ev=""):
    RESULTS.append((name, ok))
    log(f"  [{'OK' if ok else 'X '}] {name} —— {ev}")


# mock LLM：按温度返回不同长度内容（长度差异 → 评分差异，便于验证 argmax）
class _R:
    def __init__(s, t):
        s.success, s.text, s.error = True, t, None
        s.usage = {"total_tokens": len(t)}
        s.content = t


class _Fake:
    def __init__(s):
        s.calls = 0
        s._base = ("雪落无声，沈青梧立于旧楼窗前，指尖灵气流转。"
                   "顾行舟倚门轻笑，两人相视，巷口梆声渐近。")

    def generate_text(s, prompt=None, config=None, messages=None, **kw):
        s.calls += 1
        # 用调用序号制造不同篇幅（模拟版本质量差异）
        mult = 4 + (s.calls % 3) * 3
        return _R(s._base * mult + "\n【本章完】")


import core.ai_service_manager as aim  # noqa: E402
FAKE = _Fake()
aim.get_ai_service_manager = lambda: FAKE

import tkinter as tk  # noqa: E402
from tkinter import messagebox, filedialog  # noqa: E402
for _n in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, _n, lambda *a, **k: None)
filedialog.askopenfilename = lambda **k: ""
filedialog.asksaveasfilename = lambda **k: ""

import gui_main  # noqa: E402
app = gui_main.MainWindow()
app.root.withdraw()

# harness after 编组
UI_Q = queue.Queue()
MAIN_TID = threading.get_ident()
_real_after = app.root.after


def _safe_after(ms, func=None, *a):
    if func is None or threading.get_ident() == MAIN_TID:
        return _real_after(ms, func, *a) if func is not None else _real_after(ms)
    UI_Q.put((func, a))
    return "x"


app.root.after = _safe_after


def _drain():
    try:
        while True:
            fn, a = UI_Q.get_nowait()
            try:
                fn(*a)
            except Exception as e:
                log(f"[queue-exc] {e}")
    except queue.Empty:
        pass


def pump_until(cond, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        _drain()
        try:
            app.root.update()
        except tk.TclError:
            return False
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(0.03)
    return False


def main():
    app._switch_to_page("workbench")
    app._switch_workbench_tab("continue")
    pump_until(lambda: False, 0.5)

    # ---- 1. 续写多版本真跑 ----
    log("\n===== 1. 续写多版本路径（评分回填+选最佳） =====")
    app._continue_source.delete("1.0", "end")
    app._continue_source.insert("1.0", "第一章正文。" * 120)
    # 切多版本模式
    if hasattr(app, "_continue_mode_var"):
        app._continue_mode_var.set("多版本生成")
    app._continue_versions = []
    app._best_version_index = -1
    calls0 = FAKE.calls
    try:
        app._on_continue_generate()
    except Exception as e:
        check("多版本生成不崩溃", False, f"同步异常: {e}")
        traceback.print_exc()

    # 等回填完成（best_index 被设 + 评分非全0），而非仅"版本已append"
    ok = pump_until(
        lambda: len(getattr(app, "_continue_versions", [])) >= 2
        and getattr(app, "_best_version_index", -1) >= 0
        and any((v.get("score", 0) or 0) > 0 for v in app._continue_versions), 90)
    versions = getattr(app, "_continue_versions", [])
    scores = [v.get("score", 0) for v in versions]
    check("多版本生成不崩溃且产出多版本", ok and len(versions) >= 2,
          f"版本数={len(versions)} LLM={FAKE.calls - calls0}")
    check("各版本真实评分已回填（非全0）",
          len(versions) >= 2 and any(isinstance(s, (int, float)) and s > 0 for s in scores),
          f"scores={[round(s, 3) if isinstance(s, (int, float)) else s for s in scores]}")

    # best_index 指向最高分
    if versions:
        argmax = max(range(len(versions)), key=lambda i: scores[i] if isinstance(scores[i], (int, float)) else -1)
        check("_best_version_index 指向最高分版本",
              app._best_version_index == argmax,
              f"best_index={app._best_version_index} argmax={argmax}")

    # ---- 2. 一键保存锁定最高分（用户浏览低分版本） ----
    log("\n===== 2. 一键保存锁定最高分 =====")
    if len(versions) >= 2:
        argmax = max(range(len(versions)), key=lambda i: scores[i] if isinstance(scores[i], (int, float)) else -1)
        # 用户切到浏览一个非最高分版本
        non_best = next((i for i in range(len(versions)) if i != argmax), 0)
        app._current_version_index = non_best
        got = app._get_best_continue_version_index()
        check("浏览非最佳时，保存仍取最高分",
              got == argmax,
              f"浏览={non_best} 保存取={got} argmax={argmax}")
        # 误标 best_index 也不受骗
        app._best_version_index = non_best
        got2 = app._get_best_continue_version_index()
        app._best_version_index = argmax
        check("best_index被误标时仍取真最高分",
              got2 == argmax, f"误标={non_best} 取={got2} argmax={argmax}")

    # ---- 3. 开始创作/专家：内部迭代输出最高分（源码断言） ----
    log("\n===== 3. 开始创作/专家模式输出最高分（源码保证） =====")
    import io
    itr = io.open(os.path.join(ROOT, "plugins", "iterative-generator-v2", "plugin.py"),
                  encoding="utf-8").read()
    exp = io.open(os.path.join(ROOT, "plugins", "expert-novel-v1", "plugin.py"),
                  encoding="utf-8").read()
    check("迭代生成器返回best_result.content",
          "final_content = best_result.content" in itr
          and "if total_score > best_score:" in itr,
          "iterative-generator-v2 按最高分输出")
    check("专家模式返回best_content",
          "best_content = content" in exp and "if current_score > best_score:" in exp,
          "expert-novel-v1 按最高分输出")

    log("\n" + "=" * 56)
    passed = sum(1 for _, ok in RESULTS if ok)
    for name, ok in RESULTS:
        log(f"  [{'OK' if ok else 'X '}] {name}")
    log(f"\n通过 {passed}/{len(RESULTS)}")
    try:
        app.root.destroy()
    except Exception:
        pass
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"[FATAL] {e}")
        traceback.print_exc()
        sys.exit(2)
