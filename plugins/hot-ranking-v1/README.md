# 热榜工具 V1

> **插件ID**: `hot-ranking-v1`
> **版本**: 1.0.0
> **类型**: 工具插件 (Tool)

---

## 用途

小说网站排行榜数据爬取和管理工具，支持番茄小说、起点中文网、晋江文学城等主流平台，为创作提供市场参考。

### 核心功能

- **多平台支持**: 番茄、起点、晋江等主流平台
- **排行榜爬取**: 获取热门作品排行数据
- **数据分析**: 分析热门作品特征和趋势
- **数据导出**: 导出排行榜数据为多种格式

---

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `platforms` | list | ["番茄", "起点"] | 启用的平台 |
| `cache_ttl` | int | 3600 | 缓存过期时间（秒） |
| `timeout` | int | 30 | 请求超时（秒） |
| `max_retries` | int | 3 | 最大重试次数 |

### 配置示例

```yaml
plugins:
  hot-ranking-v1:
    platforms:
      - "番茄"
      - "起点"
      - "晋江"
    cache_ttl: 3600
    timeout: 30
    max_retries: 3
```

---

## 使用示例

### 1. 获取排行榜

```python
from core.service_locator import ServiceLocator
from core.plugin_registry import PluginRegistry

# 获取插件
registry = ServiceLocator.get(PluginRegistry)
hot_ranking = registry.get_plugin("hot-ranking-v1")

# 获取番茄小说排行榜
ranking = hot_ranking.get_ranking(
    platform="番茄",
    category="玄幻",
    limit=50
)

print(f"获取到 {len(ranking.books)} 部作品")
for book in ranking.books[:10]:
    print(f"{book.rank}. {book.title} - {book.author}")
```

### 2. 多平台对比

```python
# 对比多个平台排行榜
comparison = hot_ranking.compare_platforms(
    platforms=["番茄", "起点", "晋江"],
    category="玄幻"
)

print("各平台TOP3:")
for platform, books in comparison.items():
    print(f"\n{platform}:")
    for book in books[:3]:
        print(f"  {book.title}")
```

### 3. 获取作品详情

```python
# 获取作品详细信息
detail = hot_ranking.get_book_detail(
    platform="起点",
    book_id="123456"
)

print(f"书名: {detail.title}")
print(f"作者: {detail.author}")
print(f"字数: {detail.word_count}")
print(f"分类: {detail.category}")
print(f"标签: {', '.join(detail.tags)}")
print(f"简介: {detail.description[:100]}...")
```

### 4. 分析热门趋势

```python
# 分析热门作品特征
analysis = hot_ranking.analyze_trends(
    platform="番茄",
    category="玄幻",
    top_n=100
)

print(f"热门题材: {', '.join(analysis.popular_themes[:5])}")
print(f"热门标签: {', '.join(analysis.popular_tags[:10])}")
print(f"平均字数: {analysis.avg_word_count}")
print(f"热门题材占比: {analysis.theme_distribution}")
```

### 5. 导出数据

```python
# 导出为CSV
hot_ranking.export(
    platform="起点",
    format="csv",
    output_path="排行榜/起点玄幻榜.csv"
)

# 导出为JSON
hot_ranking.export(
    platform="番茄",
    format="json",
    output_path="排行榜/番茄玄幻榜.json"
)
```

---

## 输入输出

### 输入

```python
{
    "platform": "番茄",  # 平台名称
    "category": "玄幻",  # 分类（可选）
    "limit": 50,        # 获取数量
    "use_cache": true   # 是否使用缓存
}
```

### 输出

```python
@dataclass
class RankingResult:
    platform: str              # 平台名称
    category: str              # 分类
    update_time: datetime      # 更新时间
    books: List[BookInfo]      # 书籍列表
    cache_hit: bool            # 是否命中缓存

@dataclass
class BookInfo:
    rank: int                  # 排名
    title: str                 # 书名
    author: str                # 作者
    word_count: int            # 字数
    category: str              # 分类
    tags: List[str]            # 标签
    description: str           # 简介
    cover_url: str             # 封面URL
    book_id: str               # 书籍ID

@dataclass
class TrendAnalysis:
    popular_themes: List[str]  # 热门题材
    popular_tags: List[str]    # 热门标签
    avg_word_count: int        # 平均字数
    theme_distribution: dict   # 题材分布
```

---

## 支持的平台

| 平台 | 分类支持 | 排行榜类型 |
|------|---------|-----------|
| 番茄小说 | 玄幻/都市/言情等 | 热榜/新书榜/完结榜 |
| 起点中文网 | 玄幻/奇幻/都市等 | 月票榜/推荐榜/收藏榜 |
| 晋江文学城 | 原创/衍生等 | 积分榜/收藏榜/点击榜 |

---

## 依赖

- 无外部插件依赖
- 需要网络访问

---

## 冲突

- `hot-ranking-v2`

---

## 权限要求

- `network.request`
- `file.read`
- `file.write`

---

## 注意事项

1. 爬取频率建议控制在每分钟1次
2. 缓存默认1小时，避免频繁请求
3. 部分平台可能需要登录态
4. 数据仅供参考，请遵守平台规则
5. 不要用于商业用途

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-03-21 | 初始版本，支持番茄/起点/晋江 |
