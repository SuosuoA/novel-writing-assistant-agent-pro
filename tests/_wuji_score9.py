#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《无极》统一九维评分器：对全部章节用生成主链同款口径打分

与 novel-generator-v3._validate_via_plugin 完全一致的调用：
QualityValidatorPlugin.validate_with_weights(text, target_word_count,
chapter_outline, style_profile, character_profiles, world_view)

用法：python tests/_wuji_score9.py
输出：小说作品/无极/流程日志/九维统一评分.json + 控制台维度矩阵
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

PROJ_FILE = Path(ROOT) / "小说作品" / "无极" / "无极.json"
LOG_DIR = Path(ROOT) / "小说作品" / "无极" / "流程日志"
TARGET_WORDS = 2000


def log(m=""):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        print(str(m).encode("ascii", "replace").decode(), flush=True)


def main():
    from services.project_manager import ProjectManager
    pm = ProjectManager(event_bus=None)
    pm.load_project(str(PROJ_FILE))
    pd = pm.get_project_data()
    chapters = pd.get("completed_chapters", [])
    if not chapters:
        log("[错误] 项目无章节")
        sys.exit(1)

    import importlib
    from core.plugin_interface import PluginContext
    qv_mod = importlib.import_module("plugins.quality-validator-v1.plugin")
    validator = qv_mod.QualityValidatorPlugin()
    validator.initialize(PluginContext(event_bus=None, service_locator=None,
                                       config_manager=None, plugin_registry=None))

    outline = pm.get_outline() or ""
    style_profile = pd.get("style") or {}
    characters = pm.get_characters() or []
    worldview = pd.get("worldview") or ""

    report = []
    for ch in chapters:
        no = ch.get("chapter_number") or ch.get("number")
        content = ch.get("content", "")
        result = validator.validate_with_weights(
            text=content,
            target_word_count=TARGET_WORDS,
            chapter_outline=outline,
            style_profile=style_profile,
            character_profiles=characters,
            world_view=worldview,
            knowledge_categories=["xuanhuan"],
        )
        dims = {}
        if getattr(result, "feedback", None):
            for name, data in result.feedback.items():
                if isinstance(data, dict) and "score" in data:
                    dims[name] = round(float(data["score"]), 4)
        entry = {
            "chapter": no,
            "source": ch.get("source", "generation"),
            "words": len(content),
            "weighted_total": round(float(result.total_weighted_score), 4),
            "passed": bool(result.total_weighted_score >= 0.8),
            "dimensions": dims,
            "suggestions": list(getattr(result, "suggestions", []) or [])[:5],
        }
        report.append(entry)
        log(f"第{no}章({entry['source']}) 字数={entry['words']} "
            f"加权={entry['weighted_total']} 达标={entry['passed']}")
        for k, v in sorted(dims.items(), key=lambda x: x[1]):
            log(f"    {k:<22} {v}")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out = LOG_DIR / "九维统一评分.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    log(f"[证据] {out}")

    # 维度短板汇总（跨章均值最低的3个维度）
    from collections import defaultdict
    agg = defaultdict(list)
    for e in report:
        for k, v in e["dimensions"].items():
            agg[k].append(v)
    means = {k: round(sum(v) / len(v), 4) for k, v in agg.items()}
    log("\n[跨章维度均值（升序=短板在前）]")
    for k, v in sorted(means.items(), key=lambda x: x[1]):
        log(f"    {k:<22} {v}")


if __name__ == "__main__":
    main()
