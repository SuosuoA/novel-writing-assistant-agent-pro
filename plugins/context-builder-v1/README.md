# 上下文构建器 V1

> **插件ID**: `context-builder-v1`
> **版本**: 1.0.0
> **类型**: 生成器插件 (Generator)

---

## 用途

智能上下文构建器，基于RAG（检索增强生成）和智能检索技术，为小说生成构建优化的提示词上下文。

### 核心功能

- **RAG检索**: 从历史章节中检索相关内容
- **记忆管理**: 管理长篇小说的上下文记忆
- **实体追踪**: 追踪人物、地点、事件等实体
- **提示词优化**: 构建结构化的生成提示词

---

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `memory_depth` | int | 5 | 记忆深度（前N章） |
| `cache_enabled` | bool | true | 是否启用缓存 |
| `entity_tracking` | bool | true | 是否追踪实体 |
| `chunk_size` | int | 500 | 文本分块大小 |

### 配置示例

```yaml
plugins:
  context-builder-v1:
    memory_depth: 5
    cache_enabled: true
    entity_tracking: true
    chunk_size: 500
```

---

## 使用示例

### 1. 基本用法

```python
from core.service_locator import ServiceLocator
from core.plugin_registry import PluginRegistry

# 获取插件
registry = ServiceLocator.get(PluginRegistry)
builder = registry.get_plugin("context-builder-v1")

# 构建上下文
context = builder.build(
    chapter_number=10,
    outline="第十章: 主角与反派首次对决",
    characters=["李明", "王芳", "反派A"],
    worldview_id="worldview-001"
)

print(f"上下文长度: {len(context.prompt)}")
print(f"相关实体: {context.entities}")
```

### 2. 获取记忆

```python
# 获取前N章记忆
memory = builder.get_memory(chapter_number=10, depth=5)

for chapter_memory in memory:
    print(f"第{chapter_memory.chapter}章:")
    print(f"  关键事件: {chapter_memory.key_events}")
    print(f"  出场人物: {chapter_memory.characters}")
```

### 3. 实体追踪

```python
# 追踪人物
entity_history = builder.track_entity(
    entity_name="李明",
    entity_type="character"
)

print(f"李明出场记录:")
for record in entity_history:
    print(f"  第{record.chapter}章: {record.action}")

# 追踪地点
location_history = builder.track_entity(
    entity_name="昆仑山",
    entity_type="location"
)
```

### 4. 清理缓存

```python
# 清理所有缓存
builder.clear_cache()

# 清理特定章节缓存
builder.clear_cache(chapter_number=5)
```

---

## 输入输出

### 输入

```python
{
    "chapter_number": 10,
    "outline": "第十章: 主角与反派首次对决",
    "characters": ["李明", "王芳", "反派A"],
    "worldview_id": "worldview-001",
    "style_profile": {...},  # 可选
    "special_requirements": [...]  # 可选
}
```

### 输出

```python
@dataclass
class BuildContext:
    prompt: str                    # 构建好的提示词
    entities: List[Entity]         # 相关实体列表
    memory_used: List[ChapterMemory]  # 使用的记忆
    cache_hit: bool                # 是否命中缓存
    build_time: float              # 构建耗时

@dataclass
class Entity:
    name: str
    type: str  # character/location/event
    relevance: float  # 相关度 0-1
    source_chapter: int

@dataclass
class ChapterMemory:
    chapter: int
    summary: str
    key_events: List[str]
    characters: List[str]
    word_count: int
```

---

## 依赖

- 无外部插件依赖
- 需要AI服务（RAG嵌入）

---

## 冲突

- 无

---

## 权限要求

- `file.read`
- `ai.call`

---

## 性能说明

| 操作 | 平均耗时 | 缓存命中 |
|------|---------|---------|
| 首次构建 | ~2秒 | - |
| 缓存命中 | ~50ms | 是 |
| 实体追踪 | ~100ms | - |

---

## 注意事项

1. memory_depth建议设置为3-5章，过大影响性能
2. 缓存结果保存在 `cache/context/` 目录
3. 实体追踪需要历史章节已解析
4. shutdown时会自动清理缓存

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-03-21 | 初始版本 |
