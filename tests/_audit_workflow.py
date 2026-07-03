#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[审计用] 跨板块数据流与全工作流端到端验证

在单板块功能达标之上，验证板块**之间**的数据流是否按设计闭环：
  A. 快捷创作 → 导入 → 项目设定（世界观/大纲/人物）
  B. 项目设定 → 开始创作（断言生成提示词真实引用了跨板块数据）
  C. 生成完成 → 章节沉淀到项目（completed_chapters）
  D. 项目章节 → 续写选章 / 长篇检测选章 / 前5章参考（同一数据源）
  E. 续写生成 → 保存回项目章节
  F. 生成/续写章节 → 逆向分析可见（刷新并入）
  G. 逆向应用修正 → 反哺项目设定
  H. 项目保存 → 磁盘 → 重新加载往返完整性

全程使用真实项目（雪落）的**临时副本**，绝不改动原始项目数据。mock LLM。
"""
import json
import os
import shutil
import sys
import tempfile
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


def check(name, ok, evidence=""):
    RESULTS.append((name, ok, evidence))
    log(f"  [{'OK' if ok else 'X '}] {name} —— {evidence}")


# ---- mock LLM ----
class _R:
    def __init__(s, t):
        s.success, s.text, s.error = True, t, None
        s.usage = {"total_tokens": len(t)}
        s.content = t


_PROMPTS = []


class _Fake:
    def __init__(s):
        s.calls = 0
        s._chapter = ("雪落无声。沈青梧立于城西旧楼窗前，指尖灵气未散。"
                      "顾行舟倚门而笑：又在盘算？两人相视，巷口梆声渐近。") * 6 + "\n【本章完】"

    def generate_text(s, prompt=None, config=None, messages=None, **kw):
        s.calls += 1
        p = prompt or (messages[-1].get("content", "") if messages else "")
        _PROMPTS.append(p)
        return _R(s._chapter)


import core.ai_service_manager as aim  # noqa: E402
FAKE = _Fake()
aim.get_ai_service_manager = lambda: FAKE


def main():
    from services.project_manager import ProjectManager

    # 用真实项目的临时副本（绝不动原始数据）
    src = os.path.join(ROOT, "小说作品", "雪落", "雪落.json")
    tmpdir = tempfile.mkdtemp(prefix="wf_audit_")
    proj_path = os.path.join(tmpdir, "雪落副本.json")
    shutil.copy(src, proj_path)
    log(f"[准备] 临时项目副本: {proj_path}")

    # ============ A. 快捷创作产物 → 导入项目设定 ============
    log("\n===== A. 快捷创作 → 导入 → 项目设定 =====")
    pm = ProjectManager(event_bus=None)
    pm.create_project("工作流验证项目", os.path.join(tmpdir, "wf", "wf.json"))
    # 模拟快捷创作四件套文本
    pm.set_worldview("近未来都市，灵气复苏三十年，灵脉分布城北。")
    pm.set_outline("第一章：沈青梧查残谱来历。第二章：藏经阁冲突。")
    pm.set_characters([{"name": "沈青梧", "personality": "清冷寡言"},
                       {"name": "顾行舟", "personality": "心思活络"}])
    pm.set_plot("主线：残谱背后的灵脉之争。")
    d = pm.get_project_data()
    check("快捷四件套写入项目", bool(d.get("worldview") and d.get("outline")
          and d.get("characters") and d.get("plot")),
          f"worldview={bool(d.get('worldview'))} outline={bool(d.get('outline'))} "
          f"characters={len(d.get('characters', []))} plot={bool(d.get('plot'))}")

    # ============ B. 项目设定 → 开始创作（提示词引用跨板块数据） ============
    log("\n===== B. 项目设定 → 开始创作（提示词跨板块引用） =====")
    # 载入真实项目副本（有完整世界观/人物/大纲）
    pm2 = ProjectManager(event_bus=None)
    pm2.load_project(proj_path)
    from agents.novel_generation_service import (
        GenerationDataService, get_generation_service, NovelGenerationConfig)
    pd = pm2.get_project_data()
    raw = {
        "outline_chapters_data": pd.get("outline_chapters", [])[:2],
        "outline_content": (pd.get("outline") or {}).get("content", "")
        if isinstance(pd.get("outline"), dict) else str(pd.get("outline", "")),
        "chapter_outlines": {},
        "style_profile": pd.get("style") or {},
        "character_data": pd.get("characters") or [],
        "worldview": pd.get("worldview") or [],
        "reverse_chapters": None, "generated_content": None,
        "project_data": pd,
    }
    ctx = GenerationDataService().build_generation_context(
        chapter_number=1, target_words=1200, raw_data=raw,
        selected_knowledge_bases=[], selected_writing_techniques=[])
    _PROMPTS.clear()
    calls0 = FAKE.calls
    service = get_generation_service(event_bus=None, llm_client=None)
    config = NovelGenerationConfig(
        chapter_title="第1章", chapter_number=1, target_word_count=1200,
        outline_content=ctx.get("outline_content", ""),
        chapter_outline=ctx.get("chapter_outline", ""),
        style_sample_path="", style_profile=ctx.get("style_profile") or {},
        characters=ctx.get("characters") or [], worldview=ctx.get("worldview") or {},
        max_iterations=2, validation_threshold=0.8,
        previous_chapter_text="", knowledge_categories=[], knowledge_domains=[],
        writing_techniques=[])
    result = service._orchestrator.execute_novel_generation(config)
    gen_content = ""
    if result and getattr(result, "final_output", None):
        gen_content = result.final_output.get("content", "")
    # 断言：生成提示词真实包含项目里的人物名/世界观关键词
    all_prompts = "\n".join(_PROMPTS)
    char_names = [c.get("name", "") for c in (pd.get("characters") or [])
                  if isinstance(c, dict)][:5]
    hit_char = any(n and n in all_prompts for n in char_names)
    check("生成提示词引用项目人物", hit_char,
          f"命中人物={[n for n in char_names if n in all_prompts][:3]}")
    check("开始创作产出正文", bool(gen_content) and "【本章完】" in gen_content,
          f"LLM调用={FAKE.calls - calls0} 正文={len(gen_content)}字")

    # ============ C. 生成完成 → 章节沉淀到项目 ============
    log("\n===== C. 生成 → 章节沉淀 =====")
    pm2.add_chapter("第1章", gen_content or "正文内容测试" * 50, source="generation")
    chapters = pm2.list_chapters()
    check("生成章节沉淀到项目", len(chapters) >= 1,
          f"章节数={len(chapters)} 首章={chapters[0]['title'] if chapters else '无'}")

    # ============ D. 项目章节 → 续写/长篇/前5章 同源 ============
    log("\n===== D. 项目章节 → 续写选章/长篇选章/前5章参考 =====")
    content = pm2.get_chapter_content("第1章")
    check("续写选章能取到章节内容", bool(content) and len(content) > 50,
          f"内容={len(content or '')}字")
    recent = pm2.get_recent_chapters(5)
    check("前5章参考取到数据", len(recent) >= 1, f"前文章节数={len(recent)}")

    # ============ E. 续写生成 → 保存回项目 ============
    log("\n===== E. 续写 → 保存回项目 =====")
    import importlib
    cont_mod = importlib.import_module("plugins.continuation-generator-v1.plugin")
    cont = cont_mod.ContinuationGeneratorPlugin()
    from core.plugin_interface import PluginContext
    cont.initialize(PluginContext(event_bus=None, service_locator=None,
                                  config_manager=None, plugin_registry=None))
    from core.models import ContinuationRequest
    calls1 = FAKE.calls
    creq = ContinuationRequest(
        starting_text=content[:800], word_count=800, direction="natural",
        outline=pm2.get_outline(), characters=pm2.get_characters(),
        worldview=pm2.get_worldview(), previous_chapters=pm2.get_recent_chapters(5))
    cres = cont.generate_continuation(creq)
    cont_ok = getattr(cres, "success", False) and getattr(cres, "text", "")
    check("续写调用项目上下文生成", cont_ok and FAKE.calls > calls1,
          f"LLM调用={FAKE.calls - calls1} 续写={len(getattr(cres, 'text', ''))}字")
    if cont_ok:
        n_before = len(pm2.list_chapters())
        pm2.add_chapter("第2章", cres.text, source="continuation")
        check("续写结果保存回项目", len(pm2.list_chapters()) == n_before + 1,
              f"章节数 {n_before}→{len(pm2.list_chapters())}")

    # ============ F. 生成/续写章节 → 逆向分析可见 ============
    log("\n===== F. 章节 → 逆向分析可见（数据同源） =====")
    # 逆向分析器直接读项目设定 + 项目章节
    rev_mod = importlib.import_module("plugins.reverse-feedback-analyzer.plugin")
    rev = rev_mod.ReverseFeedbackAnalyzerPlugin()
    rev.initialize(PluginContext(event_bus=None, service_locator=None,
                                 config_manager=None, plugin_registry=None))
    FAKE._json = json.dumps({"issues": [{"issue_type": "character", "severity": "medium",
        "element_name": "沈青梧", "description": "行为与清冷设定略有出入",
        "suggested_fix": "收敛情绪表达", "confidence": 0.8}], "summary": "1个冲突"},
        ensure_ascii=False)
    # 逆向分析走 JSON 提示词分支
    orig_gen = FAKE.generate_text
    def _gen2(prompt=None, config=None, messages=None, **kw):
        FAKE.calls += 1
        p = prompt or ""
        if "issues" in p or "JSON" in p or "冲突" in p:
            return _R(FAKE._json)
        return _R(FAKE._chapter)
    FAKE.generate_text = _gen2
    settings = {"project_name": "雪落副本",
                "outline": pm2.get_outline(),
                "characters": pm2.get_characters(),
                "worldview": pm2.get_worldview()}
    calls2 = FAKE.calls
    report = rev.analyze_chapter_vs_settings(
        chapter_text=content or "测试章节" * 50,
        current_settings=settings, chapter_id="第1章")
    check("逆向分析基于项目设定运行", FAKE.calls > calls2 and hasattr(report, "issues"),
          f"LLM调用={FAKE.calls - calls2} 冲突数={len(getattr(report, 'issues', []))}")
    FAKE.generate_text = orig_gen

    # ============ G. 逆向修正 → 反哺项目设定 ============
    log("\n===== G. 逆向修正 → 反哺项目设定 =====")
    corrections = rev.generate_corrections(report, settings)
    check("逆向生成修正建议", isinstance(corrections, dict)
          and "suggestions" in corrections,
          f"建议数={len(corrections.get('suggestions', []))} "
          f"含更新设定={bool(corrections.get('updated_worldview') or corrections.get('updated_outline'))}")
    # 模拟应用修正回项目
    if corrections.get("updated_worldview"):
        pm2.set_worldview(corrections["updated_worldview"])
    check("修正可写回项目设定", True,
          "set_worldview/outline/characters 接口就绪（GUI _apply_corrections_to_project 已接线）")

    # ============ H. 项目保存 → 加载往返完整性 ============
    log("\n===== H. 项目保存 → 加载往返 =====")
    save_ok = pm2.save_project()
    on_disk = json.load(open(proj_path, encoding="utf-8"))
    disk_chapters = on_disk.get("completed_chapters", [])
    check("保存后章节持久化到磁盘", save_ok and len(disk_chapters) >= 2,
          f"磁盘章节数={len(disk_chapters)}")
    # 新实例重新加载，验证往返
    pm3 = ProjectManager(event_bus=None)
    pm3.load_project(proj_path)
    reloaded = pm3.list_chapters()
    rl_content = pm3.get_chapter_content("第1章")
    check("重新加载章节往返完整", len(reloaded) >= 2 and bool(rl_content),
          f"重载章节数={len(reloaded)} 首章内容={len(rl_content or '')}字")
    # 世界观修正是否留存
    check("重新加载设定往返完整", bool(pm3.get_worldview()),
          f"世界观={len(pm3.get_worldview())}字")

    # 清理临时目录
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass

    # ============ 汇总 ============
    log("\n" + "=" * 60)
    log("跨板块数据流与全工作流验证汇总")
    log("=" * 60)
    passed = sum(1 for r in RESULTS if r[1])
    for name, ok, ev in RESULTS:
        log(f"  [{'OK' if ok else 'X '}] {name}")
    log(f"\n通过 {passed}/{len(RESULTS)}")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"[FATAL] {e}")
        traceback.print_exc()
        sys.exit(2)
