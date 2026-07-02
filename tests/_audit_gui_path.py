#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[审计用-临时] 完整 GUI 数据路径端到端验证

模拟真实 GUI 路径（不手搓请求）：
  raw_data(如_collect_raw_data产出)
    → GenerationDataService.build_generation_context  (真实转换层)
    → GenerationRequest  (按 _build_generation_request 同样的字段映射)
    → expert-novel-v1.generate()  (mock LLM)
验证：经过真实转换层后，世界观/人物/大纲/风格 是否仍以正确 shape 到达插件、评分是否真出分。
"""
import os, sys, importlib.util, uuid, traceback
os.environ.setdefault("HF_HUB_OFFLINE", "1"); os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def log(m):
    try: print(m, flush=True)
    except UnicodeEncodeError: print(m.encode("ascii", "replace").decode(), flush=True)


class _R:
    def __init__(s, t): s.success, s.text, s.error = True, t, None


class _Fake:
    def __init__(s): s.calls = 0
    def generate_text(s, prompt=None, config=None, messages=None, **k):
        s.calls += 1
        return _R(("林越站在城西旧楼的窗前，霓虹忽明忽暗。他性格冷静，盘算着那笔可疑交易。"
                   "苏晴皱眉道，她心直口快。次日他决定彻查交易源头。") * 6 + "\n【本章完】")


def main():
    import core.ai_service_manager as aim
    fake = _Fake(); aim.get_ai_service_manager = lambda: fake

    # 1) 造"_collect_raw_data 会产出"的真实形态原始数据
    raw_data = {
        "outline_chapters_data": [
            {"chapter_number": 1, "title": "旧楼之约", "summary": "林越在城西旧楼等苏晴，就可疑交易试探",
             "plot_points": ["等待苏晴", "试探交易", "决定彻查"], "characters": ["林越", "苏晴"]},
        ],
        "outline_content": "全书讲述林越调查一桩旧案。",
        "chapter_outlines": {},
        "style_profile": {  # 8维分析结果形态
            "author_name": "测试风格", "style_tags": ["心理刻画", "节奏紧凑"],
            "writing_characteristics": ["善用感官描写"], "language_style": {"register": "书面"},
            "emotional_tone": {"overall_sentiment": "冷峻"},
        },
        "character_data": [  # 列表形态（GUI 持有）
            {"name": "林越", "role": "主角", "personality": "冷静、话不多、善于盘算"},
            {"name": "苏晴", "role": "女主", "personality": "心直口快、藏不住情绪"},
        ],
        "worldview": {  # 注意 rules 是字符串列表——正是修复点
            "name": "近未来都市", "elements": [{"name": "城西旧楼"}, {"name": "霓虹"}],
            "rules": ["不允许超自然力量", "科技水平接近现实"],
        },
        "reverse_chapters": None, "generated_content": None,
    }

    # 2) 真实转换层
    from agents.novel_generation_service import GenerationDataService
    ctx = GenerationDataService().build_generation_context(
        chapter_number=1, target_words=1400, raw_data=raw_data,
        selected_knowledge_bases=[], selected_writing_techniques=[], expert_config={"quality_threshold": 0.8, "max_iterations": 2})

    log("== 转换层产出 shape 检查 ==")
    log(f"  worldview: {type(ctx['worldview']).__name__}, rules类型={[type(r).__name__ for r in ctx['worldview'].get('rules',[])]}")
    log(f"  characters: {type(ctx['characters']).__name__}, keys={list(ctx['characters'].keys())}")
    log(f"  style_profile: {type(ctx['style_profile']).__name__}, author={ctx['style_profile'].get('author_name')}")
    log(f"  chapter_outline 长度: {len(ctx['chapter_outline'])} 字, 含情节要点={'情节要点' in ctx['chapter_outline']}")

    # 3) 按 _build_generation_request 同样的映射构建请求
    from types import SimpleNamespace
    req = SimpleNamespace(
        request_id=str(uuid.uuid4()), title="第1章", chapter_title="第1章",
        outline=ctx.get("outline_content", ""), chapter_outline=ctx.get("chapter_outline", ""),
        word_count=1400, word_count_target=1400, max_iterations=2,
        style_profile=ctx.get("style_profile"), character_profiles=ctx.get("characters"),
        worldview_config=ctx.get("worldview"), expert_config={"quality_threshold": 0.8, "max_iterations": 2},
        knowledge_categories=ctx.get("knowledge_categories", []),
        writing_techniques=ctx.get("writing_techniques", []),
        previous_chapter_text=ctx.get("previous_chapter_text", ""), chapter_number=1,
    )

    # 4) 真实插件
    spec = importlib.util.spec_from_file_location("epg", os.path.join(ROOT, "plugins", "expert-novel-v1", "plugin.py"))
    mod = importlib.util.module_from_spec(spec); sys.modules["epg"] = mod; spec.loader.exec_module(mod)
    plugin = mod.create_plugin()
    from core.plugin_interface import PluginContext
    from core.event_bus import EventBus
    from core.config_manager import ConfigManager
    plugin.initialize(PluginContext(event_bus=EventBus(), service_locator=None, config_manager=ConfigManager(), plugin_registry=None))

    log("\n== 经真实转换层后跑 generate() ==")
    try:
        result = plugin.generate(req)
    except Exception as e:
        log(f"[FAIL] generate 异常: {e}"); traceback.print_exc(); return 1

    meta = getattr(result, "metadata", {}) or {}
    ev = meta.get("expert_evaluation", {})
    dims = ev.get("dimension_scores", {})
    log(f"LLM 调用次数: {fake.calls}")
    log(f"总分: {ev.get('total_score')}")
    for k, v in dims.items():
        log(f"  {k} = {v}")
    distinct = len(set(round(float(v), 3) for v in dims.values())) if dims else 0
    log(f"\n维度不同值数: {distinct}")
    if distinct <= 1:
        log("[X] 经转换层后维度仍同分 → 真实路径上数据没真到达/评分没真跑")
        return 1
    log("[OK] 真实 GUI 数据路径端到端连通：转换层 shape 正确，评分真实区分")
    return 0


if __name__ == "__main__":
    sys.exit(main())
