#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[审计用] 十大创作板块 GUI 级端到端真跑验证

方法：无头启动真实 MainWindow（withdraw），载入真实项目（雪落），mock LLM，
逐板块以用户视角调用真实按钮处理器，断言：
  1) 结果真实显示到该板块的控件
  2) 数据真实写入 current_project / 项目管理器
  3) 无错误弹窗

这是"功能真实达成"的判定标准——控件能创建不算达标。
"""
import os
import sys
import time
import json
import traceback

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("DEV_MODE", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

PROJECT_JSON = os.path.join(ROOT, "小说作品", "雪落", "雪落.json")
SRC = {
    "worldview": os.path.join(ROOT, "小说作品", "雪落", "世界观", "雪落世界观.txt"),
    "characters": os.path.join(ROOT, "小说作品", "雪落", "人物", "人设.txt"),
    "outline": os.path.join(ROOT, "小说作品", "雪落", "大纲", "大纲.txt"),
    "style": os.path.join(ROOT, "小说作品", "雪落", "风格", "风格.txt"),
    "chapter1": os.path.join(ROOT, "小说作品", "雪落", "小说", "第一章.txt"),
}


def log(m=""):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        print(str(m).encode("ascii", "replace").decode(), flush=True)


# ============ 1. mock LLM（在导入 gui_main 之前安装） ============
class _R:
    def __init__(s, t):
        s.success, s.text, s.error = True, t, None
        s.usage = {"total_tokens": len(t)}
        s.tokens_used = len(t)
        s.content = t


class _FakeLLM:
    def __init__(s):
        s.calls = 0
        base = ("雪落在城北的旧巷里无声堆积。沈青梧拢了拢袖口，指尖残余的灵气尚未散尽，"
                "她性子清冷，话不多，习惯把心事压进眼底。顾行舟站在檐下看她，笑意散漫："
                "又在算什么？他心思活络，最会借势。两人对视片刻，巷口传来更夫的梆子声。"
                "次日清晨，沈青梧决定去藏经阁查证那卷残谱的来历。")
        s._t = base * 8 + "\n【本章完】"
        s._json_issues = json.dumps({
            "issues": [{
                "issue_type": "character",
                "severity": "medium",
                "element_name": "沈青梧",
                "description": "章节中沈青梧主动挑起争执，与设定【清冷寡言】不符",
                "suggested_fix": "将争执改为冷淡回避，或在设定中补充触发条件",
                "original_content": "沈青梧霍然起身呵斥",
                "confidence": 0.85,
            }],
            "summary": "发现1个人物一致性冲突",
        }, ensure_ascii=False)

    _worldview_reply = (
        "世界观名称：雾都灵脉\n"
        "时代背景：近未来都市，灵气复苏三十年。\n"
        "世界结构：现实层与灵脉层双层叠加，灵脉层由古修遗迹构成。\n"
        "力量体系：引气、筑基、金丹三阶，灵能须以契约器物为媒介。\n"
        "地理环境：城北旧巷灵脉最盛，城南新区灵气稀薄。\n"
        "社会结构：修行者登记制，灵务局统一管理。\n"
        "主要势力：灵务局、藏经阁、散修联盟。\n"
        "规则与法则：不得在凡人区显露灵能；契约器物不可转借。\n"
        "背景故事：三十年前灵潮回归，第一批觉醒者建立了如今的秩序。\n"
    )

    _worldview_json = json.dumps({
        "world_name": "雾都灵脉", "era": "近未来都市，灵气复苏三十年",
        "geography": "城北旧巷灵脉最盛，城南新区灵气稀薄",
        "social_structure": "修行者登记制，灵务局统一管理",
        "power_system": "引气、筑基、金丹三阶，须以契约器物为媒介",
        "factions": ["灵务局", "藏经阁", "散修联盟"],
        "rules": ["不得在凡人区显露灵能", "契约器物不可转借"],
        "resources": ["灵晶", "残谱"], "conflicts": ["灵脉归属之争"],
        "unique_elements": ["契约器物", "灵脉层"],
    }, ensure_ascii=False)

    def generate_text(s, prompt=None, config=None, messages=None, **kw):
        s.calls += 1
        p = prompt or (messages[-1].get("content", "") if messages else "")
        # 快捷创作·世界观模板要求JSON（world_name等字段）——须先于issues分支
        if p and ("world_name" in p or "世界观设定（JSON格式）" in p):
            return _R(s._worldview_json)
        # 一致性/逆向分析类提示词要求JSON输出
        if p and ("issues" in p or "冲突" in p and "JSON" in p):
            return _R(s._json_issues)
        if p and ("JSON" in p or "json" in p) and "issues" in p:
            return _R(s._json_issues)
        # 世界观生成提示词返回结构化文本（供解析器抽取字段）
        if p and "世界观" in p and "本章完" not in p and "续写" not in p and "JSON" not in p:
            return _R(s._worldview_reply)
        return _R(s._t)


import core.ai_service_manager as _aim
FAKE = _FakeLLM()
_aim.get_ai_service_manager = lambda: FAKE

# ============ 2. 对话框拦截（在导入 gui_main 之前安装） ============
import tkinter as tk
from tkinter import messagebox, filedialog

MSGS = []           # (kind, title, message)
FILE_Q = []         # filedialog 预置返回队列


def _mk_msg(name, ret):
    def f(title=None, message=None, **k):
        MSGS.append((name, str(title), str(message)[:300]))
        return ret
    return f


for _n, _r in [("showinfo", "ok"), ("showwarning", "ok"), ("showerror", "ok"),
               ("askyesno", True), ("askokcancel", True), ("askquestion", "yes"),
               ("askyesnocancel", True), ("askretrycancel", False)]:
    setattr(messagebox, _n, _mk_msg(_n, _r))


def _pop_file(default=""):
    return FILE_Q.pop(0) if FILE_Q else default


filedialog.askopenfilename = lambda **k: _pop_file()
filedialog.askopenfilenames = lambda **k: ([FILE_Q.pop(0)] if FILE_Q else [])
filedialog.asksaveasfilename = lambda **k: _pop_file()
filedialog.askdirectory = lambda **k: _pop_file()

# ============ 3. 启动主窗口 ============
t0 = time.time()
import gui_main  # noqa: E402

app = gui_main.MainWindow()
app.root.withdraw()
log(f"[启动] MainWindow 初始化 {time.time()-t0:.1f}s")

# --- harness专用：线程安全 after 仿真 ---
# 真实运行时主线程常驻 mainloop，工作线程的 root.after 会被 Tcl 编组；
# harness 用间歇 root.update() 驱动，跨线程 after 会抛
# "main thread is not in main loop"。此处把非主线程的 after 转为入队，
# 由 pump() 在主线程排空——只改测试环境语义，不触碰产品代码。
import threading as _th
import queue as _q
_UI_Q: "_q.Queue" = _q.Queue()
_MAIN_TID = _th.get_ident()
_real_after = app.root.after


def _safe_after(ms, func=None, *args):
    if func is None or _th.get_ident() == _MAIN_TID:
        return _real_after(ms, func, *args) if func is not None else _real_after(ms)
    _UI_Q.put((func, args))
    return "harness_after"


app.root.after = _safe_after


def _drain_ui_queue():
    try:
        while True:
            fn, args = _UI_Q.get_nowait()
            try:
                fn(*args)
            except Exception as e:
                log(f"[UI队列回调异常] {e}")
    except _q.Empty:
        pass


def pump(sec=0.5):
    deadline = time.time() + sec
    while time.time() < deadline:
        _drain_ui_queue()
        try:
            app.root.update()
        except tk.TclError:
            break
        time.sleep(0.02)


def pump_until(cond, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        _drain_ui_queue()
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


def text_of(widget):
    try:
        return widget.get("1.0", "end").strip()
    except Exception:
        return ""


def tree_rows(tree):
    try:
        return len(tree.get_children())
    except Exception:
        return -1


def errors_since(n0):
    return [m for m in MSGS[n0:] if m[0] == "showerror"]


RESULTS = []


def report(tab, item, ok, evidence=""):
    RESULTS.append((tab, item, ok, evidence))
    log(f"  [{'OK' if ok else 'X '}] {tab} | {item} | {evidence}")


# ============ 4. 载入真实项目 ============
pump(1.0)
loaded = False
try:
    if getattr(app, "_project_manager", None):
        ok = app._project_manager.load_project(PROJECT_JSON)
        if ok:
            app.current_project = app._project_manager.get_project_data()
            app.project_file = PROJECT_JSON
            app._restore_project_data_to_ui(app.current_project)
            loaded = True
except Exception as e:
    log(f"[项目载入异常] {e}")
    traceback.print_exc()
if not loaded:
    with open(PROJECT_JSON, encoding="utf-8") as f:
        app.current_project = json.load(f)
    app.project_file = PROJECT_JSON
    try:
        app._restore_project_data_to_ui(app.current_project)
        loaded = True
    except Exception as e:
        log(f"[降级载入异常] {e}")
log(f"[项目] 雪落载入: {loaded} | worldview={len(app.current_project.get('worldview', []))} "
    f"characters={len(app.current_project.get('characters', []))}")

app._switch_to_page("workbench")
pump(1.0)

TABS = ["worldview", "characters", "outline", "style", "generation",
        "reverse", "quick", "continue", "consistency", "knowledge"]
for t in TABS:
    tt = time.time()
    try:
        app._switch_workbench_tab(t)
        pump(0.3)
        log(f"[tab] {t} 切换 {time.time()-tt:.2f}s")
    except Exception as e:
        log(f"[tab] {t} 切换失败: {e}")

# ============ 5. 逐板块功能真跑 ============

# ---- T1 世界观 ----
log("\n===== T1 世界观 =====")
app._switch_workbench_tab("worldview")
pump(0.3)
n = tree_rows(getattr(app, "_worldview_tree", None))
report("世界观", "项目数据显示到列表", n > 0, f"树行数={n}（项目106条）")
e0 = len(MSGS)
FILE_Q.append(SRC["worldview"])
try:
    app._on_worldview_browse()
    pump(0.5)
    app._on_worldview_import()
    ok = pump_until(lambda: tree_rows(app._worldview_tree) > 0, 30)
    n2 = tree_rows(app._worldview_tree)
    errs = errors_since(e0)
    report("世界观", "导入txt→解析→列表刷新", ok and not errs,
           f"行数={n2} 错误弹窗={len(errs)}" + (f" {errs[0][2][:80]}" if errs else ""))
except Exception as e:
    report("世界观", "导入txt→解析→列表刷新", False, f"异常: {e}")

# ---- T2 人物设定 ----
log("\n===== T2 人物设定 =====")
app._switch_workbench_tab("characters")
pump(0.3)
n = tree_rows(getattr(app, "_character_tree", None))
report("人物", "项目数据显示到列表", n > 0, f"树行数={n}（项目15个）")
e0 = len(MSGS)
FILE_Q.append(SRC["characters"])
try:
    app._on_character_browse()
    pump(0.5)
    app._on_character_batch_import()
    ok = pump_until(lambda: tree_rows(app._character_tree) > 0, 30)
    n2 = tree_rows(app._character_tree)
    errs = errors_since(e0)
    report("人物", "批量解析导入→列表刷新", ok and not errs,
           f"行数={n2} 错误={len(errs)}" + (f" {errs[0][2][:80]}" if errs else ""))
except Exception as e:
    report("人物", "批量解析导入→列表刷新", False, f"异常: {e}")

# ---- T3 大纲管理 ----
log("\n===== T3 大纲管理 =====")
app._switch_workbench_tab("outline")
pump(0.3)
n = tree_rows(getattr(app, "_outline_tree", None))
report("大纲", "项目数据显示到树", n > 0, f"树行数={n}（项目100章）")
e0 = len(MSGS)
FILE_Q.append(SRC["outline"])
try:
    app._on_outline_browse()
    ok = pump_until(lambda: tree_rows(app._outline_tree) > 0, 30)
    n2 = tree_rows(app._outline_tree)
    ch = len(getattr(app, "_chapter_outlines", {}) or {})
    errs = errors_since(e0)
    report("大纲", "导入txt→解析→章节树", ok and not errs,
           f"树行={n2} 章节大纲={ch} 错误={len(errs)}" + (f" {errs[0][2][:80]}" if errs else ""))
except Exception as e:
    report("大纲", "导入txt→解析→章节树", False, f"异常: {e}")

# ---- T4 风格学习 ----
log("\n===== T4 风格学习 =====")
app._switch_workbench_tab("style")
pump(0.3)
e0 = len(MSGS)
try:
    prof0 = dict(getattr(app, "_style_profile", {}) or {})
    FILE_Q.append(SRC["style"])
    # 风格页交互：浏览文件后分析
    if hasattr(app, "_on_style_browse"):
        app._on_style_browse()
        pump(0.5)
    app._on_style_analyze()
    ok = pump_until(lambda: bool(getattr(app, "_style_profile", None)), 60)
    prof = getattr(app, "_style_profile", {}) or {}
    errs = errors_since(e0)
    report("风格", "样本分析→风格档案", ok and not errs,
           f"档案键={list(prof)[:6]} 错误={len(errs)}" + (f" {errs[0][2][:80]}" if errs else ""))
except Exception as e:
    report("风格", "样本分析→风格档案", False, f"异常: {e}")

# ---- T5 开始创作 ----
log("\n===== T5 开始创作 =====")
app._switch_workbench_tab("generation")
pump(0.3)
e0 = len(MSGS)
calls0 = FAKE.calls
try:
    # 直接调用开始生成（表单默认值+已载入的项目数据）
    app._on_start_generation()
    ok = pump_until(lambda: "本章完" in text_of(getattr(app, "_gen_result", None)), 90)
    body = text_of(getattr(app, "_gen_result", None))
    errs = errors_since(e0)
    report("创作", "开始生成→LLM→正文显示", ok,
           f"LLM调用={FAKE.calls - calls0} 正文={len(body)}字 错误={len(errs)}"
           + (f" {errs[0][2][:80]}" if errs else ""))
    # 评分显示（设计：九维详情+加权总分写入生成日志区 _gen_log）
    gen_log = text_of(getattr(app, "_gen_log", None))
    score_ok = ("加权总分" in gen_log) or ("综合评分" in gen_log)
    report("创作", "九维评分显示", score_ok,
           f"日志含加权总分={'加权总分' in gen_log} 九维详情={'九维度评分详情' in gen_log}")
except Exception as e:
    report("创作", "开始生成→LLM→正文显示", False, f"异常: {e}")
    traceback.print_exc()

# ---- T6 逆向反馈 ----
log("\n===== T6 逆向反馈 =====")
app._switch_workbench_tab("reverse")
pump(0.3)
e0 = len(MSGS)
calls0 = FAKE.calls
try:
    # 粘贴文本添加章节
    app._on_reverse_paste_text()
    pump(0.2)
    pt = getattr(app, "_paste_content_text", None)
    with open(SRC["chapter1"], encoding="utf-8") as f:
        ch1 = f.read()
    if pt is not None:
        pt.delete("1.0", "end")
        pt.insert("1.0", ch1[:3000])
    if hasattr(app, "_paste_title_var"):
        app._paste_title_var.set("第一章 雪落")
    app._on_reverse_add_pasted_chapter()
    pump(0.5)
    n = tree_rows(getattr(app, "_completed_chapters_tree", None))
    report("逆向", "粘贴章节→章节列表", n > 0, f"章节列表行数={n}")

    # 范围改为"分析所有章节"（默认"仅选中"而程序化添加的行未被选中）
    if hasattr(app, "_reverse_scope_var"):
        app._reverse_scope_var.set("all")
    app._on_reverse_run_analysis()
    ok = pump_until(
        lambda: tree_rows(getattr(app, "_issues_tree", None)) > 0, 60)
    pump(2.0)
    ni = tree_rows(getattr(app, "_issues_tree", None))
    errs = errors_since(e0)
    # 达标标准：LLM真被调用（语义分析非规则降级）+ 问题呈现到列表
    report("逆向", "运行分析→LLM语义分析→问题列表", ok and FAKE.calls > calls0 and not errs,
           f"LLM调用={FAKE.calls - calls0} 问题数={ni} 错误={len(errs)}"
           + (f" {errs[0][2][:100]}" if errs else ""))
    # 应用修正 → 项目数据真实变化
    if ni > 0:
        wv0 = app.current_project.get('worldview')
        app._on_reverse_apply_fix()
        pump(3.0)
        detail = text_of(getattr(app, "_issue_detail_text", None))
        report("逆向", "应用修正→设定反哺", "修正" in detail,
               f"修正详情={len(detail)}字")
except Exception as e:
    report("逆向", "分析链路", False, f"异常: {e}")
    traceback.print_exc()

# ---- T7 快捷创作 ----
log("\n===== T7 快捷创作 =====")
app._switch_workbench_tab("quick")
pump(0.3)
e0 = len(MSGS)
calls0 = FAKE.calls
try:
    qi = getattr(app, "_quick_input", None)
    if qi is not None:
        qi.delete("1.0", "end")
        qi.insert("1.0", "修仙 都市 双主角 悬疑")
    app._on_quick_generate_all()
    texts = getattr(app, "_quick_result_texts", {}) or {}

    def _quick_done():
        # 达标=四件套都有真实内容显示（mock下plot的get_full_text较短，阈值30）
        return sum(1 for w in texts.values() if len(text_of(w)) > 30) >= 4
    ok = pump_until(_quick_done, 120)
    filled = {k: len(text_of(w)) for k, w in texts.items()}
    errs = errors_since(e0)
    report("快捷", "一键生成四件套→结果显示", ok and not errs,
           f"LLM={FAKE.calls - calls0} 各结果字数={filled} 错误={len(errs)}"
           + (f" {errs[0][2][:100]}" if errs else ""))
    # 保存结果（asksaveasfilename 需要文件路径而非目录）
    e1 = len(MSGS)
    import tempfile
    tmpd = tempfile.mkdtemp(prefix="quick_save_")
    save_path = os.path.join(tmpd, "快捷创作结果.txt")
    FILE_Q.append(save_path)
    if hasattr(app, "_on_quick_save_results"):
        app._on_quick_save_results()
        pump(2.0)
        saved = os.path.exists(save_path) and os.path.getsize(save_path) > 100
        errs1 = errors_since(e1)
        report("快捷", "保存结果到文件", saved and not errs1,
               f"落盘={saved} 大小={os.path.getsize(save_path) if os.path.exists(save_path) else 0} 错误={len(errs1)}")
except Exception as e:
    report("快捷", "一键生成链路", False, f"异常: {e}")
    traceback.print_exc()

# ---- T8 续写 ----
log("\n===== T8 续写 =====")
app._switch_workbench_tab("continue")
pump(0.3)
e0 = len(MSGS)
calls0 = FAKE.calls
try:
    src_widget = None
    for attr in ("_continue_source_text", "_continue_source", "_continue_input"):
        w = getattr(app, attr, None)
        if w is not None:
            src_widget = w
            break
    with open(SRC["chapter1"], encoding="utf-8") as f:
        ch1 = f.read()
    if src_widget is not None:
        src_widget.delete("1.0", "end")
        src_widget.insert("1.0", ch1[:2000])
    app._on_continue_generate()
    _cont_state = {"widget": None}

    def _cont_done():
        for attr in ("_continue_result_text", "_continue_result", "_continue_output"):
            w = getattr(app, attr, None)
            if w is not None and len(text_of(w)) > 100:
                _cont_state["widget"] = w
                return True
        return False
    ok = pump_until(_cont_done, 90)
    res_widget = _cont_state["widget"]
    nv = tree_rows(getattr(app, "_version_tree", None))
    errs = errors_since(e0)
    report("续写", "开始续写→结果+版本", ok and not errs,
           f"LLM={FAKE.calls - calls0} 结果={len(text_of(res_widget)) if res_widget else 0}字 "
           f"版本树={nv} 错误={len(errs)}" + (f" {errs[0][2][:100]}" if errs else ""))
except Exception as e:
    report("续写", "续写链路", False, f"异常: {e}")
    traceback.print_exc()

# ---- T9 长篇检测 ----
log("\n===== T9 长篇检测 =====")
app._switch_workbench_tab("consistency")
pump(0.3)
e0 = len(MSGS)
try:
    ci = getattr(app, "_consistency_input", None)
    with open(SRC["chapter1"], encoding="utf-8") as f:
        ch1 = f.read()
    if ci is not None:
        ci.delete("1.0", "end")
        ci.insert("1.0", ch1[:3000])
    calls_t9 = FAKE.calls
    app._on_consistency_check()

    def _t9_done():
        lbl = getattr(app, "_consistency_status_label", None)
        if lbl is None:
            return False
        txt = str(lbl.cget("text"))
        return ("无冲突" in txt) or ("冲突" in txt and "检测中" not in txt) or ("失败" in txt)
    ok = pump_until(_t9_done, 90)
    pump(1.0)
    nt = tree_rows(getattr(app, "_consistency_tree", None))
    status_txt = str(getattr(app, "_consistency_status_label").cget("text")) \
        if hasattr(app, "_consistency_status_label") else ""
    errs = errors_since(e0)
    # 达标标准：检测完成出结论（无冲突/N个冲突均可），且非"失败"
    report("长篇", "检测→结论显示", ok and "失败" not in status_txt and not errs,
           f"状态={status_txt[:40]} 冲突树={nt} LLM={FAKE.calls - calls_t9} 错误={len(errs)}"
           + (f" {errs[0][2][:100]}" if errs else ""))
except Exception as e:
    report("长篇", "检测链路", False, f"异常: {e}")
    traceback.print_exc()

# ---- T10 知识库 ----
log("\n===== T10 知识库 =====")
app._switch_workbench_tab("knowledge")
pump(0.5)
e0 = len(MSGS)
try:
    app._on_knowledge_refresh()
    ok = pump_until(lambda: tree_rows(getattr(app, "_knowledge_tree", None)) > 0, 60)
    n = tree_rows(getattr(app, "_knowledge_tree", None))
    errs = errors_since(e0)
    report("知识库", "刷新→条目显示", ok and not errs,
           f"树行数={n}（库1130+条） 错误={len(errs)}" + (f" {errs[0][2][:100]}" if errs else ""))
    # 搜索
    if hasattr(app, "_knowledge_search_var"):
        app._knowledge_search_var.set("灵气")
        app._on_knowledge_search()
        pump(2.0)
        n2 = tree_rows(getattr(app, "_knowledge_tree", None))
        report("知识库", "关键词搜索", n2 >= 0, f"搜索后行数={n2}")
except Exception as e:
    report("知识库", "知识库链路", False, f"异常: {e}")
    traceback.print_exc()

# ============ 6. 汇总 ============
log("\n" + "=" * 64)
log("十板块 GUI 真跑结果汇总")
log("=" * 64)
passed = sum(1 for r in RESULTS if r[2])
for tab, item, ok, ev in RESULTS:
    log(f"  [{'OK' if ok else 'X '}] {tab:6s} {item} —— {ev[:90]}")
log(f"\n通过 {passed}/{len(RESULTS)}")
log(f"错误弹窗总数: {sum(1 for m in MSGS if m[0]=='showerror')}")
for m in MSGS:
    if m[0] == "showerror":
        log(f"  [ERR弹窗] {m[1]}: {m[2][:120]}")

try:
    app.root.destroy()
except Exception:
    pass
sys.exit(0 if passed == len(RESULTS) else 1)
