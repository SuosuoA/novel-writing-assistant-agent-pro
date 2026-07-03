#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""九维评分法证审计：数据来源 + 真实性扰动验证

三部分：
A. 权重真值对账：yaml配置 vs 锁定权重 vs 加权总分手工复算
B. 数据来源到达性：《无极》真实项目数据逐字段核验（含LanceDB知识库存量）
C. 扰动真实性：每个维度喂对照输入，真测量必须朝正确方向移动；
   知识维度另验召回条目在库中真实存在、被引用关键词真实在正文中

证据输出：小说作品/无极/流程日志/九维法证审计.json
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

LOCKED_WEIGHTS = {
    'character': 0.19, 'style': 0.19, 'outline': 0.13, 'worldview': 0.12,
    'knowledge': 0.08, 'writing_technique': 0.08, 'word_count': 0.08,
    'context_coherence': 0.08, 'ai_feeling': 0.05,
}

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []


def check(name, ok, detail):
    tag = PASS if ok else FAIL
    print(f"{tag} {name}: {detail}")
    results.append({"check": name, "ok": bool(ok), "detail": str(detail)})
    return ok


def main():
    import importlib
    from core.plugin_interface import PluginContext
    from services.project_manager import ProjectManager

    pm = ProjectManager(event_bus=None)
    pm.load_project("小说作品/无极/无极.json")
    pd = pm.get_project_data()
    ch1 = pd["completed_chapters"][0]["content"]
    outline = pm.get_outline() or ""
    chars = pm.get_characters() or []
    if isinstance(chars, dict):
        chars = [dict(v, name=v.get('name', k)) if isinstance(v, dict)
                 else {'name': k} for k, v in chars.items()]
    wv = pd.get("worldview") or ""
    if not isinstance(wv, str):
        wv = json.dumps(wv, ensure_ascii=False)
    style_profile = pd.get("style") or {}

    qv_mod = importlib.import_module("plugins.quality-validator-v1.plugin")
    v = qv_mod.QualityValidatorPlugin()
    v.initialize(PluginContext(event_bus=None, service_locator=None,
                               config_manager=None, plugin_registry=None))

    print("=" * 62)
    print("A. 权重真值对账")
    print("=" * 62)
    import yaml
    ycfg = yaml.safe_load(open("config/validator_weights.yaml", encoding="utf-8"))
    yw = ycfg.get("weights", ycfg) if isinstance(ycfg, dict) else {}
    yw = {k: v_ for k, v_ in yw.items() if k in LOCKED_WEIGHTS}
    check("A1 yaml权重=锁定权重",
          all(abs(yw.get(k, -1) - w) < 1e-9 for k, w in LOCKED_WEIGHTS.items()),
          f"yaml={yw}")
    check("A2 权重和=1.0", abs(sum(LOCKED_WEIGHTS.values()) - 1.0) < 1e-9,
          f"sum={sum(LOCKED_WEIGHTS.values())}")

    r = v.validate_with_weights(
        text=ch1, target_word_count=2000, chapter_outline=outline,
        style_profile=style_profile, character_profiles=chars,
        world_view=wv, knowledge_categories=["xuanhuan"])
    dims = {k: d["score"] for k, d in r.feedback.items()
            if isinstance(d, dict) and "score" in d}
    manual = sum(dims.get(k, 0) * w for k, w in LOCKED_WEIGHTS.items())
    check("A3 加权总分=手工复算(九维,不含chapter_end)",
          abs(manual - r.total_weighted_score) < 1e-6,
          f"手工={manual:.6f} 上报={r.total_weighted_score:.6f}")
    check("A4 chapter_end不参与加权(仅作门槛)",
          'chapter_end' not in LOCKED_WEIGHTS and 'chapter_end' in dims,
          f"chapter_end={dims.get('chapter_end')} 在feedback中但无权重")

    print()
    print("=" * 62)
    print("B. 数据来源到达性（《无极》真实项目数据）")
    print("=" * 62)
    check("B1 正文", len(ch1) > 1000, f"第1章{len(ch1)}字")
    check("B2 大纲", len(outline) > 3000 and "待定" not in outline,
          f"{len(outline)}字, 无待定")
    check("B3 人物档案", len(chars) == 3 and chars[0].get("name") == "林默",
          f"{[c.get('name') for c in chars]}")
    check("B4 世界观", len(wv) > 500, f"{len(wv)}字")
    check("B5 风格档案", True,
          f"{'已配置' if style_profile else '未配置(空dict)→style维度走文本启发式路径'}")
    import lancedb
    df = lancedb.connect("data/knowledge_base").open_table("knowledge").to_pandas()
    xh = df[df["category"] == "xuanhuan"]
    check("B6 知识库xuanhuan存量", len(xh) == 20, f"{len(xh)}条向量")

    print()
    print("=" * 62)
    print("C. 扰动真实性（真测量必须随输入移动）")
    print("=" * 62)

    def dims_of(**kw):
        args = dict(text=ch1, target_word_count=2000, chapter_outline=outline,
                    style_profile=style_profile, character_profiles=chars,
                    world_view=wv, knowledge_categories=["xuanhuan"])
        args.update(kw)
        rr = v.validate_with_weights(**args)
        return {k: d["score"] for k, d in rr.feedback.items()
                if isinstance(d, dict) and "score" in d}

    base = dims

    # C1 word_count：目标翻4倍 → 分数应大跌
    p = dims_of(target_word_count=8000)
    check("C1 word_count响应", p["word_count"] < base["word_count"] - 0.2,
          f"目标2000:{base['word_count']} → 目标8000:{p['word_count']}")

    # C2 outline：换成无关大纲 → 应下跌
    fake_ol = ("第一章：都市白领苏菲入职跨国公司，遭遇职场霸凌。"
               "第二章：竞聘总监，闺蜜背叛。第三章：商战反击，收购对手。")
    p = dims_of(chapter_outline=fake_ol)
    check("C2 outline响应", p["outline"] < base["outline"] - 0.15,
          f"真大纲:{base['outline']} → 无关大纲:{p['outline']}")

    # C3 character：换成缺席人名 → 判罚0.5
    p = dims_of(character_profiles=[{"name": "魏央", "personality": "果决"}])
    check("C3 character响应", p["character"] <= 0.5 < base["character"],
          f"真人物:{base['character']} → 缺席人物:{p['character']}")

    # C4 worldview：换成无关世界观 → 应下跌
    fake_wv = ("赛博朋克2177：新东京，义体改造，脑机接口，巨型企业统治，"
               "黑客与仿生人，霓虹雨夜，数据幽灵。" * 5)
    p = dims_of(world_view=fake_wv)
    check("C4 worldview响应", p["worldview"] < base["worldview"] - 0.15,
          f"真世界观:{base['worldview']} → 无关世界观:{p['worldview']}")

    # C5 knowledge：不存在的类别 → 回落兜底
    p = dims_of(knowledge_categories=["zzz_nonexistent"])
    check("C5 knowledge响应", p["knowledge"] < base["knowledge"] - 0.15,
          f"xuanhuan:{base['knowledge']} → 不存在类别:{p['knowledge']}")

    # C5b knowledge召回真实性：召回条目在库中存在、引用关键词真实在正文
    score_k, recalled = v._score_knowledge_reference(ch1, {"genre": "xuanhuan"})
    ids_in_db = set(xh["knowledge_id"])
    all_exist = all((k.get("id") in ids_in_db) for k in recalled) if recalled else False
    check("C5b 召回条目均真实在库", bool(recalled) and all_exist,
          f"召回{len(recalled)}条, 全部命中LanceDB: {all_exist}")
    referenced = [k for k in recalled if k.get("referenced")]
    ref_real = True
    for k in referenced:
        kws = v._extract_keywords(k.get("content", ""))[:3]
        if not any(kw in ch1 for kw in kws):
            ref_real = False
    check("C5c 被引用判定可复核", ref_real,
          f"被引用{len(referenced)}条, 其关键词均真实出现在正文: {ref_real}")

    # C6 writing_technique：劣化文本 → 应下跌
    junk = "他走了过去。他走了过去。他走了过去。" * 80
    p_junk = v.validate_with_weights(
        text=junk + "\n【本章完】", target_word_count=2000,
        chapter_outline=outline, style_profile=style_profile,
        character_profiles=chars, world_view=wv,
        knowledge_categories=["xuanhuan"])
    jd = {k: d["score"] for k, d in p_junk.feedback.items()
          if isinstance(d, dict) and "score" in d}
    check("C6 writing_technique响应",
          jd["writing_technique"] < base["writing_technique"],
          f"真文:{base['writing_technique']} → 复读机文:{jd['writing_technique']}")

    # C7 ai_feeling：AI腔文本 → 应下跌
    ai_text = ("夜幕降临，城市的霓虹灯闪烁着。在这个瞬间，他的心中涌起一股"
               "难以言喻的暖流。他知道，这将是一段全新旅程的开始。命运的齿轮"
               "开始转动，一切都将不同。他的眼中闪过一丝坚定。" * 12) + "\n【本章完】"
    p_ai = v.validate_with_weights(
        text=ai_text, target_word_count=2000, chapter_outline=outline,
        style_profile=style_profile, character_profiles=chars,
        world_view=wv, knowledge_categories=["xuanhuan"])
    ad = {k: d["score"] for k, d in p_ai.feedback.items()
          if isinstance(d, dict) and "score" in d}
    check("C7 ai_feeling响应", ad["ai_feeling"] < base["ai_feeling"] - 0.1,
          f"真文:{base['ai_feeling']} → AI腔文:{ad['ai_feeling']}")

    # C8 context_coherence：抹掉开头承接要素 → 应下降或持平不升
    stripped = "某人做了某事。\n\n" + ch1[300:]
    p_cc = v.validate_with_weights(
        text=stripped, target_word_count=2000, chapter_outline=outline,
        style_profile=style_profile, character_profiles=chars,
        world_view=wv, knowledge_categories=["xuanhuan"])
    cd = {k: d["score"] for k, d in p_cc.feedback.items()
          if isinstance(d, dict) and "score" in d}
    check("C8 context_coherence响应",
          cd["context_coherence"] <= base["context_coherence"],
          f"真开头:{base['context_coherence']} → 抹承接开头:{cd['context_coherence']}")

    # C9 chapter_end完整性哨兵
    trunc = ch1.replace("【本章完】", "").rstrip()
    trunc = trunc[:len(trunc) - 8] + "\n【本章完】"  # 人为制造悬句
    p_tr = v.validate_with_weights(
        text=trunc, target_word_count=2000, chapter_outline=outline,
        style_profile=style_profile, character_profiles=chars,
        world_view=wv, knowledge_categories=["xuanhuan"])
    td = {k: d["score"] for k, d in p_tr.feedback.items()
          if isinstance(d, dict) and "score" in d}
    check("C9 chapter_end截断判罚", td["chapter_end"] <= 0.3 and not p_tr.passed,
          f"完整:{base['chapter_end']} → 悬句+标记:{td['chapter_end']}, passed={p_tr.passed}")

    print()
    ok_n = sum(1 for x in results if x["ok"])
    print(f"===== 法证结论：{ok_n}/{len(results)} 项通过 =====")
    out = Path("小说作品/无极/流程日志/九维法证审计.json")
    out.write_text(json.dumps({
        "base_dimensions": base, "checks": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[证据] {out}")
    sys.exit(0 if ok_n == len(results) else 1)


if __name__ == "__main__":
    main()
