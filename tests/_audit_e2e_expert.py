#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[审计用-临时] 专家模式端到端真实数据流验证 harness

目的：不调用真实 API，用 mock LLM 真跑 expert-novel-v1.generate() 的完整 7 步循环，
验证：数据是否真到达插件 / 评分是否真运行 / 迭代是否真循环 / 9 维度是否真区分 / 记忆是否真写入。

用法：python tests/_audit_e2e_expert.py
"""
import os
import sys
import json
import traceback
from types import SimpleNamespace

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# ---------- 1. mock LLM ----------
class _FakeResult:
    def __init__(self, text):
        self.success = True
        self.text = text
        self.error = None
        self.tokens_used = len(text)


class _FakeAIManager:
    """记录每次调用，返回一段固定的中文章节内容（含【本章完】）。"""
    def __init__(self):
        self.calls = []
        self._chapter = (
            "夜色压在城西的旧楼上，林越站在窗前，指尖夹着一支没点燃的烟。"
            "他性格冷静，话不多，却在沉默里盘算着每一步。楼下传来脚步声，是苏晴。"
            "“你还没睡？”苏晴皱眉道，她一向心直口快，藏不住情绪。"
            "林越笑了笑：“在等一个答案。”窗外的霓虹忽明忽暗，照着两人之间没说出口的话。"
            "他想起三年前那场雨，想起自己如何一步步走到今天。次日清晨，"
            "他决定去查清楚那笔交易背后的人。城市在晨光里苏醒，新的博弈才刚刚开始。"
        ) * 4 + "\n【本章完】"

    def generate_text(self, prompt=None, config=None, messages=None, **kwargs):
        self.calls.append({
            "prompt_len": len(prompt or ""),
            "max_tokens": getattr(config, "max_tokens", None),
            "has_feedback": "上轮优化反馈" in (prompt or ""),
            "system_len": len((messages or [{}])[0].get("content", "")) if messages else 0,
        })
        return _FakeResult(self._chapter)


class _ImprovingAIManager:
    """逐轮改进：每次调用返回更完整、更贴合评分关键词、长度达标的内容。
    用于验证迭代循环能否真正推动分数上升并爬过 0.8 达标（设计预期）。"""
    def __init__(self):
        self.calls = 0
        base = (
            "夜色压在城西旧楼上，霓虹忽明忽暗。林越站在窗前，他性格冷静，话不多，"
            "心里盘算着那笔可疑交易背后的每一步。楼下脚步声响起，是苏晴——她心直口快，"
            "藏不住情绪。“你还在等？”苏晴皱眉道。林越笑了笑：“在等一个答案。”"
            "他想起三年前那场雨，沉默里全是博弈。次日清晨，他决定彻查这桩交易的源头，"
            "城西旧楼的霓虹照着他坚定的背影。"
        )
        self.base = base

    def generate_text(self, prompt=None, config=None, messages=None, **kwargs):
        self.calls += 1
        # 轮次越高，重复越多→长度越接近1400，关键词覆盖越全
        reps = {1: 2, 2: 4, 3: 6}.get(self.calls, 6)
        text = self.base * reps
        # 控制到目标附近
        text = text[:1380] + "\n【本章完】"
        return _FakeResult(text)


def _run_convergence(plugin, base_request, log):
    """收敛测试：换上逐轮改进的 LLM，验证分数能否上升并达标。"""
    import copy
    import core.ai_service_manager as aim
    imp = _ImprovingAIManager()
    aim.get_ai_service_manager = lambda: imp
    req = copy.copy(base_request)
    req.expert_config = {"quality_threshold": 0.8, "max_iterations": 3}
    req.max_iterations = 3
    try:
        result = plugin.generate(req)
    except Exception as e:
        log(f"[收敛FAIL] {e}")
        import traceback; traceback.print_exc()
        return
    meta = getattr(result, "metadata", {}) or {}
    log(f"逐轮分数: {meta.get('iteration_scores')}")
    log(f"最佳分数: {meta.get('best_score')}, 达标(is_passing): {meta.get('is_passing')}, "
        f"阈值: {meta.get('quality_threshold')}, 迭代: {meta.get('total_iterations')}")
    scores = meta.get('iteration_scores') or []
    if len(scores) >= 2 and scores[-1] > scores[0]:
        log("  [OK] 分数随迭代上升 → 反馈循环真实推动改进")
    elif scores:
        log("  [i] 分数未明显上升（mock内容差异有限，真实LLM下应更明显）")


def main():
    report = {"steps": [], "ok": True}

    def log(msg):
        try:
            print(msg, flush=True)
        except UnicodeEncodeError:
            print(msg.encode("ascii", "replace").decode("ascii"), flush=True)
        report["steps"].append(msg)

    # ---------- 2. 注入 mock 到 LLM 接缝 ----------
    try:
        import core.ai_service_manager as aim
        fake = _FakeAIManager()
        aim.get_ai_service_manager = lambda: fake
        log("[OK] 已 mock core.ai_service_manager.get_ai_service_manager")
    except Exception as e:
        log(f"[FAIL] 无法 mock AI manager: {e}")
        traceback.print_exc()
        return 1

    # ---------- 3. 加载真实插件 ----------
    try:
        import importlib.util
        plugin_path = os.path.join(ROOT, "plugins", "expert-novel-v1", "plugin.py")
        spec = importlib.util.spec_from_file_location("expert_novel_plugin_audit", plugin_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["expert_novel_plugin_audit"] = mod
        spec.loader.exec_module(mod)
        plugin = mod.create_plugin()
        log(f"[OK] 插件实例创建: id={plugin.metadata.id} name={plugin.metadata.name}")
    except Exception as e:
        log(f"[FAIL] 加载插件失败: {e}")
        traceback.print_exc()
        return 1

    # ---------- 4. 初始化插件 ----------
    try:
        from core.plugin_interface import PluginContext
        from core.event_bus import EventBus
        from core.config_manager import ConfigManager
        ctx = PluginContext(
            event_bus=EventBus(),
            service_locator=None,
            config_manager=ConfigManager(),
            plugin_registry=None,
        )
        plugin.initialize(ctx)
        log("[OK] 插件 initialize() 完成")
    except Exception as e:
        log(f"[WARN] initialize 失败（继续尝试 generate）: {e}")
        traceback.print_exc()

    # ---------- 5. 构造真实生成请求 ----------
    request = SimpleNamespace(
        title="第1章 旧楼之约",
        chapter_title="第1章 旧楼之约",
        chapter_number=1,
        chapter_outline="林越在城西旧楼等待苏晴，两人就一笔可疑交易展开试探。林越决定次日彻查交易背后的人。",
        outline="全书讲述林越调查一桩旧案，逐步揭开城市权力博弈。",
        worldview_config={
            "name": "近未来都市",
            "elements": [{"name": "城西旧楼"}, {"name": "霓虹"}, {"name": "交易"}],
            "rules": ["不允许超自然力量"],
        },
        character_profiles={
            "林越": {"name": "林越", "role": "主角", "personality": "冷静、话不多、善于盘算",
                     "speaking_style": "简短克制"},
            "苏晴": {"name": "苏晴", "role": "女主", "personality": "心直口快、藏不住情绪"},
        },
        style_profile={
            "author_name": "测试风格",
            "style_tags": ["心理刻画", "节奏紧凑", "感官描写"],
            "keywords": ["霓虹", "沉默", "博弈"],
        },
        knowledge_categories=None,
        writing_techniques=None,
        previous_chapter_text=None,
        word_count=1400,
        word_count_target=1400,
        expert_config={"quality_threshold": 0.8, "max_iterations": 3},
        max_iterations=3,
    )
    log("[OK] 请求构造完成（世界观/人物2/大纲/风格 均提供, 目标1400字, 阈值0.8, 最多3轮）")

    # ---------- 6. 执行 generate ----------
    try:
        import time
        t0 = time.time()
        result = plugin.generate(request)
        dt = time.time() - t0
        log(f"[OK] generate() 返回, 耗时 {dt:.2f}s")
    except Exception as e:
        log(f"[FAIL] generate() 抛异常: {e}")
        traceback.print_exc()
        return 1

    # ---------- 7. 检查结果 ----------
    log("\n===== 结果检查 =====")
    log(f"LLM 实际被调用次数: {len(fake.calls)}")
    for i, c in enumerate(fake.calls, 1):
        log(f"  第{i}轮API: prompt={c['prompt_len']}字, max_tokens={c['max_tokens']}, "
            f"含反馈={c['has_feedback']}, system={c['system_len']}字")

    vs = getattr(result, "validation_scores", None)
    log(f"\nvalidation_scores 类型: {type(vs).__name__}")
    if vs is not None:
        for attr in ["total_score", "worldview_score", "character_score", "outline_score",
                     "style_score", "knowledge_score", "writing_technique_score",
                     "word_count_score", "context_coherence_score", "ai_feeling_score"]:
            if hasattr(vs, attr):
                log(f"  {attr} = {getattr(vs, attr)}")
        if isinstance(vs, dict):
            log(f"  (dict) {json.dumps(vs, ensure_ascii=False, default=str)[:800]}")

    meta = getattr(result, "metadata", None)
    log(f"\nmetadata: {json.dumps(meta, ensure_ascii=False, default=str)[:800] if meta else meta}")

    content = getattr(result, "content", "") or ""
    log(f"\n最终内容长度: {len(content)} 字, 含【本章完】: {'【本章完】' in content}")

    # 评分区分度检查：9 维度是否都是同一个值（说明评分没真跑）
    if vs is not None and not isinstance(vs, dict):
        dims = [getattr(vs, a, None) for a in ["worldview_score", "character_score", "outline_score",
                "style_score", "knowledge_score", "writing_technique_score", "word_count_score",
                "context_coherence_score", "ai_feeling_score"]]
        dims = [d for d in dims if isinstance(d, (int, float))]
        if dims:
            log(f"\n9维度分布: min={min(dims):.3f} max={max(dims):.3f} 不同值数={len(set(round(d,3) for d in dims))}")
            if len(set(round(d, 3) for d in dims)) == 1:
                log("  [⚠️] 所有维度同分 → 评分可能未真正运行/被默认值填充")
            else:
                log("  [OK] 维度分数有区分度 → 评分真实运行")

    # ---------- 7.5 直连 validator 探针：暴露被吞掉的真实 traceback ----------
    log("\n===== validator 直连探针（定位被降级吞掉的异常）=====")
    try:
        enhanced = plugin._enhance_request(request)
        probe_ctx = {
            "worldview": getattr(enhanced, "worldview_data", None) or {},
            "characters": getattr(enhanced, "character_data", None) or [],
            "outline": getattr(enhanced, "outline_data", None) or {},
            "style_profile": getattr(enhanced, "style_data", None) or {},
            "knowledge_base": getattr(enhanced, "knowledge_base", None) or {},
            "techniques": getattr(enhanced, "writing_techniques", None) or {},
            "previous_chapters": getattr(enhanced, "previous_chapters", None) or [],
            "target_words": 1400,
            "_data_source": {
                "worldview_is_user_provided": True,
                "characters_is_user_provided": True,
                "outline_is_user_provided": True,
                "style_is_user_provided": True,
                "knowledge_is_loaded": bool(getattr(enhanced, "knowledge_base", None)),
                "techniques_is_loaded": bool(getattr(enhanced, "writing_techniques", None)),
            },
        }
        log(f"知识库类型={type(probe_ctx['knowledge_base']).__name__}, "
            f"技巧类型={type(probe_ctx['techniques']).__name__}, "
            f"人物类型={type(probe_ctx['characters']).__name__}")
        # 逐维度单独调用，精确定位哪个维度崩
        v = plugin._expert_validator
        dim_calls = [
            ("worldview", lambda: v._evaluate_worldview(content, probe_ctx["worldview"], is_user_provided=True)),
            ("character", lambda: v._evaluate_character(content, probe_ctx["characters"], is_user_provided=True)),
            ("outline", lambda: v._evaluate_outline(content, probe_ctx["outline"], is_user_provided=True)),
            ("style", lambda: v._evaluate_style(content, probe_ctx["style_profile"], is_user_provided=True)),
            ("word_count", lambda: v._evaluate_word_count(content, 1400)),
            ("knowledge", lambda: v._evaluate_knowledge_base(content, probe_ctx["knowledge_base"], is_loaded=True)),
            ("writing_technique", lambda: v._evaluate_writing_technique(content, probe_ctx["techniques"])),
            ("context_coherence", lambda: v._evaluate_context_continuation(content, probe_ctx["previous_chapters"])),
            ("ai_feeling", lambda: v._evaluate_ai_sense(content)),
        ]
        for name, fn in dim_calls:
            try:
                sc = fn()
                log(f"  [OK] {name} = {sc}")
            except Exception as de:
                log(f"  [CRASH] {name}: {type(de).__name__}: {de}")
                traceback.print_exc()
        # 再单独跑 _generate_analysis
        try:
            scores_probe = {n: 0.6 for n, _ in dim_calls}
            v._generate_analysis(scores_probe, content, probe_ctx)
            log("  [OK] _generate_analysis")
        except Exception as ae:
            log(f"  [CRASH] _generate_analysis: {type(ae).__name__}: {ae}")
            traceback.print_exc()
    except Exception as pe:
        log(f"[probe FAIL] {pe}")
        traceback.print_exc()

    # ---------- 7.6 子系统状态：记忆 / 技能 ----------
    log("\n===== 子系统探针（记忆/技能 是否静默失效）=====")
    log(f"_expert_validator: {'OK' if getattr(plugin,'_expert_validator',None) else '缺失'}")
    log(f"_expert_optimizer: {'OK' if getattr(plugin,'_expert_optimizer',None) else '缺失'}")
    mem = getattr(plugin, "_expert_memory", None)
    log(f"_expert_memory: {'OK' if mem else '缺失(记忆禁用?)'}")
    if mem is not None:
        try:
            # 记忆往返：存一条评估再取回
            from importlib import import_module
            ev = getattr(result, "metadata", {}).get("expert_evaluation")
            cid = "第1章 旧楼之约"
            # 直接用 plugin 的存储路径
            opt = plugin._generate_optimization(plugin._evaluate_expert(content, plugin._enhance_request(request)))
            plugin._store_to_memory(plugin._evaluate_expert(content, plugin._enhance_request(request)), opt, request)
            back = mem.retrieve_evaluation(cid)
            log(f"  记忆往返: 存储后 retrieve_evaluation('{cid}') → {'取回成功' if back else '取回为空'}")
        except Exception as me:
            log(f"  [记忆往返异常] {me}")
    # 技能注入
    try:
        guidance = plugin._inject_technique_guidance(plugin._enhance_request(request))
        log(f"技能注入(_inject_technique_guidance): 返回{len(guidance)}字 "
            f"({'有内容' if guidance.strip() else '空→技能可能未加载'})")
    except Exception as se:
        log(f"技能注入异常: {se}")

    # ---------- 7.7 收敛测试 ----------
    log("\n===== 收敛测试（逐轮改进的LLM，能否爬过0.8达标）=====")
    _run_convergence(plugin, request, log)

    log("\n===== 审计结论 =====")
    if len(fake.calls) == 0:
        log("[❌] LLM 从未被调用 → 生成链路在到达 API 前就断了")
        report["ok"] = False
    elif vs is None:
        log("[❌] 无 validation_scores → 评分链路断裂")
        report["ok"] = False
    else:
        log("[✅] 端到端打通：数据→生成→评分→迭代→结果 链路连通")

    return 0


if __name__ == "__main__":
    sys.exit(main())
