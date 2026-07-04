#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《无极》全候选选优归档：把历轮产生的所有章节候选逐章评分取最大

候选来源（流程日志/）：phase9final_第N章.txt、best_第N章_*.txt、
baseline_第N章.txt、当前项目版本、小说/第N章.txt。
顺序贪心：先定第1章最优→写入项目→再评第2章候选（保证前章上下文口径）。
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("DEV_MODE", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

PROJ = Path("小说作品/无极")
LOG = PROJ / "流程日志"
TARGET_WORDS = 2000


def main():
    import importlib
    from core.plugin_interface import PluginContext
    from services.project_manager import ProjectManager

    qv_mod = importlib.import_module("plugins.quality-validator-v1.plugin")
    v = qv_mod.QualityValidatorPlugin()
    v.initialize(PluginContext(event_bus=None, service_locator=None,
                               config_manager=None, plugin_registry=None))

    pm = ProjectManager(event_bus=None)
    pm.load_project(str(PROJ / "无极.json"))
    pd = pm.get_project_data()
    wv = pd.get("worldview") or ""
    if not isinstance(wv, str):
        wv = json.dumps(wv, ensure_ascii=False)
    outline = pm.get_outline() or ""
    style = pd.get("style") or {}
    chars = pm.get_characters() or []

    def score(text):
        r = v.validate_with_weights(
            text=text, target_word_count=TARGET_WORDS, chapter_outline=outline,
            style_profile=style, character_profiles=chars, world_view=wv,
            knowledge_categories=["xuanhuan"])
        return float(r.total_weighted_score)

    def candidates(no):
        title = f"第{no}章"
        cands = {}
        cur = pm.get_chapter_content(title)
        if cur:
            cands["project"] = cur
        for pat in (f"phase9final_{title}.txt", f"baseline_{title}.txt"):
            p = LOG / pat
            if p.exists():
                cands[pat] = p.read_text(encoding="utf-8")
        for p in sorted(LOG.glob(f"best_{title}_*.txt")):
            cands[p.name] = p.read_text(encoding="utf-8")
        p = PROJ / "小说" / f"{title}.txt"
        if p.exists():
            cands["novel_txt"] = p.read_text(encoding="utf-8")
        # 去重（按内容）
        uniq = {}
        for k, t in cands.items():
            key = t.strip()[:200]
            if key not in {x.strip()[:200] for x in uniq.values()}:
                uniq[k] = t
        return uniq

    chosen = {}
    report = {}
    for no in (1, 2, 3, 4):
        title = f"第{no}章"
        cands = candidates(no)
        best_k, best_s, best_c = None, -1.0, ""
        for k, t in cands.items():
            s = score(t)
            print(f"  {title} 候选[{k}] = {s:.4f} ({len(t)}字)")
            if s > best_s:
                best_k, best_s, best_c = k, s, t
        chosen[title] = (best_k, best_s)
        report[title] = round(best_s, 4)
        # 写入项目（保证后续章评分口径带上最优前章）
        chs = pm.get_project_data().get("completed_chapters", [])
        keep = [c for c in chs if any(c.get("title") == f"第{i}章" for i in range(1, no))]
        pm.get_project_data()["completed_chapters"] = keep
        pm.save_project()
        pm.add_chapter(title, best_c, source="continuation" if no == 4 else "generation")
        pm.save_project()
        (PROJ / "小说" / f"{title}.txt").write_text(best_c, encoding="utf-8")
        print(f"[归档] {title} <- {best_k} = {best_s:.4f}")

    print("\n===== 终版四章 =====")
    for t, s in report.items():
        print(f"  {t}: {s}  达0.9={s >= 0.9}")
    (LOG / "选优归档.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
