#!/usr/bin/env python3
"""为所有插件添加签名

V2.1修复（2026-07-03，见 经验文档/14.0完全优化.md 遗留事项#1）：
- 原实现把 plugin.json 自身算进目录哈希，但签名写回 plugin.json 后文件内容改变
  → 任何签名一经写入立即自我失效（鸡生蛋缺陷），机制从未可能通过校验。
- 修复：哈希算法与 core/plugin_loader.py::PluginSignatureVerifier 完全一致——
  排除插件根目录的签名载体文件（plugin.json/plugin.sig）、排序遍历保证确定性、
  并把「去除 signature 字段后的 manifest 规范化序列化」纳入哈希以保护清单完整性。
- 直接复用校验器的哈希实现，杜绝两处算法漂移。

用法: python scripts/add_plugin_signatures.py
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# V2.1：直接复用校验器实现，签名与校验永远同一算法
from core.plugin_loader import PluginSignatureVerifier


def main() -> int:
    plugins_dir = PROJECT_ROOT / 'plugins'
    results = []
    failed = 0

    for plugin_dir in sorted(plugins_dir.iterdir()):
        if not (plugin_dir.is_dir() and not plugin_dir.name.startswith('__')):
            continue
        plugin_json = plugin_dir / 'plugin.json'
        if not plugin_json.exists():
            continue

        try:
            # 读取plugin.json
            with open(plugin_json, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 先写回带占位/旧签名无关——哈希已排除签名载体并只取
            # manifest去signature后的规范化内容，因此可先删旧签名再计算
            data.pop('signature', None)
            with open(plugin_json, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 计算签名（与加载器同一实现）
            signature = PluginSignatureVerifier._calculate_directory_hash(plugin_dir)

            # 写入签名
            data['signature'] = signature
            with open(plugin_json, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 立即回验，确保签名可通过校验（鸡生蛋缺陷的回归防线）
            ok, err = PluginSignatureVerifier.verify_plugin_signature(
                plugin_dir, plugin_dir.name
            )
            if ok:
                results.append(f'[OK] {plugin_dir.name}: {signature[:16]}...')
            else:
                failed += 1
                results.append(f'[FAIL] {plugin_dir.name}: 签名写入后校验不通过: {err}')
        except Exception as e:
            failed += 1
            results.append(f'[FAIL] {plugin_dir.name}: {e}')

    print('\n'.join(results))
    print(f'\n共处理 {len(results)} 个插件，失败 {failed} 个')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
