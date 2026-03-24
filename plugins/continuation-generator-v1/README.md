# 续写生成器插件

智能小说续写功能，支持多种续写方向和上下文整合。

## 功能特性

1. **多种续写方向**
   - 自然续写：按情节自然发展
   - 特定方向：用户指定情节走向
   - 情感导向：侧重情感描写
   - 动作导向：侧重场景和动作
   - 对话导向：侧重人物对话

2. **上下文整合**
   - 章节大纲
   - 人物设定
   - 世界观设定
   - 风格档案
   - 前文章节参考

3. **多版本生成**
   - 支持生成多个版本供用户选择
   - 不同温度参数控制创意程度

4. **流式生成**
   - 支持实时输出
   - 逐步返回生成内容

5. **重新生成**
   - 创意模式（高温度）
   - 保守模式（低温度）
   - 不同变化

## 使用方法

### 基本续写

```python
from plugins.continuation_generator import ContinuationGeneratorPlugin
from core.models import ContinuationRequest

plugin = ContinuationGeneratorPlugin()
plugin.set_api_client(openai_client)

request = ContinuationRequest(
    starting_text="月光洒在窗台上，她轻轻叹了口气。",
    word_count=500,
    direction="natural"
)

result = plugin.generate_continuation(request)
print(result.text)
```

### 多版本生成

```python
results = plugin.generate_multiple_versions(request, num_versions=3)
for i, result in enumerate(results):
    print(f"版本{i+1}: {result.text[:100]}...")
```

### 流式生成

```python
for chunk in plugin.stream_continuation(request):
    print(chunk, end='', flush=True)
```

## 配置项

- `model`: 模型名称（默认：deepseek-chat）
- `temperature`: 默认温度（默认：0.8）
- `max_retries`: 最大重试次数（默认：3）

## 版本历史

- v1.0.0 (2026-03-24): 初始版本
