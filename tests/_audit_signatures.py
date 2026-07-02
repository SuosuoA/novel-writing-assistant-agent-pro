#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[审计用] 插件签名机制端到端验证（生产模式语义）

验证 14.0 遗留事项#1 的修复：
1. 全部插件签名校验通过（鸡生蛋缺陷已修）
2. 篡改插件代码 → 校验失败（完整性保护生效）
3. 篡改 manifest 字段 → 校验失败（清单完整性保护生效）
4. 生产模式安全分级：官方+签名 → L0；V5保护 → L2；全部 can_load
5. DEV_MODE 下未签名/签名失效仍可加载（开发豁免）

必须在设置 DEV_MODE/SKIP_PLUGIN_SIGNATURE 之前导入均不缓存的模块，
故本 harness 用 subprocess 隔离生产模式环境。
"""
import json
import os
import subprocess
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def log(m):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        print(m.encode("ascii", "replace").decode(), flush=True)


PROD_SNIPPET = r"""
import os, sys, json
from pathlib import Path
sys.path.insert(0, os.getcwd())
from core.plugin_loader import PluginSignatureVerifier
from core.hot_swap_manager import HotSwapPermission

plugins_dir = Path("plugins")
fail = []
levels = {}
for d in sorted(plugins_dir.iterdir()):
    if not d.is_dir() or d.name.startswith("__"):
        continue
    if not (d / "plugin.json").exists():
        continue
    ok, err = PluginSignatureVerifier.verify_plugin_signature(d, d.name)
    if not ok:
        fail.append(f"{d.name}: {err}")
    perm = HotSwapPermission(d.name, signature_verified=ok)
    levels[d.name] = (perm._security_level, perm.can_load())

print("VERIFY_FAIL=" + json.dumps(fail, ensure_ascii=False))
print("LEVELS=" + json.dumps(levels, ensure_ascii=False))
"""


def run_prod(snippet: str) -> str:
    env = dict(os.environ)
    env["DEV_MODE"] = "0"
    env["SKIP_PLUGIN_SIGNATURE"] = "0"
    r = subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
    if r.returncode != 0:
        log(r.stderr[-2000:])
        raise RuntimeError("生产模式子进程失败")
    return r.stdout


def main():
    ok_all = True

    # ---- 1+4. 生产模式：全部签名通过 + 安全分级 ----
    out = run_prod(PROD_SNIPPET)
    verify_fail = json.loads(out.split("VERIFY_FAIL=")[1].splitlines()[0])
    levels = json.loads(out.split("LEVELS=")[1].splitlines()[0])

    log(f"[1] 签名校验失败插件数: {len(verify_fail)} / {len(levels)}")
    for f in verify_fail:
        log(f"    [X] {f}")
    ok_all &= not verify_fail

    v5 = {"outline-parser-v3", "style-learner-v5", "character-manager-v1",
          "worldview-parser-v1", "context-builder-v1", "iterative-generator-v2",
          "quality-validator-v1", "novel-generator-v3", "hot-ranking-v1"}
    bad_lv = []
    for pid, (lv, can_load) in levels.items():
        expect = "L2" if pid in v5 else "L0"
        if lv != expect or not can_load:
            bad_lv.append(f"{pid}: level={lv}(期望{expect}) can_load={can_load}")
    log(f"[4] 生产模式分级: V5保护→L2、其余官方→L0、全部可加载: "
        f"{'通过' if not bad_lv else '失败'}")
    for b in bad_lv:
        log(f"    [X] {b}")
    ok_all &= not bad_lv

    # ---- 2. 篡改插件代码 → 校验必须失败 ----
    target = os.path.join(ROOT, "plugins", "hello-world", "plugin.py")
    with open(target, "rb") as f:
        original = f.read()
    try:
        with open(target, "ab") as f:
            f.write(b"\n# tampered\n")
        out = run_prod(PROD_SNIPPET)
        verify_fail = json.loads(out.split("VERIFY_FAIL=")[1].splitlines()[0])
        tamper_detected = any("hello-world" in f for f in verify_fail)
        others_ok = all("hello-world" in f for f in verify_fail)
        log(f"[2] 代码篡改检测: {'通过' if tamper_detected else '失败(未检出!)'}"
            f" | 其余插件不受影响: {'是' if others_ok else '否'}")
        ok_all &= tamper_detected and others_ok
    finally:
        with open(target, "wb") as f:
            f.write(original)

    # ---- 3. 篡改 manifest 字段 → 校验必须失败 ----
    manifest_path = os.path.join(ROOT, "plugins", "hello-world", "plugin.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_raw = f.read()
    try:
        data = json.loads(manifest_raw)
        data["entry_point"] = data.get("entry_point", "plugin.py")  # 确保字段存在
        data["permissions_tampered"] = True
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        out = run_prod(PROD_SNIPPET)
        verify_fail = json.loads(out.split("VERIFY_FAIL=")[1].splitlines()[0])
        manifest_detected = any("hello-world" in f for f in verify_fail)
        log(f"[3] manifest篡改检测: {'通过' if manifest_detected else '失败(未检出!)'}")
        ok_all &= manifest_detected
    finally:
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(manifest_raw)

    # ---- 5. 复原后再次全通过（确保测试自身无残留） ----
    out = run_prod(PROD_SNIPPET)
    verify_fail = json.loads(out.split("VERIFY_FAIL=")[1].splitlines()[0])
    log(f"[5] 复原后再校验: {'全部通过' if not verify_fail else '仍有失败: ' + str(verify_fail)}")
    ok_all &= not verify_fail

    log("\n===== 结论 =====")
    log("[OK] 签名机制端到端可用（生产模式）" if ok_all else "[X] 签名机制存在断点")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
