#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[审计用-临时] 快捷创作/续写/长篇检测/知识库验证 四条功能链冒烟（mock LLM）"""
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
        s.success, s.text, s.error, s.usage, s.tokens_used = True, t, None, {"total_tokens": len(t)}, len(t)


class _Fake:
    calls = 0
    def generate_text(s, prompt=None, config=None, messages=None, **kw):
        _Fake.calls += 1
        return _R("林越站在旧楼窗前，霓虹忽明忽暗。他冷静盘算着交易的每一步，苏晴的脚步声由远及近。" * 8 + "\n【本章完】")


def main():
    import core.ai_service_manager as aim
    aim.get_ai_service_manager = lambda: _Fake()

    from core.plugin_loader import get_plugin_loader
    from core.plugin_registry import get_plugin_registry
    loader = get_plugin_loader()
    loader._plugin_directories = [os.path.join(ROOT, "plugins")]
    loader._discovered_plugins = {}
    loader.discover_plugins(); loader.load_all()
    reg = get_plugin_registry()
    outcomes = {}

    # 1) 快捷创作
    try:
        from core.models import QuickCreationRequest
        qc = reg.get_plugin("quick-creator-v1")
        req = QuickCreationRequest(keywords="近未来都市悬疑 旧楼 交易 调查", genre="悬疑")
        r = qc.execute(req)
        ok = getattr(r, "success", None)
        outcomes["快捷创作"] = f"success={ok}, 内容字段={[a for a in ('worldview','outline','characters','content') if getattr(r, a, None)]}"
    except Exception as e:
        outcomes["快捷创作"] = f"CRASH: {type(e).__name__}: {str(e)[:80]}"
        traceback.print_exc()

    # 2) 续写
    try:
        from core.models import ContinuationRequest
        cg = reg.get_plugin("continuation-generator-v1")
        req = ContinuationRequest(starting_text="林越站在旧楼窗前，霓虹忽明忽暗。他知道那笔交易背后另有隐情。",
                                  direction="继续调查，引出神秘线人", word_count=500)
        r = cg.generate_continuation(req)
        outcomes["续写"] = f"success={getattr(r,'success',None)}, 字数={len(getattr(r,'text','') or '')}"
    except Exception as e:
        outcomes["续写"] = f"CRASH: {type(e).__name__}: {str(e)[:80]}"
        traceback.print_exc()

    # 3) 知识库验证
    try:
        kv = reg.get_plugin("knowledge-validator")
        scores = kv.validate("林越以雷火法门运转内力，灵气在经脉中流转，突破了瓶颈。",
                             {"knowledge_categories": ["wuxia"]})
        outcomes["知识库验证"] = f"total={getattr(scores,'total_score',None)}, 类型={type(scores).__name__}"
    except Exception as e:
        outcomes["知识库验证"] = f"CRASH: {type(e).__name__}: {str(e)[:80]}"
        traceback.print_exc()

    # 4) 长篇一致性检测
    try:
        from agents.consistency_checker_agent import ConsistencyCheckerAgent
        import inspect
        sig = inspect.signature(ConsistencyCheckerAgent.__init__)
        agent = ConsistencyCheckerAgent()
        r = agent.execute({
            "chapters": [
                {"title": "第1章", "content": "林越性格冷静，在旧楼等待苏晴。"},
                {"title": "第2章", "content": "林越暴躁地大喊大叫，完全失控。"},
            ],
            "characters": [{"name": "林越", "personality": "冷静、话不多"}],
            "worldview": {"rules": ["不允许超自然力量"]},
        })
        keys = list(r.keys())[:6] if isinstance(r, dict) else type(r).__name__
        outcomes["长篇检测"] = f"返回={keys}"
    except Exception as e:
        outcomes["长篇检测"] = f"CRASH: {type(e).__name__}: {str(e)[:100]}"
        traceback.print_exc()

    log("\n===== 四功能链冒烟结果 =====")
    for k, v in outcomes.items():
        log(f"  [{k}] {v}")
    log(f"LLM总调用: {_Fake.calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
