#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[审计用-临时] 普通模式端到端数据流验证 harness

链路：novel-generator-v3 → context-builder-v1 + iterative-generator-v2 → quality-validator-v1
mock LLM，验证：插件链装配、生成循环、九维度评分桥接、weighted_total_score/passed 返回。

用法：python tests/_audit_e2e_normal.py
"""
import os
import sys
import traceback

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("DEV_MODE", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def log(m):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        print(m.encode("ascii", "replace").decode(), flush=True)


class _FakeResult:
    def __init__(self, text):
        self.success, self.text, self.error = True, text, None
        self.tokens_used = len(text)
        self.usage = {"total_tokens": len(text)}


class _FakeAIManager:
    def __init__(self):
        self.calls = 0
        base = (
            "夜色压在城西旧楼上，霓虹忽明忽暗。林越站在窗前，他性格冷静、话不多，"
            "盘算着那笔可疑交易的每一步。苏晴皱眉道：“你还在等？”她心直口快，藏不住情绪。"
            "林越笑了笑：“在等一个答案。”次日清晨他决定彻查交易源头，新的博弈开始了。"
        )
        self._text = base * 10 + "\n【本章完】"

    def generate_text(self, prompt=None, config=None, messages=None, **kw):
        self.calls += 1
        return _FakeResult(self._text)


def main():
    # 1) mock LLM 接缝（普通模式与专家模式同用此入口）
    import core.ai_service_manager as aim
    fake = _FakeAIManager()
    aim.get_ai_service_manager = lambda: fake
    log("[OK] 已 mock get_ai_service_manager")

    # 2) 通过 PluginLoader 真实加载全部插件（注册到 registry，装配依赖）
    from core.plugin_loader import get_plugin_loader
    from core.plugin_registry import get_plugin_registry
    loader = get_plugin_loader()
    loader._plugin_directories = [os.path.join(ROOT, "plugins")]
    loader._discovered_plugins = {}
    ids = loader.discover_plugins()
    results = loader.load_all()
    ok = sum(1 for r in results.values() if r.success)
    log(f"[OK] 插件加载 {ok}/{len(ids)}")

    registry = get_plugin_registry()
    gen = registry.get_plugin("novel-generator-v3")
    if gen is None:
        log("[FAIL] 注册表拿不到 novel-generator-v3")
        return 1
    log(f"[OK] novel-generator-v3 实例: {type(gen).__name__}")

    # 3) 构造 GenerationRequest（与 GUI _build_generation_request 同款字段）
    from core.models import GenerationRequest
    import uuid
    req = GenerationRequest(
        request_id=str(uuid.uuid4()),
        title="第1章",
        outline="林越在城西旧楼等待苏晴，两人就一笔可疑交易展开试探，林越决定次日彻查幕后。",
        word_count=1400,
        max_iterations=2,
        style_profile={"author_name": "测试", "style_tags": ["心理刻画", "节奏紧凑"],
                       "keywords": ["霓虹", "沉默", "博弈"]},
        character_profiles={"林越": {"name": "林越", "role": "主角", "personality": "冷静、话不多"},
                            "苏晴": {"name": "苏晴", "role": "女主", "personality": "心直口快"}},
        worldview_config={"name": "近未来都市",
                          "elements": [{"name": "城西旧楼"}, {"name": "霓虹"}],
                          "rules": ["不允许超自然力量"]},  # 字符串规则——曾是专家模式崩溃点
    )
    req.chapter_outline = "林越在城西旧楼等待苏晴，试探交易，决定彻查幕后。"
    req.chapter_number = 1
    req.previous_chapter_text = ""
    req.knowledge_categories = []
    req.writing_techniques = []

    # 4) 执行生成
    try:
        result = gen.generate(req)
    except Exception as e:
        log(f"[FAIL] generate() 异常: {e}")
        traceback.print_exc()
        return 1

    log(f"\nLLM 调用次数: {fake.calls}")
    content = getattr(result, "content", "") or ""
    log(f"内容长度: {len(content)} | 含【本章完】: {'【本章完】' in content}")

    meta = getattr(result, "metadata", {}) or {}
    wts = meta.get("weighted_total_score")
    passed = meta.get("passed")
    log(f"weighted_total_score: {wts} | passed: {passed}")

    vs = getattr(result, "validation_scores", None)
    if vs is not None:
        dims = {}
        for a in dir(vs):
            if a.endswith("_score") and not a.startswith("_"):
                v = getattr(vs, a, None)
                if isinstance(v, (int, float)):
                    dims[a] = round(float(v), 3)
        log(f"维度分: {dims}")
        vals = [v for k, v in dims.items() if k != 'total_score']
        distinct = len(set(vals))
        log(f"维度不同值数: {distinct}")

    log("\n===== 结论 =====")
    if fake.calls == 0:
        log("[X] LLM 未被调用 → 普通模式生成链断裂")
        return 1
    if wts is None:
        log("[!] metadata 无 weighted_total_score → ADR-010 插件层评分归属未落实")
    if content and fake.calls > 0 and wts is not None:
        log("[OK] 普通模式端到端连通：请求→生成循环→九维度评分→weighted_total_score/passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
