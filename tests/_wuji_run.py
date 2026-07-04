#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《无极》全流程实战执行器（真实 API，非 mock）

用法：
  python tests/_wuji_run.py phase1              # 项目创建 + 快捷创作四件套 + 导入
  python tests/_wuji_run.py phase2 <章号>       # 生成第N章（1-3），含前章上下文
  python tests/_wuji_run.py phase3              # 第4章续写（多版本→最佳）
  python tests/_wuji_run.py phase4              # 全面检测，输出检测报告

约定：
- 项目：小说作品/无极/无极.json（不触碰其它项目）
- 每步即时落盘，可断点续跑；证据写入 小说作品/无极/流程日志/
"""
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("DEV_MODE", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

PROJ_DIR = Path(ROOT) / "小说作品" / "无极"
PROJ_FILE = PROJ_DIR / "无极.json"
LOG_DIR = PROJ_DIR / "流程日志"
TARGET_WORDS = 2000


def log(m=""):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        print(str(m).encode("ascii", "replace").decode(), flush=True)


def save_evidence(name: str, data):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    p = LOG_DIR / name
    if isinstance(data, (dict, list)):
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        p.write_text(str(data), encoding="utf-8")
    log(f"[证据] {p}")


def get_pm():
    from services.project_manager import ProjectManager
    pm = ProjectManager(event_bus=None)
    if PROJ_FILE.exists():
        pm.load_project(str(PROJ_FILE))
    return pm


# ============ Phase 1：项目 + 快捷创作设定 ============

def phase1():
    log("===== Phase 1：项目创建 + 快捷创作四件套（真实API）=====")
    from services.project_manager import ProjectManager
    pm = ProjectManager(event_bus=None)
    if PROJ_FILE.exists():
        pm.load_project(str(PROJ_FILE))
        log(f"[项目] 已存在，续用：{PROJ_FILE}")
    else:
        pm.create_project("无极", str(PROJ_FILE))
        log(f"[项目] 已创建：{PROJ_FILE}")

    import importlib
    qmod = importlib.import_module("plugins.quick-creator-v1.plugin")
    from core.plugin_interface import PluginContext
    qp = qmod.QuickCreationPlugin()
    qp.initialize(PluginContext(event_bus=None, service_locator=None,
                                config_manager=None, plugin_registry=None))

    from core.models import QuickCreationRequest
    req = QuickCreationRequest(
        keywords="无极",
        target="all",
    )
    t0 = time.time()
    result = qp.generate_all(req)
    log(f"[快捷创作] success={result.success} 耗时={time.time()-t0:.1f}s "
        f"error={result.error}")
    if not result.success:
        sys.exit(1)

    wv = result.worldview.get_full_text() if result.worldview else ""
    ol = result.outline.get_full_text() if result.outline else ""
    chars = [c.model_dump() for c in (result.characters or [])]
    plot = result.plot.get_full_text() if result.plot else ""
    log(f"[产物] 世界观={len(wv)}字 大纲={len(ol)}字 人物={len(chars)}个 情节={len(plot)}字")

    # 导入项目（GUI同路径）
    pm.set_worldview(wv)
    pm.set_outline(ol)
    pm.set_characters(chars)
    pm.set_plot(plot)
    ok = pm.save_project()
    log(f"[导入] 项目保存={ok}")

    save_evidence("phase1_四件套.json", {
        "worldview": wv, "outline": ol, "characters": chars, "plot": plot,
        "elapsed_s": round(time.time() - t0, 1),
    })
    log("[Phase1 完成]")


# ============ Phase 2：生成第 N 章 ============

def phase2(chapter_no: int):
    log(f"===== Phase 2：生成第{chapter_no}章（真实API，评分反馈循环）=====")
    pm = get_pm()
    pd = pm.get_project_data()
    assert pd and pd.get("worldview"), "项目设定缺失，请先跑 phase1"

    prev = pm.get_recent_chapters(5)
    log(f"[上下文] 前章数={len(prev)}")

    from agents.novel_generation_service import (
        GenerationDataService, get_generation_service, NovelGenerationConfig)
    raw = {
        "outline_chapters_data": [],
        "outline_content": pm.get_outline(),
        "chapter_outlines": {},
        "style_profile": pd.get("style") or {},
        "character_data": pm.get_characters(),
        "worldview": pd.get("worldview") or "",
        "reverse_chapters": None, "generated_content": None,
        "project_data": pd,
    }
    ctx = GenerationDataService().build_generation_context(
        chapter_number=chapter_no, target_words=TARGET_WORDS, raw_data=raw,
        selected_knowledge_bases=["xuanhuan"], selected_writing_techniques=[])

    service = get_generation_service(event_bus=None, llm_client=None)
    config = NovelGenerationConfig(
        chapter_title=f"第{chapter_no}章", chapter_number=chapter_no,
        target_word_count=TARGET_WORDS,
        outline_content=ctx.get("outline_content", ""),
        chapter_outline=ctx.get("chapter_outline", ""),
        style_sample_path="", style_profile=ctx.get("style_profile") or {},
        characters=ctx.get("characters") or [],
        worldview=ctx.get("worldview") or {},
        max_iterations=5,
        validation_threshold=float(os.environ.get("WUJI_THRESHOLD", "0.8")),
        previous_chapter_text=(prev[-1] if prev else ""),
        previous_chapters=prev,
        knowledge_categories=["xuanhuan"], knowledge_domains=[],
        writing_techniques=[])

    t0 = time.time()
    result = service._orchestrator.execute_novel_generation(config)
    elapsed = time.time() - t0

    content, stats = "", {}
    if result and getattr(result, "final_output", None):
        content = result.final_output.get("content", "")
        stats = result.final_output.get("stats", {}) or {}
    score = stats.get("weighted_total_score") or stats.get("final_score")
    iters = stats.get("total_iterations")
    log(f"[生成] success={getattr(result,'success',None)} 字数={len(content)} "
        f"评分={score} 迭代={iters} 耗时={elapsed:.0f}s 本章完={'【本章完】' in content}")

    if not content:
        log("[失败] 无正文产出")
        sys.exit(1)

    # 前章上下文实战证据（第2章起：prompt无法直接取，此处校验记忆种子来源）
    pm.add_chapter(f"第{chapter_no}章", content, source="generation")
    pm.save_project()
    save_evidence(f"phase2_第{chapter_no}章_stats.json", {
        "score": score, "iterations": iters, "elapsed_s": round(elapsed),
        "word_count": len(content), "has_end_marker": "【本章完】" in content,
        "dimension_scores": {k: (v.score if hasattr(v, 'score') else v)
                             for k, v in (stats.get("dimension_scores") or {}).items()}
        if isinstance(stats.get("dimension_scores"), dict) else stats.get("dimension_scores"),
        "prev_context_count": len(prev),
    })
    (PROJ_DIR / "小说").mkdir(parents=True, exist_ok=True)
    (PROJ_DIR / "小说" / f"第{chapter_no}章.txt").write_text(content, encoding="utf-8")
    log(f"[Phase2 第{chapter_no}章 完成]")


# ============ Phase 3：第4章续写 ============

def phase3():
    log("===== Phase 3：第4章续写（多版本→最佳，真实API）=====")
    pm = get_pm()
    ch3 = pm.get_chapter_content("第3章")
    assert ch3, "第3章不存在，请先完成 phase2 3"

    import importlib
    cmod = importlib.import_module("plugins.continuation-generator-v1.plugin")
    from core.plugin_interface import PluginContext
    cp = cmod.ContinuationGeneratorPlugin()
    cp.initialize(PluginContext(event_bus=None, service_locator=None,
                                config_manager=None, plugin_registry=None))

    from core.models import ContinuationRequest
    req = ContinuationRequest(
        starting_text=ch3[-1500:],
        word_count=TARGET_WORDS,
        direction="natural",
        outline=pm.get_outline(),
        characters=pm.get_characters(),
        worldview=pm.get_worldview(),
        previous_chapters=pm.get_recent_chapters(5),
        temperature=0.8,
    )
    t0 = time.time()
    results = cp.generate_multiple_versions(request=req, num_versions=3,
                                            temperatures=[0.6, 0.8, 1.0])
    ok_results = [r for r in results if getattr(r, "success", False)]
    log(f"[续写] 版本={len(results)} 成功={len(ok_results)} 耗时={time.time()-t0:.0f}s")
    if not ok_results:
        log("[失败] 无成功版本")
        sys.exit(1)

    best, best_idx, detail = cp.select_best_version(ok_results, req)
    scores = [s.get("total") for s in detail.get("scores", [])]
    log(f"[择优] best=V{best_idx+1} scores={[round(s,3) if s else s for s in scores]}")

    content = best.text
    pm.add_chapter("第4章", content, source="continuation")
    pm.save_project()
    (PROJ_DIR / "小说").mkdir(parents=True, exist_ok=True)
    (PROJ_DIR / "小说" / "第4章.txt").write_text(content, encoding="utf-8")
    save_evidence("phase3_第4章_stats.json", {
        "versions": len(results), "best_index": best_idx,
        "scores": scores, "word_count": len(content),
        "elapsed_s": round(time.time() - t0),
    })
    log("[Phase3 完成]")


# ============ Phase 4：全面检测 ============

def phase4():
    log("===== Phase 4：全面检测（4章 × 5类检测，真实API）=====")
    pm = get_pm()
    chapters = [(c["title"], pm.get_chapter_content(c["title"]))
                for c in pm.list_chapters()]
    assert len(chapters) >= 4, f"章节不足4章（当前{len(chapters)}）"

    settings = {
        "project_name": "无极",
        "outline": pm.get_outline(),
        "characters": pm.get_characters(),
        "worldview": pm.get_worldview(),
    }

    import importlib
    from core.plugin_interface import PluginContext
    report = {"chapters": {}, "summary": {}}

    # 工具准备
    from agents.consistency_checker_agent import ConsistencyCheckerAgent
    cons = ConsistencyCheckerAgent()
    rmod = importlib.import_module("plugins.reverse-feedback-analyzer.plugin")
    rev = rmod.ReverseFeedbackAnalyzerPlugin()
    rev.initialize(PluginContext(event_bus=None, service_locator=None,
                                 config_manager=None, plugin_registry=None))
    from core.knowledge_recall import get_knowledge_recall
    kr = get_knowledge_recall(Path(ROOT))
    from core.ai_feeling_detector import detect_ai_feeling

    prev_texts = []
    for title, content in chapters:
        log(f"\n--- 检测 {title}（{len(content)}字）---")
        item = {"word_count": len(content),
                "has_end_marker": "【本章完】" in content,
                "word_ok": abs(len(content) - TARGET_WORDS) <= TARGET_WORDS * 0.35}

        # 1. 跨章一致性（真实LLM）
        try:
            t0 = time.time()
            cres = cons.execute({
                "new_chapter": content,
                "existing_chapters": [{"chapter_id": t, "content": c}
                                      for t, c in zip([x[0] for x in chapters], prev_texts)],
                "genre": "xuanhuan", "top_k": 5,
            })
            item["consistency"] = {
                "is_consistent": cres.get("is_consistent"),
                "conflicts": cres.get("conflicts", []),
                "elapsed_s": round(time.time() - t0),
            }
            log(f"  [跨章一致性] 冲突={len(cres.get('conflicts', []))}")
        except Exception as e:
            item["consistency"] = {"error": str(e)}
            log(f"  [跨章一致性] 异常: {e}")

        # 2. 逆向反馈（章节vs设定，真实LLM）
        try:
            t0 = time.time()
            rrep = rev.analyze_chapter_vs_settings(
                chapter_text=content, current_settings=settings, chapter_id=title)
            issues = [{"type": getattr(i, 'issue_type', None) and str(i.issue_type),
                       "severity": getattr(i, 'severity', None) and str(i.severity),
                       "element": getattr(i, 'element_name', ''),
                       "desc": getattr(i, 'description', ''),
                       "fix": getattr(i, 'suggested_fix', '')}
                      for i in rrep.issues]
            item["reverse"] = {"issues": issues,
                               "elapsed_s": round(time.time() - t0)}
            log(f"  [逆向反馈] 冲突={len(issues)}")
        except Exception as e:
            item["reverse"] = {"error": str(e)}
            log(f"  [逆向反馈] 异常: {e}")

        # 3. 知识库一致性（LLM防幻觉）
        try:
            t0 = time.time()
            kres = kr.check_knowledge_consistency(content, category="xuanhuan",
                                                  top_k=6, use_llm=True)
            item["knowledge"] = {
                "is_consistent": kres.is_consistent,
                "score": kres.consistency_score,
                "conflicts": [{"type": c.conflict_type, "sev": c.severity,
                               "desc": c.description, "fix": c.suggested_fix}
                              for c in kres.conflicts],
                "elapsed_s": round(time.time() - t0),
            }
            log(f"  [知识防幻觉] 一致={kres.is_consistent} 冲突={len(kres.conflicts)}")
        except Exception as e:
            item["knowledge"] = {"error": str(e)}
            log(f"  [知识防幻觉] 异常: {e}")

        # 4. AI感检测（本地）
        try:
            arep = detect_ai_feeling(content)
            item["ai_feeling"] = {
                "total_score": round(arep.total_score, 3),
                "naturalness": round(arep.naturalness_score, 3),
                "issue_count": len(arep.issues),
                "top_issues": [f"[{i.issue_type}] {i.position[:30]}"
                               for i in arep.issues[:8]],
            }
            log(f"  [AI感] 自然度={arep.naturalness_score:.2f} 问题={len(arep.issues)}")
        except Exception as e:
            item["ai_feeling"] = {"error": str(e)}
            log(f"  [AI感] 异常: {e}")

        report["chapters"][title] = item
        prev_texts.append(content)

    # 汇总
    total_conflicts = sum(
        len(ch.get("consistency", {}).get("conflicts", []) or [])
        + len(ch.get("reverse", {}).get("issues", []) or [])
        + len(ch.get("knowledge", {}).get("conflicts", []) or [])
        for ch in report["chapters"].values())
    avg_nat = [ch.get("ai_feeling", {}).get("naturalness")
               for ch in report["chapters"].values()
               if ch.get("ai_feeling", {}).get("naturalness") is not None]
    report["summary"] = {
        "chapters": len(chapters),
        "total_conflicts": total_conflicts,
        "avg_naturalness": round(sum(avg_nat) / len(avg_nat), 3) if avg_nat else None,
        "end_marker_all": all(ch.get("has_end_marker")
                              for ch in report["chapters"].values()),
    }
    save_evidence("phase4_检测报告.json", report)
    log(f"\n[汇总] 章节={len(chapters)} 总冲突={total_conflicts} "
        f"平均自然度={report['summary']['avg_naturalness']} "
        f"全部含本章完={report['summary']['end_marker_all']}")
    log("[Phase4 完成]")


def _score9(text: str, pm) -> float:
    """统一九维评分（与主链完全同口径）"""
    import importlib
    from core.plugin_interface import PluginContext
    qv_mod = importlib.import_module("plugins.quality-validator-v1.plugin")
    v = qv_mod.QualityValidatorPlugin()
    v.initialize(PluginContext(event_bus=None, service_locator=None,
                               config_manager=None, plugin_registry=None))
    pd = pm.get_project_data()
    wv = pd.get("worldview") or ""
    if not isinstance(wv, str):
        wv = json.dumps(wv, ensure_ascii=False)
    r = v.validate_with_weights(
        text=text, target_word_count=TARGET_WORDS,
        chapter_outline=pm.get_outline() or "",
        style_profile=pd.get("style") or {},
        character_profiles=pm.get_characters() or [],
        world_view=wv, knowledge_categories=["xuanhuan"])
    return float(r.total_weighted_score)


def _trim_to(pm, upto_exclusive: int):
    """裁剪章节列表到第N章之前（干净级联：本章重生成不被旧版本锚定）"""
    chs = pm.get_project_data().get("completed_chapters", [])
    keep = [c for c in chs
            if any(c.get("title") == f"第{i}章" for i in range(1, upto_exclusive))]
    pm.get_project_data()["completed_chapters"] = keep
    pm.save_project()


def phase9():
    """冲9：阈值0.9多轮循环（不降标准；每轮子进程隔离防状态污染）"""
    import subprocess
    target = float(os.environ.get("WUJI_THRESHOLD", "0.9"))
    rounds = int(os.environ.get("WUJI_ROUNDS", "3"))
    log(f"===== Phase 9：冲{target}（每章≤{rounds}轮×每轮≤5迭代）=====")
    env = dict(os.environ, WUJI_THRESHOLD=str(target), PYTHONIOENCODING="utf-8")
    summary = {}

    def _run_sub(args):
        return subprocess.run([sys.executable, os.path.abspath(__file__)] + args,
                              env=env, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=1800)

    for ch in (1, 2, 3):
        best_c, best_s = "", -1.0
        for att in range(1, rounds + 1):
            pm = get_pm()
            _trim_to(pm, ch)  # 只保留前 ch-1 章
            log(f"--- 第{ch}章 第{att}轮生成 ---")
            r = _run_sub(["phase2", str(ch)])
            if r.returncode != 0:
                log(f"[轮失败] 第{ch}章第{att}轮 rc={r.returncode} tail={r.stdout[-200:]}")
                continue
            pm2 = get_pm()
            content = pm2.get_chapter_content(f"第{ch}章") or ""
            s = _score9(content, pm2)
            log(f"[轮评] 第{ch}章 第{att}轮 统一九维={s:.4f} 字数={len(content)}")
            if s > best_s:
                best_s, best_c = s, content
            if best_s >= target:
                break
        pmf = get_pm()
        _trim_to(pmf, ch)
        pmf.add_chapter(f"第{ch}章", best_c, source="generation")
        pmf.save_project()
        (PROJ_DIR / "小说" / f"第{ch}章.txt").write_text(best_c, encoding="utf-8")
        summary[f"第{ch}章"] = round(best_s, 4)
        log(f"[定稿] 第{ch}章 best={best_s:.4f}")

    # 第4章（续写多版本，本身即一轮3版本择优；再包一层冲9轮次）
    best_c, best_s = "", -1.0
    for att in range(1, rounds + 1):
        pm = get_pm()
        _trim_to(pm, 4)
        log(f"--- 第4章续写 第{att}轮 ---")
        r = _run_sub(["phase3"])
        if r.returncode != 0:
            log(f"[轮失败] 第4章第{att}轮 rc={r.returncode}")
            continue
        pm4 = get_pm()
        content = pm4.get_chapter_content("第4章") or ""
        s = _score9(content, pm4)
        log(f"[轮评] 第4章 第{att}轮 统一九维={s:.4f} 字数={len(content)}")
        if s > best_s:
            best_s, best_c = s, content
        if best_s >= target:
            break
    pmf = get_pm()
    _trim_to(pmf, 4)
    pmf.add_chapter("第4章", best_c, source="continuation")
    pmf.save_project()
    (PROJ_DIR / "小说" / "第4章.txt").write_text(best_c, encoding="utf-8")
    summary["第4章"] = round(best_s, 4)
    log(f"[定稿] 第4章 best={best_s:.4f}")

    save_evidence("phase9_冲9汇总.json", {"target": target, "rounds": rounds,
                                          "best_scores": summary})
    log(f"[Phase9 完成] {summary}")


def phase9b():
    """定向补轮：以当前各章为保底基线，只接受更优；达0.9即停（不降标准）"""
    import subprocess
    target = float(os.environ.get("WUJI_THRESHOLD", "0.9"))
    rounds = int(os.environ.get("WUJI_ROUNDS", "4"))
    log(f"===== Phase 9b：定向补轮至{target}（每章≤{rounds}轮，保底现有最佳）=====")
    env = dict(os.environ, WUJI_THRESHOLD=str(target), PYTHONIOENCODING="utf-8")
    summary = {}

    def _run_sub(args):
        return subprocess.run([sys.executable, os.path.abspath(__file__)] + args,
                              env=env, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=1800)

    def _finalize(ch_title, content, source):
        pmf = get_pm()
        chs = pmf.get_project_data().get("completed_chapters", [])
        no = int(re.sub(r"\D", "", ch_title))
        keep = [c for c in chs if any(c.get("title") == f"第{i}章" for i in range(1, no))]
        pmf.get_project_data()["completed_chapters"] = keep
        pmf.save_project()
        pmf.add_chapter(ch_title, content, source=source)
        pmf.save_project()
        (PROJ_DIR / "小说" / f"{ch_title}.txt").write_text(content, encoding="utf-8")

    import re
    for no in (1, 2, 3, 4):
        title = f"第{no}章"
        pm0 = get_pm()
        best_c = pm0.get_chapter_content(title) or ""
        best_s = _score9(best_c, pm0) if best_c else -1.0
        log(f"[基线] {title} = {best_s:.4f}")
        if best_s >= target:
            summary[title] = round(best_s, 4)
            continue
        for att in range(1, rounds + 1):
            # 修剪到前no-1章（前章=各自当前最佳，保证级联）
            pm = get_pm()
            chs = pm.get_project_data().get("completed_chapters", [])
            keep = [c for c in chs if any(c.get("title") == f"第{i}章" for i in range(1, no))]
            pm.get_project_data()["completed_chapters"] = keep
            pm.save_project()
            log(f"--- {title} 补轮{att} ---")
            r = _run_sub(["phase3"] if no == 4 else ["phase2", str(no)])
            if r.returncode != 0:
                log(f"[补轮失败] {title} 轮{att} rc={r.returncode}")
                continue
            pm2 = get_pm()
            content = pm2.get_chapter_content(title) or ""
            s = _score9(content, pm2)
            log(f"[补轮评] {title} 轮{att} 统一九维={s:.4f} 字数={len(content)}")
            if s > best_s:
                best_s, best_c = s, content
            if best_s >= target:
                break
        _finalize(title, best_c, "continuation" if no == 4 else "generation")
        summary[title] = round(best_s, 4)
        log(f"[补轮定稿] {title} best={best_s:.4f}")

    save_evidence("phase9b_补轮汇总.json", {"target": target, "rounds": rounds,
                                            "best_scores": summary})
    log(f"[Phase9b 完成] {summary}")


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else ""
    if phase == "phase1":
        phase1()
    elif phase == "phase2":
        phase2(int(sys.argv[2]))
    elif phase == "phase3":
        phase3()
    elif phase == "phase4":
        phase4()
    elif phase == "phase9":
        phase9()
    elif phase == "phase9b":
        phase9b()
    else:
        log("用法: phase1 | phase2 <章号> | phase3 | phase4")
        sys.exit(2)
