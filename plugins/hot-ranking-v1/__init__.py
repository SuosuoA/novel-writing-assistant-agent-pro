"""
热榜工具插件 V1.0

版本: 1.0.0
创建日期: 2026-03-23
迁移来源: V5 scripts/hot_ranking/

功能:
- 番茄小说热榜爬取（SSR JSON解析）
- 起点中文网热榜爬取（移动版解析）
- 晋江文学城热榜爬取（月票榜/收藏榜）
- 聚合数据生成（题材榜/类型榜/作家榜）
- 数据缓存管理（10分钟有效期）

核心规则（强制保护）:
1. 热榜模块禁止破坏性修改
2. 保留真实数据标记（is_real=True）
3. 保留降级数据机制
4. 保留V5热度归一化算法

参考文档:
- 《项目总体架构设计说明书V1.2》第四章
- 《插件接口定义V2.1》
"""

from .plugin import HotRankingPlugin, get_plugin_class, register_plugin

__all__ = ['HotRankingPlugin', 'get_plugin_class', 'register_plugin']
__version__ = '1.0.0'
