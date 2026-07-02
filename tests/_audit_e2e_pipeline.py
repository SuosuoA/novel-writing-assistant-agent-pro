#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[审计用-临时] 普通模式真实路径端到端验证
GUI路径复刻：GenerationDataService.build_generation_context → NovelGenerationService
→ PipelineOrchestrator.execute_novel_generation（mock LLM）
"""
import os, sys, traceback
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("DEV_MODE", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def log(m):
    try: print(m, flush=True)
    except UnicodeEncodeError: print(m.encode("ascii", "replace").decode(), flush=True)


class _R:
    def __init__(s, t):
        s.success, s.text, s.error = True, t, None
        s.usage = {"total_tokens": len(t)}
        s.tokens_used = len(t)


class _Fake:
    def __init__(s):
        s.calls = 0
        base = ("夜色压在城西旧楼上，霓虹忽明忽暗。林越站在窗前，他性格冷静、话不多，"
                "盘算着那笔可疑交易的每一步。苏晴皱眉道：你还在等？她心直口快，藏不住情绪。"
                "林越笑了笑：在等一个答案。次日清晨他决定彻查交易源头。")
        s._t = base * 10 + "\n【本章完】"
    def generate_text(s, prompt=None, config=None, messages=None, **kw):
        s.calls += 1
        return _R(s._t)


def main():
    import core.ai_service_manager as aim
    fake = _Fake()
    aim.get_ai_service_manager = lambda: fake
    log("[OK] mock LLM 就绪")

    # 与 GUI 一致：先数据服务加工
    from agents.novel_generation_service import (
        GenerationDataService, get_generation_service, NovelGenerationConfig)
    raw_data = {
        "outline_chapters_data": [
            {"chapter_number": 1, "title": "旧楼之约",
             "summary": "林越在城西旧楼等待苏晴，就可疑交易试探，决定次日彻查幕后",
             "plot_points": ["等待苏晴", "试探交易", "决定彻查"],
             "characters": ["林越", "苏晴"]}],
        "outline_content": "全书讲述林越调查一桩旧案。",
        "chapter_outlines": {},
        "style_profile": {"author_name": "测试", "style_tags": ["心理刻画", "节奏紧凑"]},
        "character_data": [
            {"name": "林越", "role": "主角", "personality": "冷静、话不多"},
            {"name": "苏晴", "role": "女主", "personality": "心直口快"}],
        "worldview": {"name": "近未来都市",
                      "elements": [{"name": "城西旧楼"}, {"name": "霓虹"}],
                      "rules": ["不允许超自然力量"]},
        "reverse_chapters": None, "generated_content": None,
    }
    ctx = GenerationDataService().build_generation_context(
        chapter_number=1, target_words=1400, raw_data=raw_data,
        selected_knowledge_bases=[], selected_writing_techniques=[])
    log("[OK] 数据服务加工完成")

    service = get_generation_service(event_bus=None, llm_client=None)
    config = NovelGenerationConfig(
        chapter_title="第1章", chapter_number=1, target_word_count=1400,
        outline_content=ctx.get("outline_content", ""),
        chapter_outline=ctx.get("chapter_outline", ""),
        style_sample_path="", style_profile=ctx.get("style_profile") or {},
        characters=ctx.get("characters") or [], worldview=ctx.get("worldview") or {},
        max_iterations=2, validation_threshold=0.8,
        previous_chapter_text="", knowledge_categories=[], knowledge_domains=[],
        writing_techniques=[])

    try:
        result = service._orchestrator.execute_novel_generation(config)
    except Exception as e:
        log(f"[FAIL] 管线异常: {e}")
        traceback.print_exc()
        return 1

    log(f"\nLLM 调用次数: {fake.calls}")
    log(f"result 类型: {type(result).__name__}")
    for attr in ["success", "final_content", "content", "error"]:
        v = getattr(result, attr, "<无此属性>")
        if isinstance(v, str) and len(v) > 80:
            v = f"<str {len(v)}字> 含本章完={'【本章完】' in v}"
        log(f"  .{attr} = {v}")
    # GUI显示路径检查：_on_generation_complete 读 result.final_output["content"/"stats"]
    fo = getattr(result, "final_output", None)
    log(f"  .final_output 类型: {type(fo).__name__}")
    if isinstance(fo, dict):
        c = fo.get("content", "")
        stats = fo.get("stats", {})
        log(f"  final_output.content 字数: {len(c)} | 含本章完: {'【本章完】' in c}")
        if isinstance(stats, dict):
            log(f"  final_output.stats.weighted_total_score: {stats.get('weighted_total_score')}")
            log(f"  final_output.stats.passed: {stats.get('passed')}")
            log(f"  final_output.stats.dimension_scores: {stats.get('dimension_scores')}")

    log("\n===== 结论 =====")
    ok = fake.calls > 0 and getattr(result, "success", False)
    log("[OK] 普通模式真实路径连通" if ok else "[X] 普通模式真实路径存在断点")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
