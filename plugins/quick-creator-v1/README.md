# 快捷创作生成器插件 V1

快速生成世界观、大纲、人设、关键情节等设定的插件。

## 功能特性

### 1. 世界观快速生成
- 基于关键词和参考文本
- 生成完整世界设定：地理、社会、势力、规则等
- 支持三种详细程度：快速、标准、详细

### 2. 章节大纲生成
- 基于主题和世界观
- 生成完整的章节规划
- 包含每章主要事件和字数建议

### 3. 人物设定生成
- 基于角色定位和世界观
- 生成立体丰满的人物形象
- 包含性格、背景、关系、成长弧线等

### 4. 关键情节生成
- 基于大纲和人物设定
- 生成开篇、转折、高潮、结局等关键情节
- 包含铺垫、发展、高潮、结局、伏笔等元素

### 5. 全部生成（统一入口）
- 一键生成所有设定
- 确保各设定间协调一致
- 自动处理依赖关系

## 使用方法

### 基本使用

```python
from plugins.quick_creator_v1 import QuickCreationPlugin
from core.models import QuickCreationRequest

# 创建插件实例
plugin = QuickCreationPlugin()
plugin.initialize(context)
plugin.set_api_client(openai_client)

# 生成世界观
worldview = plugin.generate_worldview(
    keywords=["修仙", "仙界", "灵气"],
    genre="仙侠",
    generation_type="standard"
)

# 生成大纲
outline = plugin.generate_outline(
    theme="少年修仙成神",
    worldview_summary="...",
    chapter_count=50
)

# 生成人物
character = plugin.generate_character(
    character_name="李明",
    role="主角",
    worldview_summary="..."
)

# 生成关键情节
plot = plugin.generate_plot(
    outline_summary="...",
    characters=["李明"],
    plot_type="高潮"
)
```

### 统一入口生成

```python
request = QuickCreationRequest(
    theme="少年修仙成神",
    genre="仙侠",
    worldview_keywords=["修仙", "仙界"],
    target_words=100000,
    chapter_count=50,
    character_names=["李明", "王芳"],
    include_worldview=True,
    include_outline=True,
    include_characters=True,
    include_plots=True,
    generation_type="standard"
)

result = plugin.generate_all(request)

if result.success:
    print("世界观:", result.worldview.world_name)
    print("大纲:", result.outline.content[:200])
    print("人物数量:", len(result.characters))
    print("情节数量:", len(result.plots))
```

## 生成详细程度

| 类型 | 说明 | Token限制 |
|------|------|-----------|
| quick | 快速生成，较少细节 | 2000-3000 |
| standard | 标准生成，平衡细节和速度 | 3000-5000 |
| detailed | 详细生成，丰富细节 | 5000-8000 |

## 生成顺序（全部生成模式）

1. **世界观** → 其他设定依赖此
2. **大纲** → 基于世界观生成
3. **人物** → 基于世界观生成
4. **情节** → 基于以上所有生成

这种顺序确保了各设定之间的协调一致性。

## 配置选项

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_generation_type | string | "standard" | 默认生成详细程度 |
| max_retries | integer | 3 | 最大重试次数 |
| timeout | integer | 60 | 超时时间（秒） |

## 注意事项

1. 使用前必须调用 `set_api_client()` 设置大模型客户端
2. 全部生成模式会按顺序生成，确保依赖关系正确
3. 生成结果会缓存在插件内部，可调用 `clear_cache()` 清除
4. 建议使用 `standard` 或 `detailed` 模式以获得更好的质量

## 版本历史

### v1.0.0 (2026-03-24)
- 初始版本
- 支持世界观、大纲、人设、情节生成
- 支持统一入口生成
- 支持三种生成详细程度
