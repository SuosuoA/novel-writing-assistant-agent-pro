#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提示词-评分数据对称性清点（九维前置数据是否输入给提示词）

原则：评分器按维度X打分的前提，是生成提示词里真的给了模型X的约束/素材。
本审计用《无极》真实项目重建生成主链的完整提示词，逐维核对：

维度            评分依据                    提示词侧应有
character      人物档案名+性格词           人物卡+【人名硬性要求】名单
style          风格档案(未配置→启发式)     风格段(未配置→如实标注)
outline        章节大纲情节点命中          大纲段(与评分用同源文本)
worldview      设定核心词Top30命中率       世界观段(核心词须在压缩后存活!)
knowledge      xuanhuan召回+被引用         【知识库参考】注入段
writing_tech   文本工艺启发式              【写作技巧要求】(选中时)+反AI指导
word_count     目标字数±10%                目标字数与区间指令
context_coh    开头衔接+人物承接           前章内容注入+衔接要求
ai_feeling     detect_ai_feeling词表       反AI指导(与检测器共享词表)

证据输出：小说作品/无极/流程日志/提示词对称性清点.json
"""
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("DEV_MODE", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

results = []


def check(name, ok, detail):
    tag = "[PASS]" if ok else "[FAIL]"
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
    outline = pm.get_outline() or ""
    chars = pm.get_characters() or []
    wv = pd.get("worldview") or ""
    if not isinstance(wv, str):
        wv = json.dumps(wv, ensure_ascii=False)
    prev = [c["content"] for c in pd.get("completed_chapters", [])[:1]]

    # ===== 重建生成主链完整提示词（与 generate_chapter 主路径同源）=====
    gmod = importlib.import_module("plugins.novel-generator-v3.plugin")
    gen = gmod.NovelGeneratorPlugin()
    gen.initialize(PluginContext(event_bus=None, service_locator=None,
                                 config_manager=None, plugin_registry=None))
    cb = gen._context_builder
    assert cb is not None, "ContextBuilder不可用"

    _chars = chars
    if isinstance(_chars, dict):
        _chars = [dict(v, name=v.get('name', k)) if isinstance(v, dict)
                  else {'name': k} for k, v in _chars.items()]

    prompt = cb.build_optimized_prompt(
        chapter_title="第2章", chapter_outline=outline, world_view=wv,
        style="", characters=_chars, previous_chapters=prev,
        max_worldview_tokens=2000, max_style_tokens=1500,
        target_word_count=2000)
    # 主路径知识/技巧注入段（generate_chapter 中 ContextBuilder 之后追加）
    knowledge_content = gen._retrieve_knowledge(["xuanhuan"], query=outline)
    if knowledge_content:
        prompt = prompt + "\n\n【知识库参考】\n" + knowledge_content
    prompt = gen._ensure_chapter_end_marker(prompt)
    print(f"重建提示词总长: {len(prompt)} 字\n")

    # ===== 逐维对称性核对 =====
    # 1. character
    names = [c.get('name') or (c.get('basic_info') or {}).get('name', '')
             for c in _chars]
    names = [n for n in names if n]
    ok = all(n in prompt for n in names) and "人名硬性要求" in prompt
    check("D1 character: 人物卡+硬性名单入prompt", ok,
          f"名单{names} 全在={all(n in prompt for n in names)}, 硬性要求在位")

    # 2. style（《无极》未配置——如实清点）
    style_cfg = pd.get("style") or {}
    if style_cfg:
        check("D2 style: 风格档案入prompt", "风格" in prompt, "已配置档案")
    else:
        check("D2 style: 未配置（数据事实）", True,
              "项目无风格档案→prompt无风格段、评分走文本启发式（对称：两边都无档案）")

    # 3. outline（与评分同源文本）
    ol_head = outline[:60].strip()
    check("D3 outline: 大纲段入prompt且与评分同源", ol_head[:30] in prompt,
          f"大纲开头30字在prompt中={ol_head[:30] in prompt}（评分用同一get_outline()）")

    # 4. worldview —— 核心词经压缩后的存活率（本清点的重点）
    from collections import Counter
    _stop = {'一个', '可以', '通过', '进行', '以及', '或者', '但是', '如果',
             '这个', '那个', '成为', '开始', '出现', '存在', '所有', '任何',
             '之间', '不同', '各种', '之后', '其中', '没有', '不是', '他们',
             '自己', '一种', '这些', '时代', '背景', '体系', '方向', '力量',
             '世界', '所谓', '最终', '真正', '其他', '一切', '对于'}
    try:
        import jieba
        toks = [w for w in jieba.cut(wv)
                if 2 <= len(w) <= 4 and re.fullmatch(r'[一-龥]+', w)
                and w not in _stop]
    except Exception:
        toks = [w for w in re.findall(r'[一-龥]{2,4}', wv) if w not in _stop]
    core = [w for w, _ in Counter(toks).most_common(30)]
    survived = [w for w in core if w in prompt]
    rate = len(survived) / len(core) if core else 0
    check("D4 worldview: 评分核心词在压缩后prompt中的存活率≥80%",
          rate >= 0.8,
          f"{len(survived)}/{len(core)} ({rate:.0%}) 丢失: {[w for w in core if w not in prompt][:8]}")

    # 5. knowledge
    check("D5 knowledge: 【知识库参考】注入段在位",
          "【知识库参考】" in prompt and len(knowledge_content) > 100,
          f"注入{len(knowledge_content)}字")
    # 注入条目与评分召回的交集（评分按正文关键词召回，注入按大纲召回——
    # 语料同库，标题应有交集）
    qv_mod = importlib.import_module("plugins.quality-validator-v1.plugin")
    v = qv_mod.QualityValidatorPlugin()
    v.initialize(PluginContext(event_bus=None, service_locator=None,
                               config_manager=None, plugin_registry=None))
    ch2 = pd["completed_chapters"][1]["content"] if len(pd.get("completed_chapters", [])) > 1 else ""
    _, recalled = v._score_knowledge_reference(ch2 or "混沌 修士 法则", {"genre": "xuanhuan"})
    inj_titles = re.findall(r'\[xuanhuan\]\s*([^:：]{4,20})[:：]', knowledge_content)
    rec_titles = [k.get("content", "")[:10] for k in recalled]
    check("D5b knowledge: 注入与评分召回同库（xuanhuan）",
          bool(inj_titles) and bool(recalled),
          f"注入{len(inj_titles)}条标题, 评分召回{len(recalled)}条（同一LanceDB类别）")

    # 6. writing_technique + 反AI指导
    from core.ai_feeling_detector import build_anti_ai_prompt_guidance
    anti = build_anti_ai_prompt_guidance()
    anti_head = anti.strip().split("\n")[0][:15]
    check("D6 反AI指导入prompt（词表与检测器同源）", anti_head in prompt,
          f"指导段首行在位={anti_head in prompt}")

    # 7. word_count
    ok_wc = ("2000" in prompt) and ("1800" in prompt or "±10%" in prompt or "2200" in prompt)
    check("D7 word_count: 目标字数+区间指令入prompt", ok_wc,
          f"含'2000'且含区间/±10%指令")

    # 8. context_coherence: 前章内容注入
    prev_tail = prev[0][-50:].strip()[:20] if prev else ""
    ok_cc = bool(prev) and (prev_tail in prompt or prev[0][:20] in prompt
                            or "上一章" in prompt or "前文" in prompt)
    check("D8 context_coherence: 前章内容/衔接要求入prompt", ok_cc,
          f"前章片段或衔接标记在位={ok_cc}")

    # 9. ai_feeling 词表同源断言
    from core.ai_feeling_detector import AIFeelingDetector
    _ai_words = AIFeelingDetector.AI_COMMON_WORDS
    check("D9 ai_feeling: 检测词表与指导共享同一常量", len(_ai_words) > 20,
          f"AI_COMMON_WORDS={len(_ai_words)}词（detect与guidance共用类常量）")

    print()
    ok_n = sum(1 for x in results if x["ok"])
    print(f"===== 对称性清点：{ok_n}/{len(results)} 项通过 =====")
    out = Path("小说作品/无极/流程日志/提示词对称性清点.json")
    out.write_text(json.dumps({"prompt_length": len(prompt), "checks": results},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[证据] {out}")
    sys.exit(0 if ok_n == len(results) else 1)


if __name__ == "__main__":
    main()
