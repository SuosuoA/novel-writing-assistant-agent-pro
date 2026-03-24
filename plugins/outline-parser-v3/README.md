# 大纲解析器 V3

> **插件ID**: `outline-parser-v3`
> **版本**: 3.0.0
> **类型**: 分析器插件 (Analyzer)

---

## 用途

基于LangChain和LLM的智能大纲解析器，将Markdown格式的小说大纲转换为结构化数据。

### 核心功能

- **Markdown解析**: 解析标准Markdown格式的大纲文件
- **层次化解析**: 自动识别卷、章、节三级结构
- **LLM增强提取**: 使用大语言模型提取关键情节、人物、世界观信息
- **缓存优化**: 解析结果缓存，避免重复处理

---

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `cache_enabled` | bool | true | 是否启用解析缓存 |
| `cache_ttl` | int | 86400 | 缓存过期时间（秒） |
| `use_llm_enhancement` | bool | true | 是否使用LLM增强提取 |
| `model_name` | string | "deepseek-chat" | LLM模型名称 |
| `max_chapters` | int | 200 | 最大章节数限制 |

### 配置示例

```yaml
plugins:
  outline-parser-v3:
    cache_enabled: true
    cache_ttl: 86400
    use_llm_enhancement: true
    model_name: "deepseek-chat"
    max_chapters: 200
```

---

## 使用示例

### 1. 基本用法

```python
from core.service_locator import ServiceLocator
from core.plugin_registry import PluginRegistry

# 获取插件
registry = ServiceLocator.get(PluginRegistry)
parser = registry.get_plugin("outline-parser-v3")

# 解析大纲文件
result = parser.parse("大纲/我的小说大纲.md")

if result.success:
    print(f"解析成功，共 {len(result.chapters)} 章")
    for chapter in result.chapters:
        print(f"第{chapter.number}章: {chapter.title}")
```

### 2. 获取大纲结构

```python
# 获取大纲层次结构
structure = parser.get_outline_structure()

# structure 结构
# {
#     "volumes": [
#         {
#             "name": "第一卷",
#             "chapters": [
#                 {"number": 1, "title": "序章", "word_count": 3000},
#                 {"number": 2, "title": "初遇", "word_count": 3500}
#             ]
#         }
#     ],
#     "total_chapters": 50,
#     "total_words": 150000
# }
```

### 3. 提取关键信息

```python
# 提取情节关键点
key_plots = parser.extract_key_plots(chapter_number=5)

# 提取人物信息
characters = parser.extract_characters(chapter_number=5)

# 提取世界观设定
worldview = parser.extract_worldview(chapter_number=5)
```

---

## 输入输出

### 输入

Markdown格式的大纲文件，支持以下格式：

```markdown
# 第一卷 起源

## 第一章 序章

- 场景：古代王朝宫殿
- 人物：皇帝、太监
- 情节：王朝衰落的预兆

### 1.1 开篇

黎明时分，皇宫深处传来一声叹息...

## 第二章 初遇

...
```

### 输出

```python
@dataclass
class OutlineResult:
    success: bool
    chapters: List[ChapterInfo]
    volumes: List[VolumeInfo]
    total_chapters: int
    total_words: int
    cache_hit: bool
    parse_time: float

@dataclass
class ChapterInfo:
    number: int
    title: str
    volume: str
    summary: str
    word_count: int
    characters: List[str]
    key_plots: List[str]
```

---

## 依赖

- 无外部插件依赖
- 需要LLM服务（用于增强提取）

---

## 冲突

- `outline-parser-v1`
- `outline-parser-v2`

---

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `FileNotFoundError` | 大纲文件不存在 | 检查文件路径 |
| `ParseError` | Markdown格式错误 | 修正大纲格式 |
| `LLMError` | LLM服务不可用 | 检查API配置或禁用LLM增强 |

---

## 注意事项

1. 大纲文件建议使用UTF-8编码
2. 章节标题建议使用 `## 第X章 标题` 格式
3. 启用LLM增强会增加API调用，建议在首次解析时启用
4. 缓存结果保存在 `cache/outline/` 目录

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 3.0.0 | 2026-03-21 | 初始版本，基于LangChain重构 |
